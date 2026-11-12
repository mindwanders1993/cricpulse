# Handoff: M0b.10 (A)
- Branch / checkout: `feat/M0b-trustworthy-data-pipeline` · main checkout `/Users/mrrobot/Desktop/Projects/cricpulse` (HEAD `ff9beae`). `git rev-parse --show-toplevel` printed this path before anything else.
- State: done (builder subtasks 1–7). The owner's cloud steps 8–12 come after landing.
- Colour: 🔴. The change is inside red zones: `src/publisher/` (the run, the rollout, the bench) and `src/config.py`.

## What changed
- `src/config.py`: new `rollout_service: str = ""` setting (D-13a). `get_settings()` no longer creates folders (D-14a).
- `src/publisher/rollout.py` (new): `ensure_api_on(version, settings)`. It reads the API service through the Cloud Run Admin API v2 over `httpx`, with a token from the metadata server (D-13b). When `SNAPSHOT_VERSION` differs, it writes the service back with only that env var changed. It then waits, with a 600 s limit, until the new revision is ready, and raises if it is not (D-14c). An empty `rollout_service` does nothing.
- `src/publisher/bench.py` (new): the five spike questions in the card's order, 20 warm runs each, p50 and p95, and the verdict `mount` or `bake` (D-3, D-13e).
- `src/publisher/main.py`:
  - `run` and `ingest-local` call `settings.ensure_directories()` themselves (D-14a).
  - After every `run` that publishes or stops "up to date", `run` calls the rollout with `LATEST.json`'s version.
  - A rollout error prints the reason and exits 1. `LATEST.json` stays written.
  - New `bench` command.
- `src/api/app.py`: keeps `snapshot_version` in `app.state`, taken from `cricket_<version>.duckdb`; None for the in-memory fallback.
- `src/api/routes/health.py`, `src/api/schemas.py`: `/ready` returns `snapshot_version`.
- `scripts/infra_m0b.sh` (new): the subcommands `setup`, `first-build`, `bench`, `status` and `open`, plus `--dry-run`. It reads `PROJECT_ID`, `REGION` (default `us-central1`), `ALERT_EMAIL`, `DEPLOYER_SA` and `BUCKET` (default `cricpulse-data`) from the environment.
  - `status` calls `/ready` with the owner's identity token (`gcloud auth print-identity-token`), because the service is private.
  - `open` runs `gcloud run services proxy cricpulse-api --port=8080`, so the owner uses the chat page at `http://localhost:8080/ui/`.
  *(Landing audit, after the first handoff.)*
- `.github/workflows/deploy.yml`: builds one image, then creates or updates three things on it:
  - the API service: **private (`--no-allow-unauthenticated`)**, bucket mounted read-only at `/mnt/data`, `DATA_DIR`, `TMP_DIR=/tmp/cricpulse`, at most 2 instances, `SNAPSHOT_PATH` unset;
  - the job `cricpulse-ingest`: 4 GiB, 1 task, 1 retry, 60 min, `ROLLOUT_SERVICE` set;
  - the bench job `cricpulse-bench`: the API's account, memory and CPU, bucket read-only.
  - `GCS_BUCKET` and `SYNC_SECRET_TOKEN` are gone. `GEMINI_API_KEY` still comes from Secret Manager.
  - The bucket name comes from the repository variable `BUCKET`, default `cricpulse-data` (landing audit).
- `tests/test_rollout.py` (new, 11 tests); `tests/test_pipeline.py` (+8); `tests/test_config.py` (+2); `tests/test_api_and_agents.py` (+2). No existing test was weakened, skipped or deleted. The `settings` fixture in `test_pipeline.py` also pins `rollout_service=""`.
- `Dockerfile`: unchanged (see "Followed the code").

## Verification run
The card's **updated** Verify (commit `8932891`), exact, run after the last file change (the audit fixes). Output went to a scratch log; summary below.
```
source .venv/bin/activate && ruff check src tests && ruff format --check src tests && python -m pytest tests/test_rollout.py tests/test_pipeline.py tests/test_config.py tests/test_api_and_agents.py -q && python -m pytest -q && bash -n scripts/infra_m0b.sh && PROJECT_ID=demo-project ALERT_EMAIL=alerts@example.com DEPLOYER_SA=deployer@demo-project.iam.gserviceaccount.com bash scripts/infra_m0b.sh --dry-run setup && PROJECT_ID=demo-project bash scripts/infra_m0b.sh --dry-run first-build && python -m src.publisher.main bench --help && python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))" && ! grep -n "GCS_BUCKET\|SYNC_SECRET_TOKEN" .github/workflows/deploy.yml && grep -q -- "--no-allow-unauthenticated" .github/workflows/deploy.yml && ! grep -q -- "--allow-unauthenticated" .github/workflows/deploy.yml && PROJECT_ID=demo-project bash scripts/infra_m0b.sh --dry-run status && PROJECT_ID=demo-project BUCKET=other-bucket bash scripts/infra_m0b.sh --dry-run open
```
- `ruff check`: "All checks passed!" `ruff format --check`: "59 files already formatted".
- The four named test files: **55 passed**. Full suite: **144 passed, 2 skipped**; before this build it was 121 passed, 2 skipped. The 1 warning was already there.
- `bash -n` passed. The four dry runs printed 30 `gcloud` commands in all:
  - `setup` and `first-build` ended "setup done…" and "first build done…";
  - `status` printed `gcloud auth print-identity-token` and `curl -s -H 'Authorization: Bearer $TOKEN' $URL/ready`;
  - `open` printed `gcloud run services proxy cricpulse-api --region=us-central1 --port=8080`.
- `bench --help` printed its usage. The YAML parsed. The old-settings grep found nothing, `--no-allow-unauthenticated` is present, and `--allow-unauthenticated` is absent.
- Also by hand: `BUCKET=other-bucket … --dry-run setup` puts that name into all four bucket commands.
- **VERIFY EXIT 0**
- Also run by hand, not part of Verify:
  - `--dry-run bench` and `--dry-run status` printed their commands and exited 0.
  - A missing `PROJECT_ID` or `ALERT_EMAIL` stops with one line and exit 1. No subcommand prints the usage and exits 2.
  - I built the image locally with Docker, then deleted it. It ran three ways on a read-only folder standing in for the bucket:
    1. The API on an empty folder: `/ready` gave `{"status":"ready",…,"snapshot_version":null}`, and nothing was written to the folder.
    2. The API on a folder holding a fixture snapshot and `LATEST.json`: `/ready` gave `"snapshot_version":"v20261111T2249Z"`.
    3. `bench` on that folder: five rows, every p95 ≤ 5 ms, `D-3: mount`.

## Done-when lines met
- Subtask 1, `infra_m0b.sh`: the Verify dry runs above. Not run against Google Cloud: this machine has no `gcloud`, and that run is the owner's.
- Subtask 2, the rollout:
  - equal version → no update: `test_an_equal_version_makes_no_update`;
  - different version → one update that keeps every other env var and setting, then waits: `test_a_different_version_updates_only_that_env_var_then_waits_for_ready` (also `test_a_missing_env_var_is_added`);
  - a revision that fails raises: `test_a_revision_that_fails_raises`;
  - the time limit raises: `test_the_time_limit_raises`;
  - an HTTP error raises: `test_an_http_error_raises[token|get|patch]`;
  - empty `rollout_service` does nothing: `test_empty_rollout_service_does_nothing`.
- Subtask 3, the four run cases:
  - publish: `test_a_publish_rolls_the_api_out_to_the_new_version`;
  - up to date: `test_an_up_to_date_run_rolls_the_api_out_to_the_live_version`;
  - failed gate: `test_a_failed_gate_never_rolls_out`;
  - rollout error: `test_a_failed_rollout_exits_non_zero_and_keeps_latest_json`.
- Subtask 4, settings and D-14a:
  - the setting: `test_settings_rollout_service`;
  - `get_settings()` creates nothing: `test_get_settings_creates_no_folders`;
  - a run on an empty data dir: `test_a_run_on_an_empty_data_dir_creates_what_it_needs`;
  - the API on a data dir it cannot write: `test_api_starts_on_a_data_dir_it_cannot_write`. Before the change this test failed with the blocked note's `PermissionError`.
- Subtask 5, `/ready` names the version: `test_ready_names_the_snapshot_latest_json_points_at` (on a read-only data dir); null for the fallback: `test_api_starts_on_a_data_dir_it_cannot_write`.
- Subtask 6, the bench: `test_bench_times_the_five_questions_on_the_live_snapshot` (five rows and a verdict, data dir byte-identical afterwards), `test_bench_without_latest_json_exits_non_zero`, `test_bench_verdict_is_mount_only_when_every_p95_is_under_300_ms`.
- Subtask 7, the image and deploy: `deploy.yml` parses and has no old settings (Verify). The image was built and run locally as above.
- **Not met: the card's "Done when" (steps 8–12 pass).** These are the owner's cloud steps after landing, and UAT U-4 in M0b.11.

## Proof
- A user can now: the nightly cloud job is ready to switch on. After each run the chat service moves to the newest snapshot, and `/ready` says which snapshot it is serving.
- Works: yes, on this machine (the tests, the dry runs, and the image on a read-only folder). Nothing has run on Google Cloud yet.
- Next: land it. Then the owner runs `setup`, the deploy workflow, `first-build`, `bench` and `status` (steps 8–12), and `open` to use the private chat page.
- Colour 🔴 · output only (Kaizen card *Proof: none*; no screen changed).

## Followed the code, not the card
1. **`Dockerfile` unchanged.** Its default command already runs `python -m src.publisher.main run`. The service's `uvicorn src.api.app:app --host 0.0.0.0 --port 8080` is set in `deploy.yml` with `--command`/`--args`. I proved it by building and running the image.
2. **The job's account also needs `roles/iam.serviceAccountUser` on the API's account.** Cloud Run checks that right on the service's identity for every new revision. `first-build` grants it, on that one account only. The card named only "the right to update the API service".
3. **The rollout polls the service, not the long-running operation the update returns.** Reading an operation needs project-level rights, which the job's account does not have under D-14b. It waits until `reconciling` is false on a revision newer than the one before. Ready means `latestReadyRevision == latestCreatedRevision`; anything else raises with `terminalCondition.message`.
4. **The schedules run as the job's account.** The card makes only two accounts. That account gets `roles/run.jobsExecutorWithOverrides` on `cricpulse-ingest` only, which also covers the Sunday `--archive all_json` override. The schedules call `…/v2/…/jobs/cricpulse-ingest:run`.
5. **`setup` also does two things the card's list leaves out, both needed or step 9 fails:**
   - it enables the six APIs it uses (Run, Scheduler, Monitoring, Secret Manager, Artifact Registry, IAM);
   - it creates the image registry `cricpulse` if it is missing, because `deploy.yml` pushes there.
6. **`setup` waits 30 s after creating a new account,** because IAM takes a moment to see it.
7. **Bench options:**
   - `bench` takes `--batter`, `--h2h-batter` and `--h2h-bowler`. The defaults are the spike's V Kohli, SPD Smith and JJ Bumrah, who are not in the fixture build, so the fixture test names Q de Kock and Ali Khan.
   - Each question gets one untimed warm-up before its 20 timed runs. p95 is the 19th of 20 sorted runs, as in the spike.
   - The bench is in `src/` because `.dockerignore` keeps `docs/` (and `spike.py`) out of the image.
8. **`/ready` also gives null for a file not named `cricket_<D-8 version>.duckdb`.** That covers the old `published/cricket_latest.duckdb` and a `SNAPSHOT_PATH` with another name.
9. **`ingest-local` does not roll out.** Subtask 3 names the run; locally `rollout_service` is empty anyway.
10. **The rollout drops a fixed revision name from the template before writing it back,** so Cloud Run names the new revision instead of refusing a duplicate. Test: `test_a_fixed_revision_name_is_dropped_so_cloud_run_names_the_new_one`.
11. **The rollout's time limit (600 s) and poll (5 s) are constants, not settings.** The card allows one setting.

## Open issues / decisions needed
1. **Please confirm (decision taken):** an equal version whose newest revision is not ready **raises** (there is still no update, so "equal → no update" holds). Without it, the night after a failed revision the run stops "up to date", exits 0, and the API silently stays on the old snapshot: the gap D-14c closes. Test: `test_an_equal_version_on_a_revision_that_failed_raises`. If you rule against it, skip `_wait_ready` when the version is equal and drop that test.
2. **Not testable here; first seen at steps 8–10:**
   - the `gcloud` flags themselves;
   - `gcloud alpha monitoring` needs the alpha component (gcloud offers to install it);
   - the alert's metric label `result="failed"` on `run.googleapis.com/job/completed_execution_count`;
   - a re-deploy with `--add-volume` on an existing volume name;
   - whether object viewer (§5.10) is enough for the API's read-only mount;
   - DuckDB's read-only open over Cloud Storage FUSE (the bench shows it).
3. **Bucket names are global:** fixed by the audit. Set `BUCKET` for the script and the same name as the repository variable `BUCKET`.
4. **Step 10's out-of-memory fix** (8 GiB for the job) also needs `--cpu=2` in `deploy.yml`.
5. **Assumed already in place:**
   - the `GEMINI_API_KEY` secret;
   - the deploy account's own rights to push images and deploy with `--allow-unauthenticated` (the old workflow used them).
   - `setup` grants the deploy account only the right to act as the two accounts.
6. **Each deploy's `--set-env-vars` removes `SNAPSHOT_VERSION`,** so the next run adds it back, which costs one extra revision. Every revision serves `LATEST.json`'s snapshot at start regardless.
7. **`run` still creates `published/` (now unused) on the bucket** through `ensure_directories()`. It is harmless and unchanged.
8. **`scripts/run_uat.py` relied on `get_settings()` making folders.** M0b.11's card already covers this.
9. **`08_AGENTIC_GENAI_REBUILD_BRAINSTORM.md` (untracked) was there before this build** and is not part of it.
10. **Both landing-audit findings are fixed:**
    - (1) the API service is private: `--no-allow-unauthenticated`, `status` with the owner's identity token, and the new `open` subcommand;
    - (2) the bucket name comes from `BUCKET` in `infra_m0b.sh` and from the repository variable `BUCKET` in `deploy.yml`, default `cricpulse-data` in both.
    - Watch at step 9: if the service already exists and is public, the deploy removes public access. `open` needs gcloud's Cloud Run proxy component, which gcloud offers to install.

- Proposed commit: `feat(M0b): cloud job, schedules and API rollout on a private service; /ready names its snapshot; D-3 bench; get_settings creates no folders [M0b.10]` — trailer `Module: M0b.10`
