# Codex Task — Full Verification of the Role-Folder Refactor (F0–F7) + Today's Change Wave

## Context

You are working in the EMSArena repository (Django 5.2 modular monolith, PostgreSQL+RLS multi-tenant exam platform; server-rendered templates, no React). Read `AGENTS.md` FIRST and obey it strictly — especially §1 (facade/import-surface preservation), §5 (module-boundary ratchet gate), §6 (role-based view skeleton and relative-import bump rules).

Today's change wave (already implemented, locally green on the sqlite fast lane) includes:

1. **F0–F7 role-folderization** — `views` of 9 apps were split into role packages with facades that preserve the full import surface (no URL names/paths changed anywhere):
   - `assignments`, `projects` → `views/{student,teacher,shared}/`
   - `labs` → same, with `submissions.py` SPLIT by role (student: autosave/submit; teacher: listing/grading)
   - `courses` → same, with `StudentCoursesView` extracted from `membership.py`; dashboard is role-branched → `shared/`
   - `appeals` → `views/{student,teacher,shared}` (old single `views.py`); `appeal_detail` is shared (owner OR reviewer)
   - `organizations` → `views/{member,org_admin,shared}` (old single `views.py`); `structure_views/` imports 7 private helpers via the facade
   - `accounts` → `views/superadmin/` package + the 6 `_superadmin_*.html` section templates moved to `profile/sections/superadmin/` (13 path references updated)
   - `blog` → `views/{public,author,moderator,shared}`; `posts.py` split three ways; `legacy_urls.py` now imports `views.public.legacy`
2. **M1 boundary gate** — `scripts/module_deps.py` (`--check` in CI via `_lint.yml`): no NEW cyclic module pair beyond `scripts/module_deps_baseline.json` (18 frozen), no NEW `core→apps` target.
3. Earlier same-day phases: infra (compose limits/logging/healthcheck/beat/alerting), deps cleanup, i18n additions (labs teacher submissions keys ×7 in 4 locales; `core.errors.csrf` ×12), CSS token/inline-style migration, coverage gate raised to 68 with `--cov=apps --cov=core --cov=config`.

## Your Job

Run the FULL verification matrix below. If anything fails, make the **minimal correct fix** and re-run until everything is green. Then produce a report.

### Hard rules (do not violate)

- NEVER merge role packages back, remove facade re-exports, rename URL names, or edit `__all__` to "fix" a failure.
- Ratchet baselines (`scripts/module_size_budget.json`, `scripts/module_deps_baseline.json`) may only SHRINK; growing them requires an explicit justification comment in your report.
- If a test asserts an OLD file path or previously-inline content, MODERNIZE THE TEST to the new architecture while preserving the behavioral contract. Precedents already in the repo: `test_take_exam_uses_five_minute_server_autosave_with_jitter` (asserts static-file content + script src), `ExamSupervisionJavaScriptAssetTests` (reads the package glob), `test_register_wizard_js_binds_next_and_back_buttons` (points at `register_wizard/submit.js`).
- Legitimate skips (do NOT "fix"): `-m postgres`-marked tests on the sqlite lane; 2 blog seed-shape tests guarded by `skip_unless_seed_migrations`; e2e tests gated on `E2E_USERNAME/E2E_PASSWORD`.
- Missing-name errors in split modules are fixed by ADDING the right import per AGENTS §6 rule 3 (depth bumps: file formerly at app root → `views/<role>/` needs `.x`→`...x`; formerly at `views/` → `..x`→`...x`; `._helpers` → `..shared._helpers`). Check FUNCTION-BODY lazy imports too, not just headers.

### Environment

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements/local.txt -r requirements/test.txt
export SECRET_KEY=codex-verify DJANGO_SETTINGS_MODULE=config.settings.test
```

### Verification matrix (run IN ORDER; every step must pass)

1. **Static gates**
   ```bash
   python scripts/check_module_size.py --check
   python scripts/module_deps.py --check
   black --check . && isort --check-only --profile black . && flake8 .
   ```
2. **Django integrity**
   ```bash
   DATABASE_URL="sqlite://" python manage.py check
   DATABASE_URL="sqlite://" python manage.py makemigrations --check --dry-run
   ```
3. **Import-surface spot checks** (all must import without error):
   ```bash
   DATABASE_URL="sqlite://" python - <<'EOF'
   import django; django.setup()
   from apps.assignments.views import create_assignment, submit_assignment, search_students
   from apps.projects.views import create_project, submit_project, api_get_students
   from apps.labs.views import auto_save_answer, submit_lab, lab_submissions, grade_submission_page, preview_randomization
   from apps.courses.views import CourseDashboardView, StudentCoursesView, MyCoursesListView, link_exam_to_course
   from apps.courses.views.shared._helpers import _student_users_queryset, IsTeacherMixin
   from apps.appeals.views import appeal_create, appeal_detail, review_appeal, build_my_appeals_context, _can_open_appeal_management
   from apps.organizations.views import select_organization, organization_dashboard, build_organization_structure_context, _can_view_structure, _structure_ajax_response
   from apps.accounts.views.superadmin import superadmin_organizations, _notify_superadmins_of_pending_org
   from apps.blog.views import home, post_detail, create_post, review_post, register_view
   from apps.blog.views.public.legacy import legacy_article_detail
   print("IMPORT SURFACE OK")
   EOF
   ```
4. **URL reverse smoke** — reverse one representative name per refactored app (`assignments:create_assignment`, `projects:create_project`, `labs:lab_submissions`, `courses:course_dashboard`, `appeals:appeal_create`, `organizations:dashboard`, `accounts:profile`, blog `article_detail` + one legacy route) via a small shell script; all must resolve.
5. **Sqlite fast lane — FULL suite** (expected ≈2130+ passed, 0 failed; only the legitimate skips listed above):
   ```bash
   DATABASE_URL="sqlite://" pytest apps core tests --ignore=tests/e2e --ignore=tests/load \
     --no-migrations -p no:cacheprovider -q
   ```
   Recent reference counts: `apps/accounts+apps/exams` = 851 passed; everything else (apps minus those two + core + tests/integration) = 1283+ passed; `organizations + tenant/RBAC integration` = 172 passed.
6. **PostgreSQL lane (AUTHORITATIVE — includes RLS)**: start Postgres+Redis (`docker compose up -d postgres redis` from `docker-compose.yml`, or use CI-equivalent services), then WITH migrations:
   ```bash
   export DATABASE_URL=postgres://<user>:<pass>@localhost:5432/<db>
   pytest --ds=config.settings.test --ignore=tests/e2e \
     --cov=apps --cov=core --cov=config --cov-fail-under=68 -q
   ```
   All `-m postgres` RLS/constraint tests and the 2 blog seed-shape tests MUST run and pass here. Coverage must be ≥68%.
7. **i18n runtime spot checks** (4 languages each):
   - `pgettext("labs.view.message", "bulk_delete_success").format(count=3)` → az "3 cavab silindi." / ru "Удалено ответов: 3." / tr "3 cevap silindi." / en "3 submissions deleted."
   - `pgettext("core.errors.csrf", "Refresh the page")` → az "Səhifəni yenilə".
8. **Stale-path zero-check** (all greps must return NOTHING):
   ```bash
   grep -rn "accounts/profile/sections/_superadmin" apps --include="*.py" --include="*.html"
   grep -rn "from .views.legacy import" apps/blog/legacy_urls.py
   grep -rn "courses.views._helpers\b" apps core tests --include="*.py" | grep -v shared
   grep -rn "apps.organizations.views import" apps | grep -vE "structure_views|views/"
   ```
9. **Docker config sanity** (no docker build needed if unavailable):
   ```bash
   GRAFANA_ADMIN_PASSWORD=x SECRET_KEY=x POSTGRES_DB=d POSTGRES_USER=u POSTGRES_PASSWORD=p \
   REDIS_PASSWORD=r ALLOWED_HOSTS=localhost CSRF_TRUSTED_ORIGINS=http://l SITE_URL=http://l \
   ADMIN_ALLOWED_IPS=127.0.0.1 docker compose -f docker-compose.prod.yml -f docker-compose.ci.yml config -q
   ```
10. **(Optional, if Docker available)** run the CI-equivalent prod smoke + Playwright e2e exactly as `.github/workflows/_prod-smoke.yml` and `_e2e-smoke.yml` do (env blocks included there), seeding via `manage.py seed_ci_e2e_user` / `seed_ci_e2e_scenario`.

### Failure triage cheat-sheet

| Symptom | Correct fix |
|---|---|
| `NameError`/`F821` in a split module | Add import from `..shared._helpers` / sibling per AGENTS §6.3; check body-level lazy imports |
| `ModuleNotFoundError: apps.X.views.<role>.<appmodule>` | Relative depth bump missed (`.scoping`→`...scoping` etc.) |
| `ImportError: cannot import name '_x' from apps.X.views` | Re-export the private name in the facade (AGENTS §1) |
| Test asserts old template/JS path or inline content | Modernize the test (see precedents above) |
| `module_deps --check` new cycle | Replace the direct cross-app import with the target module's service/selector facade — do NOT grow the baseline casually |
| E402/blank-line lint in generated files | `black` + `isort --profile black`, keep `logger = logging.getLogger(__name__)` AFTER all imports |

### Deliverable

A report containing: (a) pass/fail table for steps 1–10 with final counts; (b) unified diff of every fix you made with one-line justification each; (c) explicit confirmation that no facade export, URL name, or ratchet baseline was weakened; (d) list of any remaining known-legitimate skips. Do not push; leave changes committed locally in a single commit titled `test: verify & stabilize role-folder refactor (F0–F7)`.
