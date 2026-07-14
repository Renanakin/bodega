Write-Host "Reiniciando demo persistente de bodegaje..."
Push-Location "apps/api"
try {
  python -m app.db.demo
} finally {
  Pop-Location
}
