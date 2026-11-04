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
| 6 | M0b.10 Cloud + D-3 measurement | A + owner | Opus · high | M0b.8 committed |
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
`docker-compose.yml` (ingest service command).
**Subtasks:**
1. `run(archive=settings.nightly_archive, reparse_all=False)` per dossier §5.1, including the
   "up to date" exit and the run report `runs/<version>.json`.
2. `ingest-local --matches-dir` reuses the same steps with a directory source instead of a zip.
3. Delete the ledger and every now-unused setting, argument and method (`grep` proves none remain).
4. `tests/test_pipeline.py`: dossier §8 scenarios 1–6.
5. Risk R-6 (dossier §7): `build_from_silver` now uses plain `INSERT` for `dim_venue`; if real data holds one venue name
   with two cities, the first full build fails. Add a test that two matches naming one venue with different cities build
   without a duplicate-id error, or stop with a BLOCKED note that quotes the failing rows for a ruling.
**Verify:** `python -m pytest tests/test_pipeline.py -q` → pass; full suite → pass;
`grep -rn "ledger\|IdempotencyLedger\|export_gold_parquets" src tests` → nothing;
`python -m src.publisher.main run --help` shows the new options.
**Depends:** M0b.5, M0b.7, lane B merged

---

### M0b.10 — Cloud: job, schedule, mount, rollout; settle D-3
**Goal:** The job runs nightly on Cloud Run and the API picks up each new snapshot.
**Owns:** `scripts/infra_m0b.sh` (new), `src/publisher/rollout.py` (new), `tests/test_rollout.py` (new),
`.github/workflows/deploy.yml`, `Dockerfile`, `docs/features/M0B-SPIKE-RESULTS.md` (cloud section).
**Subtasks:**
1. `infra_m0b.sh` (owner runs): bucket, two service accounts and their roles, the job with the bucket
   mounted at `/mnt/data`, two Cloud Scheduler triggers (dossier §5.10), a job-failure email alert.
2. `rollout.py`: after publish, set the API service's `SNAPSHOT_VERSION` env var through the Cloud
   Run Admin API (REST + `google-auth`), so Cloud Run starts a new revision. Mocked HTTP tests.
3. `deploy.yml`: build once; deploy the service and update the job to the same image; service gets
   the mount (read-only) and `SNAPSHOT_PATH` unset. Job memory 4 GiB (spike §4).
4. Owner runs the first cloud full build (`--archive all_json`) and one nightly run.
5. Measure API query latency on the mount (same five queries as M0b.1). Rule D-3: mount if p95
   < 300 ms, else bake the snapshot into the image (then extend `deploy.yml`).
**Verify:** job execution succeeds; `gcloud storage cat gs://cricpulse-data/snapshots/LATEST.json` shows the
new version; `GET /ready` on the service reports it; `python -m pytest tests/test_rollout.py -q` → pass.
**Depends:** M0b.8, M0b.1

---

### M0b.11 — UAT and review hand-off
**Goal:** The owner sees the module work end to end; a fresh session reviews it.
**Owns:** `scripts/run_uat.py` (M0b journeys), `docs/uat/M0B-UAT.md` (new), `README.md` (job usage).
**Subtasks:**
1. Add journeys U-1 … U-4 (dossier §8) to `run_uat.py` where they can be automated; script the rest.
2. Record results in `docs/uat/M0B-UAT.md`; the owner signs.
3. Hand the branch to a fresh review session → `docs/reviews/M0B-REVIEW.md`.
**Verify:** UAT file complete and signed; review file exists with a verdict.
**Depends:** M0b.10
