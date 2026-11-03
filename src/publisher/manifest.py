"""Silver manifest: one row per parsed match file (M0b dossier §5.3)."""

from pathlib import Path

import polars as pl

SCHEMA = pl.Schema(
    {
        "match_id": pl.String,  # file stem, wi_ kept (M0b dossier D-9); unique
        "file_sha256": pl.String,
        "revision": pl.Int32,
        "parser_version": pl.Int32,
        "version": pl.String,  # the run that parsed it
    }
)


def manifest_path(data_dir: Path) -> Path:
    return data_dir / "silver" / "manifest.parquet"


def load(data_dir: Path) -> pl.DataFrame:
    path = manifest_path(data_dir)
    if not path.exists():
        return pl.DataFrame(schema=SCHEMA)
    return pl.read_parquet(path)


def is_current(df: pl.DataFrame, match_id: str, sha: str, parser_version: int) -> bool:
    # M0b dossier §5.3: parse when the id is new, the sha changed, or the stored parser_version is older
    hit = df.filter(
        (pl.col("match_id") == match_id)
        & (pl.col("file_sha256") == sha)
        & (pl.col("parser_version") >= parser_version)
    )
    return hit.height > 0


def upsert(df: pl.DataFrame, rows: list[dict]) -> pl.DataFrame:
    """Replace the rows for these match ids and add new ones; one row per match_id."""
    new = pl.DataFrame(rows, schema=SCHEMA).unique("match_id", keep="last", maintain_order=True)
    kept = df.filter(~pl.col("match_id").is_in(new["match_id"].implode()))
    return pl.concat([kept, new])


def save(data_dir: Path, df: pl.DataFrame) -> None:
    path = manifest_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Invariant 1: never overwrite a published file in place — write *.tmp, then rename
    tmp = path.with_name(path.name + ".tmp")
    df.write_parquet(tmp)
    tmp.replace(path)
