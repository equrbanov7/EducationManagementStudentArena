# Phase 2/3 — Security fixes (branch `audit/post-migration-qa-2026-09`)

Date: 2026-09-02 · Input: [`PHASE23_SECURITY.md`](PHASE23_SECURITY.md) · No commits made (working tree only).

Every finding below was **reproduced red first** (test failing against the unfixed code, or the
auditor's own live exploit), then fixed and re-run green. Re-verification was done twice: with the
in-process test client, and — for the five FAIL cases — as **real HTTP requests** against the QA
clone server on `http://127.0.0.1:8100`.

Production DB (`emsarena_db` @ :5432) was never touched. Test runs used private agent databases
(`ems_sec_7k3d`, `ems_sec_migr1`, `ems_sec_fresh*`) on `127.0.0.1:55432`.

---

## 1. Summary table

| # | Finding | Fix (file:line) | Regression test | Re-verified |
|---|---|---|---|---|
| P0-1 | Private correction/evidence PDFs served to anonymous users | `core/media_policies.py` (new, 8 prefixes + policies) · `core/media_views.py:52,74,452,527` | `core/tests/test_media_policies.py` (9) | HTTP 302 for all 8 prefixes; public prefixes still 200 |
| P0-2 | Exam-centre staff destroys another teacher's bank questions | `apps/exams/views/teacher/question_library/crud.py:207,226,254,264,306` | `apps/exams/tests/test_question_bank_mutation_guard.py` (5) | HTTP 403, row count unchanged |
| P1-1 | Role-gated login portals bypassable via the neutral endpoint | `apps/accounts/views/auth/login.py:264,279` | `apps/accounts/tests/test_cabinet_routing.py` (+2) | student rejected, staff still works |
| P1-2 | Teacher clones another teacher's syllabus | `apps/syllabus/services/drafts.py:266-269` | `apps/syllabus/tests/test_copy_scope.py` (3) | HTTP 409 `transition.out_of_scope`, no new row |
| P1-3 | Audit log deletable from the admin | `apps/audit/admin.py:64,78` · `apps/audit/models.py:175` | `apps/audit/tests.py::AuditLogAppendOnlyTest` (4) | in-process |
| P1-4 | CI "RLS gate" cannot detect an RLS regression | `core/tests/test_rls_gate_integrity.py` (new) + workflow proposal §4 | 3 meta-tests | in-process (postgres) |
| P2-1 | Exam-centre surfaces admit any authenticated org member | `apps/exams/services/final_center/permissions.py:75,103` · `apps/exams/views/exam_center/_shared.py:42` | `apps/exams/tests/test_supervision_surface_gate.py` (4) | HTTP no longer 200 |
| P2-2 | Faculty-scoped dean reads the org-wide role matrix | `apps/organizations/views/shared/_helpers.py:40` · `.../org_admin/endpoints.py:158` | `apps/organizations/tests/test_role_matrix_scope.py` (3) | HTTP 302 (was 200) |
| P2-3 | `organization_id` accepted from the request body | `apps/accounts/views/_helpers/tenant.py:59` (shared resolver, both views delegate) | existing suites (45) | in-process |
| P2-4 | `ALERTMANAGER_WEBHOOK_TOKEN` never reaches production | `config/settings/production.py:29` | `tests/test_security_configuration.py::ProductionSettingsImportListTest` (2) | in-process |
| P2-5 | Rate-limit typo silently disables a limiter | `core/rate_limit.py:54,108` · `config/settings/components/admin_ratelimit.py` (tail) | `core/tests/test_rate_limit_config.py` (7) | `ImproperlyConfigured` at startup |
| P2-6 | Inconsistent `X-Forwarded-For` parsing (5+ sites) | `core/utils.py:166` (single helper) + 8 delegating sites | `core/tests/test_client_ip.py` (7, incl. a repo-wide scan) | in-process |
| RLS-D | 3 of the 4 uncovered `organization_id` tables | `apps/audit/migrations/0003_rls_auditlog.py` · `apps/monitoring/migrations/0002_rls_securityevent.py` · `apps/ai_assistant/migrations/0003_rls_aiassistantlog.py` | `core/tests/test_rls_platform_logs.py` (4, NOBYPASSRLS role) | in-process (postgres) |
| RLS-D | `accounts_userprofile` | **deliberately NOT added** — see §5 | — | analysis only |

---

## 2. P0 fixes in detail

### P0-1 · Private media prefixes

**Reproduction (red).** The auditor's anonymous `curl` returned 200 with real PDF bytes for six of
the seven private prefixes; only `journal_corrections/` redirected. Locally I reproduced the same
shape by disabling the new prefix merge: 8 of 9 new tests failed, including
`_is_private()` returning `False` for `journal_lesson_corrections/…`.

**Root cause.** `core/media_views._PRIVATE_PREFIXES` governs *whether the permission check runs at
all*. Prefixes missing from that tuple were classified public, so `protected_media` skipped
authentication entirely — **including in production**: nginx already proxies `/media/` to Django
(`docker/nginx/nginx.conf:120`) and Django would then hand nginx an `X-Accel-Redirect` to
`/internal_media/` (`nginx.conf:139`, correctly `internal`) *without ever checking the user*. The
exposure was therefore not a dev-server artefact.

**Fix.** New module `core/media_policies.py` holds one checker per prefix plus a registry; the
serving view merges those into its own tuple/dict:

* `journal_corrections/` — affected student · offering instructor · `journal.correct` holder or
  org-admin-level (≥80) member. (Moved out of `media_views.py`, now also instructor-aware.)
* `journal_lesson_corrections/` — a lesson-row correction belongs to the whole group, so the
  "affected student" is any student enrolled in that offering, plus the instructor and reviewers.
* `journal_selfwork_corrections/`, `journal_coursework_corrections/`,
  `journal_component_corrections/` — enrolment's student · offering instructor · reviewer.
* `exam_score_entries/` — enrolment's student · offering instructor · reviewer.
* `legacy_excuse_documents/` — student · reviewer only. These rows carry **no offering/subject**
  (student + date range only), so an instructor scope is not computable; documented in the checker.
* `applications/` — delegated to the module's own policy `apps.applications.services.access.can_view`
  (sender · scoped handler of the current unit · watching unit · `application.manage` · superuser).
* `avatars/` stays "any authenticated user" (unchanged, deliberately low-risk).

Two design points worth flagging:

1. **Denial is now `Http404`, not `PermissionDenied`** (`core/media_views.py:527`). The permission
   check runs before the file-existence check, so 404 leaks nothing extra and stops the response
   from confirming that a given document UUID exists. 8 existing assertions in
   `core/tests/test_media_views.py` were updated accordingly (all 40 tests in that module pass).
2. **`core/` must not import `apps/`** (`scripts/module_deps.py`, baseline `core_to_apps: []`). The
   applications policy is therefore resolved lazily by dotted path
   (`APPLICATIONS_CAN_VIEW_PATH`, `django.utils.module_loading.import_string`), and
   `register_media_policy(prefix, checker)` / `registered_prefixes()` / `resolve_checker()` let any
   app register or override its own policy from `AppConfig.ready()` later without a static import.
   `python scripts/module_deps.py --check` → ✅ no new `core → apps` edge.

`core/media_views.py` was 575 lines against a 600-line cap, which is the second reason the policies
live in their own module (it is now 557).

**nginx.** No change is required in the repo: `/media/post_images/` and `/media/course_covers/` are
the only prefixes served directly, everything else proxies to Django, and the internal location
already exists:

```nginx
# docker/nginx/nginx.conf — already present, unchanged
location /media/ {                    # everything not explicitly public
    proxy_pass $emsarena_app;         # → Django protected_media (auth happens here)
    ...
}
location /internal_media/ {           # X-Accel-Redirect target
    internal;                         # not reachable from outside
    alias /var/www/media/;
    expires off;
    add_header Cache-Control "private, no-store";
}
```

The operational note is the converse: **any new private prefix must be added to
`media_policies.PRIVATE_PREFIXES` (or registered)**, because nginx's blanket `/media/` proxy means
Django is the *only* gate.

### P0-2 · Question-bank mutation ownership

**Reproduction (red).** With the new gate removed, 3 of the 5 tests fail — the exam-centre staff
POST returns 302 and the question is hard-deleted, exactly as the auditor observed.

**Root cause.** `question_bank_detail` resolved the bank through `accessible_banks()`, which
deliberately widens *read* visibility to exam-centre users ("mərkəz bank hovuzunun idarəçisidir"),
and the POST branch then inherited that widened scope. `accessible_banks`' own docstring already
promised the opposite — "Redaktə/silmə yenə yalnız sahibə açıqdır (view qatında)" — so the fix
restores documented intent rather than inventing a rule.

**Fix.** `_can_mutate_bank` (owner · superuser/superadmin · organisation owner) enforced by
`_ensure_bank_mutation_allowed(request, bank, action)` at the top of the POST branch, covering
`delete`, `delete_language`, `activate` and `deactivate` in one place. Refusals raise
`PermissionDenied` **and** write an `AuditAction.DENY` row; successful deletions now write
`AuditAction.DELETE` rows carrying the deleted question ids (previously nothing was audited at all).

**Residual, not fixed (deliberate).** `apps/exams/views/teacher/question_library/questions.py`
(`question_bank_bulk_add`, `ai_generate_bank_questions`, `bank_question_add`, `bank_question_edit`)
and `question_bank_update` use the same widened `accessible_banks()` scope with no ownership check.
Those are *additive/metadata* paths that the question-submission acceptance flow legitimately uses
("qəbul axını istənilən org bankına yaza bilir"), and `question_bank_update` intentionally lets the
exam centre set `source_teacher`. Tightening them needs a product decision about who may add
content to whose bank — recommended as a separate task, not folded into a destructive-action fix.

---

## 3. P1 / P2 fixes in detail

**P1-1 login portal.** `form_valid` applied the portal gate only under `if self.audience:`, and the
neutral `POST /accounts/login/` reaches `CustomLoginView` with `audience=None`
(`login_portal`), so the gate was skipped for every account. New `effective_audience()` never
returns `None`: an unset audience means **staff**, so a student posting to the neutral URL is
refused with the existing "müəllim və əməkdaşlar üçündür" guidance while legacy staff clients keep
working. Chosen over refusing *all* neutral logins because nothing in the codebase posts to that
URL (both templates post to their own portal), while 100+ existing tests use it for staff logins —
all 1149 `apps/accounts/tests` tests pass.

**P1-2 syllabus copy.** `copy_from_previous` validated nothing about the *source* syllabus. It now
carries the byte-identical gate its sibling `create_next_version` already had (`actor.has(PERM_EDIT)`
plus `is_author(...) or covers_unit(chair_unit_id, PERM_EDIT)`), placed in the **service** so every
caller inherits it. Test note: the fixture pins the teacher role to `RoleScopeType.COURSE` because
that is what production seeds (`default_roles_university.py`); with the factory default
(`ORGANIZATION`) `get_permission_scope` returns org-wide and the gate would look green while proving
nothing.

**P1-3 audit log.** `has_delete_permission` returned `request.user.is_superuser`; it now returns
`False` unconditionally, `get_actions` drops `delete_selected`, and `AuditLog.delete()` raises
`ValidationError` — the same application-level contract as
`registrar.ImmutableCorrectionEvidence`. The authoritative guard remains the PostgreSQL trigger
from `organizations/0019_audit_log_append_only`; the model override is the SQLite/ORM mirror. No
migration needed. Queryset-level `.delete()` is intentionally left to the trigger so
`apps/organizations/tests/test_rls.py::test_delete_is_blocked` still asserts a `DatabaseError`.

**P1-4 RLS gate.** New `core/tests/test_rls_gate_integrity.py` (marked `postgres`) asserts that
(1) `rls_app_role` exists and is `NOSUPERUSER`+`NOBYPASSRLS` — it **fails**, never skips, if the
role is gone; (2) it records whether the connection role can bypass RLS; (3) `SET LOCAL ROLE
rls_app_role` genuinely hides a foreign tenant's `OrgUnit`. That makes the enforcement mechanism
itself a tested artefact rather than an assumption. The workflow change is a **proposal only**
(`.github/` untouched) — see §4.

**P2-1 supervision surface.** `supervisor_org_or_403` only required an active organisation. New
`can_enter_supervision_surface(user, organization)` / `ensure_can_enter_supervision_surface`
require exam-centre membership *or* an assignment to at least one room/session in that tenant
(room-level `invigilators`, plus the deprecated session-level `invigilator`/`staff` for backwards
compatibility). Object-level `can_supervise_session` is unchanged. One existing test
(`test_final_center_flow.py::RoomListScopingTests`) asserted the old contract — 200 with an empty
list for an unassigned teacher — and was updated to expect 403 with a comment pointing at case 39.

**P2-2 role matrix.** `organization_roles` now requires `_can_view_role_matrix` in addition to
`_can_manage_organization`: superuser/superadmin, organisation owner, or a role actually holding
`role.view` (which `dean` does not, and `rector`'s wildcard does). The dean's implicit `org_admin`
alias no longer opens the org-wide catalogue.

**P2-3 `organization_id` from POST.** Both views delegate to one shared
`_resolve_superadmin_target_org(request, query_param=…)`. The body/query id is read **only** for
superadmins (as before), but is now validated against *active* organisations and parsed defensively
— a non-UUID value previously raised `ValidationError` and produced a 500 instead of falling back.

**P2-4 settings drift.** `ALERTMANAGER_WEBHOOK_TOKEN` added to production's explicit
`from .base import (...)` list. The new test asserts the *name the view reads* and the name in the
import list agree, so the class of drift (not just this instance) is covered.

**P2-5 rate limits.** Two layers. (a) `core.rate_limit.validate_rate_limit_settings(namespace)` is
called at the bottom of `config/settings/components/admin_ratelimit.py`, so a typo in any
`*_RATE_LIMIT` raises `ImproperlyConfigured` **at process start** — verified:
`LOGIN_RATE_LIMIT="5/10min"` now aborts `django.setup()`. An empty string stays an explicit,
documented "disabled". (b) At runtime `_parse_or_fail_closed` logs an error and **fails closed**
(reports limited) instead of returning "not limited", covering hard-coded caller bugs.

**P2-6 XFF.** `core.utils.get_client_ip` was taking the **leftmost** member — the one the client
writes — and it is the helper used by login/OTP rate limiting. It now takes the rightmost member,
skipping `TRUSTED_PROXY_HOPS` (default 1, matching nginx's overwrite in `nginx.conf:126`); a CDN in
front raises the setting. Eight call sites now delegate to it: `apps/monitoring/security.py`,
`apps/monitoring/permissions.py`, `apps/contact/views.py`, `apps/contact/services.py`,
`apps/trial_exams/views.py`, `apps/trial_exams/services.py`,
`apps/exams/services/exam_center_gate.py`, `core/middleware.py`. `apps/contact/tests.py` had a test
named `test_extract_client_ip_prefers_first_xff_entry` that pinned the spoofable behaviour — it is
rewritten with the reason. `core/tests/test_client_ip.py` includes a repo-wide scan that fails if
`HTTP_X_FORWARDED_FOR` is parsed anywhere outside `core/utils.py`.

---

## 4. Proposal: `.github/workflows/_rls-txn-pool.yml` (not applied)

The `-m postgres` job runs as `test_user`, which must be a PostgreSQL **superuser** so that
`transaction=True` tests can flush (`legacy_import/0003_security_hardening.py:161-165` exempts
superusers from the TRUNCATE guard) — and a superuser bypasses RLS unconditionally, so every
cross-tenant assertion in that job passes vacuously.

Recommended change, in order of preference:

1. **Keep the superuser connection, make the assertions role-switched.** The three real RLS suites
   (`registrar`, `organizations`, `syllabus`) already do `SET LOCAL ROLE rls_app_role` and the
   auditor confirmed all 77 assertions pass under NOBYPASSRLS. Add
   `core/tests/test_rls_gate_integrity.py` (this branch) to the job so the *mechanism* is asserted,
   and treat "an RLS test that does not switch role" as a review defect.
2. **Add a second job step** that runs only the RLS modules as a dedicated NOBYPASSRLS role:

   ```yaml
   - name: 🛡️ RLS suites as a NOBYPASSRLS role
     env:
       DATABASE_URL: postgres://rls_ci_user:rls_ci_password@localhost:5432/test_db
     run: |
       pytest --ds=config.settings.test -m postgres \
         apps/registrar/tests/test_rls.py \
         apps/organizations/tests/test_rls.py \
         apps/syllabus/tests/test_rls.py \
         core/tests/test_rls_platform_logs.py \
         core/tests/test_rls_gate_integrity.py \
         -v --tb=short --timeout=300
   ```

   with `rls_ci_user` created in the service-container bootstrap as
   `CREATE ROLE rls_ci_user LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '…'` plus `CREATEDB` (pytest-django
   needs to create `test_db`). Those modules use `TestCase`, not `TransactionTestCase`, so they do
   not need the TRUNCATE-capable teardown.
3. **Longer term**, replace the `transaction=True` ledger flush with per-test cleanup so the whole
   `-m postgres` job can drop the superuser requirement.

**Also observed (pre-existing, unrelated to these fixes):** on the local agent PostgreSQL every
`TransactionTestCase` fails at teardown with `cannot truncate a table referenced in a foreign key
constraint` (`accounts_accountrestoreevidence → organizations_organization`). Reproduced on a
freshly created database with an unmodified tree, so it predates this branch, but it means the
local `-m postgres` signal is currently unreliable for those classes and should be looked at
alongside item 3.

---

## 5. RLS coverage

Three of the four uncovered tables now have policies, following the `syllabus/0002_rls_syllabus.py`
shape with the `notifications/0005` NULL-org treatment:

| Table | Migration | `USING` | `WITH CHECK` |
|---|---|---|---|
| `audit_auditlog` | `apps/audit/migrations/0003_rls_auditlog.py` | bypass ∨ `organization_id IS NULL` ∨ `= current_org` | `true` |
| `monitoring_securityevent` | `apps/monitoring/migrations/0002_rls_securityevent.py` | same | `true` |
| `ai_assistant_aiassistantlog` | `apps/ai_assistant/migrations/0003_rls_aiassistantlog.py` | same | `true` |

All three have a nullable `organization` FK, and NULL is a *deliberate* platform-level state
(login/logout audit rows, anonymous brute-force telemetry, superadmin cross-org records) — so the
policy admits it explicitly rather than by accident, which is the fail-closed reading
`notifications/0005` established.

**Why `WITH CHECK` is permissive.** `core.audit.log_action` is not wrapped in `bypass_rls()` and is
called from dozens of paths (middleware, Celery, management commands, and
`log_superadmin_cross_org_action`, which writes *another* tenant's org id by design). A strict
`WITH CHECK` would reject those inserts, and most callers swallow audit failures in `except`
blocks — the protection would silently destroy the audit trail it is meant to protect. Row
immutability is already enforced authoritatively by the `audit_log_no_update` /
`audit_log_no_delete` triggers. `core/tests/test_rls_platform_logs.py` asserts both halves: reads
are isolated, and a cross-org write still succeeds.

**Platform read surfaces re-opened explicitly.** With RLS on, a superadmin would otherwise see only
the active org's rows. `apps/audit/views.py::build_audit_log_context` now materialises the page
inside `bypass_rls()` for superadmins (the lazy queryset would otherwise be evaluated during
template render, outside the context), and `superadmin_monitoring_required`
(`apps/monitoring/permissions.py`) wraps the whole view in `bypass_rls()`.

### `accounts_userprofile` — deliberately NOT enabled

This is the highest-value table (8,451 rows: FIN, phone, birth date, address) and the most dangerous
one to protect naively, because **it is the bootstrap table for tenant resolution**. Concretely:

1. `OrganizationMiddleware` calls `apply_rls_request_context(user_id=…, org_id=…)` only **after**
   `request.organization` has been resolved (`apps/organizations/middleware.py:311`). During
   resolution neither `app.current_org_id` nor `app.current_user_id` is set.
2. That resolution itself reads the profile: `core/tenancy.py:142`
   (`resolved_profile = user.profile`) sits **outside** the surrounding `bypass_rls()` block. A
   policy keyed on `current_org` would hide the very row that names the org — a circular dependency.
3. The failure mode is **fail-open, not fail-closed**. Django's `RelatedObjectDoesNotExist`
   subclasses `AttributeError`, so the idiom used throughout the codebase —
   `getattr(user, "profile", None)` — turns a hidden row into `None`. Two concrete regressions:
   `apps/accounts/middleware.py:216-218` (`_requires_first_login`) would return `False` and
   **silently skip the forced first-login password change**; and
   `apps/accounts/views/auth/login.py::classify_user_portal` would lose the profile role and
   mis-route users between portals (the exact "QA Y-1" bug its docstring documents).
4. Blast radius: ~765 `.profile` attribute reads plus 49 `UserProfile.objects` call sites, most of
   them outside any tenant context (OTP verification, password reset, set-initial-password, admin
   2FA, avatar serving).

**Proposal for a follow-up task** (needs its own test pass, not a drive-by):

1. Move the RLS user context earlier — set `app.current_user_id` in `OrganizationMiddleware`
   *before* org resolution (it does not depend on the org), and wrap the profile reads inside
   `core/tenancy.py` in `bypass_rls()` alongside the membership queries.
2. Then add the policy with a self-read branch, so the bootstrap read is legal:
   `bypass ∨ user_id::text = current_user ∨ organization_id IS NULL ∨ organization_id = current_org`.
3. Convert the fail-open idiom on the security-critical paths: `_requires_first_login` and
   `classify_user_portal` must distinguish "no profile row" from "profile hidden" and fail closed.
4. Only then enable `ENABLE`/`FORCE ROW LEVEL SECURITY`, with tests covering login, first-login
   password change, OTP verify, password reset and the org-picker path under `rls_app_role`.

Also still open from the audit's §D: `accounts_accountactivationevidence` and
`accounts_accountrestoreevidence` have RLS enabled but **not** `FORCE`, so the table owner bypasses
their policies (the application role is unaffected). Untouched here — it is a one-line
`ALTER TABLE … FORCE ROW LEVEL SECURITY` per table but belongs with the identity-archive owner.

---

## 6. Re-verification of the five FAIL cases

Real HTTP against the QA clone server (`:8100`), logging in through the role-gated portals, with a
direct `psql` read of the clone before/after each mutating case:

| Case | Actor | Request | Before (audit) | Now | DB |
|---|---|---|---|---|---|
| 27 | `qa.sec.dean_b` | `GET /organizations/myedu-univ/roles/` | **200** | **302** (org picker + error) | — |
| 31e | `qa.sec.exam_center_staff` | `GET /exams/question-bank/1/` | 200 | **200** (read kept by design) | — |
| 31f | `qa.sec.exam_center_staff` | `POST /exams/question-bank/1/` `bulk_action=delete` | **302, row hard-deleted** | **403** | `exams_bankquestion(bank=1)` unchanged |
| 39 | `qa.student` | `GET /exams/center/rooms/` | **200** | **302** | — |
| 46 | `qa.sec.teacher_b` | `POST /accounts/profile/syllabus/action/` `{"action":"copy"}` | **200, syllabus cloned** | **409** `transition.out_of_scope` | `syllabus_syllabus` still 3 rows; teacher_b still owns exactly 1 |

Plus P0-1, anonymous and cookie-less:

| Path | Before | Now |
|---|---|---|
| `/media/journal_lesson_corrections/<uuid>/doc.pdf` | **200 + PDF bytes** | **302 → login** |
| `/media/exam_score_entries/<uuid>/tesdiq.pdf` | **200 + PDF bytes** | **302 → login** |
| `/media/legacy_excuse_documents/<uuid>/1697461819.pdf` | **200 + PDF bytes** | **302 → login** |
| `journal_selfwork/coursework/component_corrections/`, `applications/` | 200 | **302 → login** |
| `/media/post_images/…`, `/media/course_covers/…` (control) | 200 | **200** (still public) |

Script: `scratchpad/reverify.py` — **8/8 PASS**. Note the CSRF cookie on the QA server is
`emsarena_staging_csrftoken`, so the hidden `csrfmiddlewaretoken` field must be parsed from the form;
reading the default cookie name yields 403 on every POST and produces false "blocked" verdicts.

---

## 7. Gates

Run over the 48 files this task touched:

| Gate | Result |
|---|---|
| `black --check` | ✅ (9 files reformatted, then clean) |
| `isort --check-only` | ✅ (3 files fixed, then clean) |
| `flake8` | ✅ clean |
| `scripts/module_deps.py --check` | ✅ no new cycles, **no new `core → apps` edge** |
| `scripts/check_module_size.py --check` | ✅ for my files (largest non-test: `crud.py` 478, `media_policies.py` 331, `media_views.py` 557) |
| `makemigrations --check --dry-run` (sqlite) | ✅ "No changes detected" |

**Module-size failures that are not mine** (both pre-date this work and belong to concurrent
agents; unchanged by me — `git show HEAD:` sizes in brackets):
`apps/legacy_import/models.py` 604 [599] and `apps/registrar/models/grading.py` 602 [594].

**Test runs** (private agent DBs, never the full suite in parallel with other agents):

* New/changed regression modules together — **133 passed**.
* `apps/accounts/tests` — **1149 passed, 1 skipped**.
* `apps/syllabus`, `apps/organizations/tests/test_rls.py`, `apps/monitoring`, `apps/contact` — **301 passed**.
* `apps/trial_exams`, `apps/contact/tests.py`, `core/tests/test_client_ip.py` — **37 passed**.
* `apps/exams/tests` — 999 passed; the remaining failures are all `TransactionTestCase`/Channels
  classes hitting the pre-existing TRUNCATE-flush problem described at the end of §4 (reproduced on
  a fresh DB with the fixes reverted).
* `apps/audit/tests.py` — the 4 new append-only tests pass; `SuperadminCrossOrgAuditTest` and
  `AuditLogSchemaCompatibilityTest` fail identically on a fresh database with an unmodified tree
  (same TRUNCATE-flush cause).

---

## 8. Environment note for the coordinator

At roughly 19:50 the host's iCloud-synced `~/Desktop` was **unmounted mid-session**:
`/Users/elvin/Desktop/Programming Folders/…` vanished and the repository was reachable only at
`/Users/elvin/Library/Mobile Documents/com~apple~CloudDocs/Desktop/Programming Folders/EMSArena/EMSArena`
(same inode). `.venv/bin/pytest` broke because its shebang hard-codes the old absolute path —
`.venv/bin/python -m pytest` works from either path. The mount returned at ~20:05 and the canonical
path is valid again; `scratchpad/serve_qa.sh` was rewritten (by another agent) to use the iCloud
path, which stays correct either way. Earlier in the session `git checkout` also failed with
`pack … is far too short to be a packfile` — the known iCloud pack-eviction trap; no files were
lost, and red-proofs were done with scratchpad copies instead of git.
