import zipfile
from pathlib import Path

import polars as pl
import pytest

from src.parsers.match_parser import PARSER_VERSION, MatchParser
from src.publisher import archive, manifest, quarantine
from src.utils import compute_bytes_sha256

FIXTURES = Path(__file__).parent / "fixtures"
T20 = (FIXTURES / "sample_t20.json").read_bytes()
TEST = (FIXTURES / "sample_test.json").read_bytes()
TABLES = {"matches", "innings", "deliveries", "wickets", "match_players"}


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def _empty_manifest() -> pl.DataFrame:
    return pl.DataFrame(schema=manifest.SCHEMA)


def _current(match_id: str, raw: bytes, parser_version: int = PARSER_VERSION) -> pl.DataFrame:
    row = {
        "match_id": match_id,
        "file_sha256": compute_bytes_sha256(raw),
        "revision": 1,
        "parser_version": parser_version,
        "version": "v20261101T0230Z",
    }
    return manifest.upsert(_empty_manifest(), [row])


def _parts(staging: Path, table: str) -> list[str]:
    return sorted(p.name for p in (staging / table).glob("*.parquet"))


def test_one_current_one_new_only_new_is_parsed(tmp_path: Path):
    zp = _zip(tmp_path / "a.zip", {"1001.json": T20, "1002.json": TEST})
    items = archive.iter_changed(zp, _current("1001", T20), PARSER_VERSION, reparse_all=False)
    state = archive.parse_to_staging(items, tmp_path / "_staging" / "v1")

    assert state.changed_ids == ["1002"]
    assert state.files_seen == 1
    assert state.quarantined == []
    ids = pl.read_parquet(tmp_path / "_staging" / "v1" / "matches" / "*.parquet")["match_id"]
    assert ids.to_list() == ["1002"]


def test_changed_sha_is_yielded(tmp_path: Path):
    zp = _zip(tmp_path / "a.zip", {"1001.json": T20})
    df = _current("1001", TEST)  # stored sha is of different bytes
    assert [m for m, _, _ in archive.iter_changed(zp, df, PARSER_VERSION, False)] == ["1001"]


def test_older_parser_version_is_yielded(tmp_path: Path):
    zp = _zip(tmp_path / "a.zip", {"1001.json": T20})
    df = _current("1001", T20, parser_version=PARSER_VERSION - 1)
    assert [m for m, _, _ in archive.iter_changed(zp, df, PARSER_VERSION, False)] == ["1001"]


def test_reparse_all_yields_current_members(tmp_path: Path):
    zp = _zip(tmp_path / "a.zip", {"1001.json": T20})
    items = list(archive.iter_changed(zp, _current("1001", T20), PARSER_VERSION, True))
    assert items == [("1001", compute_bytes_sha256(T20), T20)]


def test_non_json_members_and_dirs_are_ignored(tmp_path: Path):
    zp = _zip(
        tmp_path / "a.zip", {"README.txt": b"x", "1001.yaml": b"x", "d/": b"", "1001.json": T20}
    )
    assert [
        m for m, _, _ in archive.iter_changed(zp, _empty_manifest(), PARSER_VERSION, False)
    ] == ["1001"]


def test_broken_member_is_quarantined_others_parsed(tmp_path: Path):
    zp = _zip(tmp_path / "a.zip", {"1001.json": T20, "1003.json": b"{not json", "1002.json": TEST})
    items = archive.iter_changed(zp, _empty_manifest(), PARSER_VERSION, reparse_all=False)
    state = archive.parse_to_staging(items, tmp_path / "_staging" / "v1")

    assert state.changed_ids == ["1001", "1002"]
    assert [m for m, _ in state.quarantined] == ["1003"]
    assert "JSONDecodeError" in state.quarantined[0][1]
    assert state.files_seen == 3
    assert [r["match_id"] for r in state.manifest_rows] == ["1001", "1002"]


def test_batch_size_one_writes_two_parts_per_table(tmp_path: Path):
    zp = _zip(tmp_path / "a.zip", {"1001.json": T20, "1002.json": TEST})
    staging = tmp_path / "_staging" / "v1"
    items = archive.iter_changed(zp, _empty_manifest(), PARSER_VERSION, reparse_all=False)
    archive.parse_to_staging(items, staging, batch_size=1)

    assert {p.name for p in staging.iterdir()} == TABLES
    for table in TABLES:
        assert _parts(staging, table) == ["part-0.parquet", "part-1.parquet"]


def test_default_batch_size_writes_one_part_per_table(tmp_path: Path):
    zp = _zip(tmp_path / "a.zip", {"1001.json": T20, "1002.json": TEST})
    staging = tmp_path / "_staging" / "v1"
    archive.parse_to_staging(
        archive.iter_changed(zp, _empty_manifest(), PARSER_VERSION, False), staging
    )
    for table in TABLES:
        assert _parts(staging, table) == ["part-0.parquet"]


def test_wi_prefix_gives_two_different_ids(tmp_path: Path):
    zp = _zip(tmp_path / "a.zip", {"wi_211824.json": T20, "211824.json": TEST})
    items = archive.iter_changed(zp, _empty_manifest(), PARSER_VERSION, reparse_all=False)
    state = archive.parse_to_staging(items, tmp_path / "_staging" / "v1")

    assert state.changed_ids == ["wi_211824", "211824"]
    ids = pl.read_parquet(tmp_path / "_staging" / "v1" / "matches" / "*.parquet")["match_id"]
    assert sorted(ids.to_list()) == ["211824", "wi_211824"]


def test_parse_file_keeps_wi_prefix(tmp_path: Path):
    (tmp_path / "wi_211824.json").write_bytes(T20)
    (tmp_path / "211824.json").write_bytes(T20)
    parser = MatchParser()
    assert parser.parse_file(tmp_path / "wi_211824.json")["matches"]["match_id"][0] == "wi_211824"
    assert parser.parse_file(tmp_path / "211824.json")["matches"]["match_id"][0] == "211824"


def test_duplicate_id_in_zip_fails_loudly(tmp_path: Path):
    zp = _zip(tmp_path / "a.zip", {"a/1001.json": T20, "b/1001.json": TEST})
    with pytest.raises(ValueError, match="duplicate match id"):
        list(archive.iter_changed(zp, _empty_manifest(), PARSER_VERSION, reparse_all=False))


def test_manifest_rows_upsert_into_manifest(tmp_path: Path):
    zp = _zip(tmp_path / "a.zip", {"1001.json": T20})
    staging = tmp_path / "silver" / "_staging" / "v20261103T0230Z"
    state = archive.parse_to_staging(
        archive.iter_changed(zp, _empty_manifest(), PARSER_VERSION, False), staging
    )
    df = manifest.upsert(_empty_manifest(), state.manifest_rows)

    assert df.row(0, named=True) == {
        "match_id": "1001",
        "file_sha256": compute_bytes_sha256(T20),
        "revision": 2,
        "parser_version": PARSER_VERSION,
        "version": "v20261103T0230Z",
    }
    assert manifest.is_current(df, "1001", compute_bytes_sha256(T20), PARSER_VERSION)


# --- M0b dossier D-17: the error table ------------------------------------------------------


def _held(match_id: str, raw: bytes, parser_version: int = PARSER_VERSION) -> pl.DataFrame:
    row = {
        "match_id": match_id,
        "file_sha256": compute_bytes_sha256(raw),
        "parser_version": parser_version,
        "error": "JSONDecodeError: bad",
        "action": quarantine.NOT_LOADED,
        "version": "v20261101T0230Z",
    }
    return quarantine.upsert(pl.DataFrame(schema=quarantine.SCHEMA), [row])


def test_a_member_the_error_table_holds_is_skipped(tmp_path: Path):
    zp = _zip(tmp_path / "a.zip", {"1001.json": T20, "1003.json": b"{not json"})
    held = _held("1003", b"{not json")

    items = archive.iter_changed(zp, _empty_manifest(), PARSER_VERSION, False, held)

    assert [m for m, _, _ in items] == ["1001"]


def test_a_held_member_is_read_again_on_a_new_sha_a_newer_parser_or_reparse_all(tmp_path: Path):
    zp = _zip(tmp_path / "a.zip", {"1003.json": b"{not json"})

    def ids(df: pl.DataFrame, reparse_all: bool = False) -> list[str]:
        return [
            m
            for m, _, _ in archive.iter_changed(
                zp, _empty_manifest(), PARSER_VERSION, reparse_all, df
            )
        ]

    assert ids(_held("1003", b"{other bytes")) == ["1003"]
    assert ids(_held("1003", b"{not json", parser_version=PARSER_VERSION - 1)) == ["1003"]
    assert ids(_held("1003", b"{not json"), reparse_all=True) == ["1003"]


def test_the_sha_of_each_rejected_file_is_recorded(tmp_path: Path):
    zp = _zip(tmp_path / "a.zip", {"1001.json": T20, "1003.json": b"{not json"})
    items = archive.iter_changed(zp, _empty_manifest(), PARSER_VERSION, reparse_all=False)
    state = archive.parse_to_staging(items, tmp_path / "_staging" / "v1")

    assert [m for m, _ in state.quarantined] == ["1003"]  # the (match_id, error) shape is kept
    assert state.quarantined_sha256 == {"1003": compute_bytes_sha256(b"{not json")}


# --- M0b dossier D-18: the absence log and a passing failure ---------------------------------


def test_member_ids_receives_every_json_member_changed_or_not(tmp_path: Path):
    members = {"1001.json": T20, "1002.json": TEST, "1003.json": b"{not json", "README.txt": b"x"}
    zp = _zip(tmp_path / "a.zip", members)
    held = _held("1003", b"{not json")
    member_ids: set[str] = set()

    items = archive.iter_changed(zp, _current("1001", T20), PARSER_VERSION, False, held, member_ids)

    assert [m for m, _, _ in items] == ["1002"]  # 1001 is current, 1003 is held
    assert member_ids == {"1001", "1002", "1003"}  # D-18(d): every member, changed or not


@pytest.mark.parametrize("error", [MemoryError("out of memory"), OSError("disk went away")])
def test_a_memory_or_os_error_stops_the_parse_instead_of_quarantining(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
):
    def parse_json(self, match_id, data):
        raise error

    monkeypatch.setattr(MatchParser, "parse_json", parse_json)
    zp = _zip(tmp_path / "a.zip", {"1001.json": T20})
    items = archive.iter_changed(zp, _empty_manifest(), PARSER_VERSION, reparse_all=False)

    with pytest.raises(type(error), match=str(error)):
        archive.parse_to_staging(items, tmp_path / "_staging" / "v1")
