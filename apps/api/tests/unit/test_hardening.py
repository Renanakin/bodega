"""
Tests unitarios para el hardening de Fase 10.

Cubre (sin requerir infra externa):
1. test_generate_secrets_password_tiene_requisitos (mayus, minus, digito, simbolo)
2. test_generate_secrets_token_url_safe
3. test_password_hash_iterations_default_es_600k (OWASP 2023)
4. test_jwt_secret_min_length_32_en_produccion
5. test_settings_redact_passwords_en_logs (DATABASE_URL sin password)
6. test_settings_tls_en_produccion_smtp
7. test_settings_secret_key_min_length_32

Los tests no requieren Postgres, Redis, Nginx ni ningun servicio externo.
"""

from __future__ import annotations

import string

import pytest
from pydantic import SecretStr, ValidationError

pytestmark = pytest.mark.unit


class TestGenerateSecrets:
    """``infra/scripts/generate_secrets.py`` genera secretos validos (Fase 10)."""

    def test_generate_secrets_password_tiene_requisitos(self) -> None:
        """Password generado tiene mayuscula, minuscula, digito, simbolo."""
        # Import lazy: generate-secrets.py esta en infra/scripts/, no es parte
        # del paquete app/, asi que lo cargamos por path.
        import importlib.util
        import sys
        from pathlib import Path

        # tests/unit/test_hardening.py -> apps/api/tests/unit
        # parents[4] = <repo>  (REPO_ROOT)
        repo_root = Path(__file__).resolve().parents[4]
        script_path = repo_root / "infra" / "scripts" / "generate-secrets.py"
        if not script_path.exists():
            pytest.skip(f"generate-secrets.py no encontrado en {script_path}")
        spec = importlib.util.spec_from_file_location("generate_secrets", script_path)
        if spec is None or spec.loader is None:
            pytest.skip("No se pudo cargar generate-secrets.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["generate_secrets"] = module
        spec.loader.exec_module(module)
        gen_password = module.generate_password

        # Generar varios passwords para asegurar que el invariante se mantiene.
        for length in [16, 32, 64]:
            pwd = gen_password(length)
            assert len(pwd) == length, f"Length mismatch: {len(pwd)} != {length}"
            assert any(c.isupper() for c in pwd), f"Falta mayuscula en {pwd!r}"
            assert any(c.islower() for c in pwd), f"Falta minuscula en {pwd!r}"
            assert any(c.isdigit() for c in pwd), f"Falta digito en {pwd!r}"
            assert any(c in "!@#$%^&*-_=+" for c in pwd), f"Falta simbolo en {pwd!r}"

    def test_generate_secrets_token_url_safe(self) -> None:
        """Token generado es URL-safe (charset base64url)."""
        import importlib.util
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[4]
        script_path = repo_root / "infra" / "scripts" / "generate-secrets.py"
        if not script_path.exists():
            pytest.skip(f"generate-secrets.py no encontrado en {script_path}")
        spec = importlib.util.spec_from_file_location("generate_secrets", script_path)
        if spec is None or spec.loader is None:
            pytest.skip("No se pudo cargar generate-secrets.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["generate_secrets"] = module
        spec.loader.exec_module(module)
        gen_token = module.generate_token

        # URL-safe = solo [A-Za-z0-9_-], sin '+', '/', '='
        allowed = set(string.ascii_letters + string.digits + "-_")
        for _ in range(5):
            token = gen_token(32)
            assert len(token) >= 32, f"Token muy corto: {len(token)}"
            assert all(c in allowed for c in token), f"Caracter no URL-safe en {token!r}"
            # Verificar que NO contiene caracteres problematicos para .env
            assert "+" not in token, f"Token contiene '+': {token!r}"
            assert "/" not in token, f"Token contiene '/': {token!r}"
            assert "=" not in token, f"Token contiene '=': {token!r}"


class TestPasswordHashingHardening:
    """Password hash con iteraciones OWASP 2023."""

    def test_password_hash_iterations_default_es_600k(self, env_development: None) -> None:
        """Default de ``password_hash_iterations`` es 600_000 (OWASP 2023)."""
        from app.core.config import get_settings

        settings = get_settings()
        assert (
            settings.password_hash_iterations == 600_000
        ), f"Default debe ser 600_000 (OWASP 2023), recibido: {settings.password_hash_iterations}"

    def test_hash_password_con_600k_iteraciones_es_usable(self, env_development: None) -> None:
        """Hash con 600k iteraciones toma < 1s y produce output valido."""
        from app.core.security import hash_password, verify_password

        password = "test-password-seguro-123"
        # Hash toma ~250ms en CPU moderna, pero el threshold de 2s es
        # conservador para CI.
        import time

        start = time.time()
        stored = hash_password(password)
        elapsed = time.time() - start
        assert elapsed < 2.0, f"Hash tomo {elapsed:.2f}s, demasiado lento"
        # El formato es "salt$digest"
        assert "$" in stored, f"Formato invalido: {stored!r}"
        salt, digest = stored.split("$", 1)
        assert len(salt) == 32, f"Salt length incorrecto: {len(salt)}"
        assert len(digest) == 64, "PBKDF2 SHA-256 digest debe ser 64 hex chars"
        # Verify funciona
        assert verify_password(password, stored) is True
        assert verify_password("wrong-password", stored) is False


class TestSettingsHardening:
    """Settings valida secretos y TLS en produccion (Fase 10 hardening)."""

    def test_jwt_secret_min_length_32_en_produccion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """En produccion, JWT_SECRET < 32 chars es rechazado."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/d")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET", "x" * 16)  # < 32
        # Aunque JWT_SECRET falle, el validator de Settings lanza ValidationError
        # antes de llegar al model_validator de production. Verificamos que
        # el validator de longitud funciona.
        from app.core.config import Settings, reset_settings_cache

        reset_settings_cache()
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "jwt_secret" in str(exc_info.value).lower()

    def test_settings_secret_key_min_length_32(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Si SECRET_KEY esta seteado, debe tener >= 32 chars (Fase 10)."""
        monkeypatch.setenv("ENVIRONMENT", "development")  # no prod (skip prod checks)
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/d")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET", "x" * 32)
        monkeypatch.setenv("SECRET_KEY", "short")  # < 32

        from app.core.config import Settings, reset_settings_cache

        reset_settings_cache()
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "secret_key" in str(exc_info.value).lower()

    def test_settings_secret_key_optional_en_dev(self, env_development: None) -> None:
        """En dev, SECRET_KEY=None esta permitido (fallback a JWT_SECRET)."""
        from app.core.config import get_settings

        settings = get_settings()
        assert settings.secret_key is None

    def test_settings_secret_key_requerido_en_produccion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """En produccion, SECRET_KEY=None es RECHAZADO (defense in depth)."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/d")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET", "x" * 32)
        monkeypatch.setenv("SMTP_USE_TLS", "true")
        # NO seteamos SECRET_KEY -> debe fallar.

        from app.core.config import Settings, reset_settings_cache

        reset_settings_cache()
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "secret_key" in str(exc_info.value).lower()
        assert "produccion" in str(exc_info.value).lower()

    def test_settings_tls_en_produccion_smtp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """En produccion, SMTP_USE_TLS=false es RECHAZADO (ADR-0004)."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/d")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET", "x" * 32)
        monkeypatch.setenv("SECRET_KEY", "y" * 32)
        # SMTP_USE_TLS queda en default (false) -> debe fallar.

        from app.core.config import Settings, reset_settings_cache

        reset_settings_cache()
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "smtp" in str(exc_info.value).lower()

    def test_settings_redact_passwords_en_logs(self, env_development: None) -> None:
        """DATABASE_URL en logs/str() no expone el password.

        El metodo ``_redact_url`` de ``app.db.session`` debe ocultar el password.
        Verificamos que existe y funciona.
        """
        try:
            from app.db.session import _redact_url
        except ImportError:
            pytest.skip("_redact_url no esta implementado aun (legacy path)")

        # Caso 1: URL Postgres con password.
        url = "postgresql+asyncpg://user:supersecret@db.example.com:5432/bodegaje"
        redacted = _redact_url(url)
        assert "supersecret" not in redacted, f"Password leaked en: {redacted!r}"
        assert (
            "***" in redacted or "REDACTED" in redacted or "user:" in redacted
        ), f"Redaction no aplicada en: {redacted!r}"

        # Caso 2: URL Redis con password.
        url_redis = "redis://:redis_password@redis.example.com:6379/0"
        redacted_redis = _redact_url(url_redis)
        assert "redis_password" not in redacted_redis, f"Redis password leaked: {redacted_redis!r}"

    def test_settings_jwt_secret_es_secretstr(self, env_development: None) -> None:
        """JWT_SECRET es SecretStr (no se serializa accidentalmente)."""
        from app.core.config import get_settings

        settings = get_settings()
        assert isinstance(settings.jwt_secret, SecretStr)
        # repr() no debe exponer el valor.
        repr_str = repr(settings.jwt_secret)
        assert "**********" in repr_str or "SecretStr" in repr_str
        # get_secret_value() si lo expone (uso explicito, OK).
        assert len(settings.jwt_secret.get_secret_value()) > 0

    def test_settings_production_log_format_json_por_defecto(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """En produccion, log_format default es 'json' (parseable)."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/d")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET", "x" * 32)
        monkeypatch.setenv("SECRET_KEY", "y" * 32)
        monkeypatch.setenv("SMTP_USE_TLS", "true")
        # NO seteamos LOG_FORMAT -> debe ser json (default).

        from app.core.config import get_settings, reset_settings_cache

        reset_settings_cache()
        settings = get_settings()
        assert settings.log_format == "json", (
            f"En produccion, log_format debe ser 'json' (parseable), "
            f"recibido: {settings.log_format!r}"
        )

    def test_approval_token_usa_secret_key_dedicated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Approval tokens usan SECRET_KEY dedicado (no JWT_SECRET) en produccion."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/d")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET", "a" * 32)
        monkeypatch.setenv("SECRET_KEY", "b" * 32)  # DISTINTO a JWT_SECRET
        monkeypatch.setenv("SMTP_USE_TLS", "true")

        from app.core.config import reset_settings_cache
        from app.core.security import _get_serializer

        reset_settings_cache()
        serializer = _get_serializer()
        # El serializer debe usar SECRET_KEY (b...), no JWT_SECRET (a...).
        # El itsdangerous URLSafeTimedSerializer guarda el secret internamente;
        # verificar via payload firmado.
        token = serializer.dumps({"test": "value"})
        # Decodificar con secret_key
        from itsdangerous import BadSignature, URLSafeTimedSerializer  # noqa: PLC0415

        verifier_correct = URLSafeTimedSerializer(
            secret_key="b" * 32, salt="bodegaje-approval-token"
        )
        verifier_wrong = URLSafeTimedSerializer(secret_key="a" * 32, salt="bodegaje-approval-token")
        # El correcto debe poder verificar.
        verifier_correct.loads(token, max_age=3600)
        # El incorrecto (JWT_SECRET) debe FALLAR -> confirma que se usa SECRET_KEY.
        with pytest.raises(BadSignature):
            verifier_wrong.loads(token, max_age=3600)
