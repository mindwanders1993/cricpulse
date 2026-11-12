"""The run end to end through the CLI: M0b dossier §8 scenarios 1-6 and the D-12 run-safety rules."""

import datetime as dt
import io
import json
import zipfile
from pathlib import Path

import duckdb
import httpx
import orjson
import polars as pl
import pytest
from click.testing import Result
from typer.testing import CliRunner

from src.config import Settings
from src.publisher import main, silver
from src.publisher.archive import parse_to_staging
from src.publisher.bench import Timing, verdict
from src.publisher.quality_gates import QualityGateFailure
from src.publisher.rollout import RolloutError
from src.snapshot import latest_path, read_latest
from src.utils import compute_bytes_sha256

FIXTURES = Path(__file__).parent / "fixtures"
T20 = (FIXTURES / "sample_t20.json").read_bytes()
TEST = (FIXTURES / "sample_test.json").read_bytes()
PEOPLE = (FIXTURES / "sample_people.csv").read_bytes()
NAMES = (FIXTURES / "sample_names.csv").read_bytes()
ARCHIVE = "recently_added_7_json"
BOTH = {"1001.json": T20, "1002.json": TEST}


def _edited(raw: bytes, **info) -> bytes:
    data = orjson.loads(raw)
    data["info"].update(info)
    return orjson.dumps(data)


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, raw in members.items():
            zf.writestr(name, raw)
    return buf.getvalue()


class Cricsheet:
    """cricsheet.org as the run sees it: one archive and the two registers."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.files = {"/register/people.csv": PEOPLE, "/register/names.csv": NAMES}

    def serve(self, members: dict[str, bytes]) -> None:
        self.files[f"/downloads/{ARCHIVE}.zip"] = _zip(members)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # Every setting the run reads is pinned, so nothing comes from .env and all disk is under tmp_path
    s = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        tmp_dir=tmp_path / "data" / "tmp",
        cricsheet_base_url="https://cricsheet.org",
        nightly_archive=ARCHIVE,
        keep_snapshots=7,
        keep_raw_days=30,
        rollout_service="",
    )
    s.ensure_directories()
    return s


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Cricsheet:
    site = Cricsheet()

    def fake_get(client, url, **kwargs):  # mocks stop at the network
        site.calls.append(str(url))
        content = site.files.get(httpx.URL(str(url)).path)
        return httpx.Response(
            200 if content is not None else 404,
            content=content or b"",
            request=httpx.Request("GET", str(url)),
        )

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    return site


def _version(minute: int) -> str:
    return f"v20261101T02{minute:02d}Z"


def _cli(monkeypatch: pytest.MonkeyPatch, minute: int, *argv: str) -> Result:
    """Invoke the CLI with the clock at 02:<minute> UTC on 1 Nov 2026, so the run is _version(minute)."""
    now = dt.datetime(2026, 11, 1, 2, minute, tzinfo=dt.UTC)
    monkeypatch.setattr(main, "_utc_now", lambda: now)
    return CliRunner().invoke(main.app, list(argv))


def _query(settings: Settings, sql: str) -> list[tuple]:
    """Run sql on the snapshot LATEST.json names."""
    info = read_latest(settings.data_dir)
    con = duckdb.connect(str(settings.data_dir / info.path), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _ids(settings: Settings) -> list[str]:
    return [r[0] for r in _query(settings, "SELECT match_id FROM gold.dim_match ORDER BY 1")]


def _report(settings: Settings, minute: int) -> dict:
    return json.loads((settings.runs_dir / f"{_version(minute)}.json").read_text())


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


# --- M0b dossier §8 scenarios 1-6 -----------------------------------------------------------


def test_first_run_publishes_both_matches(monkeypatch, settings: Settings, site: Cricsheet):
    site.serve(BOTH)

    result = _cli(monkeypatch, 1, "run")

    assert result.exit_code == 0, result.output
    info = read_latest(settings.data_dir)
    assert (info.version, info.match_count) == (_version(1), 2)
    assert _ids(settings) == ["1001", "1002"]
    day = settings.bronze_dir / "cricsheet" / "2026-11-01"
    assert (day / f"{ARCHIVE}.zip").exists()
    report = _report(settings, 1)
    assert report["snapshot"] == info.model_dump(mode="json")
    assert (report["source"], report["files_seen"], report["changed"]) == (ARCHIVE, 2, 2)
    assert report["quarantined"] == []
    assert report["registers"] == {
        "people.csv": compute_bytes_sha256(PEOPLE),
        "names.csv": compute_bytes_sha256(NAMES),
    }
    assert list((settings.silver_dir / "_staging").iterdir()) == []
    assert list(settings.tmp_dir.glob("*.duckdb")) == []


def test_second_run_on_the_same_zip_is_up_to_date(monkeypatch, settings: Settings, site: Cricsheet):
    site.serve(BOTH)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    latest_before = latest_path(settings.data_dir).read_bytes()
    snapshots_before = _tree(settings.snapshots_dir)

    result = _cli(monkeypatch, 2, "run")

    assert result.exit_code == 0, result.output
    assert "Up to date" in result.output
    assert latest_path(settings.data_dir).read_bytes() == latest_before
    assert _tree(settings.snapshots_dir) == snapshots_before
    assert not (settings.runs_dir / f"{_version(2)}.json").exists()


def test_an_edited_match_replaces_its_rows_in_a_new_version(
    monkeypatch, settings: Settings, site: Cricsheet
):
    site.serve(BOTH)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    first = read_latest(settings.data_dir)
    site.serve({"1001.json": _edited(T20, city="Edited City"), "1002.json": TEST})

    result = _cli(monkeypatch, 2, "run")

    assert result.exit_code == 0, result.output
    info = read_latest(settings.data_dir)
    assert (info.version, info.match_count) == (_version(2), 2)
    assert info.delivery_count == first.delivery_count  # replaced, not appended
    assert _query(settings, "SELECT city FROM gold.dim_match WHERE match_id = '1001'") == [
        ("Edited City",)
    ]
    assert _report(settings, 2)["files_seen"] == 1  # only the edited member was parsed


def test_an_archive_without_a_match_never_shrinks(monkeypatch, settings: Settings, site: Cricsheet):
    site.serve(BOTH)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    site.serve({"1002.json": TEST})

    result = _cli(monkeypatch, 2, "run", "--reparse-all")

    assert result.exit_code == 0, result.output
    info = read_latest(settings.data_dir)
    assert (info.version, info.match_count) == (_version(2), 2)
    assert _ids(settings) == ["1001", "1002"]  # 1001 stays in Silver (M0b dossier §5.3)
    report = _report(settings, 2)
    assert (report["reparse_all"], report["files_seen"]) == (True, 1)


def test_a_broken_file_among_200_is_quarantined_and_the_run_publishes(
    monkeypatch, settings: Settings, site: Cricsheet
):
    members = {f"{3000 + i}.json": T20 for i in range(199)}
    members["broken.json"] = b'{"meta": '
    site.serve(members)

    result = _cli(monkeypatch, 1, "run")

    assert result.exit_code == 0, result.output
    assert read_latest(settings.data_dir).match_count == 199
    report = _report(settings, 1)
    assert (report["files_seen"], report["changed"]) == (200, 199)
    assert [q["match_id"] for q in report["quarantined"]] == ["broken"]


def test_a_failed_gate_leaves_the_live_snapshot_byte_identical(
    monkeypatch, settings: Settings, site: Cricsheet
):
    site.serve(BOTH)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    latest_before = latest_path(settings.data_dir).read_bytes()
    snapshots_before = _tree(settings.snapshots_dir)
    broken = {f"bad{i}.json": b"not json" for i in range(6)}  # 6 > max(5, 1% of 7): D-5
    site.serve({"1001.json": _edited(T20, city="Edited City"), "1002.json": TEST, **broken})

    result = _cli(monkeypatch, 2, "run")

    assert result.exit_code != 0
    assert isinstance(result.exception, QualityGateFailure)
    assert "[quarantine_bounded]" in str(result.exception)
    assert latest_path(settings.data_dir).read_bytes() == latest_before
    assert _tree(settings.snapshots_dir) == snapshots_before
    assert not (settings.runs_dir / f"{_version(2)}.json").exists()
    assert list(settings.tmp_dir.glob("*.duckdb")) == []


# --- M0b dossier D-12: the run's safety after a failure, a crash or a double start ----------


def test_a_rerun_after_a_failed_gate_rebuilds_and_fails_again(
    monkeypatch, settings: Settings, site: Cricsheet
):
    site.serve(BOTH)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    latest_before = latest_path(settings.data_dir).read_bytes()
    real_gates = main.run_quality_gates
    gated: list[int] = []

    def failing_gates(con, **kwargs):
        gated.append(kwargs["files_seen"])
        raise QualityGateFailure("[forced] gate forced to fail")

    monkeypatch.setattr(main, "run_quality_gates", failing_gates)
    site.serve({"1001.json": _edited(T20, city="Edited City"), "1002.json": TEST})
    assert _cli(monkeypatch, 2, "run").exit_code != 0

    # Same zip, same registers: only the manifest rows of run 2 are newer than LATEST.json (D-12(a))
    result = _cli(monkeypatch, 3, "run")

    assert result.exit_code != 0
    assert isinstance(result.exception, QualityGateFailure)
    assert gated == [1, 0]  # run 3 rebuilt and gated again instead of stopping "up to date"
    assert latest_path(settings.data_dir).read_bytes() == latest_before

    monkeypatch.setattr(main, "run_quality_gates", real_gates)
    assert _cli(monkeypatch, 4, "run").exit_code == 0
    assert read_latest(settings.data_dir).version == _version(4)
    assert _query(settings, "SELECT city FROM gold.dim_match WHERE match_id = '1001'") == [
        ("Edited City",)
    ]


def test_changed_registers_alone_trigger_a_build(monkeypatch, settings: Settings, site: Cricsheet):
    site.serve(BOTH)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    people = PEOPLE + b"aaaa0001,New Player,N Player,,,\n"
    site.files["/register/people.csv"] = people

    result = _cli(monkeypatch, 2, "run")

    assert result.exit_code == 0, result.output
    assert read_latest(settings.data_dir).version == _version(2)
    assert _query(settings, "SELECT count(*) FROM gold.dim_player") == [(7,)]
    report = _report(settings, 2)
    assert report["files_seen"] == 0
    assert report["registers"]["people.csv"] == compute_bytes_sha256(people)


def test_leftover_staging_with_the_marker_is_merged_first(
    monkeypatch, settings: Settings, site: Cricsheet
):
    site.serve({"1002.json": TEST})
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    real_merge = silver.merge

    def crash(*args, **kwargs):
        raise RuntimeError("the job died before the merge")

    monkeypatch.setattr(silver, "merge", crash)
    site.serve(BOTH)
    assert _cli(monkeypatch, 2, "run").exit_code != 0
    leftover = settings.silver_dir / "_staging" / _version(2)
    assert (leftover / main.PARSED_MARKER).exists()
    monkeypatch.setattr(silver, "merge", real_merge)
    site.serve({"1002.json": TEST})  # 1001 is in no archive now: only the leftover holds it

    result = _cli(monkeypatch, 3, "run")

    assert result.exit_code == 0, result.output
    assert not leftover.exists()
    assert _ids(settings) == ["1001", "1002"]
    assert _report(settings, 3)["files_seen"] == 0


def test_leftover_staging_without_the_marker_is_deleted(
    monkeypatch, settings: Settings, site: Cricsheet
):
    leftover = settings.silver_dir / "_staging" / "v20261101T0100Z"
    parse_to_staging([("ghost", "0" * 64, T20)], leftover)  # parsed; the job died before the marker
    site.serve(BOTH)

    result = _cli(monkeypatch, 1, "run")

    assert result.exit_code == 0, result.output
    assert not leftover.exists()
    assert _ids(settings) == ["1001", "1002"]
    silver_ids = pl.read_parquet(settings.silver_dir / "matches.parquet")["match_id"]
    assert sorted(silver_ids.to_list()) == ["1001", "1002"]


def test_a_second_run_in_the_same_minute_is_refused_with_nothing_written(
    monkeypatch, settings: Settings, site: Cricsheet
):
    site.serve(BOTH)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    before = _tree(settings.data_dir)
    site.calls.clear()
    site.serve({"1001.json": _edited(T20, city="Edited City"), "1002.json": TEST})

    result = _cli(monkeypatch, 1, "run")

    assert result.exit_code != 0
    assert isinstance(result.exception, FileExistsError)
    assert _tree(settings.data_dir) == before
    assert site.calls == []  # refused before step 2: nothing downloaded


# --- ingest-local: the same steps on a directory --------------------------------------------


def test_ingest_local_runs_the_same_steps_on_a_directory(
    monkeypatch, settings: Settings, site: Cricsheet, tmp_path: Path
):
    matches_dir = tmp_path / "matches"
    matches_dir.mkdir()
    for name, raw in BOTH.items():
        (matches_dir / name).write_bytes(raw)
    argv = (
        "ingest-local",
        "-m",
        str(matches_dir),
        "-p",
        str(FIXTURES / "sample_people.csv"),
        "-n",
        str(FIXTURES / "sample_names.csv"),
    )

    first = _cli(monkeypatch, 1, *argv)
    second = _cli(monkeypatch, 2, *argv)

    assert first.exit_code == 0, first.output
    assert _ids(settings) == ["1001", "1002"]
    assert _report(settings, 1)["source"] == str(matches_dir)
    assert second.exit_code == 0, second.output
    assert "Up to date" in second.output
    assert site.calls == []  # a local source downloads nothing


def test_a_run_on_an_empty_data_dir_creates_what_it_needs(
    monkeypatch, settings: Settings, site: Cricsheet, tmp_path: Path
):
    # M0b dossier D-14a: get_settings() creates no folders, so the run makes its own
    bare = settings.model_copy(
        update={"data_dir": tmp_path / "bare", "tmp_dir": tmp_path / "bare" / "tmp"}
    )
    monkeypatch.setattr(main, "get_settings", lambda: bare)
    site.serve(BOTH)

    result = _cli(monkeypatch, 1, "run")

    assert result.exit_code == 0, result.output
    assert read_latest(bare.data_dir).match_count == 2
    assert _report(bare, 1)["changed"] == 2


# --- M0b dossier D-13a: the API catches up after every run that ends with a live snapshot ---


@pytest.fixture
def rollouts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The versions the run asked the API service to serve."""
    asked: list[str] = []
    monkeypatch.setattr(main, "ensure_api_on", lambda version, settings: asked.append(version))
    return asked


def test_a_publish_rolls_the_api_out_to_the_new_version(
    monkeypatch, settings: Settings, site: Cricsheet, rollouts: list[str]
):
    site.serve(BOTH)

    assert _cli(monkeypatch, 1, "run").exit_code == 0

    assert rollouts == [_version(1)]


def test_an_up_to_date_run_rolls_the_api_out_to_the_live_version(
    monkeypatch, settings: Settings, site: Cricsheet, rollouts: list[str]
):
    site.serve(BOTH)
    assert _cli(monkeypatch, 1, "run").exit_code == 0

    result = _cli(monkeypatch, 2, "run")

    assert result.exit_code == 0, result.output
    assert "Up to date" in result.output
    assert rollouts == [_version(1), _version(1)]


def test_a_failed_gate_never_rolls_out(
    monkeypatch, settings: Settings, site: Cricsheet, rollouts: list[str]
):
    site.serve(BOTH)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    broken = {f"bad{i}.json": b"not json" for i in range(6)}  # 6 > max(5, 1% of 7): D-5
    site.serve({"1001.json": _edited(T20, city="Edited City"), "1002.json": TEST, **broken})

    result = _cli(monkeypatch, 2, "run")

    assert isinstance(result.exception, QualityGateFailure)
    assert rollouts == [_version(1)]


def test_a_failed_rollout_exits_non_zero_and_keeps_latest_json(
    monkeypatch, settings: Settings, site: Cricsheet
):
    def not_ready(version: str, settings: Settings) -> None:
        raise RolloutError(
            "revision cricpulse-api-00002-abc is not ready: container failed to start"
        )

    monkeypatch.setattr(main, "ensure_api_on", not_ready)
    site.serve(BOTH)

    result = _cli(monkeypatch, 1, "run")

    assert result.exit_code == 1
    assert f"API rollout to {_version(1)} failed" in result.output
    assert "is not ready: container failed to start" in result.output
    assert read_latest(settings.data_dir).version == _version(1)
    assert _report(settings, 1)["changed"] == 2


# --- M0b dossier D-3 and D-13e: the bench ---------------------------------------------------


def test_bench_times_the_five_questions_on_the_live_snapshot(
    monkeypatch, settings: Settings, site: Cricsheet
):
    site.serve(BOTH)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    before = _tree(settings.data_dir)
    # The spike's players are not in the fixture build; these two are (tests/fixtures registers)
    players = ("--batter", "Q de Kock", "--h2h-batter", "Q de Kock", "--h2h-bowler", "Ali Khan")

    result = _cli(monkeypatch, 2, "bench", *players)

    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    assert lines[0] == f"Bench on {_version(1)}: p50 and p95 of 20 warm runs per question"
    rows = [line.split() for line in lines[1:-1]]
    assert [r[0] for r in rows] == [
        "batting_career",
        "leaderboard",
        "matchup_h2h",
        "phase_splits",
        "venue_profile",
    ]
    assert all((r[1], r[3], r[4], r[6]) == ("p50", "ms", "p95", "ms") for r in rows)
    assert lines[-1] in ("D-3: mount", "D-3: bake")
    assert _tree(settings.data_dir) == before  # opened read-only


def test_bench_without_latest_json_exits_non_zero(monkeypatch, settings: Settings, site: Cricsheet):
    result = _cli(monkeypatch, 1, "bench")

    assert result.exit_code == 1
    assert "No LATEST.json" in result.output


def test_bench_verdict_is_mount_only_when_every_p95_is_under_300_ms():
    fast = [Timing("leaderboard", 3.2, 4.3), Timing("phase_splits", 100.0, 299.9)]
    slow = [*fast, Timing("matchup_h2h", 250.0, 300.0)]

    assert (verdict(fast), verdict(slow)) == ("mount", "bake")
