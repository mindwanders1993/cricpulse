# BLOCKED — Handoff: M0b.8 (A)
- Branch / worktree: `feat/M0b-trustworthy-data-pipeline` · main checkout `/Users/mrrobot/Desktop/Projects/cricpulse` (HEAD `1584cb7`, lane B merged)
- State: blocked. No source, test or config file was changed. The only new file is this note.
- **Conflict 1 — R-6 is real, and the fix is in a file outside Owns.** This is card subtask 5's own stop branch: "stop with a BLOCKED note that quotes the failing rows for a ruling".
  - Repro, run in the scratchpad, not a test:
    1. Take `sample_t20.json` twice. The second copy differs only in `info.city`.
    2. Run `load_matches`, which uses the same `_derive_venue_and_team` as `build_from_silver`.
    3. Result: `ConstraintException: PRIMARY KEY or UNIQUE constraint violation: duplicate key "ec4347c0be2692e078e409f3076a61e6"`. The rows are `('Church Street Park, Morrisville', 'Morrisville')` and `('Church Street Park, Morrisville', 'Somewhere Else')`.
  - Cause: `src/builder/loader.py` `_derive_venue_and_team` runs `SELECT DISTINCT md5(venue_name), venue_name, city`. One venue name with two `city` values gives two rows with one `venue_id`. Since M0b.5 that is a plain `INSERT`, so the build fails.
  - Before M0b.5 the build did not fail here. I checked on DuckDB 1.5.5: the old `INSERT OR REPLACE` silently kept one arbitrary city per venue.
  - **Real data has it.** I read `data/raw/match_json`, 22,818 files, read-only, in a session script, not a test. 896 venue names; **66 appear with more than one city value**. So the first full `run` fails at step 8:
    - 49 have one city plus a missing city. Examples: `Dubai International Cricket Stadium` (Dubai 238, none 140), `Adelaide Oval` (Adelaide 138, none 79), `Melbourne Cricket Ground` (Melbourne 102, none 90).
    - 17 have two or more real city names:

    | venue (as in the file) | cities (matches) |
    |---|---|
    | `County Ground` | Bristol 60, Chelmsford 50, Northampton 46, Derby 45, Hove 41, Taunton 19 |
    | `Shere Bangla National Stadium` | Mirpur 132, Dhaka 4 |
    | `Pallekele International Cricket Stadium` | Kandy 69, (none) 48, Pallekele 1 |
    | `M Chinnaswamy Stadium` | Bangalore 90, Bengaluru 1 |
    | `National Stadium` | Karachi 63, Hamilton 11 |
    | `St George's Park, Port Elizabeth` | Port Elizabeth 60, Gqeberha 6 |
    | `Zahur Ahmed Chowdhury Stadium` | Chittagong 31, Chattogram 11 |
    | `Dr DY Patil Sports Academy, Mumbai` | Navi Mumbai 26, Mumbai 11 |
    | `Punjab Cricket Association IS Bindra Stadium, Mohali` | Chandigarh 22, Mohali 1 |
    | `Himachal Pradesh Cricket Association Stadium` | Dharamsala 20, Dharmasala 3 |
    | `Nehru Stadium` | Kochi 9, (none) 4, Guwahati 3, Pune 1 |
    | `Grand Prairie Stadium` | Dallas 11, Grand Prairie 1 |
    | `Maharaja Yadavindra Singh International Cricket Stadium, Mullanpur` | Mohali 9, New Chandigarh 1 |
    | `Queen's Park` | Chesterfield 7, (none) 1, Invercargill 1 |
    | `Bready Cricket Club, Magheramason` | Londonderry 6, Bready 2 |
    | `Maple Leaf North-West Ground` | King City 5, Toronto 1 |
    | `Singapore Cricket Club` | Padang 4, Singapore 1 |

  - The cases are of two kinds:
    - Spellings or a missing value for one ground: most rows above.
    - **Different grounds sharing one name**: `County Ground` (6 towns), `National Stadium`, `Nehru Stadium`, `Queen's Park`. These were already merged into one `venue_id` before M0b.5.
  - `gold.dim_venue` is read by the venue resolver (`src/semantic/resolver.py:427`, `:891`), which maps both the name and the city to `venue_id`. So the city chosen changes what chat resolves.
  - Rejected workarounds:
    - **Normalise or drop `city` in `main.py` before the build.** That changes Silver data to dodge a Gold rule.
    - **Catch the `ConstraintException` in the run.** That hides it.
    - **Edit `_derive_venue_and_team`.** It is in `src/builder/loader.py`, outside M0b.8's Owns.
    - Dossier R-6: "a real duplicate is a ruling, not a workaround".
  - **Ruling needed (one question):** which city does a venue with several get?
    - **Recommendation:** keep `venue_id = md5(venue_name)` and emit one row per venue name, with its most frequent non-null city. Ties go to the alphabetically first, so it is deterministic.
      - As a ruling: *instead of failing the build (plain `INSERT`) or splitting ids by city, because `md5(venue_name)` is the id the resolver and marts read today, and M1 re-keys venues anyway (dossier §5.5).*
      - Effect: the build passes on all 66. `County Ground` gets city Bristol. The 4 shared-name grounds stay merged until M1, the same as before M0b.5, but now deterministic.
      - Sketch: `… GROUP BY venue_name, city … QUALIFY row_number() OVER (PARTITION BY venue_name ORDER BY city IS NULL, n DESC, city) = 1`
    - Not recommended: `venue_id = md5(venue_name || city)`. It splits one ground across spellings and missing cities (all 66 venues get two or more ids), and it changes every venue id the resolver reads.
  - **Card change needed:** add `src/builder/loader.py` (`_derive_venue_and_team` only) and `tests/test_loader_and_schema.py` to M0b.8's Owns, or give them a small card of their own before M0b.8. Subtask 5's test then passes instead of stopping.
- **Conflict 2 — the card's Verify grep cannot return "nothing" without weakening a lane B test.**
  - Verify: `grep -rn "ledger\|IdempotencyLedger\|export_gold_parquets" src tests` → nothing.
  - `tests/test_publisher.py:92` is M0b.7's guard, `assert not hasattr(SnapshotPublisher, "export_gold_parquets")`. It always matches.
  - That file is not in M0b.8's Owns. Removing the line would weaken a test, which the goal forbids.
  - Suggested Verify:
    - `grep -rn "ledger\|IdempotencyLedger" src tests` → nothing.
    - `grep -rn "export_gold_parquets" src` → nothing.
    - This keeps M0b.7's guard test.
  - Every other match is inside M0b.8's Owns: `src/config.py`, `src/ledger.py`, `src/publisher/main.py`, `src/downloaders/match_downloader.py`, `src/downloaders/register_downloader.py`, `tests/conftest.py`, `tests/test_ledger.py`.
- Verification run: none. No file under Owns changed, so the card's Verify was not run. `git status --short` after this note: `?? .agents/handoffs/M0b.8-blocked-1.md`, plus `08_AGENTIC_GENAI_REBUILD_BRAINSTORM.md`, which was untracked before the session.
- Done-when lines met: none.
  1. `run` per §5.1 — not built
  2. `ingest-local --matches-dir` — not built
  3. Ledger and unused settings removed — not done
  4. `tests/test_pipeline.py` §8 scenarios 1–6 — not written
  5. R-6 — this note, with the failing rows quoted
- Carried forward for the M0b.8 build session. The notes left these; all are inside M0b.8's Owns unless marked:
  - M0b.7: `main.py:88`, `:165` call the removed `export_gold_parquets`. `main.py:84`, `:162` are the only callers of `publish_snapshot`, so it can go once `run` calls gates → `publish()` → `prune()` directly.
  - M0b.6: the run passes `previous=read_latest(data_dir)`, `quarantined` and `files_seen` to `run_quality_gates` before `publish()`. The goal says the same.
  - M0b.3:
    - The staging dir must be `silver/_staging/<version>/`, because `RunState.manifest_rows[*].version` comes from its name.
    - `files_seen` counts only the changed members. Rule whether `quarantine_bounded` should use all members of the zip.
    - Register the `live` marker in `tests/conftest.py`.
    - The `wi_` stripping in `main.py:132`, `:169` goes with the ledger.
  - M0b.4: re-run a leftover `silver/_staging/<version>/` before parsing a new one (it repairs an interrupted rename). Consider `SET temp_directory` for the merge if U-1 shows spilling (`silver.py` is outside Owns).
  - M0b.5: the run calls `build_marts()` after `build_from_silver(silver_dir, register_dfs, settings)`.
  - M0b.7 settings: `snapshot_date` has no reader left in `src`. `published_dir` is still read by `src/api/app.py:33` and `scripts/run_uat.py:30` (both outside Owns), so it is not unused yet.
- Next step for whoever picks this up: the governor puts the venue-city question to the owner (recommendation above), and corrects the M0b.8 card on Owns (conflict 1) and the Verify grep (conflict 2). Then it hands M0b.8 out again. This note stays; the done note will be `.agents/handoffs/M0b.8.md`.
- Proposed commit: `docs(M0b): M0b.8 blocked on R-6 venue city and the Verify grep; note kept [M0b.8]` — trailer `Module: M0b.8`
  - Files: `.agents/handoffs/M0b.8-blocked-1.md`
