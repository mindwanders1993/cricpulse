# Handoff: M0b.8 (A)
- Branch / checkout: `feat/M0b-trustworthy-data-pipeline` · main checkout `/Users/mrrobot/Desktop/Projects/cricpulse` (HEAD `7846bdb`). `git rev-parse --show-toplevel` printed this path before anything else.
- State: done
- Colour: 🔴. Red zones touched: `src/publisher/` (the run), `src/config.py`, and paths under `settings.data_dir`.
- What changed:
  - `src/publisher/main.py`: rewritten.
    - `run [--archive] [--reparse-all]` and `ingest-local -m -p -n` share one `_pipeline` that runs dossier §5.1 steps 1–11.
    - It has the "up to date" exit and writes the run report `runs/<version>.json`.
    - D-12(a)–(d) are built in: up to date against the live snapshot, register sha256 in the report, the staging marker, and the same-minute refusal.
  - `src/builder/loader.py`: `_derive_venue_and_team` only. `dim_venue` now gets one row per venue name, with its most frequent non-null city; ties go alphabetical (D-11).
  - `src/config.py`: removed `gcs_bucket`, `snapshot_date` (and its validator), `force`, `sync_secret_token`, `raw_dir`, `raw_match_dir`, `raw_register_dir`, `parquet_dir` and `ledger_db_path`. `published_dir` stays.
  - `src/downloaders/match_downloader.py`: removed the `ledger` argument, `download_archive`, `extract_archive` and `download_and_extract`.
  - `src/downloaders/register_downloader.py`: removed the `ledger` argument, `download_file` and `download_registers`.
  - `src/ledger.py`: deleted.
  - `tests/test_ledger.py`: deleted (3 tests).
  - `tests/conftest.py`: removed the ledger import and fixture, and the removed settings in `mock_settings`. Registered the `live` marker (handed on from M0b.3's note).
  - `tests/test_config.py`: dropped the assertions on the 4 removed directory settings. Deleted `test_settings_snapshot_date_default`.
  - `tests/test_downloaders.py`: deleted `test_match_downloader_extract_skips_yaml`, `test_match_downloader_download_archive` and `test_register_downloader`, plus the imports only they used.
  - `tests/test_loader_and_schema.py`: added `test_dim_venue_one_row_per_venue_name_with_majority_city` (D-11).
  - `tests/test_pipeline.py` (new): 12 tests that run the CLI end to end. HTTP is mocked at `httpx.Client.get`, and all disk is under `tmp_path`.
  - `Dockerfile`: the default CMD is now `["run"]` (was `["run", "--mode", "incremental"]`).
- Verification run: the card's Verify, run after the last code change, as one command, with Checks first:
  ```
  source .venv/bin/activate && ruff check src tests && ruff format --check src tests && python -m pytest tests/test_pipeline.py -q && python -m pytest -q && ! grep -rn "ledger\|IdempotencyLedger" src tests && ! grep -rn "export_gold_parquets" src && python -m src.publisher.main run --help; echo "VERIFY EXIT $?"
  ```
  - `ruff check` gave "All checks passed!". `ruff format --check` gave "56 files already formatted".
  - `python -m pytest tests/test_pipeline.py -q` gave **12 passed**.
  - `python -m pytest -q` gave **121 passed, 2 skipped, 1 warning**.
    - Before: 115 passed, 2 skipped, 2 warnings.
    - The arithmetic: 115 − 3 downloader tests − 3 ledger tests − 1 snapshot_date test + 12 pipeline tests + 1 D-11 test = 121.
    - The skips are the live HEAD checks. The warning left is Starlette's `httpx` one, which was already there. The `live` marker warning is gone.
  - Both `grep -rn` printed nothing.
  - `run --help` lists `--archive` ("default: NIGHTLY_ARCHIVE, recently_added_7_json"), `--reparse-all` and `--help`.
  - **VERIFY EXIT 0.**
  - Mutation check, run by hand and reverted, with the files restored byte for byte:
    - Dropping the manifest-version rule from `_up_to_date` fails 2 pipeline tests.
    - Restoring today's per-city venue rows fails the D-11 test.
- Done-when lines met:
  1. `run(archive=settings.nightly_archive, reparse_all=False)` per §5.1, with the "up to date" exit and `runs/<version>.json`. **Met.**
     - `test_first_run_publishes_both_matches` (report contents, bronze zip, staging and tmp cleaned)
     - `test_second_run_on_the_same_zip_is_up_to_date`
  2. `ingest-local --matches-dir` reuses the same steps. **Met.** `test_ingest_local_runs_the_same_steps_on_a_directory`: publishes, then is up to date, with no download.
  3. Ledger, unused settings, arguments and methods deleted; `grep` proves none remain. **Met.** The Verify greps print nothing, and a grep of `src tests scripts conf` finds no reader of any removed setting or method.
  4. `tests/test_pipeline.py`, §8 scenarios 1–6. **Met.**
     - 1: `test_first_run_publishes_both_matches`
     - 2: `test_second_run_on_the_same_zip_is_up_to_date`
     - 3: `test_an_edited_match_replaces_its_rows_in_a_new_version` (the edited city is visible; deliveries are replaced, not appended)
     - 4: `test_an_archive_without_a_match_never_shrinks` (`--reparse-all` on an archive with only the Test match still gives 2 matches)
     - 5: `test_a_broken_file_among_200_is_quarantined_and_the_run_publishes`
     - 6: `test_a_failed_gate_leaves_the_live_snapshot_byte_identical`. The gate fails for real: 6 broken members trip `quarantine_bounded`.
  5. D-11 in `_derive_venue_and_team`, with its test. **Met.** `tests/test_loader_and_schema.py::test_dim_venue_one_row_per_venue_name_with_majority_city`.
  6. `files_seen` = the changed members the run tried to parse. **Met.**
     - `RunState.files_seen` is passed to `run_quality_gates`.
     - The reports in scenarios 3 and 4 show 1. The failed-gate test records the `files_seen` passed to the gate.
  7. D-12:
     - (a) **Met.** `test_a_rerun_after_a_failed_gate_rebuilds_and_fails_again`. The re-run on the same zip gates again and exits non-zero, and `LATEST.json` stays byte-identical. A later run with real gates publishes the edit.
     - (b) **Met.** `test_changed_registers_alone_trigger_a_build`: `files_seen` 0, a new version, and 7 players.
     - (c) **Met.**
       - `test_leftover_staging_with_the_marker_is_merged_first`: the leftover's match reaches the snapshot even though it has left the archive.
       - `test_leftover_staging_without_the_marker_is_deleted`: the "ghost" match never reaches Silver.
     - (d) **Met.** `test_a_second_run_in_the_same_minute_is_refused_with_nothing_written`: the data dir is byte-identical and nothing is downloaded.
     - (e) **Met.** `publish_snapshot` is untouched in `publisher.py`.
- Proof:
  - The nightly update is now one command, `run`. It fetches the new Cricsheet files, adds only the matches that changed, checks the new data, and publishes a new snapshot for chat.
  - Works: yes. It never loses a match, and a bad file, a failed check, a crash or a double start leave the live snapshot as it was.
  - Next: land it, then M0b.10 runs the job nightly on Cloud Run.
  - Colour 🔴, output only (no screen changes).
- Followed the code, not the card:
  - **D-11 test, "two matches … with the majority city".** Two matches with two different cities tie 1–1, so neither is a majority. The test uses three matches:
    - Zeta ×2 and Alpha ×1 gives Zeta. The majority sorts after the minority, so the count decides, not the alphabet.
    - It adds the ruling's other two branches: a 1–1 tie gives the alphabetical city, and NULL ×2 with Gamma ×1 gives Gamma.
    - The card's NULL-only case keeps NULL.
  - **`docker-compose.yml` "(ingest service command)".** The `ingest` service has no `command:` and runs the image's default CMD, which is now `["run"]`. Nothing needed changing, so the file is untouched.
  - **The Verify greps.**
    - `grep` exits 1 when it finds nothing, so "→ nothing" is run as `! grep …`. That way the whole Verify exits 0 on a pass.
    - Stale `__pycache__` files of the deleted modules made `grep -rn` print "Binary file … matches". I deleted `src/__pycache__/ledger.cpython-313.pyc` and `tests/__pycache__/test_ledger.cpython-313-pytest-9.1.1.pyc`. Both are git-ignored (`.gitignore:2`); a fresh checkout has neither.
- Open issues / decisions needed:
  - **Choices the card left to the builder.** Each one changes what a user sees, so the reviewer should check them:
    - **The D-12(c) marker holds the run's manifest rows** (`silver/_staging/<version>/_parsed.parquet`, written as `.tmp` and renamed).
      - At start, a leftover is merged and its rows go into the manifest. D-12(a)'s newer-row rule then rebuilds.
      - An empty marker would leave a gap. A leftover whose matches had left the archive would stop "up to date", with Silver ahead of the live snapshot. The test with the marker covers exactly that case.
    - **"No member changed" means `files_seen == 0`.**
      - A member that fails to parse counts as changed, so a run whose only changes are broken files still builds and gates, and `quarantine_bounded` can fire.
      - The cost: a broken file that stays in `recently_added_7_json` gets an identical snapshot republished each night until it leaves the archive.
    - **The run report is written only after a publish** (§5.1 step 11). An up-to-date run, a refused run or a failed run writes none; the exit code and the logs carry the failure.
    - **CLI changes.**
      - `ingest-local` now requires `-p` and `-n`, because step 2 needs the registers and D-12(b) compares their sha256.
      - `--export-parquet` is gone from both commands (D-6). `run` loses `--mode` and `--force`.
    - The temporary build DB `tmp/<version>.duckdb` is deleted after a publish and after a failure.
  - **On no card:** dossier §5.3 / R-4, "A Sunday full run logs ids present in the manifest but absent from `all_json`". It is outside §5.1, which is the card's goal, so I did not build it. `main.py` is where it would go. It needs a card line.
  - **Rare edge** (needs `silver.py`, outside Owns): the job could die during `silver.merge`'s final `rmtree` of the staging dir, after every rename. Two outcomes:
    - The marker survives but some table parts are gone. Every later run then fails loudly with `FileNotFoundError` naming that staging dir, until someone deletes it.
    - The marker is gone. The dir is deleted (Silver is already complete), and the crashed run's manifest rows are lost, so its matches are parsed again while they are still in an archive.
  - **Outside Owns, now stale but harmless** (`extra="ignore"`):
    - `.env.example` still lists `GCS_BUCKET`, `SNAPSHOT_DATE`, `FORCE` and `SYNC_SECRET_TOKEN`.
    - `.github/workflows/deploy.yml:70-71` still sets `GCS_BUCKET` and `SYNC_SECRET_TOKEN` (M0b.10).
    - `README.md:30` still shows `ledger.db`, and `README.md:97` shows `SYNC_SECRET_TOKEN` (M0b.11).
    - `scripts/run_uat.py:282` still posts to the removed sync endpoint (M0b.11).
    - `publisher.py:102`, the `publish_snapshot` docstring "Kept while main.py calls it (M0b.8)", is now stale (D-12(e): a later card).
  - **Not measured here:** the full 22,818-file run (U-1), the first real D-11 build on the 66 venues, and timing. Tests may not read `data/`.
  - Evals: not yet.
- Proposed commit: `feat(M0b): one run command end to end — up-to-date exit, run report, D-11 venue city, D-12 run safety; ledger and old settings removed [M0b.8]`, trailer `Module: M0b.8`
  - Files: the 13 paths under "What changed" (12 tracked, plus the new `tests/test_pipeline.py`) and `.agents/handoffs/M0b.8.md`.
