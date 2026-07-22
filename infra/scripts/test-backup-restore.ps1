# =============================================================================
# test-backup-restore.ps1 — Test E2E del flujo backup→restore (C2.1-2.4)
# =============================================================================
# Verifica que un backup de Postgres puede:
#   1. Tomarse con backup-postgres.ps1
#   2. Restaurarse en una BD separada (test_restore)
#   3. Validarse: la BD restaurada tiene el mismo schema y los datos clave
#
# USO:
#   .\test-backup-restore.ps1                          # usa defaults
#   $env:POSTGRES_DB = "bodegaje"; .\test-backup-restore.ps1
#
# REQUISITOS:
#   - Postgres corriendo (Docker o nativo)
#   - PGPASSWORD en env o pgpass configurado
#   - psql, pg_dump, pg_restore en PATH
#
# SALIDA:
#   - Exit 0 si todo OK
#   - Exit 1 si alguna validacion falla
#   - Logs a stdout con timestamp
# =============================================================================

[CmdletBinding()]
param(
    [string]$SourceDb = "bodegaje",
    [string]$TargetDb = "bodegaje_restore_test",
    [string]$BackupDir = $null,
    [int]$Timeout = 120
)

$ErrorActionPreference = "Stop"
$startTime = Get-Date

# --- Config defaults ----------------------------------------------------
$BackupDir = if ($BackupDir) { $BackupDir } else { Join-Path $env:TEMP "bodegaje-backup-test" }
$PostgresHost = if ($env:POSTGRES_HOST) { $env:POSTGRES_HOST } else { "127.0.0.1" }
$PostgresPort = if ($env:POSTGRES_PORT) { $env:POSTGRES_PORT } else { "5432" }
$PostgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "bodegaje" }

function Log([string]$msg) {
    $ts = (Get-Date).ToString("HH:mm:ss")
    Write-Host "[$ts] $msg" -ForegroundColor Cyan
}

function Pass([string]$msg) { Write-Host "  PASS: $msg" -ForegroundColor Green }
function Fail([string]$msg) { Write-Host "  FAIL: $msg" -ForegroundColor Red }

# --- 1. Verificar herramientas ------------------------------------------
Log "Verificando herramientas necesarias..."

$tools = @("psql", "pg_dump", "pg_restore")
foreach ($tool in $tools) {
    $which = Get-Command $tool -ErrorAction SilentlyContinue
    if (-not $which) {
        Fail "$tool no esta en PATH"
        exit 1
    }
    Pass "$tool -> $($which.Source)"
}

# --- 2. Verificar conexion a la BD origen -------------------------------
Log "Verificando conexion a $SourceDb@${PostgresHost}:${PostgresPort}..."

$connTest = psql -h $PostgresHost -p $PostgresPort -U $PostgresUser -d $SourceDb -tAc "SELECT 1" 2>&1
if ($LASTEXITCODE -ne 0) {
    Fail "No se pudo conectar a $SourceDb: $connTest"
    exit 1
}
Pass "Conexion a $SourceDb OK"

# --- 3. Capturar estado pre-backup (counts de tablas criticas) ----------
Log "Capturando estado pre-backup de $SourceDb..."

$preCounts = @{
    warehouses = psql -h $PostgresHost -p $PostgresPort -U $PostgresUser -d $SourceDb -tAc "SELECT count(*) FROM warehouses" 2>$null
    products = psql -h $PostgresHost -p $PostgresPort -U $PostgresUser -d $SourceDb -tAc "SELECT count(*) FROM products" 2>$null
    users = psql -h $PostgresHost -p $PostgresPort -U $PostgresUser -d $SourceDb -tAc "SELECT count(*) FROM users" 2>$null
    audit_logs = psql -h $PostgresHost -p $PostgresPort -U $PostgresUser -d $SourceDb -tAc "SELECT count(*) FROM audit_logs" 2>$null
}

Log "Pre-backup counts: warehouses=$($preCounts.warehouses), products=$($preCounts.products), users=$($preCounts.users), audit_logs=$($preCounts.audit_logs)"

# Si la BD origen esta vacia, abortamos (no hay nada que probar)
if ([int]$preCounts.warehouses -eq 0 -and [int]$preCounts.products -eq 0) {
    Fail "La BD origen esta vacia. Sembra datos antes de probar el restore."
    exit 1
}

# --- 4. Tomar backup -----------------------------------------------------
Log "Tomando backup de $SourceDb en $BackupDir..."

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

$env:BACKUP_DIR = $BackupDir
$env:POSTGRES_HOST = $PostgresHost
$env:POSTGRES_PORT = $PostgresPort
$env:POSTGRES_DB = $SourceDb
$env:POSTGRES_USER = $PostgresUser

$scriptPath = Join-Path $PSScriptRoot "backup-postgres.ps1"
if (-not (Test-Path $scriptPath)) {
    Fail "No se encontro backup-postgres.ps1 en $scriptPath"
    exit 1
}

& $scriptPath
if ($LASTEXITCODE -ne 0) {
    Fail "backup-postgres.ps1 fallo con exit $LASTEXITCODE"
    exit 1
}
Pass "Backup completado"

# --- 5. Encontrar el backup mas reciente --------------------------------
Log "Buscando el backup mas reciente en $BackupDir..."

$latestBackup = Get-ChildItem -Path $BackupDir -Filter "bodegaje-*.sql.gz" -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $latestBackup) {
    Fail "No se encontro ningun backup en $BackupDir"
    exit 1
}
Pass "Backup mas reciente: $($latestBackup.Name) ($([math]::Round($latestBackup.Length / 1KB, 1)) KB)"

# --- 6. Restaurar en BD separada ----------------------------------------
Log "Restaurando $($latestBackup.Name) -> $TargetDb..."

# Drop + create la BD destino (puede fallar si no existe, OK)
psql -h $PostgresHost -p $PostgresPort -U $PostgresUser -d postgres -c "DROP DATABASE IF EXISTS $TargetDb" 2>&1 | Out-Null

$createResult = psql -h $PostgresHost -p $PostgresPort -U $PostgresUser -d postgres -c "CREATE DATABASE $TargetDb" 2>&1
if ($LASTEXITCODE -ne 0) {
    Fail "No se pudo crear $TargetDb: $createResult"
    exit 1
}
Pass "BD $TargetDb creada"

# Detectar formato por magic bytes (gzip: 1f 8b)
$firstBytes = [System.IO.File]::ReadAllBytes($latestBackup.FullName)[0..4] | ForEach-Object { $_.ToString("x2") } | Join-String ""
$isGzip = $firstBytes.StartsWith("1f8b")

if ($isGzip) {
    Log "Formato detectado: gzip"
    Get-Content $latestBackup.FullName -Raw | gunzip | pg_restore `
        -h $PostgresHost -p $PostgresPort -U $PostgresUser `
        -d $TargetDb `
        --no-owner --no-privileges 2>&1 | Out-Null
} else {
    Log "Formato detectado: custom (binario)"
    pg_restore `
        -h $PostgresHost -p $PostgresPort -U $PostgresUser `
        -d $TargetDb `
        --no-owner --no-privileges `
        $latestBackup.FullName 2>&1 | Out-Null
}

if ($LASTEXITCODE -ne 0) {
    Fail "pg_restore fallo con exit $LASTEXITCODE"
    exit 1
}
Pass "Restore completado"

# --- 7. Validar que los datos se restauraron ----------------------------
Log "Validando datos en $TargetDb..."

$postCounts = @{
    warehouses = psql -h $PostgresHost -p $PostgresPort -U $PostgresUser -d $TargetDb -tAc "SELECT count(*) FROM warehouses" 2>$null
    products = psql -h $PostgresHost -p $PostgresPort -U $PostgresUser -d $TargetDb -tAc "SELECT count(*) FROM products" 2>$null
    users = psql -h $PostgresHost -p $PostgresPort -U $PostgresUser -d $TargetDb -tAc "SELECT count(*) FROM users" 2>$null
    audit_logs = psql -h $PostgresHost -p $PostgresPort -U $PostgresUser -d $TargetDb -tAc "SELECT count(*) FROM audit_logs" 2>$null
}

Log "Post-restore counts: warehouses=$($postCounts.warehouses), products=$($postCounts.products), users=$($postCounts.users), audit_logs=$($postCounts.audit_logs)"

$failCount = 0
foreach ($table in @("warehouses", "products", "users", "audit_logs")) {
    $pre = [int]$preCounts[$table]
    $post = [int]$postCounts[$table]
    if ($pre -eq $post) {
        Pass "$table count matches ($pre == $post)"
    } else {
        Fail "$table count mismatch (pre=$pre, post=$post)"
        $failCount++
    }
}

# --- 8. Limpiar ---------------------------------------------------------
Log "Limpiando BD de test $TargetDb..."
psql -h $PostgresHost -p $PostgresPort -U $PostgresUser -d postgres -c "DROP DATABASE IF EXISTS $TargetDb" 2>&1 | Out-Null

# --- 9. Resumen ---------------------------------------------------------
$elapsed = (Get-Date) - $startTime
Log "Test completado en $([math]::Round($elapsed.TotalSeconds, 1)) segundos"

if ($failCount -gt 0) {
    Fail "$failCount validacion(es) fallaron"
    exit 1
}

Pass "Todas las validaciones pasaron. Backup/Restore E2E OK."
exit 0
