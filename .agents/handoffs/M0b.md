# M0b — Trustworthy data pipeline

**What it does:** a nightly job turns Cricsheet's files into a new, versioned DuckDB snapshot, and it can never
shrink, corrupt or empty the live data. The API serves whichever snapshot `snapshots/LATEST.json` names.

**PR title:** `feat(M0b): trustworthy data pipeline — versioned snapshots that never shrink, Silver + manifest, quality gates, error table, run lock`
**Target:** `dev` · **Branch:** `feat/M0b-trustworthy-data-pipeline` (code and gate at `95a1138`; this note is the last commit) · **Colour:** 🔴

## What changed, in the app's words

- **Every run is a new snapshot.** A run publishes `snapshots/cricket_<version>.duckdb` and then `LATEST.json`, and
  only after every quality gate passes. A failed run leaves the live snapshot and every published file untouched.
  The last 7 snapshots are kept.
- **Only changed files are read.** A Parquet Silver layer and a manifest (`silver/manifest.parquet`) replace the
  SQLite ledger. Each night reads the last 7 days, and each Sunday reads the full archive.
- **Live data never shrinks.** New gates refuse fewer matches or deliveries than the live snapshot, and refuse a run
  with too many bad files.
- **A bad file never stops the night.** A rejected file goes to an error table (`silver/quarantine.parquet`), and the
  run report names it. A match that a newer parser rejects leaves the app. A broken new revision keeps the last
  good one. A player listed twice for one team keeps one row; a player listed for both teams is set aside.
- **Runs are safe.** Only one run at a time (`run.lock`). A crash is finished by the next run. A retry after a failed
  gate fails again until someone fixes the cause. The Sunday run names matches the archive no longer has.
- **The API reads `LATEST.json`.** The sync endpoint and the hot swap are gone. `/ready` names the snapshot it serves.
- **Pushing is a session's job now; merging stays the owner's.** On the owner's yes, a session pushes the module
  branch, opens its pull request into `dev` and watches the checks. A new pre-push check refuses `dev` and `main`
  and runs ruff and the full test suite first. This pull request also carries the two Kaizen-roles commits that
  local `dev` held (`80fc40b`, `bc40b93`).
- **Cloud code is written but not deployed.** It covers the Cloud Run job, the two schedules, the bucket mount and the
  API rollout. It runs at the deploy, after the owner's final local testing (D-15).

## Definition of Done (`docs/04` §4)

| # | Gate | Evidence | Holds |
|---|---|---|---|
| 1 | Dossier approved | `docs/features/M0B-TRUSTWORTHY-DATA-PIPELINE.md`, decisions D-1 … D-18 | yes |
| 2 | All task cards landed | M0b.1 … M0b.17 committed on the module branch; lane B merged (`1584cb7`) | yes |
| 3 | `ruff` + `pytest` green | `ruff check` clean, `ruff format --check` 61 files, `pytest -q` **194 passed, 2 skipped** (the live cricsheet.org checks), exit 0, at `95a1138` | yes |
| 4 | Evaluation set | not yet (none before M2) | n/a |
| 5 | Review findings fixed | `docs/reviews/M0B-REVIEW.md`: CHANGES REQUIRED, then a fix round (D-18), then a second look: **PASS**. Findings left open on purpose are listed with their homes in the dossier §7.1 | yes |
| 6 | UAT passes; owner signs | `docs/uat/M0B-UAT.md`: U-1, U-2 and both re-runs passed on the real archive (`v20261112T1811Z`, 23,239 matches, 11,739,043 deliveries; `run_uat.py` 8/8 on the mock model). **U-3 and the signature wait for the owner.** U-4 waits for the deploy (D-15) | owner |
| 7 | Merged to `dev` by the owner | — | owner |
| 8 | Status says **Sealed** | `docs/04` §2, set after the merge | after 7 |

## Still the owner's

1. Put a working AI key in `.env`. The current one is rejected, so the live chat fails.
2. Start `bash scripts/run_local.sh`, then ask the U-3 question at http://127.0.0.1:8000/ui/. `/ready` should show
   `v20261112T1811Z`.
3. Sign `docs/uat/M0B-UAT.md`.
4. Say yes to the push. The governor pushes the branch, opens the pull request (the commands below) and watches the
   checks. Then merge it into `dev` in the GitHub web UI (AGENTS.md boundary 4, 13 Nov 2026).
5. Later, at the deploy (D-15): M0b.10's steps 8–12, UAT U-4, the D-3 bench, and the deploy items in the dossier §7.1.
   Merging into `main` is the deploy.

## Commands `kura` runs on the owner's yes

```bash
git push -u origin feat/M0b-trustworthy-data-pipeline
gh pr create --base dev --title "feat(M0b): trustworthy data pipeline — versioned snapshots that never shrink, Silver + manifest, quality gates, error table, run lock" --body-file .agents/handoffs/M0b.md
```
