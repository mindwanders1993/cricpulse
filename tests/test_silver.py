import zipfile
from pathlib import Path

import orjson
import polars as pl
import pytest

from src.parsers.match_parser import PARSER_VERSION
from src.publisher import archive, manifest, silver

FIXTURES = Path(__file__).parent / "fixtures"
T20 = (FIXTURES / "sample_t20.json").read_bytes()
TEST = (FIXTURES / "sample_test.json").read_bytes()


def _stage(root: Path, version: str, members: dict[str, bytes], batch_size: int = 1000) -> Path:
    """Build a staging dir the way the pipeline does: zip → iter_changed → parse_to_staging."""
    zp = root / f"{version}.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    staging = root / "silver" / "_staging" / version
    items = archive.iter_changed(zp, pl.DataFrame(schema=manifest.SCHEMA), PARSER_VERSION, True)
    state = archive.parse_to_staging(items, staging, batch_size=batch_size)
    assert state.quarantined == []
    return staging


def _read(silver_dir: Path, table: str) -> pl.DataFrame:
    return pl.read_parquet(silver_dir / f"{table}.parquet")


def _row_hashes(df: pl.DataFrame) -> list[int]:
    return sorted(df.select(sorted(df.columns)).hash_rows().to_list())


def _first_run(tmp_path: Path) -> Path:
    silver_dir = tmp_path / "silver"
    silver.merge(silver_dir, _stage(tmp_path, "v1", {"1001.json": T20, "1002.json": TEST}))
    return silver_dir


def _test_with_first_innings_only() -> bytes:
    data = orjson.loads(TEST)
    data["innings"] = data["innings"][:1]
    data["meta"]["revision"] += 1
    return orjson.dumps(data)


def test_first_run_is_staging_only(tmp_path: Path):
    silver_dir = tmp_path / "silver"
    staging = _stage(tmp_path, "v1", {"1001.json": T20, "1002.json": TEST}, batch_size=1)
    staged = {t: pl.read_parquet(staging / t / "*.parquet") for t in silver.TABLES}

    counts = silver.merge(silver_dir, staging)

    assert counts == {t: staged[t].height for t in silver.TABLES}
    for table in silver.TABLES:
        assert _row_hashes(_read(silver_dir, table)) == _row_hashes(staged[table])
    assert sorted(_read(silver_dir, "matches")["match_id"]) == ["1001", "1002"]
    # M0b dossier D-18(b): the merge leaves staging; test_pipeline checks the run deletes it after
    # the manifest is saved
    assert staging.exists()
    assert not list(silver_dir.glob("*.tmp"))


def test_reparsed_match_loses_its_dropped_innings(tmp_path: Path):
    silver_dir = _first_run(tmp_path)
    assert _read(silver_dir, "innings").filter(pl.col("match_id") == "1002").height == 3

    counts = silver.merge(
        silver_dir, _stage(tmp_path, "v2", {"1002.json": _test_with_first_innings_only()})
    )

    for table in ("innings", "deliveries", "wickets"):
        rows = _read(silver_dir, table).filter(pl.col("match_id") == "1002")
        assert set(rows["innings_number"]) == {1}, table
    assert sorted(_read(silver_dir, "matches")["match_id"]) == ["1001", "1002"]
    assert counts["matches"] == 2


def test_untouched_matches_rows_are_identical(tmp_path: Path):
    silver_dir = _first_run(tmp_path)
    before = {
        t: _row_hashes(_read(silver_dir, t).filter(pl.col("match_id") == "1001"))
        for t in silver.TABLES
    }

    silver.merge(silver_dir, _stage(tmp_path, "v2", {"1002.json": _test_with_first_innings_only()}))

    for table in silver.TABLES:
        after = _read(silver_dir, table).filter(pl.col("match_id") == "1001")
        assert _row_hashes(after) == before[table], table


def test_match_absent_from_staging_is_never_dropped(tmp_path: Path):
    silver_dir = _first_run(tmp_path)
    counts = silver.merge(silver_dir, _stage(tmp_path, "v2", {"1003.json": T20}))

    assert sorted(_read(silver_dir, "matches")["match_id"]) == ["1001", "1002", "1003"]
    assert counts["matches"] == 3


def test_exception_between_write_and_rename_leaves_silver_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    silver_dir = _first_run(tmp_path)
    before = {t: (silver_dir / f"{t}.parquet").read_bytes() for t in silver.TABLES}
    staging = _stage(tmp_path, "v2", {"1002.json": _test_with_first_innings_only()})

    def fail_rename(self, target):
        raise OSError("disk went away")

    monkeypatch.setattr(Path, "replace", fail_rename)
    with pytest.raises(OSError, match="disk went away"):
        silver.merge(silver_dir, staging)
    monkeypatch.undo()

    for table in silver.TABLES:
        assert (silver_dir / f"{table}.parquet").read_bytes() == before[table], table
    assert _read(silver_dir, "innings").filter(pl.col("match_id") == "1002").height == 3
    assert staging.exists()

    # Staging was kept, so the same merge can be re-run and completes
    silver.merge(silver_dir, staging)
    assert set(
        _read(silver_dir, "innings").filter(pl.col("match_id") == "1002")["innings_number"]
    ) == {1}


def test_duplicate_staged_match_id_fails_loudly_and_writes_nothing(tmp_path: Path):
    silver_dir = _first_run(tmp_path)
    before = {t: (silver_dir / f"{t}.parquet").read_bytes() for t in silver.TABLES}
    # The same match staged twice, e.g. two runs' staging dirs mixed together (M0b dossier D-9)
    staging = _stage(tmp_path, "v2", {"1001.json": T20})
    extra = _stage(tmp_path, "v3", {"1001.json": T20})
    for table in silver.TABLES:
        (extra / table / "part-0.parquet").rename(staging / table / "part-1.parquet")

    with pytest.raises(ValueError, match="distinct ids"):
        silver.merge(silver_dir, staging)

    for table in silver.TABLES:
        assert (silver_dir / f"{table}.parquet").read_bytes() == before[table], table
    assert not list(silver_dir.glob("*.tmp"))
    assert staging.exists()


def test_duplicate_already_in_silver_fails_loudly_before_rename(tmp_path: Path):
    silver_dir = _first_run(tmp_path)
    matches = _read(silver_dir, "matches")
    pl.concat([matches, matches.filter(pl.col("match_id") == "1001")]).write_parquet(
        silver_dir / "matches.parquet"
    )
    before = {t: (silver_dir / f"{t}.parquet").read_bytes() for t in silver.TABLES}

    with pytest.raises(ValueError, match="merged matches"):
        silver.merge(silver_dir, _stage(tmp_path, "v2", {"1003.json": T20}))

    for table in silver.TABLES:
        assert (silver_dir / f"{table}.parquet").read_bytes() == before[table], table
    assert not list(silver_dir.glob("*.tmp"))


def test_staging_without_a_table_is_refused(tmp_path: Path):
    staging = _stage(tmp_path, "v1", {"1001.json": T20})
    for part in (staging / "wickets").iterdir():
        part.unlink()
    with pytest.raises(FileNotFoundError, match="wickets"):
        silver.merge(tmp_path / "silver", staging)
    assert not (tmp_path / "silver" / "matches.parquet").exists()


# --- M0b dossier D-17(a), (f): removing a match a newer parser rejects ----------------------


def test_remove_drops_the_ids_from_every_table_with_nothing_staged(tmp_path: Path):
    silver_dir = _first_run(tmp_path)
    kept = {
        t: _row_hashes(_read(silver_dir, t).filter(pl.col("match_id") == "1002"))
        for t in silver.TABLES
    }

    counts = silver.remove(silver_dir, ["1001"])

    for table in silver.TABLES:
        df = _read(silver_dir, table)
        assert "1001" not in df["match_id"].to_list(), table
        assert _row_hashes(df) == kept[table], table  # every other row exactly as it was
        assert counts[table] == df.height
    assert counts["matches"] == 1
    assert not list(silver_dir.glob("*.tmp"))


def test_remove_rerun_after_a_crash_mid_rename_finishes_the_rest(tmp_path: Path):
    silver_dir = _first_run(tmp_path)
    # The crashed removal renamed matches only; every other table still holds 1001
    matches = _read(silver_dir, "matches")
    matches.filter(pl.col("match_id") != "1001").write_parquet(silver_dir / "matches.parquet")

    counts = silver.remove(silver_dir, ["1001"])

    for table in silver.TABLES:
        assert "1001" not in _read(silver_dir, table)["match_id"].to_list(), table
    assert counts["matches"] == 1


def test_exception_between_remove_write_and_rename_leaves_silver_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    silver_dir = _first_run(tmp_path)
    before = {t: (silver_dir / f"{t}.parquet").read_bytes() for t in silver.TABLES}

    def fail_rename(self, target):
        raise OSError("disk went away")

    monkeypatch.setattr(Path, "replace", fail_rename)
    with pytest.raises(OSError, match="disk went away"):
        silver.remove(silver_dir, ["1001"])
    monkeypatch.undo()

    for table in silver.TABLES:
        assert (silver_dir / f"{table}.parquet").read_bytes() == before[table], table


def test_remove_fails_loudly_when_the_count_does_not_fall_by_the_ids(tmp_path: Path):
    silver_dir = _first_run(tmp_path)
    matches = _read(silver_dir, "matches")
    pl.concat([matches, matches.filter(pl.col("match_id") == "1002")]).write_parquet(
        silver_dir / "matches.parquet"
    )
    before = {t: (silver_dir / f"{t}.parquet").read_bytes() for t in silver.TABLES}

    with pytest.raises(ValueError, match="after removal matches"):
        silver.remove(silver_dir, ["1001"])

    for table in silver.TABLES:
        assert (silver_dir / f"{table}.parquet").read_bytes() == before[table], table
    assert not list(silver_dir.glob("*.tmp"))
