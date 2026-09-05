import contextlib
import time
from typing import Annotated

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.api.auth import verify_sync_token
from src.api.schemas import SyncDailyResponse
from src.builder.loader import DuckDBLoader
from src.config import get_settings
from src.downloaders.match_downloader import MatchDownloader
from src.downloaders.register_downloader import RegisterDownloader
from src.ledger import IdempotencyLedger
from src.parsers.match_parser import MatchParser
from src.parsers.register_parser import RegisterParser
from src.publisher.publisher import SnapshotPublisher
from src.utils import compute_file_sha256, setup_logging

logger = setup_logging()
router = APIRouter(prefix="/internal", tags=["Internal Scheduled Operations"])


@router.post(
    "/sync-daily",
    response_model=SyncDailyResponse,
    dependencies=[Depends(verify_sync_token)],
)
def sync_daily(
    request: Request,
    force: Annotated[bool, Query(description="Bypass ledger deduplication")] = False,
    archive: Annotated[
        str, Query(description="Target archive name ('recently_added_2_json' or 'all_json')")
    ] = "recently_added_2_json",
    export_parquet: Annotated[bool, Query(description="Export Gold Parquet files")] = True,
) -> SyncDailyResponse:
    """Trigger incremental daily cricket delta ingestion from Cricsheet.

    Requires valid X-Sync-Token header. Executes idempotency checks, data quality gates,
    and updates the active DuckDB snapshot atomically.
    """
    start_time = time.time()
    settings = get_settings()
    ledger = IdempotencyLedger(settings.ledger_db_path)

    logger.info("internal_sync_daily_triggered", archive=archive, force=force)

    try:
        # 1. Download & Parse Registers
        reg_downloader = RegisterDownloader(settings=settings, ledger=ledger)
        people_csv, names_csv = reg_downloader.download_registers()
        reg_parser = RegisterParser()
        register_dfs = reg_parser.parse_registers(people_csv, names_csv)

        # 2. Download Matches
        match_downloader = MatchDownloader(settings=settings, ledger=ledger)
        extracted_files = match_downloader.download_and_extract(archive)

        # 3. Filter via Ledger
        files_to_process = []
        for p in extracted_files:
            match_id = p.stem.replace("wi_", "")
            file_sha = compute_file_sha256(p)
            if force or not ledger.is_match_processed(match_id, file_sha):
                files_to_process.append(p)

        if not files_to_process:
            elapsed = round(time.time() - start_time, 2)
            logger.info("internal_sync_no_new_matches", duration_seconds=elapsed)
            return SyncDailyResponse(
                status="success",
                message="No new matches to ingest. Snapshot is up-to-date.",
                matches_downloaded=len(extracted_files),
                matches_ingested=0,
                snapshot_published=str(settings.published_dir / "cricket_latest.duckdb"),
                duration_seconds=elapsed,
            )

        # 4. Parse Matches
        match_parser = MatchParser()
        match_dfs = match_parser.parse_batch(files_to_process)

        # 5. Build DuckDB Star Schema
        temp_db_path = settings.data_dir / "temp_build.duckdb"
        if temp_db_path.exists():
            temp_db_path.unlink()

        loader = DuckDBLoader(db_path=temp_db_path)
        loader.load_registers(register_dfs)
        loader.load_matches(match_dfs)
        loader.build_marts()
        loader.close()

        # 6. Publish Snapshot
        publisher = SnapshotPublisher(settings=settings)
        snap_path, latest_path = publisher.publish_snapshot(temp_db_path)

        if export_parquet:
            publisher.export_gold_parquets(snap_path)

        # 7. Record to Ledger
        for p in files_to_process:
            match_id = p.stem.replace("wi_", "")
            file_sha = compute_file_sha256(p)
            current_max_rev = ledger.get_max_match_revision(match_id)
            ledger.record_match(
                match_id=match_id,
                file_sha256=file_sha,
                revision=current_max_rev + 1,
                archive_file=archive,
                status="SUCCESS",
            )

        # 8. Reload Active In-Memory DuckDB Connection
        if hasattr(request.app.state, "db") and request.app.state.db:
            with contextlib.suppress(Exception):
                request.app.state.db.close()
            request.app.state.db = duckdb.connect(str(latest_path), read_only=True)
            logger.info("reloaded_app_db_with_new_snapshot", path=str(latest_path))

        elapsed = round(time.time() - start_time, 2)
        logger.info(
            "internal_sync_completed_successfully",
            downloaded=len(extracted_files),
            ingested=len(files_to_process),
            duration=elapsed,
        )

        return SyncDailyResponse(
            status="success",
            message=f"Successfully ingested {len(files_to_process)} matches.",
            matches_downloaded=len(extracted_files),
            matches_ingested=len(files_to_process),
            snapshot_published=str(latest_path),
            duration_seconds=elapsed,
        )

    except Exception as e:
        logger.error("internal_sync_daily_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Internal daily sync failed: {str(e)}") from e
