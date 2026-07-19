#!/usr/bin/env bash
# =============================================================================
# check-env-isolation.sh (Regla de Oro R2)
# =============================================================================
# Verifica que los secretos no se compartan entre entornos.
# Falla (exit 1) si un valor aparece idéntico en 2+ archivos .env.
#
# Uso:
#   bash infra/scripts/check-env-isolation.sh
#
# Variables chequeadas (sensible a mayúsculas):
#   - JWT_SECRET
#   - DATABASE_URL
#   - REDIS_URL
#   - SMTP_PASSWORD
#
# Excluye archivos .example (plantillas) y archivos en .gitignore.
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILES=(
  "$REPO_ROOT/.env.development"
  "$REPO_ROOT/.env.staging"
  "$REPO_ROOT/.env.production"
)

SECRETS_TO_CHECK=(
  "JWT_SECRET"
  "SECRET_KEY"
  "POSTGRES_PASSWORD"
  "DATABASE_URL"
  "REDIS_URL"
  "SENTRY_DSN"
  "SMTP_PASSWORD"
)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Check de aislamiento de entornos (R2) ===${NC}"
echo ""

# Verificar que los archivos .env (no .example) existan
echo "Archivos a verificar:"
for env_file in "${ENV_FILES[@]}"; do
  if [[ ! -f "$env_file" ]]; then
    echo -e "  ${YELLOW}⚠${NC} $env_file no existe (saltando)"
  else
    echo -e "  ${GREEN}✓${NC} $env_file"
  fi
done
echo ""

errors=0

for secret_name in "${SECRETS_TO_CHECK[@]}"; do
  echo -n "Verificando $secret_name... "

  declare -A seen_values
  duplicates=0

  for env_file in "${ENV_FILES[@]}"; do
    if [[ ! -f "$env_file" ]]; then
      continue
    fi

    # Extraer el valor (ignorar comentarios y líneas vacías)
    value=$(grep -E "^${secret_name}=" "$env_file" 2>/dev/null | head -1 | cut -d'=' -f2- | sed 's/^["\x27]\|["\x27]$//g' || true)

    if [[ -z "$value" ]]; then
      continue
    fi

    # Si el valor es un placeholder CHANGE_ME, ignorar
    if [[ "$value" == CHANGE_ME* ]] || [[ "$value" == "" ]]; then
      continue
    fi

    # Verificar si ya vimos este valor
    if [[ -n "${seen_values[$value]:-}" ]]; then
      env_name=$(basename "$env_file")
      other_env=$(basename "${seen_values[$value]}")
      echo -e "${RED}✗ DUPLICADO${NC}"
      echo -e "  ${RED}El mismo valor de $secret_name aparece en: $other_env y $env_name${NC}"
      errors=$((errors + 1))
      duplicates=$((duplicates + 1))
    else
      seen_values[$value]="$env_file"
    fi
  done

  if [[ $duplicates -eq 0 ]]; then
    echo -e "${GREEN}✓ OK${NC}"
  fi
done

echo ""
if [[ $errors -gt 0 ]]; then
  echo -e "${RED}=== FALLO: $errors secreto(s) compartido(s) entre entornos ===${NC}"
  echo -e "${RED}Cada entorno (dev/staging/prod) debe tener secretos ÚNICOS.${NC}"
  echo -e "${RED}Edita los archivos .env.* y asigna valores diferentes.${NC}"
  exit 1
fi

echo -e "${GREEN}=== OK: todos los secretos son únicos por entorno ===${NC}"
exit 0
