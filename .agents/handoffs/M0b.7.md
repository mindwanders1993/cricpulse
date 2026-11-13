# Handoff: M0b.7 (B)
- Branch / worktree: `feat/M0b-lane-b` · `/Users/mrrobot/Desktop/Projects/cricpulse-M0b-b`. Built on `5a8aaba`, the module branch merged into lane B per the ruling in `M0b.7-blocked-1.md`.
- State: done
- What changed:
  - `src/publisher/publisher.py`:
    - **New `publish(temp_db, version) -> LatestInfo`.** It runs no gates. Steps:
      1. Refuses with `FileExistsError` if `snapshots/cricket_<version>.duckdb` exists.
      2. Copies the DB to `….duckdb.tmp` and renames it.
      3. Computes sha256 of the published file.
      4. Reads raw `COUNT(*)` of `gold.dim_match` and `gold.fact_delivery`, and `MAX(match_date)`, from that file.
      5. Builds `LatestInfo` with `parser_version=PARSER_VERSION`, imported from `src.parsers.match_parser`.
      6. Calls `write_latest`, which writes `.tmp` and renames.
    - **New `prune(today=None) -> list[Path]`.**
      - Snapshots: keeps the newest `keep_snapshots` `cricket_*.duckdb`, sorted by name (D-8 names sort by time), and never deletes the one `LATEST.json` names.
      - Raw zips: deletes `bronze/cricsheet/<YYYY-MM-DD>/*.zip` more than `keep_raw_days` days older than `today`, then removes the date folder if it is empty.
      - Age comes from the date folder name, not mtime, which is unreliable on a FUSE mount. `today` defaults to the UTC date and is a parameter only so the 30/31-day boundary test is exact.
    - **`publish_snapshot`:**
      - The in-place `shutil.copy2` to `published/` is gone.
      - It now runs `run_quality_gates(con, previous=read_latest(data_dir))`, which includes never-shrinks (invariant 1), then calls `publish()`.
      - It returns `(snapshot path, LATEST.json path)`.
      - `snapshot_date` is replaced by `version`, defaulting to the D-8 UTC name.
      - It is kept only because `main.py` still calls it.
    - **`export_gold_parquets` removed** (D-6).
  - `tests/test_publisher.py`: 1 test before, 10 now.
    - The existing `test_snapshot_publisher` was changed only where the card changes behaviour:
      - The `export_gold_parquets` block is deleted (card subtask 3).
      - The `snapshot_date=` call and the `cricket_2026_08_31` / `cricket_latest` name checks now assert the new paths: `snapshots/cricket_<version>.duckdb` and `snapshots/LATEST.json`.
      - Its 2-match query on the published file is kept.
      - Added assertions: no `published/cricket_latest.duckdb`, and no `export_gold_parquets` attribute.
- Verification run, after the last code change (re-run after this note; that output is in the session):
  - `python -m pytest tests/test_publisher.py -q` gave **10 passed**, exit 0.
  - `python -m pytest -q` gave **115 passed, 2 skipped**, exit 0. Before: 106 passed, 2 skipped. The skips are the live-site HEAD checks, marked and already there. The 2 warnings were there before.
  - `ruff check src tests && ruff format --check src tests` is clean.
  - `python -c "import src.publisher.main"` imports fine.
- Done-when lines met (subtasks):
  1. `publish()`:
     - Two files and `LATEST.json` field values: `test_two_publishes_two_files_latest_names_second`. It checks sha256, raw `COUNT(*)` against the source DB, `data_cutoff`, `parser_version` and the relative path.
     - `.tmp` then rename for both the snapshot and `LATEST.json`: `test_publish_writes_tmp_then_renames`.
     - No gates: `test_publish_runs_no_gates`. It replaces `run_quality_gates` with a function that fails if called, against a `LATEST.json` that would fail never-shrinks.
     - Refuses to overwrite: `test_publish_refuses_existing_snapshot`.
  2. `prune()`:
     - Keeps 7 of 9: `test_prune_keeps_seven_of_nine`.
     - The `LATEST` target is never pruned: `test_prune_never_deletes_latest_target`. `LATEST.json` names the oldest; 8 files remain and `LATEST.json` is byte-identical.
     - Raw zips: `test_prune_deletes_raw_zips_older_than_keep_raw_days`. 31 days old is deleted; 30 days and 1 day are kept.
  3. In-place copies and `export_gold_parquets` removed: `test_snapshot_publisher`.
     - `publish_snapshot` kept because callers remain: `main.py:84`, `:162`.
     - Its gate path: `test_publish_snapshot_gates_against_previous_latest`. A shrinking run raises `[never_shrinks_matches]`; `LATEST.json` is byte-identical and no snapshot is written.
  4. Tests: all of the above. An error before `write_latest` (an empty DuckDB file, so reading the counts fails) leaves the old `LATEST.json` byte-identical and the old snapshot's sha unchanged: `test_error_before_write_latest_leaves_latest_byte_identical`.
- Open issues / decisions needed:
  - **`main.py` will break at run time. Left alone as instructed (it is M0b.8's file).**
    - `src/publisher/main.py:88` and `:165` still call `publisher.export_gold_parquets(snap_path)`, which no longer exists.
    - `run` (where `--export-parquet` defaults to True) will publish, then raise `AttributeError` before recording to the ledger.
    - `ingest-local --export-parquet` fails the same way. `ingest-local` without the flag works.
    - No test runs `main.py`. M0b.8's Verify grep for `export_gold_parquets` catches it.
  - `main.py` prints `latest_path` as "Serving Snapshot". It is now the `LATEST.json` path, not a `.duckdb`. Cosmetic; M0b.8 rewrites it.
  - **Unused after this task, for M0b.8's settings cleanup:**
    - `settings.snapshot_date` has no reader left in `src`.
    - `published_dir` is still read by `src/api/app.py:33` (the fallback M0a removes) and `scripts/run_uat.py:30`.
    - Nothing writes `published/cricket_latest.duckdb` any more, so `run_uat.py` (M0b.11's file) reads a stale or missing file until it moves to `resolve_snapshot_path`.
  - **Orphaned files after a failed `publish()`.**
    - If it fails after the rename (for example, a bad DB), `snapshots/cricket_<version>.duckdb` stays, unnamed by `LATEST.json`.
    - It counts among the newest when pruning, until it ages out.
    - A copy that fails part-way leaves a `.duckdb.tmp`, which `prune()` ignores (it globs `*.duckdb`).
    - Neither is live data. I left both alone rather than add cleanup the card does not ask for. Rule if wanted.
  - **Same-minute re-runs.** `publish_snapshot` without a `version` uses minute-resolution D-8 names, so two runs in one minute fail the second with `FileExistsError`. That is by design: the published file is not overwritten.
  - **Register CSVs are not pruned.** D-7 names only raw zips; `bronze/registers/<date>/` grows by two small CSVs a day.
- Next step for whoever picks this up: land with `kura` (`land M0b.7`), then merge lane B back for M0b.8.
- Proposed commit: `feat(M0b): versioned atomic publish, LATEST.json and retention prune; Parquet export removed [M0b.7]`, trailer `Module: M0b.7`
  - Files: `src/publisher/publisher.py`, `tests/test_publisher.py`, `.agents/handoffs/M0b.7.md`
