# BLOCKED — Handoff: M0b.8 (A)
- Branch / checkout: `feat/M0b-trustworthy-data-pipeline` · main checkout `/Users/mrrobot/Desktop/Projects/cricpulse` (HEAD `276cab5`). `git rev-parse --show-toplevel` printed this path.
- State: blocked. I changed no source, test or config file. The only new file is this note. This is the second blocked note for M0b.8; the first is `M0b.8-blocked-1.md`.
- Colour: 🔴 (red zones: `src/publisher/` (the run) and `src/config.py`)

## Conflict 1 — removing the dossier §5.9 settings needs `tests/test_config.py`, which is outside Owns
- Dossier §5.9 removes `sync_secret_token`, `ledger_db_path`, `parquet_dir` and `raw_match_dir`. Card subtask 3 says "every now-unused setting". The card's Owns has `src/config.py` but not `tests/test_config.py`.
- `tests/test_config.py:6-13` `test_settings_default_directories` asserts that `raw_dir`, `raw_match_dir`, `raw_register_dir`, `parquet_dir` and `published_dir` exist after `ensure_directories()`. Removing `parquet_dir` or `raw_match_dir` makes it fail with `AttributeError`, so the full suite, which is part of Verify, fails.
- So neither option is allowed:
  - Keeping the two settings leaves §5.9 unmet. The dossier wins over the card.
  - Editing `tests/test_config.py` touches a file outside Owns, and it would show up in `git status`.
- Settings with no reader in `src` once M0b.8 is built, so the card can name the ones that go:

  | Setting | Readers left in `src` after M0b.8 | Tests that read it |
  |---|---|---|
  | `sync_secret_token` | none (M0b.9 removed the endpoint) | none |
  | `ledger_db_path` | none (ledger deleted) | none |
  | `parquet_dir` | only `ensure_directories` | `test_config.py:12` |
  | `raw_match_dir` | only `ensure_directories` (`extract_archive` goes) | `test_config.py:10` |
  | `raw_dir` | only `ensure_directories` and the two properties built on it (`download_archive` goes) | `test_config.py:9` |
  | `raw_register_dir` | only `ensure_directories` (`download_file` goes) | `test_config.py:11` |
  | `snapshot_date` | none since M0b.7 | `test_config.py:16-19` (the whole test), `conftest.py:23` |
  | `force` | none | `conftest.py:24` |
  | `gcs_bucket` | none (D-1: no GCS SDK) | `conftest.py:22` |

  `published_dir` stays, because `src/api/app.py:33` and `scripts/run_uat.py:30` still read it.
- **Card fix proposed:**
  - Add `tests/test_config.py` to Owns: drop the assertions for the removed settings, and delete `test_settings_snapshot_date_default` if `snapshot_date` goes.
  - Name which settings go: the dossier's four, or every row above.

## Conflict 2 — removing the extract-to-disk path deletes three tests the card does not name
- What the card asks for:
  - Owns: `src/downloaders/*.py` "(remove `ledger` and the extract-to-disk path)".
  - Subtask 3: "every now-unused … method".
- That removes `MatchDownloader.download_archive`, `extract_archive` and `download_and_extract`, and `RegisterDownloader.download_file` and `download_registers`. The run uses `download_to_bronze` and `download_registers_to_bronze` instead.
- `tests/test_downloaders.py` tests exactly those methods:
  - `test_match_downloader_extract_skips_yaml` (`:14`)
  - `test_match_downloader_download_archive` (`:31`)
  - `test_register_downloader` (`:59`)
- The three tests cannot stay once the methods go. The work order allows deleting only the tests the card names, and the card names only `tests/test_ledger.py`.
- What they test is already covered elsewhere:
  - `test_archive.py::test_non_json_members_and_dirs_are_ignored` (yaml and README members are skipped)
  - `test_downloaders.py::test_match_download_to_bronze`
  - `test_downloaders.py::test_register_download_to_bronze`
- **Card fix proposed:** name these three tests for deletion.

## Settle in the same pass
None of these blocks the build alone. Each one changes what a user or the job reports, so it is better ruled now than chosen by the builder.
- **R1 — "up to date" after a failed gate.**
  - Problem: §5.1 writes Silver (step 6) and the manifest (step 7) before the gates (step 9). If the gates fail, the next run on the same zip finds every member current in the manifest and the registers unchanged. It stops "up to date" with exit 0, while `LATEST.json` still names the older snapshot.
  - Cloud effect: the job has "max retries 1" (§5.10). The retry of a gate failure exits 0, so the execution counts as succeeded and the Q-1 failure alert never fires.
  - **Recommendation:** measure "changed" against the live snapshot. A run is up to date only when all three hold:
    - no member changed;
    - the registers equal the live snapshot's;
    - no manifest row has a `version` newer than `LATEST.json`'s `version` (D-8 names sort by time).
  - Result: the retry rebuilds, gates again and fails visibly. This keeps §5.1's step order.
  - Alternative: write the manifest after publish. That changes the step order.
- **R2 — where "registers unchanged" is read from.**
  - No register hash is stored anywhere today. `LatestInfo` has no field for it, and the manifest is per match.
  - **Recommendation:**
    - `runs/<version>.json` records the sha256 of `people.csv` and `names.csv`.
    - The next run compares them with the report of the version `LATEST.json` names.
    - No report means the registers count as changed.
- **R3 — staging left over from a crashed run** (M0b.4 note).
  - A crash between the renames in `silver.merge` leaves some tables new and some old, with staging still in place. Running `merge` again on that staging repairs it.
  - A crash during the parse leaves staging that is incomplete, which `merge` refuses with `FileNotFoundError`, or complete but holding only some batches.
  - **Recommendation:**
    - `main.py` writes a marker in the staging dir after `parse_to_staging` returns.
    - At start, a leftover dir with the marker is merged first. A leftover dir without it is deleted, because Silver was not touched.
- **R4 — two runs in the same minute** (D-8 versions are to the minute).
  - The second run would merge Silver and write the manifest, then fail at publish with `FileExistsError`.
  - **Recommendation:** refuse before step 2 when `snapshots/cricket_<version>.duckdb` or `runs/<version>.json` already exists.
- **R5 — `publish_snapshot` stays.**
  - `tests/test_publisher.py:76` and `:210` call it. That file is outside Owns, and `:76` also holds the `export_gold_parquets` guard the card keeps on purpose. So the card's "only if unused" condition keeps it.
  - Its docstring, `publisher.py:102` "Kept while main.py calls it (M0b.8)", goes stale. The card allows changing `publisher.py` only to remove the method. Leave it, or let a later card fix the docstring.

- Verification run: the card's Verify, run on today's tree, with nothing changed:
  - `python -m pytest tests/test_pipeline.py -q` → no tests ran (file does not exist), **exit 4**
  - `python -m pytest -q` → **115 passed, 2 skipped**, 2 warnings that were already there, exit 0
  - `grep -rn "ledger\|IdempotencyLedger" src tests` → 45 lines, not nothing
  - `grep -rn "export_gold_parquets" src` → 2 lines (`src/publisher/main.py:88`, `:165`)
  - `python -m src.publisher.main run --help` → the old options `--mode`, `--archive`, `--force`, `--export-parquet`; exit 0
- Done-when lines met: none.
  1. `run(archive=settings.nightly_archive, reparse_all=False)` per §5.1, with the "up to date" exit and `runs/<version>.json`: not built
  2. `ingest-local --matches-dir` on the same steps: not built
  3. Ledger and now-unused settings, arguments and methods removed: not done (conflicts 1 and 2)
  4. `tests/test_pipeline.py`, §8 scenarios 1–6: not written
  5. D-11 in `_derive_venue_and_team`, with its test: not done
  6. `files_seen` = the changed members the run tried to parse: not done
- Proof:
  - The nightly update still has no `run` command that builds, checks and publishes a new snapshot.
  - Stopped early: the task card asks for a settings test change and three test deletions that it does not allow.
  - Next, the governor fixes the card (conflicts 1 and 2, and rulings R1–R4) and starts the builder again.
  - Colour 🔴, output only.
- Followed the code, not the card: none. Nothing was built.
- Open issues / decisions needed:
  - Conflicts 1 and 2 need a card change. R1–R4 need a ruling, or a line on the card that adopts the recommendation.
  - Still valid from `M0b.8-blocked-1.md`:
    - Register the `live` marker in `tests/conftest.py`.
    - The `wi_` stripping goes with the ledger.
    - Call `build_marts()` after `build_from_silver(silver_dir, register_dfs, settings)`.
    - The staging dir is `silver/_staging/<version>/`.
    - Gates take `previous=read_latest(data_dir)`, `quarantined` and `files_seen` before `publish()`, then `prune()`.
  - Outside Owns, for later cards:
    - `README.md:30` still draws `data/ledger.db` (M0b.11 owns README).
    - `.github/workflows/deploy.yml:71` still passes `SYNC_SECRET_TOKEN`. That is harmless with `extra="ignore"` (M0b.10).
    - `scripts/run_uat.py:282` still posts to the removed `/api/v1/internal/sync-daily` (M0b.11).
  - The work order names this file `M0b.8.md`, but the first blocked note said the done note would take that name. `kura` may want to rename this one to `M0b.8-blocked-2.md` when it lands.
- Proposed commit: `docs(M0b): M0b.8 blocked on test_config.py and unnamed downloader test deletions; note kept [M0b.8]` — trailer `Module: M0b.8`
  - Files: `.agents/handoffs/M0b.8.md`
