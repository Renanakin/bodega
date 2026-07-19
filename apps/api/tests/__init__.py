"""
Suite de tests del backend (Regla de Oro R6).

Estructura:
- unit/: tests puros sin I/O.
- integration/: tests con BD real (Postgres) y Redis.
- e2e/: tests end-to-end con el stack completo.

Los tests usan pytest con marcadores:
  @pytest.mark.unit
  @pytest.mark.integration
  @pytest.mark.e2e
  @pytest.mark.concurrency
"""
