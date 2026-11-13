# BLOCKED — Handoff: M0b.10 (A)
- Branch / checkout: `feat/M0b-trustworthy-data-pipeline` · main checkout `/Users/mrrobot/Desktop/Projects/cricpulse` (HEAD `b0ea331`). `git rev-parse --show-toplevel` printed this path before anything else.
- State: blocked. I changed no source, test, script or workflow file. The only new file is this note.
- Colour: 🔴 (red zones the task touches: `src/config.py`, `src/publisher/` (the run), and paths under `settings.data_dir`)

## Conflict — the API cannot start on the read-only bucket, so owner step 9 fails
- **What the card asks for** (subtask 7): the service mounts the bucket read-only at `/mnt/data`, with `DATA_DIR=/mnt/data`. The bench job mounts it the same way (D-13e).
- **What the code does:**
  - `src/api/app.py:83` builds the app when the module is imported, and `:24` calls `get_settings()`.
  - `get_settings()` (`src/config.py:66-70`) always calls `ensure_directories()`.
  - `ensure_directories()` (`:52-63`) creates `published/`, `bronze/`, `silver/`, `snapshots/`, `runs/` and `tmp/` under `DATA_DIR`.
  - On a read-only mount, creating a folder that is not there raises an error, so the API stops before it serves anything. The bench job, which runs `bench` in `main.py`, gets the same error.
- **When the folders are missing:**
  1. **Step 9, every time.** Step 8 (`setup`) creates an empty bucket. Step 9 deploys the service before any run has written to the bucket, so the deploy fails and the workflow goes red. Step 10's first build would create the folders, but it comes after step 9.
  2. **Every start, as the card is written.** The job writes its scratch to `TMP_DIR=/tmp/cricpulse`, so nothing ever creates `tmp/` in the bucket. The card gives the service no `TMP_DIR`, so its default is `/mnt/data/tmp`.
- **Shown locally** with a folder made non-writable to stand in for the read-only mount (the scratch folder was deleted afterwards):
  ```
  1. empty read-only DATA_DIR (bucket before first build) -> PermissionError [Errno 13] Permission denied: '…/mnt_data/published'
  2. job's dirs present, tmp/ never on the bucket -> PermissionError [Errno 13] Permission denied: '…/mnt_data/tmp'
  3. same, TMP_DIR off the mount -> ok
  ```
  On the real mount the error would be "read-only file system" rather than "permission denied". Python's `mkdir(exist_ok=True)` raises either one when the folder is missing.
- **Problem 2 needs no ruling.** Setting `TMP_DIR=/tmp/cricpulse` on the service and the bench job is in Owns (`deploy.yml`) and follows dossier §5.9, which puts `tmp_dir` at `/tmp/cricpulse` in the cloud. The next build does it either way.
- **Problem 1 needs a ruling.** Every fix either changes `src/config.py` beyond the card's "one setting" or works around the problem:
  - **A (recommended):**
    - `get_settings()` stops creating folders.
    - `main.py`'s `run` and `ingest-local` call `settings.ensure_directories()` themselves. `main.py` is already in Owns.
    - The API only reads. Its fallback already checks `.exists()`, and `bench` creates nothing.
    - Card change: widen Owns to `get_settings` in `src/config.py`. Add one test that `get_settings()` creates nothing, and one that `run` on a bare data dir still publishes.
    - What relies on folders existing today: the run's build DB in `tmp_dir` (`main.py:147`) and its report in `runs_dir` (`main.py:181`). Both are covered by the `main.py` call. The downloaders, `silver`, `archive`, `manifest`, the publisher and `write_latest` each create their own folder.
  - **B:** `ensure_directories()` skips any folder it cannot create. This also needs `src/config.py`, and it hides real errors on a writable disk.
  - **C (workaround, in Owns):** `infra_m0b.sh setup` writes empty folder markers into the bucket before step 9. It is fragile: the API dies at start whenever a marker is missing. It also depends on how the mount lists folders, which no local test can check.

## Settle in the same pass (each one changes what the owner grants or sees)
1. **Permissions before the service and the job exist.**
   - The problem: `setup` (step 8) runs before `deploy.yml` creates the service and the job (step 9). The job's "permission to roll out the API" (§5.10) and the schedules' permission to start the job cannot be granted on resources that do not exist yet.
   - **Recommendation:**
     - Grant the job's account `roles/run.developer` for the whole project, plus `roles/iam.serviceAccountUser` on the API's account.
     - The two schedules run as the job's account. `run.developer` also lets them start the job with the Sunday `--archive all_json` override.
   - The cost: the job can change any Cloud Run resource in the project.
   - The alternative: grant these on the service and the job inside `deploy.yml` after creating them. The deploy account would then need permission to set IAM policies.
2. **The API's account needs `roles/secretmanager.secretAccessor` on `GEMINI_API_KEY`.** Subtask 7 keeps the key in Secret Manager, but §5.10 gives the API only "object viewer". Without this role, Cloud Run refuses the step 9 deploy. The next build adds it in `setup` unless you rule otherwise.
3. **Should the rollout wait for the new revision?** (D-13a: "a failed rollout exits non-zero")
   - As carded, the rollout returns as soon as Cloud Run accepts the change.
   - If the new revision then fails to start, the API stays on the old snapshot while the job reports success. The next run finds `SNAPSHOT_VERSION` already equal and does nothing. That is the silently stale API D-13a set out to prevent.
   - **Recommendation:** wait for the update to finish and exit non-zero if it fails. Count "equal" only when the newest revision is also ready. Two more tests in `tests/test_rollout.py`.
   - Or accept the gap as carded.
4. **Watch at step 10, no ruling needed.**
   - On Cloud Run, `/tmp` is held in memory. The build DB and DuckDB's spill folder (`TMP_DIR=/tmp/cricpulse`) count against the job's 4 GiB, on top of `memory_limit=2GB`. The spike measured on a real disk.
   - If the first build is killed for memory, the fix is 8 GiB or a lower `memory_limit`.

- What changed: nothing. The only new file is `.agents/handoffs/M0b.10.md`.
- Verification run: the card's Verify, exact, on today's tree with nothing changed:
  ```
  source .venv/bin/activate && ruff check src tests && ruff format --check src tests && python -m pytest tests/test_rollout.py tests/test_pipeline.py tests/test_config.py tests/test_api_and_agents.py -q && python -m pytest -q && bash -n scripts/infra_m0b.sh && PROJECT_ID=demo-project ALERT_EMAIL=alerts@example.com DEPLOYER_SA=deployer@demo-project.iam.gserviceaccount.com bash scripts/infra_m0b.sh --dry-run setup && python -m src.publisher.main bench --help && python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))" && ! grep -n "GCS_BUCKET\|SYNC_SECRET_TOKEN" .github/workflows/deploy.yml; echo "VERIFY EXIT $?"
  ```
  - `ruff check`: "All checks passed!" `ruff format --check`: "56 files already formatted".
  - pytest: "ERROR: file or directory not found: tests/test_rollout.py", no tests ran. **VERIFY EXIT 4.** Nothing is built, so it cannot pass.
  - The full suite run on its own, before this note: `python -m pytest -q` gave **121 passed, 2 skipped**, 1 warning that was already there.
- Done-when lines met: none. Subtasks 1–7 are not started, and steps 8–12 belong to the owner after landing.
- Proof:
  - A user can do nothing new yet: the nightly cloud job, the API catching up with each new snapshot, and `/ready` naming its snapshot are not built.
  - Works: stopped early. The API as carded could not start on the read-only cloud storage, so the owner's deploy (step 9) would fail.
  - Next: the governor rules on the fix (A recommended) and items 1–3, widens the card, and starts the builder again.
  - Colour 🔴, output only (no screen changes).
- Followed the code, not the card: none, because nothing was built. For the next build:
  - `Dockerfile` needs no change. Its default command already runs `python -m src.publisher.main run`, and `deploy.yml` starts the service with `uvicorn` on port 8080, as docker-compose's `api` service does.
  - `deploy.yml`'s job is named `cricpulse-ingest-job` today. The card's `cricpulse-ingest` will replace it.
  - The bench's players from `spike.py` (V Kohli, JJ Bumrah, SPD Smith) are not in the fixture build, so the fixture test will name fixture players.
- Open issues / decisions needed: the conflict (A, B or C) and items 1–3 above.
- Proposed commit: `docs(M0b): M0b.10 blocked — the API creates folders at start and cannot on the read-only mount; note kept [M0b.10]` — trailer `Module: M0b.10`
