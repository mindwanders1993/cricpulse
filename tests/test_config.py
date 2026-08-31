from pathlib import Path

from src.config import Settings, get_settings


def test_settings_default_directories(temp_dir: Path):
    s = Settings(data_dir=temp_dir / "data")
    s.ensure_directories()
    assert s.raw_dir.exists()
    assert s.raw_match_dir.exists()
    assert s.raw_register_dir.exists()
    assert s.parquet_dir.exists()
    assert s.published_dir.exists()


def test_settings_snapshot_date_default():
    s = Settings(snapshot_date="")
    assert len(s.snapshot_date) == 10  # YYYY-MM-DD format
    assert s.snapshot_date.count("-") == 2


def test_get_settings_singleton():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
