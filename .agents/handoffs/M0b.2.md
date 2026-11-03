# Handoff: M0b.2 (A)
- Branch / worktree: `feat/M0b-trustworthy-data-pipeline` · main checkout `/Users/mrrobot/Desktop/Projects/cricpulse`
- State: done
- What changed:
  - `src/config.py` — new settings `tmp_dir` (unset → `<data_dir>/tmp`), `snapshot_path` (`""`), `nightly_archive` (`recently_added_7_json`), `keep_snapshots` (7), `keep_raw_days` (30); properties `bronze_dir`, `silver_dir`, `snapshots_dir`, `runs_dir`; `ensure_directories` also creates `bronze/`, `silver/`, `snapshots/`, `runs/` and `tmp_dir`. No old setting removed (that's M0b.8).
  - `src/snapshot.py` (new) — `LatestInfo` (the 8 fields in §5.7), `latest_path`, `read_latest` (missing file → `None`), `write_latest` (writes `LATEST.json.tmp`, then renames it). The file lives at `<data_dir>/snapshots/LATEST.json`.
  - `src/publisher/manifest.py` (new) — `SCHEMA` (§5.3), `manifest_path` (`<data_dir>/silver/manifest.parquet`), `load`, `is_current`, `upsert`, `save` (writes `.tmp`, then renames it).
  - `tests/test_snapshot.py` (new, 6 tests), `tests/test_manifest.py` (new, 10 tests), `tests/test_config.py` (3 tests added; the existing 3 are unchanged).
- Verification run:
  - `python -m pytest tests/test_snapshot.py tests/test_manifest.py tests/test_config.py -q` → **22 passed**, exit 0
  - `python -m pytest -q` → **61 passed** (42 before the change + 19 new), 1 warning that was already there (Starlette `httpx` deprecation), exit 0
  - `ruff check src tests && ruff format --check src tests` → clean, exit 0
- Done-when lines met (subtasks):
  1. Settings §5.9 + new directories → `src/config.py`; `test_config.py::test_settings_m0b_defaults`, `::test_settings_tmp_dir_override`, `::test_settings_m0b_directories`. Old settings kept: `::test_settings_default_directories` still passes unchanged.
  2. `LatestInfo` / `read_latest` / `write_latest` → `src/snapshot.py`; `test_snapshot.py::test_write_then_read_round_trip`, `::test_latest_json_has_dossier_fields`, `::test_latest_lives_under_snapshots`, `::test_write_latest_replaces_previous`.
  3. `load` / `is_current` / `upsert` / `save` → `src/publisher/manifest.py`; `test_manifest.py::test_upsert_replaces_and_adds` and the tests named in 4.
  4. The tests the card asks for:
     - empty manifest → `test_load_missing_is_empty_with_schema`, `test_empty_manifest_nothing_is_current`
     - new id → `test_new_id_is_not_current`
     - same sha → `test_same_sha_is_current`
     - changed sha → `test_changed_sha_is_not_current`
     - older parser version → `test_older_parser_version_is_not_current`
     - save/load round trip → `test_save_load_round_trip` (plus `test_save_leaves_no_tmp`)
     - `write_latest` leaves no `.tmp` behind → `test_write_latest_leaves_no_tmp`
     - `read_latest` on a missing file returns `None` → `test_read_latest_missing_returns_none`
     - extra: `wi_` id is distinct (D-9) → `test_wi_prefix_is_a_different_id`
- Open issues / decisions needed:
  - `tmp_dir`: §5.9 gives the default as `data/tmp`. I made it `None`, which means `<data_dir>/tmp`, so it follows `data_dir`. The default comes out the same (`data/tmp`), and tests that point `data_dir` at a temp directory never create `./data/tmp`. Set `TMP_DIR=/tmp/cricpulse` in the cloud (M0b.10).
  - `snapshot_path` is a `str` (empty means unset), not a `Path`. An empty env value would otherwise parse as `Path(".")`. M0b.9's resolver should treat `""` as unset.
  - `upsert(df, rows)` takes `rows: list[dict]` with the 5 manifest columns. M0b.3's `RunState.manifest_rows` should use that shape.
  - `is_current` filters the frame on each call. That is fine at about 23k rows. If M0b.3 profiling shows it is slow, it can build a dict over the frame once.
  - D-9 is still "Proposed" in dossier §4. Rule it before M0b.3.
  - `.agents/handoffs/M0b.2-blocked-1.md` (the earlier BLOCKED note) is resolved by dossier commit `7526887`.
  - `08_AGENTIC_GENAI_REBUILD_BRAINSTORM.md` was already untracked before this session started. Not part of this task.
- Next step for whoever picks this up: land with `kura` (`land M0b.2`). Then M0b.3 (lane A) and, after cutting the lane B worktree, M0b.9.
- Proposed commit: `feat(M0b): settings, manifest and LATEST.json model [M0b.2]` — trailer `Module: M0b.2`
  - Files: `src/config.py`, `src/snapshot.py`, `src/publisher/manifest.py`, `tests/test_snapshot.py`, `tests/test_manifest.py`, `tests/test_config.py`, `.agents/handoffs/M0b.2.md`
