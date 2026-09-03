# Phase 2/3 — Security audit (EMSArena, branch `audit/post-migration-qa-2026-09`)

Date: 2026-09-02 · Target: QA clone `emsarena_rehearsal_a0d170000901` (:55433) via the live QA
server `http://127.0.0.1:8100` (daphne, app role `emsarena_app`, RLS enforced).
Production DB (`emsarena_db` @ :5432) was never touched.

**Method note.** The negative tests were executed as *real HTTP requests* against the running QA
server (session cookie obtained through the normal `/accounts/login/` form), not through the
in-process test client — the in-process harness stalled on iCloud eviction of files under `.venv`.
Every mutating case was verified against the database with a direct `psql` read before/after.

**Provenance warning.** A host reboot destroyed the scratchpad mid-audit, taking the three static
sub-review transcripts with it. Part B below distinguishes findings I re-verified myself in this
session (file:line quoted, marked **verified**) from items carried forward from the lost auth
sub-review (marked **carried — re-verify**). Do not action a "carried" item without re-reading it.

---

## A. Negative-test results

56 cases executed (55 negative + 1 positive control). **50 PASS · 5 FAIL.**
PASS = request blocked *and* no database change. "weak" = blocked by redirect/400/409 rather than
403/404, i.e. correct behaviour but a poor signal for an automated scanner.

| # | Case | URL | Acting role | Expect | Actual | Verdict |
|---|---|---|---|---|---|---|
| 1 | lesson edit, foreign offering | `POST /jurnal/<off>/ders/<les>/` | student | block | 404 | PASS |
| 2 | kollokvium save, foreign offering | `POST /jurnal/<off>/kollokvium/` | student | block | 404 | PASS |
| 3 | selfwork action, foreign offering | `POST /jurnal/<off>/serbest/` | student | block | 404 | PASS |
| 4 | coursework save, foreign offering | `POST /jurnal/<off>/kurs-isi/` | student | block | 404 | PASS |
| 5 | add timetable slot | `POST /jurnal/cedvel/` | student | block | 404, no slot | PASS |
| 6 | delete another teacher's slot | `POST /jurnal/cedvel/slot/<id>/sil/` | teacher B | block | 302, slot intact | PASS (weak) |
| 7 | correction apply w/o `journal.correct` | `POST /jurnal/duzelis/<off>/tetbiq/` | teacher (own offering) | 403 | 404 | PASS |
| 8 | correction delete w/o `journal.correct` | `POST /jurnal/duzelis/<off>/sil/` | teacher | 403 | 404 | PASS |
| 9 | correction list | `GET /jurnal/duzelis/` | student | 403 | 404 | PASS |
| 10 | create exam | `POST /exams/create/` | student | 403 | 403, none created | PASS |
| 11 | edit another teacher's exam | `POST /exams/<slug>/edit/` | teacher B | 403 | 403, title intact | PASS |
| 12 | delete another teacher's exam | `POST /exams/<slug>/delete/` | teacher B | 403 | 403, `is_deleted=f` | PASS |
| 13 | open exam edit modal | `GET /exams/<slug>/edit/` | assistant | 403 | 302 → `/` | PASS (weak) |
| 14 | create student group | `POST /exams/groups/create/` | student | 403 | 403 | PASS |
| 15 | save section of another's syllabus | `POST /accounts/profile/syllabus/version/<v>/section/` | teacher B | 403 | 400, status unchanged | PASS (weak) |
| 16 | submit another's syllabus | `POST /accounts/profile/syllabus/action/` | teacher B | 403 | 409, still `draft` | PASS (weak) |
| 17 | approve w/o `syllabus.approve` | `POST /accounts/profile/syllabus/version/<v>/decision/` | teacher | 403 | 404, still `submitted` | PASS |
| 18 | **cross-chair** approve | same | chair_head (chair PROG) → chair IT syllabus | 403 | 404, unchanged | PASS |
| 19 | **cross-faculty** approve | same | dean (Dizayn) → Hitech syllabus | 403 | 404, unchanged | PASS |
| 19b | *positive control* | same | chair_head of the owning chair | allow | 200, approved | OK |
| 20 | kollokvium window activate | `POST /accounts/kollokvium-windows/` | program_coordinator | 403 | 403, 0 windows | PASS |
| 21 | kollokvium extra-day grant | same | exam_center_**staff** | 403 | 302, 0 grants | PASS (weak) |
| 22 | journal close | `POST /accounts/jurnal-baglama/` | chair_head | 403 | 403, 0 notices | PASS |
| 23 | RIM block (HR lacks `user.block`) | `POST /accounts/rim/action/` | hr | 403 | 403, not blocked | PASS |
| 24 | RIM block **targeting a superuser** | same | ikt_rehber | 403 | 404, not blocked | PASS |
| 25 | RIM detail, equal-level peer | `GET /accounts/rim/user/<id>/` | ikt_rehber → ikt_rehber | 403 | 404 | PASS |
| 25b | RIM block, equal-level peer | `POST /accounts/rim/action/` | ikt_rehber | 403 | 404, not blocked | PASS |
| 25c | RIM set_password, equal-level peer | same | ikt_rehber | 403 | 404 | PASS |
| 26 | members page, unknown org slug | `GET /organizations/not-my-org/members/` | student | 404 | 404 | PASS |
| 27 | org **roles/permission matrix** page | `GET /organizations/myedu-univ/roles/` | dean (faculty-scoped) | 403 | **200** | **FAIL** (read-only) |
| 27b | same | teacher | 403 | 302 → org picker | PASS |
| 27c | POST a permission change there | `POST /organizations/myedu-univ/roles/` | dean | block | 200, perms unchanged | PASS |
| 28 | journal detail, foreign offering | `GET /jurnal/<off>/` | teacher B | 404 | 404 | PASS |
| 28b | same | student | 404 | 404 | PASS |
| 29 | review appeal | `POST /appeals/manage/1/` | teacher | 403 | 302 | PASS (weak) |
| 30 | appeal management list | `GET /appeals/manage/` | chair_head | 403 | 403 | PASS |
| 31 | delete another teacher's bank | `POST /exams/question-bank/<id>/delete/` | teacher B | 403 | 404, bank intact | PASS |
| 31b | rename another teacher's bank | `POST /exams/question-bank/<id>/update/` | teacher B | 403 | 404, name intact | PASS |
| 31c | read another teacher's bank | `GET /exams/question-bank/<id>/` | teacher B | 403 | 404 | PASS |
| 31d | bulk-delete in another teacher's bank | `POST /exams/question-bank/<id>/` | teacher B | 403 | 404 | PASS |
| 31e | read another teacher's bank | `GET /exams/question-bank/<id>/` | exam_center_**staff** | 403 | **200** | **FAIL** |
| 31f | **bulk-delete in another teacher's bank** | `POST /exams/question-bank/<id>/` `bulk_action=delete` | exam_center_**staff** | 403 | **302, row hard-deleted (1 → 0)** | **FAIL — write** |
| 32 | guest roster add w/o `journal.roster` | `POST /jurnal/<off>/alt-qrup/elave/` | teacher (own offering) | 403 | 404, no enrolment | PASS |
| 33 | guest roster add outside speciality | same, foreign offering | program_coordinator | 403 | 404, no enrolment | PASS |
| 34 | **inactive membership** carrying `ikt_rehber` | `GET /jurnal/duzelis/` | inactive ikt_rehber | 403 | 302 → `/` | PASS |
| 35 | grant `user.grant_privileged` to teacher role | `POST /accounts/permission-editor/` | ikt_rehber | block | 302, not granted | PASS |
| 36 | **self-escalate own role** | same, own `ikt_rehber` role | ikt_rehber | block | 302, not granted | PASS |
| 37 | permission editor w/o `role.assign` | same | dean | block | 302 → profile, not granted | PASS |
| 38 | manage-roles page | `GET /accounts/manage-roles/` | teacher | 403 | 302 → `/` | PASS |
| 39 | **exam-centre landing page** | `GET /exams/center/rooms/` | student | 403 | **200** | **FAIL** |
| 40 | RIM search | `GET /accounts/rim/search/` | member / student | 403 | 302 / 403 | PASS |
| 41 | exam-centre stats export | `GET /exams/center/stats/export/` | teacher | 403 | 403 | PASS |
| 42 | final-exam PIN lookup | `GET /exams/center/pin-lookup/` | student | 403 | 403 | PASS |
| 43 | journal xlsx of foreign offering | `GET /jurnal/<off>/export.xlsx` | teacher B | 404 | 404 | PASS |
| 44 | registrar console | `GET /jurnal/idareetme/` | teacher | 403 | 404 | PASS |
| 45 | another user's avatar | `GET /accounts/profile-avatar/<id>/` | student | block | 302 | PASS |
| 46 | **copy another teacher's syllabus** | `POST /accounts/profile/syllabus/action/` `{"action":"copy"}` | teacher B | 403 | **200, new syllabus cloned under attacker** | **FAIL — write** |
| — | exam-centre reports / stats data | `GET /exams/center/reports/`, `/stats/data/` | student | 403 | 403 | PASS |

### Writes that succeeded (reverted)
* **31f** — the deleted `exams_bankquestion` row was a probe row I seeded for the test; after the
  exploit the bank is back to its pre-test state (0 questions). No migrated data lost.
* **46** — the cloned syllabus `a98028b2-9933-4e9c-8c31-2d07b3168b85` and its 10 sections were
  deleted from the clone; only the intentional fixture syllabus remains for `qa.sec.teacher_b`.

---

## B. RLS / tenant-isolation suites (role `emsarena_ci_rls`, NOBYPASSRLS, `RLS_TRANSACTION_SCOPED=True`)

| Suite | Result |
|---|---|
| `apps/registrar/tests/test_rls.py` + `apps/organizations/tests/test_rls.py` + `apps/syllabus/tests/test_rls.py` | **77 passed, 0 failed** |
| `apps/legacy_import/tests/test_rls.py` | 19 passed, 1 failed *(harness: `SET SESSION AUTHORIZATION` needs superuser)* |
| `apps/accounts/tests/test_identity_access_postgres.py` | 9 passed, 1 failed *(harness: `DROP OWNED BY` needs superuser)* |
| `apps/organizations/tests/test_rls_transaction_pooling.py` | 1 passed, **10 errored** *(teardown flush blocked — see P1-4)* |

Core tenant isolation is genuinely enforced: all 77 cross-tenant assertions pass under a
NOBYPASSRLS role. Only one organisation exists in the clone, so cross-org probing was covered by
these suites rather than by HTTP cases.

---

## C. Findings

### P0

**P0-1 · Private correction / evidence PDFs are served to anonymous users** — **verified, empirically confirmed**
An unauthenticated `curl` (no cookies) of `http://127.0.0.1:8100/media/journal_lesson_corrections/<uuid>/doc.pdf`
returned **200 with the real PDF bytes**. Same for `journal_selfwork_corrections/`,
`journal_coursework_corrections/`, `journal_component_corrections/`, `exam_score_entries/` and
`legacy_excuse_documents/`. The control prefix `journal_corrections/` correctly returned **302 → login**,
proving a permission-checked media view exists but only covers one of the seven prefixes.
Exposure on this clone: **2,087 real documents** (764 / 500 / 280 / 311 / 178 / 54) — medical
certificates, excuse documents and grade-correction evidence, i.e. student health and disciplinary
data. Filenames are almost all the literal `doc.pdf`, so only the directory UUID is secret.
*Fix:* route every `journal_*_corrections/`, `exam_score_entries/` and `legacy_excuse_documents/`
prefix through the same permission-checked serving view that already guards `journal_corrections/`,
and stop serving those prefixes as static media.

**P0-2 · Exam-centre staff can destroy another teacher's question-bank content** — **verified, exploited on the clone**
`qa.sec.exam_center_staff` (level 60, not the bank owner, not exam-centre *head*) posted
`bulk_action=delete` to `POST /exams/question-bank/1/` (`apps/exams/urls.py:204`, view
`question_bank_detail`) and **hard-deleted** a question from `qa.sec.teacher_a`'s private,
non-shared bank — row count 1 → 0, no audit row written. The same actor also reads the bank (31e:
200) while a peer teacher is correctly refused (31c: 404), so the bank-visibility helper widens
scope for exam-centre roles and the mutating branch then inherits that widened scope without an
ownership check.
*Fix:* gate the `bulk_action` branch of `question_bank_detail` on bank ownership (`created_by`) or
an explicit `qa.*`/`exam.manage` permission, instead of on read visibility.

### P1

**P1-1 · Role-gated login portals are bypassable via the neutral endpoint** — **verified, empirically confirmed**
`apps/accounts/views/auth/login.py:265-272` applies the portal gate only `if self.audience:`, and the
neutral chooser sets `audience = None` (`login.py:137`). I authenticated **all 18 test accounts —
students and staff alike — through a single `POST /accounts/login/`**. The student-vs-staff split is
therefore a UI convention, not a server-side control; anything that assumes "students cannot reach
the staff portal" is unfounded.
*Fix:* resolve the portal from `classify_user_portal(form.get_user())` and enforce it in `form_valid`
even when `self.audience` is `None`.

**P1-2 · A teacher can clone another teacher's syllabus** — **verified, exploited on the clone**
`POST /accounts/profile/syllabus/action/` with `{"action":"copy", "syllabus": <other teacher's id>}`
returned **200** and created a new `syllabus_syllabus` row authored by the attacker containing the
victim's content (`apps/accounts/views/syllabus/api.py:195`, `syllabus_action`). The decision and
section-edit endpoints are correctly scope-gated (cases 15-19 all PASS via
`review_api.py:78-92` `_scoped_version`), so the `copy` branch is the one that skips the gate.
*Fix:* run the `copy` action through the same `services.review_scope_queryset` / author check the
other syllabus actions use.

**P1-3 · Audit log is deletable, so it is not append-only** — **verified**
`apps/audit/admin.py:64-66`: `has_delete_permission` returns `request.user.is_superuser`. Creation
and change are correctly disabled (`admin.py:58-62`) but deletion is not, so a compromised or
malicious superadmin can erase the 22,301-row audit trail from the Django admin UI — including the
records of their own actions.
*Fix:* return `False` from `has_delete_permission` and handle retention through a dated,
out-of-band archival job instead.

**P1-4 · The CI "RLS gate" cannot detect an RLS regression** — **verified**
`.github/workflows/_rls-txn-pool.yml:104-118` runs `pytest -m postgres` as `test_user`. That role
must be a superuser, because `apps/legacy_import/migrations/0003_security_hardening.py:161-165`
exempts superusers from the TRUNCATE guard and the `transaction=True` tests cannot flush otherwise —
I reproduced exactly that: under NOBYPASSRLS the transaction-pooling suite errors 10/11 times at
teardown. But a Postgres superuser also **bypasses RLS unconditionally**, so every cross-tenant
assertion in that job passes vacuously. The gate that is supposed to block promotion on an isolation
regression cannot fail for that reason.
*Fix:* run the `-m postgres` job as a dedicated NOBYPASSRLS role and give that role a
`TRUNCATE`-capable teardown path (or replace the ledger flush with per-test cleanup).

### P2

**P2-1 · Exam-centre surfaces admit any authenticated org member** — **verified**
`apps/exams/views/exam_center/_shared.py:29-35` (`supervisor_org_or_403`) checks only that an active
organisation exists; it performs no role check. A student consequently loads
`GET /exams/center/rooms/` with **200** and the full exam-control UI shell. Data leakage is nil
because the room queryset is then filtered to assigned rooms (empty for a student), and the sibling
endpoints `/center/reports/` and `/center/stats/data/` correctly return 403 — but the landing page
should not render at all, and the same helper gates every `for_supervision=True` view.
*Fix:* add an `is_exam_center_user(request.user) or has assigned rooms` check to `supervisor_org_or_403`.

**P2-2 · Faculty-scoped dean reads the org-wide role/permission matrix** — **verified**
`apps/organizations/views/org_admin/endpoints.py:148-161`: `organization_roles` gates on
`_can_manage_organization`, which the `dean` role satisfies through the implicit `org_admin` alias
granted at level ≥ 80 (`core/roles.py`). A dean scoped to one faculty therefore sees the complete
role catalogue and permission matrix of the whole organisation (case 27: 200). It is read-only — a
POST changed nothing (case 27c) — so this is disclosure, not escalation.
*Fix:* gate `organization_roles` on the `role.view` permission rather than on the `org_admin` alias.

**P2-3 · `organization_id` is accepted from the request body** — **verified**
`apps/accounts/views/kollokvium_windows.py:90` and `apps/accounts/views/journal_close.py:67` both
read `organization_id` out of `request.POST`. Both currently resolve safely (cases 20-22 all PASS,
and RLS is a second net), and only one tenant exists in this dataset, so this is latent rather than
exploitable — but it is the classic IDOR shape and will become live the moment a second organisation
is provisioned.
*Fix:* derive the target organisation from `_get_active_organization(request)` and validate any
supplied id against it.

**P2-4 · `ALERTMANAGER_WEBHOOK_TOKEN` never reaches production settings (settings drift)** — **verified**
`apps/monitoring/views.py:342-354` is the only `@csrf_exempt` view in the codebase and is correctly
token-gated with `hmac.compare_digest`, failing closed when the token is empty. But
`ALERTMANAGER_WEBHOOK_TOKEN` does not appear in `config/settings/production.py`'s explicit
`from .base import (...)` list, so in production it resolves to `""` and the webhook returns 403 to
*every* request — Alertmanager incidents are silently never ingested. Fail-closed, therefore an
availability/monitoring bug rather than a hole, but it is a live instance of the known
base→production import-list drift trap.
*Fix:* add `ALERTMANAGER_WEBHOOK_TOKEN` to the production settings import list and assert it is
non-empty at boot when monitoring is enabled.

**P2-5 · Rate-limiting has two silent global disable paths** — **verified**
`core/rate_limit.py:80-81` and `95-96` return "not limited" whenever `RATELIMIT_ENABLE` is false, and
`:83-85` / `:98-100` do the same whenever `parse_rate()` cannot parse the configured rate string. A
typo in any `*_RATE_LIMIT` env var (e.g. `5/10min` instead of `5/10m`) therefore disables that
limiter silently — including on login and OTP verification — with no warning logged.
*Fix:* log an error and fail closed (or raise at startup) when a configured rate string fails to parse.

**P2-6 · Inconsistent `X-Forwarded-For` parsing across modules** — **verified (needs a decision, not a patch)**
`apps/monitoring/security.py:41-42` and `apps/monitoring/permissions.py:28-30` take the **rightmost**
XFF member, which is correct given that nginx overwrites the header. `apps/contact/views.py:41`,
`apps/contact/services.py:239` and `apps/exams/services/exam_center_gate.py:81` parse the same header
independently. Any of them taking the **leftmost** member would let a client spoof its own IP and
defeat per-IP rate limiting or the exam-room gate.
*Fix:* extract one shared `client_ip(request)` helper documenting the trusted-proxy assumption and
use it in all five call sites.

### Checked and SAFE (not findings)

* **SQL injection** — 22 raw-SQL call sites in app code; all parameterised. The single f-string,
  `core/rls.py:100`, interpolates a developer-built `set_config(%s, %s, %s)` placeholder list and
  passes every value as a bound parameter. No request data reaches SQL text.
* **CSP** — `config/settings/components/csp.py:40-50`: `script-src` is `SELF + NONCE` with **no**
  `unsafe-inline`/`unsafe-eval`; `object-src 'none'`, `frame-ancestors 'none'`, `base-uri 'self'`,
  `form-action 'self'`. Only `style-src-attr` carries `unsafe-inline`, which is the documented,
  deliberately temporary exception.
* **CSRF** — exactly one `@csrf_exempt` in the whole codebase (P2-4 above), token-authenticated.
* **Production cookie/transport settings** — `config/settings/production.py:329-356`:
  `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` all default to `True`;
  HSTS is one year with subdomains and preload derived from it.
* **Permission editor self-escalation** — `apps/accounts/views/roles/permissions.py:29-110` correctly
  restricts the editable role list to `level < user_level` and refuses to grant a permission the
  actor does not itself hold or have delegation for. Cases 35-37 confirm this empirically.
* **RIM hierarchy** — superuser accounts are rejected as targets, and equal-level actors are refused
  (cases 24, 25, 25b, 25c all 404 via the "target not in manageable set" path, which correctly does
  not leak existence).
* **Inactive membership** — a user holding the `ikt_rehber` role through an `is_active=False`
  membership resolves to no role at all (case 34), confirming the gates read active memberships.
* **Syllabus scope gates** — cross-chair and cross-faculty approval are both fail-closed
  (`apps/accounts/views/syllabus/review_api.py:78-92`), with a positive control proving the
  legitimate approver still works.

### Carried from the lost auth sub-review — **re-verify before actioning**

I could not re-confirm these after the reboot; they are recorded so they are not lost, not as
established findings:
* Account enumeration via differing OTP / password-reset responses for existing vs unknown users.
* A superadmin escape hatch in the rate-limit decorator path (distinct from P2-5, which is about
  configuration parsing).
* `ViewAsMiddleware` impersonation: target restriction, audit coverage, and whether the swapped
  identity applies to write endpoints.

---

## D. RLS coverage (read from the live clone, `pg_class` / `pg_policy` — authoritative, not a grep)

79 tables carry an `organization_id` column. **75 have RLS enabled with a policy. 4 do not:**

| Table | Rows on clone | Note |
|---|---|---|
| `accounts_userprofile` | 8,451 | FIN, phone, birth date, address for every user — the highest-value gap |
| `audit_auditlog` | 22,301 | cross-tenant audit trail |
| `monitoring_securityevent` | 8 | security telemetry |
| `ai_assistant_aiassistantlog` | 0 | empty today |

Two further tables have RLS enabled but **not** `FORCE ROW LEVEL SECURITY`
(`accounts_accountactivationevidence`, `accounts_accountrestoreevidence`), so the table owner role
bypasses their policies; the application role is unaffected.

`applications_*` (7 tables) is **already fully covered** — it has RLS and a policy on every table,
so that app is no longer pending. `workload_*` tables **do not exist yet**; mark RLS for the
workload app as **pending** alongside any further `applications` models.

---

## E. Test accounts created on the QA clone

All created on the clone only, password **`QaSec2026!`**, `password_change_required=False`,
`email_verified=True`, org `myedu-univ`. (Pre-existing `qa.*` accounts keep `QaAudit2026!`.)

| Username | Role | Scope unit |
|---|---|---|
| `qa.sec.teacher_a` | teacher | — (instructor of 2 fixture offerings) |
| `qa.sec.teacher_b` | teacher | — (instructor of 1 fixture offering) |
| `qa.sec.chair_head_b` | chair_head | chair *İnformasiya texnologiyaları* |
| `qa.sec.dean_b` | dean | faculty *Filologiya və Tərcümə* |
| `qa.sec.exam_center_staff` | exam_center_staff | — |
| `qa.sec.hr` | hr | — |
| `qa.sec.ikt_rehber_b` | ikt_rehber | — (equal-level RIM target) |
| `qa.sec.assistant` | assistant | — |
| `qa.sec.student_b` | student | — |
| `qa.sec.member` | member | — |
| `qa.sec.inactive_ikt` | ikt_rehber, **membership `is_active=False`** | — |

Fixtures left in place on the clone: three previously instructor-less `registrar_courseoffering`
rows now point at `qa.sec.teacher_a` / `qa.sec.teacher_b`; two fixture syllabi (one approved by the
19b positive control); two exams `QA SEC Exam A/B`; two question banks `QA SEC Bank A/B`; one
schedule slot. No migrated academic data was modified.

---

## F. Suggested fix order

1. **P0-1** private media prefixes (largest blast radius, anonymous, real student health data).
2. **P0-2** question-bank bulk-delete ownership check (destructive, unaudited).
3. **P1-1** portal gate on the neutral login endpoint.
4. **P1-3** audit-log delete permission, **P1-2** syllabus copy scope.
5. **P1-4** RLS CI gate (until this is fixed, no other RLS change is verifiable).
6. P2 items, with **P2-3** to be done before a second organisation is provisioned.
