"""
Configuración central de la aplicación.

Implementa las Reglas de Oro:
- R1 (Cero Hardcoding): toda config se lee de variables de entorno.
- R2 (Aislamiento de Entornos): el archivo .env se selecciona según ENVIRONMENT.

Uso:
    from app.core.config import get_settings
    settings = get_settings()
    db_url = settings.database_url
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Paths base del proyecto
# config.py vive en apps/api/app/core/ en el repo local (4 niveles al REPO_ROOT).
# En Docker (imagen) vive en /app/app/core/ (3 niveles al /app root). Hacemos
# deteccion robusta subiendo hasta que REPO_ROOT no contenga a API_ROOT.
_API_CORE = Path(__file__).resolve().parent
API_ROOT = _API_CORE.parent.parent  # apps/api/
# En repo local: 4 niveles. En Docker: 3 niveles. Probamos 4 y si
# nos pasamos, fallback a 3.
try:
    _candidate_root = API_ROOT.parent.parent
    # Si subimos a un dir que no contiene API_ROOT, es el REPO_ROOT correcto.
    if API_ROOT.parent.name == "apps" and _candidate_root.name != "apps":
        REPO_ROOT = _candidate_root
    else:
        REPO_ROOT = API_ROOT.parent  # Docker /app
except IndexError:
    REPO_ROOT = API_ROOT.parent

# Entornos permitidos (R2)
Environment = Literal["development", "staging", "production"]


class Settings(BaseSettings):
    """Configuración de la aplicación, validada por Pydantic.

    Los tipos estrictos (PostgresDsn, RedisDsn, SecretStr, EmailStr) hacen
    que Pydantic rechace valores inválidos al cargar la configuración.
    """

    # --- Entorno (R2) ---
    environment: Environment = Field(
        default="development",
        description="Entorno de ejecución: development, staging, production.",
    )
    debug: bool = Field(
        default=False,
        description="Activa el modo debug (NO usar en producción).",
    )
    app_name: str = Field(default="Bodegaje API")
    app_version: str = Field(default="0.1.0")
    api_v1_prefix: str = Field(default="/api/v1")

    # --- Database (R1: nunca hardcoded) ---
    # Opcional: si no se define, el backend por defecto es SQLite (Fase 0/1 legacy).
    # En compose dev/staging/production, `database_url` se setea explícitamente.
    database_url: str | None = Field(
        default=None,
        description=(
            "URL completa de BD. Si es postgresql+asyncpg:// usa Postgres; "
            "si es sqlite:// usa SQLite async. Vacío = default SQLite file."
        ),
    )
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=100)
    database_echo: bool = Field(default=False, description="Log SQL queries. SOLO development.")
    db_backend: str = Field(
        default="sqlite",
        description="Backend activo: 'postgres' o 'sqlite'. Auto-detect desde database_url.",
    )

    # --- Redis (ADR-0004) ---
    # `redis_url` es la fuente canonica (la usan el engine de cache y
    # cualquier cliente que use redis.from_url). `redis_host`/`redis_port`/
    # `redis_db` se exponen como campos separados para que el worker Arq
    # (que recibe `RedisSettings` con campos discretos) los consuma sin
    # tener que parsear la URL en cada llamada.
    redis_url: str = Field(
        ...,
        description="URL completa de Redis. Ej: redis://localhost:6379/0",
    )
    redis_host: str = Field(
        default="localhost",
        description="Host de Redis. Se usa en Arq RedisSettings (ADR-0004).",
    )
    redis_port: int = Field(
        default=6379,
        ge=1,
        le=65535,
        description="Puerto de Redis. Se usa en Arq RedisSettings (ADR-0004).",
    )
    redis_db: int = Field(
        default=0,
        ge=0,
        le=15,
        description="DB de Redis (0-15). Se usa en Arq RedisSettings (ADR-0004).",
    )

    # --- Auth & Security (R1) ---
    jwt_secret: SecretStr = Field(
        ...,
        description="Secreto para firmar tokens de sesion JWT. MÍNIMO 32 caracteres.",
    )
    # Secret dedicado para tokens de aprobacion OC (ADR-0005/0006).
    # Si esta vacio, se hace fallback a ``jwt_secret`` (compat dev/test).
    # En produccion se RECOMIENDA un valor DIFERENTE a ``jwt_secret``
    # (defense in depth: compromiso de JWT no expone tokens de aprobacion).
    secret_key: SecretStr | None = Field(
        default=None,
        description=(
            "Secreto dedicado para HMAC de approval tokens (ADR-0005). "
            "Opcional; si no se setea, se usa ``jwt_secret``. MÍNIMO 32 chars. "
            "En produccion se recomienda un valor distinto a ``jwt_secret``."
        ),
    )
    jwt_algorithm: str = Field(default="HS256")
    session_duration_hours: int = Field(default=12, ge=1, le=168)
    # OWASP Password Storage Cheat Sheet (2023): PBKDF2-HMAC-SHA256 con
    # 600_000 iteraciones. Subimos de 120_000 (legacy Fase 0/1) a 600_000
    # para cumplir OWASP. Iterar 600k con PBKDF2 toma ~250ms en CPU moderna,
    # aceptable para login. Cost-of-attack vs cost-of-login balanceado.
    password_hash_iterations: int = Field(
        default=600_000,
        ge=100_000,
        description=(
            "Iteraciones PBKDF2-HMAC-SHA256 para hashear passwords. "
            "Default 600_000 = OWASP 2023 recommendation."
        ),
    )

    # --- SMTP (ADR-0005) ---
    smtp_host: str = Field(default="mailpit")
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_username: str | None = Field(default=None)
    smtp_password: SecretStr | None = Field(default=None)
    smtp_from: EmailStr = Field(default="noreply@bodega.example")
    smtp_use_tls: bool = Field(
        default=False, description="STARTTLS. Activar en staging/production."
    )
    smtp_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=120,
        description="Timeout para la conexión SMTP (Fase 7, ADR-0004).",
    )

    # --- Email Outbox policy (Fase 7, ADR-0004) ---
    email_max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Cantidad máxima de intentos de envío por email.",
    )
    # Backoff en CSV para compatibilidad con env vars. Parseo en property.
    # Default = 30s, 5min, 30min (3 intentos cubre los reintentos).
    email_retry_backoff_seconds: str = Field(
        default="30,300,1800",
        description=(
            "Backoff exponencial (segundos) entre reintentos SMTP, CSV. "
            "Ej: '30,300,1800' = 30s, 5min, 30min."
        ),
    )

    @property
    def email_retry_backoff_list(self) -> list[int]:
        """Lista de backoff en segundos parseada desde ``email_retry_backoff_seconds``.

        Garantiza que tenga al menos ``email_max_attempts`` elementos
        (extiende con el último valor si faltan).
        """
        try:
            values = [
                int(p.strip()) for p in self.email_retry_backoff_seconds.split(",") if p.strip()
            ]
        except ValueError as e:
            raise ValueError(
                f"email_retry_backoff_seconds inválido: {self.email_retry_backoff_seconds!r} ({e})"
            ) from e
        if not values:
            return [30, 300, 1800]
        # Extender si hace falta para que haya al menos email_max_attempts.
        while len(values) < self.email_max_attempts:
            values.append(values[-1])
        return values

    # --- Public URLs (Fase 7) ---
    # Usado por NotificationsService.enqueue() para construir approve_url
    # y reject_url en la plantilla del email. En dev: http://localhost:5173
    # En prod: https://bodega.example (configurable via env).
    public_base_url: str = Field(
        default="http://localhost:5173",
        description=(
            "URL base publica donde la webapp esta expuesta. Se usa para "
            "construir los enlaces approve/reject en el email de OC."
        ),
    )

    # --- Observability (R8 + Fase 9) ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description=(
            "Nivel de log global. En dev: INFO. En production: INFO. "
            "Subir a DEBUG solo para troubleshooting temporal."
        ),
    )
    log_format: Literal["json", "console"] = Field(
        default="json",
        description=(
            "Formato de log. ``json`` (default) emite JSON a stdout "
            "(parseable por Datadog/Loki); ``console`` emite texto "
            "coloreado. En production SIEMPRE ``json``."
        ),
    )
    sentry_dsn: str | None = Field(
        default=None,
        description=(
            "DSN de Sentry. Vacio = desactivado. Si esta set, "
            "Sentry captura excepciones no manejadas automaticamente "
            "con stacktrace, request_id, user context, etc."
        ),
    )
    sentry_traces_sample_rate: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description=(
            "Fraccion de transactions a samplear para tracing en Sentry. "
            "0.0 = sin tracing, 1.0 = 100% (caro). Default 0.1 (10%) "
            "es un buen balance costo/cobertura para produccion."
        ),
    )
    sentry_profiles_sample_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Fraccion de eventos a los que se les toma profile de CPU. "
            "0.0 = desactivado. 0.1 = 10% de profiles sobre transactions "
            "sampleadas. Solo activar si hay problemas de performance."
        ),
    )
    sentry_environment: str | None = Field(
        default=None,
        description=(
            "Entorno override para Sentry. Si None, usa ``environment``. "
            "Util para separar staging vs production con el mismo DSN."
        ),
    )
    metrics_enabled: bool = Field(
        default=True,
        description=(
            "Expone el endpoint ``/metrics`` con el formato Prometheus. "
            "Si False, se desactiva el Instrumentator (util para tests)."
        ),
    )
    metrics_path: str = Field(
        default="/metrics",
        description=(
            "Path donde se expone el endpoint Prometheus. Default ``/metrics`` "
            "(estandar). Cambiar solo si choca con un route existente."
        ),
    )

    # --- CORS (almacenado como CSV para compatibilidad con env vars) ---
    cors_allowed_origins: str = Field(
        default="http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1,http://localhost",
        description="Orígenes permitidos para CORS, separados por coma. Se parsea vía property.",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Lista de orígenes parseada desde cors_allowed_origins (CSV)."""
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    # --- Approval Tokens (ADR-0005/0006) ---
    approval_token_max_age_days: int = Field(default=7, ge=1, le=30)
    # TTL generico de tokens firmados (reseteo password, magic links, etc).
    # Por defecto 7 dias, alineado con approval_token_max_age_days.
    token_expiration_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description=(
            "TTL generico (dias) para tokens firmados (approval OC, magic links, "
            "reset password). Por defecto 7 dias."
        ),
    )

    # --- Background Workers (ADR-0004) ---
    worker_concurrency: int = Field(default=4, ge=1, le=32)
    worker_max_jobs: int = Field(default=10, ge=1, le=100)
    replenishment_eval_interval_seconds: int = Field(default=300, ge=60)
    replenishment_interval_minutes: int = Field(
        default=5,
        ge=1,
        le=60,
        description=(
            "Cada cuantos minutos corre el ReplenishmentEvaluator (Fase 4). "
            "El valor en segundos existe para el scheduler interno; este "
            "campo se usa para la configuracion del cron de Arq."
        ),
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str | None) -> str | None:
        """Asegura que database_url (si está definida) use un driver soportado.

        Acepta:
        - postgresql+asyncpg://...  → PostgreSQL async (producción)
        - sqlite+aiosqlite://...    → SQLite async (tests rápidos)
        - sqlite://...              → SQLite legacy (compat)
        - None / vacío              → default legacy SQLite file
        """
        if value is None or value == "":
            return None
        if not value.startswith(("postgresql+asyncpg://", "sqlite+aiosqlite://", "sqlite://")):
            raise ValueError(
                "database_url debe usar un driver soportado. "
                "Ej: postgresql+asyncpg://user:pass@host:5432/db"
            )
        return value

    @field_validator("db_backend")
    @classmethod
    def validate_db_backend(cls, value: str) -> str:
        """Solo acepta valores explícitos para evitar typos silenciosos."""
        allowed = ("postgres", "sqlite")
        if value not in allowed:
            raise ValueError(f"db_backend debe ser uno de {allowed}, recibido: {value!r}")
        return value

    @model_validator(mode="after")
    def _sync_db_backend_from_url(self) -> Settings:
        """Si database_url está definida, sincroniza db_backend con el scheme.

        Prioridad: valor explícito de `db_backend` gana sobre la auto-detección,
        para que los tests puedan forzar el backend sin depender del env.
        """
        url = self.database_url
        if url is None or url == "":
            # Mantener el default ('sqlite') — el caller no pidió URL explícita.
            return self
        if url.startswith(("postgresql+asyncpg://", "postgresql://")):
            object.__setattr__(self, "db_backend", "postgres")
        elif url.startswith(("sqlite+aiosqlite://", "sqlite://")):
            object.__setattr__(self, "db_backend", "sqlite")
        return self

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret_strength(cls, value: SecretStr) -> SecretStr:
        """Falla si el secreto es demasiado corto (R1, seguridad)."""
        secret = value.get_secret_value()
        if len(secret) < 32:
            raise ValueError("jwt_secret debe tener al menos 32 caracteres.")
        return value

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key_strength(cls, value: SecretStr | None) -> SecretStr | None:
        """Si ``secret_key`` esta seteado, debe tener al menos 32 caracteres.

        Si esta en None, se hace fallback a ``jwt_secret`` (compat dev/test).
        """
        if value is None:
            return None
        secret = value.get_secret_value()
        if len(secret) < 32:
            raise ValueError("secret_key debe tener al menos 32 caracteres (o None).")
        return value

    @model_validator(mode="after")
    def _derive_redis_discrete_from_url(self) -> Settings:
        """FIX redis_host/port desincronizados: si ``redis_host``/``port``/``db``
        no se setean explicitamente, se derivan de ``redis_url``.

        Antes, los defaults ``localhost:6379/0`` sobrescribian la URL
        real (ej. ``redis://redis:6379/0`` en Docker), lo que causaba
        que el worker Arq se conectara a un host incorrecto.

        Ahora: si el operador setea ``REDIS_HOST``/``REDIS_PORT``/``REDIS_DB``
        explicitamente, gana. Si no, se parsea la URL.
        """
        from urllib.parse import urlparse

        # Solo derivar si redis_url es una URL valida (no placeholder).
        if not self.redis_url or not self.redis_url.startswith(("redis://", "rediss://")):
            return self

        try:
            parsed = urlparse(self.redis_url)
        except ValueError:
            return self

        # Si redis_host/port/db son los defaults genericos, sobrescribir con la URL.
        if parsed.hostname and self.redis_host == "localhost":
            object.__setattr__(self, "redis_host", parsed.hostname)
        if parsed.port and self.redis_port == 6379:
            object.__setattr__(self, "redis_port", parsed.port)
        # redis_db: el path es "/0", "/1", etc. (default 0)
        if parsed.path and parsed.path.startswith("/"):
            try:
                db_from_url = int(parsed.path.lstrip("/").split("/")[0] or "0")
                if self.redis_db == 0:
                    object.__setattr__(self, "redis_db", db_from_url)
            except ValueError:
                pass
        return self

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> Settings:
        """Reglas de endurecimiento en produccion (Fase 10).

        En ``production``:
        - ``secret_key`` DEBE estar seteado (no se acepta fallback a jwt_secret).
        - ``smtp_use_tls`` debe ser True (Fase 7, ADR-0004: STARTTLS obligatorio).
        - ``debug`` DEBE ser False (OWASP A05:2021 — debug mode expone
          stack traces, settings internos, variables de entorno, queries
          SQL completas en responses 500. Prohibido en produccion).
        """
        if self.environment != "production":
            return self
        if self.secret_key is None:
            raise ValueError(
                "secret_key es OBLIGATORIO en produccion "
                "(defense in depth: tokens de aprobacion OC deben firmar "
                "con un secreto distinto a jwt_secret)."
            )
        if not self.smtp_use_tls:
            raise ValueError(
                "smtp_use_tls debe ser True en produccion (ADR-0004: "
                "STARTTLS obligatorio para SMTP)."
            )
        if self.debug:
            raise ValueError(
                "debug=True esta PROHIBIDO en produccion (OWASP A05:2021). "
                "El modo debug expone stack traces y settings internos en "
                "responses 500. Desactivar antes de desplegar."
            )
        return self

    model_config = SettingsConfigDict(
        # El archivo .env se selecciona dinamicamente en ``_select_env_file_for_env``
        # (validator ``before``) segun el ENVIRONMENT de CADA instancia.
        # Antes se seteaba al importar el modulo, lo cual contaminaba los tests
        # con el .env del environment de la shell del test runner.
        env_file=None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def _select_env_file_for_env(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Selecciona el .env correcto segun ENVIRONMENT (Fase 10 — Issue 2).

        Se ejecuta antes de la validacion de campos, lo cual permite que
        cada instancia de ``Settings`` (ej. en tests con monkeypatch)
        use el .env del ENVIRONMENT que se setea en el momento, no
        el que estaba al importar el modulo.

        Si el caller pasa ``_env_file=None`` explicitamente (tests de
        hardening), respeta eso y NO carga ningun .env.
        """
        # Si el caller ya especifico _env_file (incluso None), respetar.
        if "_env_file" in values:
            return values
        # Determinar el env de forma robusta: argumento explicito > env var > default.
        env: str = (
            values.get("environment")
            or os.environ.get("ENVIRONMENT")
            or "development"
        )
        env = str(env).lower()
        if env not in ("development", "staging", "production"):
            env = "development"
        # Forzar que select_env_file() lea con el ENVIRONMENT ya seteado.
        prev = os.environ.get("ENVIRONMENT")
        os.environ["ENVIRONMENT"] = env
        try:
            cls.model_config["env_file"] = select_env_file()
        finally:
            if prev is None:
                os.environ.pop("ENVIRONMENT", None)
            else:
                os.environ["ENVIRONMENT"] = prev
        return values

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    # --- Compatibilidad con código legacy (Fase 0/1) ---
    # DEPRECAR en Fase 3+ cuando todo el código use AsyncSession.

    @property
    def resolved_database_path(self) -> Path:
        """DEPRECATED: solo para el SQLiteDatabase legacy. Usa database_url async."""
        # Devuelve un path ficticio para mantener compat con create_database()
        return API_ROOT / "data" / "bodegaje.sqlite3"

    @property
    def sqlite_migrations_dir(self) -> Path:
        """DEPRECATED: solo para el SQLiteDatabase legacy."""
        return REPO_ROOT / "db" / "migrations" / "sqlite"


def select_env_file() -> str | None:
    """Selecciona el archivo .env según la variable ENVIRONMENT (R2).

    Orden de búsqueda (Fase 10 — Issue 2):
      1. ``infra/.env.<env>``        — fuente canonica post-Fase 10 (48 vars)
      2. ``infra/.env.<env>.example``— fallback si no hay copia materializada
      3. ``<repo>/.env.<env>``       — legacy raiz (28 vars), compat Fase 0-9
      4. ``<api>/.env.<env>``        — legacy API
      5. ``<cwd>/.env.<env>``        — override local del dev

    Returns:
        Path al archivo .env.<environment> o None si no existe.
    """
    environment = os.getenv("ENVIRONMENT", "development").lower()
    if environment not in ("development", "staging", "production"):
        environment = "development"

    candidates = [
        REPO_ROOT / "infra" / f".env.{environment}",
        REPO_ROOT / "infra" / f".env.{environment}.example",
        REPO_ROOT / f".env.{environment}",
        API_ROOT / f".env.{environment}",
        Path.cwd() / f".env.{environment}",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    # En desarrollo, también aceptar .env genérico
    if environment == "development":
        for candidate in [REPO_ROOT / ".env", API_ROOT / ".env", Path.cwd() / ".env"]:
            if candidate.exists():
                return str(candidate)
    return None


# Inyectar el env_file inicial al importar (sirve para los lugares donde se
# instancia Settings sin pasar por el validator ``before``, ej. fuera de tests).
Settings.model_config["env_file"] = select_env_file()
# En tests, el validator ``before`` (``_select_env_file_for_env``) sobreescribe
# este valor en cada instancia con el .env del ENVIRONMENT vigente al momento.


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton cacheado de Settings (R1, R2).

    Usar siempre esta función en lugar de instanciar Settings() directamente.
    El decorador @lru_cache garantiza que solo se lee el .env una vez por proceso.
    """
    return Settings()  # legacy fallback; ver docstring


def reset_settings_cache() -> None:
    """Útil para tests que necesitan recargar la configuración."""
    get_settings.cache_clear()
