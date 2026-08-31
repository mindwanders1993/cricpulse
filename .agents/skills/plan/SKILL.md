---
name: plan
description: Use this skill to initiate a new feature or fix. It analyzes the codebase and creates a surgical implementation plan for user approval.
---

# Phase 1: Context & Plan Engineering

When activated, execute these steps:

1. **Understand Goal**: Read the user's request. Ask clarifying questions if the goal or scope is ambiguous.
2. **Context Gathering**: View relevant files in `backend/` or `frontend/` to understand the architecture.
3. **Draft Plan**: Create a markdown artifact outlining:
   - **Goal**: One sentence summary.
   - **Branch**: Proposed branch name created off `dev` (e.g., `feat/...` or `fix/...`).
   - **Files to Modify**: Exact list of files.
   - **Karpathy Check**: Confirm this is the simplest viable approach (Surgical Changes).
4. **Pause and Prompt**: 
   Output the following to the user and WAIT for their response:
   > "Here is the plan. Options: 
   > [1] Approve (Proceed to Build)
   > [2] Ideate (Modify Plan)
   > [3] Reject"
