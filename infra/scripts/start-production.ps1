Write-Host "Levantando perfil production de bodegaje..."
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml up --build -d

