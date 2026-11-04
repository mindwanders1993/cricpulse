# Handoff: M0b.6 (B)
- Branch / worktree: `feat/M0b-lane-b` · `/Users/mrrobot/Desktop/Projects/cricpulse-M0b-b`
- State: done
- What changed:
  - `src/publisher/quality_gates.py`:
    - New signature: `run_quality_gates(con, previous: LatestInfo | None = None, quarantined: int = 0, files_seen: int = 0)`. The defaults keep today's callers working unchanged: `publisher.py:31` and `test_loader_and_schema.py:62`.
    - The existing seven gates are unchanged (same SQL, same order, first in `results`).
    - Grain gates added, citing D-10: `innings_grain_uniqueness` on `(match_id, innings_number)` and `player_match_grain_uniqueness` on `(match_id, player_id)`. Both columns pairs are the primary keys D-10 drops in M0b.5.
    - Shrink gates added, citing §5.6 and invariant 1, and only added when `previous` is not `None`:
      - `never_shrinks_matches`: `COUNT(gold.dim_match) ≥ previous.match_count`.
      - `never_shrinks_deliveries`: `COUNT(gold.fact_delivery) ≥ 0.999 × previous.delivery_count`.
    - `quarantine_bounded` added, citing D-5: `quarantined ≤ max(5, ceil(0.01 × files_seen))`. It is evaluated in Python after the SQL loop, so no run-state value goes into SQL. It is recorded in `results` like the others.
    - A failure still raises one `QualityGateFailure` listing every failed gate as `[<gate name>] …`.
  - `tests/test_quality_gates.py` (new, 14 tests).
- Verification run (after the last file change):
  - `python -m pytest tests/test_quality_gates.py tests/test_publisher.py -q` gave **15 passed**, exit 0.
  - `python -m pytest -q` gave **78 passed** (64 before + 14 new), exit 0. The 1 warning (Starlette `httpx` deprecation) was there before.
  - `ruff check src tests && ruff format --check src tests` is clean, exit 0.
- Done-when lines met (subtasks):
  1. Signature: `quality_gates.py::run_quality_gates`. Every test calls it with the keyword args. The old positional call is still covered by `test_loader_and_schema.py::test_duckdb_loader_and_marts`.
  2. Shrink and quarantine gates:
     - `never_shrinks_matches`: `test_never_shrinks_matches_passes_on_equal_count` and `test_never_shrinks_matches_fails_when_fewer`.
     - `never_shrinks_deliveries`: `test_never_shrinks_deliveries_passes_within_tolerance` and `test_never_shrinks_deliveries_fails_below_tolerance`. These test the exact 0.999 boundary.
     - `quarantine_bounded`: `test_quarantine_bounded_floor_of_five`, `test_quarantine_bounded_fails_over_floor`, `test_quarantine_bounded_one_percent` (1,050 files, limit 11) and `test_quarantine_bounded_exact_one_percent` (700 files, limit 7).
  3. Grain gates: `test_innings_grain_gate_passes`, `test_innings_grain_gate_fails_on_duplicate`, `test_player_match_grain_gate_passes` and `test_player_match_grain_gate_fails_on_duplicate`. The duplicate is made with a constraint-free `CREATE OR REPLACE … AS SELECT`, which is how the table will look after D-10. The existing seven are covered by `test_existing_seven_unchanged_and_pass`, which asserts the first seven names in order and that all gates pass.
  4. Tests:
     - Each new gate passes and fails on purpose: the tests above.
     - `previous=None` skips the shrink gates: `test_previous_none_skips_shrink_gates`.
     - The failure names its gate: every fail test uses `pytest.raises(QualityGateFailure, match=r"\[<gate>\]")`, and the tests that leave other gates passing also assert the unrelated gate is absent from the message.
- Open issues / decisions needed:
  - **The delivery tolerance is worded three ways.** Dossier §5.6 says `≥ 0.999 × previous`. The `invariants` rule book §1 says counts are "≥ the live snapshot's", which is strict. The card names the gate but gives no rule. I followed the dossier (dossier wins). Align the `invariants` wording to §5.6, or rule otherwise.
  - The shrink gates compare raw `COUNT(*)` of `gold.dim_match` and `gold.fact_delivery`. M0b.7 must write `LatestInfo.match_count` and `delivery_count` from the same two counts, or the gate compares different quantities.
  - Callers do not pass the new arguments yet: `publisher.py` still calls `run_quality_gates(con)`. Wiring `previous`, `quarantined` and `files_seen` belongs to M0b.7 (publish) and M0b.8 (pipeline entry).
  - A false start, recorded so the next session does not repeat it: I briefly changed the 1% formula to `files_seen / 100` thinking `0.01 * n` misrounds. A search of n = 1 to 100,000 found no such case, so I reverted to the card's formula. The 700-file boundary test was kept.
  - Still open from M0b.9: `scripts/run_uat.py` scenario 8 calls the removed sync endpoint.
- Next step for whoever picks this up: land with `kura` (`land M0b.6`), then M0b.7 on lane B.
- Proposed commit: `feat(M0b): quality gates for never-shrinks, bounded quarantine and fact grain [M0b.6]`, trailer `Module: M0b.6`
  - Files: `src/publisher/quality_gates.py`, `tests/test_quality_gates.py`, `.agents/handoffs/M0b.6.md`
