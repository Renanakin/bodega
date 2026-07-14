Write-Host "Levantando perfil staging de bodegaje..."
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.staging.yml up --build -d

