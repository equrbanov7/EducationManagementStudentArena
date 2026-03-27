# EMS Arena — E2E Test Suite

End-to-end tests for the EMS Arena platform using **Playwright** + **pytest**.

## Directory layout

```
tests/e2e/
├── conftest.py            # Shared fixtures, helpers, autouse skip guard
├── test_smoke.py          # Existing minimal smoke suite (login, dashboard, exams)
├── test_role_journeys.py  # Deterministic multi-role happy paths
├── test_known_regressions.py  # Fixed regressions kept as enforced assertions
├── test_auth_flows.py     # Authentication & account lifecycle
├── test_rbac_access.py    # Role-based access control (RBAC)
├── test_course_workflows.py  # Course management (teacher & student)
├── test_exam_workflows.py    # Exam system (teacher & student)
├── test_security.py       # Security baselines (CSRF, 5xx, data leakage)
├── test_notifications.py  # Notification inbox & unread-count AJAX
└── test_blog_flows.py     # Blog/content pages & audit log
```

## Requirements

| Package | Purpose |
|---|---|
| `pytest` | Test runner |
| `pytest-playwright` | Playwright integration |
| `playwright` | Browser automation |
| `pytest-timeout` | Per-test timeout support |

### Install

```bash
pip install -r requirements/test.txt
pip install pytest-playwright playwright
playwright install chromium
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `BASE_URL` | `http://localhost` | Root URL of the running EMS Arena app |
| `E2E_USERNAME` | *(empty)* | Username for authenticated test flows |
| `E2E_PASSWORD` | *(empty)* | Password for authenticated test flows |
| `E2E_ROLE_PASSWORD` | *(empty)* | Shared password for the deterministic multi-role scenario users |
| `E2E_ORG_SLUG` | `ci-role-matrix-university` | Active organization slug for role-based fixtures |
| `E2E_ISOLATED_ORG_SLUG` | `ci-isolated-university` | Secondary tenant slug for isolation checks |
| `E2E_PENDING_ORG_SLUG` | `ci-pending-university` | Pending organization slug for approval regressions |

> **Security** — Never hardcode credentials inside test files. Always use
> environment variables or a `.env` file that is excluded from version control.

## Running the tests

### Smoke suite only (fastest, ≈30 s)

```bash
BASE_URL=http://localhost:8000 \
E2E_USERNAME=myuser \
E2E_PASSWORD=mypassword \
  pytest tests/e2e/test_smoke.py -v --timeout=60
```

### Full E2E suite

```bash
BASE_URL=http://localhost:8000 \
E2E_USERNAME=myuser \
E2E_PASSWORD=mypassword \
  pytest tests/e2e/ -v --timeout=60
```

### Role-based scenario suite

Seed the deterministic multi-role scenario first, then run the deeper
role-journey and known-regression modules:

```bash
python manage.py seed_ci_e2e_scenario --password "YourSharedScenarioPassword"

BASE_URL=http://localhost:8000 \
E2E_ROLE_PASSWORD="YourSharedScenarioPassword" \
  pytest tests/e2e/test_role_journeys.py \
         tests/e2e/test_known_regressions.py \
         -v --timeout=60
```

### Unauthenticated-only tests (no credentials needed)

```bash
BASE_URL=http://localhost:8000 \
  pytest tests/e2e/ -v --timeout=60 -k "not skipif"
```

### With headed browser (useful when debugging a failing test)

```bash
BASE_URL=http://localhost:8000 \
E2E_USERNAME=myuser \
E2E_PASSWORD=mypassword \
  pytest tests/e2e/ -v --timeout=60 --headed
```

### With video/trace on failure

```bash
BASE_URL=http://localhost:8000 \
E2E_USERNAME=myuser \
E2E_PASSWORD=mypassword \
  pytest tests/e2e/ -v --timeout=60 \
    --video=on-first-retry \
    --tracing=on-first-retry \
    --screenshot=on-first-retry
```

Artefacts are written to `test-results/` by default.

## Seeding a deterministic E2E user

For a fresh database, run the management command to create a university test
user that holds every university role:

```bash
python manage.py seed_ci_e2e_user \
  --username myuser \
  --password mypassword \
  --org-name "My Test University" \
  --org-slug "my-test-university"
```

This command is idempotent — running it again on an existing database will
update the user and organization instead of creating duplicates.

For the fuller multi-role audit scenario, use:

```bash
python manage.py seed_ci_e2e_scenario \
  --password "YourSharedScenarioPassword"
```

This command creates a stable university tenant, owner/admin/teacher/staff/
student accounts, a late-joining student propagation scenario, an isolated
second tenant, and a pending-approval organization used by regression tests.

## CI integration

The E2E suite runs automatically in CI as the **🎭 E2E Smoke Tests** job
defined in `.github/workflows/ci.yml`.  The job:

1. Builds and starts the production Docker stack.
2. Runs `seed_ci_e2e_user` inside the app container.
3. Runs `seed_ci_e2e_scenario` inside the app container.
4. Runs `pytest tests/e2e/ -v --tb=short --timeout=60` on the host runner with screenshots, video, and traces retained on failure.

The CI credentials are stored as workflow-level `env` variables; they are
**not** repository secrets and are safe for non-production CI databases.

## Test design principles

- **No hardcoded credentials** — all credentials come from environment variables.
- **Skip-not-fail** — tests skip gracefully when `BASE_URL` is unreachable or
  credentials are not set, so the suite can be collected without starting the app.
- **Role fixtures** — `conftest.py` now exposes `owner_page`, `org_admin_page`,
  `teacher_page`, `staff_page`, `student_page`, `late_student_page`,
  `resume_student_page`, and `pending_owner_page` for deterministic role flows.
- **Semantic selectors** — tests prefer `input[name='…']`, role selectors, and
  stable CSS classes (`.auth-form`, `.org-card`) over fragile XPath or
  pixel-perfect coordinates.
- **Resilient assertions** — tests check HTTP status codes and the presence of
  key structural elements rather than exact text strings that change with
  translations.
- **Fixed-regression coverage** — `test_known_regressions.py` now keeps the
  highest-risk audit scenarios as normal passing assertions so CI fails if any
  of those bugs reappear.
- **Isolated** — tests do not depend on data created by other tests; they
  either use the seeded CI user's pre-existing data or skip when data is absent.
