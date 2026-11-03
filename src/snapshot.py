"""The `LATEST.json` model: which published snapshot is live (M0b dossier §5.7)."""

from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel

LATEST_NAME = "LATEST.json"


class LatestInfo(BaseModel):
    version: str
    path: str  # relative to data_dir, e.g. snapshots/cricket_v20261026T0230Z.duckdb
    sha256: str
    match_count: int
    delivery_count: int
    data_cutoff: date
    parser_version: int
    created_at: datetime


def latest_path(data_dir: Path) -> Path:
    # M0b dossier §5.2: LATEST.json lives beside the snapshots it names
    return data_dir / "snapshots" / LATEST_NAME


def read_latest(data_dir: Path) -> LatestInfo | None:
    path = latest_path(data_dir)
    if not path.exists():
        return None
    return LatestInfo.model_validate_json(path.read_bytes())


def write_latest(data_dir: Path, info: LatestInfo) -> None:
    path = latest_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Invariant 1: never overwrite a published file in place — write *.tmp, then rename
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(info.model_dump_json(indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
