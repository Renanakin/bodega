#!/bin/sh
# backup.sh - Backup diario de Postgres para bodegaje.
#
# Diseño (Fase 7 / Recomendaciones go-live):
# - Corre dentro del contenedor `backup` (mismo docker-compose).
# - Volumen dedicado `postgres_backups` montado en /backups.
# - Dump en formato custom (-Fc) -> permite restore selectivo
#   (pg_restore --table=...) si solo quieres una tabla.
# - Compresion adicional con gzip -> ~1/4 del tamaño plano.
# - Rotacion: conserva los ultimos 7 dias (BACKUP_RETENTION_DAYS).
# - Verificacion: el dump debe ser > MIN_SIZE_BYTES (default 1KB) para
#   considerarse valido. Si falla, exit != 0 y supercronic lo logea.
# - Restauracion: ver docs/propuesta_ejecutables/cheatsheet.md
#   seccion "Restaurar backup de Postgres".
#
# Variables (env, tomadas del docker-compose):
#   POSTGRES_HOST     - host de la BD (default: db)
#   POSTGRES_PORT     - puerto (default: 5432)
#   POSTGRES_DB       - nombre BD (default: bodegaje)
#   POSTGRES_USER     - usuario (default: bodegaje)
#   PGPASSWORD        - password (inyectado del .env via docker secrets
#                       o env_file, NUNCA hardcoded)
#   BACKUP_DIR        - dir destino (default: /backups)
#   BACKUP_RETENTION_DAYS - dias a conservar (default: 7)
#   MIN_SIZE_BYTES    - tamaño minimo valido (default: 1024)

set -e

POSTGRES_HOST="${POSTGRES_HOST:-db}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-bodegaje}"
POSTGRES_USER="${POSTGRES_USER:-bodegaje}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
MIN_SIZE_BYTES="${MIN_SIZE_BYTES:-1024}"

TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
BACKUP_FILE="${BACKUP_DIR}/bodegaje-${TIMESTAMP}.dump.gz"
LATEST_LINK="${BACKUP_DIR}/bodegaje-latest.dump.gz"

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

# Asegurar dir existe (cuando el volumen se monta vacio la primera vez)
mkdir -p "${BACKUP_DIR}"

log "Iniciando backup: ${POSTGRES_DB}@${POSTGRES_HOST}:${POSTGRES_PORT} -> ${BACKUP_FILE}"

# pg_dump -Fc (custom) + gzip.
# -Fc es mas eficiente que -Fp y permite pg_restore selectivo.
START_TS=$(date +%s)

if ! pg_dump \
    -h "${POSTGRES_HOST}" \
    -p "${POSTGRES_PORT}" \
    -U "${POSTGRES_USER}" \
    -d "${POSTGRES_DB}" \
    -Fc \
    --no-owner \
    --no-privileges \
    --verbose \
    2>/tmp/pg_dump_err.log | gzip > "${BACKUP_FILE}"; then
    log "ERROR: pg_dump fallo. stderr:"
    cat /tmp/pg_dump_err.log
    rm -f "${BACKUP_FILE}"
    exit 1
fi

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))
SIZE=$(stat -c %s "${BACKUP_FILE}" 2>/dev/null || stat -f %z "${BACKUP_FILE}")

log "Backup completado en ${DURATION}s. Tamaño: ${SIZE} bytes."

# Validacion: tamaño minimo razonable
if [ "${SIZE}" -lt "${MIN_SIZE_BYTES}" ]; then
    log "ERROR: backup demasiado pequeño (${SIZE} < ${MIN_SIZE_BYTES} bytes). Sospechoso."
    rm -f "${BACKUP_FILE}"
    exit 2
fi

# Validacion 2: gzip realmente descomprime OK
if ! gzip -t "${BACKUP_FILE}" 2>/dev/null; then
    log "ERROR: gzip integridad fallida en ${BACKUP_FILE}"
    rm -f "${BACKUP_FILE}"
    exit 3
fi

# Symlink "latest" -> el backup mas reciente
ln -sfn "${BACKUP_FILE}" "${LATEST_LINK}"

# Rotacion: borrar backups con mas de N dias
DELETED=$(find "${BACKUP_DIR}" -maxdepth 1 -name "bodegaje-*.dump.gz" -mtime "+${BACKUP_RETENTION_DAYS}" -type f -delete -print | wc -l)
if [ "${DELETED}" -gt 0 ]; then
    log "Rotacion: ${DELETED} backup(s) > ${BACKUP_RETENTION_DAYS}d eliminados."
fi

# Listar backups actuales
COUNT=$(ls -1 "${BACKUP_DIR}"/bodegaje-*.dump.gz 2>/dev/null | wc -l)
TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1)
log "Estado final: ${COUNT} backup(s), ${TOTAL_SIZE} total en ${BACKUP_DIR}"

exit 0
