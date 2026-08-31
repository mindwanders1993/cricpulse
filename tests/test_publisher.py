from pathlib import Path

import duckdb

from src.builder.loader import DuckDBLoader
from src.config import Settings
from src.parsers.match_parser import MatchParser
from src.parsers.register_parser import RegisterParser
from src.publisher.publisher import SnapshotPublisher


def test_snapshot_publisher(temp_dir: Path, mock_settings: Settings):
    # 1. Build a valid duckdb database
    raw_db = temp_dir / "raw_test.duckdb"
    loader = DuckDBLoader(db_path=raw_db)

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

    # 2. Publish snapshot
    publisher = SnapshotPublisher(settings=mock_settings)
    snap_path, latest_path = publisher.publish_snapshot(raw_db, snapshot_date="2026-08-31")

    assert snap_path.exists()
    assert latest_path.exists()
    assert snap_path.name == "cricket_2026_08_31.duckdb"
    assert latest_path.name == "cricket_latest.duckdb"

    # Verify DuckDB can query the published snapshot
    con = duckdb.connect(str(latest_path), read_only=True)
    row = con.execute("SELECT COUNT(*) FROM gold.dim_match;").fetchone()
    assert row[0] == 2
    con.close()

    # 3. Export Gold Parquets
    parquet_dir = publisher.export_gold_parquets(latest_path)
    assert parquet_dir.exists()
    assert (parquet_dir / "fact_delivery.parquet").exists()
    assert (parquet_dir / "dim_player.parquet").exists()
    assert (parquet_dir / "mart_player_batting_career.parquet").exists()
