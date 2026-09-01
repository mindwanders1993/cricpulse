# CricPulse Kaizen Governor

You are operating within the **CricPulse** repository — a serverless cricket lakehouse and generative multi-agent platform. We use a Goal-Driven, Context & Loop Engineering methodology based on Kaizen and Karpathy principles (Simplicity First, Surgical Changes, Scale-to-Zero).

## 🚦 Operational Workflow (Strict Protocol)
You must guide the user through the following chained phases for any feature or fix. Do not skip phases unless explicitly requested by the user:

1. **Plan**: Activate the `plan` skill to analyze requirements and propose a surgical strategy.
2. **Build**: Activate the `build` skill to implement code, enforce security invariants, and run tests loops.
3. **Commit**: Activate the `commit` skill to review diffs and create conventional commits.
4. **PR**: Activate the `pr` skill to generate a PR body and push to GitHub.

## 🌿 Git Branching & Staging Model (`feature → dev → main`)
- **`dev` (Staging / Integration)**: Primary development branch.
  - All new feature/fix/chore branches branch from `dev` (`git checkout dev && git pull origin dev && git checkout -b feat/<description>`).
  - Feature PRs target **`dev`** (`--base dev`).
- **`main` (Production Releases)**:
  - Changes are tested and verified end-to-end on `dev` before releasing.
- **🚫 HARD RULE: `dev → main` Release Merge**:
  - The agent must **NEVER** merge `dev` into `main` via terminal / CLI (`gh pr merge` or `git merge`).
  - The `dev → main` release merge MUST ALWAYS be performed manually by the user from the **GitHub Web UI**.
- **Never reuse a merged branch**: Always start fresh from `dev`.

## 🏛️ 3-Subsystem Architectural Guardrails
1. **Subsystem 1: Headless DE Pipeline** (`src/downloaders`, `src/parsers`, `src/builder`, `src/publisher`)
   - Pure Polars + DuckDB, strictly zero always-on Spark/Airflow compute.
   - Idempotency enforced via SQLite SHA-256 audit tables (`match_file_audit`, `register_audit`).
2. **Subsystem 2: AI-Ready Semantic Layer** (`conf/semantic_catalog.yaml`, `src/semantic/`)
   - Mathematical formulas locked in YAML code.
   - Bowling economy strictly excludes byes & leg-byes.
   - 3-tier DuckDB entity resolution (Exact, Alias, Fuzzy) with zero heavy vector database overhead.
3. **Subsystem 3: Generative AI Microservice** (`src/ai/`, `src/api/`)
   - Scale-to-Zero FastAPI service querying immutable DuckDB snapshots in memory.
   - Hardened `sqlglot` AST security guardrails (read-only `SELECT`/CTE only, strict `gold.*` schema allowlist).
   - Autonomous 3-turn reflection loops for Text-to-SQL error self-correction.

## 📚 Available Skills
| Skill | When to Use |
|:---|:---|
| `plan` | Starting any new feature or fix |
| `build` | Implementing an approved plan (includes linting + test loops) |
| `commit` | After build is approved — stages, drafts, and commits |
| `pr` | Pushes branch and opens PR via GitHub CLI |
| `test` | Running / debugging backend pytest suite |
| `dev_env` | Local development server, Docker, `.env` configuration |

## ⚠️ Token & Context Monitoring
- Periodically clear scratchpads and drop old file contents from memory.
- At the end of the **Build** phase, summarize your actions.
- Explicitly prompt the user: *"Notice: If token usage in your UI is getting high, we can use the `/goal` command to start a fresh, focused session using our current summary."*

## 🔄 Interactive Chaining & Self-Learning
- **Prompt Options**: At the end of every phase, provide explicit bracketed options to the user (e.g., `[1] Approve to Build, [2] Ideate`). Wait for their selection before proceeding.
- **Continuous Improvement**: Authorized to edit these `.agents/` files to update your own knowledge base.
