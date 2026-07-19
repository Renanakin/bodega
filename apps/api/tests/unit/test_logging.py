"""
Tests unitarios para core/logging.py y core/middleware.py (Regla de Oro R8).
"""
from __future__ import annotations

import pytest
import structlog
from app.core.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
)

pytestmark = pytest.mark.unit


class TestLogging:
    """Logging profesional: context vars, JSON en producción, sin print()."""

    def test_logger_returns_bound_logger(self) -> None:
        log = get_logger("test.module")
        assert log is not None
        assert hasattr(log, "info")
        assert hasattr(log, "error")

    def test_bind_request_context_sets_vars(self, env_development: None) -> None:
        """Los ContextVar se propagan a los logs siguientes."""
        configure_logging()
        bind_request_context(request_id="abc-123", user_id="user-456")
        # Verificar que structlog tiene el context
        ctx = structlog.contextvars.get_contextvars()
        assert ctx.get("request_id") == "abc-123"
        assert ctx.get("user_id") == "user-456"
        clear_request_context()
        ctx = structlog.contextvars.get_contextvars()
        assert ctx.get("request_id") is None

    def test_configure_logging_is_idempotent(self, env_development: None) -> None:
        """Llamar configure_logging() múltiples veces no rompe el estado."""
        configure_logging()
        configure_logging()
        configure_logging()
        # Si llega aquí sin error, es idempotente
        assert True


class TestNoPrintStatements:
    """Verifica R8: no hay print() en código de producción."""

    def test_no_print_in_app_code(self) -> None:
        """Grep estático: cero print() en apps/api/app/."""
        import re
        from pathlib import Path

        app_root = Path(__file__).resolve().parents[2] / "app"
        print_pattern = re.compile(r"^\s*print\s*\(", re.MULTILINE)
        offenders: list[str] = []

        for py_file in app_root.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            if print_pattern.search(content):
                offenders.append(str(py_file.relative_to(app_root.parent)))

        assert not offenders, f"print() found in: {offenders}"


class TestNoOsGetenv:
    """Verifica R1: os.getenv solo en core/."""

    def test_no_os_getenv_outside_core(self) -> None:
        import re
        from pathlib import Path

        app_root = Path(__file__).resolve().parents[2] / "app"
        pattern = re.compile(r"os\.getenv\s*\(", re.MULTILINE)
        offenders: list[str] = []

        for py_file in app_root.rglob("*.py"):
            rel = py_file.relative_to(app_root.parent).as_posix()
            if rel.startswith("app/core/"):
                continue
            content = py_file.read_text(encoding="utf-8")
            if pattern.search(content):
                offenders.append(rel)

        assert not offenders, f"os.getenv found outside core/: {offenders}"


class TestNoHardcodedSecrets:
    """Verifica R1: cero secretos hardcoded fuera de core/."""

    def test_no_password_or_secret_in_code(self) -> None:
        import re
        from pathlib import Path

        app_root = Path(__file__).resolve().parents[2] / "app"
        # Buscar patrones típicos de secretos hardcoded
        patterns = [
            re.compile(r'password\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
            re.compile(r'secret\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
            re.compile(r"postgres://[^/\s]+:[^@\s]+@", re.IGNORECASE),
        ]
        offenders: list[str] = []

        for py_file in app_root.rglob("*.py"):
            rel = py_file.relative_to(app_root.parent).as_posix()
            # Excluir core/ (donde está permitido definir los campos)
            if rel.startswith("app/core/") and not rel.endswith("config.py"):
                continue
            content = py_file.read_text(encoding="utf-8")
            for pat in patterns:
                if pat.search(content):
                    offenders.append(f"{rel}: {pat.pattern}")
                    break

        assert not offenders, f"Hardcoded secrets found: {offenders}"
