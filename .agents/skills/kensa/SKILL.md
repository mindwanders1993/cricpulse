---
name: kensa
description: Kensa (検査) — Module review for CricPulse, run once per module in a fresh session that built none of it. Five lenses — correctness against the dossier, data integrity and the eight invariants, security, tests, waste — written to docs/reviews/M<n>-REVIEW.md. Reads and reports; fixes nothing. Activate on "review M<n>", "kensa".
---

# `kensa` — the review

> **Objective:** one honest, read-only review per module, on the merged module branch, before the owner merges it.

## Who reviews

- **A fresh session, Fable · high, never the author's or the governor's.** It fixes nothing and runs no git write.
- **After the lanes are merged.** Seams between lanes first: every value one lane produces and another consumes,
  checked on the real code, not a test's fixture.
- **Findings become fix-round cards.** After the fix round, another fresh session adds a second look at the fix diff
  only, in the same file.

## Gather

`git diff dev...<module branch>` · `.agents/handoffs/M<n>*.md` · the dossier · the cards · `AGENTS.md`. Run the
gates yourself and record the exit codes; a pasted result is not evidence.

## The five lenses

1. **Correctness against the dossier.** Each Done-when line met? Anything dropped, invented, or quietly narrowed?
   Does every ruling-driven branch cite its ruling?
2. **Data integrity and the eight invariants.** Can live data shrink? Is any published file overwritten in place? Any
   GCS SDK? Any cricket formula outside the catalog? Any DuckDB access from a request that bypasses the guard? For
   cricket arithmetic: recompute one batting and one bowling figure by hand from a fixture and compare.
3. **Security.** Path handling under `data_dir`; the `sqlglot` guard (schema allowlist, statement type, row limit,
   timeout); secrets in code, logs or fixtures; web text treated as data; request size and rate limits where the
   module adds a route.
4. **Tests.** Weakened, skipped, deleted or rewritten to pass? Does a test prove each Done-when line? Does any test
   read `data/`? Is the mock boundary the network and nothing closer?
5. **Waste.** Dead routes, dead settings, unused modules, leftover legacy paths the module was meant to retire, files
   outside any card's Owns.

## The file — `docs/reviews/M<n>-REVIEW.md`

```markdown
# Review: M<n> — <name>
- Reviewer: kensa, a fresh session that built none of this
- Date · Branch · Commit
## Verdict: APPROVED | CHANGES REQUIRED
## 1. How this was reviewed (read in full / not read)
## 2. Gates as run here (command → exit code, counts)
## 3. Findings, by severity (F1 … each with file:line, evidence, what must change)
## 4. The five lenses (PASS | FLAGGED, one paragraph each)
## 5. Nits (at most five)
## 6. Second look (added after the fix round)
```

First line of the verdict to the governor: `CONTINUE` or `ESCALATE: <reason>`. Then the Kaizen question: did anything
go wrong twice?
