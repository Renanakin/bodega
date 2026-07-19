#!/usr/bin/env bash
# =============================================================================
# restore-postgres.sh — Restaura un backup a una BD (Fase 10)
# =============================================================================
# Uso:
#   ./restore-postgres.sh <backup-file>                         # restaura a BD `bodegaje`
#   ./restore-postgres.sh <backup-file> --target-db <nombre>    # restaura a otra BD
#   ./restore-postgres.sh --list                                # lista backups disponibles
#
# Precauciones:
#   - El restore SOBREESCRIBE la BD destino. Pide confirmacion interactiva.
#   - Si la BD destino tiene conexiones activas, se sugiere cerrarlas primero
#     (el restore usa DROP DATABASE que falla si hay conexiones).
#
# Variables de entorno:
#   POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, PGPASSWORD
# =============================================================================
set -euo pipefail

# --- Modo --list: listar backups disponibles ---------------------------
if [ "${1:-}" = "--list" ]; then
    BACKUP_DIR="${BACKUP_DIR:-/var/backups/bodegaje}"
    if [ ! -d "$BACKUP_DIR" ]; then
        echo "ERROR: directorio $BACKUP_DIR no existe" >&2
        exit 1
    fi
    echo "Backups disponibles en $BACKUP_DIR:"
    echo "  Timestamp          Tamano     Edad"
    echo "  -----------------  ---------  ----"
    find "$BACKUP_DIR" -name "bodegaje-*.sql.gz" -type f -printf "  %f  %s bytes  %TD %TH:%TM\n" 2>/dev/null | sort -r | head -30
    exit 0
fi

BACKUP_FILE="${1:?Uso: $0 <backup-file> [--target-db <nombre>]}"
shift

TARGET_DB="bodegaje"
while [ $# -gt 0 ]; do
    case "$1" in
        --target-db) TARGET_DB="$2"; shift 2 ;;
        --target-db=*) TARGET_DB="${1#--target-db=}"; shift ;;
        --help|-h)
            sed -n '2,20p' "$0"
            exit 0
            ;;
        *) echo "ERROR: argumento desconocido: $1" >&2; exit 2 ;;
    esac
done

# --- Validaciones previas ----------------------------------------------
if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: archivo de backup no existe: $BACKUP_FILE" >&2
    exit 1
fi

if ! command -v pg_restore >/dev/null 2>&1; then
    echo "ERROR: pg_restore no esta en PATH. Instalar postgresql-client." >&2
    exit 1
fi

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-bodegaje}"

# --- Confirmacion explicita --------------------------------------------
echo "ADVERTENCIA: esto va a SOBREESCRIBIR la base de datos '$TARGET_DB' en $POSTGRES_HOST:$POSTGRES_PORT."
echo "  Backup a restaurar: $BACKUP_FILE"
echo
read -p "Estas seguro? Escribe 'SI' (en mayusculas) para continuar: " confirm
if [ "$confirm" != "SI" ]; then
    echo "Cancelado por el usuario"
    exit 0
fi

# --- Verificar que la BD destino existe --------------------------------
EXISTS=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
    -tAc "SELECT 1 FROM pg_database WHERE datname='$TARGET_DB'" 2>/dev/null || echo "")

if [ "$EXISTS" = "1" ]; then
    echo "[$(date -Iseconds)] Dropping database $TARGET_DB ..."
    # Terminar conexiones activas antes del drop
    psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d postgres -c "
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '$TARGET_DB' AND pid <> pg_backend_pid()
    " >/dev/null 2>&1 || true
    dropdb -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" --if-exists "$TARGET_DB"
fi

echo "[$(date -Iseconds)] Creating database $TARGET_DB ..."
createdb -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" "$TARGET_DB"

# --- Restore -----------------------------------------------------------
echo "[$(date -Iseconds)] Restaurando $BACKUP_FILE -> $TARGET_DB ..."
# Detectar formato por magic bytes
FIRST_BYTES=$(head -c 5 "$BACKUP_FILE" | xxd -p 2>/dev/null || echo "")
if [ "${FIRST_BYTES:0:10}" = "1f8b080000" ]; then
    # gzip compressed (formato plain dump | gzip)
    gunzip -c "$BACKUP_FILE" | pg_restore \
        -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
        -d "$TARGET_DB" \
        --no-owner --no-privileges \
        --jobs=4
else
    # Formato custom (binario). pg_restore lo lee directo.
    pg_restore \
        -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
        -d "$TARGET_DB" \
        --no-owner --no-privileges \
        --jobs=4 \
        "$BACKUP_FILE"
fi

echo "[$(date -Iseconds)] Restore OK en $TARGET_DB"
echo
echo "Verificacion post-restore:"
TABLE_COUNT=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$TARGET_DB" \
    -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo "?")
echo "  Tablas en public: $TABLE_COUNT"
