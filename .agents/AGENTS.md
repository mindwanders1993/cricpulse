# KaizenCodes Kaizen Governor

You are operating within the KaizenCodes repository. We use a Goal-Driven, Context & Loop Engineering methodology based on Kaizen and Karpathy principles (Simplicity First, Surgical Changes).

## 🚦 Operational Workflow (Strict Protocol)
You must guide the user through the following chained phases for any feature or fix. Do not skip phases unless explicitly requested by the user (Option B - Soft Enforcement).

1. **Plan**: Activate the `plan` skill to analyze requirements and propose a strategy.
2. **Build**: Activate the `build` skill to implement code and run tests loops.
3. **Commit**: Activate the `commit` skill to review diffs and create conventional commits.
4. **PR**: Activate the `pr` skill to generate a PR body and push.

## 🌿 Git Branching & Staging Model (`feature → dev → main`)
Following the proven pattern from `cockroachpartyfun_project`:
- **`dev` (Staging / Integration)**: Primary development branch.
  - All new feature/fix/chore branches branch from `dev` (`git checkout dev && git pull origin dev && git checkout -b feat/<description>`).
  - Feature PRs target **`dev`** (`--base dev`).
- **`main` (Production Releases)**:
  - Changes are tested and verified end-to-end on `dev` before releasing.
- **🚫 HARD RULE: `dev → main` Merge**:
  - The agent must **NEVER** merge `dev` into `main` via terminal / CLI (`gh pr merge` or `git merge`).
  - The `dev → main` release merge MUST ALWAYS be performed manually by the user from the **GitHub Web UI**.
- **Never reuse a merged branch**: Always start fresh from `dev`.

## 🎨 UX / Frontend Tier Execution Model
For large frontend refactors or rebrand modules (like `feat/kaizencodes-rebrand-ux`), use a **Tiered Parallel Execution Model**:
- **Tier 0 (Foundation — Sequential)**: Design tokens, project-wide text rebrand. Must complete first.
- **Tier 1 (Core UI — Parallel)**: 4 independent UI modules that can run simultaneously (e.g., Landing Page, Questions List, Auth Modal, AI Sensei Gate).
- **Tier 2 (Session & Backend — Parallel)**: Session timer hooks, backend metadata rebrand.

Reference implementation: see the KaizenCodes Modular Implementation Plan in the Antigravity artifacts for the full module breakdown and goal prompts.

## 📚 Available Skills
| Skill | When to Use |
|:---|:---|
| `plan` | Starting any new feature or fix |
| `build` | Implementing an approved plan (includes linting + test loops) |
| `commit` | After build is approved — stages, drafts, and commits |
| `pr` | Pushes branch and opens PR via GitHub CLI |
| `add_sql_question` | Adding 1–5 new SQL challenges interactively or in batch |
| `batch_add_sql_questions` | Autonomous factory for 5–10 questions with zero interruption |
| `ingest_kb` | Scraping raw SQL questions from GitHub repos or web sources |
| `test` | Running / debugging backend pytest, Vitest, or Playwright E2E |
| `uat` | Autonomous UAT Orchestrator, visual checks & markdown report generator |
| `dev_env` | Starting the app, fixing CORS, managing ports, Docker, `.env` |

## ⚠️ Token & Context Monitoring
You do not have a raw token counter, but you MUST manage context bloat:
- Periodically clear your scratchpads and drop old file contents from memory.
- At the end of the **Build** phase, summarize your actions.
- Explicitly prompt the user: *"Notice: If token usage in your UI is getting high, we can use the `/goal` command to start a fresh, focused session using our current summary."*

## 🔄 Interactive Chaining & Self-Learning
- **Prompt Options**: At the end of every phase, provide explicit bracketed options to the user (e.g., `[1] Approve to Build, [2] Ideate`). Wait for their selection before proceeding.
- **Continuous Improvement**: During the Commit/PR phase, ask the user if this workflow could be improved. If so, you are authorized to edit these `.agents/` files to update your own knowledge base.
