#!/bin/sh
# healthcheck.sh - Verifica que el ultimo backup es reciente (< 25h).
# Si no hay backup o es muy viejo, exit 1 y docker marca el contenedor unhealthy.

set -e

BACKUP_DIR="${BACKUP_DIR:-/backups}"
MAX_AGE_HOURS=25

LATEST=$(ls -1t "${BACKUP_DIR}"/bodegaje-*.dump.gz 2>/dev/null | head -1)

if [ -z "${LATEST}" ]; then
    echo "FAIL: no hay backups en ${BACKUP_DIR}"
    exit 1
fi

# stat -c %Y -> epoch del mtime
MTIME=$(stat -c %Y "${LATEST}")
NOW=$(date +%s)
AGE_SEC=$((NOW - MTIME))
MAX_SEC=$((MAX_AGE_HOURS * 3600))

if [ "${AGE_SEC}" -gt "${MAX_SEC}" ]; then
    echo "FAIL: ultimo backup tiene $((AGE_SEC / 3600))h (max ${MAX_AGE_HOURS}h). Archivo: ${LATEST}"
    exit 1
fi

echo "OK: ultimo backup tiene $((AGE_SEC / 3600))h. Archivo: $(basename ${LATEST})"
exit 0
