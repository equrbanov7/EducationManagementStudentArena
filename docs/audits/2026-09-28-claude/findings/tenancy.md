# Tenancy / multi-tenant isolation audit, 2026-09-28 (slug: `tenancy`)

## 1. Scope and method

**Model reviewed:** `core/tenancy.py` (`scoped_by_organization`, `request_has_active_organization_context`, `restore_request_organization_from_profile`), `core/helpers._tenant_scoped_courses`, the per-app `_tenant_scoped_*` / `_get_tenant_*_or_404` helpers (assignments, labs, projects), `apps/organizations/middleware.py` (active-org resolution plus the per-request RLS GUCs), `core/rls.py`, the RLS migrations, `apps/organizations/checks.py` (the W011/E011 DB-role check), `docker-compose.prod.yml` (DB user, `POOL_MODE=session`, `RLS_TRANSACTION_SCOPED=False`, `CONN_MAX_AGE=0`), `docs/audits/RLS_BYPASS_AUDIT.md`, `docs/operations/*`, and the prior audits (2026-09-13 `access.md`/`security.md` and the 2026-09-12 Codex report).

**New code from 2026-09-28, read line by line:**
- `apps/courses/views/teacher/groups.py`
- `apps/courses/views/teacher/ai.py` and `apps/courses/ai_planner.py`
- `apps/courses/views/teacher/membership.py`
- `apps/registrar/course_groups.py`
- `apps/courses/views/shared/{_helpers,dashboard}.py`
- `apps/assignments/views/{teacher/crud,shared/api}.py`
- `apps/projects/views/{teacher/crud,shared/api}.py`
- `apps/labs/views/teacher/crud.py`
- the profile my-courses diff (`_stage1.py`)

**Systematic greps (non-test code):**
- Every bare-model `get_object_or_404(Model, …)`: 78 sites. The 37 without an org, owner or parent filter were reviewed individually.
- Every `Model.objects.get/filter(pk|id[__in]=var)` in views without scoping keywords: 87 sites reviewed.
- Every `User.objects.filter(id…)` and every broad `User.objects.filter(...)`. `auth_user` has no RLS, so these matter most.
- Every endpoint that reads `organization`/`org_id` from GET or POST.

**Other surfaces spot-checked:** media checkers (`core/media_views.py`, `core/media_policies.py`), export and extraction jobs (`exams/export_registry.py`, `extract_jobs.py`), the WS consumer `exams/consumers.py`, subject_folder, applications (assign), workload and timetable teacher lookups, exam form user querysets, the notification-publish fan-out, and the new `bypass_rls` management commands.

**Inventory:** ran `venv/bin/python scripts/rls_bypass_inventory.py [--markdown]`.

**Runtime probes:**
- Scratch file: `scratchpad/audit/test_tenancy_idor_probes.py`. It sets up two orgs (A and B), two teachers, students in each org, registry groups (OrgUnit plus StudentAcademicRecord) in each org, and a course in each org. It logs in as the teacher of org A.
- Sandbox: `ems_audit_tenancy` @ :55432, run with `--ds=config.settings.test --create-db`.
- Result: **23 tests, all passing** (the first run had 1 fixture error, fixed and re-run). Output lines are quoted below.
- **Caveat:** the sandbox role `emsarena_agent` is SUPERUSER+BYPASSRLS. The HTTP probes therefore measure the **application layer only**, which is the worst case.
- `RLSLayerProbe` and N03 switch to `SET LOCAL ROLE rls_app_role` (NOSUPERUSER, NOBYPASSRLS) to measure the DB layer.

## 2. Status of prior findings

| Prior item | Status | Evidence |
|---|---|---|
| Codex 2026-09-12 **P0-01**: prod app DB role is superuser/BYPASSRLS | **FIXED-SINCE-LAST (per repo evidence; not independently verified, no prod access)** | `docs/operations/NEW_SERVER_TASKS_2026-09-14.md:30` "[x] RLS tətbiq rolu yaradıldı … `emsarena_app` super=false bypass=false". Commit `6e71c4f2` (2026-09-27) says "prod app rolu NOBYPASSRLS olduğu üçün tenant kontekstsiz OrgUnit/üzvlük sətirləri görünmürdü (prod dry-run…)", which is operational proof that RLS is enforced at runtime. The comment at `apps/organizations/management/commands/apply_org_structure.py:38` says the same. **Residual:** the compose default is `EMS_DB_ROLE_ENFORCE=warn` (`docker-compose.prod.yml:75`), and nothing shows prod was raised to `error`. `docs/operations/PROD_DB_ROLE_CHECKLIST.md:7` still says "prod hələ superuser ilə işləyir" (stale). See T-05. |
| access F-05: `registrar_guestrosterdocument` has no RLS | **FIXED** | Catalog probe R02: the only org-column table without RLS is `['accounts_userprofile']`. `core/tests/test_audit_2026_09_13_rls_coverage.py` is the CI guard. |
| access F-07: structure slug pages give a 200 empty shell cross-tenant | **FIXED** | `apps/organizations/views/shared/_helpers.py:176-198`: `_can_view_structure` now requires active org == URL org for the non-org-wide path. |
| access F-10: `attempt_grants` writes a grant for any user | **FIXED** | `apps/exams/views/teacher/exams/attempt_grants.py:106-120` `_organization_student` uses `Exists(Membership… organization_id=exam.organization_id)`. Covered by `apps/exams/tests/test_audit_2026_09_13_backend.py` (outsider test). |
| access F-11: suspended-org user stays logged in | **FIXED** | `apps/organizations/middleware.py` Step 2 now calls `_fetch_blocked_organization` for users with no active membership. |
| access F-13: `RLS_BYPASS_AUDIT.md` stale | **REGRESSED (still open)** | Doc: 156 calls / 65 files. Script now: **179 calls / 82 files**, **11 files "TƏSNİF EDİLMƏYİB"** (the script exits 1). Not wired into CI (no workflow or test references `rls_bypass_inventory`). See T-04. |
| `accounts_userprofile` has an org column but no RLS (PII: FIN/phone/address) | **STILL OPEN (known design decision)** | R02 plus R01: `profile_b_visible: True` under `rls_app_role` with tenant A. |
| `accountactivationevidence` / `accountrestoreevidence` have RLS on but FORCE off | **STILL OPEN (P3)** | R02: `rls_on=166 force=164`. |
| security.md: avatar served cross-tenant by any authenticated user | **Unchanged (documented design)** | `apps/accounts/views/profile/avatar.py:31` `get_object_or_404(User, id=user_id, is_active=True)`. `_check_avatar_access` returns True. |

## 3. New findings

### T-01 Notification broadcast `org_<id>` target authorizes on ANY membership in the target org (cross-tenant at app layer; any teacher can broadcast org-wide)
Severity: P2   Category: Tenancy / RBAC   Status: CONFIRMED

Location: `apps/accounts/services/profile_actions.py:99-112` (`resolve_notification_recipients`). UI side: `apps/accounts/views/profile/context_builder/_helpers.py:127-150` (`_get_publish_notification_targets`).

Evidence:
```python
if target.startswith("org_"):
    org = Organization.objects.get(pk=org_id, is_active=True, status="active")
    # Superadmin can target any org; org admin only their own.
    if not is_superadmin:
        if not Membership.objects.filter(user=user, organization=org, is_active=True).exists():
            return None
    member_user_ids = Membership.objects.filter(organization=org, is_active=True).values_list("user_id", flat=True)
    return User.objects.filter(pk__in=member_user_ids, is_active=True)
```

How verified: scratch tests `PublishNotificationTargetProbe`. The request was POST `accounts:profile` with `profile_form=publish-notification`, `notif_targets=[org_<id>]`.
- `N01 plain teacher -> org_A 302 student_a notified: True`. A non-admin teacher has the section (`rbac.py:372-375`) and can notify every member of the org. The UI never offers them this target; the server accepts it anyway.
- `N02 admin(A)+student(B) -> org_B [no RLS] 302 student_b notified: True`. The owner/admin of org A, active org A, holds only a *student* membership in org B, yet the notification reaches all org-B members. The UI (`_helpers.py:127-150`) also *lists* `org_<id>` for every org in which the admin has any membership.
- `N03 … [rls_app_role] 302 student_b notified: False`. Under the NOBYPASSRLS role, the `organizations_membership` RLS (tenant = A) empties the recipient set, so **production is mitigated for the cross-tenant variant** if the prod role is really NOBYPASSRLS. The same-tenant org-wide broadcast by a plain teacher (N01) is **not** mitigated by RLS.

Impact:
- (a) Any teacher, exam-center or HR user can push a system notification to the whole university: about 8.4k users, with an arbitrary http(s) link and file attachments (`notif_files`). This is a phishing and spam vector with system-notification trust.
- (b) For multi-org users, it is a cross-tenant write blocked only by RLS (single layer).
- The code comment "org admin only their own" contradicts the check.

Root cause: the authorization checks *membership* in the target org instead of "target org == active org AND actor is org admin (or has a `notification.publish_org` key) there".

Recommended fix: in the `org_` branch, for non-superadmins require all of:
- `org.pk == get_request_organization(request).pk`, and
- `capabilities["is_org_admin"]` (or a dedicated permission key).

Pass `request`/`organization` into `resolve_notification_recipients`. In `_get_publish_notification_targets`, list only the active org. Add regression tests N01 and N02 (expect no notification).

Effort: Small

### T-02 RLS cannot stop cross-tenant *user binding*; `auth_user` and `accounts_userprofile` are readable across tenants under the app role
Severity: P3 (defense-in-depth gap; no exploitable path found)   Category: Tenancy / RLS design   Status: CONFIRMED (DB layer)

Location: RLS policy design, `apps/organizations/migrations/0003_rls_policies.py:137` (`_indirect_org_policy("courses_coursemembership", _COURSE_ORG_SUBQUERY)`) and equivalents for the M2M/assignment tables. `auth_user` and `accounts_userprofile` have no RLS.

Evidence (probe R01, run as `rls_app_role` with `app.current_org_id = A`):
`{'course_b_visible': False, 'course_b_membership_visible': False, 'auth_user_b_visible': True, 'profile_b_visible': True, 'membership_b_visible': False, 'insert_cross_tenant_membership': 'ALLOWED'}`

How verified: `test_R01_rls_matrix`, a raw INSERT of `courses_coursemembership(course=A-course, user=B-student)` under the restricted role.

Impact:
- Every "which users may be attached" decision (`students[]`, `user_ids`, `group_ids` → students, `assignee`, `teacher_id`, `head_user`) depends solely on app code. That code is correct today: T05, T10, T14, T15, T03 and N-series all pass.
- If an ORM query on `UserProfile` misses its org filter, it leaks cross-tenant PII even with the NOBYPASSRLS role.

Root cause: the policies constrain rows only by the parent object's org, not by the referenced user's org. `auth_user` and `userprofile` are deliberately RLS-free, because they are read before login.

Recommended fix (pick by cost):
- (1) Keep a single shared helper, e.g. `org_member_users(org, ids)`, and route every user-id intake through it, with a grep/CI guard against `User.objects.filter(pk__in=<request data>)` in views.
- (2) Longer term: a narrow RLS policy on `accounts_userprofile` with a login-time `bypass_rls()`, as tracked since 2026-09-02.
- (3) Optionally a DB trigger on `courses_coursemembership` that requires an active `organizations_membership` of the user in the course org.

Effort: Medium (1: Small)

### T-03 `AddMemberView` accepts any same-org user (teachers and staff too) as a course "student"
Severity: P3   Category: Authorization (same tenant)   Status: CONFIRMED (read)

Location: `apps/courses/views/teacher/membership.py:240-252` (`AddMemberView.post`)

Evidence:
```python
user_qs = User.objects.filter(id=uid)
if owner_org is not None:
    user_qs = user_qs.filter(profile__organization=owner_org)
user = user_qs.get()
membership, created = CourseMembership.objects.get_or_create(course=course, user=user, defaults={"role": "student", ...})
```

The picker (`_available_students_queryset`) restricts to students via `_student_users_queryset`, but the POST does not.

How verified: read. The cross-tenant part is blocked (T05: `add_member(student_b) 200 … "0 tələbə kursa əlavə olundu"`, and student_b was not added).

Impact: a course owner can enrol same-org staff or teachers as students. They then see student-side course data and receive task notifications. No cross-tenant exposure.

Recommended fix: `user_qs = _student_users_queryset(user_qs, organization=owner_org)`, mirroring the picker, and use active membership rather than `profile.organization` alone.

Effort: Small

### T-04 `bypass_rls()` inventory drift: 179 calls / 82 files, 11 unclassified, script not enforced
Severity: P3   Category: Tenancy governance   Status: CONFIRMED (REGRESSED from F-13)

Location: `docs/audits/RLS_BYPASS_AUDIT.md` (states 156/65) and `scripts/rls_bypass_inventory.py`.

Evidence: `179 çağırış / 82 fayl`. "TƏSNİF EDİLMƏYİB" lists 11 files:
- `apps/ai_assistant/retention.py`
- `apps/subject_folder/{tasks.py, services/plagiarism/dispatch.py, management/commands/subject_folder_{digest,similarity,sync_journal}.py}`
- `apps/surveys/management/commands/surveys_{ensure_template,open_campaign}.py`
- `apps/timetable/tasks.py`
- `apps/workload/management/commands/{import_teaching_task_workbook,sync_plan_offerings}.py`

Also new but classified: `apps/audit/views_filters.py` (superadmin only) and 5 accounts/org management commands.

How verified: ran the script. `grep -r rls_bypass_inventory .github core/tests apps/*/tests` returns nothing.

Sample review of the request-path ones:
- `audit/views_filters.py:107-115`: superadmin only. OK.
- `subject_folder/services/plagiarism/dispatch.py:26`: the engine filters `organization_id=submission.organization_id` (`engine.py:123`). OK.
- The new management commands take `--org` and filter by it. OK.

No leak found. The process gate is what failed.

Recommended fix: classify the 11 files in the script, regenerate the doc table, and add a CI step (or pytest) that runs `scripts/rls_bypass_inventory.py` and fails on unclassified files.

Effort: Small

### T-05 DB-role enforcement left at `warn`; stale operations doc
Severity: P3   Category: Tenancy / ops   Status: PLAUSIBLE (prod `.env` not visible)

Location: `docker-compose.prod.yml:75` `EMS_DB_ROLE_ENFORCE: ${EMS_DB_ROLE_ENFORCE:-warn}`; `.env.production.example:67` `EMS_DB_ROLE_ENFORCE=warn`; `docs/operations/PROD_DB_ROLE_CHECKLIST.md:7` says prod still runs as superuser.

Impact: if `.env` ever loses `APP_DATABASE_USER`, the compose fallback (`docker-compose.prod.yml:72` `${APP_DATABASE_USER:-${POSTGRES_USER}}`) silently reconnects as the owner/superuser. Only a W011 warning is logged, and the RLS layer, which T-01(N03) currently relies on, disappears.

How verified: read. The prod value is not verified.

Recommended fix: set `EMS_DB_ROLE_ENFORCE=error` in the prod `.env` (step 4 of the checklist). Consider removing the `:-${POSTGRES_USER}` fallback for the app URL. Update the checklist header to "done 2026-09-14/27".

Effort: Small (owner op)

## 4. Areas verified clean (with probe results)

App layer, sandbox without RLS; teacher A with active org A:

| Probe | Endpoint | Result |
|---|---|---|
| T01 | `courses:available_groups` on course B | 403 |
| T02 | `available_groups` search on own course, `q=ZZ` | only `{'ZZA-Group'}` (org-B group not listed) |
| T03 | `add_members_bulk` own course, `group_ids=[org-B group]` | 400 "Qrup seçilməyib", no membership |
| T04 | `add_members_bulk` into course B | 403 |
| T05 | `add_member` own course, `user_ids=[student_b]` | 200 with 0 added |
| T06 | `available_students` own course | `set()` (student_b hidden) |
| T07 | `delete_group_from_course` course B | 403, membership intact |
| T08 | `delete_member` (own course, foreign membership id) | 404 |
| T09 | `ai_apply` course B | 403 |
| T10 | `create_assignment` own course, `students[]=[B, A]` | assigned = {A} only |
| T11 | `create_assignment` course B | 404 |
| T12 | `edit_assignment` GET, foreign assignment | 404 |
| T13 | `assignments:search_students` course B | 404 |
| T14 | `create_project` with a foreign student | not assigned |
| T15 | `create_lab` with a foreign student | not allowed |
| T16 | `labs:api_get_students` course B | 404 |
| T17 | `projects:api_get_students` course B | 404 |

Code review, clean:
- `registrar/course_groups.py`: every query takes `organization=`, `resolve_groups` parses UUIDs and filters by org, and enrollment offering ids come from org-scoped offerings.
- `groups.py` / `membership.py` / `ai.py`: course fetched via `_tenant_scoped_courses` plus owner. The `organization or course.organization` fallback is safe because the course is already tenant-scoped.
- Media checkers: labs, projects, course resources and submissions all require org membership.
- Export jobs: org guard in the worker; downloads are `user=request.user`.
- The `exams/consumers.py` supervision WS checks owner, author or superadmin after a bypassed lookup.
- `applications` assign: `handles_unit` check.
- `workload`: `ensure_assignable_teacher`.
- `timetable`: `teacher_or_404` uses scoped ids.
- `subject_folder` downloads: `organization=` plus pk.
- Exam form user querysets: org-scoped, except the superadmin path.
- Session-mode PgBouncer plus `CONN_MAX_AGE=0` plus the middleware `reset_rls_context` in `finally`: no GUC carry-over between requests.

## 5. Score

**Multi-Tenancy: 86 / 100** (previous 78)

Up from 78:
- The prod runtime role is now NOBYPASSRLS (+), so RLS finally counts as a second layer.
- F-05, F-07, F-10 and F-11 are closed.
- The CI RLS-coverage test exists.
- All 17 app-layer IDOR probes on the new 2026-09-28 LMS code were blocked.

Deductions:
- −6: T-01. A confirmed app-layer cross-tenant write, mitigated only by RLS, plus an org-wide broadcast by any teacher.
- −4: `userprofile` PII without RLS, and RLS unable to constrain user binding (T-02).
- −2: bypass inventory drift not enforced (T-04).
- −2: `EMS_DB_ROLE_ENFORCE=warn` plus the silent superuser fallback (T-05).

## 6. Prioritized remediation

| Prio | Action | Dependency | Risk | Effort | Benefit |
|---|---|---|---|---|---|
| 1 | T-01: restrict the `org_` notification target to the active org plus org-admin (or a new permission key); list only the active org in the UI; add N01/N02 regression tests | none | low (a teacher loses a capability the UI never offered) | S | closes the org-wide phishing vector and the cross-tenant app-layer write |
| 2 | T-05: set `EMS_DB_ROLE_ENFORCE=error` in the prod `.env`; drop the `APP_DATABASE_USER` → `POSTGRES_USER` fallback; update `PROD_DB_ROLE_CHECKLIST.md` | owner server access | low (check verified on the clone) | S | RLS layer cannot silently disappear |
| 3 | T-04: classify the 11 files in `rls_bypass_inventory.py`, refresh the doc, add a CI step that fails on unclassified files | none | none | S | every new `bypass_rls` gets reviewed |
| 4 | T-03: filter `AddMemberView` POST through `_student_users_queryset` plus active membership | none | low | S | picker and POST agree |
| 5 | T-02(1): shared `org_member_users(org, ids)` helper plus a grep guard against raw `User.objects.filter(pk__in=request…)` in views | none | low | S–M | uniform user-id intake |
| 6 | T-02(2): RLS on `accounts_userprofile` with an explicit login-path bypass | design decision, full-suite run | medium (login and registration paths) | M | cross-tenant PII protected at the DB layer |
| 7 | FORCE RLS on `accounts_accountactivationevidence` / `accountrestoreevidence` | migration | low | S | consistency |
