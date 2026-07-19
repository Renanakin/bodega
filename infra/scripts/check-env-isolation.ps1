# =============================================================================
# check-env-isolation.ps1 (Regla de Oro R2 - versión Windows)
# =============================================================================
# Verifica que los secretos no se compartan entre entornos.
# Equivalente Windows de check-env-isolation.sh.
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File infra/scripts/check-env-isolation.ps1
# =============================================================================

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $repoRoot

$envFiles = @(
  "$repoRoot\.env.development",
  "$repoRoot\.env.staging",
  "$repoRoot\.env.production"
)

$secretsToCheck = @(
  "JWT_SECRET",
  "SECRET_KEY",
  "POSTGRES_PASSWORD",
  "DATABASE_URL",
  "REDIS_URL",
  "SENTRY_DSN",
  "SMTP_PASSWORD"
)

Write-Host "=== Check de aislamiento de entornos (R2) ===" -ForegroundColor Yellow
Write-Host ""

Write-Host "Archivos a verificar:"
foreach ($envFile in $envFiles) {
  if (-not (Test-Path $envFile)) {
    Write-Host "  [skip] $envFile no existe" -ForegroundColor Yellow
  } else {
    Write-Host "  [ok]   $envFile" -ForegroundColor Green
  }
}
Write-Host ""

$errors = 0

foreach ($secretName in $secretsToCheck) {
  Write-Host -NoNewline "Verificando $secretName... "
  $seenValues = @{}
  $duplicates = 0

  foreach ($envFile in $envFiles) {
    if (-not (Test-Path $envFile)) {
      continue
    }

    $line = Select-String -Path $envFile -Pattern "^${secretName}=" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $line) {
      continue
    }

    $value = ($line -replace "^${secretName}=", "").Trim('"', "'").Trim()

    if ([string]::IsNullOrWhiteSpace($value) -or $value.StartsWith("CHANGE_ME")) {
      continue
    }

    if ($seenValues.ContainsKey($value)) {
      $envName = Split-Path -Leaf $envFile
      $otherEnv = Split-Path -Leaf $seenValues[$value]
      Write-Host "DUPLICADO" -ForegroundColor Red
      Write-Host "  El mismo valor de $secretName aparece en: $otherEnv y $envName" -ForegroundColor Red
      $errors++
      $duplicates++
    } else {
      $seenValues[$value] = $envFile
    }
  }

  if ($duplicates -eq 0) {
    Write-Host "OK" -ForegroundColor Green
  }
}

Write-Host ""
if ($errors -gt 0) {
  Write-Host "=== FALLO: $errors secreto(s) compartido(s) entre entornos ===" -ForegroundColor Red
  Write-Host "Cada entorno (dev/staging/prod) debe tener secretos UNICOS." -ForegroundColor Red
  Write-Host "Edita los archivos .env.* y asigna valores diferentes." -ForegroundColor Red
  exit 1
}

Write-Host "=== OK: todos los secretos son unicos por entorno ===" -ForegroundColor Green
exit 0
