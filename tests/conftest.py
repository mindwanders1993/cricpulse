import os
from pathlib import Path

import pytest

# Ensure testing environment variable is set so LLM clients run in deterministic mock mode
os.environ["APP_ENV"] = "test"

from src.config import Settings
from src.ledger import IdempotencyLedger


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def mock_settings(temp_dir: Path) -> Settings:
    settings = Settings(
        data_dir=temp_dir / "data",
        gcs_bucket="test-cricpulse-bucket",
        snapshot_date="2026-08-31",
        force=False,
    )
    settings.ensure_directories()
    return settings


@pytest.fixture
def ledger(temp_dir: Path) -> IdempotencyLedger:
    db_path = temp_dir / "test_ledger.db"
    return IdempotencyLedger(db_path)
