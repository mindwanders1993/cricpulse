---
name: plan
description: Use this skill to initiate a new feature or fix. It analyzes the codebase and creates a surgical implementation plan for user approval.
---

# Phase 1: Context & Plan Engineering

When activated, execute these steps:

1. **Understand Goal**: Read the user's request. Ask clarifying questions if the goal or scope is ambiguous.
2. **Context Gathering**: View relevant files in `src/`, `conf/`, `scripts/`, or `tests/` across the 3 CricPulse subsystems:
   - **Subsystem 1 (DE Pipeline)**: `src/downloaders`, `src/parsers`, `src/builder`, `src/publisher`, `src/cli.py`
   - **Subsystem 2 (Semantic Layer)**: `conf/semantic_catalog.yaml`, `src/semantic/`
   - **Subsystem 3 (GenAI Microservice)**: `src/ai/`, `src/api/`
3. **Draft Plan**: Create a markdown artifact outlining:
   - **Goal**: One sentence summary.
   - **Branch**: Proposed branch name created off `dev` (e.g., `feat/...`, `fix/...`, or `chore/...`).
   - **Files to Modify**: Exact list of files.
   - **Subsystem Invariants**: Check affected security guardrails (`sqlglot` AST, read-only DuckDB, SHA-256 idempotency).
   - **Karpathy Check**: Confirm this is the simplest viable approach (Surgical Changes, Simplicity First).
4. **Pause and Prompt**: 
   Output the following to the user and WAIT for their response:
   > "Here is the plan. Options: 
   > [1] Approve (Proceed to Build)
   > [2] Ideate (Modify Plan)
   > [3] Reject"
