"""
Tests unitarios para core/config.py (Reglas de Oro R1, R2).
"""

from __future__ import annotations

import pytest
from app.core.config import Settings, get_settings, reset_settings_cache, select_env_file
from pydantic import SecretStr, ValidationError

pytestmark = pytest.mark.unit


class TestSettings:
    """Settings rechaza valores inválidos y carga desde .env correcto."""

    def test_rejects_short_jwt_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """R1: jwt_secret debe tener al menos 32 caracteres."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/d")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET", "short")
        reset_settings_cache()
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "jwt_secret" in str(exc_info.value).lower()

    def test_rejects_invalid_database_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """R1: database_url debe usar driver asyncpg o aiosqlite."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("DATABASE_URL", "mysql://u:p@localhost:3306/d")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET", "x" * 32)
        reset_settings_cache()
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "database_url" in str(exc_info.value).lower()

    def test_loads_valid_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Settings acepta valores válidos y los expone tipados."""
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/d")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET", "x" * 32)
        monkeypatch.setenv("SMTP_HOST", "mail.example.com")
        reset_settings_cache()

        settings = Settings()
        assert settings.environment == "staging"
        assert settings.is_production is False
        assert settings.is_development is False
        assert isinstance(settings.jwt_secret, SecretStr)
        assert settings.smtp_host == "mail.example.com"

    def test_get_settings_is_cached(self, env_development: None) -> None:
        """get_settings() devuelve siempre la misma instancia (singleton)."""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_cors_origins_csv_is_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CORS_ALLOWED_ORIGINS como CSV se parsea a lista vía property."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/d")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("JWT_SECRET", "x" * 32)
        monkeypatch.setenv(
            "CORS_ALLOWED_ORIGINS", "https://app.example.com,https://admin.example.com"
        )
        reset_settings_cache()
        from app.core.config import Settings

        settings = Settings()
        assert "https://app.example.com" in settings.cors_origins_list
        assert "https://admin.example.com" in settings.cors_origins_list
        # El campo crudo sigue siendo string
        assert isinstance(settings.cors_allowed_origins, str)


class TestSelectEnvFile:
    """select_env_file elige el archivo según ENVIRONMENT (R2)."""

    def test_defaults_to_development(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        # El archivo puede no existir en el path; verificamos que no lance
        result = select_env_file()
        assert result is None or result.endswith((".env", ".env.development"))

    def test_returns_production_file_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        result = select_env_file()
        # Si no existe el archivo, retorna None; si existe, debe ser .env.production
        assert result is None or ".env.production" in result
