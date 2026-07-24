# Makefile para Bodegaje
# Targets principales:
#   make help          - muestra ayuda
#   make e2e           - bateria E2E completa (5 tests, ~70s)
#   make e2e-quick     - sin Playwright (3 tests, ~25s)
#   make e2e-oc        - solo modulo OC por correo
#   make e2e-backup    - solo backup + restore
#
# Requisitos:
#   - python 3.10+ en PATH
#   - requests (pip install requests)
#   - playwright (pip install playwright && playwright install) para tests visuales
#   - docker compose corriendo (los tests golpean http://localhost:8080)
#
# Uso tipico:
#   make e2e-quick     # antes de commit
#   make e2e           # smoke completo
#   make e2e-oc        # debug del modulo de OC

# Detectar el binario de Python
PYTHON ?= python
E2E_DIR := tests/e2e

.PHONY: help e2e e2e-quick e2e-oc e2e-backup e2e-replenishment \
        e2e-layout e2e-manual e2e-all-no-playwright clean-e2e

help: ## Muestra esta ayuda
	@echo "Targets disponibles:"
	@echo "  make e2e                     Bateria E2E completa (5 tests, ~70s)"
	@echo "  make e2e-quick                Sin Playwright (3 tests, ~25s)"
	@echo "  make e2e-oc                   Solo modulo OC por correo (12s)"
	@echo "  make e2e-backup               Solo backup + restore (5s)"
	@echo "  make e2e-replenishment        Solo cobertura de solicitudes (5s)"
	@echo "  make e2e-layout               Solo bug11_layout (Playwright, 5s)"
	@echo "  make e2e-manual               Solo screenshots manual (Playwright, 40s)"
	@echo "  make clean-e2e                Limpia caches y reportes de tests"
	@echo ""
	@echo "Variables:"
	@echo "  PYTHON=<binario>              Default: python"

e2e: ## Bateria E2E completa
	cd $(E2E_DIR) && $(PYTHON) run_all.py

e2e-quick: ## Sin Playwright (3 tests, ~25s)
	cd $(E2E_DIR) && $(PYTHON) run_all.py --skip bug11_layout manual_screens

e2e-oc: ## Solo modulo OC por correo
	cd $(E2E_DIR) && $(PYTHON) run_all.py --only oc_correo_flujo

e2e-backup: ## Solo backup + restore
	cd $(E2E_DIR) && $(PYTHON) run_all.py --only backup_restore

e2e-replenishment: ## Solo cobertura de solicitudes
	cd $(E2E_DIR) && $(PYTHON) run_all.py --only replenishment_bug12

e2e-layout: ## Solo bug11_layout (Playwright)
	cd $(E2E_DIR) && $(PYTHON) run_all.py --only bug11_layout

e2e-manual: ## Solo screenshots manual (Playwright)
	cd $(E2E_DIR) && $(PYTHON) run_all.py --only manual_screens

clean-e2e: ## Limpia caches y reportes generados
	find $(E2E_DIR) -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	find $(E2E_DIR) -name "*.pyc" -delete 2>/dev/null || true
	find $(E2E_DIR) -name "_run_*.log" -delete 2>/dev/null || true
	@echo "Cache E2E limpiado"
