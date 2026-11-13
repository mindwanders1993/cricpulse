---
name: catalog-first
description: Catalog-first protocol for CricPulse. A metric, dimension or entity type is defined in conf/semantic_catalog.yaml and typed in src/semantic/models.py before any tool, golden query, SQL template or prompt uses it. Loaded by build and plan sessions; not in the / menu.
user-invocable: false
---

# `catalog-first`

> **Why:** the catalog is the one place the cricket arithmetic is written down. The golden queries, the stat tools, the
> text-to-SQL prompt and (from M3) the checker all read it. A formula that lives only in code drifts from the others
> silently, and a wrong denominator looks exactly like a right one in a chat answer.

## The rule

Before writing a tool, a query template or a prompt line that computes or names a cricket number:

1. **Find it in the catalog.** `grep -n "<metric>" conf/semantic_catalog.yaml`. If it exists, use its name, its
   formula and its description verbatim.
2. **If it does not exist, add it there first:** name, description, formula, the denominator rule (legal balls,
   balls faced, dismissals), the extras rule (byes, leg-byes, wides, no-balls), and the format it applies to.
3. **Type it** in `src/semantic/models.py` if it is returned by a tool.
4. **Test it** in `tests/test_semantic.py` with a hand-computed figure from a fixture match.
5. Only then write the code that uses it.

## What this forbids

- `SUM(runs)/COUNT(*)` typed into a golden query without the catalog naming that metric.
- A prompt that explains strike rate in its own words instead of quoting the catalog description.
- A chart or tile label that names a metric the catalog does not have.

## Where the catalog is silent

Context-adjusted metrics (par-relative scoring, true strike rate, true economy) are not in the catalog yet. They are
planned requirements, not something a build session invents: stop with a BLOCKED note that names the missing metric.
