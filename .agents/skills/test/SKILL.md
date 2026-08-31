---
name: test
description: A dedicated QA orchestration skill. Covers backend unit tests, component tests, Playwright E2E tests, snapshot management, and coverage reporting for the KaizenCodes platform.
---

# KaizenCodes Test Orchestration Skill (`test`)

## 🎯 Purpose
Run, diagnose, and manage the full KaizenCodes test suite. Activate this skill when:
- Debugging test failures after a build.
- Running E2E tests after catalog or UI changes.
- Checking code coverage before a PR.
- Playwright snapshots are stale due to catalog count changes.

All commands should be run from the **project root**: `/Users/mrrobot/Desktop/Projects/kaizencodes`.

---

## 🧪 Backend Tests (pytest)

### Run full suite with coverage:
```bash
cd backend && source .venv/bin/activate && pytest
```

### Run specific test file:
```bash
cd backend && source .venv/bin/activate && pytest tests/test_question_service.py -v
```

### Run with coverage report:
```bash
cd backend && source .venv/bin/activate && pytest --cov=app --cov-report=term-missing
```

### Key test files and what they cover:
| File | Coverage |
|:---|:---|
| `tests/test_question_service.py` | Question loading, slug resolution, preview data |
| `tests/test_query_runner.py` | DuckDB execution sandbox, timeout enforcement |
| `tests/test_evaluator.py` | DataFrame comparison, pass/fail logic |
| `tests/test_sql_sanitizer.py` | Block `ATTACH`, `COPY`, `INSTALL`, `LOAD`, `PRAGMA` |
| `tests/test_api.py` | Full integration: `/execute`, `/submit`, `/hint` |
| `tests/test_auth.py` | JWT token flow, Cognito mock |
| `tests/test_serializer.py` | `df_to_json_rows()` type safety |
| `tests/test_dynamodb.py` | DynamoDB table init mock |

### Mocking AWS / Cognito / DynamoDB:
Tests use `unittest.mock` and `moto` (if installed). DynamoDB tests use:
```python
from unittest.mock import MagicMock, patch
@patch("app.db.get_dynamodb_resource")
def test_...(mock_get_resource):
    ...
```
For Cognito, set env vars in `pytest.ini` or `conftest.py` to dummy values. Never use real credentials in tests.

---

## ⚛️ Frontend Component Tests (Vitest)

### Run all component tests:
```bash
cd frontend && npm run test
```

### Run in watch mode (for development):
```bash
cd frontend && npx vitest
```

### Key test areas:
- `src/components/` — unit tests for React components
- `src/lib/` — utility logic (API client, storage helpers)

---

## 🎭 Playwright E2E Tests

### Run E2E tests:
```bash
cd frontend && npm run test:e2e
```

### ⚠️ Snapshot Management (CRITICAL)
Playwright visual snapshot tests will **FAIL** if the question catalog count changes (e.g., after adding a new batch of questions). This is expected behavior. Follow this protocol:

1. **Confirm** the new question count is correct by checking `/api/v1/questions`.
2. **Update snapshots** with:
   ```bash
   cd frontend && npx playwright test --update-snapshots
   ```
3. **Review** the diff of updated snapshot images in `frontend/tests/e2e/__screenshots__/`.
4. **Commit** the new snapshot files: `git add frontend/tests/e2e/__screenshots__/ && git commit -m "test(e2e): update visual snapshots for new question catalog"`
5. **Re-run clean** to confirm all tests pass:
   ```bash
   cd frontend && npm run test:e2e
   ```

### Run E2E with UI (interactive debug mode):
```bash
cd frontend && npm run test:e2e:ui
```

### Prerequisites for E2E:
- Backend must be running on `http://localhost:8000`
- Frontend must be running on `http://localhost:3001`
- Or configure `baseURL` in `playwright.config.ts`

---

## 🔍 Diagnosing Failures

### Pre-commit hook failures (Ruff):
```bash
cd backend && source .venv/bin/activate && ruff check --fix . && ruff format .
```
Common ruff errors in this project:
- `I001` — imports not sorted/formatted (fix with `--fix`)
- `SIM114` — combine redundant `elif` branches
- `DTZ001` — `datetime.datetime()` without `tzinfo` — use `datetime.datetime(..., tzinfo=datetime.timezone.utc)`

### Type errors (TypeScript):
```bash
cd frontend && npx tsc --noEmit
```

### Backend test isolation (if tests interfere):
```bash
cd backend && source .venv/bin/activate && pytest --forked
```
