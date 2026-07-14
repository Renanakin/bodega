Write-Host "Levantando stack local de bodegaje..."
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.local.yml up --build

