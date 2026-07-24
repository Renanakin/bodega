# Tests E2E

Bateria de tests end-to-end que validan el sistema completo contra una instancia
en vivo (http://localhost:8080). Son tests de **integracion de modulo**, no
unitarios: cada test ejercita un modulo completo del sistema.

## Estructura

```
tests/e2e/
  run_all.py                  # Orquestador (corre todos en serie)
  test_oc_correo_flujo.py     # Modulo OC por correo (3 escenarios)
  test_backup_restore.py      # Backup + restore a BD temporal
  test_bug11_layout.py        # BUG 11: layout del bloque cubiertos (Playwright)
  test_manual_screens.py      # Screenshots del manual de usuario (Playwright)
  test_replenishment_bug12.py # BUG 12: cobertura por estado de solicitud
  REPORTE_OC_CORREO.md        # Reporte detallado del modulo OC
```

## Requisitos

- Python 3.10+ con `pip install requests`
- Para tests de Playwright (manual_screens, bug11_layout):
  `pip install playwright && playwright install chromium`
- Sistema levantado: `docker compose -f infra/docker/docker-compose.yml up -d`

## Como correr

### Desde la raiz del repo

**PowerShell (Windows nativo):**

```powershell
.\test-e2e.ps1                 # Bateria completa (~70s)
.\test-e2e.ps1 quick           # Sin Playwright (~25s)
.\test-e2e.ps1 oc              # Solo OC
.\test-e2e.ps1 backup          # Solo backup
```

**Make (git-bash / WSL):**

```bash
make e2e                       # Bateria completa
make e2e-quick                 # Sin Playwright
make e2e-oc                    # Solo OC
make e2e-backup                # Solo backup
```

**Python directo:**

```bash
python tests/e2e/run_all.py                          # Bateria completa
python tests/e2e/run_all.py --skip bug11_layout manual_screens
python tests/e2e/run_all.py --only oc_correo_flujo
python tests/e2e/run_all.py --verbose
python tests/e2e/run_all.py --cleanup  # Tambien rechaza OCs previas
```

### Desde esta carpeta

```bash
cd tests/e2e
python run_all.py
```

## Exit codes del orquestador

| Codigo | Significado |
| ------ | ----------- |
| 0      | Todos los tests pasaron |
| 1      | Al menos un test fallo |
| 2      | Error del orquestador (script no existe, sin tests seleccionados) |
| 124    | Timeout del test (configurable por test en `run_all.py`) |
| 130    | Ctrl+C (interrumpido por el usuario) |

## Agregar un test nuevo

1. Crear `tests/e2e/test_<nombre>.py` con `if __name__ == "__main__":` al final
2. Devolver exit 0 si pasa, exit != 0 si falla
3. Imprimir en stdout una linea con `Pasados: N / N` o `[OK]` (el orquestador extrae el resumen)
4. Agregar una entrada en `TESTS` en `run_all.py`:

```python
TestCase(
    name="mi_test",
    script="test_mi_test.py",
    description="Que valida este test",
    timeout_s=120,
),
```

## Convenciones

- **TAG aleatorio por corrida**: cada test que crea datos debe usar un TAG unico
  (random suffix) para no colisionar con corridas previas.
- **Snapshot antes/despues**: para validar que el test no dejo basura, capturar
  estado antes (`codigos_antes`) y comparar al final.
- **Limpieza de ruido**: si hay datos previos de tests anteriores, el orquestador
  los rechaza con `--cleanup`. El test debe tolerar este estado.
- **Idempotencia**: los tests deben poderse correr N veces seguidas sin fallar
  ni dejar el sistema en estado inconsistente.
- **Reportar via stdout**: el orquestador parsea la salida, asi que un test que
  falla debe imprimir contexto suficiente en stdout/stderr.
