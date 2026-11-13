import copy
import zipfile
from pathlib import Path

import duckdb
import orjson
import polars as pl
import pytest

from src.builder.loader import MEMORY_LIMIT, DuckDBLoader
from src.config import Settings
from src.parsers.match_parser import PARSER_VERSION, MatchParser
from src.parsers.register_parser import RegisterParser
from src.publisher import archive, manifest, silver
from src.publisher.quality_gates import run_quality_gates


def test_duckdb_loader_and_marts(temp_dir: Path):
    db_path = temp_dir / "test_cricpulse.duckdb"
    loader = DuckDBLoader(db_path=db_path)

    # 1. Load registers
    reg_parser = RegisterParser()
    reg_dfs = reg_parser.parse_registers(
        "tests/fixtures/sample_people.csv",
        "tests/fixtures/sample_names.csv",
    )
    loader.load_registers(reg_dfs)

    # Verify dim_player
    player_cnt = loader.con.execute("SELECT COUNT(*) FROM gold.dim_player;").fetchall()[0][0]
    assert player_cnt == 6

    # 2. Load matches
    match_parser = MatchParser()
    match_dfs = match_parser.parse_batch(
        [
            "tests/fixtures/sample_t20.json",
            "tests/fixtures/sample_test.json",
        ]
    )
    loader.load_matches(match_dfs)

    # Verify dim_match and fact_delivery
    match_cnt = loader.con.execute("SELECT COUNT(*) FROM gold.dim_match;").fetchall()[0][0]
    assert match_cnt == 2

    deliv_cnt = loader.con.execute("SELECT COUNT(*) FROM gold.fact_delivery;").fetchall()[0][0]
    assert deliv_cnt > 200

    # 3. Build Marts
    loader.build_marts()

    batting_cnt = loader.con.execute(
        "SELECT COUNT(*) FROM gold.mart_player_batting_career;"
    ).fetchall()[0][0]
    assert batting_cnt > 0

    bowling_cnt = loader.con.execute(
        "SELECT COUNT(*) FROM gold.mart_player_bowling_career;"
    ).fetchall()[0][0]
    assert bowling_cnt > 0

    # Test bowling economy exclusion of byes/leg-byes
    econ_check = loader.con.execute(
        "SELECT MIN(economy_rate), MAX(economy_rate) FROM gold.mart_player_bowling_career;"
    ).fetchall()[0]
    assert econ_check[0] is not None and econ_check[0] >= 0

    # 4. Run Quality Gates
    results = run_quality_gates(loader.con)
    assert len(results) >= 7
    assert all(r["passed"] for r in results)

    loader.close()


# --- M0b.5: Gold from Silver -------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"
MATCH_FIXTURES = ("sample_t20.json", "sample_test.json")
GOLD_MATCH_TABLES = (
    "dim_match",
    "fact_delivery",
    "fact_innings",
    "fact_wicket_detail",
    "fact_player_match",
    "dim_venue",
    "dim_team",
)


def _silver_from_fixtures(root: Path) -> Path:
    """Build Silver the way the pipeline does: zip → iter_changed → parse_to_staging → merge."""
    zp = root / "all_json.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        for name in MATCH_FIXTURES:
            zf.writestr(name, (FIXTURES / name).read_bytes())
    staging = root / "silver" / "_staging" / "v1"
    items = archive.iter_changed(zp, pl.DataFrame(schema=manifest.SCHEMA), PARSER_VERSION, True)
    assert archive.parse_to_staging(items, staging).quarantined == []
    silver_dir = root / "silver"
    silver.merge(silver_dir, staging)
    return silver_dir


def _checksums(con: duckdb.DuckDBPyConnection) -> dict[str, tuple[int, str]]:
    """Row count and an order-independent checksum of every row, per Gold match table."""
    out = {}
    for table in GOLD_MATCH_TABLES:
        out[table] = con.execute(f"""
            SELECT count(*), md5(coalesce(string_agg(h, ',' ORDER BY h), ''))
            FROM (SELECT md5(CAST(t AS VARCHAR)) AS h FROM gold.{table} AS t)
        """).fetchone()
    return out


def test_build_from_silver_matches_load_matches(temp_dir: Path, mock_settings: Settings):
    silver_dir = _silver_from_fixtures(temp_dir)

    from_dfs = DuckDBLoader(db_path=temp_dir / "from_dfs.duckdb")
    from_dfs.load_matches(MatchParser().parse_batch([str(FIXTURES / n) for n in MATCH_FIXTURES]))
    from_silver = DuckDBLoader(db_path=temp_dir / "from_silver.duckdb")
    from_silver.build_from_silver(silver_dir, settings=mock_settings)

    expected = _checksums(from_dfs.con)
    assert expected["dim_match"][0] == 2
    assert expected["fact_delivery"][0] > 200
    assert all(rows > 0 for rows, _ in expected.values())
    assert _checksums(from_silver.con) == expected
    from_dfs.close()
    from_silver.close()


def test_build_from_silver_loads_registers_and_builds_marts(
    temp_dir: Path, mock_settings: Settings
):
    silver_dir = _silver_from_fixtures(temp_dir)
    reg_dfs = RegisterParser().parse_registers(
        "tests/fixtures/sample_people.csv",
        "tests/fixtures/sample_names.csv",
    )
    loader = DuckDBLoader(db_path=temp_dir / "snapshot.duckdb")
    loader.build_from_silver(silver_dir, reg_dfs, settings=mock_settings)
    loader.build_marts()

    assert loader.con.execute("SELECT count(*) FROM gold.dim_player").fetchone()[0] == 6
    assert all(r["passed"] for r in run_quality_gates(loader.con))
    loader.close()


def test_build_from_silver_sets_memory_limit_and_spill_dir(temp_dir: Path, mock_settings: Settings):
    loader = DuckDBLoader(db_path=temp_dir / "snapshot.duckdb")
    loader.build_from_silver(_silver_from_fixtures(temp_dir), settings=mock_settings)

    spill = loader.con.execute("SELECT current_setting('temp_directory')").fetchone()[0]
    limit = loader.con.execute("SELECT current_setting('memory_limit')").fetchone()[0]
    reference = duckdb.connect()
    reference.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
    assert MEMORY_LIMIT == "2GB"  # M0b spike §4
    assert limit == reference.execute("SELECT current_setting('memory_limit')").fetchone()[0]
    assert Path(spill) == mock_settings.tmp_dir
    reference.close()
    loader.close()


def test_duplicated_match_in_silver_fails_the_build(temp_dir: Path, mock_settings: Settings):
    silver_dir = _silver_from_fixtures(temp_dir)
    matches = silver_dir / "matches.parquet"
    duplicated = pl.concat([pl.read_parquet(matches), pl.read_parquet(matches).head(1)])
    duplicated.write_parquet(matches)

    loader = DuckDBLoader(db_path=temp_dir / "snapshot.duckdb")
    with pytest.raises(duckdb.ConstraintException):
        loader.build_from_silver(silver_dir, settings=mock_settings)
    loader.close()


def test_load_matches_twice_fails_loudly(temp_dir: Path):
    match_dfs = MatchParser().parse_batch([str(FIXTURES / "sample_t20.json")])
    loader = DuckDBLoader(db_path=temp_dir / "snapshot.duckdb")
    loader.load_matches(match_dfs)
    with pytest.raises(duckdb.ConstraintException):
        loader.load_matches(match_dfs)
    loader.close()


def test_fact_tables_have_no_primary_keys_and_dimensions_keep_theirs(temp_dir: Path):
    loader = DuckDBLoader(db_path=temp_dir / "snapshot.duckdb")
    keyed = {
        row[0]
        for row in loader.con.execute("""
            SELECT table_name FROM duckdb_constraints()
            WHERE schema_name = 'gold' AND constraint_type = 'PRIMARY KEY'
        """).fetchall()
    }
    assert not {t for t in keyed if t.startswith("fact_")}
    assert {"dim_match", "dim_player", "dim_venue", "dim_team"} <= keyed
    loader.close()


def test_dim_venue_one_row_per_venue_name_with_majority_city(temp_dir: Path):
    # M0b dossier D-11: venue_id = md5(venue_name); the most frequent non-null city, ties alphabetical
    base = orjson.loads((FIXTURES / "sample_t20.json").read_bytes())
    venues = {  # match_id: (venue, city); None = the file names no city
        "m1": ("Majority Ground", "Zeta"),
        "m2": ("Majority Ground", "Zeta"),
        "m3": ("Majority Ground", "Alpha"),
        "m4": ("Tied Ground", "Beta"),
        "m5": ("Tied Ground", "Alpha"),
        "m6": ("Mostly Unnamed City Ground", None),
        "m7": ("Mostly Unnamed City Ground", None),
        "m8": ("Mostly Unnamed City Ground", "Gamma"),
        "m9": ("No City Ground", None),
    }
    parsed = []
    for match_id, (venue, city) in venues.items():
        data = copy.deepcopy(base)
        data["info"]["venue"] = venue
        data["info"].pop("city", None)
        if city is not None:
            data["info"]["city"] = city
        parsed.append(MatchParser().parse_json(match_id, data))
    match_dfs = {table: pl.concat([dfs[table] for dfs in parsed]) for table in parsed[0]}

    loader = DuckDBLoader(db_path=temp_dir / "snapshot.duckdb")
    loader.load_matches(match_dfs)  # plain INSERT: two rows for one venue_id would fail here
    rows = loader.con.execute(
        "SELECT venue_name, city, venue_id = md5(venue_name) FROM gold.dim_venue ORDER BY venue_name"
    ).fetchall()
    loader.close()

    assert rows == [
        ("Majority Ground", "Zeta", True),
        ("Mostly Unnamed City Ground", "Gamma", True),
        ("No City Ground", None, True),
        ("Tied Ground", "Alpha", True),
    ]
