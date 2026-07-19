#!/usr/bin/env bash
# =============================================================================
# pre-deploy-check.sh — Verificaciones previas al deploy (Fase 10)
# =============================================================================
# Uso: ./infra/scripts/pre-deploy-check.sh [production|staging|local]
# Exit code: 0 si todos los checks pasan, != 0 si alguno falla.
#
# Checks (10):
#   1. No hay secretos en el diff staged
#   2. Migraciones son archivos numerados (0001_init.sql, 0002_*.sql, ...)
#   3. Tests unitarios pasan
#   4. docker compose config valido
#   5. nginx config valido (via docker run nginx:alpine nginx -t)
#   6. Archivo .env existe
#   7. JWT_SECRET >= 32 caracteres
#   8. SECRET_KEY >= 32 caracteres (en produccion)
#   9. Puerto 80 no esta ocupado (en produccion)
#   10. Disco tiene > 1GB libre
# =============================================================================
set -euo pipefail

ENVIRONMENT="${1:-production}"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() { echo -e "  ${GREEN}[OK]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; FAILED=1; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }

FAILED=0

echo "============================================================"
echo "PRE-DEPLOY CHECKS ($ENVIRONMENT)"
echo "============================================================"
echo

# --- Check 1: No hay secretos en el diff staged ------------------------
echo -n "[1/10] Verificando que no hay secretos en el diff staged... "
if git diff --staged 2>/dev/null | grep -E "(SECRET_KEY|JWT_SECRET|POSTGRES_PASSWORD|SMTP_PASSWORD|SENTRY_DSN)\s*=" 2>/dev/null | grep -v "^\+\s*#" | grep -v "=__" >/dev/null 2>&1; then
    fail "Detectados secretos reales en el diff staged (placeholders OK)"
    git diff --staged | grep -E "(SECRET_KEY|JWT_SECRET|POSTGRES_PASSWORD|SMTP_PASSWORD|SENTRY_DSN)\s*=" | head -5
else
    pass "Sin secretos en el diff staged"
fi

# --- Check 2: Migraciones son archivos numerados ----------------------
echo -n "[2/10] Verificando estructura de migraciones... "
cd "$REPO_ROOT"
MIG_COUNT=$(ls db/migrations/0*.sql 2>/dev/null | wc -l)
if [ "$MIG_COUNT" -lt 1 ]; then
    fail "No hay migraciones numeradas (esperado: db/migrations/0*.sql)"
else
    pass "$MIG_COUNT archivos de migracion encontrados"
fi

# --- Check 3: Tests unitarios pasan -----------------------------------
echo "[3/10] Corriendo tests unitarios (puede tardar ~1 min)..."
cd "$REPO_ROOT/apps/api"
if python -m pytest tests/unit -q --no-header --tb=line -x 2>&1 | tail -5; then
    pass "Tests unitarios OK"
else
    fail "Tests unitarios fallaron"
fi

# --- Check 4: docker compose config valido ----------------------------
echo -n "[4/10] Verificando docker-compose config... "
cd "$REPO_ROOT"
if command -v docker >/dev/null 2>&1; then
    COMPOSE_FILES="-f infra/docker/docker-compose.yml"
    case "$ENVIRONMENT" in
        production) COMPOSE_FILES="$COMPOSE_FILES -f infra/docker/compose.production.yml" ;;
        staging)    COMPOSE_FILES="$COMPOSE_FILES -f infra/docker/compose.staging.yml" ;;
        local)      COMPOSE_FILES="$COMPOSE_FILES -f infra/docker/compose.local.yml" ;;
    esac
    if docker compose $COMPOSE_FILES config -q 2>/dev/null; then
        pass "docker compose config valido"
    else
        fail "docker compose config invalido"
        docker compose $COMPOSE_FILES config 2>&1 | head -10
    fi
else
    warn "docker no instalado, saltando check"
fi

# --- Check 5: nginx config valido -------------------------------------
echo -n "[5/10] Verificando nginx config... "
NGINX_CONF="infra/docker/nginx/conf.d/${ENVIRONMENT}.conf"
if [ ! -f "$NGINX_CONF" ]; then
    NGINX_CONF="infra/docker/nginx/conf.d/default.conf"
fi
if command -v docker >/dev/null 2>&1; then
    if docker run --rm -v "$REPO_ROOT:/cfg:ro" nginx:alpine \
        sh -c "cp /cfg/$NGINX_CONF /etc/nginx/conf.d/default.conf && nginx -t" 2>&1 | tail -5; then
        pass "Nginx config valido"
    else
        fail "Nginx config invalido"
    fi
elif command -v nginx >/dev/null 2>&1; then
    if nginx -t -c "$REPO_ROOT/$NGINX_CONF" 2>&1 | tail -3; then
        pass "Nginx config valido (nginx local)"
    else
        fail "Nginx config invalido"
    fi
else
    warn "docker y nginx no disponibles, saltando check"
fi

# --- Check 6: .env existe ---------------------------------------------
echo -n "[6/10] Verificando que existe .env... "
cd "$REPO_ROOT"
ENV_FILE=".env.$ENVIRONMENT"
[ "$ENVIRONMENT" = "local" ] && ENV_FILE=".env.development"

if [ -f "$ENV_FILE" ]; then
    pass "Archivo $ENV_FILE existe"
else
    fail "Archivo $ENV_FILE no existe. Crear desde infra/.env.example."
fi

# --- Check 7: JWT_SECRET >= 32 chars ----------------------------------
echo -n "[7/10] Verificando JWT_SECRET >= 32 caracteres... "
if [ -f "$ENV_FILE" ]; then
    JWT_SECRET=$(grep -E "^JWT_SECRET=" "$ENV_FILE" | cut -d= -f2-)
    if [ -z "$JWT_SECRET" ] || [ "$JWT_SECRET" = "__GENERAR_CON_python_secrets_token_urlsafe_32__" ]; then
        fail "JWT_SECRET es placeholder o vacio"
    elif [ "${#JWT_SECRET}" -lt 32 ]; then
        fail "JWT_SECRET tiene solo ${#JWT_SECRET} chars (minimo 32)"
    else
        pass "JWT_SECRET tiene ${#JWT_SECRET} chars"
    fi
else
    warn "$ENV_FILE no existe, saltando"
fi

# --- Check 8: SECRET_KEY >= 32 chars (produccion) ---------------------
echo -n "[8/10] Verificando SECRET_KEY >= 32 caracteres (produccion)... "
if [ "$ENVIRONMENT" = "production" ]; then
    if [ -f "$ENV_FILE" ]; then
        SECRET_KEY=$(grep -E "^SECRET_KEY=" "$ENV_FILE" | cut -d= -f2-)
        if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "__GENERAR_CON_python_secrets_token_urlsafe_32_OTRO__" ]; then
            fail "SECRET_KEY es placeholder o vacio (REQUERIDO en produccion)"
        elif [ "${#SECRET_KEY}" -lt 32 ]; then
            fail "SECRET_KEY tiene solo ${#SECRET_KEY} chars (minimo 32)"
        else
            pass "SECRET_KEY tiene ${#SECRET_KEY} chars"
        fi
    else
        warn "$ENV_FILE no existe, saltando"
    fi
else
    pass "Check solo aplica a production (skipped para $ENVIRONMENT)"
fi

# --- Check 9: Puerto 80 no ocupado (produccion) -----------------------
echo -n "[9/10] Verificando puerto 80 libre (produccion)... "
if [ "$ENVIRONMENT" = "production" ]; then
    if command -v ss >/dev/null 2>&1; then
        if ss -tlnp 2>/dev/null | grep -E ":80\s" | grep -v ":8080" >/dev/null; then
            warn "Puerto 80 esta ocupado (verificar que sea nginx, no otro proceso)"
            ss -tlnp 2>/dev/null | grep -E ":80\s" | head -3
        else
            pass "Puerto 80 libre"
        fi
    else
        warn "ss no instalado, saltando check"
    fi
else
    pass "Check solo aplica a production (skipped para $ENVIRONMENT)"
fi

# --- Check 10: Disco > 1GB libre --------------------------------------
echo -n "[10/10] Verificando espacio en disco (>1GB libre)... "
if command -v df >/dev/null 2>&1; then
    FREE_KB=$(df -k / | awk 'NR==2 {print $4}')
    if [ -n "$FREE_KB" ] && [ "$FREE_KB" -gt 1048576 ]; then
        FREE_GB=$(echo "scale=2; $FREE_KB / 1048576" | bc 2>/dev/null || echo "?")
        pass "Disco tiene ${FREE_GB}GB libres"
    else
        fail "Disco tiene < 1GB libre (FREE_KB=$FREE_KB)"
    fi
else
    warn "df no instalado, saltando check"
fi

# --- Resumen -----------------------------------------------------------
echo
echo "============================================================"
if [ "$FAILED" -eq 0 ]; then
    echo -e "${GREEN}OK: todos los checks pasaron. Listo para deploy.${NC}"
    exit 0
else
    echo -e "${RED}FALLO: hay checks pendientes. NO hacer deploy hasta resolver.${NC}"
    exit 1
fi
