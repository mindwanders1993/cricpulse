---
name: invariants
description: The eight CricPulse invariants in full — never-shrinking live data, directory storage, Polars + DuckDB only, catalog-owned cricket arithmetic, one guarded door to the database, numbers from tool output, web text as data, secrets from settings. Loaded by build and review sessions; not in the / menu.
user-invocable: false
---

# `invariants` — the eight invariants

## 1. Live data never shrinks
- No code path writes `LATEST.json` until every quality gate (`run_quality_gates`) has passed on the new snapshot.
- Gate: the new snapshot's `dim_match` count is ≥ the live snapshot's, and `fact_delivery` is ≥ 0.999 × the live
  count (M0b dossier §5.6: a revised match may carry fewer balls); quarantine count is
  ≤ `max(5, 1%)` of the run's files (M0b D-5).
- Published files are written as `<name>.tmp` then renamed. Nothing is overwritten in place. Nothing is deleted
  before its replacement is live (M0b D-7 prunes afterwards).

## 2. Storage is a directory
- Everything under `settings.data_dir`: `bronze/`, `silver/`, `snapshots/`, `runs/`, `tmp/` (M0b dossier §5.2).
- Prohibited: `google.cloud.storage`, `gcsfs`, any bucket URL in code. In the cloud the bucket is mounted (M0b D-1).

## 3. Polars + DuckDB, scale to zero
- No Spark, Airflow, or always-on worker. The nightly job is a Cloud Run Job that starts, runs, exits.
- DuckDB builds run on local disk under `tmp/`, never on the mount.

## 4. Cricket arithmetic lives in the catalog
- `conf/semantic_catalog.yaml` defines every metric and dimension; `src/semantic/models.py` types them.
- Balls faced and legal balls exclude wides; no-balls count as balls faced but not legal balls. Bowling economy and
  average exclude byes and leg-byes. Batting average divides by dismissals, never by innings.
- A formula typed into Python or SQL that the catalog does not define is a defect (`catalog-first`).

## 5. One door to the database from a request
- Request-path SQL goes through `src/ai/guardrails.py`: `sqlglot` AST, `SELECT`/CTE only, `gold.*` allowlist,
  row limit, timeout, read-only connection to an immutable snapshot.
- No `duckdb.connect` outside the snapshot loader; no f-string SQL with user text.

## 6. Every number in an answer appears in a tool's output (TR-1, from M3)
- The checker compares the draft against tool outputs; one regeneration, then a numbers-only fallback.
- The receipt names the query, the row count, the data cutoff and the sources.

## 7. Web text is data, never instructions, never a historical number (TR-3)
- Search, when it exists (R3), supplies only live inputs: toss, playing XI, weather, injuries.
- Fetched text is wrapped as data in the prompt; a historical statistic from the web is discarded.

## 8. Secrets come from settings
- Keys and tokens only via `src/config.py`. Never in code, logs, fixtures, test names or commit messages.
- Mock mode when a key is unset, so the suite runs offline.
