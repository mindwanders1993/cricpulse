import datetime as dt
import shutil
from pathlib import Path

import duckdb

from src.config import Settings, get_settings
from src.parsers.match_parser import PARSER_VERSION
from src.publisher.quality_gates import run_quality_gates
from src.snapshot import LatestInfo, latest_path, read_latest, write_latest
from src.utils import compute_file_sha256, setup_logging

logger = setup_logging()


class SnapshotPublisher:
    """Publishes versioned DuckDB snapshots under snapshots/, names the live one in LATEST.json, prunes."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def publish(self, temp_db: Path | str, version: str) -> LatestInfo:
        """Copy temp_db to snapshots/cricket_<version>.duckdb, then point LATEST.json at it.

        Runs no quality gates: the run calls run_quality_gates first (M0b dossier §5.1 steps 9-10).
        """
        data_dir = self.settings.data_dir
        snapshots_dir = self.settings.snapshots_dir
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        target = snapshots_dir / f"cricket_{version}.duckdb"
        if target.exists():
            # Invariant 1: a published snapshot is never overwritten; D-8 gives each run its own version
            raise FileExistsError(f"snapshot already published: {target}")

        # M0b dossier §5.7: write *.tmp, then rename
        tmp = target.with_name(target.name + ".tmp")
        shutil.copy2(temp_db, tmp)
        tmp.rename(target)

        sha256 = compute_file_sha256(target)
        con = duckdb.connect(str(target), read_only=True)
        try:
            # Raw COUNT(*), the same quantities the never-shrinks gates compare (M0b dossier §5.6)
            match_count = con.execute("SELECT COUNT(*) FROM gold.dim_match").fetchone()[0]
            delivery_count = con.execute("SELECT COUNT(*) FROM gold.fact_delivery").fetchone()[0]
            data_cutoff = con.execute("SELECT MAX(match_date) FROM gold.dim_match").fetchone()[0]
        finally:
            con.close()

        info = LatestInfo(
            version=version,
            path=target.relative_to(data_dir).as_posix(),
            sha256=sha256,
            match_count=match_count,
            delivery_count=delivery_count,
            data_cutoff=data_cutoff,
            parser_version=PARSER_VERSION,
            created_at=dt.datetime.now(dt.UTC),
        )
        write_latest(data_dir, info)
        logger.info(
            "snapshot_published",
            version=version,
            path=info.path,
            match_count=match_count,
            delivery_count=delivery_count,
        )
        return info

    def prune(self, today: dt.date | None = None) -> list[Path]:
        """Delete snapshots beyond the newest keep_snapshots and raw zips older than keep_raw_days."""
        deleted: list[Path] = []

        # M0b dossier D-7: keep the newest snapshots by version name (D-8 names sort by time)
        snapshots = sorted(
            self.settings.snapshots_dir.glob("cricket_*.duckdb"), key=lambda p: p.name, reverse=True
        )
        info = read_latest(self.settings.data_dir)
        # M0b dossier §5.7: never the one LATEST.json names
        live_name = Path(info.path).name if info else None
        for snap in snapshots[self.settings.keep_snapshots :]:
            if snap.name != live_name:
                snap.unlink()
                deleted.append(snap)

        # M0b dossier D-7: raw zips live in bronze/cricsheet/<YYYY-MM-DD>/ (§5.2)
        today = today or dt.datetime.now(dt.UTC).date()
        for zip_path in sorted(self.settings.bronze_dir.glob("cricsheet/*/*.zip")):
            day_dir = zip_path.parent
            if (today - dt.date.fromisoformat(day_dir.name)).days > self.settings.keep_raw_days:
                zip_path.unlink()
                deleted.append(zip_path)
                if not any(day_dir.iterdir()):
                    day_dir.rmdir()

        logger.info("pruned", deleted=[str(p) for p in deleted])
        return deleted

    def publish_snapshot(
        self, temp_db_path: Path | str, version: str | None = None
    ) -> tuple[Path, Path]:
        """Gate the temporary DuckDB file, then publish it. Kept while main.py calls it (M0b.8)."""
        temp_db_path = Path(temp_db_path)
        version = version or dt.datetime.now(dt.UTC).strftime("v%Y%m%dT%H%MZ")  # M0b dossier D-8

        logger.info("running_pre_publish_validation", path=str(temp_db_path))
        con = duckdb.connect(str(temp_db_path), read_only=True)
        try:
            # Invariant 1: every gate, never-shrinks included, before LATEST.json is written
            run_quality_gates(con, previous=read_latest(self.settings.data_dir))
        finally:
            con.close()

        info = self.publish(temp_db_path, version)
        return self.settings.data_dir / info.path, latest_path(self.settings.data_dir)
