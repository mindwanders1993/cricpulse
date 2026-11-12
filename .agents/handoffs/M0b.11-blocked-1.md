# Handoff: M0b.11 (A)
- Branch / checkout: feat/M0b-trustworthy-data-pipeline, /Users/mrrobot/Desktop/Projects/cricpulse
- State: blocked
- Colour: 🟡 (BLOCKED, see below)

## BLOCKED
Verify cannot pass as written. Subtask 2 has the builder run U-1 (`run --archive all_json`) on the real `data/`, and
`run_uat.py` needs the `LATEST.json` that run writes. U-1 failed at the quality gate on the real data:
`[player_match_grain_uniqueness] Duplicate (match_id, player_id) detected in fact_player_match (got: 2)`.
The run downloaded and parsed all 23,241 matches (0 quarantined), then the gate stopped it before publishing, so there is no
`data/snapshots/LATEST.json` and `python scripts/run_uat.py` exits 1 with "no snapshot yet". The fix is in
`src/` (Gold build / loader, and possibly the gate), which is outside Owns and a 🔴 zone. Not worked around.
Also note: the full archive is now 23,241 files, not the 22,818 the dossier's U-1 line says.

Needed from the governor: a fix card for the two duplicate (match_id, player_id) rows (which two matches is not yet
identified; query `fact_player_match` on a rebuilt Silver, `data/silver/` is already populated), then re-run U-1,
U-2, `run_uat.py` and fill in `docs/uat/M0B-UAT.md`. The zip is already in `data/bronze/cricsheet/2026-11-12/`
so the re-run need not redownload only if the downloader reuses it (it does not: it re-fetches, about 13 min at this
network speed).

- What changed:
  - `scripts/run_uat.py`: opens the snapshot LATEST.json names via `create_app()` with no path; no LATEST.json prints "no snapshot yet: run `python -m src.publisher.main run` first", exit 1; no fixture DB, no removed-module imports, writes nothing under `data/`; scenario 8 (sync webhook) replaced by "/ready snapshot_version equals LATEST.json's version" (U-3).
  - `docs/uat/M0B-UAT.md` (new): U-1..U-4 with commands and what to record; U-1 failure recorded; U-2/U-3 not run; U-4 "waits for the deploy (D-15)"; sign-off blank.
  - `README.md`: "Running the job locally" section (`run`, `ingest-local`, `bench`, `run_local.sh`, cloud steps at the deploy).
- Verification run: the full Verify command was not run as one line because it cannot pass. Pieces: `ruff check src tests scripts/run_uat.py` All checks passed; `ruff format --check src tests scripts/run_uat.py` 60 files already formatted; `python -m pytest -q` 144 passed, 2 skipped; `python scripts/run_uat.py` not run (no LATEST.json; by design it would exit 1); `test -f docs/uat/M0B-UAT.md` and `grep -q "U-4"` hold. Overall exit: not 0.
- Done-when lines met: "1–3 landed": 1 coded but not exercised against a snapshot; 2 written, results not recorded; 3 met. Owner signature and M0B-REVIEW.md: not met (later steps).
- Proof: output only. U-1 ran 13 min 27 s, 23,241 matches parsed, gate failed on 2 duplicate player rows, no snapshot. Not green.
- Followed the code, not the card: scenarios 1-7 kept (health/ready, two leaderboards, text-to-SQL, scout, story, chat router); only the sync scenario was dropped (endpoint removed in M0b.9). The U-1 count of 22,818 files is now 23,241.
- Open issues / decisions needed: the duplicate (match_id, player_id) rows (needs a `src/` fix card); `MatchDownloader` buffers the whole 149 MB archive in memory and re-downloads even when bronze has it (not a bug here, just slow); `data/silver/` and `data/bronze/` now hold this run's partial output (ignored by git); the scenarios in `run_uat.py` assert on T20 data (`match_type=T20`) which a real snapshot should have.
- Proposed commit: `docs(uat): UAT script on LATEST.json, M0B-UAT.md, local-run README (U-1 blocked on a gate failure) [M0b.11]`
