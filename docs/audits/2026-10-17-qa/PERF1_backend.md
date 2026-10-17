# PERF-1 — Backend performance: queries, DB time, hot paths (2026-10-17)

Scope: server-side cost of the most-used and newest pages and endpoints. This covers query count, DB time, wall time, N+1 patterns, plans, polling endpoints and per-request middleware cost.
Target: the local QA clone `emsarena_rehearsal_a0d170000901` on `127.0.0.1:55433`, used as role `emsarena_app` with RLS enforced.
Nothing was run against prod or the real DB. No repo code was changed. No qa.* password was changed.

## 0. Method, and what it cannot tell you

* **Client.** Django test client with `force_login`, `DEBUG=False`, `SESSION_ENGINE=cached_db` (same as prod), LocMem cache in place of Redis, and `NETWORK_ZONE_ENFORCED=True` for the middleware run. Each endpoint ran 3–5 times.
  * "warm" is the median of runs 2..n.
  * "cold" is run 1. It includes per-process warm-up, so a cold run of ~400–500 ms on the first page of a process is template compilation, not a finding.
* **Prod planner settings mirrored per session.** The clone runs PostgreSQL defaults, so each connection was set to the prod values from `docker-compose.prod.yml`: `random_page_cost=1.1`, `effective_cache_size=6GB`, `work_mem=32MB`, `jit=off`, `effective_io_concurrency=200`.
  * This matters. With clone defaults (`random_page_cost=4`), the legacy-excuse query in the journal picked a **parallel seq scan of `registrar_lesson`** (305 k rows, 14 ms). With prod settings it uses the offering index (0.7 ms).
  * Any timing taken on the clone or staging without these settings overstates DB cost. Consider putting the same `-c` flags on the staging Postgres too.
* **Bypassed redirects.** Real (non-qa) users on the clone still have `password_change_required` and an empty FİN. Their first-login and profile-completion redirects were bypassed in-process (`patches.py`) so that the target page itself was measured. The cost of those two middlewares was measured separately (§3).
* **Writes ran in rolled-back transactions.** This covers autosave, add-lesson, the schedule slots seeded for `action=plan`, the 90-ticket final-center session (`seed_room_monitor_demo`), and the 300-player live session (`lx_be_support`). The clone is unchanged.
* **Measurement limits.**
  * DB time comes from Django's cursor timer, which has ms resolution and includes the local network round-trip. That is about 0.3–0.5 ms per query here, and similar through pgbouncer in prod.
  * Wall time is a fast desktop CPU. Prod app containers are slower per core.
* **Data shape.** The clone's current semester (Payız 2026/2027) has almost no lessons. Full-semester grids were therefore measured on legacy offerings:
  * 50 students × 172 lessons;
  * 557 × 226, a legacy outlier.
* **Scripts and raw JSON:** `/private/tmp/claude-501/-Users-elvin-Developer-EMSArena/fbb0dcda-5104-4c01-810c-9dca5de595d2/scratchpad/perf/`.
  * `harness.py` — the measure loop.
  * `inspect_ep.py` — every SQL statement with its app call-site.
  * `explain2.py` — EXPLAIN ANALYZE under the same RLS context.
  * `mw_cost.py` — interleaved middleware probes.
  * The rest are one script per area.

## 1. Endpoint table (warm unless noted)

q = queries, DB = summed query ms, wall = full request ms, KB = response size.

### Teacher

| Endpoint (user) | q | DB ms | wall ms | KB | Note |
|---|---|---|---|---|---|
| Cabinet full page `/accounts/profile/` (qa.teacher) | 31 | 24 | 55 | 94 | |
| Section `dashboard` XHR (qa.teacher / jale.qeniyeva) | 23 / 22 | 21 / 18 | 44 / 35 | 19 | 3 supervision queries ×2 (F-03) |
| Badges `/accounts/profile/api/badges/` | 16–17 | 6–10 | 14–17 | 0 | fetched on every section switch |
| Journal list `/jurnal/` | 18 | 6–8 | 24 | 49 | budget test exists |
| Journal detail, 31 st × 3 lessons (current semester) | 49 | 32 | 78 | 80 | |
| Journal detail, 50 × 172, default window | 48 | 44 | 144 | 175 | |
| Journal detail, 50 × 172, `lw=0` (all lessons) | 48 | 63 | **410** | 906 | template-bound |
| Journal detail, «Yekun» tab, 50 × 172 | **76** | 76 | 224 | 130 | F-06 |
| Journal detail, 557 × 226 (legacy outlier), default window | 53 | 155 | **939** | 1 115 | F-10 |
| Autosave POST, 1 cell (typical keystroke) | 21 | 6 | 17 | – | |
| Autosave POST, 33 cells, first write / re-save | 28 / 21 | 23 / 17 | 40 / 31 | – | set-based, good |
| New-lesson modal: rooms `ders-otaqlari/` | 9 | 4 | 10 | 9 | |
| New-lesson modal: teacher search `ders-muellimleri/axtar/` | 10 | 9 | 20 | 1 | |
| New-lesson submit (`action=add_lesson`) | 23 | 22 | 28 | – | |
| «Mənim dərs yüküm»: section `my-workload` | 21 | 15 | 35 | 27 | |
| «Mənim dərs yüküm»: `ders-yuku/mene/setirler/` | 13 | 11 | 24 | 32 | |

### Student

| Endpoint (user) | q | DB ms | wall ms | KB | Note |
|---|---|---|---|---|---|
| Cabinet full page (seyideli.eliyev, 6 current subjects) | 24 | 18 | 48 | 89 | |
| Section `dashboard` | 14 | 8 | 27 | 22 | |
| Section `my-journal` (current / 59-enrollment legacy) | 15 / 18 | 11 | 29–31 | 12 | |
| Section `my-subjects` «Fənlərim» (current) | **48** | 60 | 121 | 92 | F-05 |
| Section `my-subjects` «Fənlərim» (legacy, 59 enrollments) | 41 | 58 | 117 | 134 | F-05 |
| Section `my-schedule` (6 subjects) | 27 | 23 | 73 | 17 | 2 queries per subject (F-04) |
| Badges | 17 | 8–14 | 19–30 | 0 | |

### Dean / RİM / chair

| Endpoint (user) | q | DB ms | wall ms | KB | Note |
|---|---|---|---|---|---|
| Section `groups-registry` (dean / teaching_office_head) | 31 / 21 | 22 / 41 | 66 / 137 | 133 / 327 | F-08 |
| Group students drawer JSON, 227 / 55 students | 11 | 8 / 6 | 30 / 16 | 93 / 24 | fine |
| Section `schedule-manage`, ~390–1 550 seeded slots | 23 | 21–25 | 60–63 | 125–138 | |
| Schedule editor `action=plan`, 388 slots in semester | 19 | 14 | 49 | 11 | |
| Schedule editor `action=plan`, **1 552 slots** | 19 | 30 | **150** | 14 | F-07 |
| Schedule editor `action=check`, 1 552 slots | 15 | 32 | **158** | – | F-07 |
| Section `workload-distribution` (chair_head) | 24 | 15 | 30 | 28 | |
| Workload rows `ders-yuku/setirler/` (177 rows) | 22 | 37 | 98 | 314 | F-09 |
| People directory, students list `q=''` / `q='əli'` (dean) | 13 | 21 / 30 | 31 / 43 | 16 | F-13 |
| People directory, teachers `q='ova'` | 12 | 25 | 39 | 7 | |
| RİM centre section `rim-center` | 9 | 3 | 13 | 60 | |
| RİM user search `rim/search/?counts=1` (q='') | **30** | **103** | 125 | 15 | F-02 |
| RİM user search `q='hes'` | 29 | 54 | 75 | 15 | F-02 |
| Journal list as ikt_rehber / TOH / dean | 22 / 22 / 18 | 44 / 46 / 30 | 69 / 77 / 47 | 90 | fine |

### Exams (rolled-back session: 90 tickets, 55 active; live: 300 players)

| Endpoint (user) | q | DB ms | wall ms | KB | Note |
|---|---|---|---|---|---|
| Exam-center room list | 18 | 13 | 29 | 58 | |
| Room monitor page | 18 | 4 | 22 | 177 | |
| **Room snapshot POLL** `rooms/<id>/api/snapshot/` | 9 | 1 | 8 | 76 | 3 s shared cache, good |
| Session monitor page `sessions/<id>/monitor/` | **75** | 18 | 68 | 130 | F-01 |
| **Session snapshot POLL** `sessions/<id>/api/snapshot/` | **71** | 14 | 57 | 76 | **N+1, F-01** |
| Ticket snapshot modal POLL (30 s) | 20 | 9 | 18 | 1 | |
| Student `final_ticket_state` POLL (30 s, WS-down fallback only) | 9–10 | 4 | 10–11 | 0 | |
| Teacher «İmtahanlarım» section (`/exams/` redirects here) | 19 | 8 | 26 | 32 | |
| Student assigned-exams section (`/exams/available/` redirects here) | 15 | 13 | 27 | 9 | |
| **Live `state/<pin>/` player, lobby `light=1`** | 13 | 6 | 9 | 0 | F-11 |
| **Live `state/<pin>/` player, question open** | **17** | 8 | 13 | 1 | 3 s poll if WS down, else 12 s (F-11) |
| Live `state/<pin>/` host, lobby / question | 16 / 19 | 6 / 8 | 12 / 16 | 23–25 | |
| Monitoring: section `system-monitoring` (superadmin) | 14 | 14 | 21 | 19 | |
| Monitoring APIs `exams` / `database` / `incidents` / `summary` | 8–11 | 2–8 | 8–32 | – | Prometheus/Loki unreachable locally; DB part only |

## 2. Findings, ranked by impact

### H — fix soon

**F-01 (H). Session monitor and its 30 s snapshot poll: one `exams_exam` query per active ticket.**
* Evidence: `sessions/<id>/api/snapshot/` ran **71 queries, 55 of them the same `SELECT … FROM exams_exam WHERE id = …`**. The session has 55 active tickets, so the count is 16 + N.
* Call-site: `apps/exams/domain/attempt_deadline.py:52` ← `attempts.py:249` (`deadline_at`) ← `attempts.py:264/275` (`expire_if_time_limit_reached`) ← `services/final_center/tickets.py:397` (`sync_ticket_completion`), plus `_ticket_row` at `monitor.py:91`.
* Cause: `apps/exams/services/final_center/monitor.py:127` loads `session.tickets.select_related("student", "attempt", "exam")`, but `ticket.attempt.exam` is a separate FK and is never loaded.
* Fix: `select_related("student", "attempt", "attempt__exam", "exam")` at monitor.py:127. The ticket snapshot path (`monitor.py:222`) needs the same check.
* Impact:
  * 71 → ~16 queries per poll, constant in seat count. A 300-seat session would otherwise run ~320 queries per poll per open monitor tab.
  * Also add a query-budget test like the room snapshot has.
  * The room snapshot was already fixed (3 s shared cache, 9 q). The session snapshot was not covered by that wave.

**F-02 (H for RİM daily work, M for system load). RİM user search: N+1 on memberships, plus a whole-org DISTINCT/GROUP BY that sorts on disk.**
* Evidence: `/accounts/rim/search/` makes **20 identical membership queries per page**. The call-site is `apps/accounts/services/rim/detail.py:58` (`serialize_memberships`), called from `serialize_row` at `detail.py:104`, from `views/rim/api.py:73`.
* The page query (`services/rim/search.py:239`) takes 56 ms. It aggregates all 9.6 k users with `GROUP BY` and `DISTINCT` over every user + profile + organization column.
  * EXPLAIN: `Sort Method: external merge Disk: 7544kB`, `GroupAggregate rows=9615`.
  * `COUNT(*)` over the same DISTINCT subquery (`search.py:237`) takes another 19 ms, and `status_counts` (`search.py:180`) 17 ms.
  * The `.distinct()` comes from `services/rim/policy.py:327/361`.
* Fix:
  1. After pagination, prefetch once: `Prefetch("memberships", queryset=Membership.objects.filter(is_active=True[, organization=…]).select_related("role", "organization", "scope_unit"), to_attr="_rim_memberships")`. Make `serialize_memberships` use `_rim_memberships` when present, and keep the scope filter in Python.
  2. Drop `.distinct()` in `manageable_users_queryset`. The `GROUP BY` from the `MAX(role.level)` annotation already makes rows unique.
  3. Otherwise paginate on `values("pk")` first, then fetch the 20 full rows.
* Impact: 30 → ~11 queries and ~100 → ~25 ms per keystroke or search. No temp-file spill.

### M — worth a small PR each

**F-03 (M, every staff cabinet request). Supervision-duty check runs 3 queries, twice per cabinet section and once per badges call.**
* Evidence: `exams_invigilatorduty` + 2× `exams_examroomsession` from `apps/exams/services/final_center/duties.py:149/199/204` (`supervision_scope`), via `permissions.py:169` (`user_supervises_final_sessions`), via `apps/accounts/views/_helpers/rbac.py:237` inside `_role_capabilities`.
* `_role_capabilities` runs twice per section render (dashboard x2), so a teacher, tutor, dean or chair pays 6 queries per section and 3 per badges call.
* Fix: memoize `user_supervises_final_sessions` on the user object for the request (`user.__dict__.setdefault("_ems_supervises_final", …)`), or memoize `_role_capabilities(user, profile)` per request. Optionally add a 30 s cache keyed by user, invalidated on `InvigilatorDuty` / `ExamRoomSession` save.
* Impact: −3 to −6 queries (~2–4 ms) on every staff cabinet navigation.

**F-04 (M). Student «Cədvəlim» (`my-schedule`): 2 queries per subject.**
* Evidence: `apps/registrar/page_contexts.py:569` calls `gradebook.entry_score_for(enrollment, cap, rule=…)` without `components=` / `marks=`. Each enrollment then runs `AssessmentComponent.objects.filter(offering=…)` (`gradebook_components.py:93`) and `_own_scored_marks` (`entry_standard.py:329`). That is 6 subjects → 12 queries.
* Fix: before the loop at `page_contexts.py:548`, load components once with `finals_batch` (the same loader as `finals_batch.py:292`), and marks once with `LessonMark.objects.filter(enrollment__in=enrollments, score__isnull=False)` grouped with `finals_batch.group_marks`. Pass both in.
* Impact: 27 → ~15 queries. The count stops growing with subject count (8–10 subjects per semester).

**F-05 (M, students). «Fənlərim» (`my-subjects`) recomputes the same inputs 3–4 times.**
* Evidence: 48 queries, 121 ms. The eligibility trio (assessment scheme status, `legacy_import_legacyentitymap` migrated set, `SUM(lesson.hours)`) runs 4× for the same offering set:
  * `exam_eligibility.py:283/286/311` from `registrar/services.py:326/329`;
  * `analytics.py:424/426`;
  * `cabinet_policy.py:115/116`;
  * `finals_batch.py:411/412`.
* The student's enrollment list is loaded 3× (`services.py:227`, `transcript.py:301`, `cabinet_policy.py:103`).
* Fix: one request-scoped memo keyed by `frozenset(offering_ids)` inside `exam_eligibility` for `frozen_offering_ids` and `lesson_hours_map`. The existing `journal_read_memo` pattern fits. Then pass the already-loaded enrollments through `data["batch_inputs"]`.
* Impact: −12 to −15 queries and ~30–40 ms per open.

**F-06 (M). Journal «Yekun» tab: the components / scores / eligibility batch is built three times.**
* Evidence: 76 queries, 224 ms on 50 × 172. `finals_batch.py:292` (the component query with JSON-path and bits sub-plan, 5–6 ms each) runs 3× from:
  * `gradebook.py:186`;
  * `finals.py:485`;
  * `journal_extras.py:203`.
* The enrollment list is loaded 6×. The scheme-status / migrated / hours trio runs 3×.
* Fix: memo `finals_batch.entry_batch` inputs (components, component scores, eligibility) on the offering object for the request, as `journal_read_memo` already does for scheme, syllabus and kollokvium. Feed `finals.get_offering_results` and `journal_extras.get_final_breakdown` from it.
* Impact: ~76 → ~50 queries, −60 to −80 ms.

**F-07 (M, scales with timetable size). Schedule editor `action=plan` / `check` load and instantiate every live slot of the semester.**
* Evidence: 388 slots → 49 ms; **1 552 slots → 150 ms** for plan and 158 ms for check. The query count stays at 19, so the cost is Python model instantiation.
* Cause: `apps/registrar/schedule_suggest.py:242` → `schedule_conflicts.live_slots` (`schedule_conflicts.py:195-204`) does `select_related` of 5 relations for the whole semester. Only `mine` (group/teacher slots) needs full objects. Room occupancy needs only `pk, weekday, start_time, end_time, week_type, room, offering_id`.
* Fix: two queries.
  1. `live_slots(...).filter(Q(offering__group_id=group) | Q(instructor_id=t) | Q(instructor__isnull=True, offering__instructor_id=t) | Q(offering_id__in=partner_offerings))` with `select_related`.
  2. A `.values(...)` list for room occupancy.
* Impact: ~150 → ~30–40 ms per dialog interaction once the full timetable is in. This is the same order of growth as prod after the timetable imports.

**F-08 (M). Groups registry: unbounded group list and the same settings JSON read three times.**
* Evidence: `apps/organizations/groups_registry.py:285` runs `units = list(queryset)` over all visible groups with a 3-level `select_related` (19.8 ms for teaching_office_head). The response is **327 KB**.
* `_group_settings` is then read 3× (`groups_registry.py:179` via `:192` / `:398` / `:399`, and `:202` via `:402`; 3.2–3.6 ms each). Another all-groups query feeds `group_options` (`:404`, up to 1 000 rows). `student_total` uses `group_id IN (<all ids>)` (`:377`, 9.7 ms).
* Fix:
  * Derive the language and admission-year options from `units` already in memory (one pass), or call `_group_settings` once and pass the list.
  * Make `student_total` a subquery: `group__in=queryset.values("pk")`.
  * Longer term: move the language, course and form filters into SQL (JSON key lookups on `settings`) and paginate in the DB.
* Impact: −4 queries, −15 to −20 ms. Payload reduction needs the SQL-pagination step.

**F-09 (M). Workload distribution rows: rows, prefetch and balance built twice.**
* Evidence: `/ders-yuku/setirler/` 22 q, 98 ms, 314 KB JSON for 177 rows. `distribution_readiness` (`apps/workload/services/distribution.py:32-33`) reloads `task.rows.all().prefetch_related("groups")` and recomputes `balance_for_rows`. `serialize_rows` (`services/queries.py:60-61`) already did both in the same request (`views/distribution_api.py:130-132`). `teacher_load_panel` loads all assignments again (`queries.py:129`).
* Fix: let `serialize_rows` return `(payload, rows, balance)`. Pass `rows` and `balance` to `distribution_readiness` when no season/search filter is applied (otherwise keep the full reload).
* Impact: −3 queries, about −10 ms DB and −20 ms Python.

**F-10 (M for big and legacy journals, L for typical). The journal grid loads every LessonMark as a full model instance.**
* Evidence: 557 × 226 → 939 ms, 1.1 MB. cProfile: 39 k model `__init__` and 146 k `uuid.UUID()` calls. `gradebook.py:180-181` (`get_offering_journal`) loads all marks of the offering with every column. Out-of-window marks feed only totals (absence hours, entry score).
* Fix: `.only("id", "lesson_id", "enrollment_id", "status", "score", "hours"…)` on the marks queryset in `gradebook.py:180`. Or split it: aggregate totals in SQL per enrollment, and fetch full mark rows only for the window lessons.
* Impact: roughly −30–40 % Python time on large grids. A typical current journal (30 × 30) costs only 10–20 ms here.

**F-11 (M on live-game days). Live `state/<pin>/` player poll: 13–17 queries, most of them identical across all players.**
* Polling: every 12 s per player with WS open, every 3 s with WS down (`apps/live_exam/static/js/wait_room_page.js:571`). 300 players gives 25–100 req/s.
* Evidence (`apps/live_exam/views/api.py:151-275`): these are the same for every player of a given (session, index):
  * question count (`domain/session.py:55`);
  * eligible-player count (`api.py:204`);
  * question + options (`domain/session.py:81`);
  * answered count (`api.py:250`);
  * pre-question ranking over all players (`reveal.py:109/306/309`).
* `get_request_player` (`apps/live_exam/auth.py:177`) opens a nested `bypass_rls()` inside the view's own bypass. That adds 3 extra statements: `current_setting`, set, reset.
* Fix:
  * Cache the per-(session, current_index, state) part of the payload for 1–2 s (process-local or Redis), keyed by the session's state version. Keep only the player-specific queries per request: player row, own answer, own rank.
  * Skip the nested bypass when the caller is already in bypass.
* Impact: 17 → ~6 queries per poll. At 300 players with WS down, that is ~1 700 → ~600 queries/s.

### L — cheap wins / hygiene

**F-12 (L, every authenticated request). Baseline middleware runs 6 queries; 1–2 are avoidable.**
* Measured warm: user SELECT, the `accounts_userprofile access_state IN (staged, archived)` EXISTS (`apps/accounts/backends.py:65` → `identity.py:102`), the profile SELECT (`roles.py:20` via `organizations/middleware.py:223`), the RLS `set_config` (1 statement), the membership SELECT, and the RLS reset at response time.
* Fix: in `EmailOrUsernameBackend.get_user`, fetch `User` with `select_related("profile")` and evaluate `access_state` on it. Python-side ~4 ms per request; mostly DB round-trips (cProfile: 70 % inside `OrganizationMiddleware`).
* Impact: −1 to −2 round-trips (~0.5–1 ms) on every authenticated request, about 60 k requests per week in prod.

**F-13 (L). People directory search filters the scope with `OR path LIKE` and seq-scans all records.**
* Evidence: `apps/accounts/services/people/students.py:220-221`. The scope EXISTS has `group_id = X OR orgunit.path LIKE 'X/%'`, which seq-scans `registrar_studentacademicrecord` (8.8 k rows) and `organizations_orgunit` (938). The diacritic regex runs on top (18 ms on q='əli').
* Fix: resolve the scope subtree to a list of unit ids first, then filter `group_id__in=ids`.
* Impact: ~−10 ms per search.

**F-14 (L). Syllabus lookup: 9-relation `select_related` + Case/OR tiers cost ~7 ms of planning for 0.25 ms of execution.**
* `apps/syllabus/services/offerings.py:96-101` (`_RELATED` at `:49`). EXPLAIN on a warm connection: `Planning Time: 6.97 ms`, `Execution Time: 0.245 ms`.
* It runs once per journal open (memoized) and once on the teacher dashboard (`dashboard_widgets.py:171`).
* Fix: pick the syllabus id with the tier query and no joins (`values_list("pk", flat=True)[:1]`), then `select_related(*_RELATED).get(pk=…)`, or trim `_RELATED` to what callers read.
* Impact: −5 to −7 ms per journal open and per teacher dashboard.

**F-15 (L). Membership rows are re-queried even though the middleware already holds `request.org_memberships`.**
* `apps/notifications/services/profile_state.py:41` (badges, every section).
* `apps/surveys/services/inbox.py:26` (badges).
* `apps/registrar/integrity.py:138` via `journal_access.py:61` (×2 per journal open).
* Fix: pass `request.org_memberships` through, or read it from the request when `user == request.user`.
* Impact: −1 to −3 queries per request.

**F-16 (L). `schedule-manage` staff choice list seq-scans all memberships.**
* `apps/registrar/schedule_editor.py:163-170`: 871 staff out of 9.7 k memberships, 7–9 ms, on every editor open.
* Fix: cache per org for 5 min, or restrict the list to the actor's scope.

**F-17 (L, ops). Clone and staging planner settings differ from prod (see §0).**
* Fix: add the same `-c random_page_cost=1.1 -c jit=off -c effective_cache_size=…` flags to the staging Postgres container, so that clone EXPLAINs and QA timings are representative.

## 3. Middleware cost per request (interleaved probes, `scratchpad/perf/mw_cost.py`)

Warm, authenticated, internal IP; external IP with `NETWORK_ZONE_ENFORCED=True` gives the same numbers.

| Middleware | Queries | Notes |
|---|---|---|
| `SessionMiddleware` / session load | 0 (cached_db hit) | 1 query when the cache is cold |
| `SessionTimeoutMiddleware` (forces auth load) | 2–3 | user + access_state EXISTS (+ session when not cached); F-12 |
| `OrganizationMiddleware` (RLS + memberships) | 4 | profile, `set_config` ×1 (one round-trip for 3 GUCs), membership, reset at response; ~4 ms Python + DB |
| `NetworkZoneMiddleware` | **0** | internal and external zone; facts are lazy |
| `FirstLoginPasswordMiddleware` | 0 | |
| **`ProfileCompletionMiddleware` (new)** | **0 warm** (3 cold, once per process / `LOCAL_TTL`, for runtime settings) | 0 for qa.* (exempt). 0 for a real non-exempt user, both when the gate redirects and when the fields are filled. `/exams/` prefix is exempt. It holds its "zero extra queries" docstring promise |
| `SurveyGateMiddleware` | 0 | |
| **Total baseline** | **6** (7 with a cold session cache) | ~5.4 ms per request locally for a 404 page |

## 4. What is already fine (no action)

* **Journal autosave POST.** 21 queries for 1 cell and 28 for 33 cells, in 17–40 ms. Writes are set-based, the count does not grow with cells, and the lock is on the offering row.
* **Group students drawer JSON.** 11 queries for both 55 and 227 students.
* **Room snapshot poll.** 9 q, 8 ms, thanks to the 3 s shared `snapshot_cache`.
* **`final_ticket_state` fallback poll.** 9–10 q, and it only fires every 30 s when WS is down.
* **Journal list `/jurnal/`.** 15–22 q for every role, 22–80 ms. A budget test exists.
* **New-lesson modal lookups.** 9–10 q. **«Mənim dərs yüküm».** 13–21 q, ≤35 ms.
* **RİM centre section.** 9 q. **Monitoring APIs.** DB part is 8–11 q.
* **Live `state` in the lobby with `light=1`.** 13 q, 9 ms (F-11 is about the question phase and the shared parts).
* **`action=plan` query count is constant (19).** Only the Python cost grows with slots (F-07).
* **Legacy-excuse and lesson-mark queries use the offering / lesson indexes under prod planner settings.** The seq scan seen on the clone is a settings artefact (F-17), not a missing index.
* **No missing indexes were found** on the hot paths measured. Every seq scan seen with prod settings was on small tables (orgunit 938, role 25, organization 1), or on whole-population aggregates (RİM search, people scope) where an index would not help (F-02, F-13).
* **No page exceeded 50 queries except** the session monitor and snapshot (75/71, F-01), the «Yekun» tab (76, F-06) and journal detail at 48–53, which is distinct work rather than N+1.
* **Pages over 300 ms locally:** only journal detail with `lw=0` on 172 lessons (410 ms) and the 557-student legacy journal (939 ms), both template/model-bound (F-10). Also `action=plan` / `check` at 1.5 k slots, near 150 ms (F-07).

## 5. Top 5 fixes

1. **F-01.** `apps/exams/services/final_center/monitor.py:127`: add `"attempt__exam"` to `select_related`. The session monitor/snapshot poll drops from 16 + N to ~16 queries. Add a budget test.
2. **F-02.** RİM search (`services/rim/detail.py:58`, `services/rim/policy.py:327/361`): prefetch memberships for the page and drop the redundant `DISTINCT`. 30 → ~11 queries, ~100 → ~25 ms, no disk sort.
3. **F-03.** Memoize `user_supervises_final_sessions` / `_role_capabilities` per request (`apps/accounts/views/_helpers/rbac.py:237`). −3 to −6 queries on every staff cabinet section and badges call.
4. **F-07.** `schedule_suggest._Plan` (`schedule_suggest.py:242`): load full slot objects only for the group/teacher, and a `.values()` list for room occupancy. 150 → ~35 ms at 1.5 k slots, before the full timetable lands.
5. **F-05 + F-06 + F-04.** One request-scoped memo for eligibility inputs and component batches (`exam_eligibility`, `finals_batch.entry_batch`), and batch components/marks in `page_contexts.py:569`.
   * «Fənlərim» 48 → ~33 queries.
   * «Yekun» 76 → ~50 queries.
   * «Cədvəlim» stops growing per subject.
