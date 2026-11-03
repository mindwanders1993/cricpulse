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


def test_settings_m0b_defaults(temp_dir: Path):
    s = Settings(data_dir=temp_dir / "data")
    assert s.tmp_dir == temp_dir / "data" / "tmp"
    assert s.snapshot_path == ""
    assert s.nightly_archive == "recently_added_7_json"
    assert s.keep_snapshots == 7
    assert s.keep_raw_days == 30


def test_settings_tmp_dir_override(temp_dir: Path):
    s = Settings(data_dir=temp_dir / "data", tmp_dir=temp_dir / "scratch")
    s.ensure_directories()
    assert s.tmp_dir == temp_dir / "scratch"
    assert s.tmp_dir.is_dir()


def test_settings_m0b_directories(temp_dir: Path):
    s = Settings(data_dir=temp_dir / "data")
    s.ensure_directories()
    for name in ("bronze", "silver", "snapshots", "runs", "tmp"):
        assert (temp_dir / "data" / name).is_dir()
