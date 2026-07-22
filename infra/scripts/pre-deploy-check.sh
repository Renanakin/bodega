#!/usr/bin/env bash
# =============================================================================
# pre-deploy-check.sh — Verificaciones previas al deploy (Fase 10 + C2)
# =============================================================================
# Uso: ./infra/scripts/pre-deploy-check.sh [production|staging|local]
# Exit code: 0 si todos los checks pasan, != 0 si alguno falla.
#
# Checks (12 — v2 con C2.6):
#   1. No hay secretos en el diff staged
#   2. Migraciones son archivos numerados (0001_init.sql, 0002_*.sql, ...)
#   3. Tests unitarios pasan
#   4. docker compose config valido
#   5. nginx config valido (via docker run nginx:alpine nginx -t)
#   6. Archivo .env existe
#   7. JWT_SECRET >= 32 caracteres
#   8. SECRET_KEY >= 32 caracteres (en produccion)
#   9. Puerto 80 no esta ocupado (en produccion)
#  10. Disco tiene > 1GB libre
#  11. C2.1: Hay un backup reciente (<25h) de Postgres
#  12. C2.3: El restore E2E fue exitoso en los ultimos 7 dias
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
echo "PRE-DEPLOY CHECKS ($ENVIRONMENT) - v2 con C2"
echo "============================================================"
echo

# --- Check 1: No hay secretos en el diff staged ------------------------
echo -n "[1/12] Verificando que no hay secretos en el diff staged... "
if git diff --staged 2>/dev/null | grep -E "(SECRET_KEY|JWT_SECRET|POSTGRES_PASSWORD|SMTP_PASSWORD|SENTRY_DSN)\s*=" 2>/dev/null | grep -v "^\+\s*#" | grep -v "=__" >/dev/null 2>&1; then
    fail "Detectados secretos reales en el diff staged (placeholders OK)"
    git diff --staged | grep -E "(SECRET_KEY|JWT_SECRET|POSTGRES_PASSWORD|SMTP_PASSWORD|SENTRY_DSN)\s*=" | head -5
else
    pass "Sin secretos en el diff staged"
fi

# --- Check 2: Migraciones son archivos numerados ----------------------
echo -n "[2/12] Verificando estructura de migraciones... "
cd "$REPO_ROOT"
MIG_COUNT=$(ls db/migrations/0*.sql 2>/dev/null | wc -l)
if [ "$MIG_COUNT" -lt 1 ]; then
    fail "No hay migraciones numeradas (esperado: db/migrations/0*.sql)"
else
    pass "$MIG_COUNT archivos de migracion encontrados"
fi

# --- Check 3: Tests unitarios pasan -----------------------------------
echo "[3/12] Corriendo tests unitarios (puede tardar ~1 min)..."
cd "$REPO_ROOT/apps/api"
PYTHON_BIN="$(command -v python3 || command -v python || command -v py)"
if [ -z "$PYTHON_BIN" ]; then
    fail "No se encontro Python (python3, python, ni py en PATH)"
elif "$PYTHON_BIN" -m pytest tests/unit -q --no-header --tb=line -x 2>&1 | tail -5; then
    pass "Tests unitarios OK"
else
    fail "Tests unitarios fallaron"
fi

# --- Check 4: docker compose config valido ----------------------------
echo -n "[4/12] Verificando docker-compose config... "
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
echo -n "[5/12] Verificando nginx config... "
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
echo -n "[6/12] Verificando que existe .env... "
cd "$REPO_ROOT"
ENV_FILE=".env.$ENVIRONMENT"
[ "$ENVIRONMENT" = "local" ] && ENV_FILE=".env.development"

if [ -f "$ENV_FILE" ]; then
    pass "Archivo $ENV_FILE existe"
else
    fail "Archivo $ENV_FILE no existe. Crear desde infra/.env.example."
fi

# --- Check 7: JWT_SECRET >= 32 chars ----------------------------------
echo -n "[7/12] Verificando JWT_SECRET >= 32 caracteres... "
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
echo -n "[8/12] Verificando SECRET_KEY >= 32 caracteres (produccion)... "
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
echo -n "[9/12] Verificando puerto 80 libre (produccion)... "
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
echo -n "[10/12] Verificando espacio en disco (>1GB libre)... "
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

# --- Check 11 (C2.1): Backup reciente de Postgres --------------------
echo -n "[11/12] Verificando que existe un backup reciente (<25h)... "
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/bodegaje}"
if [ -d "$BACKUP_DIR" ]; then
    LATEST=$(find "$BACKUP_DIR" -name "bodegaje-*.sql.gz" -type f -mtime -1 2>/dev/null | head -1)
    if [ -z "$LATEST" ]; then
        if [ "$ENVIRONMENT" = "production" ]; then
            fail "No hay backup en las ultimas 25h en $BACKUP_DIR (bloqueante en produccion)"
        else
            warn "No hay backup reciente en $BACKUP_DIR (recomendable)"
        fi
    else
        SIZE=$(du -h "$LATEST" | cut -f1)
        pass "Backup reciente: $(basename $LATEST) ($SIZE)"
    fi
else
    if [ "$ENVIRONMENT" = "production" ]; then
        fail "Directorio $BACKUP_DIR no existe (bloqueante en produccion)"
    else
        warn "Directorio $BACKUP_DIR no existe (recomendable)"
    fi
fi

# --- Check 12 (C2.3): Restore E2E reciente ----------------------------
echo -n "[12/12] Verificando que el restore E2E fue exitoso en los ultimos 7 dias... "
RESTORE_LOG_DIR="${RESTORE_LOG_DIR:-$REPO_ROOT/.restore-logs}"
if [ -d "$RESTORE_LOG_DIR" ]; then
    LATEST_LOG=$(find "$RESTORE_LOG_DIR" -name "restore-*.log" -type f -mtime -7 2>/dev/null | head -1)
    if [ -z "$LATEST_LOG" ]; then
        if [ "$ENVIRONMENT" = "production" ]; then
            fail "No hay log de restore E2E en los ultimos 7 dias (bloqueante en produccion)"
        else
            warn "No hay log de restore E2E reciente (recomendable)"
        fi
    else
        # Verificar que el ultimo log dice PASS
        if grep -q "PASS: Todas las validaciones" "$LATEST_LOG" 2>/dev/null; then
            pass "Restore E2E OK en $(basename $LATEST_LOG)"
        else
            fail "Ultimo restore E2E no fue exitoso: $(basename $LATEST_LOG)"
        fi
    fi
else
    if [ "$ENVIRONMENT" = "production" ]; then
        warn "Directorio $RESTORE_LOG_DIR no existe. Crear con test-backup-restore.ps1"
    else
        warn "Restore E2E no probado aun. Ejecutar test-backup-restore.ps1"
    fi
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
