# Paquete de tests de infra.
#
# Los tests aqui son LIVE: requieren que Nginx/Postgres/etc esten corriendo.
# Por defecto estan SKIPPED (decorador @pytest.mark.skip con motivo).
# Para correrlos:
#
#   1. Levantar el stack dev:
#      docker compose -f infra/docker/docker-compose.yml \
#                     -f infra/docker/compose.local.dev.yml up -d
#
#   2. Quitar el skip (o usar el parametro -k o pytest.mark.no_skip):
#      cd infra && pytest tests/test_nginx_headers.py -v --no-header -p no:cacheprovider
#
#   3. Verificar headers en securityheaders.com (despues del deploy real).
