from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    app_name: str = "Bodegaje API"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    database_path: str = "data/bodegaje.sqlite3"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_database_path(self) -> Path:
        path = Path(self.database_path)
        if path.is_absolute():
            return path
        return API_ROOT / path

    @property
    def sqlite_migrations_dir(self) -> Path:
        return REPO_ROOT / "db" / "migrations" / "sqlite"


settings = Settings()
