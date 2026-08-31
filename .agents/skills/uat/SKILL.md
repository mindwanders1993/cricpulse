---
name: uat
description: Autonomous User Acceptance Testing (UAT) Orchestrator. Executes Playwright E2E test suites, captures multimodal screenshots, performs visual state verification, and generates structured execution reports according to docs/UAT_MANUAL_TESTING_GUIDE.md.
---

# 🥋 KaizenCodes Autonomous UAT Skill

Use this skill to execute, monitor, and diagnose comprehensive User Acceptance Testing (UAT) across all 10 feature modules of KaizenCodes.

## 🚀 Usage Modes

### 1. Full Platform UAT Execution
Run all 30+ automated test suites and generate `docs/UAT_EXECUTION_REPORT.md`:
```bash
cd frontend && npx playwright test
```

### 2. Targeted Suite Execution
Run specific UAT test suites:
- **Auth & Account Lifecycle**: `cd frontend && npx playwright test e2e/auth.spec.ts`
- **Guest Mode & Progress**: `cd frontend && npx playwright test e2e/guest.spec.ts`
- **Catalog & Discovery**: `cd frontend && npx playwright test e2e/catalog.spec.ts`
- **Execution & Diff Engine**: `cd frontend && npx playwright test e2e/execution.spec.ts`
- **SQL IDE & Profiler**: `cd frontend && npx playwright test e2e/workspace.spec.ts`
- **Navigation & Themes**: `cd frontend && npx playwright test e2e/navigation.spec.ts`

### 3. Visual & Responsive Verification
- **Pixel Visual Snapshot**: `cd frontend && npx playwright test e2e/visual.spec.ts`
- **Update Snapshots**: `cd frontend && npx playwright test e2e/visual.spec.ts --update-snapshots`

---

## 📋 Defect Diagnosis & Auto-Remediation Protocol

If a test case fails during UAT:
1. **Locate Error Context**: Inspect `frontend/test-results/<test-name>/error-context.md` and failure screenshots in `frontend/test-results/<test-name>/test-failed-1.png`.
2. **Classify Issue**:
   - *Selector Drifting*: Use semantic text or accessible role locators (`getByRole`, `getByPlaceholder`).
   - *Asynchronous Race Condition*: Use `expect(locator).toBeVisible({ timeout: 15000 })`.
   - *Backend 500 / Data Error*: Run `pytest` and inspect FastAPI endpoint traces.
3. **Generate Defect Report**: Format defect report matching [`docs/UAT_MANUAL_TESTING_GUIDE.md`](file:///Users/mrrobot/Desktop/Projects/kaizencodes/docs/UAT_MANUAL_TESTING_GUIDE.md) template.

---

## 📊 Automated Reports
Every run automatically outputs an audit log to [`docs/UAT_EXECUTION_REPORT.md`](file:///Users/mrrobot/Desktop/Projects/kaizencodes/docs/UAT_EXECUTION_REPORT.md) containing:
- Test IDs (`TC-AUTH-01`, `TC-EXEC-02`, etc.)
- Exact execution time in milliseconds
- PASS / FAIL status icon
- Error traces and failure screenshot paths
