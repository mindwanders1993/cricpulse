---
name: pr
description: Use this skill to push the current branch and create a Pull Request via the GitHub CLI.
---

# Phase 4: Publisher (PR Creation)

When activated, execute these steps:

1. **Target Branch Selection**:
   - **Feature / Fix branches (`feat/*`, `fix/*`, `chore/*`)** MUST target **`dev`** (`--base dev`).
   - **Release PRs (`dev → main`)** target **`main`** (`--base main`) only after end-to-end verification in `dev`.

2. **Draft PR Body**: Generate a PR body in a scratch file (`/tmp/pr_body.md`) containing:
   - Target branch (`feature → dev` or `dev → main`).
   - Summary of changes.
   - Verification Evidence (e.g., "Pytest passed", "Playwright E2E passed").
   - Karpathy Checklist ("Surgical changes only").
3. **Pause and Prompt**:
   Output the proposed PR Target, Title, and Body to the user and WAIT:
   > "Ready to publish. Options:
   > [1] Approve (Push and open PR to `dev`)
   > [2] Edit PR Body"
4. **Execute**: If approved, run:
   - `git push -u origin HEAD`
5. **Finalize**: Ask the user if they want to merge the feature PR into `dev` or review on GitHub.
6. **Release Flow (`dev → main`) — 🚫 HARD RULE**:
   - When shipping a release milestone, run the full verification loop on `dev`.
   - The agent may open a Release PR `dev → main` if requested.
   - **CRITICAL**: The agent must **NEVER** merge `dev → main` from the terminal. The merge into `main` MUST ALWAYS be performed by the user directly from the **GitHub Web UI**.


