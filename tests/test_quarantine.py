"""The error table, silver/quarantine.parquet (M0b dossier D-17c)."""

from pathlib import Path

import polars as pl

from src.publisher import manifest, quarantine


def _row(
    match_id: str,
    sha: str = "sha-a",
    action: str = quarantine.NOT_LOADED,
    version: str = "v20261102T0230Z",
    parser_version: int = 1,
    error: str = "ValueError: bad",
) -> dict:
    return {
        "match_id": match_id,
        "file_sha256": sha,
        "parser_version": parser_version,
        "error": error,
        "action": action,
        "version": version,
    }


def _table(*rows: dict) -> pl.DataFrame:
    return quarantine.upsert(pl.DataFrame(schema=quarantine.SCHEMA), list(rows))


def _manifest(match_id: str, sha: str) -> pl.DataFrame:
    row = {
        "match_id": match_id,
        "file_sha256": sha,
        "revision": 1,
        "parser_version": 1,
        "version": "v20261101T0230Z",
    }
    return manifest.upsert(pl.DataFrame(schema=manifest.SCHEMA), [row])


def _by_id(df: pl.DataFrame) -> dict[str, dict]:
    return {r["match_id"]: r for r in df.iter_rows(named=True)}


# --- load and save --------------------------------------------------------------------------


def test_load_missing_is_empty_with_schema(temp_dir: Path):
    df = quarantine.load(temp_dir)
    assert df.height == 0
    assert df.schema == quarantine.SCHEMA


def test_save_load_round_trip_leaves_no_tmp(temp_dir: Path):
    df = _table(_row("1001"), _row("wi_2", sha="sha-b", action=quarantine.REMOVED))
    quarantine.save(temp_dir, df)
    quarantine.save(temp_dir, quarantine.upsert(df, [_row("1003")]))

    loaded = quarantine.load(temp_dir)
    assert loaded.equals(quarantine.upsert(df, [_row("1003")]))
    assert loaded.schema == quarantine.SCHEMA
    assert sorted(p.name for p in (temp_dir / "silver").iterdir()) == ["quarantine.parquet"]


# --- upsert and drop ------------------------------------------------------------------------


def test_upsert_replaces_and_adds_one_row_per_id():
    df = _table(_row("1", sha="old"), _row("2", sha="keep"))
    df = quarantine.upsert(df, [_row("1", sha="new", version="v3"), _row("3", sha="added")])

    assert df["match_id"].n_unique() == df.height == 3
    by_id = _by_id(df)
    assert (by_id["1"]["file_sha256"], by_id["1"]["version"]) == ("new", "v3")
    assert by_id["2"]["file_sha256"] == "keep"
    assert by_id["3"]["file_sha256"] == "added"
    assert df.schema == quarantine.SCHEMA


def test_a_removed_row_keeps_its_action_and_version_until_its_file_parses():
    df = _table(_row("1001", sha="sha-a", action=quarantine.REMOVED, version="v2"))

    # A later revision is rejected too: it is no longer in Silver, so it stays removed, from run v2
    df = quarantine.upsert(
        df, [_row("1001", sha="sha-b", action=quarantine.NOT_LOADED, version="v5")]
    )

    row = _by_id(df)["1001"]
    assert (row["file_sha256"], row["action"], row["version"]) == (
        "sha-b",
        quarantine.REMOVED,
        "v2",
    )
    assert quarantine.drop(df, ["1001"]).height == 0


def test_a_kept_last_good_row_takes_the_new_action_and_run():
    df = _table(_row("1001", action=quarantine.KEPT_LAST_GOOD, version="v2"))
    df = quarantine.upsert(df, [_row("1001", action=quarantine.REMOVED, version="v4")])

    assert (_by_id(df)["1001"]["action"], _by_id(df)["1001"]["version"]) == (
        quarantine.REMOVED,
        "v4",
    )


def test_drop_removes_only_the_ids_that_parsed_cleanly():
    df = _table(_row("1"), _row("2"), _row("3"))
    assert sorted(quarantine.drop(df, ["1", "3", "9"])["match_id"]) == ["2"]
    assert quarantine.drop(df, []).equals(df)


# --- is_held: D-17(d) -----------------------------------------------------------------------


def test_is_held_on_the_same_id_sha_and_parser_version():
    df = _table(_row("1001", sha="sha-a", parser_version=1))

    assert quarantine.is_held(df, "1001", "sha-a", 1)
    assert not quarantine.is_held(df, "1001", "sha-b", 1)  # a new revision is read again
    assert not quarantine.is_held(df, "1001", "sha-a", 2)  # a newer parser reads it again
    assert not quarantine.is_held(df, "1002", "sha-a", 1)
    assert not quarantine.is_held(pl.DataFrame(schema=quarantine.SCHEMA), "1001", "sha-a", 1)


# --- classify: D-17(a), (b), (c) ------------------------------------------------------------


def test_classify_against_the_manifest():
    rows = quarantine.classify(
        _manifest("1001", "sha-a"),
        [("1001", "sha-a", "E1"), ("1001x", "sha-a", "E2")],
        2,
        "v20261103T0230Z",
    )
    assert rows == [
        _row(
            "1001",
            action=quarantine.REMOVED,
            version="v20261103T0230Z",
            parser_version=2,
            error="E1",
        ),
        _row(
            "1001x",
            action=quarantine.NOT_LOADED,
            version="v20261103T0230Z",
            parser_version=2,
            error="E2",
        ),
    ]
    other = quarantine.classify(_manifest("1001", "sha-a"), [("1001", "sha-b", "E")], 1, "v3")
    assert other[0]["action"] == quarantine.KEPT_LAST_GOOD


# --- removed_since: D-17(e) -----------------------------------------------------------------


def test_removed_since_counts_removed_rows_newer_than_the_live_version():
    df = _table(
        _row("1", action=quarantine.REMOVED, version="v20261101T0230Z"),  # already published
        _row("2", action=quarantine.REMOVED, version="v20261102T0230Z"),
        _row("3", action=quarantine.REMOVED, version="v20261103T0230Z"),
        _row("4", action=quarantine.KEPT_LAST_GOOD, version="v20261103T0230Z"),
        _row("5", action=quarantine.NOT_LOADED, version="v20261103T0230Z"),
    )
    assert quarantine.removed_since(df, "v20261101T0230Z") == 2
    assert quarantine.removed_since(df, "v20261103T0230Z") == 0


# --- held_since: D-17(h) --------------------------------------------------------------------


def test_held_since_counts_rows_newer_than_the_live_version_the_run_did_not_read():
    df = _table(
        _row("1", version="v20261101T0230Z"),  # already published
        _row("2", version="v20261102T0230Z"),
        _row("3", action=quarantine.REMOVED, version="v20261102T0230Z"),
        _row("4", version="v20261103T0230Z"),  # read again by this run: its own count has it
    )
    assert quarantine.held_since(df, "v20261101T0230Z", ["4"]) == 2
    assert quarantine.held_since(df, "v20261101T0230Z", []) == 3
    assert quarantine.held_since(df, "v20261103T0230Z", []) == 0
