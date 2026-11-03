from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.config import Settings, get_settings
from src.snapshot import (
    LatestInfo,
    latest_path,
    read_latest,
    resolve_snapshot_path,
    write_latest,
)


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


def test_resolve_prefers_snapshot_path_setting(temp_dir: Path):
    write_latest(temp_dir, _info())
    settings = Settings(data_dir=temp_dir, snapshot_path="/elsewhere/pinned.duckdb")
    assert resolve_snapshot_path(settings) == Path("/elsewhere/pinned.duckdb")


def test_resolve_uses_latest_json_when_setting_empty(temp_dir: Path):
    write_latest(temp_dir, _info())
    settings = Settings(data_dir=temp_dir, snapshot_path="")
    expected = temp_dir / "snapshots" / "cricket_v20261026T0230Z.duckdb"
    assert resolve_snapshot_path(settings) == expected


def test_resolve_none_without_setting_or_latest(temp_dir: Path):
    settings = Settings(data_dir=temp_dir, snapshot_path="")
    assert resolve_snapshot_path(settings) is None


def test_app_starts_on_snapshot_named_by_latest_json(temp_dir: Path, monkeypatch):
    info = _info(version="v20261103T0230Z")
    db_file = temp_dir / info.path
    db_file.parent.mkdir(parents=True)
    con = duckdb.connect(str(db_file))
    con.execute("CREATE TABLE marker AS SELECT 'from_latest' AS source")
    con.close()
    write_latest(temp_dir, info)

    settings = get_settings()
    monkeypatch.setattr(settings, "data_dir", temp_dir)
    monkeypatch.setattr(settings, "snapshot_path", "")

    with TestClient(create_app()) as client:
        row = client.app.state.db.execute("SELECT source FROM marker").fetchone()
    assert row == ("from_latest",)
