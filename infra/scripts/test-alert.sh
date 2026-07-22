#!/usr/bin/env bash
# =============================================================================
# test-alert.sh — Simula una alerta y verifica que llegue al canal (C3.7)
# =============================================================================
# Uso:
#   ./test-alert.sh high-error-rate   # simula 5xx errors
#   ./test-alert.sh outbox-backlog    # inserta emails pendientes
#   ./test-alert.sh redis-down        # mata Redis
#
# Pre-requisitos:
#   - Prometheus + Alertmanager corriendo (compose.observability.yml)
#   - Variable SLACK_WEBHOOK_URL configurada (o ver el log)
#
# Salida:
#   - Explica paso a paso como verificar que la alerta llego.
# =============================================================================
set -euo pipefail

SCENARIO="${1:-help}"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info() { echo -e "${CYAN}ℹ${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
ok()   { echo -e "${GREEN}✓${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; }

case "$SCENARIO" in
    help|--help|-h)
        cat <<EOF
Uso: $0 <escenario>

Escenarios disponibles:
  high-error-rate    Genera 5xx errors durante 1 min y verifica que la
                     alerta HighErrorRate se dispare.
  outbox-backlog     Inserta 150 registros en email_outbox con status='pending'
                     y verifica que OutboxBacklog se dispare.
  redis-down         Mata el contenedor Redis y verifica que la app degrade
                     graceful.
  help               Este mensaje.

Pre-requisitos: stack de observabilidad corriendo (compose.observability.yml).
EOF
        exit 0
        ;;
esac

# --- Verificar que el stack de observabilidad esta corriendo -------------
info "Verificando stack de observabilidad..."

if ! docker ps | grep -q "bodegaje-prometheus"; then
    err "Prometheus no esta corriendo. Inicia con:"
    echo "  docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.observability.yml up -d"
    exit 1
fi
ok "Prometheus corriendo"

if ! docker ps | grep -q "bodegaje-alertmanager"; then
    err "Alertmanager no esta corriendo."
    exit 1
fi
ok "Alertmanager corriendo"

# --- Ejecutar escenario ------------------------------------------------
case "$SCENARIO" in
    high-error-rate)
        info "Escenario: high-error-rate"
        echo
        echo "Pasos:"
        echo "  1. Generar requests que retornen 5xx"
        echo "  2. Esperar 5-10 min a que la alerta se dispare"
        echo "  3. Verificar:"
        echo "     - Prometheus: http://localhost:9090/alerts"
        echo "     - Alertmanager: http://localhost:9093"
        echo "     - Slack: #oncall"
        echo

        # Generar errores 500 pegandole a un endpoint que no existe
        # con auth invalida (causa 500 por bug en middleware, no 401)
        info "Generando errores 5xx (60 segundos)..."
        for i in $(seq 1 60); do
            # Pegar a un endpoint que sabemos falla con 500
            curl -s -o /dev/null -w "%{http_code}\n" \
                http://localhost:8000/api/v1/internal/force-500 \
                -H "Authorization: Bearer invalid" || true
            sleep 1
        done &
        GENERATOR_PID=$!

        warn "Espera 5-10 minutos para que la alerta se dispare."
        warn "Para detener la generacion: kill $GENERATOR_PID"
        echo
        echo "Verificar alerta en: http://localhost:9090/alerts (filtro: HighErrorRate)"
        ;;

    outbox-backlog)
        info "Escenario: outbox-backlog"
        echo
        echo "Insertando 150 emails en outbox con status='pending'..."

        docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "
          INSERT INTO email_outbox (id, to_email, subject, body_html, status, created_at)
          SELECT
            gen_random_uuid()::text,
            'test-' || i || '@example.com',
            'Test email #' || i,
            '<p>Body</p>',
            'pending',
            now() - (i || ' minutes')::interval
          FROM generate_series(1, 150) AS i;
        "

        ok "150 emails insertados."
        warn "Espera 10-15 minutos a que la alerta OutboxBacklog se dispare."
        echo "Verificar en: http://localhost:9090/alerts (filtro: OutboxBacklog)"
        ;;

    redis-down)
        info "Escenario: redis-down"
        echo
        warn "Esto MATARA el contenedor Redis. El sistema seguira funcionando"
        warn "pero el cache de idempotencia y el outbox quedaran no disponibles."
        echo
        read -p "Continuar? (escribe SI): " confirm
        if [ "$confirm" != "SI" ]; then
            info "Cancelado."
            exit 0
        fi

        docker stop bodegaje-redis
        ok "Redis detenido."

        # Esperar a que la app se recupere
        sleep 5
        info "Health check:"
        curl -s http://localhost:8000/api/v1/health/ready | jq .

        # Reanudar
        warn "Para reanudar: docker start bodegaje-redis"
        ;;

    *)
        err "Escenario desconocido: $SCENARIO"
        echo "Usa '$0 help' para ver los disponibles."
        exit 1
        ;;
esac

# --- Verificacion final ------------------------------------------------
echo
info "Para verificar la alerta llego al canal configurado:"
echo "  1. Prometheus UI:    http://localhost:9090/alerts"
echo "  2. Alertmanager UI: http://localhost:9093"
echo "  3. Slack:           #oncall (critical) o #ops-warnings (warning)"
echo
info "Para inspeccionar las reglas:"
echo "  curl -s http://localhost:9090/api/v1/rules | jq ."
echo
info "Para silenciar la alerta durante 1h:"
echo "  amtool silence add --alertmanager=http://localhost:9093 --duration=1h --comment='test' HighErrorRate"
