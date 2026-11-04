# BLOCKED — Handoff: M0b.7 (B)
- Branch / worktree: `feat/M0b-lane-b` · `/Users/mrrobot/Desktop/Projects/cricpulse-M0b-b` (HEAD `ef9a7d8`)
- State: blocked. No source or test file was changed.
- **The conflict: the task needs a constant that lives in a lane A file.**
  - Card subtask 1: `SnapshotPublisher.publish(temp_db, version) -> LatestInfo`.
  - `LatestInfo.parser_version: int` is required (`src/snapshot.py:20`). Dossier §5.7 shows `"parser_version": 1` in `LATEST.json`.
  - `publish()` has to fill that field. The card lists what it reads from the file (sha256, counts, `data_cutoff`) but not where `parser_version` comes from.
  - The only source is `PARSER_VERSION = 1` in `src/parsers/match_parser.py`. Dossier §6 assigns that file to M0b.3 (lane A).
  - That constant is in commit `86d786b` on `feat/M0b-trustworthy-data-pipeline`, but not on `feat/M0b-lane-b`. On this branch, `grep -rni "PARSER_VER" src conf tests scripts` finds nothing.
  - The card says M0b.7 depends only on M0b.6. In practice it also depends on M0b.3.
  - `sensei` rule: "A task needs another lane's file → a wave-0 change or a new task, never a workaround."
  - Every workaround I found is a guess. I rejected these:
    - **A local `PARSER_VERSION = 1` in `publisher.py`.** This makes a second source of truth. When M1 bumps the real constant (dossier R-5), `LATEST.json` would report a stale version.
    - **A `try: import … except ImportError` fallback.** Same defect, but hidden.
    - **Adding `PARSER_VERSION` to `match_parser.py` here.** That file is outside Owns, and it would collide with `86d786b` at lane merge.
    - **A `parser_version` argument on `publish()`.** This changes the card's signature. It also only moves the problem: `publish_snapshot`, which stays because `main.py` still calls it, would then need the constant itself.
- What changed: nothing except this note.
- Verification run (baseline, nothing changed, so this is today's code and not the card's work):
  - `python -m pytest tests/test_publisher.py -q` gave **1 passed**, exit 0.
  - `python -m pytest -q` gave **78 passed**, 1 warning (the Starlette `httpx` deprecation, already there), exit 0.
- Done-when lines met: none. The work was not started.
  1. `publish()`: not met (blocked, above).
  2. `prune()`: not met. It does not need `PARSER_VERSION`, but I did not build it alone, so the card lands whole.
  3. Removing the in-place copies and `export_gold_parquets`: not met.
  4. Tests: not met.
- Decision needed (the owner or `sensei`). **Recommended: before M0b.7, `kura` brings the module branch into lane B (merge `feat/M0b-trustworthy-data-pipeline`, which has M0b.3 and M0b.4), and the card's Depends becomes "M0b.6; M0b.3 in lane B".**
  - Then `publish()` imports `PARSER_VERSION` from `src.parsers.match_parser`, and there is one source of truth.
  - This is instead of a local constant or a new argument, because both make a second source that drifts.
  - Alternative: move M0b.7 to lane A after the lanes merge (it would then run before M0b.8 there).
- Notes for whoever builds M0b.7 after the ruling. These are not blockers.
  - `src/publisher/main.py:88` and `:165` call `export_gold_parquets`. Subtask 3 removes that method. Until M0b.8 rewrites `main.py`, `run` (where `--export-parquet` defaults to True) would raise `AttributeError` after publishing. No test runs `main.py`. M0b.8's Verify grep for `export_gold_parquets` catches it.
  - `publish_snapshot` still has callers (`main.py:84`, `:162`), so it stays. Without its in-place copies it has to hand over to `publish()`, which writes `LATEST.json`. For invariant 1 ("every gate before `LATEST.json`"), it must call `run_quality_gates(con, previous=read_latest(data_dir))`. Otherwise the never-shrink gates are skipped on that path.
  - M0b.6 note: `LatestInfo.match_count` and `delivery_count` must be raw `COUNT(*)` of `gold.dim_match` and `gold.fact_delivery`, which is what the shrink gates compare.
  - `scripts/run_uat.py:30` reads `published/cricket_latest.duckdb`. Once `publish_snapshot` stops writing that file, the harness reads a stale or missing file. That script belongs to M0b.11.
  - Same-minute re-runs give the same D-8 version. `publish()` should refuse an existing `snapshots/cricket_<version>.duckdb` rather than rename over a published file.
- Next step for whoever picks this up: `sensei` rules on the decision above, then re-issues the M0b.7 goal line on the updated lane.
- Proposed commit: none for code. If the governor wants this note kept: `docs(M0b): M0b.7 blocked on PARSER_VERSION from lane A [M0b.7]`, trailer `Module: M0b.7`.
  - Files: `.agents/handoffs/M0b.7.md`
