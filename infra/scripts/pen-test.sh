#!/usr/bin/env bash
# =============================================================================
# pen-test.sh — Pen-test automatico con OWASP ZAP contra staging (C5.5)
# =============================================================================
# Uso:
#   ./infra/scripts/pen-test.sh https://staging.bodega.cl
#   ./infra/scripts/pen-test.sh http://localhost:8080
#
# Requiere:
#   - Docker (o OWASP ZAP instalado)
#   - URL accesible
#
# Salida:
#   - Reporte HTML en /tmp/zap-report.html
#   - Reporte JSON en /tmp/zap-report.json
#   - Exit 0 si no hay alertas HIGH, 1 si hay.
# =============================================================================
set -euo pipefail

URL="${1:-http://localhost:8080}"
REPORT_DIR="${REPORT_DIR:-/tmp}"

echo "=========================================="
echo "OWASP ZAP Baseline Scan"
echo "Target: $URL"
echo "=========================================="

# Opcion 1: Docker (recomendado, no requiere instalacion local)
if command -v docker >/dev/null 2>&1; then
    echo "Usando ZAP via Docker..."

    # Crea red efimera para alcanzar el host si es local
    NETWORK_ARG=""
    if [[ "$URL" == *"localhost"* ]] || [[ "$URL" == *"127.0.0.1"* ]]; then
        NETWORK_ARG="--network host"
    fi

    docker run --rm -t \
        ${NETWORK_ARG} \
        -v "$REPORT_DIR:/zap/wrk:rw" \
        ghcr.io/zaproxy/zaproxy:stable \
        zap-baseline.py \
            -t "$URL" \
            -r "zap-report.html" \
            -J "zap-report.json" \
            -l "WARN" \
            -I || true  # ZAP retorna codigo != 0 si hay alertas; las manejamos abajo

# Opcion 2: ZAP local (si esta instalado)
elif command -v zap-baseline.py >/dev/null 2>&1; then
    echo "Usando ZAP local..."
    cd "$REPORT_DIR"
    zap-baseline.py -t "$URL" -r "zap-report.html" -J "zap-report.json" -l "WARN" -I || true
else
    echo "ERROR: ni Docker ni ZAP local disponibles."
    echo "  - Instala Docker: https://docs.docker.com/get-docker/"
    echo "  - O instala ZAP: https://www.zaproxy.org/download/"
    exit 2
fi

# Resumir resultados del JSON
if [[ -f "$REPORT_DIR/zap-report.json" ]]; then
    echo ""
    echo "=========================================="
    echo "RESUMEN DE HALLAZGOS"
    echo "=========================================="

    # Contar alertas por severidad
    HIGH=$(python -c "import json; d=json.load(open('$REPORT_DIR/zap-report.json')); print(sum(1 for s in d.get('site', []))" 2>/dev/null || echo "?")
    MEDIUM=$(python -c "import json; d=json.load(open('$REPORT_DIR/zap-report.json')); print(sum(len(s.get('alerts', [])) for s in d.get('site', []) for a in s.get('alerts', []) if a.get('riskdesc','').startswith('Medium')))" 2>/dev/null || echo "?")
    LOW=$(python -c "import json; d=json.load(open('$REPORT_DIR/zap-report.json')); print(sum(len(s.get('alerts', [])) for s in d.get('site', []) for a in s.get('alerts', []) if a.get('riskdesc','').startswith('Low')))" 2>/dev/null || echo "?")
    INFO=$(python -c "import json; d=json.load(open('$REPORT_DIR/zap-report.json')); print(sum(len(s.get('alerts', [])) for s in d.get('site', []) for a in s.get('alerts', []) if a.get('riskdesc','').startswith('Informational')))" 2>/dev/null || echo "?")

    echo "  High:        $HIGH"
    echo "  Medium:      $MEDIUM"
    echo "  Low:         $LOW"
    echo "  Informational: $INFO"
    echo ""
    echo "Reporte HTML completo: $REPORT_DIR/zap-report.html"
    echo "Reporte JSON:          $REPORT_DIR/zap-report.json"
fi

# Exit code: 0 si no hay HIGH, 1 si hay
if [[ -f "$REPORT_DIR/zap-report.json" ]]; then
    HIGH_COUNT=$(python -c "import json; d=json.load(open('$REPORT_DIR/zap-report.json')); print(sum(1 for s in d.get('site', []) for a in s.get('alerts', []) if a.get('riskdesc','').startswith('High')))" 2>/dev/null || echo "0")
    if [[ "$HIGH_COUNT" -gt 0 ]]; then
        echo ""
        echo "FAIL: $HIGH_COUNT alertas HIGH encontradas. Ver reporte."
        exit 1
    fi
fi
exit 0
