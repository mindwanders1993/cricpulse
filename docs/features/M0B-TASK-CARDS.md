# M0b — Task Cards

**Contract:** `M0B-TRUSTWORTHY-DATA-PIPELINE.md` ("the dossier"). Where a card and the dossier
disagree, the dossier wins and the card is corrected before the task is handed out.
**Written:** 26 Oct 2026, against `dev` at `bf7ccd4`.

---

## 0. Before Task 1

- [x] **Your uncommitted AI/UI work on `dev`** (`src/ai/*`, `src/api/*`, `index.html`, `clarifier.py`,
      tests) needs a home first — commit it on its own branch, or stash it. M0b must start from a clean `dev`.
- [x] Cut the module branch: `git checkout dev && git checkout -b feat/M0b-trustworthy-data-pipeline`.
- [x] Dossier decisions D-1 … D-8 ruled by the owner. *(D-1…D-8 on 26 Oct; D-10 on 3 Nov 2026.)*

---

## 1. Order — Waves and Lanes

```
Lane A (pipeline)  M0b.1 ─┐
                   M0b.2 ─┼─▶ M0b.3 ─▶ M0b.4 ─▶ M0b.5 ─┐
Lane B (API/publish)      └─▶ M0b.9 ─▶ M0b.6 ─▶ M0b.7 ─┴─▶ M0b.8 ─▶ M0b.10 ─▶ M0b.11
```

| Wave | Task | Lane | Model · effort | Starts when |
|---|---|---|---|---|
| 1 | M0b.1 Spike: measure | A | Sonnet · medium | now (changes no code) |
| 1 | M0b.2 Settings, manifest, `LATEST.json` model | A | Opus · high | branch exists |
| 2 | M0b.3 Archive reader | A | Opus · high | M0b.2 committed |
| 2 | M0b.9 API reads `LATEST.json`; sync endpoint removed | B | Opus · high | M0b.2 committed |
| 3 | M0b.4 Silver merge | A | Opus · **xhigh** | M0b.3 committed |
| 3 | M0b.6 Quality gates | B | Opus · **xhigh** | M0b.9 committed |
| 4 | M0b.5 Gold from Silver | A | Opus · high | M0b.4 committed |
| 4 | M0b.7 Publish | B | Opus · **xhigh** | M0b.6 committed |
| 5 | M0b.8 Pipeline entry + integration test + cleanup | A | Opus · **xhigh** | M0b.5 and M0b.7 committed; lane B merged |
| 6 | M0b.10 Cloud + D-3 measurement | A + owner | Opus · **xhigh** *(was high; 12 Nov 2026: it now changes the run)* | M0b.8 committed |
| 7 | M0b.11 UAT + review hand-off | A | Sonnet · medium | M0b.10 done |

- **Lane B** runs in its own worktree: `git worktree add ../cricpulse-M0b-b -b feat/M0b-lane-b`
  from the module branch **after M0b.2 is committed**. It merges back before M0b.8.
- The lanes own different files, so they never conflict (see each card's **Owns**).
- xhigh = data-integrity work (merge, gates, publish, the run itself).

---

## 2. Rules for Every Task

1. **Never overwrite a published file in place.** Write `*.tmp`, then rename.
2. **Live data never shrinks.** Nothing writes `LATEST.json` before the gates pass.
3. **Storage is a directory** (`settings.data_dir`). No GCS SDK calls (dossier D-1).
4. **Stay inside "Owns".** Need another file? Stop and report BLOCKED with the reason.
5. **Do not touch cricket logic** in the parser (M1) or API safety (M0a).
6. **Finish green:** `ruff check src tests` + `python -m pytest -q` + the card's Verify.
7. **Commit locally** on the lane branch with a conventional message. **The owner pushes and merges.**
8. **Cloud commands** (`gcloud …`) are run by the owner. Cards list them exactly.
9. End with a short **hand-off note** in the commit body: what changed, what to watch, anything open.

---

## 3. Cards

### M0b.1 — Spike: measure the full build and query speed — ✅ Done 26 Oct
Results: `M0B-SPIKE-RESULTS.md`. Raised D-9 and D-10.

**Goal:** Real numbers for job memory, snapshot size and query speed before we design around guesses.
**Owns:** `docs/features/M0B-SPIKE-RESULTS.md` (new). Scratch files under `/tmp` only. **No code changes.**
**Subtasks:**
1. Parse 1,000 files with today's `MatchParser.parse_batch`; record time and peak memory
   (`/usr/bin/time -l` on macOS).
2. Full build with today's CLI into a scratch dir:
   `DATA_DIR=/tmp/m0b-spike python -m src.publisher.main ingest-local -m data/raw/match_json -p <people.csv> -n <names.csv>`.
   Record total time, peak memory, snapshot size, match and delivery counts. If it runs out of memory,
   record the largest batch that worked and extrapolate.
3. Write the parsed tables to Parquet (ZSTD); record size per table (this is Silver's size).
4. On the full snapshot, time five typical queries 20 times each, cold and warm (p50/p95):
   one player's batting career, a batter-vs-bowler matchup, phase splits, a leaderboard, a venue profile.
5. Write the results and three recommendations: job memory, staging batch size, D-3 lean.
**Verify:** `M0B-SPIKE-RESULTS.md` has every number filled, and the exact commands to reproduce them.
**Depends:** —

---

### M0b.2 — Settings, manifest and the `LATEST.json` model
**Goal:** The building blocks every later task uses.
**Owns:** `src/config.py`, `src/snapshot.py` (new), `src/publisher/manifest.py` (new),
`tests/test_snapshot.py` (new), `tests/test_manifest.py` (new), `tests/test_config.py`.
**Subtasks:**
1. Settings (dossier §5.9): add `tmp_dir`, `snapshot_path`, `nightly_archive`, `keep_snapshots`,
   `keep_raw_days`. `ensure_directories` also creates `bronze/`, `silver/`, `snapshots/`, `runs/`, `tmp/`.
   Do **not** remove old settings yet (M0b.8 does).
2. `src/snapshot.py`: `LatestInfo` (Pydantic, fields per dossier §5.7), `read_latest(data_dir) -> LatestInfo | None`,
   `write_latest(data_dir, info)` (temp + rename).
3. `src/publisher/manifest.py`: `load(data_dir) -> pl.DataFrame` (empty frame with the schema when
   missing), `is_current(df, match_id, sha, parser_version) -> bool`, `upsert(df, rows) -> pl.DataFrame`,
   `save(data_dir, df)` (temp + rename).
4. Tests: empty manifest; new id; same sha; changed sha; older parser version; save/load round trip;
   `write_latest` leaves no `.tmp` behind; `read_latest` on a missing file → `None`.
**Verify:** `python -m pytest tests/test_snapshot.py tests/test_manifest.py tests/test_config.py -q` → pass; full suite → pass.
**Depends:** —

---

### M0b.3 — Archive reader: stream, diff, parse, quarantine
**Goal:** Read a Cricsheet zip without extracting it, parse only what changed, and survive bad files.
**Owns:** `src/publisher/archive.py` (new), `src/downloaders/match_downloader.py`,
`src/downloaders/register_downloader.py`, `src/parsers/match_parser.py` (**only** the
`PARSER_VERSION = 1` constant and the match-id rule in `parse_file`), `tests/test_archive.py` (new), `tests/test_downloaders.py`.
**Subtasks:**
1. Downloaders: add `download_to_bronze(archive_name, date) -> Path` (match zip) and
   `download_registers_to_bronze(date) -> tuple[Path, Path]`. Keep today's methods and the `ledger`
   argument for now (callers go in M0b.8 and M0b.9).
2. `archive.iter_changed(zip_path, manifest_df, parser_version, reparse_all)` → yields
   `(match_id, sha256, raw_bytes)` for `.json` members that are new or changed. Match id = file stem,
   `wi_` kept (D-9); `parse_file` uses the same rule.
3. `archive.parse_to_staging(items, staging_dir, batch_size=1000) -> RunState`
   (`changed_ids`, `manifest_rows`, `quarantined: list[(match_id, error)]`, `files_seen`).
   Parse with `MatchParser.parse_json(match_id, orjson.loads(raw))`; write `part-<n>.parquet` per
   table every `batch_size` matches.
4. Tests (zips built from `tests/fixtures` at test time): one current + one new → only the new one parsed;
   a broken member → quarantined, others parsed; `batch_size=1` → two parts per table;
   `wi_211824.json` and `211824.json` → two different ids.
5. A live test, marked `@pytest.mark.live` and skipped by default: HEAD
   `recently_added_7_json.zip` and `all_json.zip` on cricsheet.org → 200.
**Verify:** `python -m pytest tests/test_archive.py tests/test_downloaders.py -q` → pass; full suite → pass.
**Depends:** M0b.2

---

### M0b.4 — Silver merge
**Goal:** Replace changed matches in Silver and keep every other row exactly as it was.
**Owns:** `src/publisher/silver.py` (new), `tests/test_silver.py` (new).
**Subtasks:**
1. `silver.merge(silver_dir, staging_dir) -> dict[str, int]` (rows per table) using the DuckDB
   `COPY … UNION ALL BY NAME` of dossier §5.4; write `.tmp`, then rename.
2. First run (no Silver file) → staging only.
3. Delete the staging dir only after every table is renamed into place.
4. Tests: first run; a re-parsed match whose second innings disappeared → its old rows gone;
   untouched matches' rows identical (compare sorted hashes); an exception between write and rename
   → the old Silver file is still readable and unchanged.
**Verify:** `python -m pytest tests/test_silver.py -q` → pass; full suite → pass.
**Depends:** M0b.3

---

### M0b.5 — Gold from Silver
**Goal:** Build the whole Gold schema from all of Silver, every run.
**Owns:** `src/builder/loader.py`, `src/builder/schema.py` (fact-table DDL only), `tests/test_loader_and_schema.py`.
**Subtasks:**
1. `DuckDBLoader.build_from_silver(silver_dir)`: fill `dim_match`, `fact_delivery`, `fact_innings`,
   `fact_wicket_detail`, `fact_player_match` with `INSERT … SELECT … FROM read_parquet(…)` using the
   same column mapping as `load_matches`; then derive `dim_venue` and `dim_team` as today.
   Share the mapping SQL with `load_matches` rather than copying it.
2. D-10: remove the primary keys from the fact tables in `schema.py`; `build_from_silver` and
   `load_matches` use plain `INSERT` for every table they fill (D-9). `load_matches` stays (tests use it).
2a. Set `memory_limit` and a spill `temp_directory` on the build connection (settings, spike §4).
3. Test: for the fixtures, `build_from_silver` and `load_matches` give identical row counts and
   identical per-table checksums; a duplicated match in Silver makes the build fail with an error.
**Verify:** `python -m pytest tests/test_loader_and_schema.py -q` → pass; full suite → pass.
**Depends:** M0b.4

---

### M0b.9 — API reads `LATEST.json`; sync endpoint and hot swap removed  *(lane B)*
**Goal:** The API serves the snapshot the job published, and can no longer write or swap data.
**Owns:** `src/snapshot.py` (add the resolver), `src/api/app.py` (snapshot path + router include only),
`src/api/routes/internal.py` (delete), `src/api/routes/__init__.py`, `src/api/auth.py` (delete),
`src/api/schemas.py` (remove `SyncDailyResponse` only), `tests/test_api_and_agents.py` (remove the
sync test only), `tests/test_snapshot.py`.
**Subtasks:**
1. `resolve_snapshot_path(settings) -> Path | None`: `snapshot_path` setting if set, else
   `data_dir / read_latest(data_dir).path`, else `None`.
2. `app.py` lifespan uses it. Keep today's fallback when it returns `None` (M0a removes it).
3. Delete the internal route, its auth helper, its schema and its test.
4. Tests: resolver precedence (env → `LATEST.json` → `None`); app starts on a `LATEST.json`-named fixture DB.
**Verify:** `python -m pytest tests/test_snapshot.py tests/test_api_and_agents.py -q` → pass;
`grep -rn "sync-daily\|verify_sync_token" src tests` → nothing; full suite → pass.
**Depends:** M0b.2

---

### M0b.6 — Quality gates: never shrinks, quarantine bounded  *(lane B)*
**Goal:** A run that would lose data, or that hit too many bad files, cannot publish.
**Owns:** `src/publisher/quality_gates.py`, `tests/test_quality_gates.py` (new).
**Subtasks:**
1. Signature: `run_quality_gates(con, previous: LatestInfo | None = None, quarantined: int = 0, files_seen: int = 0)`.
2. Add `never_shrinks_matches`, `never_shrinks_deliveries` (skipped when `previous is None`) and
   `quarantine_bounded` (`quarantined ≤ max(5, ceil(0.01 × files_seen))`).
3. Add grain gates for `fact_innings` and `fact_player_match` (they lose their keys in D-10).
   The existing seven gates are unchanged.
4. Tests: each new gate passes and fails on purpose; `previous=None` skips the shrink gates;
   the failure raises `QualityGateFailure` naming the gate.
**Verify:** `python -m pytest tests/test_quality_gates.py tests/test_publisher.py -q` → pass; full suite → pass.
**Depends:** M0b.9 (lane order only)

---

### M0b.7 — Publish: versioned file, `LATEST.json`, prune  *(lane B)*
**Goal:** Publishing is atomic and keeps a short history.
**Owns:** `src/publisher/publisher.py`, `tests/test_publisher.py`.
**Subtasks:**
1. `SnapshotPublisher.publish(temp_db, version) -> LatestInfo`: copy to
   `snapshots/cricket_<version>.duckdb.tmp`, rename, compute sha256, read counts and `data_cutoff`
   (max `match_date`) from the file, then `write_latest`. **No gates inside** — the run calls them first.
2. `prune()`: keep the newest `keep_snapshots` files and never the one `LATEST.json` names; delete raw
   zips older than `keep_raw_days`.
3. Remove `publish_snapshot`'s in-place copies and `export_gold_parquets` (dossier D-6). Keep
   `publish_snapshot` only if a caller remains; otherwise remove it in M0b.8.
4. Tests: two publishes → two files, `LATEST.json` names the second; prune keeps 7 of 9; the
   `LATEST` target is never pruned; an error before `write_latest` leaves the old `LATEST.json`
   byte-identical.
**Verify:** `python -m pytest tests/test_publisher.py -q` → pass; full suite → pass.
**Depends:** M0b.6; M0b.3 — `publish()` imports `PARSER_VERSION` from `src.parsers.match_parser`, so the module branch is merged into lane B first *(ruled 4 Nov 2026: instead of a local constant or a `parser_version` argument, because either is a second source of truth that drifts when M1 bumps the parser)*

---

### M0b.8 — Pipeline entry, integration test and cleanup
**Goal:** One `run` command does dossier §5.1 end to end, and the old path is gone.
**Owns:** `src/publisher/main.py`, `tests/test_pipeline.py` (new), `src/ledger.py` (delete),
`tests/test_ledger.py` (delete), `tests/conftest.py`, `src/config.py` (remove unused settings),
`src/downloaders/*.py` (remove `ledger` and the extract-to-disk path), `tests/test_downloaders.py`,
`src/publisher/publisher.py` (only to remove `publish_snapshot` if unused), `Dockerfile` (default CMD),
`docker-compose.yml` (ingest service command), `src/builder/loader.py` (**only** `_derive_venue_and_team`, D-11),
`tests/test_loader_and_schema.py` (add the D-11 test) *(Owns widened 4 Nov 2026 from M0b.8's first BLOCKED note)*.
`tests/test_config.py` (drop the removed settings' assertions; delete `test_settings_snapshot_date_default`) *(Owns widened 10 Nov 2026 from M0b.8's second BLOCKED note)*.
**Subtasks:**
1. `run(archive=settings.nightly_archive, reparse_all=False)` per dossier §5.1, including the
   "up to date" exit and the run report `runs/<version>.json`.
2. `ingest-local --matches-dir` reuses the same steps with a directory source instead of a zip.
3. Delete the ledger and every now-unused setting, argument and method (`grep` proves none remain). The settings that go
   (governor, 10 Nov 2026, from the second BLOCKED note): `sync_secret_token`, `ledger_db_path`, `parquet_dir`, `raw_match_dir`,
   `raw_dir`, `raw_register_dir`, `snapshot_date`, `force`, `gcs_bucket`; `published_dir` stays (read by `src/api/app.py`
   and `scripts/run_uat.py`). Tests deleted with the extract-to-disk path, each covered elsewhere:
   `test_match_downloader_extract_skips_yaml`, `test_match_downloader_download_archive`, `test_register_downloader`
   (`tests/test_downloaders.py`), plus `tests/test_ledger.py`.
4. `tests/test_pipeline.py`: dossier §8 scenarios 1–6.
5. D-11 (dossier §4, R-6): `_derive_venue_and_team` emits one `dim_venue` row per venue name — `md5(venue_name)`,
   the most frequent non-null city, ties alphabetical (`GROUP BY … QUALIFY row_number() OVER (PARTITION BY venue_name
   ORDER BY city IS NULL, n DESC, city) = 1`). Test: two matches naming one venue with different cities build one row
   with the majority city; a venue whose only city is NULL keeps NULL.
6. `files_seen` for `quarantine_bounded` is the number of changed members the run tried to parse (D-5: "its files").
7. D-12 (dossier §4): (a) "up to date" measured against the live snapshot; (b) the registers' sha256 in `runs/<version>.json`;
   (c) the staging marker — leftover with marker merged first, without it deleted; (d) refuse a second run of the same version
   before step 2. Each gets a test in `tests/test_pipeline.py`: a gate failure followed by a re-run on the same zip rebuilds and
   fails again (exit non-zero, `LATEST.json` unchanged); changed registers alone trigger a build; a staging dir with and without
   the marker; a second run of the same minute refused with nothing written. (e) `publish_snapshot` stays.
**Verify:** `python -m pytest tests/test_pipeline.py -q` → pass; full suite → pass;
`grep -rn "ledger\|IdempotencyLedger" src tests` → nothing; `grep -rn "export_gold_parquets" src` → nothing
(the lane B guard test in `tests/test_publisher.py` keeps the string on purpose);
`python -m src.publisher.main run --help` shows the new options.
**Depends:** M0b.5, M0b.7, lane B merged

---

### M0b.10 — Cloud: job, schedule, mount, rollout; settle D-3
**Goal:** The job runs nightly on Cloud Run and the API picks up each new snapshot.
**Split** *(governor, 12 Nov 2026, before the builder started)*: the builder does subtasks 1–7 and proves them
locally; the task is landed after them. The owner then runs the cloud steps 8–12 with `scripts/infra_m0b.sh`;
M0b.10 is done when those pass and D-3 is recorded. No builder runs `gcloud`.
**Owns:** `scripts/infra_m0b.sh` (new), `src/publisher/rollout.py` (new), `src/publisher/bench.py` (new),
`tests/test_rollout.py` (new), `src/publisher/main.py` (the rollout call and the `bench` command),
`tests/test_pipeline.py`, `src/config.py` and `tests/test_config.py` (one setting; `get_settings` stops creating
folders, D-14a), `src/api/app.py`,
`src/api/routes/health.py`, `src/api/schemas.py` and `tests/test_api_and_agents.py` (`/ready` names the version),
`.github/workflows/deploy.yml`, `Dockerfile`
*(Owns widened 12 Nov 2026 before the builder started: the first card had no call site and no setting for the
rollout, no way for `/ready` to report the version, a `google-auth` dependency outside Owns, and a Verify only the
owner could run. `docs/features/M0B-SPIKE-RESULTS.md` moves to step 11, written by the governor.)*
**Subtasks (builder):**
1. `scripts/infra_m0b.sh` — the owner's one command. Re-runnable: creates what is missing, changes nothing that
   exists. `--dry-run` prints every `gcloud` command instead of running it. Reads `PROJECT_ID`, `REGION` (default
   `us-central1`, D-13c), `ALERT_EMAIL` and `DEPLOYER_SA` from the environment; nothing personal is written into the
   repo. Subcommands:
   - `setup` (D-14b; before any job or service exists): bucket `cricpulse-data`; the job and API service accounts
     with their bucket roles (dossier §5.10); the API account's access to the `GEMINI_API_KEY` secret; `DEPLOYER_SA`
     allowed to act as both accounts; a job-failure email alert to `ALERT_EMAIL`. No project-wide Cloud Run roles.
   - `first-build` (D-14b; after the deploy): grant the job's account the right to update the API service only, and
     the schedules' identity the right to start `cricpulse-ingest` only (with the Sunday run's `--archive all_json`
     override); run the job once with `--archive all_json` and wait; only if it succeeds, create the two schedules
     (D-13d). Re-runnable like `setup`.
   - `bench`: run the bench job (D-13e) and print its output.
   - `status`: print `LATEST.json` from the bucket and `/ready` from the service.
2. `src/publisher/rollout.py` (D-13a, b): `ensure_api_on(version, settings)` reads the API service through the Cloud
   Run Admin API v2 (REST over `httpx`) and, when its `SNAPSHOT_VERSION` env var differs, updates only that env var
   so Cloud Run starts a new revision, then **waits until that revision is ready and raises if it is not** (D-14c),
   with a time limit. The token comes from the metadata server. Empty `rollout_service` → no-op.
   `tests/test_rollout.py`, HTTP mocked at the transport: equal → no update; different → one update that keeps every
   other env var and setting of the service, then waits for ready; a revision that fails, or the time limit, raises;
   an HTTP error raises.
3. `src/publisher/main.py`: a run that publishes, or stops "up to date", then calls `ensure_api_on` with
   `LATEST.json`'s version. A failed gate never calls it. A rollout error exits non-zero with the reason;
   `LATEST.json` stays written. Tests in `tests/test_pipeline.py` for each of the four cases.
4. `src/config.py`: `rollout_service: str = ""` — the service's full name
   `projects/<project>/locations/<region>/services/cricpulse-api`; empty = no rollout. Test in `tests/test_config.py`.
   D-14a: `get_settings()` no longer calls `ensure_directories()`; `run` and `ingest-local` in `main.py` call it
   themselves. Tests: `get_settings()` on an empty data dir creates nothing (`tests/test_config.py`); a run on an
   empty data dir creates what it needs (`tests/test_pipeline.py`); the API starts on a data dir it cannot write
   (`tests/test_api_and_agents.py`).
5. `/ready` names the snapshot it serves: `snapshot_version` from the opened file's name (`cricket_<version>.duckdb`),
   null for the in-memory fallback. `src/api/app.py` keeps it in `app.state`; `HealthResponse` gains the field. Test
   in `tests/test_api_and_agents.py`. Refusing to start without a snapshot stays M0a.
6. `src/publisher/bench.py` and `python -m src.publisher.main bench`: open the snapshot `LATEST.json` names,
   read-only; run the five questions timed in `docs/features/m0b_spike/spike.py` (batting career, ODI leaderboard,
   head-to-head, phase splits, venue profile) 20 warm times each; print p50/p95 per question, then `D-3: mount` when
   every p95 < 300 ms, else `D-3: bake`. Test in `tests/test_pipeline.py` on the fixture build: five rows and a verdict.
7. `Dockerfile` and `.github/workflows/deploy.yml`: one image; the job runs `python -m src.publisher.main run`, the
   service runs `uvicorn src.api.app:app` on port 8080. `deploy.yml` builds once, then creates or updates the
   service (bucket mounted read-only at `/mnt/data`, `DATA_DIR=/mnt/data`, `TMP_DIR=/tmp/cricpulse`, `SNAPSHOT_PATH`
   unset, max 2 instances), the job `cricpulse-ingest` (dossier §5.10, `DATA_DIR=/mnt/data`, `TMP_DIR=/tmp/cricpulse`,
   `ROLLOUT_SERVICE` set) and the bench job (D-13e, `TMP_DIR=/tmp/cricpulse`) on the same image. Drop `GCS_BUCKET` and `SYNC_SECRET_TOKEN` (settings gone since
   M0b.8); keep `GEMINI_API_KEY` from Secret Manager.
**Verify (builder):** `source .venv/bin/activate && ruff check src tests && ruff format --check src tests && python -m pytest tests/test_rollout.py tests/test_pipeline.py tests/test_config.py tests/test_api_and_agents.py -q && python -m pytest -q && bash -n scripts/infra_m0b.sh && PROJECT_ID=demo-project ALERT_EMAIL=alerts@example.com DEPLOYER_SA=deployer@demo-project.iam.gserviceaccount.com bash scripts/infra_m0b.sh --dry-run setup && PROJECT_ID=demo-project bash scripts/infra_m0b.sh --dry-run first-build && python -m src.publisher.main bench --help && python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))" && ! grep -n "GCS_BUCKET\|SYNC_SECRET_TOKEN" .github/workflows/deploy.yml`
**Owner steps (after landing; the owner runs every `gcloud` command):**
8. `PROJECT_ID=… ALERT_EMAIL=… DEPLOYER_SA=… bash scripts/infra_m0b.sh setup`
9. Push the module branch; GitHub → Actions → *Deploy to Google Cloud Run* → *Run workflow* on that branch.
10. `bash scripts/infra_m0b.sh first-build`, then `… status`: `LATEST.json` shows the new version and `/ready`
    names the same one. Watch: on Cloud Run `/tmp` is memory, so the build file and DuckDB's spill count against
    the job's 4 GiB; the governor reads the run's peak memory, and out of memory → 8 GiB in `deploy.yml`.
11. `bash scripts/infra_m0b.sh bench`: the governor records the numbers in `docs/features/M0B-SPIKE-RESULTS.md`
    (cloud section) and the D-3 row. `D-3: bake` → a new card extends `deploy.yml`.
12. After the next scheduled night, `… status`: a new version, or "up to date" with `/ready` on `LATEST.json`'s version.
**Done when:** steps 8–12 pass (they are also UAT U-4 in M0b.11).
**Depends:** M0b.8, M0b.1

---

### M0b.11 — UAT and review hand-off
**Goal:** The owner sees the module work end to end; a fresh session reviews it.
**Owns:** `scripts/run_uat.py` (M0b journeys), `docs/uat/M0B-UAT.md` (new), `README.md` (job usage).
**Subtasks:**
1. Add journeys U-1 … U-4 (dossier §8) to `run_uat.py` where they can be automated; script the rest.
   `run_uat.py` creates the folders it writes: `get_settings()` no longer does (D-14a, 12 Nov 2026).
2. Record results in `docs/uat/M0B-UAT.md`; the owner signs.
3. Hand the branch to a fresh review session → `docs/reviews/M0B-REVIEW.md`.
**Verify:** UAT file complete and signed; review file exists with a verdict.
**Depends:** M0b.10
