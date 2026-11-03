from pathlib import Path

import polars as pl

from src.publisher import manifest


def _row(match_id: str, sha: str = "sha-a", parser_version: int = 1, version: str = "v1") -> dict:
    return {
        "match_id": match_id,
        "file_sha256": sha,
        "revision": 1,
        "parser_version": parser_version,
        "version": version,
    }


def test_load_missing_is_empty_with_schema(temp_dir: Path):
    df = manifest.load(temp_dir)
    assert df.height == 0
    assert df.schema == manifest.SCHEMA


def test_empty_manifest_nothing_is_current():
    df = pl.DataFrame(schema=manifest.SCHEMA)
    assert not manifest.is_current(df, "211824", "sha-a", 1)


def test_new_id_is_not_current():
    df = manifest.upsert(pl.DataFrame(schema=manifest.SCHEMA), [_row("211824")])
    assert not manifest.is_current(df, "999999", "sha-a", 1)


def test_same_sha_is_current():
    df = manifest.upsert(pl.DataFrame(schema=manifest.SCHEMA), [_row("211824", sha="sha-a")])
    assert manifest.is_current(df, "211824", "sha-a", 1)


def test_changed_sha_is_not_current():
    df = manifest.upsert(pl.DataFrame(schema=manifest.SCHEMA), [_row("211824", sha="sha-a")])
    assert not manifest.is_current(df, "211824", "sha-b", 1)


def test_older_parser_version_is_not_current():
    df = manifest.upsert(pl.DataFrame(schema=manifest.SCHEMA), [_row("211824", parser_version=1)])
    assert not manifest.is_current(df, "211824", "sha-a", 2)


def test_wi_prefix_is_a_different_id():
    df = manifest.upsert(pl.DataFrame(schema=manifest.SCHEMA), [_row("wi_211824")])
    assert manifest.is_current(df, "wi_211824", "sha-a", 1)
    assert not manifest.is_current(df, "211824", "sha-a", 1)


def test_upsert_replaces_and_adds():
    df = manifest.upsert(
        pl.DataFrame(schema=manifest.SCHEMA), [_row("1", sha="old"), _row("2", sha="keep")]
    )
    df = manifest.upsert(df, [_row("1", sha="new", version="v2"), _row("3", sha="added")])
    assert df.height == 3
    assert df["match_id"].n_unique() == 3
    by_id = {r["match_id"]: r for r in df.iter_rows(named=True)}
    assert by_id["1"]["file_sha256"] == "new"
    assert by_id["1"]["version"] == "v2"
    assert by_id["2"]["file_sha256"] == "keep"
    assert by_id["3"]["file_sha256"] == "added"
    assert df.schema == manifest.SCHEMA


def test_save_load_round_trip(temp_dir: Path):
    df = manifest.upsert(
        pl.DataFrame(schema=manifest.SCHEMA), [_row("1"), _row("wi_2", sha="sha-b")]
    )
    manifest.save(temp_dir, df)
    loaded = manifest.load(temp_dir)
    assert loaded.equals(df)
    assert loaded.schema == manifest.SCHEMA


def test_save_leaves_no_tmp(temp_dir: Path):
    df = manifest.upsert(pl.DataFrame(schema=manifest.SCHEMA), [_row("1")])
    manifest.save(temp_dir, df)
    manifest.save(temp_dir, manifest.upsert(df, [_row("2")]))
    assert sorted(p.name for p in (temp_dir / "silver").iterdir()) == ["manifest.parquet"]
    assert manifest.load(temp_dir).height == 2
