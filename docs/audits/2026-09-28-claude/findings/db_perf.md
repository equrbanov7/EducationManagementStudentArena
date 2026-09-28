# AUDIT 2026-09-28: DB / ORM / PERFORMANCE / CONCURRENCY / CELERY / OBSERVABILITY (slug `db_perf`)

Repo HEAD `914a6571` (Develop), plus the uncommitted 2026-09-28 working tree (136 paths).
The audit was read-only: no tracked file was edited. The only DB touched was the agent sandbox `ems_audit_db_perf` at 127.0.0.1:55432. Ports :5432 and :55433 were never opened.
Scratch artefacts are in `scratchpad/audit/db_perf/`:
- `test_db_perf_budget.py` → `budget_results.json`
- `test_trace_membership.py`
- `test_silent_rollback.py`
- `test_save_budget.py`
- `asgi_thread_probe.py`
- `mig_scan.py`

## 1. Scope and method (what was actually run)

**Commands and scripts run**

| What | Command / script | Result |
|---|---|---|
| Missing migrations | `manage.py makemigrations --check --dry-run --settings=config.settings.test` | **No changes detected**. The history-consistency check was skipped because the DB did not exist yet, which is harmless. |
| Migration graph | `mig_scan.py` (MigrationLoader, no DB) | 28 apps, 314 migrations, **0 multi-leaf apps**, 0 `RunPython` without reverse, 0 `RunSQL` without reverse. The only op on a big table since the last audit is `registrar 0076` `AddIndexConcurrently` (atomic=False), which is correct. |
| Query budget, 2 scales | `test_db_perf_budget.py` (sandbox, `CaptureQueriesContext`, warm-up GET first) | SMALL = 1 group × 2 students, 2 lessons. FULL = 30 students × 12 lessons, all marked. 21 page×role combinations. See §3.0. |
| Origin of duplicate queries | `test_trace_membership.py` (`execute_wrapper` + stack) | Student cabinet page traced. |
| Grid-save cost | `test_save_budget.py` (real POST to `registrar:journal_detail`) | 2 → 30 students. |
| Silent-rollback proof | `test_silent_rollback.py` (`TransactionTestCase`) | Proves DB-01. |
| Daphne/asgiref concurrency | `asgi_thread_probe.py` (repo venv: Django 5.2, asgiref 3.11.0, Daphne 4.2.2; standalone minimal settings, no repo code, no DB) | Proves DB-03. |

**Code read**
- Settings: `production.py` DB, `celery_cache.py`, `exam.py` request queue.
- Compose: `docker-compose.prod.yml` (postgres, pgbouncer, app, celery), `docker/prod-entrypoint.sh`, `docker/nginx/nginx.conf`.
- `core/rls.py`, `core/rls_pooling.py`, `core/middleware.py` (RequestQueue).
- Task modules: `apps/*/tasks.py`, `core/email_tasks.py`.
- `docker/prometheus/alerts.yml` and `prometheus.yml`, Grafana dashboard, `apps/audit`, `core/audit.py`, `apps/registrar/grade_audit.py`, `status.py`.
- Grade write paths: `gradebook.py`, `finals.py`, `gradebook_components.py`. Also `applications/services/workflow.py`, `exams/services/unit_pin_sync.py`.
- Legacy tooling: `scripts/legacy_reconcile/transport.py`, `docs/migration/reports/MISSING_SCORES_2026-09-25.md`, `k6/reports/*`, `docs/performance/*`.

**Delegated read-only sweeps (spot-verified by me before use)**
1. The 2026-09-28 uncommitted diff (courses/assignments/labs/projects/course_groups/profile my-courses) for ORM, transaction and blocking-work issues.
2. Audit-trail coverage of academic and privilege write paths.

One claim from sweep 2 was **wrong and has been corrected here**: "production sets ATOMIC_REQUESTS=True". In fact `production.py:341-343` sets it only when `RLS_TRANSACTION_SCOPED`, which defaults to False (`docker-compose.prod.yml:80`).

**Not done**
- No load test against any running server.
- No EXPLAIN on real-size data. The clone is off-limits under this brief, so real-volume plans come from the 2026-09-13 audit.
- Exam-attempt paths and WebSocket load belong to the exam auditors.

## 2. Status of prior findings (2026-09-13 perf/data/backend/infra)

| Prior ID | Item | Status | Evidence |
|---|---|---|---|
| perf F-01 | `group_students` N+1 | **FIXED** | `apps/organizations/group_students.py:96,144` `select_related("student","program","group")` |
| perf F-02 | `teacher_group_list` Prefetch `.only()` missing `teacher_id` | **FIXED** | `apps/exams/forms/group.py:197` |
| perf F-03 | individual plan per-student queries | **FIXED** | `apps/registrar/individual_plan.py:197-219` `seasons_cache`/`rows_cache` |
| perf F-04 | 12× duplicate syllabus lookup | **FIXED** | `apps/syllabus/services/offerings.py:62-100`: single OR query ranked by `_tier` |
| perf F-05 | finish `get_or_create` +1 query per question | **FIXED** (now a defensive branch only) | `apps/exams/views/student/attempts.py:287-293` |
| perf F-06 | appeal stats N+1 | **FIXED** | `apps/appeals/views/teacher/statistics.py:263-269` prefetch + `item_count` |
| perf F-07 / F-08 | repeated RLS `set_config` / `access_state` | **FIXED** | `5c081c59`, `e3a1a73a`; session memo `core/rls.py:89-205` (bound to raw connection object, disabled in txn-pool mode and inside atomic). Reviewed; no staleness path found. |
| perf F-09 | `organizations_membership` SELECT 3–5× per page | **STILL OPEN (worse)** | Now **5–9× per page** (§3.0). Traced 8 origins on the student cabinet: `organizations/middleware.py:68/165/342`, `organizations/scoping.py:224` via `rbac.py:227`, `profile/context_builder/builder.py:30` ×3 via `_stage1.py:125,187`, `builder.py:34` via `_stage3.py:166`, `applications/services/access.py:147`. P3. |
| perf F-10 | `/exams/groups/` 2 MB page | **FIXED** | `642cd110` (lazy candidates) |
| perf F-11 | `jsi18n` uncached | **FIXED** | `config/urls.py:74` `cache_page` + `vary_on_headers` |
| perf F-12 / F-13 / F-14 | syllabus list / lessons-log / journal-list org-wide heaviness | **FIXED** | `accounts/views/syllabus/section.py:180-217` (paginate before `build_row`); `registrar/lessons_log.py:62-63` `range_totals` + `totals_cache_key`; `registrar/page_contexts.py:218-262` per-page `_offering_student_counts`. Sandbox FULL: rector journal list 35 queries / 110 ms, lessons-log 49 queries / 235 ms. |
| perf F-15 / F-16 | people analytics planner misestimate; heavy HTML shells | **Not re-verified** (needs clone) / **STILL OPEN** | people-students 182 KB and groups-registry 180 KB even at 2 students (shell weight). |
| perf §6 | `registrar_lesson (organization_id, date)` index | **FIXED** | `registrar/migrations/0076_lesson_org_date_index.py` (`AddIndexConcurrently`) |
| data 6.2 | 9 duplicate indexes | **FIXED** | `642cd110` |
| data 6.2 | LessonMark zero-selectivity org indexes (~60 MB) | **STILL OPEN** (P3) | `registrar/models/grading.py:206-227`: FK `organization` index + `Index(organization, enrollment)` + RLS text index. `entered_by` FK index is on a 100 %-NULL legacy column. |
| data C1 / F1 (P1) | `FinalGrade.exam_score` range CHECK | **FIXED (owner variant 0..100)** | `grading.py:500-502` `registrar_finalgrade_exam_score_range` (0..100, not 0..50, per owner decision). Legacy >50 rows are tolerated by design. |
| data F2 (P1) | superadmin hard delete cascades academic history | **FIXED** | `accounts/services/account_deletion.py:510-557` raises `hard_delete_academic_history` if SAR / Enrollment / attempt exists. The ORM CASCADE (`SAR.student`, `Enrollment.student` CASCADE, `models/academic.py:181`) remains the only structural brake: P3 defence-in-depth. |
| data C3 / C4 | OrgUnit group name / code uniqueness | **STILL OPEN** (P3, needs data clean-up first) | `organizations/models.py:250` only `unique_together (organization, slug)` |
| data 6.4 | `accounts_userprofile` has no RLS | **STILL OPEN** | `organizations/migrations/0018_rls_labs_projects.py:9` note. Owned by the tenancy auditor. |
| data L1–L10 | legacy reconciliation/review | **Not verifiable here** (clone off-limits) | Progress evidence: `docs/migration/reports/MISSING_SCORES_2026-09-25.md` (3,649 current students reconciled against MyEdu; 3 repair steps rehearsed; "production-a HƏLƏ HEÇ NƏ YAZILMAYIB"). The reconcile tool is properly read-only (`scripts/legacy_reconcile/transport.py:1-45, 290-310`: `READ ONLY` txn, `SET LOCAL statement_timeout`, refuses superuser/BYPASSRLS). |
| backend F-02 / F-03 / F-04 | role changes / attempt grants / org status + grade bands unaudited | **FIXED** | `accounts/views/roles/manage.py:187-205` → `_helpers/membership.py:148-180`; `exams/views/teacher/exams/attempt_grants.py:77-158`; `accounts/views/superadmin/endpoints.py:181-372` |
| backend F-07 | multi-write views without atomic | **PARTIAL / REGRESSED in new code** | 11 views wrapped (`8a442dac`), but new or edited 2026-09-28 handlers `assignments/views/teacher/crud.py` and `projects/views/teacher/crud.py` create/edit, and `labs` edit, are not atomic (DB-06). |
| backend F-09 | `.delay` without `on_commit` | **STILL OPEN** (P3, benign while ATOMIC_REQUESTS is off) | `blog/signals.py:180`, `exams/views/teacher/extract_jobs.py:103,163,209` |
| infra P2-6 / P3-14 | sweep blind writes / overlap | FIXED per scorecard | Not re-verified; exam area. |
| infra P3-18 | pgbouncer backend cap | **FIXED** | `docker-compose.prod.yml:294-300` `MAX_DB_CONNECTIONS 230` |
| infra P1-3 / P2-8 | Watchdog, notification-failure alert, heavy-queue monitoring | **FIXED (repo side)** | `docker/prometheus/alerts.yml:336-393` |

## 3. New findings

### 3.0 Measurement: query budget of key pages (sandbox, `config.settings.test`, LocMem cache, local PG 16)

| page (actor) | queries SMALL → FULL | ms FULL | HTML FULL | top duplicate (FULL) |
|---|---|---|---|---|
| teacher journal_detail grid | 60 → 60 | 595 | **493 KB** (80 KB at 2×2) | 5× membership |
| teacher journal_detail yekun | 60 → 60 | 438 | 493 KB | 5× membership |
| teacher journal_list | 32 → 32 | 66 | 52 KB | 4× `current_setting` |
| teacher journal_xlsx | 36 → 36 | 255 | 9 KB | — |
| teacher dashboard / assigned-courses / statistics | 48 / 53 / 52 (flat) | 126–149 | 79–84 KB | 5–7× membership |
| student my-journal / my-subjects / my-transcript / my-courses | 65 → 65 each | 161–207 | 74 KB | **7× membership** |
| student dashboard / notifications | 52 / 52 | 163–232 | 69–76 KB | 5–6× |
| rector journal_list / lessons-log / people-students / groups-registry / audit-log / statistics / analytics | 35 / 49 / 39 / 45 / 42 / 46 / 36 (all flat) | 110–254 | 46–183 KB | up to **9× membership** |
| teacher grid **save** POST (1 lesson) | **36 → 125** (2 → 30 students) | 81 | 302 | per-cell `save()` + per-enrollment `recompute_absence_hours` |

**Reading the table**
- All 21 read pages are **scale-flat**: no N+1 across 2 → 30 students and 2 → 12 lessons.
- Absolute counts are high: 32–65 queries per page, of which about 15–25 are framework/shell (RLS GUC, session, membership ×5–9, badges).
- The grid save is linear, at about 3.2 queries per student, and fine at group scale (DB-10).
- Journal grid HTML is about 1.2 KB per cell. The default window of 20 lessons × 30 students is about 700 KB uncompressed; nginx gzips it.

---

### DB-01 Best-effort grade audit inside `@transaction.atomic` silently discards the grade write while reporting success
Severity: **P2**   Category: Data integrity / Reliability   Status: **CONFIRMED** (test)

**Location:**
- `apps/registrar/grade_audit.py:69-104` (`log_grade_changes`).
- Same pattern in `apps/registrar/status.py:21-45` (`audit_status_change`).
- Callers inside atomic blocks:
  - `gradebook.save_marks` (`gradebook.py:127` `@transaction.atomic`, call at `:249`)
  - `finals.set_exam_score` / `set_resit_score` / `set_final_extras` (`finals.py:291,344,381`)
  - `gradebook_components.save_component_scores` (`:262`, call `:412`)
  - `selfwork_marks.py:109,206`, `journal_extras.py:106`, `gradebook_lessons.py:183,269`, `selfwork_hook.py:248`, `exam_bridge`

Evidence:
```python
    try:
        ...
        AuditLog.objects.create(user=..., organization=offering.organization, ...)
    except Exception:  # noqa: BLE001 — caller chooses the transaction policy
        if fail_closed:
            raise
```
Django's `Model.save_base` runs under `mark_for_rollback_on_error`, so a DB error in the INSERT sets `connection.needs_rollback=True`. The swallowed exception then makes `Atomic.__exit__` issue a silent ROLLBACK (`django/db/transaction.py:242`: commit only if `not connection.needs_rollback`).

How verified: `test_silent_rollback.py`. An `execute_wrapper` makes only `INSERT INTO "audit_auditlog"` raise `DatabaseError`, then `save_marks()` runs for one cell. Output:
```
save_marks result: {'written': 1, 'rejected': 0} | LessonMark rows persisted: 0
1 passed
```
The view then shows "Jurnal yadda saxlanıldı (1 xana)" (`registrar/views.py:582-586`).

**Impact:** any DB-level failure of the audit INSERT loses the whole batch of marks, final/exam scores, component scores, etc., and the teacher is told the save succeeded. Queued `on_commit` notifications are dropped. The trigger is rare because nothing currently rejects audit rows (RLS `WITH CHECK (true)`, no length overflow found). Realistic triggers are transient DB errors, a future constraint/trigger on `audit_auditlog`, or a timeout once DB-02 is fixed. The harm is silent loss of academic data.

**Root cause:** a "best-effort" try/except without a savepoint inside an outer atomic block.

**Recommended fix:**
- In `log_grade_changes` and `audit_status_change`, wrap the create in `with transaction.atomic():` (savepoint) and add `logger.exception(...)` in the `except`. This is the same pattern already used at `apps/appeals/services/decisions.py:52-73` and `apps/subject_folder/services/events.py:70-78`.
- Or make grade audits fail-closed.
- Add a regression test like `test_silent_rollback.py`.

Effort: Small

### DB-02 No statement / lock / idle-in-transaction timeouts anywhere; 900 s proxy and Daphne windows
Severity: **P2**   Category: Reliability / Database   Status: **CONFIRMED** (read)

**Location:**
- `docker-compose.prod.yml:161-199`: postgres `-c` flags have no `statement_timeout`, `lock_timeout`, `idle_in_transaction_session_timeout`, `log_min_duration_statement` or `log_lock_waits`.
- `config/settings/production.py:324-330`: `dj_database_url.config(...)` with no `OPTIONS`.
- `docker/postgres-init/10-create-app-role.sh:46` and `scripts/provision-app-db-role.sh:60`: `ALTER ROLE` sets no timeouts.
- `docker/prometheus/...`: none.
- `docker/nginx/nginx.conf:303` `location /` `proxy_read_timeout 900s`; `docker/prod-entrypoint.sh:34-40` `--http-timeout 900`.
- PgBouncer has no `QUERY_WAIT_TIMEOUT`, so the default is 120 s.

Evidence: `grep -rn "statement_timeout|lock_timeout|idle_in_transaction|connection_created"` over repo code/config (excluding venv/tests) finds hits only in `scripts/legacy_reconcile/transport.py` (read-only reconcile tool).

How verified: grep + read.

**Impact:**
- A runaway query, or a row lock held by a stuck request, blocks writers indefinitely. Grade writes take `SELECT … FOR UPDATE` on the offering (`gradebook.py:150`), so one hung journal transaction freezes that offering's journal for everyone.
- The PgBouncer server connection (session mode) stays pinned for up to 900 s.
- Nothing records slow queries or lock waits in the PG log. Only `pg_stat_statements` is available.

**Recommended fix:**
- `ALTER ROLE <app_role> SET statement_timeout='30s'; SET lock_timeout='5s'; SET idle_in_transaction_session_timeout='60s';`
- Celery, export and OCR paths that need more should use `SET LOCAL statement_timeout` inside their own transaction.
- Postgres: `log_lock_waits=on`, `log_min_duration_statement=1000`.
- PgBouncer: `QUERY_WAIT_TIMEOUT=15`.
- nginx: keep 900 s only for WS/OCR locations and set `location /` to 60 s.
- Do DB-01 first, because timeouts turn latent audit failures into real ones.

Effort: Small (config) + Medium (test the long-running paths)

### DB-03 Capacity model is wrong: `ASGI_THREADS` does not bound sync-view concurrency, and there is no request backpressure
Severity: **P2**   Category: Scalability / Reliability   Status: **CONFIRMED** (probe)

**Location:**
- `docker-compose.prod.yml:438` `ASGI_THREADS=12`.
- `docs/operations/deployment.md:78` ("Daphne + `ASGI_THREADS`").
- `docs/performance/OPTIMIZATION_5000_USERS.md` ("12 × 12 = 144 eyni-anlı sync slot").
- The prior audit's pool maths ("8×12 = 96 connections").
- Django: `core/handlers/asgi.py:165` `async with ThreadSensitiveContext()`. asgiref 3.11 `sync.py:463-469` creates `ThreadPoolExecutor(max_workers=1)` **per request context**. Daphne's `ASGI_THREADS` only sizes the loop *default* executor (`daphne/server.py:11-13`).

Evidence (`asgi_thread_probe.py`, same Django/asgiref/Daphne versions as prod):
```
60 concurrent sync requests x 0.5s, ASGI_THREADS=12 -> elapsed 0.53s, distinct threads 60, peak concurrent in view 60
```

**Impact**
- Every in-flight HTTP request gets its own OS thread. With `CONN_MAX_AGE=0` + PgBouncer **session** mode, each thread also holds its own PgBouncer server connection for the full request.
- The real limits are:
  - the GIL (about 1 core of Python per replica), and
  - the PgBouncer pool (150 + 50 reserve per user/db pair, 230 backend cap).
- Under a burst, threads grow without bound, latency degrades for everyone, and requests wait up to 120 s in PgBouncer instead of being shed. This matches the July k6 login ladder: p95 0.9 s → 16 s from 50 → 1000 VU with 0 % errors (`k6/reports/login-stampede-DEPLOYED_20260718-214509/REPORT.md`).
- Slow requests pin idle DB backends (AI call DB-05, exports, OCR sync fallback), so a few dozen can starve the pool.
- `RequestQueueMiddleware` (8 unsafe requests per process, 60 s wait) is the only admission control, and it covers writes only.

**Recommended fix:**
- Add explicit admission control, for example a nginx upstream `server … max_conns=N` per replica with a `queue` (nginx plus), or a small ASGI/WSGI concurrency-limit middleware for **all** methods (e.g., 24 per replica, 503 + Retry-After). Alternatively switch to gunicorn + N sync workers, where concurrency equals worker count.
- Set PgBouncer `QUERY_WAIT_TIMEOUT=15`.
- Correct the docs and sizing tables.

Effort: Medium

### DB-04 Course "add groups" bulk endpoint: unbounded group list, ~3–5 queries per student in one transaction (2026-09-28 code)
Severity: **P2**   Category: Performance / Concurrency   Status: **CONFIRMED** (read)

**Location:** `apps/courses/views/teacher/groups.py:95-140` `AddMembersBulkView.post`; `apps/registrar/course_groups.py:184-200` `resolve_groups`.

Evidence:
```python
groups = course_groups.resolve_groups(organization=organization, group_ids=request.POST.getlist("group_ids"))
...
with transaction.atomic():
    for group in groups:
        for student in allowed_users.filter(pk__in=ids).order_by("pk"):
            membership, created = CourseMembership.objects.get_or_create(course=course, user=student, defaults=...)
            ...  membership.save(update_fields=["group_name"])
            notify_course_membership_assigned(membership=membership, created=created, ...)
```
`resolve_groups` accepts any number of the org's active groups (no cap, not limited to the teacher's own groups).

How verified: read both functions (sweep finding re-checked).

**Impact:**
- One POST with all org groups (clone: 766 groups / 7.8k students) runs about 25–40k queries and notifications in a single transaction, pinning a thread and a DB backend for minutes and holding row locks.
- The read-then-save of `group_name` can lose an update under concurrent adds, which is P3.

**Recommended fix:**
- Cap `group_ids` (e.g., 20).
- Pre-load existing memberships once, `bulk_create(ignore_conflicts=True)`, then a conditional `.filter(group_name="").update(...)`.
- Send notifications in bulk via `on_commit`.
- Consider limiting groups to the teacher's taught groups (security decision).

Effort: Small–Medium

### DB-05 AI course-plan: synchronous Gemini call in the request thread, no timeout, up to 9 calls + sleeps; check-then-record rate limit
Severity: **P2**   Category: Heavy work in request / Reliability   Status: **CONFIRMED** (read)

**Location:**
- `apps/courses/views/teacher/ai.py:50-69` (new) → `apps/courses/ai_planner.py:117-140` → `apps/exams/services/ai_json.py:48-63` (new) → `apps/exams/services/ai_question_generation.py:95-129`.

Evidence:
```python
for model_name in model_chain:
    for attempt in range(_MAX_RETRIES + 1):          # _MAX_RETRIES = 2
        response = model.generate_content(prompt, generation_config=generation_config)   # no timeout
        ... time.sleep(_RETRY_BASE_DELAY * (attempt + 1))
```
`ai_json.py:48` only *checks* the limit; `:62` records the hit only after success.

**Impact:**
- Each plan request pins a thread and (session pooling) a DB backend for the whole LLM round-trip. Worst case is minutes, under nginx/Daphne 900 s.
- Parallel or failing calls are never counted, so one user can multiply them. This compounds DB-03.

**Recommended fix:**
- Set `request_options={"timeout": 30}` and cap total attempts for this caller.
- Reserve quota atomically before the call, plus a per-user in-flight lock `cache.add`.
- Better: run it as a Celery `heavy` task and poll.

Effort: Small (timeout/quota) / Medium (Celery)

### DB-06 Assignment / project create+edit and lab edit: multi-write POST without a transaction (2026-09-28 code)
Severity: **P2**   Category: Backend / Data integrity   Status: **CONFIRMED** (read + grep)

**Location:**
- `apps/assignments/views/teacher/crud.py:126-157` (create), `:237-270` (edit)
- `apps/projects/views/teacher/crud.py:122-153`, `:232-262`
- `apps/labs/views/teacher/crud.py:285-288` (edit; create is atomic at `:146`)

Evidence (`grep -n atomic` shows none in assignments/projects crud):
```python
assignment = Assignment.objects.create(course=course, ...)
assignment.assigned_students.set(_course_student_users(course, student_ids))
notify_task_assignment(task=assignment, user_ids=..., task_kind="assignment")
```

**Impact:**
- A failure after `create` leaves a committed task with no recipients. The user retries and creates a duplicate.
- Edit can commit new fields with the old recipient list.
- Full-row `save()` overwrites concurrent status changes. Status transitions are not validated against current state, which is P3.

**Recommended fix:** wrap the create/save and `.set()` in `transaction.atomic()`, send notifications via `transaction.on_commit`, and use `save(update_fields=…)`. This is the same fix already applied to `create_lab`.

Effort: Small

### DB-07 Audit-trail gaps for academic changes (who/what/old/new)
Severity: **P2**   Category: Logging / Audit   Status: **CONFIRMED** (read; sweep, spot-checked)

**Location and evidence:**
- **Lesson update not audited:** `gradebook_lessons.py:199-254` (date/hours/kind, `allow_past`/`allow_locked`). Hours change the absence-limit denominator, which drives exam eligibility.
- **Lesson delete only partially audited:** `:257-276` cascades marks but audits "column deleted" with no per-student old values.
- **Catalog console:** `registrar/catalog_console.py:405-437` audits only status. Program, curriculum and admission year changes and **offering instructor** changes (which grant journal write access) are unaudited. Compare `workload/services/offering_sync.py:421`, which does audit.
- **Assignment / lab / project grading:** `task_submission_core/services.py:136-153`, `labs/lab_grading_service.py:55-80` overwrite the grade with no audit.
- **Django admin bulk actions:** `organizations/admin.py:113-123, 285-295, 339-349` use `queryset.update()`, so there is no admin log entry. Membership/role activation is unaudited.
- **Journal "yekun" form:** `registrar/views.py:377-400` calls `finals.set_exam_score` directly, bypassing the `ExamScoreEntry` ledger and justification used by `exam_score_entry.record_exam_score`.
- **Weak identifiers:** grade audit rows carry no `request_id` or IP, and identify students by display name (`grade_audit.py:29-33`).

How verified: read the files above.

**Impact:** a grade-relevant change cannot always be reconstructed (who changed lesson hours or the instructor, who regraded a lab), and per-student history search depends on names.

**Recommended fix:**
- Add `log_action(..., old_values, new_values)` to lesson update/delete (per-student marks on delete), the catalog console field diff, and task grading.
- Make admin actions iterate and log, or use `log_action` in the action.
- Put `request_id` and a student id in grade audit rows.
- Route the yekun form through `record_exam_score`, or document it as intentional.

Effort: Medium

### DB-08 Monitoring blind spots for the DB tier
Severity: **P3**   Category: Monitoring   Status: **CONFIRMED** (read)

**Location:** `docker/prometheus/alerts.yml` (35 rules), `docker/grafana/dashboards/emsarena-overview.json`.

Evidence:
- PgBouncer is scraped (`prometheus.yml:77`) but has **no alert** on `pgbouncer_pools_client_waiting_connections` or `maxwait`.
- No alert on deadlocks (`pg_stat_database_deadlocks`), long or idle-in-transaction sessions, DB size growth, or cache hit ratio.
- `PgConnectionsHigh` text says "max_connections=200" but the config is 250 (`alerts.yml:69-76`).
- Grafana has 5 panels only (HTTP rate, p95, PG connections, 5xx, scrape health); no Celery, Redis or PgBouncer panels.
- The app exposes only `http_requests_total` and a latency histogram (`core/metrics.py:52-66`). There are no in-flight or DB-time metrics.

**Impact:** the most likely saturation mode (DB-03: PgBouncer queueing) is invisible until latency alerts fire.

**Recommended fix:**
- Alerts: `PgBouncerClientsWaiting` (`cl_waiting > 0 for 2m`), `PostgresDeadlocks` (`increase(pg_stat_database_deadlocks[10m]) > 0`), long transactions via the postgres_exporter `pg_stat_activity_max_tx_duration`.
- Add an in-flight requests gauge in `MetricsMiddleware`.
- Fix the alert text.

Effort: Small

### DB-09 Applications workflow: status guard on an unlocked, stale instance
Severity: **P3**   Category: Concurrency   Status: **CONFIRMED** (read)

**Location:** `apps/applications/views/_base.py:56-68` (`load_application`, no `select_for_update`) → `views/endpoints.py:184-196` → `services/workflow.py:53-61,286-330` (`_guard` checks `application.status` in memory, then `save`).

**Impact:** two handlers can concurrently `resolve` and `reject` the same application. Both pass the guard and write two terminal events and two notifications; the last writer wins. The per-actor request queue only serialises the *same* user.

**Recommended fix:** at the start of each transition, `application = Application.objects.select_for_update().get(pk=application.pk)` inside the existing `@transaction.atomic`, or use a conditional `UPDATE … WHERE status=<expected>`.

Effort: Small

### DB-10 Grid save is O(cells) writes
Severity: **P3**   Category: Performance   Status: **CONFIRMED** (measured)

**Location:** `apps/registrar/gradebook.py:180-238` (per-cell `mark.save()`), `:283-300` (per-enrollment `recompute_absence_hours`).

Evidence: POST save 36 → 125 queries for 2 → 30 students (81 ms, sandbox).

**Impact:** fine for one lesson. A "correction mode" save of a whole window (20 lessons × 30 students = 600 cells) is about 1,800+ queries while holding the offering `FOR UPDATE` lock.

**Recommended fix:** `bulk_create` new marks and `bulk_update` changed ones, plus one aggregate for absence hours per enrollment (`values('enrollment').annotate(Sum)`).

Effort: Medium

### DB-11 `StudentAcademicRecord` post_save runs PIN provisioning per save, not de-duplicated
Severity: **P3**   Category: Heavy work in request / signals   Status: **PLAUSIBLE** (read, not measured)

**Location:** `apps/exams/services/unit_pin_sync.py:56-76`. Every SAR save without restrictive `update_fields` queues `on_commit(sync_student_pins_for_unit(group_id))`, which re-provisions PINs for every secure exam of the group.

**Impact:** bulk imports and ATİS/roster scripts that save N records of one group queue N identical syncs in the request/command thread. This is O(N × exams × group size) while final exams are assigned.

**Recommended fix:** de-duplicate per transaction (a set on `connection` or a `transaction.on_commit` guard keyed by `unit_id`), or run it as a Celery task.

Effort: Small

### DB-12 Retention and append-only gaps
Severity: **P3**   Category: Database / Operations   Status: **CONFIRMED** (read)

Evidence:
- `InAppNotification` purge exists only as a manual command (`notifications/management/commands/purge_notifications.py`), not in `CELERY_BEAT_SCHEDULE`.
- `audit_auditlog` has no retention or partitioning.
- The append-only triggers cover UPDATE/DELETE only (`organizations/migrations/0019_audit_log_append_only.py:53-60`), not TRUNCATE. The app role has no TRUNCATE privilege per the 2026-09-13 audit, so the residual risk is the owner role only.

**Recommended fix:** schedule a weekly `purge_notifications` (soft-deleted only), add a `BEFORE TRUNCATE` trigger mirroring `legacy_import/migrations/0003`, and define an audit retention/archival policy (owner decision).

Effort: Small

### DB-13 Framework overhead per page (5–9 identical membership SELECTs)
Severity: **P3**   Category: Performance   Status: **CONFIRMED** (measured + traced)

This is prior F-09, still open. Origins are listed in §2. Request-scoped memoisation of `get_permission_scope` and of `context_builder/builder.py:30-34` would save about 5 round-trips on every cabinet page (about 10 % of the queries).

Effort: Small

### Checked and OK (no finding)
- **Grade write concurrency:**
  - `save_marks` / `finals.*` / components / selfwork are `@transaction.atomic` and take `select_for_update` in the documented order: offering → enrollment → cell.
  - The existing threaded test `apps/registrar/tests/test_grade_write_concurrency.py` covers same-cell races and the no-deadlock ordering.
  - Syllabus section save: `select_for_update` + revision check (`syllabus/services/drafts.py:379-381`).
  - Application numbering is locked (`applications/services/submit.py:42`).
  - Enrollment uniqueness is DB-backed (`uniq_student_offering`).
- **RLS / PgBouncer:**
  - Session pooling + session GUCs + `DISCARD ALL` + `CONN_MAX_AGE=0` is consistent.
  - The transaction-pool path (`RLS_TRANSACTION_SCOPED`) is gated and the session memo disables itself there.
  - `MAX_DB_CONNECTIONS=230 < max_connections 250`.
- **Celery:**
  - `acks_late` + prefetch 1; soft/hard limits of 240/300 s (900/840 s on the heavy queue).
  - `timetable.run_solver` is explicitly sent to `heavy` (`timetable/services/runs.py:294`).
  - Sweeps are CAS/idempotent (per infra); `reap_stuck_extraction_jobs` handles crashed jobs.
  - The broker visibility timeout (default 3600 s) exceeds every task limit; the result backend is bounded (`RESULT_EXPIRES` 3600).
  - Redis runs AOF + `noeviction`; cache and session code tolerate Redis errors (cached_db, `REDIS_CACHE_TIMEOUT` 2 s, RequestQueue local fallback).
  - `task_reject_on_worker_lost` is off: a crashed task is marked failed, not redelivered, which is acceptable given the reaper.
  - Email tasks have bounded retries.
  - The `core.tasks.defer` thread pool is not used for any audit or academic write (only `exams/services/difficulty.py:225`).
- **Migrations:** no pending changes, a single leaf per app, all reversible, concurrent index for the big table.
- **2026-09-28 code:** `registrar/course_groups.py` is org-scoped and batched (about 4–5 queries, search capped at 30); the course dashboard prefetches; review pages are paginated. No new models or migrations.

## 4. Load estimates (ESTIMATES, not measurements)

**Measured inputs**
- **Login:** the July k6 login ladder on the production host (80 cores / 62 GiB, 8 replicas) plateaued at **≈105–112 RPS**, about 55–60 complete logins/s, with host load 70–97. It is CPU-bound on password hashing, with 0 % errors but p95 rising 0.9 s → 16 s (50 → 1000 VU). Source: `k6/reports/login-stampede-DEPLOYED_20260718-214509`, July data, not re-measured.
- **Single process:** the 2026-09-13 clone run reached ≈40 RPS per single process for a light page mix.
- **Page cost:** the sandbox shows 32–65 queries and 65–250 ms per cabinet page.

**Assumptions**
- Each replica is GIL-bound to about 1 core of Python, giving **15–40 page RPS per replica**. The low end is heavy cabinet/journal pages (100–200 ms CPU); the high end is a light mix.
- An active portal user produces about 1 page view per 20–40 s, and one view is about 1.5–2 app requests (HTML + section fragment/JSON), so **0.04–0.1 app RPS per concurrent user**.
- DB in-flight connections = RPS × mean latency (session mode, one connection per in-flight request).
- Exam traffic (autosave every 30 ± 10 s) and WebSockets are excluded; that is the exam auditors' scope.

| Concurrent users | App RPS (est.) | Replicas needed (15–40 RPS each, 50 % headroom) | DB in-flight conns (≈RPS × 0.15 s) | Assessment |
|---|---|---|---|---|
| 100 | 4–10 | 1 | 1–2 | Trivial |
| 500 | 20–50 | 2–4 | 3–8 | OK with the default 8 replicas |
| 1 000 | 40–100 | 3–8 | 6–15 | OK with 8 replicas; p95 should stay < 0.5 s outside login storms |
| 5 000 | 200–500 | **10–25** | 30–75 (fits pool 150) | **At or beyond 8-replica capacity (≈120–320 RPS)**. Needs 12–16+ replicas; the host has the cores, but 16 × 2 GB is 32 GB of RAM. A login storm of 5,000 in < 90 s exceeds the measured ≈55–60 logins/s, giving p95 of several seconds. DB-03 (no shedding) makes overload look like "everything is slow" rather than 503s. |
| 10 000 | 400–1 000 | **20–50** | 60–150 (at the PgBouncer pool 150 + reserve) | **Not feasible on the single host as configured**. RAM runs out: 30 × 2 GB app + 16 GB PG + Redis 4 GB is more than 62 GiB. The pool saturates, and `max_connections` 250 caps it. Needs fewer queries per page (shell memoisation DB-13, caching), a second app host, and either transaction pooling (`RLS_TRANSACTION_SCOPED`, already built but untested at load) or a larger pool. |

**Key sensitivity:** the per-page Python cost. Cutting framework and shell queries from about 25 to about 10 per page (DB-13) and caching badge/shell fragments is the cheapest scalability win. Login capacity is bounded by hash cost × cores. The replica count does not help once the host CPU is saturated.

## 5. Scores (0–100)

| Area | Score | Justification |
|---|---|---|
| **Database** | **80** | Strong schema: UUID PKs, all FKs indexed, rich UNIQUE/CHECK (incl. `exam_score` 0..100), 60+ invariant triggers, append-only audit, RLS+FORCE on most tables, clean reversible migrations, hard-delete gate. Minus: no statement/lock/idle timeouts (DB-02), ORM-only CASCADE on student history, zero-selectivity lessonmark indexes, userprofile without RLS, no OrgUnit name/code uniqueness, no retention. |
| **Backend** | **77** | Service layer is disciplined (locks, atomic, audit on most academic paths; prior F-02/03/04/hard-delete fixed). Minus: silent-rollback audit pattern (DB-01), new non-atomic task CRUD (DB-06), sync LLM in request (DB-05), unbounded bulk add (DB-04), audit gaps (DB-07). |
| **Performance** | **82** | All 21 key pages measured scale-flat; the prior 4 N+1s and 4 heavy org-wide pages are fixed. Minus: 32–65 queries per page with 5–9 duplicate membership SELECTs, a 490–700 KB journal grid, linear grid save. |
| **Scalability** | **64** | 8 replicas + pool 150 carry about 1k users comfortably; 5k needs 12–16+ replicas; 10k is not reachable on one host. The capacity model/docs are wrong (DB-03), there is no backpressure, and session pooling ties DB connections to request lifetime. Transaction pooling is built but off. |
| **Concurrency** | **82** | Grade, final, selfwork and syllabus paths are locked in a documented order and race-tested. Minus: applications workflow (DB-09), course bulk-add and topic order read-modify-write, and no `lock_timeout` to bound lock waits (DB-02). |
| **Reliability** | **68** | Celery design is sound (acks_late, CAS, reaper, queue split, time limits); Redis failure is tolerated. Minus: silent grade loss path (DB-01), no DB timeouts with 900 s windows (DB-02), no load shedding (DB-03), sync fallbacks run heavy jobs in request threads when the broker is down. |
| **Monitoring** | **70** | Watchdog, notification-failure and heavy-queue alerts are fixed; JSON logs with request_id; `pg_stat_statements`; strong audit model. Minus: no PgBouncer-wait, deadlock or long-transaction alerts, sparse Grafana, no slow-query or lock-wait logging (DB-08), audit gaps and weak identifiers (DB-07). |

## 6. Prioritised remediation (db_perf area)

| # | Priority | Action | Dependency | Risk | Effort | Benefit |
|---|---|---|---|---|---|---|
| 1 | P2 (first) | DB-01: savepoint + `logger.exception` in `grade_audit.log_grade_changes` and `registrar/status.audit_status_change`; add a regression test (copy of `test_silent_rollback.py`) | none | very low | S | removes a silent grade-loss path |
| 2 | P2 | DB-06: `transaction.atomic` + `on_commit` notify in assignments/projects create/edit and labs edit | none | low | S | no half-created or duplicate tasks |
| 3 | P2 | DB-02: role-level `statement_timeout 30s`, `lock_timeout 5s`, `idle_in_transaction_session_timeout 60s`; PgBouncer `QUERY_WAIT_TIMEOUT=15`; PG `log_lock_waits`, `log_min_duration_statement=1000`; nginx `location /` 60 s | #1 done; audit long jobs (exports/OCR/legacy) and give them `SET LOCAL` | medium (long jobs may hit the timeout) | S–M | bounded lock/connection hold, visible slow queries |
| 4 | P2 | DB-05: Gemini `timeout=30`, cap attempts, atomic quota reservation + in-flight lock; later move to a Celery heavy task | none | low | S / M | prevents thread/DB pinning by LLM calls |
| 5 | P2 | DB-04: cap `group_ids`, bulk create/update, bulk notify on commit; consider restricting to the teacher's groups | product decision on scope | low | S–M | bounds worst-case request |
| 6 | P2 | DB-03: concurrency-limit middleware (all methods) or nginx `max_conns` per replica + 503/Retry-After; fix the sizing docs; decide the replica count for 5k (12–16) against RAM | load test on staging | medium | M | graceful degradation instead of latency collapse |
| 7 | P2 | DB-07: audit lesson update/delete, catalog instructor/program changes, task grading, admin bulk actions; add `request_id` and student id to grade audits | none | low | M | full academic traceability |
| 8 | P3 | DB-08: PgBouncer-waiting, deadlock and long-transaction alerts; in-flight gauge; Grafana DB/Celery panels | none | none | S | early saturation signal |
| 9 | P3 | DB-13 / F-09: request-scoped memo for membership/permission-scope lookups | none | low | S | about −5 queries on every page |
| 10 | P3 | DB-09 / DB-10 / DB-11 / DB-12: lock application transitions; bulk grid save; de-duplicate PIN sync; schedule notification purge, TRUNCATE trigger, audit retention policy | owner decision for retention | low | S–M each | correctness and hygiene |
| 11 | P3 | Lessonmark index clean-up (drop single `organization_id` FK index or the composite; drop the `entered_by` index), OrgUnit name/code uniqueness after data clean-up | data clean-up for C3/C4 | low (CONCURRENTLY) | S | about 60 MB less index write amplification |
