# Codex Prompt — M3 "Clean Core + Public Facades" Verification (EMSArena)

Copy everything below this line into Codex.

---

You are verifying the "M3" refactor stage in EMSArena (Django 5.2 multi-tenant exam/LMS platform, PostgreSQL RLS, Daphne/Channels, Celery). M2 (zero cyclic module pairs) was already verified by you at the previous step. M3 finishes the modular-monolith hardening in two parts, again **with zero URL, template, or behavior changes**:

- **M3-A:** all `core → apps` import edges dissolved (10 → 0). `core/` now imports NO app module.
- **M3-B:** every module with a real cross-module API got a `public.py` facade (10 modules, 91 names); assignments/labs/projects were migrated to consume `task_submission_core` through its facade.

Your job: run the full verification lanes, fix ONLY test-side or trivially-mechanical issues, and report anything that looks like a real behavior change. Both guard gates must stay at zero: `python scripts/module_deps.py --check` (0 cyclic pairs AND 0 core→apps targets).

## What changed — M3-A (core cleanup)

1. **Audit helpers moved down to core:** `log_action` and `log_superadmin_cross_org_action` moved from `apps/audit/utils.py` to **`core/audit.py`** (AuditLog resolved via `django_apps.get_model("audit", "AuditLog")` inside `log_action`). `apps/audit/utils.py` keeps `AuditLogMixin` and re-exports both functions, so `from apps.audit.utils import log_action` still works everywhere. Core consumers (`core/admin_auth.py`, `core/admin_security.py`, `core/permissions.py`, `core/tasks.py`) now import from `core.audit`.
2. **Permission-string matching moved down to core:** `has_permission`, `_permission_variants`, `_wildcard_variants`, `PERMISSION_PREFIX_ALIASES` moved from `apps/organizations/permissions.py` into **`core/permissions.py`** (pure string logic). `apps/organizations/permissions.py` re-exports all four; the rest of that module (PERMISSION_CATEGORIES, grant-prefix helpers, etc.) is unchanged.
3. **Admin 2FA OTP inverted via a FAIL-CLOSED hook registry:** new **`core/auth_otp.py`** with hooks `issue_email_otp(user, *, purpose)` and `verify_otp_code(user, *, code, purpose)`; unregistered hooks raise `RuntimeError` (2FA must not silently pass). `AccountsConfig.ready()` registers adapters around `apps.accounts.services.{issue_email_otp, verify_otp_code}`. `core/admin_auth.py` and `core/admin_site.py` use the hooks + `get_model("accounts", "EmailOTP")` for `EmailOTP.Purpose.ADMIN_LOGIN`.
4. **live_exam read-side cache moved to its app:** `get_cached_session_settings`, `get_cached_exam_question_ids`, and `warm_session_settings_cache` moved from `core/cache.py` / `core/tasks.py` to **`apps/live_exam/cache.py`** (importing key builders, `_safe_cache_get`, and TTL constants from `core.cache`). Invalidators (`invalidate_session_settings_cache`, `invalidate_exam_question_ids_cache`, `invalidate_exam_metadata_cache`) stay in `core.cache` — their callers (exams views, live_exam session_settings) are untouched. Tests in `tests/integration/test_security_and_architecture.py` were updated to import from the new locations. Note: the moved getters have no production callers (read paths never used them) — this is a relocation of dormant API, not a behavior change.
5. **Remaining core model references switched to `get_model`:** `core/tenancy.py` (Membership, Organization ×2 sites), `core/media_views.py` (11 model lookups: ExamAnswerFile, ExamAnswer, Exam+ExamAttempt, ProjectSubmission, Lab/LabQuestion/LabSubmission/LabAnswer, CourseResource, TrialExamRequest), `core/helpers.py` (Course), `core/email_tasks.py` (blog Post). No import of any `apps.*` module remains anywhere under `core/` (the `scripts/module_deps.py` scanner is regex-based and counts even commented/docstring occurrences of `from apps.<x>`, so none exist even in docs/examples).

## What changed — M3-B (public facades)

6. New **`apps/<module>/public.py`** facades built from a scan of actual cross-module consumption (callables/constants only — models are deliberately NOT re-exported; ORM relations / `get_model` remain the way to reach models): `exams` (16 names), `organizations` (19), `task_submission_core` (20), `notifications` (rewritten, 17), `accounts` (8 — points at `core.roles` / OTP services), `appeals` (4), `audit` (3 — write side points at `core.audit`), `courses` (2 — dashboard_sources extension point), `contact` (1), `trial_exams` (1). Every facade has `__all__` and resolves at import time.
7. **Exemplar consumer migration:** all 17 `from apps.task_submission_core.<submodule> import ...` lines across `apps/assignments`, `apps/labs`, `apps/projects` (12 files) were rewritten to `from apps.task_submission_core.public import ...`.
8. `AGENTS.md` §5 updated: core may import no app module (use `get_model` or hook registries — examples `core/audit.py`, `core/auth_otp.py`); new cross-module consumption must go through `apps.<module>.public`.

## Environment

Same as your previous M2 run: repo root with `manage.py`; venv from `requirements/base.txt` + `requirements/test.txt`; Postgres lane = CI-equivalent `DATABASE_URL` with migrations + RLS; sqlite fast lane = `DATABASE_URL="sqlite://"` with `--no-migrations`.

## Steps (run in order; stop and report on hard failures)

1. `git status` / diff scope sanity — changes should match the file lists above plus `AGENTS.md` and `scripts/module_deps_baseline.json`.
2. Static gates:
   - `python -m flake8 apps core config`
   - `python -m black --check apps core config` and `python -m isort --check-only apps core config`
   - `python scripts/module_deps.py --check` → **0 cyclic pairs, 0 core→apps targets**
   - `python scripts/check_module_size.py` → pass
   - Extra assertion: `grep -rn "from apps\." core --include="*.py" | grep -v tests` → empty.
3. `python manage.py check` and `python manage.py makemigrations --check --dry-run` → no new migrations (pure refactor).
4. **sqlite fast lane:** `DATABASE_URL="sqlite://" python -m pytest apps core tests -q --no-migrations` → 0 failures (~2130+ passed expected).
5. **Authoritative Postgres lane:** full suite with migrations + RLS + coverage gate `--cov=apps --cov=core --cov=config --cov-fail-under=68` → 0 failures, coverage ≥ 68% (was 71.38% at your M2 run).
6. **Hook & facade wiring smoke (Postgres lane):**
   ```
   python manage.py shell -c "
   import importlib
   # facades resolve
   for m in ['exams','organizations','task_submission_core','appeals','audit','contact','trial_exams','accounts','courses','notifications']:
       mod = importlib.import_module(f'apps.{m}.public')
       assert all(getattr(mod, n, None) is not None for n in mod.__all__), m
   # OTP hooks registered from accounts
   from core import auth_otp
   assert all('accounts' in f.__module__ for f in auth_otp._HOOKS.values()), {k: v.__module__ for k, v in auth_otp._HOOKS.items()}
   # back-compat re-export identity
   from core.audit import log_action as core_la
   from apps.audit.utils import log_action as legacy_la
   assert core_la is legacy_la
   from core.permissions import has_permission as core_hp
   from apps.organizations.permissions import has_permission as legacy_hp
   assert core_hp is legacy_hp
   print('M3 wiring OK')"
   ```
7. **Fail-closed 2FA check (unit-level):** in a test shell, replace a hook with the unregistered default and confirm `core.auth_otp.issue_email_otp(...)` raises `RuntimeError` (then restore). The point: admin 2FA must hard-fail, not silently pass, if accounts registration were ever missing.
8. **Behavior spot-checks via Django test client** (these cover the riskiest touched surfaces; add missing ones as tests under `tests/integration/`):
   - **Admin 2FA end-to-end:** admin login → OTP e-mail issued → wrong code rejected (+ rate-limit branch + audit DENY logged) → correct code accepted. (`core/tests/test_admin_2fa.py` and `test_admin_security.py` already exist — they must pass unmodified.)
   - **Private media access control (`core/media_views.py` — security-critical):** for each file family (exam answer file, exam/attempt media, lab / lab question / lab submission / lab answer files, project submission file, course resource, trial exam request file): owner/teacher can fetch; a student from ANOTHER organization gets 403/404; anonymous gets redirect/403. The get_model swap must not have changed any authorization outcome.
   - **Tenancy resolution (`core/tenancy.py`):** active-organization restore fallback and membership-based org context still work (existing tenant tests must pass on Postgres/RLS).
   - **Audit writes:** perform a logged action (e.g. an org admin action) and assert an `AuditLog` row is created with ip/user_agent/request_id — proving `core.audit.log_action` writes exactly as before.
   - **RBAC:** permission checks incl. wildcard (`course.*`), legacy alias (`grading.*` vs `grade.*`), and grant-prefix flows — covering the moved `has_permission`.
   - **Blog e-mail task:** `send_new_post_notification_email` for an existing and a missing post pk (get_model swap in `core/email_tasks.py`).
   - **Task apps through the facade:** assignment/lab/project submit + teacher grade flows (they now import via `task_submission_core.public`).
9. **E2E (if Playwright stack available):** run the standard suite; seeds were untouched in M3 but the admin/media/profile flows above get real coverage here.
10. **RLS sanity:** the tenant-isolation test set must pass on the Postgres lane (`core/tenancy.py` and `core/media_views.py` are the RLS-adjacent files touched).

## Rules

- Do NOT weaken assertions, delete tests, or add skips to make things green.
- Back-compat surfaces that MUST keep working (fix the TEST, not these, if a test imports them): `from apps.audit.utils import log_action, log_superadmin_cross_org_action, AuditLogMixin`; `from apps.organizations.permissions import has_permission, PERMISSION_CATEGORIES, PERMISSION_PREFIX_ALIASES`; `from apps.accounts.services import issue_email_otp, verify_otp_code`; all `core.cache` invalidator functions; every `apps.<module>.public` name listed in its `__all__`.
- Names that intentionally MOVED (update tests that still use old paths): `core.cache.get_cached_session_settings` / `get_cached_exam_question_ids` → `apps.live_exam.cache`; `core.tasks.warm_session_settings_cache` → `apps.live_exam.cache`.
- If you find an actual behavior difference (authorization outcome, redirect, message, status code, audit payload, OTP flow), STOP and report with a minimal repro — only obvious mechanical slips (missing import, wrong relative depth) may be fixed in app code.
- Follow `AGENTS.md` conventions (§1 facade preservation, §5 module-boundary gate incl. the new zero-core rule, §6 role skeleton).

## Report format

Table: step | command | result (passed/failed/skipped) | notes. Then: modified test files (and why), any app-code fixes (with justification), coverage %, and final verdict: "M3 verified" or blocking findings.
