"""The error table: every rejected match file, for a person to work through by hand (M0b dossier D-17)."""

from pathlib import Path

import polars as pl

REMOVED = "removed"  # D-17(a): same file as its manifest row; its rows left Silver
KEPT_LAST_GOOD = "kept_last_good"  # D-17(b): a new revision; the last good rows stay
NOT_LOADED = "not_loaded"  # D-17(c): a new id; never in Silver

SCHEMA = pl.Schema(
    {
        "match_id": pl.String,  # one row per match id
        "file_sha256": pl.String,  # of the rejected file's JSON bytes
        "parser_version": pl.Int32,
        "error": pl.String,
        "action": pl.String,  # REMOVED | KEPT_LAST_GOOD | NOT_LOADED
        "version": pl.String,  # the run that set action
    }
)


def quarantine_path(data_dir: Path) -> Path:
    return data_dir / "silver" / "quarantine.parquet"


def load(data_dir: Path) -> pl.DataFrame:
    path = quarantine_path(data_dir)
    if not path.exists():
        return pl.DataFrame(schema=SCHEMA)
    return pl.read_parquet(path)


def is_held(df: pl.DataFrame, match_id: str, sha: str, parser_version: int) -> bool:
    # M0b dossier D-17(d): skipped like a current manifest row (manifest.is_current)
    hit = df.filter(
        (pl.col("match_id") == match_id)
        & (pl.col("file_sha256") == sha)
        & (pl.col("parser_version") >= parser_version)
    )
    return hit.height > 0


def classify(
    manifest_df: pl.DataFrame,
    rejected: list[tuple[str, str, str]],
    parser_version: int,
    version: str,
) -> list[dict]:
    """One row per rejected (match_id, sha, error), its action set against the manifest (D-17a, b)."""
    rows = []
    for match_id, sha, error in rejected:
        loaded = manifest_df.filter(pl.col("match_id") == match_id)["file_sha256"].to_list()
        if not loaded:
            action = NOT_LOADED
        elif loaded[0] == sha:
            action = REMOVED
        else:
            action = KEPT_LAST_GOOD
        rows.append(
            {
                "match_id": match_id,
                "file_sha256": sha,
                "parser_version": parser_version,
                "error": error,
                "action": action,
                "version": version,
            }
        )
    return rows


def upsert(df: pl.DataFrame, rows: list[dict]) -> pl.DataFrame:
    """Replace the rows for these match ids and add new ones; one row per match_id."""
    # M0b.13 card: a removed match is no longer in Silver, so its row keeps `removed` and the run that
    # removed it until its file parses cleanly (never_shrinks_matches counts it once, D-17e)
    was_removed = dict(df.filter(pl.col("action") == REMOVED).select("match_id", "version").rows())
    rows = [
        {**r, "action": REMOVED, "version": was_removed[r["match_id"]]}
        if r["match_id"] in was_removed
        else r
        for r in rows
    ]
    new = pl.DataFrame(rows, schema=SCHEMA).unique("match_id", keep="last", maintain_order=True)
    kept = df.filter(~pl.col("match_id").is_in(new["match_id"].implode()))
    return pl.concat([kept, new])


def drop(df: pl.DataFrame, match_ids: list[str]) -> pl.DataFrame:
    """Drop the rows of ids whose file parsed cleanly (D-17c: a row leaves when its file parses)."""
    return df.filter(~pl.col("match_id").is_in(match_ids))


def removed_since(df: pl.DataFrame, version: str) -> int:
    """The matches removed from Silver since the run `version` (D-17e: newer than LATEST.json's)."""
    return df.filter((pl.col("action") == REMOVED) & (pl.col("version") > version)).height


def held_since(df: pl.DataFrame, version: str, read_ids: list[str]) -> int:
    """Rows newer than the run `version` whose files this run did not read again (D-17h)."""
    return df.filter((pl.col("version") > version) & ~pl.col("match_id").is_in(read_ids)).height


def save(data_dir: Path, df: pl.DataFrame) -> None:
    path = quarantine_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Invariant 1: never overwrite a published file in place — write *.tmp, then rename
    tmp = path.with_name(path.name + ".tmp")
    df.write_parquet(tmp)
    tmp.replace(path)
