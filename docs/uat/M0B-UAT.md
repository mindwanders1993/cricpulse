# M0b UAT: trustworthy data pipeline

Run from the repo root with `source .venv/bin/activate`. Run alone: `data/` is live data. Builder runs: 12 Nov 2026.

## U-1 Full local build

```bash
python -m src.publisher.main run --archive all_json
```

Record: match count, snapshot size (`ls -l data/snapshots/`), time, `runs/<version>.json` readable.

**Builder result (12 Nov 2026, after M0b.12): PASSED.** Snapshot `v20261112T1216Z`, data cutoff 2026-11-03.
23,241 files seen, 23,239 matches published, 2 quarantined (match 1130677 "KV Sharma" and 1229824 "J Butler", each
listed for both teams: the D-16c rule), 11,739,043 deliveries. Silver: 51,424 innings, 358,951 wickets, 512,657
match_players. Snapshot `cricket_v20261112T1216Z.duckdb` is 449,851,392 bytes (about 430 MiB). Time 10 min 24 s,
almost all of it the 149 MB download. Every quality gate passed, including `player_match_grain_uniqueness` (0) and
`quarantine_bounded` (2). `data/runs/v20261112T1216Z.json` is readable JSON (source, registers, quarantined list,
snapshot block).

## U-2 Incremental run

```bash
python -m src.publisher.main run
```

Record: match count never drops against U-1, `runs/<version>.json` readable, "up to date" or a new version.

**Builder result: PASSED.** "Changed: 0, parsed: 0, quarantined: 0. Up to date: v20261112T1216Z stays live."
Count stays 23,239 (never drops), no new version, 6.7 s. The run wrote no second `runs/` file (nothing changed).

## Re-run after M0b.13 (D-17)

Builder runs: 12 Nov 2026, M0b.14, on the real `data/`. U-1 and U-2 above stay as recorded.

```bash
python -m src.publisher.main run --archive all_json    # 1
python -m src.publisher.main run --archive all_json    # 2, straight after
GEMINI_API_KEY= python scripts/run_uat.py              # 3
```

**Run 1: PASSED.** Console: "match_quarantined ... player listed for both teams: KV Sharma (match_id 1130677)",
"... J Butler (match_id 1229824)"; "Changed: 2, parsed: 0, quarantined: 2, removed: 0"; every quality gate passed
(`never_shrinks_matches` 23239, `never_shrinks_deliveries` 11739043, `quarantine_bounded` 2); "Published
v20261112T1811Z: 23239 matches, 11739043 deliveries, data to 2026-11-03". Version `v20261112T1811Z`, 23,239
matches, 11,739,043 deliveries, time 9 min 56 s (nearly all of it the 149 MB download). `data/runs/v20261112T1811Z.json`
lists both files under `quarantined`, each with action `not_loaded`.

**Run 2: PASSED.** "Changed: 0, parsed: 0, quarantined: 0, removed: 0" and "Up to date: v20261112T1811Z stays live."
No new version, no second `runs/` file, 21.5 s (D-17d: held files are skipped).

**Error table** (`data/silver/quarantine.parquet`, read with polars), 2 rows, both `parser_version` 1 and
`version` v20261112T1811Z:

| match_id | error | action |
|---|---|---|
| 1130677 | ValueError: player listed for both teams: KV Sharma | not_loaded |
| 1229824 | ValueError: player listed for both teams: J Butler | not_loaded |

**`run_uat.py` on the new snapshot: PASSED 8 of 8** with the mock model, in 0.75 s. Scenario 8 reports
`snapshot_version v20261112T1811Z` matches `LATEST.json`.

## Re-run after the fix round (D-18)

Builder runs: 12 to 13 Nov 2026, M0b.17, on the real `data/`, after M0b.15 (`434163d`) and M0b.16 (`f88ab7c`).

```bash
python -m src.publisher.main run --archive all_json    # 1
GEMINI_API_KEY= python scripts/run_uat.py              # 2
```

**Run: PASSED.** Console: "CricPulse run v20261112T1906Z (source: all_json)"; both register files and the 149,036,509
byte archive downloaded; "Changed: 0, parsed: 0, quarantined: 0, removed: 0, absent from archive: 0"; "Up to date:
v20261112T1811Z stays live." No new version was published, so the live version stays `v20261112T1811Z`: 23,239 matches,
11,739,043 deliveries (unchanged, never dropped), data to 2026-11-03. Cricsheet added no matches since 12 Nov.
Absent count 0, so the log carries no absent ids. No new file in `data/runs/`. Time 28 min 3 s (nearly all of it the
download, slower than the 9 min 56 s of the M0b.14 run). Lock check: `data/run.lock` does not exist afterwards.

**`run_uat.py` on `LATEST.json` (`v20261112T1811Z`): PASSED 8 of 8** with the mock model, in 0.82 s. Scenario 8
reports `snapshot_version v20261112T1811Z` matches `LATEST.json`.

## U-3 API on the new snapshot

```bash
python scripts/run_uat.py          # exits 1 with "no snapshot yet" until a run has published
bash scripts/run_local.sh          # then, in the chat page http://127.0.0.1:8000/ui/, ask:
```

Owner question: "Who has scored the most runs in T20 internationals?" Expected: an answer with its numbers from
the snapshot; `curl -s localhost:8000/ready` shows `snapshot_version` equal to `data/snapshots/LATEST.json`'s version.
After the M0b.13 re-run, `/ready` should now show `v20261112T1811Z`.

**Builder result: `run_uat.py` PASSED 8 of 8 on `v20261112T1216Z` (cutoff 2026-11-03), with the MOCK model.**
Journeys: health and ready, batting and bowling leaderboards (top T20 batter JC Buttler, bowler SP Narine),
text-to-SQL with DDL attacks blocked, scout, story, chat router, and `/ready` naming the `LATEST.json` version.
The three analytics paths and the guardrails were seen working; no invariant was broken.
**Live model: not exercised.** The `GEMINI_API_KEY` in `.env` is rejected by OpenRouter (401 Unauthorized), so the
four model scenarios (4 to 7) fail with the key set and pass with the mock (`GEMINI_API_KEY= python scripts/run_uat.py`,
which the client treats as no key). The owner needs a working key (or accepts the mock) before asking the U-3 chat
question and expecting a live answer.

## U-4 Cloud

Waits for the deploy (D-15): job run, new `LATEST.json` in the bucket, the API revision serves the new version
(`scripts/infra_m0b.sh status`).

## Owner sign-off

Signed: ______________________  Date: ______________
