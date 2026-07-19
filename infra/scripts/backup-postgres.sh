#!/usr/bin/env bash
# =============================================================================
# backup-postgres.sh — Backup diario de PostgreSQL con rotacion (Fase 10)
# =============================================================================
# Uso:
#   ./backup-postgres.sh                      # backup local al directorio por defecto
#   ./backup-postgres.sh --upload-s3          # ademas sube a S3 si BACKUP_S3_BUCKET esta set
#   BACKUP_DIR=/custom/path ./backup-postgres.sh
#
# Variables de entorno (todas opcionales con defaults):
#   BACKUP_DIR              directorio destino del backup (default /var/backups/bodegaje)
#   POSTGRES_HOST           host de Postgres (default localhost)
#   POSTGRES_PORT           puerto de Postgres (default 5432)
#   POSTGRES_DB             nombre de la BD (default bodegaje)
#   POSTGRES_USER           usuario de Postgres (default bodegaje)
#   PGPASSWORD              password de Postgres (REQUERIDO en prod; opcional si .pgpass)
#   BACKUP_RETENTION_DAILY  dias a retener backups diarios (default 7)
#   BACKUP_S3_BUCKET        bucket S3 donde subir (opcional, requiere aws cli)
#   AWS_REGION              region AWS para el upload (default us-east-1)
#
# Idempotencia:
#   - El archivo se nombra con timestamp (unico por ejecucion).
#   - Si ya existe un backup del mismo timestamp (carrera), se aborta.
#   - find -mtime +N -delete elimina los > N dias.
#   - Si no se logra hacer backup, el script retorna exit code != 0.
#
# Verificacion de integridad:
#   - Tras el dump, se hace gunzip -t para validar el gzip.
#   - Se verifica que existe al menos un backup de las ultimas 25h.
#   - Si la verificacion falla, se emite error a stderr y se retorna != 0.
# =============================================================================
set -euo pipefail

# --- Configuracion con defaults -----------------------------------------
BACKUP_DIR="${BACKUP_DIR:-/var/backups/bodegaje}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-bodegaje}"
POSTGRES_USER="${POSTGRES_USER:-bodegaje}"
RETENTION_DAILY="${BACKUP_RETENTION_DAILY:-7}"
BACKUP_S3_BUCKET="${BACKUP_S3_BUCKET:-}"
AWS_REGION="${AWS_REGION:-us-east-1}"

UPLOAD_S3=0
for arg in "$@"; do
    case "$arg" in
        --upload-s3) UPLOAD_S3=1 ;;
        --help|-h)
            sed -n '2,25p' "$0"
            exit 0
            ;;
        *)
            echo "ERROR: argumento desconocido: $arg" >&2
            exit 2
            ;;
    esac
done

# --- Validaciones previas -----------------------------------------------
if ! command -v pg_dump >/dev/null 2>&1; then
    echo "ERROR: pg_dump no esta en PATH. Instalar postgresql-client." >&2
    exit 1
fi

if [ -z "${PGPASSWORD:-}" ] && [ ! -f "${HOME}/.pgpass" ]; then
    echo "ERROR: PGPASSWORD no esta seteado y no existe ~/.pgpass." >&2
    echo "       Setea PGPASSWORD o configura ~/.pgpass (chmod 600)." >&2
    exit 1
fi

# --- Crear directorio destino ------------------------------------------
mkdir -p "$BACKUP_DIR"

# Permisos restrictivos (solo owner puede leer backups con secretos).
chmod 700 "$BACKUP_DIR" 2>/dev/null || true

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="$BACKUP_DIR/bodegaje-${TIMESTAMP}.sql.gz"

# Si ya existe un backup con este timestamp (carrera rara), abortar.
if [ -e "$BACKUP_FILE" ]; then
    echo "ERROR: ya existe $BACKUP_FILE - posible carrera." >&2
    exit 1
fi

# --- Ejecutar pg_dump ----------------------------------------------------
echo "[$(date -Iseconds)] Iniciando backup de $POSTGRES_DB@$POSTGRES_HOST ..."

if ! pg_dump \
    -h "$POSTGRES_HOST" \
    -p "$POSTGRES_PORT" \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --no-owner --no-privileges \
    --format=custom --compress=9 \
    --file="$BACKUP_FILE" 2>&1; then
    echo "ERROR: pg_dump fallo. Limpiando $BACKUP_FILE ..." >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

# --- Verificacion de integridad del gzip --------------------------------
if ! gunzip -t "$BACKUP_FILE" 2>/dev/null; then
    # pg_dump --format=custom NO produce gzip, solo cuando es --format=plain|gzip.
    # Verificar con file (magic bytes) o con un gunzip -t equivalente.
    # Para formato custom, el archivo es binario; verificamos que no este vacio
    # y que pg_restore pueda leerlo (lo testeamos al final con --list).
    if [ ! -s "$BACKUP_FILE" ]; then
        echo "ERROR: backup vacio ($BACKUP_FILE). Abortando." >&2
        rm -f "$BACKUP_FILE"
        exit 1
    fi
    # Formato custom: validar con pg_restore --list
    if ! pg_restore --list "$BACKUP_FILE" >/dev/null 2>&1; then
        echo "ERROR: backup corrupto (pg_restore --list fallo). Abortando." >&2
        rm -f "$BACKUP_FILE"
        exit 1
    fi
fi

# --- Reportar tamano -----------------------------------------------------
SIZE_BYTES=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null || echo "?")
SIZE_HUMAN=$(du -h "$BACKUP_FILE" | cut -f1)
echo "[$(date -Iseconds)] Backup OK: $BACKUP_FILE ($SIZE_HUMAN, $SIZE_BYTES bytes)"

# --- Rotacion: eliminar backups > N dias --------------------------------
DELETED=$(find "$BACKUP_DIR" -name "bodegaje-*.sql.gz" -type f -mtime +$RETENTION_DAILY -delete -print | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "[$(date -Iseconds)] Rotacion: $DELETED backups > ${RETENTION_DAILY} dias eliminados"
fi

# --- Verificar al menos 1 backup en las ultimas 25h --------------------
LATEST=$(find "$BACKUP_DIR" -name "bodegaje-*.sql.gz" -type f -mtime -1 | head -1)
if [ -z "$LATEST" ]; then
    echo "ERROR: no hay backup en las ultimas 25h. Alerta requerida." >&2
    exit 1
fi

# --- Upload opcional a S3 (DR off-site) ---------------------------------
if [ "$UPLOAD_S3" -eq 1 ] && [ -n "$BACKUP_S3_BUCKET" ]; then
    if ! command -v aws >/dev/null 2>&1; then
        echo "ERROR: aws cli no instalado. Backup local OK, sin upload a S3." >&2
        # No fallar el backup si S3 no esta disponible - el local ya esta bien.
    else
        S3_PATH="s3://${BACKUP_S3_BUCKET}/daily/$(basename "$BACKUP_FILE")"
        if aws s3 cp "$BACKUP_FILE" "$S3_PATH" --storage-class STANDARD_IA --region "$AWS_REGION" 2>&1; then
            echo "[$(date -Iseconds)] Subido a $S3_PATH"
        else
            echo "WARN: fallo upload a S3, backup local OK en $BACKUP_FILE" >&2
        fi
    fi
fi

echo "[$(date -Iseconds)] Backup completo"
