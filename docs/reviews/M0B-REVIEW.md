# Review: M0b — Trustworthy data pipeline
- **Reviewer:** kensa (fresh session, claude-fable-5-2) · **Date:** 13 Nov 2026 · **Branch:** `feat/M0b-trustworthy-data-pipeline` at `70e00eb` (36 commits on `dev`) · **Colour:** 🔴
- **Read:** the dossier (D-1 … D-17, R-1 … R-8), the 14 cards, every handoff note, the UAT sheet, and every changed file under `src/`, `tests/`, `scripts/`, `.github/`, line by line in the red zones.
- **Ran:** `ruff check src tests` (clean), `ruff format --check src tests` (61 files formatted), `python -m pytest -q` (**180 passed, 2 skipped**: the two live cricsheet.org checks). Six probes of the real run code in a scratch folder, deleted afterwards. `data/` and `.env*` were not opened.

### Pass 1 — Logic and the spec: FLAGGED
### Pass 2 — Security and red zones: FLAGGED
### Pass 3 — Rules and hygiene: PASS

**In one paragraph.** The three Done-when lines hold on the laptop, and I found no way for a run to shrink, corrupt or empty the live snapshot: every gate runs before `LATEST.json` is written, and every published file goes through `*.tmp` and a rename. The seams between the two lanes match field for field. No test was weakened. What is flagged: two things the dossier rules that were never built (findings 2 and 3), one hole in run safety when two runs overlap (finding 1), and one crash window that ends in a false "Up to date" (finding 4). The rest are small.

---

### Seams between the lanes (checked on the producer's code, not the consumer's fixture)

| What crosses | Written by | Read by | Result |
|---|---|---|---|
| `LATEST.json` `version` | `publisher.py:50-60` | gates' messages, `_up_to_date` (`main.py:146-149`), `removed_since` / `held_since` (`main.py:208-212`), rollout (`main.py:267`), `run_uat.py` | Match. Version strings compare as text; D-8's format sorts by time |
| `LATEST.json` `path` | `publisher.py:52`, relative to `data_dir`, POSIX | `snapshot.py:53`, `bench` (`main.py:368`), prune (`publisher.py:80`) | Match. The API's name pattern (`app.py:20`) fits `VERSION_FORMAT` (`main.py:32`) |
| `match_count`, `delivery_count` | `publisher.py:44-45`, raw `COUNT(*)` | `quality_gates.py:129-146`, the same two `COUNT(*)` | Match |
| `sha256` | `publisher.py:40` | nobody | See finding 9 |
| `data_cutoff`, `parser_version`, `created_at` | `publisher.py:46-58` | `run_uat.py` prints the cutoff; nothing else yet (M1) | Fine |
| Run report `registers` | `main.py:245` | `_up_to_date` (`main.py:142-143`) | Match, same dict shape. A published run with no report counts as changed (D-12b) |
| Run report `quarantined` | `main.py:249`, the error table's own rows | the owner | Match, tested end to end |
| Manifest rows | `archive.py:98-106` | `manifest.is_current`, `quarantine.classify`, `_up_to_date` | Match. See finding 4 for the one window where a row is lost |
| Error table | `quarantine.py`, via `main._apply` | `is_held` in both readers (`archive.py:53-58`, `main.py:62`), the two gate inputs | Match |
| Gate inputs | `main.py:225-232` | `run_quality_gates(con, previous, quarantined, files_seen, removed)` | Match with dossier §5.6 |
| Snapshot resolution | job writes `snapshots/LATEST.json` | `resolve_snapshot_path` (`snapshot.py:45-53`), `app.py:34-38` | Match. `SNAPSHOT_PATH` wins, then `LATEST.json`, then the old fallback (M0a removes it) |
| `SNAPSHOT_VERSION` on the service | `rollout.py:76-88` | nobody reads its value; it only makes Cloud Run start a new revision, which reads `LATEST.json` | As D-13a designs it. See finding 7 |

**Proved only on a stub:** the whole of `rollout.py` (Cloud Run Admin API and the metadata server, mocked at the transport) and every `gcloud` line. They wait for the deploy (D-15), so they are not findings. What the real service answers that the stub does not: a PATCH returns a long-running operation, which the code rightly ignores and polls the service instead; and a revision counts as ready as soon as the container listens, whatever database it opened (finding 7).

---

### Tests
- **Integrity:** none weakened or skipped. Deleted tests are the ones the cards name (`test_ledger.py`, three extract-to-disk downloader tests, the sync-endpoint test, `test_settings_snapshot_date_default`), each for code that no longer exists. `test_snapshot_publisher` and `test_settings_default_directories` were rewritten for the new publish and the removed settings; their assertions got stricter, not looser. The only new skip is the `live` marker R-3 asks for. No `noqa`, no `type: ignore`, no `xfail`.
- **Criterion coverage:** dossier §8 scenarios 1–8 each have a test that drives the real CLI with only the network mocked (`tests/test_pipeline.py`). D-12 (a)–(d), D-13a's four cases, D-14a's three, D-17 (a)–(f) and (h) each have a named test. Not covered, because the code does not exist: findings 1, 2 and 3.
- **Hand recompute (Kaizen card rule).** I built a snapshot from `tests/fixtures/sample_t20.json` and `sample_test.json` through the real `_pipeline` in a temp folder, then worked the same figures out from the raw JSON with plain loops:

| Figure | By hand from the fixture | In the snapshot's mart |
|---|---|---|
| Batting, RR Rossouw (`cad00a4d`), T20 | 78 runs, 38 balls faced (wides left out), 0 dismissals, 3 fours, 7 sixes, strike rate 205.26 | 78, 38, 0, 3, 7, 205.26, average NULL |
| Bowling, CJ Gannon (`519c30cb`), T20 | 24 legal balls, 13 runs conceded (his 1 leg-bye left out), 3 wickets, economy 3.25, average 4.33 | 24, 13, 3, 3.25, 4.33 |

Both match. The bowling check is a real one: counting the leg-bye would have given 14 and 3.50.

---

### Red zones, line by line: why each is safe
- **`src/publisher/main.py`** — Gates run at `:225-232`, publish at `:235`; a gate failure raises before `publish` and the build file is deleted in `finally`. Nothing else writes `LATEST.json`. Markers, the run report, the manifest and the error table are all `*.tmp` then rename. Flagged: findings 1, 4, 5.
- **`src/publisher/publisher.py`** — Refuses to overwrite a published snapshot (`:31-33`); copy to `.tmp`, rename, then `write_latest` last. Prune never deletes the file `LATEST.json` names (`:80-84`). Flagged: findings 5, 9, 10.
- **`src/publisher/silver.py`** — Merge and removal write every table to `.tmp`, check the match count, and only then rename; a failure deletes the `.tmp` files and leaves Silver as it was. Null and duplicate ids are refused before any write (`:35-42`). Paths are quoted; ids are bound as a parameter (`:105-107`). Flagged: finding 6.
- **`src/publisher/archive.py`** — Reads zip members in memory, never extracts, so a hostile member name cannot write outside the folder; the id is only the file stem and is never used in a path. A duplicate stem fails the run (D-9). Flagged: finding 8.
- **`src/publisher/quarantine.py`, `manifest.py`** — Pure frame logic plus `*.tmp`-then-rename saves. Safe.
- **`src/publisher/quality_gates.py`** — The seven old gates are byte-for-byte unchanged; the new ones match §5.6; a gate that errors counts as failed. Safe.
- **`src/publisher/rollout.py`** — The token comes from the metadata server, goes only into a header, and is never logged or printed; the error path prints the URL and reason only. Empty `rollout_service` returns at once. Safe as far as a stub can show.
- **`src/snapshot.py`** — `write_latest` is `.tmp` then replace. A malformed `LATEST.json` raises and the API refuses to start, which is the right way to fail. `path` is trusted as written; only the job's account can write it (D-14b). Safe.
- **`src/config.py`** — No secret has a default; `get_settings()` creates nothing (D-14a); `sync_secret_token` and `gcs_bucket` are gone. Safe.
- **`src/ai/guardrails.py`** — Not in the diff. The one door is untouched, and the sync endpoint, the only request path that could write data, is deleted with its auth helper.
- **Access:** the API service is `--no-allow-unauthenticated` (`deploy.yml:75`); the job's rights are per resource (`infra_m0b.sh:120-129, 180-187`). No secret, key or token is in the diff.

### The eight invariants
1 kept (`main.py:225-235`, `snapshot.py:40-42`, `publisher.py:36-38`) · 2 kept (no GCS SDK; `grep` clean) · 3 kept (Polars + DuckDB; the Gold file is built under `tmp_dir`, `main.py:215`) · 4 kept (no cricket formula added; `bench.py` reads marts and golden queries) · 5 kept (no new request-path connection; guard untouched) · 6, 7 not in scope · 8 kept. Evals: not yet (none before M2).

---

### Findings

**Medium**

1. `src/publisher/main.py:169` with `:71-77` and `:215-216` — **Two runs that overlap can lose matches without any error.** A run's first act is to tidy leftover staging folders, and it treats another run's half-written folder as a crashed one: without the marker it deletes it. The first run carries on, merges only the batches written after the delete, and still records every file as done in the manifest. Probe: run A parses `1001` and `1002`, run B starts between them; afterwards the manifest lists both, Silver holds only `1002`, and the next run on the same files publishes without `1001`, exit 0. Only `--reparse-all` heals it. D-12 is titled "after a failure, a crash or a double start", but (d) only refuses a second run after the first has finished in the same minute. Two runs in the same minute before either publishes also share one staging folder and one build file, and each deletes the other's. — *What a user would see:* a match, or a corrected scorecard, missing from every answer, with green runs. It needs an overlap: the owner starting a run in a second terminal during the ten-minute full build, a manual job execution during the nightly one, or Cloud Scheduler delivering twice. *Fix direction:* one lock file under `data_dir` taken before `_recover_staging`, refused if held.

2. `src/parsers/match_parser.py:162-168` — **D-16(b) is ruled but not built.** The dossier says a name listed twice for one team keeps one row. The code only catches a player on both teams (c). Probe: a file with one name repeated in one team's list parses cleanly, goes into Silver and the manifest, and `player_match_grain_uniqueness` then fails that run and every retry; the error table stays empty, so nothing names the file. The card's Done-when ("each cause found has a test") was met, since only cause (c) turned up; the decision itself was not. — *What a user would see:* one such file from Cricsheet stops every nightly publish until someone changes the parser and bumps `PARSER_VERSION`. This is the M0b.11 stop over again. *Fix direction:* drop the exact repeat in the parser, with a test; or a ruling that says (b) waits.

3. `src/publisher/main.py` (no line: the code is absent) — **The Sunday absence log of dossier §5.3 and R-4 was never built and is on no card.** R-4's whole plan is "never-delete rule + Sunday absence log". The never-delete half exists. Nothing logs or reports ids that are in the manifest but missing from `all_json`. M0b.8's builder said so in its handoff note ("On no card … it needs a card line"); no card followed. — *What a user would see:* a match Cricsheet withdraws, or re-issues under a new file name, stays in the app for good; in the rename case its runs are counted twice, and no one is told. *Fix direction:* list the absent ids in the run report on an `all_json` run; or move the line to M1 in the dossier.

**Low**

4. `src/publisher/main.py:122-124` with `src/publisher/silver.py:92` — **A crash between the merge and the manifest write ends in a false "Up to date".** `silver.merge` deletes the staging folder, marker included, before step 7 saves the manifest. Probe: kill the run there; Silver holds the new match, the manifest does not, no marker is left. If the next archive no longer carries that file (a crashed Sunday run followed by a nightly one), the run prints "Up to date" and exits 0 while Silver is ahead of the live snapshot. The match appears only when something else forces a build, or on the next Sunday run. D-12(c) and (a) exist to stop exactly this. M0b.8's handoff named the edge; it was not carded. *Fix direction:* save the manifest before the staging folder goes.

5. `src/publisher/publisher.py:90` with `src/publisher/main.py:239` and `:347` — **Anything that fails in prune leaves a published snapshot with no report and no API rollout.** Probe: one zip in a folder under `bronze/cricsheet/` whose name is not a date (say a hand-made `old/`) makes `date.fromisoformat` raise after `LATEST.json` has moved. Every later run rebuilds, publishes again, and fails again at the same line; `_roll_out` is never reached, so in the cloud the API stays on the old snapshot while the alert fires nightly. Loud, and no data is lost, but the publish and the tidy-up are tied together. *Fix direction:* skip folders that are not dates; write the report and roll out before pruning.

6. `src/api/app.py:42` and `src/publisher/silver.py:28, 100` — **Two DuckDB connections have no spill folder set.** The API's read-only connection defaults to `<snapshot>.duckdb.tmp`, beside the snapshot (probe confirmed). On the read-only mount a query that needs to spill fails; on the laptop a heavy question creates a folder inside `snapshots/` from the request path. The service is given `TMP_DIR` (D-14a) but never uses it. The Silver merge spills to `.tmp` in the working folder rather than `settings.tmp_dir` (§5.10 asks for a spill dir). For the deploy; the D-3 bench opens the file the same way, so it will show it.

7. `src/publisher/rollout.py:46-54` with `src/api/app.py:46-50` — **The rollout checks that a revision is ready, not which snapshot it serves.** If the service cannot see the file `LATEST.json` names (the card itself warns the `BUCKET` variable and the script's `BUCKET` can differ), the API starts on the empty in-memory fallback, Cloud Run calls it ready, and the job exits 0. `status` would show `snapshot_version: null`, but only if someone looks. Closes when M0a refuses to start without a snapshot; until then, the deploy should not rely on a green job alone.

8. `src/publisher/archive.py:90` — **Every exception counts as a bad file.** That is D-5, but with D-17(a) it now has a second effect: on a parser bump or `--reparse-all`, a passing failure on an unchanged file (out of memory is an `Exception` here) marks a healthy live match `removed`, and the gate allows the drop. It stays out until a later parser bump or `--reparse-all`, because the file is then held. *Fix direction:* let `MemoryError` and `OSError` stop the run.

9. `src/publisher/publisher.py:37-40` — **The `sha256` in `LATEST.json` is taken from the copy, not the source, and nothing reads it.** A bad copy onto the mount would be recorded with its own hash and published. Comparing it with the build file's hash before `write_latest` costs one read.

10. `src/publisher/publisher.py:99-115`, `README.md:30, 73, 97` — **Leftovers the notes promised a later card for.** `publish_snapshot` has no caller but one test, and its docstring still says "Kept while main.py calls it" (D-12e: "fixed by a later card"; none was written). The README diagram still shows the ledger, the sync webhook and `SYNC_SECRET_TOKEN`. M0b.8's note also lists stale names in `.env.example` (not opened by this review).

11. `src/builder/loader.py:61, 71, 84` — **Citation.** §5.5 says "plain `INSERT` everywhere in this build, never `INSERT OR REPLACE`" and, two lines on, "registers loaded as today". The registers keep `INSERT OR REPLACE` with no comment, so a repeated id in `people.csv` silently keeps the last row. Needs one line in the dossier and one in the code saying which sentence wins.

12. Commit `276cab5` (housekeeping, not M0b work) — `.agents/skills/{gemba,hansei,hoshin,kensa,kura,sensei,shiken,takumi}` are tracked links to `/Users/mrrobot/Desktop/Projects/archon/kaizen/…`, and `AGENTS.md` names the owner contract by the same absolute path. On any other machine, or on GitHub, all eight role skills are dangling links, and a home-folder path is in the repo. The deny rules for push and PR in `.claude/settings.json` are intact; only the goal-cap hook went, as the commit says.

### Already settled, not re-opened
The cloud steps, UAT U-4 and the D-3 bench wait for the deploy (D-15). R-8 is accepted. The U-3 chat question and the owner's signature are still open, as expected; the sheet says plainly that the live model was not exercised (the local key is rejected) and the harness ran on the mock. Findings 6 and 7 touch the deploy and are for that day, not this fix round.

### Diff: 95 files, +8206 / -1652
(`src/`, `tests/`, `scripts/`, `Dockerfile`, `.github/`: +4632 / -970; the rest is docs, handoff notes and the skills housekeeping. Every code file sits in some card's Owns; no mass formatting, no scratch files. `docs/features/m0b_spike/` holds the spike's scripts, which M0b.10's card cites.)

### Verdict: CHANGES REQUIRED
A short fix round, then a second look at the fix diff only:
- **Fix:** 1 (the run lock) and 4 (manifest before the marker goes). Both are small and both are run safety in a red zone.
- **Fix or rule:** 2 (D-16b) and 3 (the absence log). Each is a dossier line with no code; either build it or change the dossier to say where it went.
- **Card for later, no need to hold the module:** 5, 8, 9, 10, 11. **At the deploy:** 6, 7. **Owner's call, outside M0b:** 12.

### Kaizen: did anything go wrong twice?
Yes, two things.
1. **Silver and the manifest are written before anything checks the result, and the gap was found one case at a time.** D-12(a) (a failed gate, then a quiet "up to date"), R-7 / D-17 (a bad match stuck in Silver after M0b.11's failed build), D-17(h) (the retry that passed quietly), and now findings 2 and 4 are all the same shape: state gets ahead of `LATEST.json` and the next run trusts it. Four rulings and two findings for one cause.
2. **A builder wrote an open issue in its handoff note and no card picked it up.** M0b.8's note named the missing absence log, the merge-then-manifest crash edge and the stale `publish_snapshot` docstring; all three are findings here (3, 4, 10). The same module also had six BLOCKED notes because a card's Owns or its facts did not match the code (M0b.2, M0b.7, M0b.8 twice, M0b.10, M0b.11), though each of those was caught before any code was written, which is the notes working as meant.

---

## Second look — fix round (8514602..f88ab7c)
- **Reviewer:** kensa (fresh session, claude-fable-5-2) · **Date:** 13 Nov 2026 · **Branch:** `feat/M0b-trustworthy-data-pipeline` at `f88ab7c` · **Colour:** 🔴
- **Scope:** the fix diff only: `db181cd` (D-18 notes), `434163d` (M0b.15), `f88ab7c` (M0b.16). Read: D-18, §7.1, both cards, both handoff notes, and every changed line under `src/` and `tests/`. Findings 5, 6, 7, 9, 10, 11 and 12 are carried (§7.1) and were not looked at again.
- **Ran:** `ruff check src tests` (clean), `ruff format --check src tests` (61 files formatted), `python -m pytest -q` (**194 passed, 2 skipped**: the two live cricsheet.org checks, as before). In a scratch copy of `src/` and `tests/` (made with `git archive`, deleted afterwards): 20 small reversals of the fix, one at a time, each run against the card's test slice; 17 probes through the real CLI; 8 real processes racing for the lock, 5 rounds; one run killed with SIGTERM. `data/` and `.env*` were not opened. Nothing in the repo was changed but this section.

### Pass 1 — Logic and the spec: FLAGGED (low only)
### Pass 2 — Security and red zones: FLAGGED (low only)
### Pass 3 — Rules and hygiene: PASS

**In one paragraph.** All five D-18 lines hold in the code. The fix broke nothing it touched: the crash recovery, D-17's removal, the error table and `ingest-local` all behave as ruled, and the lock is released on every exit that Python can unwind. I found no way for this diff to shrink, corrupt or lose live data. Six low findings: two are tests that do not fail when half a ruling line is taken out, two are edges of the lock, one is a spelling of the full archive that skips the absence log, one is the as-built docs.

---

### 1. Does each D-18 line hold, and does a test fail without it?

"Fails without it" was checked by taking the line out of the scratch copy and running the slice (`test_pipeline`, `test_silver`, `test_archive`, `test_match_parser`, `test_quarantine`).

| Line | Holds in the code | Test | Fails without the fix |
|---|---|---|---|
| (a) refuse a second run | `main.py:74-87`, lock taken at `:367` and `:402`, before the D-12(d) check (`:218`) and the staging recovery (`:224`) | `test_pipeline.py:715` | Yes, for `run`. **No for `ingest-local`** (finding 3) |
| (a) the lock goes in a `finally` | `main.py:91-94` | `test_pipeline.py:756`, and 29 others that would meet a left-over lock | Yes |
| (a) 2 hours, then taken over with a warning | `main.py:43`, `:81`, `:89-90`; an empty lock ages by file time, `:64-65` | `test_pipeline.py:770`, `:794` | Yes: 1 hour, 3 hours and "never" each fail |
| (b) the merge leaves staging | `silver.py:88-90` | `test_silver.py:63`, `test_pipeline.py:834` | Yes |
| (b) staging goes after step 7, marker first | `main.py:171-176` | `test_pipeline.py:813`, `:834` | Yes: deleting before the save fails both |
| (c) an exact repeat keeps one row; both teams still raises | `match_parser.py:166-172` | `test_match_parser.py:121`, `:131`; the two D-16(c) tests, unchanged | Yes, each way |
| (d) member ids, changed or not | `archive.py:51-52` | `test_archive.py:209` | Yes |
| (d) report field and console count, `all_json` only | `main.py:250`, `:256`, `:315-316`, `:401` | `test_pipeline.py:867`, `:891` | Yes, each of the three |
| (d) the `absent_from_archive` log line | `main.py:251-252` | none | **No** (finding 4) |
| (d) nothing deleted | no delete on that path | `test_pipeline.py:867` (four matches stay in Gold and the manifest) | n/a |
| (e) `MemoryError` and `OSError` stop the run | `archive.py:94-97` | `test_archive.py:222` (both), `test_pipeline.py:910` | Yes, each error on its own |

D-18(d) as amended in `db181cd` matches the code: an up-to-date full run prints the count, logs the ids and writes no report (probed).

### 2. Did the fix break anything it touched?

| Area | What I did | Result |
|---|---|---|
| D-12(c) recovery, now that the merge leaves staging | Crash between the merge and step 7 (the card's test). Crash right after step 7, marker still there. Crash between the marker's delete and the folder's. A merge that raises | Each is finished by the next run. The replayed merge adds no rows (row counts per table equal before and after). The folder without a marker is deleted and the run still publishes, because the manifest rows are newer than `LATEST.json`. No false "Up to date" in any of them |
| D-17's removal path | Parser bump rejects `9001` (unchanged file) while a new match `1003` arrives; crash between the merge and step 7 | Next run: `9001` gone from all five Silver tables and the manifest, `1003` in the manifest and Gold, the error row still `removed` at the crashed run's version, the gate passes, the run after that is "Up to date". The removal-only case (`test_pipeline.py:575`) passes unchanged |
| The error table | Read `_apply` (`main.py:159-162`): unchanged but for where staging goes. Replays are idempotent: `upsert` keeps a `removed` row's version, `drop` is a filter | Safe. D-18(e)'s test also shows it byte-identical after a stopped run |
| `ingest-local` | A held lock; a failure inside the run; a clean run | Refused with exit 1 and the tree byte-identical; lock held during the run and gone after the failure; no `absent_from_archive` field. The "no .json files" check runs before the lock and only reads the input folder |
| The lock's `finally` | Success, "Up to date", a failed gate, D-12(d)'s refusal, `MemoryError`, `KeyboardInterrupt`, a failed rollout (`typer.Exit(1)` from `_roll_out`) | Lock gone every time. The rollout runs inside the lock (seen from inside `ensure_api_on`). A refused run never reaches the `finally`, so it leaves the holder's lock alone |
| Real processes | 8 started on one barrier, 5 rounds | Exactly one held the lock each round, 7 refused, no lock left |

Not an exit Python unwinds: a kill. See finding 1.

### 3. Test integrity
- One assertion changed, the one the card allows: `tests/test_silver.py:61-63`, `assert not staging.exists()` → `assert staging.exists()`. Its old meaning moved to `test_pipeline.py:813`, which fails if staging goes before the manifest is saved.
- `git diff 8514602..f88ab7c -- tests` removes no other line. No test deleted, no `skip`, `xfail`, `noqa` or `type: ignore` added. The only new marker is one `parametrize`.
- New: 9 tests in `test_pipeline.py`, 2 in `test_archive.py` (one runs twice), 2 in `test_match_parser.py`, one fixture. The fixture differs from `both_teams_1229824.json` in one line (Guernsey's "J Butler" → a second "IDA Damarell").
- 18 of the 20 reversals were caught. The two that were not are findings 3 and 4.
- **Hand recompute (Kaizen card rule),** on the new fixture, built with `sample_t20` and `sample_test` through the real `ingest-local` in a scratch folder:

| Figure | By hand from the fixture | In the snapshot's mart |
|---|---|---|
| Batting, IDA Damarell (`580ae7f2`), T20 | 1 run, 2 balls faced, 0 dismissals, strike rate 50.00 | 1, 2, 0, 50.0, 1 match played, average NULL |
| Bowling, ACF Stokes (`7f74b21d`), T20 | 6 legal balls, 5 runs conceded, 0 wickets, economy 5.00 | 6, 5, 0, 5.0 |

Both match. The repeated name gives one `fact_player_match` row and one match played, not two (21 rows, 21 players).

### 4. Red zones, line by line: why each change is safe
- **`src/publisher/main.py:58-94` (the lock).** `open("x")` is the exclusive create. The lock holds a version and a time, no secret. A refusal raises before the `try`, so only the run that created a lock deletes it on the normal paths. The path is fixed (`data_dir/run.lock`); nothing a request or a file's content can steer. A lock whose content is not the expected JSON object fails the run with a traceback and leaves the lock: it fails closed. Flagged: findings 1 and 5.
- **`main.py:149-177` (`_apply`).** Staging and its marker now outlive every write. The marker is deleted first, so a half-deleted folder can never be replayed. `_apply` is only called with a marker on disk (`:245-246` writes it under the same condition as `:267`; the recovery checks it at `:119`), so the unconditional `unlink` cannot miss. Gates still run before `publish` (`:287-297`); nothing in this diff writes `LATEST.json`.
- **`main.py:248-258`, `:315-316` (the absence log).** Read-only on the manifest: a set difference, a log line, a count and a report field. The id set is filled by the time it is read, because `parse_to_staging` drains the reader first (`:237`).
- **`main.py:367-377`, `:401-419` (the two commands).** The same calls as before, inside the lock. `bench` takes none and only reads.
- **`src/publisher/archive.py:51-52`, `:94-97`.** The id is still only the file stem and is never used in a path. The re-raise sits before the catch-all, so D-5's quarantine is unchanged for every other error. A stopped parse leaves staging without a marker, which the next run deletes; Silver is untouched.
- **`src/publisher/silver.py:88-90`.** One deletion removed. The `*.tmp`-then-rename merge is untouched.
- **`src/parsers/match_parser.py:166-172`** (🟡, not a red zone). Same result as before for every file without a repeat; the both-teams check comes first.
- No secret, key or token in the diff. The two handoff notes name the checkout by its home-folder path, as all 21 notes do; that belongs with carried finding 12.

### The eight invariants
1 kept (gates before publish, `main.py:287-297`; every write still `*.tmp` then rename; the lock is the only new file under `data_dir` and nothing reads it but the run) · 2 kept · 3 kept (no new library) · 4 kept (no cricket formula touched) · 5 kept (no request path changed) · 6, 7 not in scope · 8 kept. Evals: not yet (none before M2). Decision citations: every new branch and constant cites D-18 or D-16(b). Owns: each commit stays inside its card's Owns; `db181cd` is the governor's dossier edit.

---

### Findings

No high, no medium.

**Low**

1. `src/publisher/main.py:91-94` with `:81-87` and `.github/workflows/deploy.yml:95-96` — **A run that is killed leaves its lock, and the retry is refused.** The `finally` only runs when Python unwinds. Probe: a run sent SIGTERM exits 143 and `run.lock` stays; the next start prints "another run is in progress" and exits 1. The cloud job has `--max-retries=1` and `--task-timeout=60m`: after a timeout, an out-of-memory kill or a moved instance, Cloud Run starts the retry at once, the lock is under 2 hours old, and the retry stops in seconds. The D-12(c) recovery then waits for the next schedule, about a day later, which takes the lock over. Before the fix the retry did that recovery. — *What a user would see:* nothing wrong in the app, and no data lost; one night's new matches arrive a day late, with a failure alert. On the laptop: closing the terminal mid-run blocks every run for 2 hours with a message that says a run is in progress and does not say the lock can be deleted. *Fix direction:* turn SIGTERM into an exception in `run` and `ingest-local` so the `finally` runs; or say in the message when the lock will be taken over. *Home:* the deploy (D-15), beside §7.1's D-18a row.

2. `src/publisher/main.py:401` with `src/downloaders/match_downloader.py:21-23` — **Two other spellings of the full archive skip the absence log.** The downloader turns `--archive all` and `--archive all_json.zip` into `all_json.zip`. `main.py` compares the raw text with `"all_json"`. Probe: both fetch the full archive and publish; the console line has no "absent from archive", the report has no field, and no id is logged. — *What a user would see:* a full run typed by hand as `--archive all` names no withdrawn match. The two schedules pass `all_json` exactly (`scripts/infra_m0b.sh:190, 194`), so the nightly path is not affected.

3. `tests/test_pipeline.py` (no test) for `src/publisher/main.py:367` — **No test fails when `ingest-local` stops taking the lock.** D-18(a) names both commands; the four lock tests drive `run` only. With the lock taken out of `ingest-local` the slice stays green (90 passed). The code is right today (probe: refused, tree unchanged, lock freed on failure). *Fix direction:* one test: a held lock, `ingest-local` exits 1 and changes nothing.

4. `tests/test_pipeline.py:867` for `src/publisher/main.py:251-252` — **No test asserts the `absent_from_archive` log line.** After `db181cd`, that line is the only place the ids go on an up-to-date full run, which the handoff note calls the common Sunday case. With the line removed the slice stays green. *Fix direction:* assert the ids in `caplog` on the test's second `all_json` run.

5. `src/publisher/main.py:94` — **A run deletes whatever lock is there when it ends, its own or not.** D-18(a) rules that a lock 2 hours old belongs to a dead run. If the run is alive (the laptop slept mid-run, or a download crawled), a second run takes the lock over, the two run side by side, and when the first ends it deletes the second's lock, so a third can start. Probe confirmed the delete. The handoff note's "another run's lock is never deleted" is true only while the 2-hour rule is. — *What a user would see:* review finding 1 again, but only after a run has lived past 2 hours. *Fix direction:* delete the lock only if it still holds this run's version. Rare; can be carried.

6. `docs/features/M0B-TRUSTWORTHY-DATA-PIPELINE.md:96-116, 120-131, 310-324` — **The as-built sections do not show the fix.** §5.1's steps have no lock and no "staging goes after step 7"; §5.2's layout has no `run.lock`; §8's test list ends at D-17. D-18 and §5.2's staging line are right. One line each.

**Seen, and not raised**
- A run refused in the instant the holder finishes ends with a `FileNotFoundError` instead of the message (`main.py:62`). It exits non-zero and writes nothing; M0b.15's note lists it.
- A lock that is valid JSON but not the expected object (`{}`, a time with no zone) fails every run with a traceback until someone deletes it. Only a hand-written lock can look like that.
- Two spellings that the register maps to one id in one team keep one row, the first spelling (M0b.16's note). That follows the card's rule.
- The takeover race and the bucket mount are ruled or carried (D-18a, §7.1).

### Diff: 12 files, +776 / -40
(`src/`: 4 files, +119 / -37. `tests/`: 4 files and one fixture, +566 / -1. The rest is the dossier and two handoff notes.)

### Verdict: PASS
Every D-18 line holds, nothing the fix touched is broken, and no test was weakened. The six findings are low and none can shrink or corrupt the live snapshot.
- **Cheap to add before the pull request, the governor's call:** 3 and 4 (two short tests) and 6 (three doc lines).
- **Carry in §7.1:** 1 → the deploy (D-15); 2 and 5 → the first card of M1.
