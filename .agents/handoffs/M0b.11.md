# Handoff: M0b.11 (A)
- Branch / checkout: feat/M0b-trustworthy-data-pipeline, /Users/mrrobot/Desktop/Projects/cricpulse
- State: done (builder subtasks 1-3; 4 owner, 5 governor)
- Colour: 🟡

- What changed:
  - `scripts/run_uat.py`: opens the snapshot LATEST.json names via `create_app()`; no LATEST.json -> "no snapshot yet..." exit 1; no fixture DB; sync scenario replaced by "/ready names the LATEST.json version".
  - `docs/uat/M0B-UAT.md` (new): U-1..U-4 with commands; U-1, U-2, U-3 (script) results recorded; U-4 "waits for the deploy (D-15)"; sign-off blank.
  - `README.md`: "Running the job locally" section.
  - Real `data/` now holds snapshot v20261112T1216Z (ignored by git); `data/silver.failed-20261112/` untouched.
- Verification run: `source .venv/bin/activate && ruff check src tests scripts/run_uat.py && ruff format --check src tests scripts/run_uat.py && python -m pytest -q && python scripts/run_uat.py && test -f docs/uat/M0B-UAT.md && grep -q "U-4" docs/uat/M0B-UAT.md`
  run with `GEMINI_API_KEY=` exported (mock model): ruff clean, 60 files formatted, 146 passed 2 skipped, run_uat 8/8 PASS, files present. Exit 0.
  WITHOUT that override the same command exits 1: the key in `.env` gets 401 from OpenRouter, so scenarios 4-7 fail (environment, not code).
- Done-when lines met: "1-3 landed": built and verified, waits for kura to land. Owner signature: not met (subtask 4, owner). M0B-REVIEW.md verdict: not met (subtask 5, governor).
- Proof: output only (no screen changed). U-1: 23,241 files, 23,239 published, 2 quarantined (D-16c), 11,739,043 deliveries, 449,851,392-byte snapshot, 10 min 24 s, all gates passed. U-2: "Up to date", 6.7 s, count unchanged. run_uat: 8 of 8 on v20261112T1216Z, mock model.
- Followed the code, not the card: file count 23,241 (not 22,818); the model switches to mock only when the key is empty or APP_ENV=test (src/ai/gemini_client.py), so the Verify command needs `GEMINI_API_KEY=` here; sync scenario dropped (endpoint removed in M0b.9), replaced by /ready check.
- Open issues / decisions needed: (1) the `GEMINI_API_KEY` in `.env` is rejected (401): owner must supply a working key before the live U-3 chat question, or accept mock; Verify as written needs a working key or an empty one. (2) `08_AGENTIC_GENAI_REBUILD_BRAINSTORM.md` untracked, not mine. (3) Downloader buffers 149 MB and re-fetches every full run.
- Proposed commit: `docs(uat): UAT script on LATEST.json, M0B-UAT.md with U-1/U-2 results, local-run README [M0b.11]` — trailer `Module: M0b.11`
