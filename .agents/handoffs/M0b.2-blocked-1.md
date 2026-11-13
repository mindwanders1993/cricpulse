# BLOCKED

# Handoff: M0b.2 (A)
- Branch / worktree: `feat/M0b-trustworthy-data-pipeline` · main checkout `/Users/mrrobot/Desktop/Projects/cricpulse`
- State: blocked — no code written. Stopped before the first edit because the card and the dossier disagree on the scope of M0b.2.
- What changed: only this note, `.agents/handoffs/M0b.2.md`. Nothing under the card's Owns was touched.
- Verification run: not run. Nothing was built, so there is nothing to verify.
- Done-when lines met: none attempted (subtasks 1–4 not started).

## The conflict

**Who deletes the ledger: the dossier says M0b.2, the card says M0b.8.**

| Source | Says |
|---|---|
| Dossier §6 Files Touched | `src/ledger.py`, `tests/test_ledger.py`, `tests/conftest.py` (ledger fixture) — **DELETED — M0b.2** |
| Dossier §9 Task Summary | M0b.2 = "Settings + manifest; **delete the ledger**" |
| Card M0b.2 | Owns: `src/config.py`, `src/snapshot.py`, `src/publisher/manifest.py`, `tests/test_snapshot.py`, `tests/test_manifest.py`, `tests/test_config.py`. No ledger file, no ledger subtask. |
| Card M0b.3 subtask 1 | "Keep today's methods and the `ledger` argument for now (callers go in M0b.8 and M0b.9)" |
| Card M0b.8 | Owns `src/ledger.py` (delete), `tests/test_ledger.py` (delete), `tests/conftest.py`; subtask 3 "Delete the ledger" |

AGENTS.md: "Where they disagree, the dossier wins and the card is corrected before the task is handed out." The card
was not corrected, so the build cannot follow either source without working around the other.

**The code says the dossier's version cannot be done inside M0b.2.** `src.ledger.IdempotencyLedger` is imported by:

- `src/publisher/main.py:12` (M0b.8's file)
- `src/downloaders/match_downloader.py:7`, `src/downloaders/register_downloader.py:6` (M0b.3 / M0b.8's files)
- `src/api/routes/internal.py:14` (M0b.9 removes it)
- `tests/conftest.py:10` (M0b.8's file)
- `src/config.py:53` `ledger_db_path` (removal is M0b.8 per the card, and §5.9 lists it as removed)

Deleting the ledger in M0b.2 would break those imports and the suite, or need edits in four files outside Owns.

## Decision needed (governor / owner)

Recommendation: **correct the dossier, not the card** — change §6's ledger row and §9's M0b.2 row to M0b.8,
instead of deleting the ledger in M0b.2, because its callers (downloaders, `main.py`, `internal.py`) only go away in
M0b.3/M0b.8/M0b.9 and deleting it first breaks the suite. Then re-issue the same `/goal` line; the card as written is
buildable.

## Other dossier issues seen while reading (not blocking on their own; fix in the same pass)

1. **Where `LATEST.json` lives.** §5.2 and §5.7 say `snapshots/LATEST.json`; §5.8 says `DATA_ROOT/LATEST.json`.
   `read_latest(data_dir)` / `write_latest(data_dir, info)` in this card need one answer. Card M0b.10's Verify uses
   `gs://cricpulse-data/snapshots/LATEST.json`, so `snapshots/LATEST.json` looks intended; §5.8 should say so.
2. **`src/snapshot.py` ownership.** §6 assigns `src/snapshot.py` to M0b.9 only; the card creates it in M0b.2
   (`LatestInfo`, `read_latest`, `write_latest`) and M0b.9 adds the resolver. Compatible, but §6 should list both.
3. **D-9 is still "Proposed — from the spike"** in §4, while card §0 records D-1…D-8 and D-10 as ruled. M0b.2 does
   not depend on it (the manifest stores `match_id` as given), but M0b.3 does — rule it before M0b.3 is handed out.

## Next step for whoever picks this up

1. Governor (sensei): rule the ledger conflict above, edit the dossier (§6, §9, §5.8, and D-9's status), commit the
   doc change through kura.
2. Re-issue the M0b.2 `/goal` line to a fresh build session on Opus · high.

- Proposed commit: none — nothing to land. (When built: `feat(M0b): settings, manifest and LATEST.json model [M0b.2]` — trailer `Module: M0b.2`.)
