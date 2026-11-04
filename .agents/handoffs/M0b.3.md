# Handoff: M0b.3 (A)
- Branch / worktree: `feat/M0b-trustworthy-data-pipeline` · main checkout `/Users/mrrobot/Desktop/Projects/cricpulse`
- State: done
- What changed:
  - `src/downloaders/match_downloader.py` — new `download_to_bronze(archive_name, date) -> Path`, writes `bronze/cricsheet/<YYYY-MM-DD>/<archive>.zip` (§5.2). Today's methods and the `ledger` argument are unchanged.
  - `src/downloaders/register_downloader.py` — new `download_registers_to_bronze(date) -> (people, names)`, writes `bronze/registers/<YYYY-MM-DD>/{people,names}.csv`. Today's methods and the `ledger` argument are unchanged.
  - `src/parsers/match_parser.py` — `PARSER_VERSION = 1`. `parse_file` match id is now `json_path.stem` (wi_ kept, D-9). No other line touched.
  - `src/publisher/archive.py` (new) — `RunState` dataclass, `iter_changed`, `parse_to_staging`. `iter_changed` reads members straight from the zip without extracting, and uses `manifest.is_current` for the diff. A repeated id in one zip raises `ValueError` (D-9). `parse_to_staging` quarantines any exception from `orjson.loads` or `parse_json` (D-5). It writes `<staging>/<table>/part-<n>.parquet` for all 5 tables every `batch_size` matches, plus one for the remainder.
  - `tests/test_archive.py` (new, 12 tests). `tests/test_downloaders.py`: 2 tests and 1 live test (2 params) added; the existing 3 are unchanged.
- Verification run (after the last code change):
  - `python -m pytest tests/test_archive.py tests/test_downloaders.py -q` → **17 passed, 2 skipped** (the live ones), exit 0
  - `python -m pytest -q` → **75 passed, 2 skipped** (61 before + 14 new), 2 warnings, exit 0. One warning was already there (Starlette `httpx`); the new one is `PytestUnknownMarkWarning` for `live`, see open issues.
  - `ruff check src tests && ruff format --check src tests` → clean, exit 0
  - `CRICPULSE_LIVE=1 python -m pytest tests/test_downloaders.py -q -k live` → **2 passed** (cricsheet.org HEAD → 200 for both archives), run once by hand
- Done-when lines met (subtasks):
  1. Downloaders write to bronze → `test_downloaders.py::test_match_download_to_bronze`, `::test_register_download_to_bronze`. Old methods kept: the 3 existing downloader tests pass unchanged.
  2. `iter_changed` yields only new or changed `.json` members; id = stem with `wi_` kept → `test_archive.py::test_one_current_one_new_only_new_is_parsed`, `::test_changed_sha_is_yielded`, `::test_older_parser_version_is_yielded`, `::test_reparse_all_yields_current_members`, `::test_non_json_members_and_dirs_are_ignored`, `::test_duplicate_id_in_zip_fails_loudly`. `parse_file` uses the same rule → `::test_parse_file_keeps_wi_prefix`.
  3. `parse_to_staging` → `RunState` with parts per table → `::test_batch_size_one_writes_two_parts_per_table`, `::test_default_batch_size_writes_one_part_per_table`. Manifest rows fit `manifest.upsert` → `::test_manifest_rows_upsert_into_manifest`.
  4. Tests the card names (zips built in `tmp_path` from `tests/fixtures`):
     - one current + one new → only the new one parsed → `::test_one_current_one_new_only_new_is_parsed`
     - broken member → quarantined, others parsed → `::test_broken_member_is_quarantined_others_parsed`
     - `batch_size=1` → two parts per table → `::test_batch_size_one_writes_two_parts_per_table`
     - `wi_211824.json` + `211824.json` → two ids → `::test_wi_prefix_gives_two_different_ids`
  5. Live HEAD test, `@pytest.mark.live`, skipped by default → `test_downloaders.py::test_live_cricsheet_archive_exists[recently_added_7_json|all_json]`. It runs only with `CRICPULSE_LIVE=1`.
- Open issues / decisions needed:
  - **Dossier §6 vs card on the downloaders.** §6 says "drop ledger args" in M0b.3. The card and this goal say keep them (callers go in M0b.8/M0b.9; the ledger was ruled on 3 Nov to be deleted in M0b.8). I followed the card. The governor should change §6 to match the 3 Nov ruling.
  - **`live` marker isn't registered.** Registering it needs `pyproject.toml` (`markers = ["live: ..."]`) or `conftest.py`, and both are outside Owns. Until then pytest shows `PytestUnknownMarkWarning`, and skipping depends on `skipif(CRICPULSE_LIVE != "1")`, not on the marker. If someone adds `--strict-markers` before the marker is registered, collection fails. Suggest registering it in M0b.8.
  - **`wi_` is still stripped in two callers outside Owns.** `src/publisher/main.py:132,169` and `src/api/routes/internal.py:62,103` use those ids for ledger keys only. `parse_file` now keeps `wi_`, so the ledger key and the parsed id differ for women's matches until M0b.8/M0b.9 remove those paths.
  - `RunState.manifest_rows[*].version` comes from `staging_dir.name`, because §5.2 puts staging at `silver/_staging/<version>/`, and the card's signature has no `version` argument. M0b.8 must pass a staging dir named after the run version.
  - `files_seen` counts the items given to `parse_to_staging` (the changed ones), not every member of the zip. If the `quarantine_bounded` gate (M0b.6) means 1% of all archive files, M0b.8 has to count members separately.
  - `iter_changed` calls `manifest.is_current`, which runs one Polars filter per member. That's fine at about 23k members (O(n²) in theory). If M0b.8 timing shows it's slow, build a lookup dict once.
  - `08_AGENTIC_GENAI_REBUILD_BRAINSTORM.md` was already untracked when this session started. Not part of this task.
- Next step for whoever picks this up: land with `kura` (`land M0b.3`). Then M0b.4 (Silver merge, Opus · xhigh), which reads `<staging>/<table>/*.parquet`.
- Proposed commit: `feat(M0b): archive reader, bronze downloads, PARSER_VERSION and D-9 match id [M0b.3]` — trailer `Module: M0b.3`
  - Files: `src/publisher/archive.py`, `src/downloaders/match_downloader.py`, `src/downloaders/register_downloader.py`, `src/parsers/match_parser.py`, `tests/test_archive.py`, `tests/test_downloaders.py`, `.agents/handoffs/M0b.3.md`
