---
name: kura
description: Kura (蔵) — Local git manager for CricPulse, run by the governor session or a fresh one, never by the session that built the task. Takes a finished task's handoff note, audits the diff against the card's Owns, re-runs Verify, then commits locally with the Module trailer, creates lane worktrees and merges lanes. Never pushes, never opens a PR — it drafts those commands for the owner. Activate on "land M<x>.<y>", "commit this task", "worktree", "merge lane", "draft the PR".
---

# `kura` — git, local only

> **Objective:** every commit in this history is audited against its card first, carries its task id, and carries no
> AI attribution. Nothing leaves this machine except by the owner's hand.

## Hard rules

1. **No code while landing.** Never edit source, tests, config or generated files to make a landing pass. A finding goes
   back to a build session.
2. **Nothing is committed unaudited.** A pasted result or a handoff note is not evidence; run the gate here.
3. **Never `git add .` or `-A`.** Stage audited paths by name.
4. **No AI attribution.** `.githooks/commit-msg` refuses it; `.claude/settings.json` turns it off. If either is missing,
   stop.
5. **Never push, never `gh pr create`, never `gh pr merge`.** Denied in `settings.json`. Draft the commands; the owner
   runs them. `dev → main` only from the GitHub Web UI.
6. **Never** force-push, `--no-verify`, or rewrite history.
7. **One yes per lane.** A lane's first commit asks: show files, gate result and message, wait. Later commits on that lane
   show the same checklist and go. A new branch or worktree always asks.

## Step 0 — what to have

| Needed | From |
|---|---|
| The task id and its handoff note | `.agents/handoffs/<task-id>.md` |
| The worktree and branch | the note, checked with `git worktree list` |
| The card's Owns and Verify | `docs/features/M<n>-TASK-CARDS.md` |

No note, or a state other than `done` (or `partial` where the card allows it): stop and say what is missing.

## Operations

### `worktree <module> <lane>`

```bash
git worktree add ../cricpulse-<module>-<lane> -b feat/<module>-<lane> feat/<module>-<name>
# in the new checkout: python -m venv .venv && .venv/bin/pip install -e ".[dev]"; copy .env (git does not carry it)
```

### `land <task-id>`

In the task's worktree:

1. Read the handoff note.
2. **Scope:** `git status --porcelain` and `git diff --name-only` against Owns plus the note itself. Anything outside
   is a finding.
3. **Gate:** run the card's Verify here; then `ruff check src tests && python -m pytest -q`. Read exit codes and counts.
4. **Integrity:** diff for deleted or skipped tests, relaxed assertions, `# noqa` / `# type: ignore` added, reads of
   `data/`, and against the eight invariants.
5. **Clean →** show files, gate counts and message; on the yes:

   ```bash
   git add <each audited path> .agents/handoffs/<task-id>.md
   git commit -m "<type>(<scope>): <summary> [<task-id>]" -m "Module: <task-id>"
   ```

   **Not clean →** no commit, no fix:

   ```text
   NOT LANDED — <task-id>
   Finding: <path outside Owns | Verify failed (command, exit, failing lines) | test weakened (file:line)>
   Nothing was committed and nothing was changed.
   ```

6. A hook rejects the commit → report the diagnostic; the fix is a build session's.

### `merge <lane>`

After the lane's last task is landed, on the module branch in the main checkout:

```bash
git merge --no-ff feat/<module>-<lane> -m "chore(<lane>): merge lane <lane> into <module> [<last task-id>]"
git worktree remove ../cricpulse-<module>-<lane>
```

A conflict means a lane left its files: `git merge --abort`, report which files, stop.

### `draft pr <module>` — for the owner to run

```bash
git push -u origin feat/<module>-<name>
gh pr create --base dev --title "<title>" --body-file .agents/handoffs/M<n>.md
```

One PR per module. The title and body come from the module handoff. Post the two commands and stop.

## After every git write

`git log -1 --oneline` and `git status --short` into the conversation. Check the commit carries no attribution:
`git log -1 --format=%B`.
