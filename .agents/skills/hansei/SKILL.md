---
name: hansei
description: Hansei (反省) — Honest reflection at the end of a CricPulse module, or whenever the owner says "hansei", "kaizen check", "what went wrong", "are we looping". Reads git, the handoff notes and the review, proposes at most one change to how the work is done, and never applies it without the owner's yes.
---

# `hansei` — reflection

> **Objective:** after each module, find what went wrong twice and change at most one thing. Kaizen is small.

## When

At the end of every module, after the UAT is signed and before the next module is planned. Or whenever asked.

## Read facts, not memory

1. `git log dev..<module branch>`: commits, fix rounds, documents.
2. `.agents/handoffs/`: every note headed BLOCKED, and why.
3. `docs/reviews/M<n>-REVIEW.md`: findings by round. Did the second look find anything that mattered?
4. The cards: how many were corrected after hand-out, and what each correction was.

## Answer, one screen

1. **What went well** — one or two lines, so it is kept.
2. **What went wrong twice** — only things seen at least twice, each with evidence (a commit, a note, a count).
3. **At most one change** — what, in which file (`AGENTS.md`, a skill, a hook), and **what it removes, named first**.
   A change that removes nothing is not proposed. A rule that must always hold becomes a hook or a script, not a
   paragraph.
4. **What to stop doing** — a step, a document or a skill nobody used.

## Rules

- Propose, never apply. The owner's yes, then one small commit of its own.
- A mistake seen once goes in the handoff; twice, it becomes a Gotcha in `AGENTS.md`; `AGENTS.md` stays under a page.
- Do not redesign the roles mid-module.
