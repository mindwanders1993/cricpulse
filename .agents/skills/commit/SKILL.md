---
name: commit
description: Use this skill after the build phase is approved. It prepares a git diff, drafts a conventional commit, and commits the code upon approval.
---

# Phase 3: Verification & Commit

When activated, execute these steps:

1. **Review**: Run `git status` and `git diff` to review the changes. Ensure no scratch files or unrequested changes are included.

2. **Draft Message**: Create a Conventional Commit message (`type(scope): concise description`).

3. **Pause and Prompt**:
   Output the following to the user and WAIT for their response:
   > "Please review the proposed commit.
   > Message: `<proposed-message>`
   > Options:
   > [1] Approve (Commit changes)
   > [2] Edit Message"

4. **Execute**: If approved, run `git add .` and `git commit -m "<message>"`.

5. **Pre-Commit Hook Failure Protocol**:
   If `git commit` is **rejected by the pre-commit hook** (Ruff / ESLint), do NOT just re-run the commit blindly:
   - Run the auto-remediation commands:
     ```bash
     cd backend && source .venv/bin/activate && ruff check --fix . && ruff format .
     cd frontend && npm run lint --fix 2>/dev/null || true
     ```
   - Run `git diff` and **show the user what was auto-fixed**.
   - Only after confirming the auto-fixes are safe, re-run `git add . && git commit -m "<message>"`.
   - If the hook still fails after remediation, diagnose the remaining error manually before proceeding.

6. **Self-Learning Prompt**:
   Output:
   > "Commit successful. Options:
   > [1] Proceed to PR
   > [2] Done (Stay on branch)
   >
   > *Kaizen Check: Did we encounter any workflow friction today? Should I update my `.agents/` knowledge base to improve for next time?*"
