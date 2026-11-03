from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
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
    # M0b dossier §5.9: None means <data_dir>/tmp (data/tmp by default); /tmp/cricpulse in the cloud
    tmp_dir: Path | None = None
    snapshot_path: str = ""
    nightly_archive: str = "recently_added_7_json"  # M0b dossier D-2
    keep_snapshots: int = 7  # M0b dossier D-7
    keep_raw_days: int = 30  # M0b dossier D-7

    @field_validator("snapshot_date", mode="before")
    @classmethod
    def set_default_snapshot_date(cls, v: str) -> str:
        if not v or not v.strip():
            return datetime.now(UTC).strftime("%Y-%m-%d")
        return v.strip()

    @model_validator(mode="after")
    def set_default_tmp_dir(self) -> "Settings":
        if self.tmp_dir is None:
            self.tmp_dir = self.data_dir / "tmp"
        return self

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze"

    @property
    def silver_dir(self) -> Path:
        return self.data_dir / "silver"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

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
        # M0b dossier §5.2 storage layout
        for d in (
            self.bronze_dir,
            self.silver_dir,
            self.snapshots_dir,
            self.runs_dir,
            self.tmp_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
