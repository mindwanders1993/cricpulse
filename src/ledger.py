import sqlite3
from pathlib import Path

from src.utils import setup_logging

logger = setup_logging()


class IdempotencyLedger:
    """SQLite-backed idempotency ledger for match files and player registers.

    Ensures re-running pipelines never causes duplicate data or recomputation.
    """

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.execute("PRAGMA journal_mode = WAL;")
        con.execute("PRAGMA foreign_keys = ON;")
        return con

    def _init_schema(self) -> None:
        with self._get_connection() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS match_file_audit (
                    match_id     TEXT NOT NULL,
                    file_sha256  TEXT NOT NULL,
                    revision     INTEGER NOT NULL DEFAULT 1,
                    archive_file TEXT NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'SUCCESS',
                    ingested_at  TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (match_id, file_sha256)
                );
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS register_audit (
                    source_file   TEXT NOT NULL,
                    file_sha256   TEXT NOT NULL,
                    row_count     INTEGER NOT NULL,
                    snapshot_date TEXT NOT NULL,
                    status        TEXT NOT NULL DEFAULT 'SUCCESS',
                    ingested_at   TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (source_file, file_sha256)
                );
            """)
            con.execute("""
                CREATE INDEX IF NOT EXISTS idx_match_audit_match_id 
                ON match_file_audit(match_id);
            """)

    def is_match_processed(self, match_id: str, file_sha256: str) -> bool:
        """Check if a match with the given SHA-256 has already been ingested successfully."""
        with self._get_connection() as con:
            cur = con.execute(
                """
                SELECT 1 FROM match_file_audit 
                WHERE match_id = ? AND file_sha256 = ? AND status = 'SUCCESS'
                LIMIT 1;
                """,
                (str(match_id), file_sha256),
            )
            return cur.fetchone() is not None

    def get_max_match_revision(self, match_id: str) -> int:
        """Get the highest revision number for a match_id, or 0 if never seen."""
        with self._get_connection() as con:
            cur = con.execute(
                """
                SELECT MAX(revision) FROM match_file_audit 
                WHERE match_id = ? AND status = 'SUCCESS';
                """,
                (str(match_id),),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else 0

    def record_match(
        self,
        match_id: str,
        file_sha256: str,
        revision: int,
        archive_file: str,
        status: str = "SUCCESS",
    ) -> None:
        """Record a match file ingestion event in the audit ledger."""
        with self._get_connection() as con:
            con.execute(
                """
                INSERT INTO match_file_audit (match_id, file_sha256, revision, archive_file, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(match_id, file_sha256) DO UPDATE SET
                    revision = excluded.revision,
                    archive_file = excluded.archive_file,
                    status = excluded.status,
                    ingested_at = datetime('now');
                """,
                (str(match_id), file_sha256, revision, archive_file, status),
            )

    def is_register_processed(self, source_file: str, file_sha256: str) -> bool:
        """Check if a register file with the given SHA-256 has already been ingested."""
        with self._get_connection() as con:
            cur = con.execute(
                """
                SELECT 1 FROM register_audit 
                WHERE source_file = ? AND file_sha256 = ? AND status = 'SUCCESS'
                LIMIT 1;
                """,
                (source_file, file_sha256),
            )
            return cur.fetchone() is not None

    def record_register(
        self,
        source_file: str,
        file_sha256: str,
        row_count: int,
        snapshot_date: str,
        status: str = "SUCCESS",
    ) -> None:
        """Record a register file ingestion event in the audit ledger."""
        with self._get_connection() as con:
            con.execute(
                """
                INSERT INTO register_audit (source_file, file_sha256, row_count, snapshot_date, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_file, file_sha256) DO UPDATE SET
                    row_count = excluded.row_count,
                    snapshot_date = excluded.snapshot_date,
                    status = excluded.status,
                    ingested_at = datetime('now');
                """,
                (source_file, file_sha256, row_count, snapshot_date, status),
            )

    def get_processed_match_count(self) -> int:
        """Return total unique match IDs processed successfully."""
        with self._get_connection() as con:
            cur = con.execute(
                "SELECT COUNT(DISTINCT match_id) FROM match_file_audit WHERE status = 'SUCCESS';"
            )
            row = cur.fetchone()
            return row[0] if row else 0
