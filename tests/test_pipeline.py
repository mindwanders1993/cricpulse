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
from src.parsers.match_parser import MatchParser
from src.publisher import archive, main, manifest, quarantine, silver
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


# --- M0b dossier D-17: a match a newer parser rejects leaves the app; the error table --------

REAL_PARSE_JSON = MatchParser.parse_json


def _one_ball(raw: bytes) -> bytes:
    """The T20 cut to its first ball: removing it drops 1 of 1,604 deliveries, inside the 0.999 gate."""
    data = orjson.loads(raw)
    first = data["innings"][0]
    first["overs"] = [{**first["overs"][0], "deliveries": first["overs"][0]["deliveries"][:1]}]
    data["innings"] = [first]
    return orjson.dumps(data)


ONE_BALL = _one_ball(T20)
WORLD = {**BOTH, "9001.json": ONE_BALL}


def _parser(monkeypatch: pytest.MonkeyPatch, version: int, *rejected: str) -> None:
    """A parser change (M0b dossier D-17g): PARSER_VERSION is `version` and it rejects `rejected`."""

    def parse_json(self, match_id, data):
        if match_id in rejected:
            raise ValueError(f"rejected by parser {version}: {match_id}")
        return REAL_PARSE_JSON(self, match_id, data)

    monkeypatch.setattr(MatchParser, "parse_json", parse_json)
    for module in (main, archive):
        monkeypatch.setattr(module, "PARSER_VERSION", version)


def _both_teams(raw: bytes) -> bytes:
    """A new revision that lists one player for both teams, which the parser rejects (D-16c)."""
    data = orjson.loads(raw)
    first, second = data["info"]["teams"]
    data["info"]["players"][second].append(data["info"]["players"][first][0])
    data["meta"]["revision"] += 1
    return orjson.dumps(data)


def _silver_ids(settings: Settings, table: str) -> set[str]:
    return set(pl.read_parquet(settings.silver_dir / f"{table}.parquet")["match_id"])


def _manifest_ids(settings: Settings) -> set[str]:
    return set(manifest.load(settings.data_dir)["match_id"])


def _error_table(settings: Settings) -> dict[str, dict]:
    return {r["match_id"]: r for r in quarantine.load(settings.data_dir).iter_rows(named=True)}


def _remove_9001(monkeypatch: pytest.MonkeyPatch, settings: Settings, site: Cricsheet) -> Result:
    """Run 1 publishes WORLD; run 2, on parser 2, rejects the unchanged 9001 and removes it."""
    site.serve(WORLD)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    _parser(monkeypatch, 2, "9001")
    result = _cli(monkeypatch, 2, "run")
    assert result.exit_code == 0, result.output
    return result


def test_an_unchanged_file_a_newer_parser_rejects_leaves_the_app(
    monkeypatch, settings: Settings, site: Cricsheet
):
    result = _remove_9001(monkeypatch, settings, site)

    assert "quarantined: 1, removed: 1" in result.output
    for table in silver.TABLES:
        assert "9001" not in _silver_ids(settings, table), table
    assert _manifest_ids(settings) == {"1001", "1002"}
    info = read_latest(settings.data_dir)
    assert (info.version, info.match_count) == (_version(2), 2)
    assert _ids(settings) == ["1001", "1002"]
    row = _error_table(settings)["9001"]
    assert row == {
        "match_id": "9001",
        "file_sha256": compute_bytes_sha256(ONE_BALL),
        "parser_version": 2,
        "error": "ValueError: rejected by parser 2: 9001",
        "action": "removed",
        "version": _version(2),
    }
    assert _report(settings, 2)["quarantined"] == [row]


def test_a_rejected_new_revision_keeps_the_last_good_rows(
    monkeypatch, settings: Settings, site: Cricsheet
):
    site.serve(BOTH)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    first = read_latest(settings.data_dir)
    manifest_before = manifest.load(settings.data_dir)
    revision = _both_teams(T20)
    site.serve({"1001.json": revision, "1002.json": TEST})

    result = _cli(monkeypatch, 2, "run")

    assert result.exit_code == 0, result.output
    assert "quarantined: 1, removed: 0" in result.output
    info = read_latest(settings.data_dir)
    assert (info.version, info.match_count) == (_version(2), 2)
    assert info.delivery_count == first.delivery_count
    assert _query(settings, "SELECT city FROM gold.dim_match WHERE match_id = '1001'") == [
        ("Morrisville",)
    ]
    assert manifest.load(settings.data_dir).equals(manifest_before)
    row = _error_table(settings)["1001"]
    assert (row["action"], row["file_sha256"], row["version"]) == (
        "kept_last_good",
        compute_bytes_sha256(revision),
        _version(2),
    )
    assert row["error"] == "ValueError: player listed for both teams: Q de Kock"
    assert _report(settings, 2)["quarantined"] == [row]


def test_a_rejected_new_id_is_not_loaded(monkeypatch, settings: Settings, site: Cricsheet):
    site.serve({**BOTH, "1003.json": b"not json"})

    result = _cli(monkeypatch, 1, "run")

    assert result.exit_code == 0, result.output
    assert _ids(settings) == ["1001", "1002"]
    assert _manifest_ids(settings) == {"1001", "1002"}
    row = _error_table(settings)["1003"]
    assert (row["action"], row["file_sha256"], row["version"]) == (
        "not_loaded",
        compute_bytes_sha256(b"not json"),
        _version(1),
    )
    assert _report(settings, 1)["quarantined"] == [row]


def test_a_second_run_with_the_same_rejected_file_stops_up_to_date(
    monkeypatch, settings: Settings, site: Cricsheet
):
    _remove_9001(monkeypatch, settings, site)
    latest_before = latest_path(settings.data_dir).read_bytes()
    table_before = quarantine.quarantine_path(settings.data_dir).read_bytes()

    result = _cli(monkeypatch, 3, "run")

    assert result.exit_code == 0, result.output
    assert "Up to date" in result.output
    assert "Changed: 0" in result.output  # 9001 is skipped while the error table holds it
    assert latest_path(settings.data_dir).read_bytes() == latest_before
    assert quarantine.quarantine_path(settings.data_dir).read_bytes() == table_before
    assert not (settings.runs_dir / f"{_version(3)}.json").exists()


def test_a_file_that_later_parses_cleanly_leaves_the_table_and_is_back_in_gold(
    monkeypatch, settings: Settings, site: Cricsheet
):
    _remove_9001(monkeypatch, settings, site)
    _parser(monkeypatch, 3)  # the parser fix: version 3 accepts 9001 again

    result = _cli(monkeypatch, 3, "run")

    assert result.exit_code == 0, result.output
    info = read_latest(settings.data_dir)
    assert (info.version, info.match_count) == (_version(3), 3)
    assert _ids(settings) == ["1001", "1002", "9001"]
    assert _error_table(settings) == {}
    assert _report(settings, 3)["quarantined"] == []
    assert manifest.load(settings.data_dir).filter(pl.col("match_id") == "9001")[
        "parser_version"
    ].to_list() == [3]


def test_a_retry_after_a_gate_failure_that_followed_a_removal_passes_never_shrinks_matches(
    monkeypatch, settings: Settings, site: Cricsheet
):
    site.serve(WORLD)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    real_gates = main.run_quality_gates

    def failing_gates(con, **kwargs):
        raise QualityGateFailure("[forced] gate forced to fail")

    monkeypatch.setattr(main, "run_quality_gates", failing_gates)
    _parser(monkeypatch, 2, "9001")
    # Only 9001 is served, so the error-table row alone is newer than LATEST.json (D-17e)
    site.serve({"9001.json": ONE_BALL})
    assert _cli(monkeypatch, 2, "run").exit_code != 0  # 9001 left Silver; nothing was published
    assert read_latest(settings.data_dir).version == _version(1)
    assert manifest.load(settings.data_dir).filter(pl.col("version") > _version(1)).is_empty()
    seen: list[dict] = []

    def recording_gates(con, **kwargs):
        results = real_gates(con, **kwargs)
        seen.extend(results)
        return results

    monkeypatch.setattr(main, "run_quality_gates", recording_gates)

    result = _cli(monkeypatch, 3, "run")

    assert result.exit_code == 0, result.output
    assert _report(settings, 3)["files_seen"] == 0  # 9001 is held, yet its removal still counts
    gate = next(r for r in seen if r["check"] == "never_shrinks_matches")
    assert gate == {"check": "never_shrinks_matches", "passed": True, "value": 2, "removed": 1}
    assert read_latest(settings.data_dir).match_count == 2


def test_once_a_removal_is_live_any_other_drop_still_fails_never_shrinks_matches(
    monkeypatch, settings: Settings, site: Cricsheet
):
    _remove_9001(monkeypatch, settings, site)
    latest_before = latest_path(settings.data_dir).read_bytes()
    silver.remove(settings.silver_dir, ["1001"])  # a loss the error table knows nothing about
    site.files["/register/people.csv"] = PEOPLE + b"aaaa0001,New Player,N Player,,,\n"

    result = _cli(monkeypatch, 3, "run")

    assert isinstance(result.exception, QualityGateFailure)
    assert "[never_shrinks_matches] Fewer matches than live snapshot" in str(result.exception)
    assert "less 0 removed" in str(result.exception)  # 9001's removal is already in LATEST.json
    assert latest_path(settings.data_dir).read_bytes() == latest_before


def test_a_crash_between_the_silver_removal_and_the_manifest_write_is_finished_by_the_next_run(
    monkeypatch, settings: Settings, site: Cricsheet
):
    site.serve(WORLD)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    _parser(monkeypatch, 2, "9001")
    site.serve({"9001.json": ONE_BALL})  # nothing parses, so nothing is staged but the plan
    real_remove = silver.remove

    def remove_then_crash(*args, **kwargs):
        real_remove(*args, **kwargs)
        raise RuntimeError("the job died before the manifest write")

    monkeypatch.setattr(silver, "remove", remove_then_crash)
    assert _cli(monkeypatch, 2, "run").exit_code != 0
    leftover = settings.silver_dir / "_staging" / _version(2)
    assert (leftover / main.PARSED_MARKER).exists()
    assert "9001" not in _silver_ids(settings, "matches")
    assert "9001" in _manifest_ids(settings)  # the half-done removal
    monkeypatch.setattr(silver, "remove", real_remove)

    result = _cli(monkeypatch, 3, "run")

    assert result.exit_code == 0, result.output
    assert not leftover.exists()
    assert _manifest_ids(settings) == {"1001", "1002"}
    for table in silver.TABLES:
        assert "9001" not in _silver_ids(settings, table), table
    info = read_latest(settings.data_dir)
    assert (info.version, info.match_count) == (_version(3), 2)
    assert _ids(settings) == ["1001", "1002"]
    row = _error_table(settings)["9001"]
    assert (row["action"], row["version"]) == ("removed", _version(2))


def test_reparse_all_retries_rejected_files(monkeypatch, settings: Settings, site: Cricsheet):
    _parser(monkeypatch, 1, "9001")  # this parser rejects 9001 from the first run
    site.serve(WORLD)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    assert _error_table(settings)["9001"]["action"] == "not_loaded"
    assert "Up to date" in _cli(monkeypatch, 2, "run").output  # held, so skipped (D-17d)
    _parser(monkeypatch, 1)  # fixed with the same PARSER_VERSION: only --reparse-all reads it again

    result = _cli(monkeypatch, 3, "run", "--reparse-all")

    assert result.exit_code == 0, result.output
    assert _report(settings, 3)["files_seen"] == 3
    assert _ids(settings) == ["1001", "1002", "9001"]
    assert _error_table(settings) == {}


# --- M0b dossier D-17(h): a rejected file counts toward quarantine_bounded until a run publishes

SIX_BROKEN = {f"bad{i}.json": b"not json" for i in range(6)}  # 6 > max(5, 1%): D-5


def _six_broken_twice(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, site: Cricsheet
) -> tuple[bytes, dict[str, bytes]]:
    """Run 1 publishes BOTH; runs 2 and 3 serve six broken new files beside it and both fail.

    Returns LATEST.json and the snapshots tree as run 1 left them."""
    site.serve(BOTH)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    before = (latest_path(settings.data_dir).read_bytes(), _tree(settings.snapshots_dir))
    site.serve({**BOTH, **SIX_BROKEN})
    for minute in (2, 3):
        result = _cli(monkeypatch, minute, "run")
        assert isinstance(result.exception, QualityGateFailure), result.output
        assert "[quarantine_bounded] 6 of 6 files quarantined, limit 5" in str(result.exception)
    return before


def test_a_retry_after_a_quarantine_bounded_failure_fails_it_again(
    monkeypatch, settings: Settings, site: Cricsheet
):
    latest_before, snapshots_before = _six_broken_twice(monkeypatch, settings, site)

    assert latest_path(settings.data_dir).read_bytes() == latest_before
    assert _tree(settings.snapshots_dir) == snapshots_before  # nothing published
    for minute in (2, 3):
        assert not (settings.runs_dir / f"{_version(minute)}.json").exists()
    # Run 3 read none of the six again: they were held (D-17d), and still counted (D-17h)
    assert {r["version"] for r in _error_table(settings).values()} == {_version(2)}


def test_held_rows_stop_counting_once_their_files_parse(
    monkeypatch, settings: Settings, site: Cricsheet
):
    _six_broken_twice(monkeypatch, settings, site)
    site.serve({**BOTH, **{name: T20 for name in SIX_BROKEN}})  # Cricsheet's fixed revisions

    result = _cli(monkeypatch, 4, "run")

    assert result.exit_code == 0, result.output
    assert read_latest(settings.data_dir).match_count == 8
    assert _error_table(settings) == {}


def test_held_rows_stop_counting_once_a_publish_moves_latest_json_past_them(
    monkeypatch, settings: Settings, site: Cricsheet
):
    site.serve(BOTH)
    assert _cli(monkeypatch, 1, "run").exit_code == 0
    real_gates = main.run_quality_gates
    gated: list[tuple[int, int]] = []

    def failing_gates(con, **kwargs):
        raise QualityGateFailure("[forced] gate forced to fail")

    def recording_gates(con, **kwargs):
        gated.append((kwargs["quarantined"], kwargs["files_seen"]))
        return real_gates(con, **kwargs)

    three = {f"bad{i}.json": b"not json" for i in range(3)}
    monkeypatch.setattr(main, "run_quality_gates", failing_gates)
    site.serve({**BOTH, **three})
    assert _cli(monkeypatch, 2, "run").exit_code != 0  # three rows newer than LATEST.json
    monkeypatch.setattr(main, "run_quality_gates", recording_gates)
    one = {"new0.json": b"not json"}
    site.serve({**BOTH, **three, **one})
    assert _cli(monkeypatch, 3, "run").exit_code == 0  # 1 own + 3 held = 4, within 5: publishes
    four = {f"late{i}.json": b"not json" for i in range(4)}
    site.serve({**BOTH, **three, **one, **four})

    result = _cli(monkeypatch, 4, "run")

    # LATEST.json is now run 3, past every older row: only run 4's own four count, not 8
    assert result.exit_code == 0, result.output
    assert gated == [(4, 4), (4, 4)]
    assert read_latest(settings.data_dir).version == _version(4)


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


def test_ingest_local_skips_a_file_the_error_table_holds(
    monkeypatch, settings: Settings, site: Cricsheet, tmp_path: Path
):
    matches_dir = tmp_path / "matches"
    matches_dir.mkdir()
    for name, raw in {**BOTH, "1003.json": b"not json"}.items():
        (matches_dir / name).write_bytes(raw)
    argv = ("ingest-local", "-m", str(matches_dir), "-p", str(FIXTURES / "sample_people.csv"))
    argv += ("-n", str(FIXTURES / "sample_names.csv"))

    first = _cli(monkeypatch, 1, *argv)
    second = _cli(monkeypatch, 2, *argv)

    assert first.exit_code == 0, first.output
    assert _error_table(settings)["1003"]["action"] == "not_loaded"
    assert second.exit_code == 0, second.output
    assert "Up to date" in second.output  # M0b dossier D-17(d)


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
