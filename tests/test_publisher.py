import datetime as dt
import shutil
from pathlib import Path

import duckdb
import pytest

from src.builder.loader import DuckDBLoader
from src.config import Settings
from src.parsers.match_parser import PARSER_VERSION, MatchParser
from src.parsers.register_parser import RegisterParser
from src.publisher import publisher as publisher_module
from src.publisher.publisher import SnapshotPublisher
from src.publisher.quality_gates import QualityGateFailure
from src.snapshot import LatestInfo, latest_path, read_latest, write_latest
from src.utils import compute_file_sha256


def _build_db(path: Path) -> Path:
    loader = DuckDBLoader(db_path=path)
    reg_dfs = RegisterParser().parse_registers(
        "tests/fixtures/sample_people.csv",
        "tests/fixtures/sample_names.csv",
    )
    loader.load_registers(reg_dfs)
    match_dfs = MatchParser().parse_batch(
        [
            "tests/fixtures/sample_t20.json",
            "tests/fixtures/sample_test.json",
        ]
    )
    loader.load_matches(match_dfs)
    loader.build_marts()
    loader.close()
    return path


@pytest.fixture
def built_db(temp_dir: Path) -> Path:
    return _build_db(temp_dir / "raw_test.duckdb")


@pytest.fixture
def empty_db(temp_dir: Path) -> Path:
    path = temp_dir / "empty.duckdb"
    duckdb.connect(str(path)).close()  # a valid DuckDB file with no gold schema
    return path


def _latest_for(version: str, match_count: int = 2, delivery_count: int = 10) -> LatestInfo:
    return LatestInfo(
        version=version,
        path=f"snapshots/cricket_{version}.duckdb",
        sha256="0" * 64,
        match_count=match_count,
        delivery_count=delivery_count,
        data_cutoff=dt.date(2026, 11, 1),
        parser_version=PARSER_VERSION,
        created_at=dt.datetime(2026, 11, 1, 2, 30, tzinfo=dt.UTC),
    )


def _nine_snapshots(settings: Settings) -> list[str]:
    versions = [f"v202611{day:02d}T0230Z" for day in range(1, 10)]
    for v in versions:
        (settings.snapshots_dir / f"cricket_{v}.duckdb").write_bytes(v.encode())
    return versions


def _snapshot_names(settings: Settings) -> list[str]:
    return sorted(p.name for p in settings.snapshots_dir.glob("cricket_*.duckdb"))


def test_snapshot_publisher(temp_dir: Path, mock_settings: Settings, built_db: Path):
    publisher = SnapshotPublisher(settings=mock_settings)
    snap_path, latest = publisher.publish_snapshot(built_db, version="v20260831T0000Z")

    assert snap_path.exists()
    assert latest.exists()
    assert snap_path == mock_settings.snapshots_dir / "cricket_v20260831T0000Z.duckdb"
    assert latest == latest_path(mock_settings.data_dir)
    assert read_latest(mock_settings.data_dir).path == "snapshots/cricket_v20260831T0000Z.duckdb"

    # Verify DuckDB can query the published snapshot
    con = duckdb.connect(str(snap_path), read_only=True)
    row = con.execute("SELECT COUNT(*) FROM gold.dim_match;").fetchall()[0]
    assert row[0] == 2
    con.close()

    # M0b.7: the in-place copies and the Parquet export are gone (dossier D-6)
    assert not (mock_settings.published_dir / "cricket_latest.duckdb").exists()
    assert not hasattr(SnapshotPublisher, "export_gold_parquets")


def test_two_publishes_two_files_latest_names_second(mock_settings: Settings, built_db: Path):
    publisher = SnapshotPublisher(settings=mock_settings)
    first = publisher.publish(built_db, "v20261101T0230Z")
    second = publisher.publish(built_db, "v20261102T0230Z")

    assert _snapshot_names(mock_settings) == [
        "cricket_v20261101T0230Z.duckdb",
        "cricket_v20261102T0230Z.duckdb",
    ]
    assert first.path == "snapshots/cricket_v20261101T0230Z.duckdb"
    assert read_latest(mock_settings.data_dir) == second
    assert second.version == "v20261102T0230Z"
    assert second.path == "snapshots/cricket_v20261102T0230Z.duckdb"

    published = mock_settings.data_dir / second.path
    assert second.sha256 == compute_file_sha256(published)
    con = duckdb.connect(str(built_db), read_only=True)
    try:
        assert (
            second.match_count == con.execute("SELECT COUNT(*) FROM gold.dim_match").fetchone()[0]
        )
        assert (
            second.delivery_count
            == con.execute("SELECT COUNT(*) FROM gold.fact_delivery").fetchone()[0]
        )
        assert (
            second.data_cutoff
            == con.execute("SELECT MAX(match_date) FROM gold.dim_match").fetchone()[0]
        )
    finally:
        con.close()
    assert second.match_count == 2
    assert second.delivery_count > 0
    assert second.parser_version == PARSER_VERSION


def test_publish_writes_tmp_then_renames(monkeypatch, mock_settings: Settings, built_db: Path):
    copies: list[str] = []
    moves: list[tuple[str, str]] = []
    real_copy2, real_rename, real_replace = shutil.copy2, Path.rename, Path.replace

    def spy_copy2(src, dst, *args, **kwargs):
        copies.append(Path(dst).name)
        return real_copy2(src, dst, *args, **kwargs)

    def spy_rename(self, target):
        moves.append((self.name, Path(target).name))
        return real_rename(self, target)

    def spy_replace(self, target):
        moves.append((self.name, Path(target).name))
        return real_replace(self, target)

    monkeypatch.setattr(shutil, "copy2", spy_copy2)
    monkeypatch.setattr(Path, "rename", spy_rename)
    monkeypatch.setattr(Path, "replace", spy_replace)

    SnapshotPublisher(settings=mock_settings).publish(built_db, "v20261101T0230Z")

    assert copies == ["cricket_v20261101T0230Z.duckdb.tmp"]
    assert moves == [
        ("cricket_v20261101T0230Z.duckdb.tmp", "cricket_v20261101T0230Z.duckdb"),
        ("LATEST.json.tmp", "LATEST.json"),
    ]
    assert list(mock_settings.snapshots_dir.glob("*.tmp")) == []


def test_publish_runs_no_gates(monkeypatch, mock_settings: Settings, built_db: Path):
    def no_gates(*args, **kwargs):
        raise AssertionError("publish() must not run quality gates")

    monkeypatch.setattr(publisher_module, "run_quality_gates", no_gates)
    # A previous LATEST.json the new snapshot would shrink against: publish() still does not gate
    write_latest(mock_settings.data_dir, _latest_for("v20261031T0230Z", match_count=999))

    info = SnapshotPublisher(settings=mock_settings).publish(built_db, "v20261101T0230Z")

    assert read_latest(mock_settings.data_dir) == info


def test_publish_refuses_existing_snapshot(mock_settings: Settings, built_db: Path, empty_db: Path):
    publisher = SnapshotPublisher(settings=mock_settings)
    info = publisher.publish(built_db, "v20261101T0230Z")
    published = mock_settings.data_dir / info.path
    latest_before = latest_path(mock_settings.data_dir).read_bytes()

    with pytest.raises(FileExistsError):
        publisher.publish(empty_db, "v20261101T0230Z")

    assert compute_file_sha256(published) == info.sha256
    assert latest_path(mock_settings.data_dir).read_bytes() == latest_before


def test_error_before_write_latest_leaves_latest_byte_identical(
    mock_settings: Settings, built_db: Path, empty_db: Path
):
    publisher = SnapshotPublisher(settings=mock_settings)
    first = publisher.publish(built_db, "v20261101T0230Z")
    latest_file = latest_path(mock_settings.data_dir)
    latest_before = latest_file.read_bytes()

    # No gold schema: reading the counts fails after the copy, before write_latest
    with pytest.raises(duckdb.CatalogException):
        publisher.publish(empty_db, "v20261102T0230Z")

    assert latest_file.read_bytes() == latest_before
    assert not latest_file.with_name("LATEST.json.tmp").exists()
    assert compute_file_sha256(mock_settings.data_dir / first.path) == first.sha256


def test_publish_snapshot_gates_against_previous_latest(mock_settings: Settings, built_db: Path):
    write_latest(mock_settings.data_dir, _latest_for("v20261031T0230Z", match_count=3))
    latest_before = latest_path(mock_settings.data_dir).read_bytes()

    with pytest.raises(QualityGateFailure, match=r"\[never_shrinks_matches\]"):
        SnapshotPublisher(settings=mock_settings).publish_snapshot(
            built_db, version="v20261101T0230Z"
        )

    assert latest_path(mock_settings.data_dir).read_bytes() == latest_before
    assert _snapshot_names(mock_settings) == []


def test_prune_keeps_seven_of_nine(mock_settings: Settings):
    versions = _nine_snapshots(mock_settings)
    write_latest(mock_settings.data_dir, _latest_for(versions[-1]))

    deleted = SnapshotPublisher(settings=mock_settings).prune(today=dt.date(2026, 11, 9))

    assert _snapshot_names(mock_settings) == [f"cricket_{v}.duckdb" for v in versions[2:]]
    assert sorted(p.name for p in deleted) == [f"cricket_{v}.duckdb" for v in versions[:2]]


def test_prune_never_deletes_latest_target(mock_settings: Settings):
    versions = _nine_snapshots(mock_settings)
    write_latest(mock_settings.data_dir, _latest_for(versions[0]))  # LATEST names the oldest
    latest_before = latest_path(mock_settings.data_dir).read_bytes()

    SnapshotPublisher(settings=mock_settings).prune(today=dt.date(2026, 11, 9))

    assert _snapshot_names(mock_settings) == [
        f"cricket_{v}.duckdb" for v in [versions[0], *versions[2:]]
    ]
    assert latest_path(mock_settings.data_dir).read_bytes() == latest_before


def test_prune_deletes_raw_zips_older_than_keep_raw_days(mock_settings: Settings):
    cricsheet = mock_settings.bronze_dir / "cricsheet"
    zips = {}
    for day in ("2026-10-04", "2026-10-05", "2026-11-03"):  # 31, 30 and 1 days before 4 Nov
        (cricsheet / day).mkdir(parents=True)
        zips[day] = cricsheet / day / "recently_added_7_json.zip"
        zips[day].write_bytes(b"zip")

    deleted = SnapshotPublisher(settings=mock_settings).prune(today=dt.date(2026, 11, 4))

    assert deleted == [zips["2026-10-04"]]
    assert not (cricsheet / "2026-10-04").exists()
    assert zips["2026-10-05"].exists()
    assert zips["2026-11-03"].exists()
