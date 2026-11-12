"""Silver merge: replace re-parsed matches, keep every other row exactly as it was (M0b dossier §5.4)."""

import shutil
from pathlib import Path

import duckdb

from src.utils import setup_logging

logger = setup_logging()

TABLES = ("matches", "innings", "deliveries", "wickets", "match_players")
MEMORY_LIMIT = "2GB"  # M0b spike §4 recommendation 3: DuckDB memory_limit=2GB inside a 4 GiB job


def _q(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def merge(silver_dir: Path, staging_dir: Path) -> dict[str, int]:
    """Merge staging_dir/<table>/*.parquet into silver_dir/<table>.parquet; return rows per table."""
    for table in TABLES:
        if not any((staging_dir / table).glob("*.parquet")):
            raise FileNotFoundError(f"staging has no parts for {table!r}: {staging_dir}")
    silver_dir.mkdir(parents=True, exist_ok=True)
    staged_matches = _q(staging_dir / "matches" / "*.parquet")

    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
    # Row order in Silver carries no meaning; dropping it lets COPY stream instead of buffering
    con.execute("SET preserve_insertion_order = false")

    # M0b dossier D-9: a duplicate (or missing) match id fails loudly before anything is written.
    # A NULL id would also turn `NOT IN` below into "drop every old row".
    total, distinct, nulls = con.execute(
        f"SELECT count(*), count(DISTINCT match_id), count(*) - count(match_id) "
        f"FROM read_parquet({staged_matches})"
    ).fetchone()
    if nulls or total != distinct:
        raise ValueError(
            f"staging matches: {total} rows, {distinct} distinct ids, {nulls} null ids"
        )

    old_matches = silver_dir / "matches.parquet"
    if old_matches.exists():
        (expected_matches,) = con.execute(
            f"SELECT count(*) FROM (SELECT match_id FROM read_parquet({_q(old_matches)}) "
            f"UNION SELECT match_id FROM read_parquet({staged_matches}))"
        ).fetchone()
    else:
        expected_matches = total

    written: list[tuple[Path, Path]] = []
    try:
        for table in TABLES:
            final = silver_dir / f"{table}.parquet"
            tmp = final.with_name(final.name + ".tmp")
            staged = _q(staging_dir / table / "*.parquet")
            if final.exists():
                # M0b dossier §5.4: drop every row of a re-parsed match, then add its new rows
                source = (
                    f"SELECT * FROM read_parquet({_q(final)}) "
                    f"WHERE match_id NOT IN (SELECT match_id FROM read_parquet({staged_matches})) "
                    f"UNION ALL BY NAME SELECT * FROM read_parquet({staged})"
                )
            else:
                source = f"SELECT * FROM read_parquet({staged})"  # first run: staging only
            # Invariant 1: write *.tmp, rename later; the live file is never overwritten in place
            con.execute(f"COPY ({source}) TO {_q(tmp)} (FORMAT PARQUET, COMPRESSION ZSTD)")
            written.append((tmp, final))

        # Never shrink: the merged match set is exactly old ∪ staged, each id once (D-9)
        rows, ids = con.execute(
            f"SELECT count(*), count(DISTINCT match_id) FROM read_parquet({_q(written[0][0])})"
        ).fetchone()
        if rows != expected_matches or ids != expected_matches:
            raise ValueError(f"merged matches: {rows} rows, {ids} ids, expected {expected_matches}")
        counts = {
            final.stem: con.execute(f"SELECT count(*) FROM read_parquet({_q(tmp)})").fetchone()[0]
            for tmp, final in written
        }
    except BaseException:
        for tmp, _ in written:
            tmp.unlink(missing_ok=True)
        raise
    finally:
        con.close()

    for tmp, final in written:
        tmp.replace(final)
    # Staging goes only after every table is in place, so a crash mid-rename can be re-run
    shutil.rmtree(staging_dir)
    logger.info("silver_merged", rows=counts, matches=expected_matches)
    return counts


def remove(silver_dir: Path, match_ids: list[str]) -> dict[str, int]:
    """Drop every row of these match ids from each Silver table; return rows per table (M0b dossier D-17a)."""
    old_matches = _q(silver_dir / "matches.parquet")
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
    con.execute("SET preserve_insertion_order = false")
    written: list[tuple[Path, Path]] = []
    try:
        con.execute(
            "CREATE TEMP TABLE removed_ids AS SELECT unnest(?::VARCHAR[]) AS match_id", [match_ids]
        )
        # A re-run after a crash mid-rename finds some ids already gone, so count the ones still here
        ids_before, present = con.execute(
            f"SELECT count(DISTINCT match_id), count(DISTINCT match_id) "
            f"FILTER (WHERE match_id IN (SELECT match_id FROM removed_ids)) "
            f"FROM read_parquet({old_matches})"
        ).fetchone()
        expected_matches = ids_before - present

        for table in TABLES:
            final = silver_dir / f"{table}.parquet"
            tmp = final.with_name(final.name + ".tmp")
            source = (
                f"SELECT * FROM read_parquet({_q(final)}) "
                f"WHERE match_id NOT IN (SELECT match_id FROM removed_ids)"
            )
            # Invariant 1 and M0b dossier D-17(f): write *.tmp, rename later, as the merge does
            con.execute(f"COPY ({source}) TO {_q(tmp)} (FORMAT PARQUET, COMPRESSION ZSTD)")
            written.append((tmp, final))

        # M0b.13 card: the match count falls by exactly the removed ids, each other id once (D-9)
        rows, ids = con.execute(
            f"SELECT count(*), count(DISTINCT match_id) FROM read_parquet({_q(written[0][0])})"
        ).fetchone()
        if rows != expected_matches or ids != expected_matches:
            raise ValueError(
                f"after removal matches: {rows} rows, {ids} ids, expected {expected_matches}"
            )
        counts = {
            final.stem: con.execute(f"SELECT count(*) FROM read_parquet({_q(tmp)})").fetchone()[0]
            for tmp, final in written
        }
    except BaseException:
        for tmp, _ in written:
            tmp.unlink(missing_ok=True)
        raise
    finally:
        con.close()

    for tmp, final in written:
        tmp.replace(final)
    logger.info("silver_removed", match_ids=match_ids, rows=counts, matches=expected_matches)
    return counts
