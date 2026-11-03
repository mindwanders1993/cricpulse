# M0b — Trustworthy Data Pipeline · Module Dossier

**Status:** Approved by the owner, 26 Oct 2026 (D-1 … D-8 as recommended) · **Date:** 26 Oct 2026
**Release:** R0 "Make it correct" · **Branch:** `feat/M0b-trustworthy-data-pipeline` from `dev`
**Contract for:** `M0B-TASK-CARDS.md`. Where a card and this dossier disagree, this dossier wins.

---

## 0. At a Glance

| | |
|---|---|
| **Goal** | A nightly job that turns Cricsheet files into a new, versioned DuckDB snapshot — and can never shrink, corrupt or empty the live data. |
| **Fixes** | Blocking bugs 1 and 2 from `08 §9`, and the data half of bug 3. |
| **Done when** | (1) Two runs in a row never lose a match. (2) A bad file or a failed gate leaves the live snapshot untouched. (3) The job runs on Cloud Run and the API serves its snapshot. |
| **Size** | 11 tasks, in two lanes |
| **Risk** | Memory and time of the first full build — measured first (M0b.1) |

---

## 1. Scope

**In**
- Ingestion as a standalone job (local CLI and Cloud Run Job).
- Silver layer (Parquet) + manifest, replacing the SQLite ledger.
- Full Gold rebuild from Silver on every run.
- New quality gates: never shrinks, keys unique, quarantine bounded.
- Versioned, atomic publish + `LATEST.json` + retention.
- API reads the snapshot that `LATEST.json` names; the sync endpoint and the hot swap are removed.
- Cloud setup: job, schedule, storage mount, snapshot delivery to the API.

**Out (other modules)**
- Cricket-correctness parser fixes, `snapshot_info`, venue ids, mart fixes → **M1**.
- Refusing to start without a snapshot, cursor per request, SQL hardening, `uv` → **M0a**.

---

## 2. What It Covers

| Document | Items |
|---|---|
| PRD | TR-9; R0 |
| HLD | §4 nightly flow, §5.1–5.2 layers and layout, ADR-2, ADR-3, ADR-4, ADR-10 |
| LLD | §2.1–2.5, §6.1 (sync endpoint removed), §8.2 (job, retention) |

---

## 3. Today vs Target

```
TODAY                                              TARGET
─────                                              ──────
API endpoint /internal/sync-daily                  Cloud Run Job (separate process)
  download → extract all files to disk               download zip → bronze/
  ledger (SQLite, ephemeral disk) filters            manifest (Parquet, in storage) diffs
  parse ONLY changed files                           parse only changed files (from the zip)
  build Gold from ONLY those files   ◀── BUG 1       merge into Silver → build Gold from ALL Silver
  gates                                              gates + never-shrinks vs previous
  copy2 over cricket_latest.duckdb   ◀── BUG 2       write new versioned file → write LATEST.json
  close + reopen live connection     ◀── BUG 2       new API revision on the new snapshot
  (no data in the deployed image)    ◀── BUG 3       API loads the snapshot named by LATEST.json
```

---

## 4. Decisions

| # | Question | Recommendation | Alternative | Owner's ruling |
|---|---|---|---|---|
| D-1 | How does the job reach GCS? | **Storage is just a directory (`DATA_ROOT`).** Locally `./data`; in the cloud, the bucket is mounted at `/mnt/data` with Cloud Storage FUSE. No GCS SDK code. | A small storage adapter on `google-cloud-storage` | Approved as recommended, 26 Oct |
| D-2 | Which Cricsheet archive each night? | **`recently_added_7_json` nightly + `all_json` every Sunday** (full reconcile). Seven days survives a few failed nights. | `recently_added_2_json` only (today) | Approved as recommended, 26 Oct |
| D-3 | How does the API get the snapshot? (ADR-4) | **Decide by measurement in M0b.10.** Default: read-only on the mount if a typical query is < 300 ms p95; else bake it into the image. | Copy to local disk at start | Approved as recommended, 26 Oct |
| D-4 | What happens to `src/ledger.py`? | **Delete it** (and its tests and the `ledger` arguments). The manifest replaces it. Registers are re-parsed every run (two small CSVs). | Keep it beside the manifest | Approved as recommended, 26 Oct |
| D-5 | A match file fails to parse | **Quarantine it and continue.** The run fails only if more than `max(5, 1%)` of its files fail. | Fail the whole run (today) | Approved as recommended, 26 Oct |
| D-6 | `export_gold_parquets` | **Remove it.** Silver is now the Parquet layer. | Keep behind a flag | Approved as recommended, 26 Oct |
| D-7 | Retention | **Keep 7 snapshots and 30 days of raw zips;** the job prunes older ones. | GCS lifecycle rules | Approved as recommended, 26 Oct |
| D-9 | Match id (spike §3: two files collide today) | **File stem, `wi_` prefix kept**; Silver → Gold uses plain `INSERT` so a duplicate fails loudly | Strip the prefix (today — loses a match) | Proposed — from the spike |
| D-10 | Primary keys on Gold fact tables (spike §2.3) | **Drop them**; uniqueness stays a quality gate; dimension keys stay. Snapshot 1.1 GB → 0.4 GB, memory 5.5 → 2 GB, same query speed | Keep them | Proposed — from the spike |
| D-8 | Snapshot version name | **`v20261026T0230Z`** (UTC, sortable, one per run) | Date only (collides on re-runs) | Approved as recommended, 26 Oct |

---

## 5. Design

### 5.1 The run, step by step

```
python -m src.publisher.main run [--archive all_json] [--reparse-all]

 1  version = now_utc("v%Y%m%dT%H%MZ")
 2  download registers  → bronze/registers/<date>/{people,names}.csv
 3  download archive    → bronze/cricsheet/<date>/<archive>.zip
 4  for each .json member of the zip (no extraction to disk):
        sha = sha256(bytes); id = file stem (D-9)
        if manifest says (id, sha, PARSER_VERSION) is current → skip
        try parse_json(id, orjson.loads(bytes)) → staging batch
        except → quarantine(id, error)
        every 1,000 matches → write staging Parquet parts (bounded memory)
 5  if nothing changed and registers unchanged → stop, exit 0 ("up to date")
 6  merge staging into Silver, table by table (§5.4)
 7  write the new manifest
 8  build Gold from ALL Silver into tmp/<version>.duckdb (§5.5)
 9  run quality gates against the previous LATEST.json (§5.6)
10  publish: snapshots/<version>.duckdb, then LATEST.json (§5.7)
11  prune old snapshots and zips; write runs/<version>.json (run report)
```

A failure at any step before 10 leaves `LATEST.json` and every published snapshot untouched.

### 5.2 Storage layout under `DATA_ROOT`

```
bronze/registers/<YYYY-MM-DD>/{people,names}.csv
bronze/cricsheet/<YYYY-MM-DD>/<archive>.zip
silver/<table>.parquet            # matches, innings, deliveries, wickets, match_players
silver/manifest.parquet
silver/_staging/<version>/<table>/part-<n>.parquet   # deleted after merge
snapshots/cricket_<version>.duckdb
snapshots/LATEST.json
runs/<version>.json
tmp/                              # local scratch only — never on the mount
```

`tmp/` is the job's local disk (`TMP_DIR`), because DuckDB must build its file on a normal filesystem,
not on a FUSE mount.

### 5.3 Manifest

| Column | Type | Rule |
|---|---|---|
| `match_id` | VARCHAR, unique | file stem, `wi_` kept (D-9) |
| `file_sha256` | VARCHAR | of the JSON bytes |
| `revision` | INTEGER | `meta.revision` from the file |
| `parser_version` | INTEGER | `PARSER_VERSION` at parse time |
| `version` | VARCHAR | the run that parsed it |

- **Parse when:** the id is new, **or** the sha changed, **or** `parser_version < PARSER_VERSION`, **or** `--reparse-all`.
- **Never delete** a match because it is missing from an archive. A Sunday full run logs ids present in
  the manifest but absent from `all_json`; a person decides.
- `PARSER_VERSION` lives in `src/parsers/match_parser.py`. M1 bumps it to re-parse everything.

### 5.4 Silver merge (DuckDB, streaming, bounded memory)

```sql
COPY (
    SELECT * FROM read_parquet('silver/deliveries.parquet')
    WHERE match_id NOT IN (SELECT match_id FROM read_parquet('<staging>/matches/*.parquet'))
    UNION ALL BY NAME
    SELECT * FROM read_parquet('<staging>/deliveries/*.parquet')
) TO 'silver/deliveries.parquet.tmp' (FORMAT PARQUET, COMPRESSION ZSTD);
-- then rename .tmp → final
```
- First run: no Silver file yet → staging only.
- `match_id NOT IN` uses the set of **all re-parsed** matches, so a match that loses an innings on
  revision loses those rows too.

### 5.5 Gold from Silver
`DuckDBLoader.build_from_silver(silver_dir, register_dfs)`:
- `INIT_SCHEMA_SQL`, with **no primary keys on fact tables** (D-10).
- Plain `INSERT` everywhere in this build — never `INSERT OR REPLACE` — so a duplicate fails loudly (D-9).
- Registers loaded as today (`load_registers`).
- Each Gold fact/dim filled with `INSERT … SELECT … FROM read_parquet('silver/<table>.parquet')` —
  the same column mapping as `load_matches` today, read from Parquet instead of DataFrames.
- `dim_venue` and `dim_team` derived as today (M1 changes venue ids).
- `build_marts()` as today.

### 5.6 Quality gates (added to `run_quality_gates`)

| Gate | Rule | Needs |
|---|---|---|
| `never_shrinks_matches` | `match_count ≥ previous.match_count` | previous `LATEST.json` (skipped on the first run) |
| `never_shrinks_deliveries` | `delivery_count ≥ 0.999 × previous.delivery_count` | same |
| `quarantine_bounded` | quarantined ≤ `max(5, 1% of the run's files)` | run state |
| existing seven gates | unchanged | — |

`run_quality_gates(con, previous: LatestInfo | None, quarantined: int, files_seen: int)`.

### 5.7 Publish protocol (atomic by construction)

```
copy tmp/<version>.duckdb  → snapshots/cricket_<version>.duckdb.tmp → rename (drop .tmp)
compute sha256 of the published file
write snapshots/LATEST.json.tmp → rename to LATEST.json
prune: keep the newest 7 snapshots (never the one LATEST names)
```

`LATEST.json` (illustrative values):
```json
{
  "version": "v20261026T0230Z",
  "path": "snapshots/cricket_v20261026T0230Z.duckdb",
  "sha256": "…",
  "match_count": 22817,
  "delivery_count": 11500000,
  "data_cutoff": "2026-10-25",
  "parser_version": 1,
  "created_at": "2026-10-26T02:41:07Z"
}
```
`data_cutoff` = latest `match_date` in `dim_match`.

### 5.8 API side
- New `src/snapshot.py`: `resolve_snapshot_path(settings) -> Path`.
  Order: `SNAPSHOT_PATH` env if set → else `DATA_ROOT/LATEST.json`'s `path`.
- `src/api/app.py` lifespan calls it. (Refusing to start when it is missing is **M0a**; until then the
  current fallback stays.)
- **Removed:** `src/api/routes/internal.py`, `src/api/auth.py`, `SyncDailyResponse`, the
  `sync_secret_token` setting, the router include in `app.py`.

### 5.9 Settings (`src/config.py`)

| Setting | Default | Note |
|---|---|---|
| `data_dir` | `data` | Stays as `DATA_ROOT` (`/mnt/data` in the cloud) |
| `tmp_dir` | `data/tmp` | Local scratch; `/tmp/cricpulse` in the cloud |
| `snapshot_path` | empty | Optional override for the API |
| `nightly_archive` | `recently_added_7_json` | D-2 |
| `keep_snapshots` / `keep_raw_days` | `7` / `30` | D-7 |
| removed | `sync_secret_token`, `ledger_db_path`, `parquet_dir`, `raw_match_dir` | no longer used |

### 5.10 Cloud (owner runs the `gcloud` commands; the card lists them)

| Piece | Setting |
|---|---|
| Bucket | `cricpulse-data`, single region (same as Cloud Run) |
| Job `cricpulse-ingest` | Image = API image, command `python -m src.publisher.main run`; **4 GiB**, DuckDB `memory_limit=2GB` + spill dir (spike §4); 1 task; max retries 1; timeout 60 min; bucket mounted at `/mnt/data` |
| Schedules | Nightly 02:00 IST (`recently_added_7_json`); Sunday 03:00 IST (`--archive all_json`) |
| Service account | Job: object admin on the bucket + permission to roll out the API. API: object viewer. |
| API rollout | After publish, the job updates the service's `SNAPSHOT_VERSION` env var → Cloud Run starts a new revision |
| API snapshot access | D-3, decided in M0b.10 |

---

## 6. Files Touched

| File | Change | Task |
|---|---|---|
| `docs/features/M0B-SPIKE-RESULTS.md` | NEW: measurements | M0b.1 |
| `src/config.py` | settings per §5.9 | M0b.2 |
| `src/publisher/manifest.py` | NEW | M0b.2 |
| `src/ledger.py`, `tests/test_ledger.py`, `tests/conftest.py` (ledger fixture) | DELETED | M0b.2 |
| `src/downloaders/*.py` | drop ledger args; write to `bronze/<date>/` | M0b.3 |
| `src/publisher/archive.py` | NEW: stream zip members, diff, parse, quarantine, staging | M0b.3 |
| `src/parsers/match_parser.py` | `PARSER_VERSION = 1`; match id = file stem (D-9) | M0b.3 |
| `src/builder/schema.py` | fact tables without primary keys (D-10) | M0b.5 |
| `src/publisher/silver.py` | NEW: merge | M0b.4 |
| `src/builder/loader.py` | `build_from_silver` (`load_matches` stays — tests build fixture DBs with it) | M0b.5 |
| `src/publisher/quality_gates.py` | new gates + signature | M0b.6 |
| `src/publisher/publisher.py` | versioned publish, `LATEST.json`, prune; remove `export_gold_parquets` | M0b.7 |
| `src/publisher/main.py` | new `run`; `ingest_local` reuses the same path | M0b.8 |
| `tests/test_pipeline.py` | NEW: multi-run integration | M0b.8 |
| `src/snapshot.py`, `src/api/app.py`, `src/api/routes/internal.py`, `src/api/auth.py`, `src/api/schemas.py` | §5.8 | M0b.9 |
| `Dockerfile`, `.github/workflows/deploy.yml`, `scripts/infra_m0b.sh` | job + schedule + mount | M0b.10 |
| `src/publisher/rollout.py` | NEW: bump the API's `SNAPSHOT_VERSION` via the Cloud Run Admin API (REST) | M0b.10 |
| `scripts/run_uat.py`, `docs/uat/M0B-UAT.md` | UAT | M0b.11 |

**Overlap with M0a:** both touch `src/api/app.py` (M0b: one line to call the resolver; M0a: start-up
refusal and cursors). Whichever lands second rebases.

---

## 7. Risks and Open Questions

| # | Risk / question | Plan |
|---|---|---|
| R-1 | First full build too slow or too big for the job | **Resolved by M0b.1:** 65 s; ~2 GB peak with D-10; snapshot ~0.4 GB |
| R-2 | DuckDB on a FUSE mount is slow | Never build on the mount (§5.2 `tmp/`); API access decided by measurement (D-3) |
| R-3 | Cricsheet archive names differ from what we expect | M0b.3 checks each archive URL with a HEAD request in a test against the live site (marked, skipped in CI) |
| R-4 | A Cricsheet revision removes a whole match | Never-delete rule + Sunday absence log |
| R-5 | Silver schema drift when M1 adds columns | `UNION ALL BY NAME`; M1 bumps `PARSER_VERSION` to rebuild Silver |
| Q-1 | Should a failed nightly run alert someone? | Proposed: Cloud Run job failure → email alert (free). Confirm in M0b.10. |

---

## 8. Test and UAT Plan

**Automated (`tests/test_pipeline.py`, fixtures zipped at test time):**
1. First run with T20 + Test fixtures → 2 matches; `LATEST.json` written.
2. Second run, same zip → "up to date"; nothing published.
3. Third run, the T20 file edited (one run changed) → still 2 matches; the edit is visible; new version.
4. Fourth run, an archive with only the Test match → still 2 matches (**never shrinks**).
5. Run with a broken JSON among 200 files → quarantined; run publishes.
6. Gate forced to fail → `LATEST.json` and old snapshots byte-identical.
7. `resolve_snapshot_path` picks `SNAPSHOT_PATH`, else `LATEST.json`.

**UAT journeys (`docs/uat/M0B-UAT.md`, owner walks them):**
- U-1 Full local build on all 22,818 files → match count, size, time recorded.
- U-2 Incremental local run → counts never drop; `runs/<version>.json` readable.
- U-3 API on the new snapshot → `/ready` and a chat question answer from it.
- U-4 Cloud: job run → new `LATEST.json` in the bucket → API revision serves the new version.

---

## 9. Task Summary

| Task | Title | Lane |
|---|---|---|
| M0b.1 | Spike: measure the full build and query speed — **Done**, `M0B-SPIKE-RESULTS.md` | A |
| M0b.2 | Settings + manifest; delete the ledger | A |
| M0b.3 | Archive reader: stream, diff, parse, quarantine | A |
| M0b.4 | Silver merge | A |
| M0b.5 | Gold from Silver | A |
| M0b.6 | Quality gates: never shrinks, quarantine bounded | B |
| M0b.7 | Publish: versioned file, `LATEST.json`, prune | B |
| M0b.8 | Pipeline entry + multi-run integration test | A |
| M0b.9 | API reads `LATEST.json`; remove sync endpoint and hot swap | B |
| M0b.10 | Cloud: job, schedule, mount, rollout; settle D-3 | A (with owner) |
| M0b.11 | UAT + review hand-off | A |

Cards with subtasks and Verify steps: `M0B-TASK-CARDS.md`.
