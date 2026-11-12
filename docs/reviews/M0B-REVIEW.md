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
