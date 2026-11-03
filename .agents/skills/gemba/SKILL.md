---
name: gemba
description: Gemba (現場) — Acceptance on the real service for CricPulse. Runs the UAT harness (scripts/run_uat.py) and the module's scripted chat journeys against a real snapshot, records the result in docs/uat/M<n>-UAT.md for the owner to sign. Activate on "gemba", "UAT", "walk the chat", "uat M<n>".
---

# `gemba` — acceptance on the real service

> **Objective:** show what the running service does for the journeys the dossier promises, on real data, and record it.

## Commands

```bash
source .venv/bin/activate
python scripts/run_uat.py                       # the automated harness (health, leaderboards, guard, agents, sync)
bash scripts/run_local.sh                       # the service on :8000 for hand-driven chat journeys
curl -s localhost:8000/ready | python3 -m json.tool
```

A UAT run uses a real snapshot under `data/` (or the harness's fixture build), never the test suite's temp databases.
It runs alone: no build session on the same data directory at the same time.

## The journeys

The dossier's §8 lists them. Each journey is a question a user would type, the answer anatomy expected (insight, numbers,
chart, table, receipt), and the invariant it proves. From M2 on, every number in the recorded answer is checked
against the tool output in the receipt.

## The record — `docs/uat/M<n>-UAT.md`

```markdown
# UAT: M<n> — <name>
- Date · Branch · Commit · Snapshot (version, data cutoff) · Model (live or mock)
- Harness: `python scripts/run_uat.py` → <passed>/<total>, exit <code>
## Journeys
| # | Question | Expected | Observed | Pass |
## Invariants observed (never shrinks, receipt present, numbers match tool output …)
## Owner sign-off: ____ (date)
```

The owner signs the file; that is Definition of Done row 6. A failing journey is a finding for a fix card, never
something `gemba` repairs.
