from pathlib import Path

import httpx

from src.config import Settings, get_settings
from src.ledger import IdempotencyLedger
from src.utils import compute_file_sha256, setup_logging

logger = setup_logging()


class RegisterDownloader:
    """Downloads Cricsheet player registers (`people.csv` and `names.csv`)."""

    def __init__(self, settings: Settings | None = None, ledger: IdempotencyLedger | None = None):
        self.settings = settings or get_settings()
        self.ledger = ledger or IdempotencyLedger(self.settings.ledger_db_path)
        self.base_url = self.settings.cricsheet_base_url.rstrip("/")

    def download_file(self, filename: str) -> Path:
        """Download a single register CSV file."""
        url = f"{self.base_url}/register/{filename}"
        dest_dir = self.settings.raw_register_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        logger.info("downloading_register_file", url=url, dest=str(dest_path))

        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            with open(dest_path, "wb") as f:
                f.write(response.content)

        file_sha256 = compute_file_sha256(dest_path)
        logger.info(
            "register_file_downloaded",
            filename=filename,
            sha256=file_sha256,
            size_bytes=dest_path.stat().st_size,
        )
        return dest_path

    def download_registers(self) -> tuple[Path, Path]:
        """Download both people.csv and names.csv."""
        people_csv = self.download_file("people.csv")
        names_csv = self.download_file("names.csv")
        return people_csv, names_csv
