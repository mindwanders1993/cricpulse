---
name: takumi
description: Takumi (匠) — Surgical build loop for CricPulse. How a build session works one task card under a /goal: stay inside Owns, ruff and pytest after every change, prove with the card's Verify, stop when confused, end with a handoff note. Loaded by a build session; never by the governor.
---

# `takumi` — the build loop

> **Objective:** one task card, built as it says, proven in the conversation, handed off in a note. Nothing more.

## The inner loop

```
1. Read the card and the dossier section it names ──▶ 2. Edit surgically ──▶ 3. ruff check ──▶ 4. pytest (the card's tests) ──▶ repeat
```

```bash
source .venv/bin/activate
ruff check src tests && ruff format src tests
python -m pytest <the card's test files> -q
python -m pytest -q                      # the full suite, before claiming done
```

## Rules

- **Proof (0) first:** `git rev-parse --show-toplevel` prints the checkout the goal names, or the session stops.
- **Stay inside Owns.** The card lists the files this task may edit. A change needed anywhere else is not made: write a
  report headed **BLOCKED** that names the conflict, and stop.
- **The dossier wins.** If the card, the dossier and the code disagree, stop with a BLOCKED note; never guess.
- **No git writes.** `git status`, `git diff`, `git log`, `git check-ignore` only. Another session lands it (`kura`).
- **Prove it.** Run the card's Verify after the last file change and show its output and exit code.
- **Stop when confused.** The same failure after two repair attempts: stop, show the diagnostic and both attempts in the
  handoff note, headed BLOCKED. Never `# noqa`, `# type: ignore` or a loosened assertion to get green.
- **Never weaken a test.** No deletion, no skip, no relaxed assertion, beyond what the card names.
- **Cite the decision.** A branch, guard or constant that exists because of a ruling carries a one-line comment naming
  it (`M0b dossier D-5`). A comment that restates the code is not a citation.
- **Data files are not fixtures.** Tests build what they need in a temp directory; nothing under `data/` is read or
  written by a test.
- **A designed stop is a clean stop.** Wrong folder, the tool-call cap, a conflict: one line, the note, stop.

## Invariant checkpoints while building

1. **Never shrink:** does any path write `LATEST.json`, or overwrite a published file in place, before the gates run?
2. **Directory storage:** any `google.cloud` import? Remove it; storage is a path.
3. **Catalog:** any cricket formula typed into Python or SQL that the catalog does not define? Define it there first
   (`catalog-first`).
4. **One door:** any DuckDB query from a request path that does not go through the guard?
5. **Secrets:** any key, token or `.env` value in code, a fixture or a log line?

## End with the handoff note — `.agents/handoffs/<task-id>.md`

Branch and worktree · state (done · partial · blocked) · what changed · the verification run · each Done-when line with
the test or file that covers it · open issues · next step · proposed commit
(`<type>(<scope>): <summary> [<task-id>]`, trailer `Module: <task-id>`). Format in `sensei`.

The last message is three short lines: what now works, whether it is proven (yes, no, stopped early), and what happens
next. Everything else is in the note.
