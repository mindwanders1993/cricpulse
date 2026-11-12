"""Archive reader: stream a Cricsheet zip, diff against the manifest, parse, quarantine (M0b dossier §5.1 step 4)."""

import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import orjson
import polars as pl

from src.parsers.match_parser import PARSER_VERSION, MatchParser
from src.publisher import manifest, quarantine
from src.utils import compute_bytes_sha256, setup_logging

logger = setup_logging()


@dataclass
class RunState:
    changed_ids: list[str] = field(default_factory=list)
    manifest_rows: list[dict] = field(default_factory=list)  # shape of manifest.SCHEMA, for upsert
    quarantined: list[tuple[str, str]] = field(default_factory=list)  # (match_id, error)
    # M0b dossier D-17(c): the error table holds each rejected file by its sha
    quarantined_sha256: dict[str, str] = field(default_factory=dict)  # match_id → sha256
    files_seen: int = 0  # items handed to parse_to_staging


def iter_changed(
    zip_path: Path,
    manifest_df: pl.DataFrame,
    parser_version: int,
    reparse_all: bool,
    quarantine_df: pl.DataFrame | None = None,
) -> Iterator[tuple[str, str, bytes]]:
    """Yield (match_id, sha256, raw_bytes) for .json members that are new or changed; no extraction.

    A member the error table `quarantine_df` holds is skipped, unless `reparse_all` (M0b dossier D-17d).
    """
    seen: set[str] = set()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            if member.is_dir() or not member.filename.endswith(".json"):
                continue
            match_id = Path(member.filename).stem  # M0b dossier D-9: file stem, wi_ prefix kept
            if match_id in seen:
                # M0b dossier D-9: a duplicate id fails loudly instead of losing a match
                raise ValueError(f"duplicate match id {match_id!r} in {zip_path.name}")
            seen.add(match_id)
            raw = zf.read(member)
            sha = compute_bytes_sha256(raw)
            if not reparse_all and manifest.is_current(manifest_df, match_id, sha, parser_version):
                continue
            if (
                not reparse_all
                and quarantine_df is not None
                and quarantine.is_held(quarantine_df, match_id, sha, parser_version)
            ):
                continue
            yield match_id, sha, raw


def parse_to_staging(
    items: Iterable[tuple[str, str, bytes]], staging_dir: Path, batch_size: int = 1000
) -> RunState:
    """Parse items into staging_dir/<table>/part-<n>.parquet, one part per table every batch_size matches."""
    # M0b dossier §5.2: staging lives at silver/_staging/<version>/, so its name is the run version
    version = staging_dir.name
    parser = MatchParser()
    state = RunState()
    batch: list[dict[str, pl.DataFrame]] = []
    part = 0

    def flush() -> None:
        nonlocal part
        for table in batch[0]:
            table_dir = staging_dir / table
            table_dir.mkdir(parents=True, exist_ok=True)
            pl.concat([dfs[table] for dfs in batch]).write_parquet(
                table_dir / f"part-{part}.parquet"
            )
        part += 1
        batch.clear()

    for match_id, sha, raw in items:
        state.files_seen += 1
        try:
            data = orjson.loads(raw)
            dfs = parser.parse_json(match_id, data)
            revision = data.get("meta", {}).get("revision")
        except Exception as exc:  # M0b dossier D-5: quarantine the file and continue
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("match_quarantined", match_id=match_id, error=error)
            state.quarantined.append((match_id, error))
            state.quarantined_sha256[match_id] = sha
            continue
        batch.append(dfs)
        state.changed_ids.append(match_id)
        state.manifest_rows.append(
            {
                "match_id": match_id,
                "file_sha256": sha,
                "revision": revision,
                "parser_version": PARSER_VERSION,
                "version": version,
            }
        )
        if len(batch) >= batch_size:
            flush()
    if batch:
        flush()
    return state
