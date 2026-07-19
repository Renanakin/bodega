# =============================================================================
# start-production.ps1 — Arranca el stack de produccion con pre-deploy checks
# =============================================================================
# Por defecto corre el pre-deploy check antes de levantar el stack.
# Para saltar el check (NO recomendado en CI/CD automatizado), usar -SkipCheck.
# =============================================================================

[CmdletBinding()]
param(
    [switch]$SkipCheck,
    [switch]$Build,
    [switch]$Help
)

if ($Help) {
    Write-Host @"
Uso: .\start-production.ps1 [-SkipCheck] [-Build] [-Help]

Opciones:
  -SkipCheck   Saltear el pre-deploy check (NO recomendado).
  -Build       Forzar rebuild de las imagenes (sin cache).
  -Help        Mostrar esta ayuda.

Ejemplos:
  .\start-production.ps1                    # check + arranque
  .\start-production.ps1 -Build             # check + rebuild + arranque
  .\start-production.ps1 -SkipCheck -Build  # solo rebuild + arranque
"@
    exit 0
}

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $repoRoot
Set-Location $repoRoot

# --- Pre-deploy check (a menos que se skipee) --------------------------
if (-not $SkipCheck) {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Cyan
    Write-Host "PRE-DEPLOY CHECK" -ForegroundColor Cyan
    Write-Host "=========================================" -ForegroundColor Cyan
    $checkScript = Join-Path $PSScriptRoot "pre-deploy-check.sh"
    if (Test-Path $checkScript) {
        # Intentar ejecutar via bash (Git Bash o WSL). Si no hay bash, skip.
        $bash = Get-Command "bash" -ErrorAction SilentlyContinue
        if ($bash) {
            & bash $checkScript production
            if ($LASTEXITCODE -ne 0) {
                Write-Host ""
                Write-Host "ABORTANDO: el pre-deploy check fallo." -ForegroundColor Red
                Write-Host "Resolver los checks pendientes antes de continuar." -ForegroundColor Red
                Write-Host "Para saltar (NO recomendado): -SkipCheck" -ForegroundColor Yellow
                exit 1
            }
        } else {
            Write-Host "[WARN] bash no disponible, saltando pre-deploy check" -ForegroundColor Yellow
            Write-Host "       Instalar Git Bash o WSL para tener el check completo." -ForegroundColor Yellow
        }
    } else {
        Write-Host "[WARN] pre-deploy-check.sh no encontrado, saltando" -ForegroundColor Yellow
    }
}

# --- Verificar que existe .env.production ------------------------------
$envFile = Join-Path $repoRoot ".env.production"
if (-not (Test-Path $envFile)) {
    Write-Host ""
    Write-Host "ERROR: .env.production no existe." -ForegroundColor Red
    Write-Host "       Crear desde infra/.env.production.example:" -ForegroundColor Red
    Write-Host "         cp infra/.env.production.example .env.production" -ForegroundColor Red
    Write-Host "       Y reemplazar todos los placeholders __*__." -ForegroundColor Red
    Write-Host ""
    Write-Host "Para generar secretos seguros:" -ForegroundColor Yellow
    Write-Host "         python infra/scripts/generate-secrets.py" -ForegroundColor Yellow
    exit 1
}

# --- Verificar que JWT_SECRET y SECRET_KEY son fuertes ----------------
$envContent = Get-Content $envFile -Raw
if ($envContent -match '^JWT_SECRET=(.+)$') {
    $jwtSecret = $Matches[1].Trim()
    if ($jwtSecret.Length -lt 32 -or $jwtSecret.StartsWith("__")) {
        Write-Host ""
        Write-Host "ERROR: JWT_SECRET es placeholder o < 32 chars." -ForegroundColor Red
        Write-Host "       Generar con: python infra/scripts/generate-secrets.py" -ForegroundColor Red
        exit 1
    }
}
if ($envContent -match '^SECRET_KEY=(.+)$') {
    $secretKey = $Matches[1].Trim()
    if ($secretKey.Length -lt 32 -or $secretKey.StartsWith("__")) {
        Write-Host ""
        Write-Host "ERROR: SECRET_KEY es placeholder o < 32 chars (REQUERIDO en produccion)." -ForegroundColor Red
        Write-Host "       Generar con: python infra/scripts/generate-secrets.py" -ForegroundColor Red
        exit 1
    }
}

# --- Levantar el stack -------------------------------------------------
Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "ARRANCANDO STACK DE PRODUCCION" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

$composeArgs = @(
    "-f", "infra/docker/docker-compose.yml",
    "-f", "infra/docker/compose.production.yml"
)
if ($Build) {
    $composeArgs += "build"
    $composeArgs += "--no-cache"
}
$composeArgs += "up"
$composeArgs += "-d"

& docker compose @composeArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: docker compose fallo con exit code $LASTEXITCODE" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Stack arrancado. Verificar con:" -ForegroundColor Green
Write-Host "  docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml ps"
Write-Host "  curl -i http://localhost/api/v1/health"
Write-Host ""
