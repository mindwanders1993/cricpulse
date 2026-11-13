"""M0b.1 spike: measure parse, Silver size, Gold build, snapshot size, query speed.

Usage: python spike.py <repo> <out_dir> [limit]
Reads Cricsheet JSON from <repo>/data/raw/match_json; writes only under <out_dir>.
"""

import glob
import json
import resource
import statistics
import sys
import time
from pathlib import Path

REPO, OUT = Path(sys.argv[1]), Path(sys.argv[2])
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else None
sys.path.insert(0, str(REPO))

import duckdb  # noqa: E402
import polars as pl  # noqa: E402

from src.builder.loader import DuckDBLoader  # noqa: E402
from src.parsers.match_parser import MatchParser  # noqa: E402
from src.parsers.register_parser import RegisterParser  # noqa: E402
from src.publisher.quality_gates import run_quality_gates  # noqa: E402
from src.semantic import golden_queries as gq  # noqa: E402

TABLES = ["matches", "innings", "deliveries", "wickets", "match_players"]
results: dict = {}


def peak_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024, 1)  # macOS: bytes


def mark(name: str, t0: float, **extra) -> None:
    results[name] = {"seconds": round(time.time() - t0, 1), "peak_rss_mb": peak_mb(), **extra}
    print(name, results[name], flush=True)


files = sorted(glob.glob(str(REPO / "data/raw/match_json/*.json")))
if LIMIT:
    files = files[:LIMIT]
results["files"] = len(files)
OUT.mkdir(parents=True, exist_ok=True)
parser = MatchParser()

# 1. One batch of 1,000 with today's parse_batch
t0 = time.time()
first = parser.parse_batch(files[:1000])
mark("parse_first_1000", t0, deliveries=len(first["deliveries"]))
del first

# 2. All files in batches of 1,000 -> Parquet parts (bounded memory)
parts = OUT / "silver_parts"
t0 = time.time()
failed: list[tuple[str, str]] = []
for b, start in enumerate(range(0, len(files), 1000)):
    frames: dict[str, list[pl.DataFrame]] = {t: [] for t in TABLES}
    for f in files[start : start + 1000]:
        try:
            dfs = parser.parse_file(f)
        except Exception as e:  # quarantine
            failed.append((Path(f).name, f"{type(e).__name__}: {e}"[:200]))
            continue
        for t in TABLES:
            if not dfs[t].is_empty():
                frames[t].append(dfs[t])
    for t in TABLES:
        if frames[t]:
            d = parts / t
            d.mkdir(parents=True, exist_ok=True)
            pl.concat(frames[t], how="vertical_relaxed").write_parquet(
                d / f"part-{b:03d}.parquet", compression="zstd"
            )
mark("parse_all_to_parts", t0, failed=len(failed), failed_examples=failed[:5])

# 3. Compact parts into one Silver file per table (DuckDB, streaming)
silver = OUT / "silver"
silver.mkdir(exist_ok=True)
t0 = time.time()
con = duckdb.connect()
sizes = {}
for t in TABLES:
    out = silver / f"{t}.parquet"
    con.execute(
        f"COPY (SELECT * FROM read_parquet('{parts}/{t}/*.parquet', union_by_name=true)) "
        f"TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    sizes[t] = {
        "mb": round(out.stat().st_size / 1024 / 1024, 1),
        "rows": con.execute(f"SELECT COUNT(*) FROM read_parquet('{out}')").fetchone()[0],
    }
con.close()
mark("silver_compact", t0, sizes=sizes, total_mb=round(sum(v["mb"] for v in sizes.values()), 1))

# 4. Gold build from Silver with today's DDL, register loader, column mapping and marts
db_path = OUT / "cricket_full.duckdb"
db_path.unlink(missing_ok=True)
t0 = time.time()
loader = DuckDBLoader(db_path=db_path)
reg = RegisterParser().parse_registers(
    REPO / "data/raw/register_csv/people.csv", REPO / "data/raw/register_csv/names.csv"
)
loader.load_registers(reg)
c = loader.con
p = lambda t: f"read_parquet('{silver / (t + '.parquet')}')"  # noqa: E731
c.execute(f"""
    INSERT OR REPLACE INTO gold.dim_match (
        match_id, match_date, match_type, gender, season, venue_name, city,
        team1, team2, toss_winner, toss_decision, winner, result_type,
        win_by_runs, win_by_wickets, player_of_match, player_of_match_id,
        is_dls_applied, overs_limit, revision)
    SELECT match_id, match_date::DATE, match_type, gender, season, venue, city,
        team1, team2, toss_winner, toss_decision, winner, result_type,
        win_by_runs, win_by_wickets, player_of_match, player_of_match_id,
        is_dls_applied, overs_limit, revision
    FROM {p("matches")}""")
mark("gold_dim_match", t0)
for gold, src, verb in [
    ("fact_delivery", "deliveries", "INSERT OR REPLACE"),
    ("fact_innings", "innings", "INSERT OR REPLACE"),
    ("fact_wicket_detail", "wickets", "INSERT"),
    ("fact_player_match", "match_players", "INSERT OR REPLACE"),
]:
    t1 = time.time()
    c.execute(f"{verb} INTO gold.{gold} SELECT * FROM {p(src)}")
    mark(f"gold_{gold}", t1)
c.execute("""
    INSERT OR REPLACE INTO gold.dim_venue (venue_id, venue_name, city, country)
    SELECT DISTINCT md5(venue_name), venue_name, city, NULL FROM gold.dim_match WHERE venue_name IS NOT NULL""")
c.execute("""
    INSERT OR REPLACE INTO gold.dim_team (team_id, team_name)
    SELECT DISTINCT md5(team1), team1 FROM gold.dim_match WHERE team1 IS NOT NULL
    UNION SELECT DISTINCT md5(team2), team2 FROM gold.dim_match WHERE team2 IS NOT NULL""")
t1 = time.time()
loader.build_marts()
mark("gold_marts", t1)
t1 = time.time()
gate_error = None
try:
    run_quality_gates(c)
except Exception as e:
    gate_error = f"{type(e).__name__}: {e}"[:300]
mark("quality_gates", t1, error=gate_error)
c.execute("CHECKPOINT")
loader.close()
mark("gold_build_total", t0)

# 5. Snapshot facts
con = duckdb.connect(str(db_path), read_only=True)
counts = {
    t: con.execute(f"SELECT COUNT(*) FROM gold.{t}").fetchone()[0]
    for t in ["dim_match", "fact_delivery", "fact_innings", "dim_player", "dim_venue"]
}
cutoff = str(con.execute("SELECT MAX(match_date) FROM gold.dim_match").fetchone()[0])
results["snapshot"] = {
    "mb": round(db_path.stat().st_size / 1024 / 1024, 1),
    "counts": counts,
    "data_cutoff": cutoff,
}
print("snapshot", results["snapshot"], flush=True)


# 6. Query timings: 5 typical queries, 20 warm runs each + 1 cold (fresh connection)
def pid(name: str) -> str:
    return con.execute(
        "SELECT player_id FROM gold.dim_player WHERE unique_name = ? OR full_name = ? LIMIT 1",
        [name, name],
    ).fetchone()[0]


kohli, bumrah, smith = pid("V Kohli"), pid("JJ Bumrah"), pid("SPD Smith")
venue = con.execute(
    "SELECT md5(venue_name) FROM gold.dim_match GROUP BY venue_name ORDER BY COUNT(*) DESC LIMIT 1"
).fetchone()[0]
queries = {
    "batting_career": lambda k: k.execute(
        "SELECT * FROM gold.mart_player_batting_career WHERE player_id = ?", [kohli]
    ).fetchall(),
    "matchup_h2h": lambda k: gq.get_head_to_head_matchup(k, smith, bumrah, "Test"),
    "phase_splits": lambda k: gq.get_player_phase_splits(k, kohli, "T20"),
    "leaderboard": lambda k: k.execute(
        "SELECT * FROM gold.mart_player_batting_career WHERE UPPER(match_type)='ODI' "
        "ORDER BY total_runs DESC NULLS LAST LIMIT 20"
    ).fetchall(),
    "venue_profile": lambda k: gq.get_venue_phase_and_toss_profile(k, venue, "T20"),
}
timings = {}
for name, fn in queries.items():
    cold_con = duckdb.connect(str(db_path), read_only=True)
    t1 = time.perf_counter()
    try:
        fn(cold_con)
        cold = round((time.perf_counter() - t1) * 1000, 1)
    except Exception as e:
        timings[name] = {"error": f"{type(e).__name__}: {e}"[:200]}
        cold_con.close()
        continue
    cold_con.close()
    runs = []
    for _ in range(20):
        t1 = time.perf_counter()
        fn(con)
        runs.append((time.perf_counter() - t1) * 1000)
    runs.sort()
    timings[name] = {
        "cold_ms": cold,
        "p50_ms": round(statistics.median(runs), 1),
        "p95_ms": round(runs[18], 1),
    }
    print(name, timings[name], flush=True)
results["queries"] = timings
results["peak_rss_mb_total"] = peak_mb()
(OUT / "results.json").write_text(json.dumps(results, indent=2, default=str))
print("DONE", OUT / "results.json")
