import zipfile
from pathlib import Path

import httpx

from src.config import Settings, get_settings
from src.ledger import IdempotencyLedger
from src.utils import compute_file_sha256, setup_logging

logger = setup_logging()


class MatchDownloader:
    """Downloads and extracts Cricsheet match JSON archives."""

    def __init__(self, settings: Settings | None = None, ledger: IdempotencyLedger | None = None):
        self.settings = settings or get_settings()
        self.ledger = ledger or IdempotencyLedger(self.settings.ledger_db_path)
        self.base_url = self.settings.cricsheet_base_url.rstrip("/")

    def download_archive(self, archive_name: str = "recently_added_2_json") -> Path:
        """Download match archive ZIP if not already downloaded or if force is enabled."""
        if not archive_name.endswith("_json") and not archive_name.endswith(".zip"):
            archive_name = f"{archive_name}_json"

        filename = f"{archive_name}.zip" if not archive_name.endswith(".zip") else archive_name
        url = f"{self.base_url}/downloads/{filename}"

        dest_dir = self.settings.raw_dir / "zips"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        logger.info("downloading_match_archive", url=url, dest=str(dest_path))

        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            with open(dest_path, "wb") as f:
                f.write(response.content)

        file_sha256 = compute_file_sha256(dest_path)
        logger.info(
            "match_archive_downloaded",
            path=str(dest_path),
            sha256=file_sha256,
            size_bytes=dest_path.stat().st_size,
        )
        return dest_path

    def extract_archive(self, zip_path: Path, output_dir: Path | None = None) -> list[Path]:
        """Extract only `.json` files from the archive, skipping `.yaml` and non-JSON files."""
        target_dir = output_dir or self.settings.raw_match_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        extracted_files: list[Path] = []
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                # Strictly process .json files and ignore README, .yaml, or folder entries
                if member.filename.endswith(".json") and not member.is_dir():
                    filename = Path(member.filename).name
                    extracted_path = target_dir / filename
                    with zf.open(member) as source, open(extracted_path, "wb") as target:
                        target.write(source.read())
                    extracted_files.append(extracted_path)

        logger.info(
            "match_archive_extracted", count=len(extracted_files), target_dir=str(target_dir)
        )
        return extracted_files

    def download_and_extract(self, archive_name: str = "recently_added_2_json") -> list[Path]:
        """Download and extract match files in a single step."""
        zip_path = self.download_archive(archive_name)
        return self.extract_archive(zip_path)
