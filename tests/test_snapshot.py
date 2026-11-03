from datetime import UTC, date, datetime
from pathlib import Path

from src.snapshot import LatestInfo, latest_path, read_latest, write_latest


def _info(version: str = "v20261026T0230Z", match_count: int = 2) -> LatestInfo:
    return LatestInfo(
        version=version,
        path=f"snapshots/cricket_{version}.duckdb",
        sha256="ab" * 32,
        match_count=match_count,
        delivery_count=500,
        data_cutoff=date(2026, 10, 25),
        parser_version=1,
        created_at=datetime(2026, 10, 26, 2, 41, 7, tzinfo=UTC),
    )


def test_latest_lives_under_snapshots(temp_dir: Path):
    assert latest_path(temp_dir) == temp_dir / "snapshots" / "LATEST.json"


def test_read_latest_missing_returns_none(temp_dir: Path):
    assert read_latest(temp_dir) is None


def test_write_then_read_round_trip(temp_dir: Path):
    info = _info()
    write_latest(temp_dir, info)
    assert read_latest(temp_dir) == info


def test_write_latest_leaves_no_tmp(temp_dir: Path):
    write_latest(temp_dir, _info())
    files = sorted(p.name for p in (temp_dir / "snapshots").iterdir())
    assert files == ["LATEST.json"]


def test_write_latest_replaces_previous(temp_dir: Path):
    write_latest(temp_dir, _info("v20261026T0230Z", match_count=2))
    write_latest(temp_dir, _info("v20261027T0230Z", match_count=3))
    latest = read_latest(temp_dir)
    assert latest is not None
    assert latest.version == "v20261027T0230Z"
    assert latest.match_count == 3
    assert sorted(p.name for p in (temp_dir / "snapshots").iterdir()) == ["LATEST.json"]


def test_latest_json_has_dossier_fields(temp_dir: Path):
    write_latest(temp_dir, _info())
    text = latest_path(temp_dir).read_text()
    for field in (
        "version",
        "path",
        "sha256",
        "match_count",
        "delivery_count",
        "data_cutoff",
        "parser_version",
        "created_at",
    ):
        assert f'"{field}"' in text
    assert '"data_cutoff": "2026-10-25"' in text
