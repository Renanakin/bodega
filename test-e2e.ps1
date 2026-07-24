# test-e2e.ps1
# Wrapper PowerShell nativo para correr la bateria E2E en Windows.
# Equivalente al `Makefile` para gente que no tiene `make`.
#
# Uso:
#   .\test-e2e.ps1                       # bateria completa (5 tests, ~70s)
#   .\test-e2e.ps1 -Quick                # sin Playwright (3 tests, ~25s)
#   .\test-e2e.ps1 -Only oc_correo_flujo # solo OC
#   .\test-e2e.ps1 -ShowOutput           # output completo
#   .\test-e2e.ps1 -Clean                # limpia caches primero
#
# Aliases (primer argumento posicional):
#   .\test-e2e.ps1 oc              -> solo oc_correo_flujo
#   .\test-e2e.ps1 quick           -> sin Playwright
#   .\test-e2e.ps1 backup          -> solo backup_restore
#   .\test-e2e.ps1 replenishment   -> solo cobertura de solicitudes
#   .\test-e2e.ps1 layout          -> solo bug11_layout (Playwright)
#   .\test-e2e.ps1 manual          -> solo screenshots manual (Playwright)
#   .\test-e2e.ps1 all             -> bateria completa

[CmdletBinding()]
param(
    [Parameter(Position=0)]
    [string]$Command = "",
    [string]$Only = "",
    [string[]]$Skip = @(),
    [switch]$Quick,
    [switch]$ShowOutput,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path "$RepoRoot/tests/e2e")) {
    $RepoRoot = $PSScriptRoot
}
$E2EDir = Join-Path $RepoRoot "tests/e2e"
$RunAll = Join-Path $E2EDir "run_all.py"

if (-not (Test-Path $RunAll)) {
    Write-Host "[ERROR] No se encontro $RunAll" -ForegroundColor Red
    exit 2
}

# Parsear alias de primer argumento
if ($Command) {
    switch ($Command) {
        "oc"      { $Only = "oc_correo_flujo" }
        "quick"   { $Quick = $true }
        "backup"  { $Only = "backup_restore" }
        "all"     { $Only = ""; $Skip = @() }
        "replenishment" { $Only = "replenishment_bug12" }
        "layout"  { $Only = "bug11_layout" }
        "manual"  { $Only = "manual_screens" }
        default   {
            Write-Host "[WARN] alias desconocido: $Command" -ForegroundColor Yellow
            Write-Host "Aliases: oc | quick | backup | all | replenishment | layout | manual" -ForegroundColor Yellow
        }
    }
}

# Construir argumentos
$pyArgs = @($RunAll, "--no-color")
if ($Only) {
    $pyArgs += @("--only", $Only)
}
if ($Skip.Count -gt 0) {
    $pyArgs += @("--skip") + $Skip
}
if ($Quick) {
    $pyArgs += @("--skip", "bug11_layout", "manual_screens")
}
if ($ShowOutput) {
    $pyArgs += @("--verbose")
}

# Limpieza previa si se pidio
if ($Clean) {
    Write-Host "[clean] Limpiando caches..." -ForegroundColor Yellow
    Get-ChildItem $E2EDir -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem $E2EDir -Filter "*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem $E2EDir -Filter "_run_*.log" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
}

# Verificar Python
try {
    $pyVersion = python --version 2>&1
    Write-Host "[setup] $pyVersion" -ForegroundColor Cyan
} catch {
    Write-Host "[ERROR] Python no encontrado en PATH" -ForegroundColor Red
    exit 2
}

# Verificar que el sistema este corriendo
try {
    $r = Invoke-WebRequest -Uri "http://localhost:8080/api/v1/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    Write-Host "[setup] API health: $($r.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "[WARN] API no responde en localhost:8080. Los tests E2E fallaran." -ForegroundColor Yellow
    Write-Host "       Levanta el sistema: docker compose -f infra/docker/docker-compose.yml up -d" -ForegroundColor Yellow
    $continuar = Read-Host "Continuar de todos modos? (s/N)"
    if ($continuar -ne "s" -and $continuar -ne "S") {
        exit 2
    }
}

# Correr
Write-Host ""
Write-Host "Comando: python $($pyArgs -join ' ')" -ForegroundColor DarkGray
Write-Host ""
& python @pyArgs
exit $LASTEXITCODE
