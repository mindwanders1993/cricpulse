# Handoff: M0b.4 (A)
- Branch / worktree: `feat/M0b-trustworthy-data-pipeline` · main checkout `/Users/mrrobot/Desktop/Projects/cricpulse` (M0b.3 landed as `86d786b`)
- State: done
- What changed:
  - `src/publisher/silver.py` (new). It has `TABLES`, `MEMORY_LIMIT` and `merge(silver_dir, staging_dir) -> dict[str, int]`. The merge runs in four phases:
    1. **Pre-checks, nothing written yet.** Every table must have staging parts. Staged `matches.match_id` must be non-null and unique (D-9). A NULL id would make `NOT IN` drop every old row.
    2. **Write.** Each table gets its own DuckDB `COPY (old WHERE match_id NOT IN staged UNION ALL BY NAME staged) TO <table>.parquet.tmp` (§5.4). On the first run there is no Silver file, so the source is staging only.
    3. **Check before rename.** The merged `matches.tmp` must hold exactly |old ∪ staged| rows and ids, so no match is lost and no duplicate gets in. On any failure in phases 2–3, the `.tmp` files are removed, Silver is untouched, and the error is re-raised.
    4. **Rename and clean up.** Every `.tmp` is renamed into place, then the staging dir is deleted.
  - Memory: in-memory DuckDB with `memory_limit = '2GB'` (spike §4 rec. 3) and `preserve_insertion_order = false`, so `COPY` streams instead of buffering. Nothing is loaded into Python or Polars.
  - `tests/test_silver.py` (new, 8 tests). Staging is built the way the pipeline builds it: a zip made from `tests/fixtures`, then `archive.iter_changed`, then `archive.parse_to_staging`.
- Verification run (after the last file change, see the session):
  - `python -m pytest tests/test_silver.py -q` → **8 passed**, exit 0
  - `python -m pytest -q` → **83 passed, 2 skipped** (75 + 8 new), 2 warnings, exit 0. Both warnings were already there (Starlette `httpx`, unregistered `live` marker from M0b.3).
  - `ruff check src tests && ruff format --check src tests` → clean, exit 0
- Done-when lines met (subtasks):
  1. `merge` uses the §5.4 `COPY … UNION ALL BY NAME`, writes `.tmp` and then renames, and returns rows per table → `src/publisher/silver.py`; `test_silver.py::test_first_run_is_staging_only` (checks the returned counts).
  2. First run means staging only → `::test_first_run_is_staging_only`. Row hashes equal the staged parts, and there are no `.tmp` files left.
  3. Staging is deleted only after every rename → `::test_first_run_is_staging_only` (staging gone after success). `::test_exception_between_write_and_rename_leaves_silver_unchanged` covers failure: staging is kept, and re-running the same merge completes.
  4. Tests the card names:
     - first run → `::test_first_run_is_staging_only`
     - a re-parsed match whose 2nd and 3rd innings disappeared loses those rows (innings, deliveries, wickets) → `::test_reparsed_match_loses_its_dropped_innings`
     - untouched matches' rows are identical (sorted row hashes, all 5 tables) → `::test_untouched_matches_rows_are_identical`
     - exception between write and rename (`Path.replace` raises) → old Silver files are byte-identical and still readable → `::test_exception_between_write_and_rename_leaves_silver_unchanged`
  - The goal's extra requirements:
    - never shrink → `::test_match_absent_from_staging_is_never_dropped` and the phase-3 check
    - duplicate fails loudly (D-9) → `::test_duplicate_staged_match_id_fails_loudly_and_writes_nothing` and `::test_duplicate_already_in_silver_fails_loudly_before_rename`
    - incomplete staging is refused → `::test_staging_without_a_table_is_refused`
- Open issues / decisions needed:
  - **What "never shrink a table" means here.** Rows may drop: §5.4 says a re-parsed match that lost an innings loses those rows, and the card tests that. So the merge enforces that no **match** is lost: the merged match set is exactly old ∪ staged. The row-count floor (`delivery_count ≥ 0.999 × previous`) is the M0b.6 gate. If the owner meant a row floor inside the merge, that would contradict §5.4 and needs a ruling.
  - **Spill directory isn't set.** DuckDB uses its default temp directory. `merge` has no settings argument (card signature). If M0b.8/M0b.10 measurements show spilling, add `SET temp_directory` pointing at `settings.tmp_dir`, so it's on local disk and not the mount (§5.2). With `preserve_insertion_order = false` and only a small id set on the anti-join build side, spilling isn't expected.
  - **Bounded memory isn't measured on the full 22.8k-file Silver here.** Tests must not read `data/`. It rests on DuckDB's streaming `COPY` plus `memory_limit`. Measure it in M0b.8/U-1.
  - **Interrupted renames.** The five renames aren't atomic as a group. If a crash lands mid-rename, some tables are new and some old, and staging still exists. Re-running `merge` with that staging is idempotent and repairs it (tested via the re-run in the rename-failure test). M0b.8 should re-run a leftover `_staging/<version>/` before parsing a new one.
  - Only `matches` gets the uniqueness check. In the child tables, a match id appearing many times is normal.
  - `08_AGENTIC_GENAI_REBUILD_BRAINSTORM.md` was already untracked before this session. Not part of this task.
- Next step for whoever picks this up: land with `kura` (`land M0b.4`). Then M0b.5 (Gold from Silver), which reads `silver/<table>.parquet`.
- Proposed commit: `feat(M0b): Silver merge — tmp then rename, never loses a match, duplicates fail [M0b.4]` — trailer `Module: M0b.4`
  - Files: `src/publisher/silver.py`, `tests/test_silver.py`, `.agents/handoffs/M0b.4.md`
