from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    data_dir: Path = Path("data")
    gcs_bucket: str = "cricpulse-data"
    cricsheet_base_url: str = "https://cricsheet.org"
    snapshot_date: str = Field(default="")
    force: bool = False
    sync_secret_token: str = "dev-secret-token"
    gemini_api_key: str = ""

    @field_validator("snapshot_date", mode="before")
    @classmethod
    def set_default_snapshot_date(cls, v: str) -> str:
        if not v or not v.strip():
            return datetime.now(UTC).strftime("%Y-%m-%d")
        return v.strip()

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def raw_match_dir(self) -> Path:
        return self.raw_dir / "match_json"

    @property
    def raw_register_dir(self) -> Path:
        return self.raw_dir / "register_csv"

    @property
    def parquet_dir(self) -> Path:
        return self.data_dir / "parquet"

    @property
    def published_dir(self) -> Path:
        return self.data_dir / "published"

    @property
    def ledger_db_path(self) -> Path:
        return self.data_dir / "ledger.db"

    def ensure_directories(self) -> None:
        """Ensure all required local scratch directories exist."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.raw_match_dir.mkdir(parents=True, exist_ok=True)
        self.raw_register_dir.mkdir(parents=True, exist_ok=True)
        self.parquet_dir.mkdir(parents=True, exist_ok=True)
        self.published_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
