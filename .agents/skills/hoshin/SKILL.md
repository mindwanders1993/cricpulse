---
name: hoshin
description: Hōshin (方針) — Planner for CricPulse. Takes one module from docs/04_IMPLEMENTATION_PLAN.md §2 through its deep dive (dossier) and task cards before any code, against the PRD, HLD and LLD. Every decision names the road not taken. Activate on "plan M<n>", "deep dive M<n>", "write the cards for M<n>".
---

# `hoshin` — the planner

> **Objective:** a dossier the owner approves and task cards a build session can follow without the conversation that
> produced them. Nothing in `src/` or `tests/` changes in this skill.

## Pre-flight

1. **Module check.** The module is in `docs/04` §2 and its dependencies are Sealed. One module at a time.
2. **Authority.** Read its PRD items (`docs/01`), its HLD section (`docs/02`), its LLD section (`docs/03`) and the
   plan's first-cut scope (`docs/04` §3). The dossier may refine these; it may not contradict a sealed decision.
3. **Code read.** Name the commit the plan was written against. Read the files the module touches; the cards' Owns
   come from here, not from memory.
4. **Simplicity filter.** Minimal files. No abstraction for one use. Reuse the catalog, the golden queries, the
   guard and the existing tests before adding anything.

## Artifacts

### `docs/features/M<n>-<NAME>.md` — the dossier (template: `docs/04` §5.1)

Status line (Draft | Approved by the owner, date) · §0 at a glance · §1 scope and non-goals · §2 what it covers (PRD
rows) · §3 today vs target · §4 decisions · §5 design · §6 files touched, by task · §7 risks and open questions ·
§8 test and UAT plan · §9 task summary.

**§4 Decisions:** one row per `D-n`: question · recommendation · alternative · status. A ruling is written as
**"<chosen>, instead of <alternative>, because <reason>"** and dated. Open rulings are listed for the owner in one
message, each as a question with one recommendation.

### `docs/features/M<n>-TASK-CARDS.md` — the cards (template: `docs/04` §5.2)

- **§0 Before Task 1:** what must be true (clean `dev`, module branch, rulings made).
- **§1 Order:** waves and lanes as a table — task, lane, model · effort, starts when. Wave 0 holds every shared file
  (settings, models, catalog). Lane B is cut as a worktree only after wave 0 is committed. At most two lanes; the
  lanes own disjoint files.
- **§2 Rules for every task:** the module's invariants in one screen.
- **§3 Cards:** one per task `M<n>.<k>`: Goal · **Owns** (every file it may edit, tests included) · Subtasks ·
  **Done when** · one **Verify** command (the card's tests, then the full gate) · Depends.
- For every value one lane produces and another consumes, the card names the producer.
- Before writing a card's Owns, grep for every test that imports or names an owned file, and every file an owned file
  imports. Each one is in Owns or has a line saying why it stays out.

The governor hands out one `/goal` line per card; it never rewrites a card into a prompt.

## Gate

Dossier first: the owner reads §0, §1 and §4 and rules the open decisions. Then the cards. "Build this? yes/no", one
recommendation per open choice. Update the module's Status column in `docs/04` §2 to **Deep dive** on approval.
