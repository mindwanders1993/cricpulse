# Handoff: M0b.15 (A)
- Branch / checkout: `feat/M0b-trustworthy-data-pipeline`, main checkout `/Users/mrrobot/Desktop/Projects/cricpulse`. `git rev-parse --show-toplevel` printed exactly that path before any work.
- State: done
- Colour: 🔴 (`src/publisher/` is a red zone)
- What changed:
  - `src/publisher/main.py`:
    - **(a) The run lock.** `_run_lock(settings)` is a context manager. It creates `<data_dir>/run.lock` with `open("x")` (`O_CREAT | O_EXCL`) and writes `{"version", "started"}` into it. It yields the start time, which `_pipeline` now takes as a parameter instead of reading the clock itself. `run` and `ingest-local` hold it for the whole command, so the staging recovery, the D-12(d) check, every write and (for `run`) the API rollout all happen inside it.
    - A held lock prints `another run is in progress: <version>, started <time>` and exits 1. Another run's lock is never deleted. The lock goes in a `finally`.
    - A lock whose start time is 2 hours or more before this run's is taken over, with the warning log `run_lock_taken_over`. A lock left empty, by a run killed between creating it and writing it, ages by its file time instead (`_lock_holder`).
    - `bench` takes no lock.
    - New constants: `RUN_LOCK`, `STALE_LOCK = 2 h`, `ALL_JSON`.
    - **(b) Staging goes last.** `_apply` now deletes staging after step 7 saves the manifest: the marker first, then the folder. The D-12(c) recovery calls `_apply`, so it does the same. A crash while staging is being deleted leaves a folder with no marker, which the next run deletes. The `_recover_staging` comment and the `_apply` docstring say so.
    - **(d) The absence log.** On an `--archive all_json` run, `run` passes a set that `iter_changed` fills with every member id. `_pipeline` works out `absent` as the sorted manifest ids missing from that set. The console line adds `, absent from archive: N` (only on `all_json` runs; the line is now `soft_wrap`). The report gets `absent_from_archive` (only on `all_json` runs). A non-empty list is also logged as `absent_from_archive` with the ids (see Open issues 1). Nothing is deleted.
  - `src/publisher/archive.py`:
    - `iter_changed` takes an optional sixth argument, `member_ids`, which receives every `.json` member id, changed or not (D-18d). Callers that pass four or five arguments work as before.
    - **(e)** `parse_to_staging` re-raises `MemoryError` and `OSError`. Every other exception is still quarantined, as D-5 says.
  - `src/publisher/silver.py`: `merge` no longer deletes the staging folder (D-18b). The `shutil` import went with it.
  - `tests/test_pipeline.py`: 9 new tests in four sections, D-18(a), (b), (d) and (e). Added `import os`.
  - `tests/test_archive.py`: 2 new tests (one runs twice, once per error type): `member_ids`, and the `MemoryError`/`OSError` re-raise.
  - `tests/test_silver.py`: the one line the card allows, `:61`. It changed from `assert not staging.exists()` to `assert staging.exists()` (the merge now leaves staging), with a comment that points to the pipeline test.
  - No new fixture files. No other test was changed, skipped or deleted.
- Verification run: `source .venv/bin/activate && ruff check src tests && ruff format --check src tests && python -m pytest tests/test_pipeline.py tests/test_silver.py tests/test_archive.py -q && python -m pytest -q`
  - ruff: "All checks passed!", "61 files already formatted"
  - Card slice: 72 passed
  - Full suite: 192 passed, 2 skipped (the live cricsheet.org tests, as before), 1 warning (starlette, as before)
  - Exit code: 0, run after the last file change. The baseline before the work was 180 passed, 2 skipped.
  - Checked against the old code (a scratch copy with `git diff -- src/` reversed, deleted afterwards): 12 of the 13 new test runs failed on the old code. The one that passed is `test_ingest_local_writes_no_absence_log`, which only guards that the field stays absent. With only `RUN_LOCK` added to the old code, the overlap test failed at `second.exit_code`: the old code let the second run go ahead (exit 0).
  - `git status --short`: `M` on `src/publisher/{archive,main,silver}.py` and `tests/test_{archive,pipeline,silver}.py`; `??` on this note. `??` on the owner's `08_AGENTIC_GENAI_REBUILD_BRAINSTORM.md`, left alone.
- Done-when lines met:
  - **D-18(a), one run at a time.** Met:
    - `test_pipeline.py::test_a_run_started_while_another_holds_the_lock_exits_non_zero_and_changes_nothing`. A second run starts inside the first run's parse, before its marker exists: the window from review finding 1. The second run exits 1 with the message, downloads nothing, and leaves the whole `data_dir` tree byte for byte as it was (the first run's unmarked staging included). The first run then publishes all three matches.
    - `test_pipeline.py::test_the_lock_is_gone_after_a_successful_run_and_after_a_failed_one`
    - `test_pipeline.py::test_a_lock_older_than_two_hours_is_taken_over`. A lock 1 h 59 min old is refused and left in place. One 2 h 2 min old is taken over, and the run publishes.
    - `test_pipeline.py::test_an_empty_lock_ages_by_its_file_time`
  - **D-18(b), the manifest before staging goes.** Met:
    - `test_pipeline.py::test_a_crash_between_the_merge_and_the_manifest_write_is_finished_by_the_next_run`. Staging and its marker survive the crash. The next archive no longer carries the match, and the next run still does not stop "Up to date": the match reaches the manifest and Gold.
    - `test_pipeline.py::test_the_run_deletes_staging_only_after_the_manifest_is_saved`: the assertion moved from `test_silver.py:61`.
    - `test_silver.py::test_first_run_is_staging_only`: the merge leaves staging.
  - **D-18(d), the absence log.** Met:
    - `test_pipeline.py::test_a_full_archive_run_names_the_manifest_ids_it_lacks_and_keeps_them`. The report lists `["1001", "9001"]` and the console prints `absent from archive: 2`. All four matches stay in Gold and the manifest. The nightly archive's report has no such field. A second `all_json` run is "Up to date" and still prints the count.
    - `test_pipeline.py::test_ingest_local_writes_no_absence_log`
    - `test_archive.py::test_member_ids_receives_every_json_member_changed_or_not`
  - **D-18(e), a passing failure stops the run.** Met:
    - `test_pipeline.py::test_a_memory_error_from_the_parser_stops_the_run_and_removes_nothing`. After a parser bump the run stops on `MemoryError`. Silver, the manifest and the error table are byte for byte unchanged, the error table is still empty, `LATEST.json` is unchanged, and the lock is gone.
    - `test_archive.py::test_a_memory_or_os_error_stops_the_parse_instead_of_quarantining[error0, error1]`
  - **The full suite passes.** Met: 192 passed, 2 skipped.
  - **No test reads or writes `data/`.** Met: every new test uses the `settings` fixture or `tmp_path`. The proof run used a scratch `DATA_DIR`, deleted afterwards.
- Proof: output only (the Kaizen card's Proof is "none"; no screen changed).
  - A second run started while one is going stops at once with "another run is in progress: <version>, started <time>", and nothing in the data changes.
  - A Sunday full-archive run names the matches Cricsheet no longer carries, under `absent_from_archive`, and keeps them in the app.
  - A crash after the merge is finished by the next run instead of a false "Up to date". An out-of-memory parse stops the run instead of removing a healthy match.
  - The proof run: `ingest-local` on the two fixture matches, with `DATA_DIR` in the session scratch folder. The first time, another run's lock was in place: `another run is in progress: v-nightly-demo, started 2026-11-12T18:47:04+00:00`, exit 1, and that lock was left as it was. The second time, without it: `Changed: 2, parsed: 2, quarantined: 0, removed: 0` / `Published v20261112T1847Z: 2 matches, 1603 deliveries`, exit 0, and no lock left behind.
- Followed the code, not the card:
  - The card says `run` and `ingest-local` take the lock "before anything else". The lock lives in `data_dir`, and since D-14a `get_settings()` creates no folders, so `settings.ensure_directories()` runs first. The lock comes right after it, before the staging recovery, the D-12(d) check and every download. `ingest-local`'s "No .json files found" check also stays before the lock: it only reads the input folder.
- Open issues / decisions needed:
  1. **An up-to-date `all_json` run writes no run report** (D-12: an up-to-date run publishes nothing and writes no report). After a week of nightlies the Sunday full run will usually be up to date. In that common case the ids reach only the log line `absent_from_archive` (dossier §5.3: "a Sunday full run logs ids"), and the console shows only the count. The card's goal says "named in the run report". If the owner should find them in `runs/`, an up-to-date full run would need a small report of its own. That is a governor ruling, not built here.
  2. `run` holds the lock through the API rollout too, because the rollout is part of the command. A run started during a slow rollout is refused.
  3. A takeover race remains: two runs that find a dead run's lock within the same few milliseconds can both take it over. Each deletes the lock, then creates its own, and the second can delete the first one's fresh lock. This needs a dead run plus two starts at the same moment. Not fixed.
  4. A run refused just as the holder finishes (the lock is gone between the refused create and the read) exits non-zero with a `FileNotFoundError` instead of retrying. Nothing is written.
  5. Whether the exclusive create holds on the bucket mount is still carried to the deploy (D-18f, dossier §7.1). Unchanged.
  6. Docs outside Owns: the comment in dossier §5.2, `silver/_staging/<version>/... # deleted after merge`, should now read "deleted after the manifest is saved" (D-18b).
- Proposed commit: `fix(M0b): one run at a time, the manifest before staging goes, the absence log, a passing failure stops the run [M0b.15]` — trailer `Module: M0b.15`
