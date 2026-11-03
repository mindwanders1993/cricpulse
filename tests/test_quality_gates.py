from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from src.builder.loader import DuckDBLoader
from src.parsers.match_parser import MatchParser
from src.parsers.register_parser import RegisterParser
from src.publisher.quality_gates import QualityGateFailure, run_quality_gates
from src.snapshot import LatestInfo

EXISTING_SEVEN = [
    "dim_player_uniqueness",
    "dim_match_uniqueness",
    "delivery_grain_uniqueness",
    "referential_integrity_delivery_match",
    "non_negative_runs",
    "valid_over_numbers",
    "marts_populated",
]


@pytest.fixture
def con(temp_dir: Path) -> duckdb.DuckDBPyConnection:
    """A Gold build of the two fixture matches."""
    loader = DuckDBLoader(db_path=temp_dir / "gates.duckdb")
    loader.load_registers(
        RegisterParser().parse_registers(
            "tests/fixtures/sample_people.csv", "tests/fixtures/sample_names.csv"
        )
    )
    loader.load_matches(
        MatchParser().parse_batch(
            ["tests/fixtures/sample_t20.json", "tests/fixtures/sample_test.json"]
        )
    )
    loader.build_marts()
    yield loader.con
    loader.close()


def _counts(con: duckdb.DuckDBPyConnection) -> tuple[int, int]:
    matches = con.execute("SELECT COUNT(*) FROM gold.dim_match").fetchone()[0]
    deliveries = con.execute("SELECT COUNT(*) FROM gold.fact_delivery").fetchone()[0]
    return matches, deliveries


def _previous(match_count: int, delivery_count: int) -> LatestInfo:
    return LatestInfo(
        version="v20261102T0230Z",
        path="snapshots/cricket_v20261102T0230Z.duckdb",
        sha256="cd" * 32,
        match_count=match_count,
        delivery_count=delivery_count,
        data_cutoff=date(2026, 11, 1),
        parser_version=1,
        created_at=datetime(2026, 11, 2, 2, 41, tzinfo=UTC),
    )


def _duplicate_one_row(con: duckdb.DuckDBPyConnection, table: str) -> None:
    # A copy without constraints, as the fact tables will be after D-10, with one row doubled
    con.execute(
        f"CREATE OR REPLACE TABLE gold.{table} AS "
        f"SELECT * FROM gold.{table} UNION ALL (SELECT * FROM gold.{table} LIMIT 1)"
    )


def _names(results: list[dict]) -> list[str]:
    return [r["check"] for r in results]


# --- defaults, first run --------------------------------------------------------------------


def test_existing_seven_unchanged_and_pass(con):
    results = run_quality_gates(con)
    names = _names(results)
    assert names[:7] == EXISTING_SEVEN
    assert all(r["passed"] for r in results)


def test_previous_none_skips_shrink_gates(con):
    names = _names(run_quality_gates(con, previous=None))
    assert "never_shrinks_matches" not in names
    assert "never_shrinks_deliveries" not in names
    assert {
        "innings_grain_uniqueness",
        "player_match_grain_uniqueness",
        "quarantine_bounded",
    } <= set(names)


# --- never_shrinks_matches ------------------------------------------------------------------


def test_never_shrinks_matches_passes_on_equal_count(con):
    matches, deliveries = _counts(con)
    results = run_quality_gates(con, previous=_previous(matches, deliveries))
    gate = next(r for r in results if r["check"] == "never_shrinks_matches")
    assert gate["passed"] and gate["value"] == matches


def test_never_shrinks_matches_fails_when_fewer(con):
    matches, deliveries = _counts(con)
    with pytest.raises(QualityGateFailure, match=r"\[never_shrinks_matches\]") as exc:
        run_quality_gates(con, previous=_previous(matches + 1, deliveries))
    assert "never_shrinks_deliveries" not in str(exc.value)


# --- never_shrinks_deliveries ---------------------------------------------------------------


def test_never_shrinks_deliveries_passes_within_tolerance(con):
    matches, deliveries = _counts(con)
    # previous is the largest count for which today's count is still >= 0.999 x previous
    previous_deliveries = int(deliveries / 0.999)
    assert previous_deliveries > deliveries
    results = run_quality_gates(con, previous=_previous(matches, previous_deliveries))
    gate = next(r for r in results if r["check"] == "never_shrinks_deliveries")
    assert gate["passed"]


def test_never_shrinks_deliveries_fails_below_tolerance(con):
    matches, deliveries = _counts(con)
    with pytest.raises(QualityGateFailure, match=r"\[never_shrinks_deliveries\]") as exc:
        run_quality_gates(con, previous=_previous(matches, int(deliveries / 0.999) + 1))
    assert "never_shrinks_matches" not in str(exc.value)


# --- quarantine_bounded ---------------------------------------------------------------------


def test_quarantine_bounded_floor_of_five(con):
    results = run_quality_gates(con, quarantined=5, files_seen=10)
    gate = next(r for r in results if r["check"] == "quarantine_bounded")
    assert gate["passed"] and gate["value"] == 5


def test_quarantine_bounded_fails_over_floor(con):
    with pytest.raises(QualityGateFailure, match=r"\[quarantine_bounded\]"):
        run_quality_gates(con, quarantined=6, files_seen=10)


def test_quarantine_bounded_one_percent(con):
    # 1% of 1,050 rounds up to 11, above the floor of 5
    run_quality_gates(con, quarantined=11, files_seen=1050)
    with pytest.raises(QualityGateFailure, match=r"\[quarantine_bounded\]"):
        run_quality_gates(con, quarantined=12, files_seen=1050)


def test_quarantine_bounded_exact_one_percent(con):
    # 1% of 700 is exactly 7: 7 passes, 8 fails
    run_quality_gates(con, quarantined=7, files_seen=700)
    with pytest.raises(QualityGateFailure, match=r"\[quarantine_bounded\]"):
        run_quality_gates(con, quarantined=8, files_seen=700)


# --- grain gates (D-10) ---------------------------------------------------------------------


def test_innings_grain_gate_passes(con):
    results = run_quality_gates(con)
    assert next(r for r in results if r["check"] == "innings_grain_uniqueness")["passed"]


def test_innings_grain_gate_fails_on_duplicate(con):
    _duplicate_one_row(con, "fact_innings")
    with pytest.raises(QualityGateFailure, match=r"\[innings_grain_uniqueness\]") as exc:
        run_quality_gates(con)
    assert "player_match_grain_uniqueness" not in str(exc.value)


def test_player_match_grain_gate_passes(con):
    results = run_quality_gates(con)
    assert next(r for r in results if r["check"] == "player_match_grain_uniqueness")["passed"]


def test_player_match_grain_gate_fails_on_duplicate(con):
    _duplicate_one_row(con, "fact_player_match")
    with pytest.raises(QualityGateFailure, match=r"\[player_match_grain_uniqueness\]") as exc:
        run_quality_gates(con)
    assert "innings_grain_uniqueness" not in str(exc.value)
