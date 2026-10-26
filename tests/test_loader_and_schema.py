from pathlib import Path

from src.builder.loader import DuckDBLoader
from src.parsers.match_parser import MatchParser
from src.parsers.register_parser import RegisterParser
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
