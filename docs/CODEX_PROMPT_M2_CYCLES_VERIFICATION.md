# Codex Prompt — M2 "Zero Module Cycles" Refactor Verification (EMSArena)

Copy everything below this line into Codex.

---

You are verifying a large dependency-inversion refactor ("M2") in EMSArena, a Django 5.2 multi-tenant exam/LMS platform (PostgreSQL RLS, Daphne/Channels, Celery, server-rendered templates). The refactor dissolved ALL 18 cyclic module pairs (now 0) **without changing any URL, template path, or behavior**. Your job: run the authoritative verification lanes, fix ONLY test-side or trivially-mechanical issues, and report anything that looks like a real behavior change.

## What changed (rounds R2–R5; R1 was already verified previously)

1. **exams ↔ appeals** — new hook registry `apps/exams/score_adjustments.py` (6 hooks, neutral defaults); `apps/appeals/apps.py` `ready()` registers implementations from `apps.appeals.services`. Exams call sites (`views/student/results.py`, `views/teacher/results/_attempt_views.py`, `views/teacher/results/_helpers.py`, `services/result_calculation.py`) no longer import appeals; old try/except lazy-import fallbacks were removed (neutral defaults replace them).
2. **exams ↔ live_exam** — lazy accessors `get_live_session_model()` / `get_live_active_states()` in `apps/exams/constants.py`; `LIVE_ACTIVE_STATES` removed from `views/teacher/exams/constants.py` and the duplicate tuple removed from `views/student/lists.py`.
3. **courses ↔ {assignments, projects, labs}** — provider registry `apps/courses/dashboard_sources.py`; each task app contributes its course-dashboard section via `apps/<app>/course_dashboard.py`, registered in its `AppConfig.ready()`. `CourseDashboardView` (`apps/courses/views/shared/dashboard.py`) no longer imports task models. `apps/courses/signals.py` uses `django_apps.get_model` for Assignment/Project.
4. **blog ↔ exams** — `DATA_URL_PNG_RE` moved to `core/constants.py` (back-compat re-export left in `apps/blog/utils.py`); seed command uses `get_model` for blog models.
5. **courses/exams/organizations triangle** — kept natural directions `courses→exams→organizations`; reverse edges converted to `get_model` lazy lookups in: `apps/exams/services/access_policy.py`, `apps/exams/views/teacher/exams/_shared.py`, `apps/exams/management/commands/{seed_group_demo_data.py,_seed_helpers/courses.py,_seed_helpers/users.py}`, `apps/organizations/management/commands/{seed_ci_e2e_scenario.py,seed_ci_e2e_user.py,backfill_admin_memberships.py}`.
6. **accounts god-hub (biggest)**:
   - `ProfileRole` (constants class) + 6 pure role helpers (`is_superadmin_user`, `get_user_role_level`, `user_has_any_role`, `get_profile_role_label`, `map_signup_role_to_profile_role`, `map_org_role_to_profile_role`) moved to **`core/roles.py`**. `apps/accounts/models.py` and `apps/accounts/policies/roles.py` keep back-compat re-exports, so `from apps.accounts.models import ProfileRole` still works. ~13 external import sites switched to `core.roles`.
   - New hook registry **`apps/accounts/profile_hooks.py`** (8 hooks, neutral defaults). Blog registers implementations from **`apps/blog/profile_sections.py`** in `BlogConfig.ready()` (`register_all()`). Hooks: `posts_section`, `create_category_section`, `category_management_section`, `pending_posts_count`, `pending_posts_section`, `public_posts_context`, `category_post_actions`, `post_moderation_views`.
   - Moved verbatim into `apps/blog/profile_sections.py`: profile posts section (ex `_sections/posts.py`, file deleted), category management section (ex `_sections/category_management.py`, file deleted), pending-post-approvals block (ex `context_builder/_stage2.py`), public-profile posts logic (ex `public.py`), category CRUD POST branch (ex `post_handler.py`).
   - `apps/accounts/views/post_management.py` (513 lines: superadmin/org post moderation) moved to **`apps/blog/views/moderator/post_management.py`**; the accounts module is now a thin shim delegating through `profile_hooks.post_moderation_view(name)` (unregistered → 404). URLs and the `accounts.views` facade surface are unchanged.

Guard scripts: `scripts/module_deps.py` (baseline is now **zero** cycles) and `scripts/check_module_size.py` (600-line soft cap).

## Environment

- Repo root: the EMSArena Django project (contains `manage.py`, `apps/`, `core/`, `config/`).
- Python venv with `requirements*.txt` installed.
- For the Postgres lane use the same setup as CI (`DATABASE_URL=postgres://...`; RLS migrations enabled). The sqlite fast lane uses `DATABASE_URL="sqlite://"` with `--no-migrations`.

## Steps (run in order; stop and report on hard failures)

1. `git status` — confirm working tree state; note the diff scope matches the file list above (plus `AGENTS.md`, `scripts/module_deps_baseline.json`).
2. Static gates:
   - `python -m flake8 apps core config`
   - `python -m black --check apps core config` and `python -m isort --check-only apps core config`
   - `python scripts/module_deps.py --check` → must print zero frozen cycles, no new cycles.
   - `python scripts/check_module_size.py` → must pass.
3. `python manage.py check` and `python manage.py makemigrations --check --dry-run` → **no new migrations expected** (pure refactor; `core/roles.py` move must not generate model changes because `UserProfile.role` choices reference the same constants).
4. **sqlite fast lane:** `DATABASE_URL="sqlite://" python -m pytest apps core tests -q --no-migrations` → expect ~2130+ passed, small skip count, 0 failures.
5. **Authoritative Postgres lane:** full suite WITH migrations and RLS, same command CI uses, including coverage gate: `--cov=apps --cov=core --cov=config --cov-fail-under=68`. Expect ≥ the previous baseline (2175 passed at commit fc9d7030) plus/minus newly added tests; 0 failures.
6. **Hook wiring smoke (Postgres lane):**
   ```
   python manage.py shell -c "
   from apps.exams import score_adjustments as sa
   from apps.accounts import profile_hooks as ph
   from apps.courses import dashboard_sources as ds
   assert all(f.__module__.startswith('apps.appeals') for f in sa._HOOKS.values())
   assert all(f.__module__.startswith('apps.blog') for f in ph._HOOKS.values())
   assert sorted(p.__module__ for p in ds._PROVIDERS) == ['apps.assignments.course_dashboard','apps.labs.course_dashboard','apps.projects.course_dashboard']
   print('hooks OK')"
   ```
7. **Seed commands really run** (fresh test DB is fine):
   - `python manage.py seed_ci_e2e_scenario --password 'Passw0rd!Test'` (flag name per `add_arguments`; adjust if different)
   - `python manage.py seed_group_demo_data --password 'Passw0rd!Test'` (adjust flags per command)
   Both must complete without exceptions (they now use `apps.get_model` lazily).
8. **Behavior spot-checks via Django test client** (these cover the moved code paths; add as tests under `tests/integration/` if any are missing):
   - Profile page GET for: a superadmin, an org admin, a teacher with `can_manage_blog`, a plain student — sections render, `posts_count` badge present for blog managers.
   - `?section=posts`, `?section=create-post`, `?section=category-management`, `?section=create-category`, `?section=pending-post-approvals` (as superadmin/moderator) — 200 responses, expected context keys (`user_posts`, `category_management_page`, `pending_post_approval_*`).
   - Profile POST: `profile_form=category-create` (valid + invalid), `category-management-save` (valid + invalid + missing id), `category-management-delete` (existing, missing, protected) — same redirects/messages as before; invalid forms re-render with bound form and correct `active_section`.
   - Public profile `accounts:public_user_profile` for a user with published posts: search `?q=`, category filter, pagination, and invalid `?page=abc` → 400.
   - Post moderation URLs (`accounts:superadmin_post_management`, `accounts:org_post_management`, delete/moderate POST endpoints) — permissions, rate-limit branch, and audit logging still work; anonymous → login redirect; unauthorized → PermissionDenied/redirect as before.
   - Course dashboard GET as teacher and as student (assignments/projects/labs/exams sections populated; student sees only assigned items).
   - Student exam results page with an appeal bonus applied → effective score/bonus still shown; teacher results list unchanged.
   - Student exams list and teacher exam detail with an active live session → "live" filter/flags still work.
9. **E2E (if the Playwright stack is available):** run the standard E2E suite; it depends on `seed_ci_e2e_scenario`, which was touched — a green run is the strongest signal.
10. **RLS/tenant sanity:** run the existing tenant-isolation tests (they exist in the suite); nothing in this refactor should touch RLS, but `bypass_rls` usage moved files (`post_management`), so confirm those tests pass on Postgres.

## Rules

- Do NOT weaken assertions, delete tests, or add skips to make things green.
- If a test fails because it imports a moved private name (e.g. `apps.accounts.views.profile._sections.posts`, `_load_managed_category` from `post_handler`, `build_posts_context`), update the TEST to the new location (`apps/blog/profile_sections.py`, `apps/blog/views/moderator/post_management.py`) — the back-compat surfaces that must keep working are: `from apps.accounts.models import ProfileRole`, `from apps.accounts.policies import ...` (all 8 names), `accounts.views.{superadmin_post_management, superadmin_delete_post, org_post_management, org_moderate_post}`, `from apps.blog.utils import DATA_URL_PNG_RE`.
- If you find an actual behavior difference (different redirect, message, context key, status code, queryset semantics), STOP and report it with a minimal repro — do not "fix" app code beyond obvious mechanical slips (missing import, wrong relative depth).
- Follow repo conventions in `AGENTS.md` (§1 facade preservation, §5 module-boundary gate, §6 role skeleton).

## Report format

Table of: step | command | result (passed/failed/skipped counts) | notes. Then: list of any test files you modified and why, any app-code fixes (with justification), coverage %, and a final verdict: "M2 refactor verified" or a list of blocking findings.
