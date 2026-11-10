import datetime as dt
from pathlib import Path

import httpx

from src.config import Settings, get_settings
from src.utils import compute_file_sha256, setup_logging

logger = setup_logging()


class MatchDownloader:
    """Downloads Cricsheet match JSON archives."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.cricsheet_base_url.rstrip("/")

    def download_to_bronze(self, archive_name: str, date: dt.date) -> Path:
        """Download a match archive to bronze/cricsheet/<date>/<archive>.zip (M0b dossier §5.2)."""
        if not archive_name.endswith("_json") and not archive_name.endswith(".zip"):
            archive_name = f"{archive_name}_json"
        filename = f"{archive_name}.zip" if not archive_name.endswith(".zip") else archive_name
        url = f"{self.base_url}/downloads/{filename}"

        dest_dir = self.settings.bronze_dir / "cricsheet" / date.isoformat()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        logger.info("downloading_match_archive", url=url, dest=str(dest_path))
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            dest_path.write_bytes(response.content)

        logger.info(
            "match_archive_downloaded",
            path=str(dest_path),
            sha256=compute_file_sha256(dest_path),
            size_bytes=dest_path.stat().st_size,
        )
        return dest_path
