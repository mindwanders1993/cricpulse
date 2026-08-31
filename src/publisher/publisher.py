import shutil
from pathlib import Path

import duckdb

from src.config import Settings, get_settings
from src.publisher.quality_gates import run_quality_gates
from src.utils import setup_logging

logger = setup_logging()


class SnapshotPublisher:
    """Validates and publishes the DuckDB serving snapshot and Gold Parquets."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def publish_snapshot(
        self, temp_db_path: Path | str, snapshot_date: str | None = None
    ) -> tuple[Path, Path]:
        """Validate the temporary DuckDB file with quality gates and promote it to published storage."""
        temp_db_path = Path(temp_db_path)
        date_str = snapshot_date or self.settings.snapshot_date

        logger.info("running_pre_publish_validation", path=str(temp_db_path))

        # 1. Connect and run DQ gates
        con = duckdb.connect(str(temp_db_path), read_only=True)
        try:
            run_quality_gates(con)
        finally:
            con.close()

        # 2. Promote to timestamped snapshot file
        published_dir = self.settings.published_dir
        published_dir.mkdir(parents=True, exist_ok=True)

        snapshot_filename = f"cricket_{date_str.replace('-', '_')}.duckdb"
        snapshot_path = published_dir / snapshot_filename
        latest_path = published_dir / "cricket_latest.duckdb"

        shutil.copy2(temp_db_path, snapshot_path)
        shutil.copy2(temp_db_path, latest_path)

        logger.info(
            "snapshot_published_successfully",
            snapshot=str(snapshot_path),
            latest=str(latest_path),
            size_mb=round(snapshot_path.stat().st_size / (1024 * 1024), 2),
        )

        return snapshot_path, latest_path

    def export_gold_parquets(self, db_path: Path | str) -> Path:
        """Export all Gold Star Schema tables as partitioned Parquet files."""
        parquet_dir = self.settings.parquet_dir / "gold"
        parquet_dir.mkdir(parents=True, exist_ok=True)

        con = duckdb.connect(str(db_path), read_only=True)
        try:
            tables = [
                "dim_player",
                "dim_match",
                "dim_venue",
                "dim_team",
                "fact_delivery",
                "fact_innings",
                "fact_wicket_detail",
                "fact_player_match",
                "mart_player_batting_career",
                "mart_player_bowling_career",
                "mart_player_matchup_matrix",
            ]

            for tbl in tables:
                out_path = parquet_dir / f"{tbl}.parquet"
                con.execute(f"COPY gold.{tbl} TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD);")
                logger.info("parquet_exported", table=tbl, path=str(out_path))

        finally:
            con.close()

        return parquet_dir
