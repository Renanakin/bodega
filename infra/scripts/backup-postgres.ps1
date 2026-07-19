# =============================================================================
# backup-postgres.ps1 — Backup diario de PostgreSQL con rotacion (Fase 10, Windows)
# =============================================================================
# Equivalente Windows de backup-postgres.sh. Mismas garantias:
# - Idempotente (nombre unico por timestamp)
# - Verifica integridad del archivo
# - Rota backups > N dias
# - Verifica que existe al menos 1 backup reciente
# - Upload opcional a S3 via AWS CLI
#
# Uso:
#   .\backup-postgres.ps1                        # backup local
#   .\backup-postgres.ps1 -UploadS3              # ademas sube a S3
#   $env:BACKUP_DIR = "D:\backups"; .\backup-postgres.ps1
#
# Variables de entorno (todas opcionales con defaults):
#   BACKUP_DIR              directorio destino (default $env:USERPROFILE\backups\bodegaje)
#   POSTGRES_HOST           host de Postgres (default localhost)
#   POSTGRES_PORT           puerto de Postgres (default 5432)
#   POSTGRES_DB             nombre de la BD (default bodegaje)
#   POSTGRES_USER           usuario de Postgres (default bodegaje)
#   POSTGRES_PASSWORD       password (REQUERIDO en prod, o usar pgpass.conf)
#   BACKUP_RETENTION_DAILY  dias a retener (default 7)
#   BACKUP_S3_BUCKET        bucket S3 destino (opcional)
#   AWS_REGION              region AWS (default us-east-1)
# =============================================================================

[CmdletBinding()]
param(
    [switch]$UploadS3
)

$ErrorActionPreference = "Stop"

# --- Configuracion con defaults -----------------------------------------
$BackupDir = if ($env:BACKUP_DIR) { $env:BACKUP_DIR } else { Join-Path $env:USERPROFILE "backups\bodegaje" }
$PostgresHost = if ($env:POSTGRES_HOST) { $env:POSTGRES_HOST } else { "localhost" }
$PostgresPort = if ($env:POSTGRES_PORT) { $env:POSTGRES_PORT } else { "5432" }
$PostgresDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "bodegaje" }
$PostgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "bodegaje" }
$RetentionDaily = if ($env:BACKUP_RETENTION_DAILY) { [int]$env:BACKUP_RETENTION_DAILY } else { 7 }
$BackupS3Bucket = if ($env:BACKUP_S3_BUCKET) { $env:BACKUP_S3_BUCKET } else { "" }
$AwsRegion = if ($env:AWS_REGION) { $env:AWS_REGION } else { "us-east-1" }

# --- Validaciones previas ----------------------------------------------
$pgDump = Get-Command "pg_dump.exe" -ErrorAction SilentlyContinue
if (-not $pgDump) {
    Write-Error "pg_dump.exe no esta en PATH. Instalar PostgreSQL client tools o agregar al PATH."
    exit 1
}

if (-not $env:POSTGRES_PASSWORD -and -not $env:PGPASSWORD) {
    # En Windows, pgpass.conf esta en %APPDATA%\postgresql\pgpass.conf
    $pgpassPath = Join-Path $env:APPDATA "postgresql\pgpass.conf"
    if (-not (Test-Path $pgpassPath)) {
        Write-Error "POSTGRES_PASSWORD/PGPASSWORD no seteado y no existe pgpass.conf. Abortando."
        exit 1
    }
}

# --- Crear directorio destino ------------------------------------------
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

# Intentar permisos restrictivos (Windows usa ACLs; icacls limita acceso)
try {
    $acl = Get-Acl $BackupDir
    # Remover reglas de acceso heredadas y dejar solo el usuario actual
    $acl.SetAccessRuleProtection($true, $false)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $env:USERNAME, "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow"
    )
    $acl.AddAccessRule($rule)
    Set-Acl $BackupDir $acl
} catch {
    Write-Warning "No se pudieron ajustar permisos de $BackupDir (puede ser contenedor Docker). Continuando..."
}

# --- Generar nombre unico ----------------------------------------------
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupFile = Join-Path $BackupDir "bodegaje-$Timestamp.sql.gz"

if (Test-Path $BackupFile) {
    Write-Error "Ya existe $BackupFile - posible carrera. Abortando."
    exit 1
}

# --- Ejecutar pg_dump --------------------------------------------------
# Seteamos PGPASSWORD para esta ejecucion (no se hereda a procesos hijos
# si no se exporta explicitamente).
$env:PGPASSWORD = $env:POSTGRES_PASSWORD
if (-not $env:PGPASSWORD) { $env:PGPASSWORD = $env:PGPASSWORD_BACKUP }

$timestampLog = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
Write-Host "[$timestampLog] Iniciando backup de $PostgresDb@$PostgresHost ..."

try {
    # pg_dump en Windows no soporta --format=custom+gzip directamente.
    # Usamos --format=custom (binario) y dejamos que pg_restore lo lea.
    # Si se quiere gzip, hay que usar --format=plain y pipear a gzip.
    $output = & pg_dump.exe `
        -h $PostgresHost `
        -p $PostgresPort `
        -U $PostgresUser `
        -d $PostgresDb `
        --no-owner --no-privileges `
        --format=custom `
        --file="$BackupFile" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump fallo con exit code $LASTEXITCODE: $output"
    }
} catch {
    Write-Error "pg_dump fallo: $_"
    if (Test-Path $BackupFile) { Remove-Item $BackupFile -Force }
    exit 1
}

# --- Verificar integridad ---------------------------------------------
if (-not (Test-Path $BackupFile)) {
    Write-Error "Backup no se creo: $BackupFile"
    exit 1
}

$fileInfo = Get-Item $BackupFile
if ($fileInfo.Length -eq 0) {
    Write-Error "Backup vacio ($BackupFile). Abortando."
    Remove-Item $BackupFile -Force
    exit 1
}

# Validar con pg_restore --list (el archivo custom-format debe listarse OK)
try {
    $null = & pg_restore.exe --list "$BackupFile" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore --list fallo"
    }
} catch {
    Write-Error "Backup corrupto (pg_restore --list fallo): $_"
    Remove-Item $BackupFile -Force
    exit 1
}

# --- Reportar tamano ---------------------------------------------------
$sizeHuman = "{0:N2} MB" -f ($fileInfo.Length / 1MB)
$timestampLog = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
Write-Host "[$timestampLog] Backup OK: $BackupFile ($sizeHuman)"

# --- Rotacion ----------------------------------------------------------
$cutoff = (Get-Date).AddDays(-$RetentionDaily)
$deleted = 0
Get-ChildItem -Path $BackupDir -Filter "bodegaje-*.sql.gz" -File |
    Where-Object { $_.LastWriteTime -lt $cutoff } |
    ForEach-Object {
        Remove-Item $_.FullName -Force
        $deleted++
    }
if ($deleted -gt 0) {
    Write-Host "[$timestampLog] Rotacion: $deleted backups > $RetentionDaily dias eliminados"
}

# --- Verificar al menos 1 backup reciente ------------------------------
$recent = Get-ChildItem -Path $BackupDir -Filter "bodegaje-*.sql.gz" -File |
    Where-Object { $_.LastWriteTime -gt (Get-Date).AddHours(-25) } |
    Select-Object -First 1
if (-not $recent) {
    Write-Error "No hay backup en las ultimas 25h. Alerta requerida."
    exit 1
}

# --- Upload opcional a S3 ---------------------------------------------
if ($UploadS3 -and $BackupS3Bucket) {
    $aws = Get-Command "aws" -ErrorAction SilentlyContinue
    if (-not $aws) {
        Write-Warning "aws cli no instalado. Backup local OK, sin upload a S3."
    } else {
        $s3Path = "s3://$BackupS3Bucket/daily/$($fileInfo.Name)"
        try {
            & aws s3 cp "$BackupFile" $s3Path --storage-class STANDARD_IA --region $AwsRegion 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "[$timestampLog] Subido a $s3Path"
            } else {
                Write-Warning "Fallo upload a S3 (exit $LASTEXITCODE), backup local OK."
            }
        } catch {
            Write-Warning "Excepcion subiendo a S3: $_. Backup local OK."
        }
    }
}

$timestampLog = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
Write-Host "[$timestampLog] Backup completo"
