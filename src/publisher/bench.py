"""The D-3 measurement: the five spike questions timed on one snapshot, read-only (M0b dossier D-13e)."""

import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import duckdb

from src.semantic import golden_queries as gq

RUNS = 20  # M0b dossier D-13e: 20 warm runs per question
P95_LIMIT_MS = 300.0  # M0b dossier D-3: read from the mount when a typical query is < 300 ms p95
# The players docs/features/m0b_spike/spike.py timed, so the cloud numbers compare with the spike's
BATTER, H2H_BATTER, H2H_BOWLER = "V Kohli", "SPD Smith", "JJ Bumrah"


@dataclass(frozen=True)
class Timing:
    question: str
    p50_ms: float
    p95_ms: float


def _player_id(con: duckdb.DuckDBPyConnection, name: str) -> str:
    row = con.execute(
        "SELECT player_id FROM gold.dim_player WHERE unique_name = ? OR full_name = ? LIMIT 1",
        [name, name],
    ).fetchone()
    if row is None:
        raise ValueError(f"player not in gold.dim_player: {name}")
    return row[0]


def _questions(
    con: duckdb.DuckDBPyConnection, batter: str, h2h_batter: str, h2h_bowler: str
) -> dict[str, Callable[[], object]]:
    """The five questions of M0b spike §2.4, as spike.py asks them."""
    bat, h2h_bat, h2h_bowl = (_player_id(con, n) for n in (batter, h2h_batter, h2h_bowler))
    venue = con.execute(
        "SELECT md5(venue_name) FROM gold.dim_match GROUP BY venue_name ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()[0]
    return {
        "batting_career": lambda: con.execute(
            "SELECT * FROM gold.mart_player_batting_career WHERE player_id = ?", [bat]
        ).fetchall(),
        "leaderboard": lambda: con.execute(
            "SELECT * FROM gold.mart_player_batting_career WHERE UPPER(match_type)='ODI' "
            "ORDER BY total_runs DESC NULLS LAST LIMIT 20"
        ).fetchall(),
        "matchup_h2h": lambda: gq.get_head_to_head_matchup(con, h2h_bat, h2h_bowl, "Test"),
        "phase_splits": lambda: gq.get_player_phase_splits(con, bat, "T20"),
        "venue_profile": lambda: gq.get_venue_phase_and_toss_profile(con, venue, "T20"),
    }


def run_bench(
    db_path: Path,
    batter: str = BATTER,
    h2h_batter: str = H2H_BATTER,
    h2h_bowler: str = H2H_BOWLER,
) -> list[Timing]:
    """Open db_path read-only and time each question RUNS times after one untimed warm-up run."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        timings = []
        for question, ask in _questions(con, batter, h2h_batter, h2h_bowler).items():
            ask()
            runs = []
            for _ in range(RUNS):
                start = time.perf_counter()
                ask()
                runs.append((time.perf_counter() - start) * 1000)
            runs.sort()
            # p95 as the spike took it: the 19th of 20 sorted runs
            p95 = runs[int(RUNS * 0.95) - 1]
            timings.append(Timing(question, round(statistics.median(runs), 1), round(p95, 1)))
        return timings
    finally:
        con.close()


def verdict(timings: list[Timing]) -> str:
    """M0b dossier D-3: "mount" when every p95 is under the limit, else "bake" it into the image."""
    return "mount" if all(t.p95_ms < P95_LIMIT_MS for t in timings) else "bake"
