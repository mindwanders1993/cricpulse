import os
from pathlib import Path

import pytest

# Ensure testing environment variable is set so LLM clients run in deterministic mock mode
os.environ["APP_ENV"] = "test"

from src.config import Settings


def pytest_configure(config: pytest.Config) -> None:
    # M0b dossier R-3: the live cricsheet.org checks carry this marker and skip unless CRICPULSE_LIVE=1
    config.addinivalue_line("markers", "live: reaches cricsheet.org; needs CRICPULSE_LIVE=1")


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def mock_settings(temp_dir: Path) -> Settings:
    settings = Settings(data_dir=temp_dir / "data")
    settings.ensure_directories()
    return settings
