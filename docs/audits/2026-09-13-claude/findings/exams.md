# AUDIT — İMTAHAN SİSTEMİ (slug `exams`) — 2026-09-13 (ikinci buraxılış, RESUME)

Baza: Develop HEAD `96016cff`. Auditor READ-ONLY; bütün artefaktlar `scratchpad/audit/exams/`.
Əvvəlki auditor (rate-limit ilə kəsilib) bu qovluqda 4 repro test faylı + 1 perf testi + `inventory.py` qoymuşdu; onlar
sandbox DB `ems_audit_exams`-də yenidən işlədilib (`pytest_run1.log`).

Baxılan əvvəlki hesabatlar: `docs/audits/2026-09-12-codex/FINAL_REPORT_AZ.md` (§13 yalnız kağız-bal axını), `docs/audits/2026-09-05/ISSUES.md`,
`docs/audits/2026-09-02/PHASE23_SECURITY*.md` (P0-2 sual bankı, P2-1 mərkəz səthi — bu hesabatda yenidən yoxlanılır).

## 0. Status cədvəli (yoxlama başlıqları)

| # | Yoxlama | Status | Sübut |
|---|---|---|---|
| 1 | Lifecycle & state machine | PARTIAL (publish/unpublish/delete/restore PASS; bilet yolu siyasəti FAIL EX-04; draft constraint FAIL EX-08) | §1, §3.1 |
| 2 | PIN / imtahan girişi | FAIL (EX-02 zal-kənar final start, EX-03 rate-limit yox, EX-06 IP limiter bypass); `/exams/final/` enumeration PASS | §3.2 |
| 3 | Taymer & submit | PARTIAL (server deadline authority PASS; deadline-anı POST itkisi EX-05; OCC/409 PASS) | §3.3 |
| 4 | Sual/cavab məxfiliyi | FAIL (EX-01 in_progress nəticə səhifəsi cavab açarını verir); take_exam HTML/JSON PASS | §3.4 |
| 5 | Paralellik | PARTIAL (DB unique in_progress + actor lock PASS; draft boşluğu EX-08; valideyn sətir kilidi EX-09; qiymətləndirmə kilidli PASS) | §3.5 |
| 6 | Tenant/rol sərhədləri + endpoint inventarı | PARTIAL (164 endpoint inventarı; cross-tenant cəhd endpoint-ləri PASS; sual bankı yazı qapısı FAIL EX-10) | §2, §3.6 |
| 7 | Audit logları | PASS (publish/unpublish/results-hidden/delete/restore/duplicate/grant/session/ticket/PIN-lookup/grade ledger) | §3.7 |
| 8 | Performans | PARTIAL (start/take/autosave/result büdcəsi sual sayından asılı deyil; finish N+1 EX-11; klon cəhd cədvəli boş → EXPLAIN N/A) | §3.8 |

## 1. Vəziyyət maşını (state machine)

### 1.1 Exam (`apps/exams/domain/exam_definition.py`)
Status hesablanır (`lifecycle_status`, :309-328): `draft` (`is_active=False`) → `scheduled` (aktiv, `start_datetime` gələcəkdə) → `active`. Əlavə bayraqlar: `is_deleted` (zibil qutusu), `is_archived` (legacy, ləğv edilib), `results_hidden_from_students`.

| Keçid | Yol | Qapı | Atomiklik | Audit | Status |
|---|---|---|---|---|---|
| draft → active (publish) | `services/lifecycle.py:publish_exam` (:48-74); create/edit modalı avtomatik çağırır (`views/teacher/exams/list_detail.py:180-186`) | aktiv sual var + dil-parity + silinməyib (`exam_publish_gate_error`) | `select_for_update` + şərti UPDATE | `exam_published` | PASS |
| active → draft (unpublish) | `unpublish_exam` (:77-86) | — | şərti UPDATE | `exam_unpublished` | PASS |
| form ilə `is_active` dəyişmə | `forms/exam.py:296-303` — sahə `disabled`+`HiddenInput` | qapı keçilmir | — | — | PASS (sualsız imtahan publish ola bilməz) |
| results hidden ↔ published | `set_results_hidden` (:89-109) | — | şərti UPDATE | `exam_results_hidden/published` | PASS |
| → deleted (soft) | `views/teacher/exams/actions.py:130-165` | müəllif və ya `exam.delete` icazəsi | plain save (`is_deleted, deleted_at, is_active=False`) | `exam_soft_deleted` | PASS (cəhdlər qorunur; `can_user_start` `is_deleted` rədd edir `domain/access_policy.py:253`) |
| deleted → restored | `actions.py:320-350` | `_get_deleted_exam_or_404` (author+tenant) | `is_active` toxunulmur → draft kimi qayıdır | `exam_restored` | PASS |
| duplicate | `services/duplication.py:79-83` — kopya `is_active=False` | | | `exam_duplicated` | PASS |
| **Bilet yolu ilə start** | `services/final_center/tickets.py:270-327` | oturum ACTIVE + bilet WAITING/READY; **`can_user_start` yox** (vaxt pəncərəsi, `max_attempts`, `is_active` yoxlanmır) | atomic | ticket audit | **FAIL → EX-04** |

### 1.2 ExamAttempt (`domain/attempts.py:19-24`, constraint :220-228)
Statuslar: `draft`, `in_progress`, `submitted`, `expired`. `is_finished` = status ∈ {submitted, expired} (`ATTEMPT_FINISHED_STATUSES`).

| Keçid | Yol | Qapı | Status |
|---|---|---|---|
| ∅ → in_progress | `services/attempts.py:_create_attempt_or_get_active` (:261-303) | `can_user_start` + `attempts_left_for` (qrant-şüurlu) + cache actor-lock + kapasite qapısı + DB unique (`in_progress`) | PASS (cache yoxdursa DB constraint son xətt) |
| in_progress → draft | `views/student/attempts.py:432-434` (`save_draft`) | tələbənin öz POST-u | **DB unique `draft`-ı əhatə etmir → EX-08** |
| draft → in_progress | `start_exam` resume (`get_active_attempt_for_user` draft-ı da aktiv sayır) | | PASS |
| in_progress/draft → submitted | `finish` POST (`attempts.py:419-422`), supervision resume-window expiry (`domain/attempts.py:324`), `end_room` (final center) | lock altında `mark_finished` | PASS; jurnal körpüsü `mark_finished` boğazından (`schedule_journal_sync`) |
| in_progress/draft → expired | `expire_if_time_limit_reached` (`domain/attempts.py:269-273`) — GET/POST lazy, periodik sweep (`sweep_overdue_attempts`) | `deadline_at = started_at + total_duration_minutes` | PASS (server authority) — amma POST-dan ƏVVƏL çağırılır → EX-05 |
| finished → in_progress (reopen) | `services/supervision/actions.py:teacher_resume_attempt` | `attempt.is_finished → ValueError` (:26-27) | PASS (bitmiş cəhd yenidən açılmır) |
| nəticə görmə | `views/student/results.py:exam_result` | **status yoxlanmır** | **FAIL → EX-01** |
| qiymət dəyişmə | `services/manual_grading.py` (`select_for_update` attempt+answers, `ExamGradeEvent` ledger) | `_ensure_teacher` + author-scoped exam | PASS |

### 1.3 FinalExamTicket / ExamRoomSession (`domain/final_center.py:55-100`)
Bilet: `assigned → waiting → ready → active → completed`, yan keçidlər `removed/absent`; `TICKET_TRANSITIONS` cədvəli ilə (`transition_ticket` şərti UPDATE). Oturum: `scheduled → entry_open → active → ended/cancelled` (`services/final_center/sessions.py` open/start/end/cancel — hamısı `_audit_session`). PASS (kod oxunuşu; 09-02/09-05 auditlərində də yoxlanıb).

### 1.4 ExamStudentPin (`domain/student_access.py`)
Yaradılış: `provision_exam_student_pins` (create/edit modalı, final/midterm). `expires_at = end_datetime + 120 dəq`, `revoked_at`. `verify_student_pin` sabit-vaxt + `is_usable`. Kabinetdə dərhal görünür (`student_visible_pin`, Fernet). PASS — amma PIN-in özü zal-kənar başlanğıc üçün kifayət edir (EX-02).

## 2. Endpoint inventarı

Mənbə: `inventory.py` (statik guard-token skaneri, HEAD `96016cff`) → `endpoint_inventory.md`. 129 (exams) + 9 (appeals) + 26 (live_exam) = **164 endpoint**. «auth» = `login_required`; «rol/obyekt guard» və «tenant guard» sütunları view mənbəyində görünən tokenlərdir (helper daxilindəki yoxlama görünmür — «-» ≠ qoruma yoxdur; aşağıda əl ilə yoxlananlar qeyd olunub).

Əl ilə yoxlanan «tenant token-siz» view-lar (statik skanerin false-positive-ləri):
- `exam_center_room_monitor/snapshot/attempt_violations/start_all/end_all/open_all` → `_get_room_and_sessions` → `supervisor_org_or_403` + `ExamRoom(organization=…)` + `can_supervise_session` (`views/exam_center/room_monitor.py:42-55`) — PASS.
- `question_bank_delete` → `accessible_banks` + `created_by_id == user` (`question_library/crud.py:207-224`) — PASS. `bank_question_add/edit`, `question_bank_bulk_add`, `ai_generate_bank_questions` → yalnız `accessible_banks` — **FAIL EX-10**.
- `coding_autosave/run/submit/submission_download` → `_get_coding_attempt` (`tenant_scoped_exams` + `user=request.user` + `ensure_active_attempt_access`, `views/student/coding.py:58-70`) — PASS.
- appeals `my_appeals/manage_appeals/review_appeal/appeal_detail` → `can_review_appeal/_same_tenant` (`apps/appeals/services/permissions.py:41-60`), `appeal_create` `tenant_scoped_exams` + `user=request.user` (`views/student/endpoints.py:143-152`) — PASS.
- live_exam `teacher_live_results/teacher_live_session_detail` → `_ensure_teacher_access` (`exam.manage|exam.host` + `exam.organization_id == request.organization.id`, `apps/live_exam/views/results.py:25-33`) — PASS (org-daxili istənilən müəllif — dizayn). Anonim `pin_entry/join_*/player_screen/answer_submit/state_json/qr_png` — Kahoot-tipli, oyunçu cookie-token ilə (`auth.py:148`) — dizayn üzrə anonim.
- `exam_code_check` → `tenant_scoped_exams` var, amma final üçün zal qapısı yoxdur — **EX-02/EX-03**.

Cross-tenant/cross-user sübut testləri (sandbox): `CrossTenantAttemptEndpointsTests` — B təşkilatının tələbəsi (allowed_users-də olsa belə) `take_exam`/`question_seen`/`start_exam` → 404, attempt yaranmır; eyni org-un başqa tələbəsi yad cəhdə `take_exam`/`exam_result` → 404. **PASS**.

<details><summary>Tam cədvəl (164 sətir)</summary>


### exams (129 endpoint)

| # | METHOD | PATH | view | auth | rol/obyekt guard | tenant guard | qeyd |
|---|---|---|---|---|---|---|---|
| 1 | ANY | `/exams/available/` | `exams.views.student.lists.student_exam_list` | login_required | - | tenant_scoped_exams | - |
| 2 | GET,POST | `/exams/final/` | `exams.views.student.final_center.final_exam_entry` | manual is_authenticated | _ensure_hall_access, _validated_session_ticket | _validated_session_ticket | login(request |
| 3 | ANY | `/exams/final/waiting/<int:ticket_id>/` | `exams.views.student.final_center.final_exam_waiting` | login_required | _ensure_hall_access, _resolve_own_ticket | _resolve_own_ticket | - |
| 4 | POST | `/exams/final/waiting/<int:ticket_id>/cancel/` | `exams.views.student.final_center.final_exam_cancel` | login_required | _ensure_hall_access, _resolve_own_ticket | _resolve_own_ticket | - |
| 5 | POST | `/exams/final/waiting/<int:ticket_id>/begin/` | `exams.views.student.final_center.final_exam_begin` | login_required | _ensure_hall_access, _resolve_own_ticket | _resolve_own_ticket | - |
| 6 | ANY | `/exams/final/waiting/<int:ticket_id>/state/` | `exams.views.student.final_center.final_ticket_state` | login_required | _resolve_own_ticket | _resolve_own_ticket | - |
| 7 | ANY | `/exams/assigned/` | `exams.views.student.lists.assigned_student_exam_list` | login_required | - | tenant_scoped_exams | - |
| 8 | ANY | `/exams/my-history/` | `exams.views.student.results.student_exam_history` | login_required | - | tenant_scoped_exams, user=request.user | - |
| 9 | POST | `/exams/code-check/` | `exams.views.shared.access.exam_code_check` | login_required | - | tenant_scoped_exams | - |
| 10 | ANY | `/exams/center/rooms/` | `exams.views.exam_center.rooms.exam_center_room_list` | login_required | supervisor_org_or_403 | organization=org, organization=organization, supervisor_org_or_403 | - |
| 11 | ANY | `/exams/center/rooms/<int:room_id>/monitor/` | `exams.views.exam_center.room_monitor.exam_center_room_monitor` | login_required | can_assign_invigilators | - | - |
| 12 | POST | `/exams/center/rooms/<int:room_id>/invigilators/` | `exams.views.exam_center.room_monitor.exam_center_room_assign_invigilators` | login_required | can_assign_invigilators, supervisor_org_or_403 | organization=org, organization=organization, supervisor_org_or_403, user=request.user | - |
| 13 | ANY | `/exams/center/rooms/<int:room_id>/api/snapshot/` | `exams.views.exam_center.room_monitor.exam_center_room_snapshot` | login_required | - | - | - |
| 14 | ANY | `/exams/center/rooms/<int:room_id>/api/attempts/<int:attempt_id>/violations/` | `exams.views.exam_center.room_monitor.exam_center_attempt_violations` | login_required | - | - | - |
| 15 | POST | `/exams/center/rooms/<int:room_id>/start-all/` | `exams.views.exam_center.room_monitor.exam_center_room_start_all` | login_required | - | - | - |
| 16 | POST | `/exams/center/rooms/<int:room_id>/end-all/` | `exams.views.exam_center.room_monitor.exam_center_room_end_all` | login_required | - | - | - |
| 17 | POST | `/exams/center/rooms/<int:room_id>/open-all/` | `exams.views.exam_center.room_monitor.exam_center_room_open_all` | login_required | - | - | - |
| 18 | ANY | `/exams/center/sessions/<int:session_id>/` | `exams.views.exam_center.sessions.exam_center_session_detail` | login_required | get_center_session_or_404 | get_center_session_or_404 | - |
| 19 | ANY | `/exams/center/sessions/<int:session_id>/history/` | `exams.views.exam_center.sessions.exam_center_session_history` | login_required | ensure_can_view_final_history, supervisor_org_or_403 | organization=org, organization=organization, supervisor_org_or_403 | - |
| 20 | ANY | `/exams/center/sessions/<int:session_id>/monitor/` | `exams.views.exam_center.monitor.exam_center_session_monitor` | login_required | get_center_session_or_404 | get_center_session_or_404 | - |
| 21 | ANY | `/exams/center/sessions/<int:session_id>/api/snapshot/` | `exams.views.exam_center.monitor.exam_center_session_snapshot` | login_required | get_center_session_or_404 | get_center_session_or_404 | - |
| 22 | ANY | `/exams/center/sessions/<int:session_id>/tickets/<int:ticket_id>/snapshot/` | `exams.views.exam_center.monitor.exam_center_ticket_snapshot` | login_required | get_center_session_or_404 | get_center_session_or_404 | - |
| 23 | POST | `/exams/center/sessions/<int:session_id>/tickets/<int:ticket_id>/resume/` | `exams.views.exam_center.monitor.exam_center_ticket_resume` | login_required | get_center_session_or_404 | get_center_session_or_404 | - |
| 24 | POST | `/exams/center/sessions/<int:session_id>/tickets/<int:ticket_id>/reentry/` | `exams.views.exam_center.monitor.exam_center_ticket_reentry` | login_required | get_center_session_or_404 | get_center_session_or_404, organization=org, organization=organization, user=request.user | raw_pin |
| 25 | POST | `/exams/center/sessions/<int:session_id>/open-entry/` | `exams.views.exam_center.monitor.exam_center_session_open_entry` | login_required | get_center_session_or_404 | get_center_session_or_404 | - |
| 26 | POST | `/exams/center/sessions/<int:session_id>/start/` | `exams.views.exam_center.monitor.exam_center_session_start` | login_required | get_center_session_or_404 | get_center_session_or_404 | - |
| 27 | POST | `/exams/center/sessions/<int:session_id>/end/` | `exams.views.exam_center.monitor.exam_center_session_end` | login_required | get_center_session_or_404 | get_center_session_or_404 | - |
| 28 | POST | `/exams/center/sessions/<int:session_id>/cancel/` | `exams.views.exam_center.monitor.exam_center_session_cancel` | login_required | get_center_session_or_404 | get_center_session_or_404 | - |
| 29 | POST | `/exams/center/sessions/<int:session_id>/tickets/<int:ticket_id>/remove/` | `exams.views.exam_center.monitor.exam_center_ticket_remove` | login_required | get_center_session_or_404 | get_center_session_or_404 | - |
| 30 | POST | `/exams/center/sessions/<int:session_id>/tickets/<int:ticket_id>/seat/` | `exams.views.exam_center.sessions.exam_center_ticket_seat` | login_required | get_center_session_or_404 | get_center_session_or_404 | - |
| 31 | POST | `/exams/center/sessions/<int:session_id>/tickets/<int:ticket_id>/readmit/` | `exams.views.exam_center.sessions.exam_center_ticket_readmit` | login_required | get_center_session_or_404 | get_center_session_or_404 | - |
| 32 | ANY | `/exams/center/reports/` | `exams.views.exam_center.reports.exam_center_reports` | login_required | center_org_or_403 | center_org_or_403, organization=org, organization=organization | - |
| 33 | GET | `/exams/center/stats/data/` | `exams.views.exam_center.statistics.exam_center_stats_data` | login_required | - | _stats_org | - |
| 34 | GET | `/exams/center/stats/export/` | `exams.views.exam_center.statistics.exam_center_stats_export` | login_required | - | _stats_org | - |
| 35 | GET | `/exams/center/stats/filters/` | `exams.views.exam_center.statistics.exam_center_stats_filters` | login_required | - | _stats_org, organization=org, organization=organization | - |
| 36 | GET | `/exams/center/stats/charts/` | `exams.views.exam_center.statistics_charts.exam_center_stats_charts` | login_required | - | _stats_org | - |
| 37 | GET | `/exams/center/stats/ai/` | `exams.views.exam_center.statistics_charts.exam_center_stats_ai` | login_required | - | _stats_org | - |
| 38 | ANY | `/exams/center/pin-lookup/` | `exams.views.exam_center.pin_lookup.exam_center_pin_lookup` | login_required | center_org_or_403 | center_org_or_403 | - |
| 39 | GET | `/exams/center/pin-lookup/search/` | `exams.views.exam_center.pin_lookup.exam_center_pin_search` | login_required | center_org_or_403 | center_org_or_403, organization=org, organization=organization | - |
| 40 | GET | `/exams/center/pin-lookup/student/<int:student_id>/` | `exams.views.exam_center.pin_lookup.exam_center_student_pins` | login_required | center_org_or_403 | center_org_or_403, organization=org, organization=organization, user=request.user | decrypt_ticket_pin, student_visible_pin |
| 41 | ANY | `/exams/` | `exams.views.teacher.exams.list_detail.teacher_exam_list` | login_required | - | - | - |
| 42 | ANY | `/exams/create/` | `exams.views.teacher.exams.list_detail.createAndEditExamView` | login_required | _ensure_exam_permission, _ensure_teacher, is_superadmin_user | _get_editable_exam_or_404, organization=org, organization=organization, user=request.user | - |
| 43 | GET | `/exams/lookups/subjects/` | `exams.views.teacher.exams.lookups.subject_search` | login_required | _ensure_teacher | organization=org, organization=organization | - |
| 44 | GET | `/exams/lookups/bank-teachers/` | `exams.views.teacher.exams.lookups.bank_teacher_search` | login_required | _ensure_teacher | - | - |
| 45 | GET | `/exams/lookups/groups/` | `exams.views.teacher.exams.lookups.group_search` | login_required | _ensure_teacher | organization=org, organization=organization | - |
| 46 | GET | `/exams/lookups/faculties/` | `exams.views.exam_center.statistics.stats_faculty_search` | login_required | - | _stats_org, organization=org, organization=organization | - |
| 47 | GET | `/exams/lookups/departments/` | `exams.views.exam_center.statistics.stats_department_search` | login_required | - | _stats_org, organization=org, organization=organization | - |
| 48 | GET | `/exams/lookups/teachers/` | `exams.views.exam_center.statistics.stats_teacher_search` | login_required | - | _stats_org, organization=org, organization=organization | - |
| 49 | GET | `/exams/lookups/users/` | `exams.views.teacher.exams.lookups.user_search` | login_required | _ensure_teacher | organization=org, organization=organization | - |
| 50 | GET | `/exams/lookups/invigilators/` | `exams.views.teacher.exams.lookups.invigilator_search` | login_required | can_assign_invigilators | organization=org, organization=organization | - |
| 51 | GET | `/exams/lookups/assigned-count/` | `exams.views.teacher.exams.lookups.assigned_student_count` | login_required | _ensure_teacher | - | - |
| 52 | GET | `/exams/<slug:slug>/available-question-count/` | `exams.views.teacher.exams.lookups.exam_available_question_count` | login_required | _ensure_teacher | tenant_scoped_exams | - |
| 53 | POST | `/exams/<slug:slug>/grant-extra-attempt/` | `exams.views.teacher.exams.attempt_grants.grant_extra_attempt` | login_required | _ensure_teacher | _get_editable_exam_or_404 | - |
| 54 | POST | `/exams/<slug:slug>/grant-extra-attempt-group/` | `exams.views.teacher.exams.attempt_grants.grant_extra_attempt_group` | login_required | _ensure_teacher | _get_editable_exam_or_404, organization=org, organization=organization | - |
| 55 | ANY | `/exams/pending-work/` | `exams.views.teacher.results._attempt_views.teacher_pending_attempts` | login_required | _ensure_teacher | request.user.exams, tenant_scoped_exams | - |
| 56 | POST | `/exams/import/extract-jobs/` | `exams.views.teacher.extract_jobs.start_text_extraction` | login_required | _ensure_teacher | user=request.user | - |
| 57 | GET | `/exams/import/extract-jobs/<uuid:job_id>/` | `exams.views.teacher.extract_jobs.text_extraction_status` | login_required | _ensure_teacher | user=request.user | - |
| 58 | GET | `/exams/question-imports/<str:token>/visual/<int:source_index>.png` | `exams.views.teacher.submission_media.question_import_visual_preview` | login_required | _ensure_teacher | organization_id= | - |
| 59 | GET | `/exams/export-jobs/<uuid:job_id>/waiting/` | `exams.views.teacher.extract_jobs.export_job_waiting` | login_required | _ensure_teacher | user=request.user | - |
| 60 | GET | `/exams/export-jobs/<uuid:job_id>/download/` | `exams.views.teacher.extract_jobs.export_job_download` | login_required | _ensure_teacher | user=request.user | - |
| 61 | ANY | `/exams/question-submissions/new/` | `exams.views.teacher.submission_inbox.question_submission_create` | login_required | _ensure_teacher | organization=org, organization=organization | - |
| 62 | POST | `/exams/question-submissions/ai-generate/` | `exams.views.teacher.submission_inbox.ai_generate_submission_questions` | login_required | _ensure_teacher | - | - |
| 63 | ANY | `/exams/question-submissions/inbox/` | `exams.views.teacher.submission_review.question_submission_inbox` | login_required | - | - | - |
| 64 | ANY | `/exams/question-submissions/<int:submission_id>/` | `exams.views.teacher.submission_inbox.question_submission_detail` | login_required | _ensure_teacher, is_exam_center_user | organization=org, organization=organization | - |
| 65 | POST | `/exams/question-submissions/<int:submission_id>/delete/` | `exams.views.teacher.submission_inbox.question_submission_delete` | login_required | _ensure_teacher | organization=org, organization=organization | - |
| 66 | ANY | `/exams/question-submissions/<int:submission_id>/review/` | `exams.views.teacher.submission_review.question_submission_review` | login_required | _ensure_teacher | organization=org, organization=organization | - |
| 67 | GET | `/exams/question-submissions/<int:submission_id>/questions/` | `exams.views.teacher.submission_review.question_submission_questions` | login_required | is_exam_center_user | organization=org, organization=organization | - |
| 68 | GET | `/exams/question-submissions/<int:submission_id>/visual/<int:source_index>.png` | `exams.views.teacher.submission_media.question_submission_visual_preview` | login_required | _ensure_teacher, is_exam_center_user | organization=org, organization=organization, organization_id= | - |
| 69 | POST | `/exams/question-submissions/<int:submission_id>/decide/` | `exams.views.teacher.submission_review.question_submission_decide` | login_required | _ensure_teacher | organization=org, organization=organization | - |
| 70 | ANY | `/exams/question-submissions/<int:submission_id>/chair-review/` | `exams.views.teacher.submission_chair.question_submission_chair_review` | login_required | - | - | - |
| 71 | POST | `/exams/question-submissions/<int:submission_id>/chair-decide/` | `exams.views.teacher.submission_chair.question_submission_chair_decide` | login_required | - | - | - |
| 72 | ANY | `/exams/question-bank/` | `exams.views.teacher.question_library.crud.question_bank_list` | login_required | _ensure_teacher, ensure_can_create_question_bank, is_exam_center_user | organization=org, organization=organization, user=request.user | - |
| 73 | ANY | `/exams/question-bank/<int:bank_id>/` | `exams.views.teacher.question_library.crud.question_bank_detail` | login_required | _ensure_teacher | user=request.user | - |
| 74 | ANY | `/exams/question-bank/<int:bank_id>/update/` | `exams.views.teacher.question_library.crud.question_bank_update` | login_required | _ensure_teacher, is_exam_center_user | user=request.user | - |
| 75 | ANY | `/exams/question-bank/<int:bank_id>/delete/` | `exams.views.teacher.question_library.crud.question_bank_delete` | login_required | _ensure_teacher | - | - |
| 76 | ANY | `/exams/question-bank/<int:bank_id>/bulk-add/` | `exams.views.teacher.question_library.questions.question_bank_bulk_add` | login_required | _ensure_teacher | organization_id= | - |
| 77 | ANY | `/exams/question-bank/<int:bank_id>/bulk-add/template-download/` | `exams.views.teacher.question_library.export.question_bank_template_download` | login_required | _ensure_teacher | - | - |
| 78 | ANY | `/exams/question-bank/<int:bank_id>/ai-generate/` | `exams.views.teacher.question_library.questions.ai_generate_bank_questions` | login_required | _ensure_teacher | - | - |
| 79 | ANY | `/exams/question-bank/<int:bank_id>/export.docx` | `exams.views.teacher.question_library.export.question_bank_word_export` | login_required | _ensure_teacher | - | - |
| 80 | ANY | `/exams/question-bank/<int:bank_id>/questions/add/` | `exams.views.teacher.question_library.questions.bank_question_add` | login_required | _ensure_teacher | - | - |
| 81 | ANY | `/exams/question-bank/<int:bank_id>/questions/<int:question_id>/edit/` | `exams.views.teacher.question_library.questions.bank_question_edit` | login_required | _ensure_teacher | - | - |
| 82 | ANY | `/exams/groups/` | `exams.views.teacher.groups.teacher_group_list` | login_required | - | - | - |
| 83 | ANY | `/exams/groups/create/form/` | `exams.views.teacher.groups.create_student_group` | login_required | - | - | - |
| 84 | POST | `/exams/groups/create/` | `exams.views.teacher.groups.teacher_create_group` | login_required | - | organization=org, organization=organization, user=request.user | - |
| 85 | ANY | `/exams/groups/namizedler/` | `exams.views.teacher.groups.teacher_group_candidates` | login_required | - | - | - |
| 86 | POST | `/exams/groups/<int:group_id>/update/` | `exams.views.teacher.groups.teacher_update_group` | login_required | - | organization=org, organization=organization, user=request.user | - |
| 87 | POST | `/exams/groups/<int:group_id>/delete/` | `exams.views.teacher.groups.teacher_delete_group` | login_required | - | organization=org, organization=organization, user=request.user | - |
| 88 | POST | `/exams/groups/<int:group_id>/students/<int:student_id>/remove/` | `exams.views.teacher.groups.teacher_remove_student_from_group` | login_required | - | organization=org, organization=organization, user=request.user | - |
| 89 | POST | `/exams/groups/<int:group_id>/students/<int:student_id>/add/` | `exams.views.teacher.groups.teacher_add_student_to_group` | login_required | - | organization=org, organization=organization, user=request.user | - |
| 90 | ANY | `/exams/<slug:slug>/attempt/<int:attempt_id>/check/` | `exams.views.teacher.results._attempt_views.teacher_check_attempt` | login_required | _ensure_teacher, request_has_permission | get_teacher_exam_or_404 | - |
| 91 | POST | `/exams/<slug:slug>/attempt/<int:attempt_id>/ai-grade/` | `exams.views.teacher.results._attempt_views.ai_grade_answer` | login_required | _ensure_teacher | get_teacher_exam_or_404 | - |
| 92 | ANY | `/exams/<slug:slug>/attempt/<int:attempt_id>/view/` | `exams.views.teacher.results._attempt_views.teacher_view_attempt` | login_required | _ensure_can_view_attempt_results | get_result_viewable_exam_or_404 | - |
| 93 | ANY | `/exams/<slug:slug>/start/` | `exams.views.student.attempts.start_exam` | login_required | - | tenant_scoped_exams | - |
| 94 | ANY | `/exams/<slug:slug>/attempt/<int:attempt_id>/result/` | `exams.views.student.results.exam_result` | login_required | - | student=request.user, tenant_scoped_exams, user=request.user | - |
| 95 | POST | `/exams/<slug:slug>/attempt/<int:attempt_id>/coding/autosave/` | `exams.views.student.coding.coding_autosave` | login_required | - | - | - |
| 96 | POST | `/exams/<slug:slug>/attempt/<int:attempt_id>/coding/run/` | `exams.views.student.coding.coding_run` | login_required | - | - | - |
| 97 | POST | `/exams/<slug:slug>/attempt/<int:attempt_id>/coding/submit/` | `exams.views.student.coding.coding_submit` | login_required | ensure_active_attempt_access | - | - |
| 98 | GET | `/exams/<slug:slug>/attempt/<int:attempt_id>/coding/submissions/<int:submission_id>/download/` | `exams.views.student.coding.coding_submission_download` | login_required | - | - | - |
| 99 | ANY | `/exams/<slug:slug>/attempt/<int:attempt_id>/` | `exams.views.student.attempts.take_exam` | login_required | ensure_active_attempt_access | tenant_scoped_exams, user=request.user | - |
| 100 | POST | `/exams/<slug:slug>/attempt/<int:attempt_id>/question-seen/` | `exams.views.student.question_timer.question_seen` | login_required | ensure_active_attempt_access | tenant_scoped_exams, user=request.user | - |
| 101 | POST | `/exams/<slug:slug>/question-bank/ai-generate/` | `exams.views.teacher.question_bank._views_create.ai_generate_question_bank` | login_required | _ensure_teacher, ensure_can_manage_exam_questions | get_teacher_exam_or_404 | - |
| 102 | ANY | `/exams/<slug:slug>/test-bank/` | `exams.views.teacher.question_bank._views_misc.test_question_bank` | login_required | _ensure_teacher, ensure_can_manage_exam_questions | get_teacher_exam_or_404, organization_id= | - |
| 103 | ANY | `/exams/<slug:slug>/questions/export.docx` | `exams.views.teacher.question_bank._views_misc.exam_questions_word_export` | login_required | _ensure_teacher | get_teacher_exam_or_404 | - |
| 104 | ANY | `/exams/<slug:slug>/test-bank/template-download/` | `exams.views.teacher.question_bank._views_misc.test_question_bank_template_download` | login_required | _ensure_teacher | get_teacher_exam_or_404 | - |
| 105 | ANY | `/exams/<slug:slug>/create-bank/` | `exams.views.teacher.question_bank._views_create.create_question_bank` | login_required | _ensure_teacher, ensure_can_manage_exam_questions | get_teacher_exam_or_404 | - |
| 106 | ANY | `/exams/<slug:slug>/process-bank/` | `exams.views.teacher.question_bank._views_create.process_question_bank` | login_required | _ensure_teacher, ensure_can_manage_exam_questions | get_teacher_exam_or_404 | - |
| 107 | ANY | `/exams/<slug:slug>/add-question/` | `exams.views.teacher.questions.crud.add_exam_question` | login_required | _ensure_teacher, ensure_can_manage_exam_questions | get_teacher_exam_or_404 | - |
| 108 | GET,POST | `/exams/<slug:slug>/questions-bank/` | `exams.views.teacher.questions.bank.teacher_questions_bank` | login_required | _ensure_teacher, ensure_can_manage_exam_questions | get_teacher_exam_or_404 | - |
| 109 | ANY | `/exams/<slug:slug>/questions/<int:question_id>/edit/` | `exams.views.teacher.questions.crud.edit_exam_question` | login_required | _ensure_teacher, ensure_can_manage_exam_questions | get_teacher_exam_or_404 | - |
| 110 | ANY | `/exams/<slug:slug>/questions/<int:question_id>/delete/` | `exams.views.teacher.questions.crud.delete_exam_question` | login_required | _ensure_teacher, ensure_can_manage_exam_questions | get_teacher_exam_or_404 | - |
| 111 | GET | `/exams/<slug:slug>/questions/page/` | `exams.views.teacher.exams.list_detail.teacher_exam_detail_questions_page` | login_required | _ensure_teacher | get_teacher_exam_or_404 | - |
| 112 | ANY | `/exams/<slug:slug>/results/` | `exams.views.teacher.results._results_views.teacher_exam_results` | login_required | _ensure_teacher, request_has_permission | get_teacher_exam_or_404 | - |
| 113 | ANY | `/exams/<slug:slug>/statistics/` | `exams.views.teacher.statistics.teacher_exam_statistics` | login_required | _ensure_teacher | get_teacher_exam_or_404, organization=org | - |
| 114 | ANY | `/exams/<slug:slug>/languages/` | `exams.views.teacher.languages.exam_language_manager` | login_required | _ensure_teacher, ensure_can_manage_exam_questions | get_teacher_exam_or_404, organization_id= | - |
| 115 | ANY | `/exams/<slug:slug>/bank-picker/` | `exams.views.teacher.question_library.picker.exam_bank_picker` | login_required | _ensure_teacher, ensure_can_manage_exam_questions | get_teacher_exam_or_404 | - |
| 116 | POST | `/exams/<slug:slug>/results/delete-attempts/` | `exams.views.teacher.results._attempt_views.delete_exam_attempts` | login_required | _ensure_teacher, request_has_permission | get_teacher_exam_or_404 | - |
| 117 | ANY | `/exams/<slug:slug>/results/export.xlsx` | `exams.views.teacher.results._results_views.export_exam_results_xlsx` | login_required | _ensure_teacher | get_teacher_exam_or_404 | - |
| 118 | ANY | `/exams/<slug:slug>/toggle-active/` | `exams.views.teacher.exams.actions.toggle_exam_active` | login_required | _ensure_exam_permission, _ensure_teacher | get_teacher_exam_or_404, user=request.user | - |
| 119 | POST | `/exams/<slug:slug>/toggle-results-visibility/` | `exams.views.teacher.exams.actions.toggle_exam_results_visibility` | login_required | _ensure_exam_permission, _ensure_teacher | get_teacher_exam_or_404, user=request.user | - |
| 120 | ANY | `/exams/<slug:slug>/edit/` | `exams.views.teacher.exams.list_detail.createAndEditExamView` | login_required | _ensure_exam_permission, _ensure_teacher, is_superadmin_user | _get_editable_exam_or_404, organization=org, organization=organization, user=request.user | - |
| 121 | ANY | `/exams/<slug:slug>/delete/` | `exams.views.teacher.exams.actions.delete_exam` | login_required | _ensure_exam_permission, _ensure_teacher | _get_editable_exam_or_404, user=request.user | - |
| 122 | ANY | `/exams/deleted/` | `exams.views.teacher.exams.actions.deleted_exams_list` | login_required | _ensure_teacher | author=request.user, tenant_scoped_exams | - |
| 123 | POST | `/exams/<slug:slug>/restore/` | `exams.views.teacher.exams.actions.restore_exam` | login_required | _ensure_exam_permission, _ensure_teacher | _get_deleted_exam_or_404, user=request.user | - |
| 124 | POST | `/exams/<slug:slug>/permanent-delete/` | `exams.views.teacher.exams.actions.permanent_delete_exam` | login_required | _ensure_exam_permission, _ensure_teacher | _get_deleted_exam_or_404 | - |
| 125 | POST | `/exams/<slug:slug>/archive/` | `exams.views.teacher.exams.actions.toggle_exam_archive` | login_required | _ensure_exam_permission, _ensure_teacher | _get_editable_exam_or_404, user=request.user | - |
| 126 | POST | `/exams/<slug:slug>/duplicate/` | `exams.views.teacher.exams.actions.duplicate_exam` | login_required | _ensure_exam_permission, _ensure_teacher | _get_editable_exam_or_404, user=request.user | - |
| 127 | POST | `/exams/supervision/api/log/<int:attempt_id>/` | `exams.views.teacher.supervision.monitor.log_incident_api` | login_required | - | user=request.user | - |
| 128 | GET | `/exams/supervision/api/status/<int:attempt_id>/` | `exams.views.teacher.supervision.monitor.supervision_status_api` | login_required | - | user=request.user | - |
| 129 | ANY | `/exams/<slug:slug>/` | `exams.views.teacher.exams.list_detail.teacher_exam_detail` | login_required | _ensure_teacher | get_teacher_exam_or_404, user=request.user | - |

Auth token-siz view-lar (exams): yoxdur
Tenant token-siz view-lar (exams): `exam_center_room_monitor`, `exam_center_room_snapshot`, `exam_center_attempt_violations`, `exam_center_room_start_all`, `exam_center_room_end_all`, `exam_center_room_open_all`, `teacher_exam_list`, `bank_teacher_search`, `assigned_student_count`, `ai_generate_submission_questions`, `question_submission_inbox`, `question_submission_chair_review`, `question_submission_chair_decide`, `question_bank_delete`, `question_bank_template_download`, `ai_generate_bank_questions`, `question_bank_word_export`, `bank_question_add`, `bank_question_edit`, `teacher_group_list`, `create_student_group`, `teacher_group_candidates`, `coding_autosave`, `coding_run`, `coding_submit`, `coding_submission_download`

### appeals (9 endpoint)

| # | METHOD | PATH | view | auth | rol/obyekt guard | tenant guard | qeyd |
|---|---|---|---|---|---|---|---|
| 1 | ANY | `/appeals/my/` | `appeals.views.student.endpoints.my_appeals` | login_required | - | - | - |
| 2 | ANY | `/appeals/create/<int:attempt_id>/` | `appeals.views.student.endpoints.appeal_create` | login_required | can_create_appeal | student=request.user, tenant_scoped_exams, user=request.user | - |
| 3 | ANY | `/appeals/manage/` | `appeals.views.teacher.endpoints.manage_appeals` | login_required | _can_open_appeal_management | - | - |
| 4 | ANY | `/appeals/manage/<int:appeal_id>/` | `appeals.views.teacher.endpoints.review_appeal` | login_required | can_review_appeal | - | - |
| 5 | GET | `/appeals/stats/data/` | `appeals.views.teacher.statistics.appeal_stats_data` | login_required | - | _stats_org | - |
| 6 | GET | `/appeals/stats/charts/` | `appeals.views.teacher.statistics.appeal_stats_charts` | login_required | - | _stats_org | - |
| 7 | GET | `/appeals/stats/filters/` | `appeals.views.teacher.statistics.appeal_stats_filters` | login_required | - | _stats_org, organization=org, organization=organization | - |
| 8 | GET | `/appeals/stats/ai/` | `appeals.views.teacher.statistics.appeal_stats_ai` | login_required | - | _stats_org | - |
| 9 | ANY | `/appeals/<int:appeal_id>/` | `appeals.views.shared.detail.appeal_detail` | login_required | can_review_appeal | - | - |

Auth token-siz view-lar (appeals): yoxdur
Tenant token-siz view-lar (appeals): `my_appeals`, `manage_appeals`, `review_appeal`, `appeal_detail`

### live_exam (26 endpoint)

| # | METHOD | PATH | view | auth | rol/obyekt guard | tenant guard | qeyd |
|---|---|---|---|---|---|---|---|
| 1 | ANY | `/exams/live/create/<slug:slug>/` | `live_exam.views.host.session.live_create_session_by_slug` | login_required | _ensure_host_org_permission | _ensure_host_org_permission, user=request.user | - |
| 2 | ANY | `/exams/live/` | `live_exam.views.player.join.live_pin_entry` | - | - | - | - |
| 3 | ANY | `/exams/live/host/<str:pin>/` | `live_exam.views.host.session.live_host_lobby` | login_required | _ensure_host_org_permission | _ensure_host_org_permission | - |
| 4 | ANY | `/exams/live/host/<str:pin>/presentation/` | `live_exam.views.host.session.live_host_presentation` | login_required | _ensure_host_org_permission | _ensure_host_org_permission | - |
| 5 | POST | `/exams/live/host/<str:pin>/start/` | `live_exam.views.host.game.host_start_game` | login_required | _ensure_host_org_permission | _ensure_host_org_permission, user=request.user | - |
| 6 | POST | `/exams/live/host/<str:pin>/next/` | `live_exam.views.host.game.host_next_question` | login_required | _ensure_host_org_permission | _ensure_host_org_permission | - |
| 7 | POST | `/exams/live/host/<str:pin>/skip-intro/` | `live_exam.views.host.game.host_skip_question_intro` | login_required | _ensure_host_org_permission | _ensure_host_org_permission | - |
| 8 | POST | `/exams/live/host/<str:pin>/reveal/` | `live_exam.views.host.game.host_reveal` | login_required | _ensure_host_org_permission | _ensure_host_org_permission | - |
| 9 | POST | `/exams/live/host/<str:pin>/finish/` | `live_exam.views.host.game.host_finish` | login_required | _ensure_host_org_permission | _ensure_host_org_permission, user=request.user | - |
| 10 | POST | `/exams/live/host/<str:pin>/lock/` | `live_exam.views.host.game.host_toggle_lock` | login_required | _ensure_host_org_permission | _ensure_host_org_permission | - |
| 11 | POST | `/exams/live/host/<str:pin>/settings/` | `live_exam.views.host.game.host_update_settings` | login_required | _ensure_host_org_permission | _ensure_host_org_permission | - |
| 12 | POST | `/exams/live/host/<str:pin>/players/remove/` | `live_exam.views.host.game.host_remove_player` | login_required | _ensure_host_org_permission | _ensure_host_org_permission | - |
| 13 | ANY | `/exams/live/results/<slug:slug>/` | `live_exam.views.results.teacher_live_exam_results` | login_required | _ensure_teacher | - | - |
| 14 | ANY | `/exams/live/results/<slug:slug>/<str:pin>/` | `live_exam.views.results.teacher_live_session_detail` | login_required | _ensure_teacher | - | - |
| 15 | ANY | `/exams/live/join/<str:pin>/` | `live_exam.views.player.join.live_join_page` | - | - | get_request_player | - |
| 16 | POST | `/exams/live/join/<str:pin>/enter/` | `live_exam.views.player.join.live_join_enter` | - | - | bypass_rls | bypass_rls |
| 17 | ANY | `/exams/live/play/<str:pin>/` | `live_exam.views.player.wait.live_player_screen` | - | - | bypass_rls, get_request_player | bypass_rls |
| 18 | POST | `/exams/live/play/<str:pin>/answer/` | `live_exam.views.api.live_answer_submit` | - | - | bypass_rls, get_request_player | bypass_rls |
| 19 | ANY | `/exams/live/wait/<str:pin>/` | `live_exam.views.player.wait.live_wait_room` | - | - | bypass_rls, get_request_player | bypass_rls |
| 20 | POST | `/exams/live/wait/<str:pin>/profile/` | `live_exam.views.player.wait.live_wait_profile_update` | - | - | bypass_rls, get_request_player | bypass_rls |
| 21 | POST | `/exams/live/wait/<str:pin>/reaction/` | `live_exam.views.player.wait.live_wait_reaction` | - | - | bypass_rls, get_request_player | bypass_rls |
| 22 | ANY | `/exams/live/qr/<str:pin>.png` | `live_exam.views.player.join.live_qr_png` | - | - | bypass_rls | bypass_rls |
| 23 | ANY | `/exams/live/state/<str:pin>/` | `live_exam.views.api.live_state_json` | - | - | bypass_rls, get_request_player | bypass_rls |
| 24 | POST | `/exams/live/<str:pin>/start/` | `live_exam.views.host.game.host_start_game` | login_required | _ensure_host_org_permission | _ensure_host_org_permission, user=request.user | - |
| 25 | POST | `/exams/live/<str:pin>/next/` | `live_exam.views.host.game.host_next_question` | login_required | _ensure_host_org_permission | _ensure_host_org_permission | - |
| 26 | POST | `/exams/live/<str:pin>/finish/` | `live_exam.views.host.game.host_finish` | login_required | _ensure_host_org_permission | _ensure_host_org_permission, user=request.user | - |

Auth token-siz view-lar (live_exam): `pin_entry`, `join_page`, `join_enter`, `player_screen`, `answer_submit`, `wait_room`, `wait_room_profile`, `wait_room_reaction`, `qr_png`, `state_json`
Tenant token-siz view-lar (live_exam): `pin_entry`, `teacher_live_results`, `teacher_live_session_detail`

</details>

## 3. Yoxlamalar — detallı sübut

### 3.1 Lifecycle — PARTIAL
- Publish qapısı (sualsız / dil-parity pozulmuş / silinmiş imtahan dərc olunmur) — `lifecycle.py:26-36`; create/edit forması `is_active`-i dəyişə bilmir (`forms/exam.py:296-303`). PASS (kod).
- `start_exam` `is_active`/`is_deleted`/vaxt pəncərəsi/exclusion/limit/parity/kod → `can_user_start` (`domain/access_policy.py:247-329`); aktiv sual yoxdursa rədd (`views/student/attempts.py:290`); jurnal qayıb-limit qapısı (`registrar_block_reason`). PASS.
- Bilet yolu start siyasətini keçir — **EX-04** (repro PASS/XFAIL).
- Silinmiş imtahanla cəhdlər: soft-delete, nəticələr qorunur; `include_deleted=True` müəllim nəticə view-larında. PASS.
- `draft` status DB-də «açıq» sayılmır — **EX-08**.
- Browser (dev-clone :8011): klon bazasında `exams_exam`=1 sətir (RLS altında 0 görünür), `exams_examattempt`=0 — wizard→start→submit axını brauzerdə **NOT TESTED** (məlumat yoxdur; HTTP-səviyyəli sandbox testləri eyni yolları əhatə edir). `/exams/final/` səhifəsi açıldı, konsol xətası yoxdur (screenshot).

### 3.2 PIN / giriş — FAIL
- `/exams/final/` (`views/student/final_center.py:212-256`): zal IP/CIDR qapısı (`_ensure_hall_access` → `final_exam_access_allowed`, `exam_center_gate.py:92-121`) PASS (`test_final_entry_page_is_gated_by_hall_ip`); IP+username limiter (`entry.py:61-79`); generik xəta mesajı + `equalize_verification_timing` → enumeration PASS (yalnız `ERROR_LOCKED` kilidli biletin varlığını açır — P3 qeyd); PIN kilidi `FINAL_EXAM_PIN_MAX_FAILURES`. Fərdi-PIN yolu IP limiterini yan keçir — **EX-06**.
- PIN tələbəyə + imtahana bağlıdır (`uniq_exam_student_pin`, `verify_student_pin(exam, user, code)`); reuse: bilet PIN-i birdəfəlik (`revoke_ticket_pin`), fərdi PIN imtahan bitənə +120 dəq qədər çox-istifadəli (dizayn: kompüter dəyişməsi). Expiry PASS (`is_usable`).
- Aktivasiya-öncəsi sızma: `can_user_start` `is_before_start` rədd edir; PIN dərhal görünür (dizayn). PASS.
- **`/exams/code-check/`**: final imtahanı zal/bilet olmadan başladır — **EX-02**; rate-limit yoxdur — **EX-03**. `final_attempt_entry_session_valid` (`entry.py:294-306`) biletsiz cəhd üçün `True` qaytarır (geriyə uyğunluq) → bu yolla yaranan cəhd `take_exam`-də də keçir.
- PIN girişi tam Django sessiyası verir (`test_pin_only_login_yields_full_platform_session` PASS: kabinet + tələbə imtahan siyahısı 200) — zal kompüterində tələbənin bütün kabineti açıqdır (P3 qeyd; final nəticə səhifəsi timeout-la `logout` edir).

### 3.3 Taymer / submit — PARTIAL
- Server authority: `deadline_at` (`domain/attempts.py:239-245`), lazy expiry GET/POST-da (`take_exam:480`), lock altında yenidən yoxlama (`_handle_take_exam_post:324-326`), periodik `sweep_overdue_attempts`. Client vaxtı yalnız göstəriş üçündür. PASS.
- Deadline anındakı «finish» POST-u atılır — **EX-05**.
- Duplicate submit: `is_finished` → `_finished_attempt_response` (`already_finished: True`) idempotent. PASS.
- Autosave/finish yarışı: `select_for_update` + OCC (`autosave_occ_conflict_response`, stale tab → 409) PASS; kilid valideyn `exams_exam` sətrini də tutur — **EX-09**.
- Çox-tab/refresh: GET aktiv cəhdə qayıdır; `autosave_revision` ilə köhnə tab 409. PASS (kod + `test_repro_exams_audit` OCC yolu dolayı).
- Rədd edilən fayl yükləməsi əvvəlki faylları silir — **EX-07**.

### 3.4 Məxfilik — FAIL (EX-01)
- `take_exam` HTML-də `is_correct/correct_answer/data-correct/"correct":` markerləri yoxdur (`TakeExamPageDoesNotLeakAnswerKeyTests` PASS); strict delivery JSON `safe_delivered_question` `is_correct`-i qəsdən çıxarır (`services/question_delivery.py:29-58`); randomizer snapshot-u `is_correct` saxlayır amma yalnız server tərəfində (`randomizer.py:392-397`). PASS.
- Nəticə səhifəsi `in_progress` cəhd üçün açıqdır — **EX-01 (P0)**.
- Müəllim sınaq cəhdi (`is_trial`) yalnız müəllifə; müəllimin cavab açarı `teacher` view-larında author-scoped. PASS.

### 3.5 Paralellik — PARTIAL
- Eyni-anlı start: `_exam_start_actor_lock` (cache) + `uniq_active_attempt_per_user_exam` + `uniq_attempt_number_per_user_exam` + `IntegrityError` → mövcud cəhdə qayıt (`attempts.py:261-303`). Sandbox loglarında cache `incr` xətası «capacity counter failed; bypassing the gate» — locmem-də kapasite qapısı işləmir, DB constraint qoruyur. PASS (in_progress), FAIL draft üçün (EX-08).
- `max_attempts` yarışı: `attempts_left_for` kilidsiz sayılır; iki paralel start eyni anda bir açıq cəhd yarada bilər (constraint), sonra ikincisi resume olur — artıq cəhd yaranmır. PASS.
- İkiqat qiymətləndirmə: `apply_manual_grading` attempt+answers `select_for_update`, ledger `ExamGradeEvent`. PASS.

### 3.6 Tenant / rol — PARTIAL (bax §2)
- 09-02 P0-2 (bulk delete) düzəlişi yerindədir (`_can_mutate_bank`), amma eyni sinif `bank_question_add/edit/bulk_add/ai_generate` üçün tətbiq olunmayıb — **EX-10** (yeni sandbox repro `test_repro_bank_question_edit_foreign.py`: 4/4 PASS = tapıntı təsdiqlənir).
- 09-02 P2-1 (`supervisor_org_or_403` tələbəyə açıq) — düzəlib: `ensure_can_enter_supervision_surface` (`_shared.py:29-44`). PASS (kod).
- Müəllim yalnız öz imtahanlarını redaktə/nəticə görür (`get_teacher_exam_or_404` author-scoped, `tenant.py:52-57`); mərkəz org-daxili oxu (`get_result_viewable_exam_or_404`). PASS.

### 3.7 Audit log — PASS
`log_action` çağırışları: publish/unpublish/results-hidden (`lifecycle.py`), create/update (`list_detail.py:206-215`), soft-delete/archive/duplicate/restore (`actions.py:147,222,277,347`), ikinci şans qrantı (`second_chance.py:136`), oturum open/start/end/cancel (`sessions.py:_audit_session`), bilet təyinatı (`tickets.py:120`), nəzarətçi təyinatı (`room_monitor.py:212`), PIN lookup (`pin_lookup.py:210-214`), giriş doğrulaması (`entry.py`), qiymət ledger-i (`ExamGradeEvent`), supervision hadisələri (`SupervisionIncident`). Boşluq: `reissue_student_pin/revoke_student_pin` yalnız second-chance kontekstində loglanır (P3).

### 3.8 Performans — PARTIAL
Sandbox (`query_budget.json`, `pytest_run1.log`), 5 sual vs 25 sual, hər sual 3-4 variant:

| Yol | 5q | 25q | Qiymət |
|---|---|---|---|
| `start_exam` GET (cəhd + randomizer) | 43 / 51 | 43 / 48 | sabit (±3 səs-küy) — PASS |
| `take_exam` GET (ilk / təkrar) | 32 / 28 | 28 / 28 | sabit — PASS |
| autosave (1 sual) | 27 | 27 | sabit — PASS (27 hələ də çoxdur: tenant/perm + lock + revision) |
| `question_seen` | 25 | 25 | sabit |
| finish (cavabsız) | 47 | 67 | +1/sual |
| finish (bütün cavablar POST-da) | 52 | 112 | **+3/sual → EX-11 (P3)** |
| `exam_result` | 33 | 33 | sabit — PASS |

Klon (:55433, `BEGIN…ROLLBACK`, `clone_explain.txt`): `exams_examattempt`=0, `exams_examanswer`=0 sətir → həcm-əsaslı EXPLAIN **NOT APPLICABLE**. İndeks örtüyü yoxlanıb: `(user_id, exam_id, status)`, `(user_id, exam_id, started_at DESC)`, partial `uniq_active_attempt_per_user_exam`, `examattempt_active_sweep_idx`, `examanswer(attempt_id, question_id)` — isti sorğular index-scan (plan: `exams_exama_user_id_bf4f2e_idx`). RLS siyasəti `exams_examanswer` üçün sətir-başına korrelyasiyalı subplan (attempt→exam→question→org) — planlama 409 buffer/1,7 ms; böyük cəhd həcmində ölçülməlidir (P3 qeyd, EX-12).

## 4. Tapıntılar (P0–P3) və minimal düzəliş təklifləri

Repro sübutu: `pytest_run1.log` / `pytest_run1_verbose.txt` — 21 PASS (sübut testləri), 4 XFAIL (istənilən davranış hələ yoxdur), 2 FAIL (perf sənəd-assertləri, aşağıda).

### EX-01 · P0 · Bitməmiş (in_progress) cəhdin nəticə səhifəsi düzgün cavabları göstərir
- Kod: `apps/exams/views/student/results.py:134-169` (`exam_result`) — `attempt` yalnız `id/exam/user` ilə götürülür, `status` yoxlanmır; `views/student/_helpers.py:53-81` (`annotate_attempt_result_visibility`) test imtahanı üçün `can_view_result=True` verir; şablon `templates/exams/student/exam_result.html:306-311` `opt.is_correct` → `correct-option` çap edir. `_hide_test_answer_correctness_in_cabinet` (`results.py:57`) yalnız `return_to=profile` + final/midterm halında gizlədir — birbaşa URL ilə final üçün də açıqdır.
- Repro: `test_repro_result_in_progress_leak.py::test_result_page_of_in_progress_attempt_reveals_correct_options` **PASS** (status `in_progress` ikən 200 + `correct-option` + «DÜZGÜN-0», sonra `take_exam` yenidən 200 → tələbə cavabları düzəldə bilər).
- Təsir: istənilən test-tipli imtahanda (quiz/kollokvium/final) tələbə ikinci tabda `/exams/<slug>/attempt/<id>/result/` açıb öz sual dəstinin cavab açarını görür. İmtahan bütövlüyü sıfırlanır.
- Düzəliş (minimal): `exam_result` başlanğıcında `attempt.expire_if_time_limit_reached()` çağır və `if not attempt.is_finished: return redirect(take_exam)` (və ya 404). Eyni yoxlama `_resolve_result_navigation`-dan asılı olmayaraq tətbiq olunmalıdır. Regresiya testi: yuxarıdakı repro-nu `assertNotIn("correct-option")` ilə çevir.

### EX-02 · P1 · `/exams/code-check/` (və `start_exam`+PIN) final imtahanı zal/bilet/nəzarətçi qapısından KƏNARDA başladır
- Dizayn niyyəti: `apps/accounts/views/_dashboard_helpers/assigned_tasks.py:203-207` — «Final imtahanları HƏMİŞƏ imtahan mərkəzi axını ilə verilir: tələbə kabinetdən imtahana BAŞLAYA BİLMİR … `/exams/final/`»; `/exams/final/` `_ensure_hall_access` (IP/CIDR), gözləmə otağı, nəzarətçi «Başlat» tələb edir (`views/student/final_center.py:221,433,471,489`).
- Kod: `views/shared/access.py:61-110` (`exam_code_check`) → `exam.can_user_start(user, code)` (`domain/access_policy.py:304-313`) final/midterm üçün PIN-i `verify_student_pin` ilə yoxlayır və dərhal `_start_or_resume_attempt` çağırır; zal IP, bilet, oturum, kompüter heç yerdə yoxlanmır. PIN kabinetdə açıq görünür (`student_visible_pin`).
- Repro: `test_repro_code_check_final_bypass.py::test_code_check_with_cabinet_pin_starts_final_outside_hall` **PASS** — `FINAL_EXAM_ALLOWED_IPS=10.10.10.0/24` ikən 127.0.0.1-dən POST → 302 `/attempt/`, `ExamAttempt` yaranır (`room_id=None`, `room_computer_id=None`), `FinalExamTicket` yoxdur, `take_exam` 200. Nəzarət: `/exams/final/` eyni şəraitdə 403 (`test_final_entry_page_is_gated_by_hall_ip` PASS).
- Düzəliş: `exam_code_check` və `start_exam`-da `exam.exam_type_extended == "final"` olduqda rədd et (yalnız `/exams/final/` axını; `is_trial` müəllif istisnası qala bilər). Alternativ: `can_user_start`-ın final qolunda `require_center_flow` bayrağı ilə `code` yolunu bağla.

### EX-03 · P1 · `/exams/code-check/`-də PIN/kod brute-force məhdudiyyəti yoxdur
- Kod: `views/shared/access.py:61` — heç bir rate-limit/lockout; `verify_student_pin` (`services/student_pins.py:134-152`) hər çağırışda `check_password` (PBKDF2) icra edir. `student_pin_login_rate_limited` (`student_pins.py:34-57`) YALNIZ `/exams/final/` yolunda çağırılır. `FINAL_EXAM_PIN_MAX_FAILURES`/`LOCK_MINUTES` (`config/settings/components/exam.py:101-102`) bu yolda tətbiq olunmur.
- Repro: `test_repro_code_check_final_bypass.py::test_code_check_has_no_rate_limit` **PASS** — 30 ardıcıl səhv PIN → hamısı 400, heç bir 429/kilid. 8 rəqəmli PIN (`FINAL_EXAM_PIN_LENGTH=8`) → 10^8 fəza; authenticated tələbə üçün brute-force + hash-CPU DoS.
- Düzəliş: `exam_code_check`-də (və `start_exam` `code` ilə) `student_pin_login_rate_limited(request.user.username)` + exam-id üzrə ikinci açar; limit aşımında 429.

### EX-04 · P2 · Bilet yolu `begin_attempt_for_ticket` `can_user_start` siyasətini keçir (bitmiş/deaktiv imtahana cəhd yaradır)
- Repro: `test_repro_exams_audit.py::TicketBeginBypassesStartPolicyTests` — `end_datetime` 1 saat əvvəl keçmiş final üçün `begin_attempt_for_ticket(ticket)` `in_progress` attempt yaradır (`test_current_behaviour_attempt_is_created_for_ended_exam` PASS; istənilən davranış XFAIL).
- Kod: `services/final_center/tickets.py:270-327` (`begin_attempt_for_ticket`) — yalnız oturum `ACTIVE` + bilet `WAITING/READY` yoxlanır (:279-293); cəhd `_create_attempt_or_get_active` ilə birbaşa yaradılır (:296); `exam.is_active`, `start/end_datetime`, `attempts_left_for` çağırılmır (şərh :321-323 «cəhd limiti YENİ cəhdi bloklayır» deyir, amma bu yolda limit yoxlanmır). Nəzarətçi start-ı tələb olunduğu üçün P2.
- Düzəliş: `begin_attempt_for_ticket` içində `can_start, reason = ticket.exam.can_user_start(ticket.student, code=None)`-un vaxt/aktivlik/limit hissəsini yoxla (PIN qolunu ötürərək — məs. `skip_code=True` parametri) və `TicketStateError(reason)` at.

### EX-05 · P2 · İmtahan müddəti bitəndə client-in avtomatik «finish» POST-u atılır — son cavablar itir
- Kod: `views/student/attempts.py:480-485` — `take_exam` POST-u emal etməzdən əvvəl `expire_if_time_limit_reached()` → `_finished_attempt_response` (gövdə oxunmur). `_handle_take_exam_post:324-326`-dakı `is_time_up` «saxla-və-bitir» qolu bu yolla praktiki əlçatmazdır. Client: `static/exams/js/take_exam/timers.js:235-241` taymer 0 → 1,5 s sonra `finish` göndərir. Grace pəncərəsi yoxdur.
- Repro: `test_repro_deadline_autosubmit_dropped.py` **PASS** — deadline +2 s POST → `already_finished`, seçim saxlanmayıb, `correct_count=0`.
- Yumşaldıcı: test cavabları 1 s, yazılı 3 s debounce ilə avtosaxlanır (`draft.js:515-533`) — itki pəncərəsi kiçikdir, amma son cavab/yazılı mətn itə bilər (final zalında 3 s interval).
- Düzəliş: `take_exam`-da POST üçün expiry-ni `_handle_take_exam_post`-a buraxmaq (GET-də saxlamaq) — orada lock altında `is_time_up` hesablanıb cavablar saxlanılır və status `expired` olur; və ya `EXAM_SUBMIT_GRACE_SECONDS` (məs. 10 s) ilə `expire_if_time_limit_reached(at_time=now-grace)`.

### EX-06 · P2 · `/exams/final/` fərdi-PIN yolu IP rate-limiterini yan keçir
- Kod: `views/student/final_center.py:245-256` — `validate_entry` (`services/final_center/entry.py:110-123`, IP+user limiter) `rate_limited` qaytaranda `ticket=None` → `_handle_student_pin_login` çağırılır, orada yalnız per-username limiter (`student_pins.py:34`).
- Repro: `StudentPinPathIgnoresIpLimiterTests::test_current_behaviour_ip_limiter_is_bypassed_by_student_pin_path` PASS (IP limiteri dolu ikən 302 + attempt).
- Düzəliş: `_handle_login`-da `error_code == ERROR_RATE_LIMITED` olduqda fərdi-PIN yoluna düşmə.

### EX-07 · P2 · Rədd edilən fayl yükləməsi yazılı cavabın əvvəlki fayllarını silir
- Repro: `RejectedUploadKeepsPreviousFilesTests` — `.exe` yükləməsi 400 alır, amma `ExamAnswerFile` 1 → 0. Kod: `views/student/attempts.py:135-162` (`_save_written_answer_if_changed`) — :154 `answer.files.all().delete()` sonra :156 `validate_uploaded_file`; `ValidationError` atomic blok içində tutulur → COMMIT.
- Düzəliş: əvvəl validasiya, sonra silmə; və ya `ValidationError`-u `transaction.atomic()` xaricində tut (`set_rollback(True)`).

### EX-08 · P2 · `draft` statusu unikal-məhdudiyyətdən kənardadır
- Kod: `domain/attempts.py:220-224` `uniq_active_attempt_per_user_exam` yalnız `status="in_progress"`; tələbə `save_draft` ilə cəhdi `draft`-a salır (`attempts.py:432-434`) → DB ikinci açıq cəhdi bloklamır (`DraftStatusUniqueConstraintGapTests` PASS/XFAIL). Tətbiq qatı (`get_active_attempt_for_user`) hər ikisini «açıq» sayır — DB son müdafiə xətti draft üçün işləmir.
- Düzəliş: constraint şərtini `status__in=["draft","in_progress"]` et (migrasiya; mövcud dublikatlar üçün əvvəl data yoxlaması).

### EX-09 · P2 · Autosave/finish `select_for_update()` valideyn `exams_exam` sətrini də kilidləyir
- Kod: `views/student/attempts.py:309` `ExamAttempt.objects.select_for_update().select_related("exam")` → SQL `... INNER JOIN "exams_exam" ... FOR UPDATE` (`OF` yoxdur) — `query_budget.json:F01_autosave_lock_sql`. `AutosaveLocksParentExamRowTests::test_view_lock_shape_blocks_concurrent_exam_row_writers` PASS: paralel bağlantı imtahan sətrini `NOWAIT` ilə ala bilmir.
- Təsir: bir imtahanın bütün tələbələrinin autosave/finish tranzaksiyaları imtahan sətri üzərində serializasiya olunur; müəllimin publish/unpublish (`lifecycle.py` `select_for_update`) və `results_hidden` keçidləri autosave axını ilə növbəyə düşür. 3 s autosave × N tələbə finalda darboğaz.
- Düzəliş: `select_for_update(of=("self",))` (`test_of_self_lock_shape_does_not_block_exam_row` PASS — bu forma yalnız cəhd sətrini kilidləyir).


### EX-10 · P1 · Sual bankı sualının əlavə/redaktəsi yalnız OXU görünürlüyünə söykənir (09-02 P0-2 düzəlişi natamam)
- Kod: `views/teacher/question_library/questions.py:201-204` (`bank_question_add`), `:247-251` (`bank_question_edit`), `:36` (`question_bank_bulk_add`), `:167` (`ai_generate_bank_questions`) — bank `accessible_banks(user, org)` ilə tapılır (`services/question_bank_attach.py:43-62`: mərkəz → org-un BÜTÜN bankları; müəllim → öz + paylaşılan), `_can_mutate_bank` (`crud.py:227-243`) çağırılmır. Docstring vədi: «Redaktə/silmə yenə yalnız sahibə açıqdır (view qatında)».
- Repro: `test_repro_bank_question_edit_foreign.py` **4/4 PASS** (tapıntı təsdiqlənir): imtahan mərkəzi rəhbəri yad müəllimin PAYLAŞILMAMIŞ bankının sualını dəyişdi (200, mətn «MƏRKƏZ DƏYİŞDİ»); eyni org-un başqa müəllimi paylaşılan bankın sualını dəyişdi və sual əlavə etdi (1→2). Audit sətri yazılmır.
- Təsir: final imtahan bank məzmunu (cavab açarı daxil) sahibdən başqası tərəfindən sessizcə dəyişdirilə bilər.
- Düzəliş: hər dörd view-da `if not _can_mutate_bank(request.user, bank): raise PermissionDenied` (mövcud helper; `question_bank_detail` POST-dakı kimi `deny` audit sətri ilə). Məhsul mərkəzə redaktə vermək istəyirsə — bunu `_can_mutate_bank`-ın özündə açıq qərar kimi yaz.

### EX-11 · P3 · `finish` POST-u sual sayı ilə xətti artan sorğu (N+1)
- `query_budget.json`: finish 5q=52 → 25q=112 (+3/sual: `question.options.all()` + `selected_options.set()` + `answer.save()` hər sual üçün, `views/student/attempts.py:96-133`). 50 sualda ~200 sorğu; bir dəfəlik olduğu üçün P3.
- Düzəliş: `_attempt_answers_queryset`-də `prefetch_related("question__options", "selected_options")` (autosave üçün artıq qismən var) və toplu M2M yazı.

### EX-12 · P3 · `exams_examanswer` RLS siyasəti sətir-başına korrelyasiyalı subplan
- `clone_explain.txt`: policy `EXISTS (attempt JOIN exam JOIN question … organization_id = current_setting)` — hər cavab sətri üçün 3 cədvəlli nested loop; planlama 409 buffer / 1,7 ms. Klonda cəhd yoxdur → real təsir ölçülməyib. Böyük finalda (5 000 cəhd × 50 sual) ölçülməlidir; alternativ: `exams_examanswer`-ə `organization_id` denormalizasiyası (ExamScoreSheet-də olduğu kimi).

### P3 qeydlər (tapıntı kartı açılmayıb)
- `/exams/final/` `ERROR_LOCKED` mesajı kilidli biletin mövcudluğunu açır (`entry.py:155-157`) — generik mesaja bərabərləşdirmək olar.
- PIN girişi tam platform sessiyası verir (`test_pin_only_login_yields_full_platform_session`) — zal kompüterində kabinet açıq qalır; final nəticə timeout-u `logout` edir, amma tələbə imtahan zamanı başqa tab-da kabineti gəzə bilər.
- `reissue_student_pin/revoke_student_pin` müstəqil çağırışda audit yazmır (yalnız `grant_second_chance` konteksti loglanır).
- Sandbox log: locmem cache-də `cache.incr` «Key … not found» → «capacity counter failed; bypassing the gate» — Redis kəsintisində kapasite qapısı səssizcə söndürülür (dizayn: fail-open; qeyd).

## 5. Xülasə və bal

**FINDINGS:** `/private/tmp/claude-501/-Users-elvin-Developer-EMSArena/97340224-f199-4361-9ce5-242af1bb0439/scratchpad/audit/exams/FINDINGS.md`
Artefaktlar: `endpoint_inventory.md`, `query_budget.json`, `clone_explain.txt`, `pytest_run1.log`, `pytest_run1_verbose.txt`, 5 repro test faylı (+ yeni `test_repro_bank_question_edit_foreign.py`).

Sayı: **P0 = 1** (EX-01) · **P1 = 3** (EX-02, EX-03, EX-10) · **P2 = 6** (EX-04–EX-09) · **P3 = 3 + 4 qeyd** (EX-11, EX-12 + qeydlər).

10 sətirlik xülasə:
1. Online imtahan mühərrikinin skeleti möhkəmdir: atomik publish/unpublish qapısı, DB-səviyyəli `in_progress` unikal məhdudiyyəti, server-tərəfli deadline, OCC (409), kilidli qiymətləndirmə + ledger, geniş audit — bunlar sübutla PASS.
2. **P0:** `exam_result` cəhdin bitib-bitmədiyini yoxlamır — tələbə imtahan gedərkən ikinci tabda nəticə URL-ini açıb düzgün variantları görür, sonra cavabları düzəldir (repro PASS, quiz; final üçün kod eyni).
3. **P1:** `/exams/code-check/` kabinetdə görünən PIN ilə FINAL imtahanı zal IP qapısı, bilet, gözləmə otağı və nəzarətçi start-ı olmadan başladır (repro PASS, `FINAL_EXAM_ALLOWED_IPS` dolu ikən 127.0.0.1-dən).
4. **P1:** eyni endpoint-də PIN brute-force limiti yoxdur (30 səhv → 30×400).
5. **P1:** 09-02 P0-2 düzəlişi yalnız bulk-əməliyyatı bağlayıb; `bank_question_add/edit/bulk_add/ai_generate` hələ də oxu görünürlüyü ilə yazır — mərkəz yad paylaşılmamış bankın sualını, müəllim paylaşılan bankın sualını dəyişir (yeni repro 4/4).
6. P2: bilet yolu start siyasətini keçir (bitmiş/deaktiv imtahana cəhd), deadline anındakı avtomatik finish POST-u itir, fərdi-PIN yolu IP limiterini yan keçir, rədd edilən fayl yükləməsi köhnə faylları silir, `draft` DB unikal-məhdudiyyətindən kənardadır, autosave kilidi valideyn `exams_exam` sətrini tutur.
7. Tenant sərhədləri: B təşkilatının tələbəsi A-nın cəhd endpoint-lərinə 404; eyni org-un başqa tələbəsi yad cəhdə 404; müəllim yalnız öz imtahanları; appeals/live_exam/exam-center səthləri org-scoped — PASS.
8. Performans: start/take/autosave/result büdcəsi sual sayından asılı deyil (43/28/27/33); finish +3 sorğu/sual (P3); klonda cəhd məlumatı olmadığından həcm EXPLAIN-i N/A, indeks örtüyü yerindədir.
9. Browser: dev-clone `/exams/final/` səhifəsi konsol-xətasız açılır; tam tələbə axını brauzerdə klon məlumatının olmaması səbəbindən NOT TESTED (HTTP-səviyyəli sandbox testləri ilə əvəz edilib).
10. Codex §13 ilə üst-üstə düşmə yoxdur — Codex yalnız kağız-bal axınını yoxlamışdı; bu hesabat onlayn mühərriki əhatə edir.

**İmtahan sistemi balı: 58 / 100.**
Əsaslandırma: bünövrə (lifecycle, kilidlər, timer, audit, tenant) 80+ səviyyəsindədir, amma cavab açarının imtahan zamanı sızması (P0) və finalın zal nəzarətindən kənarda başladıla bilməsi (P1) universitet final imtahanının bütövlüyünü birbaşa pozur; hər ikisi 5-10 sətirlik düzəlişdir (status yoxlaması; final üçün `code-check` rəddi + rate-limit). Bu üçü + EX-10 bağlanandan sonra təkrar qiymət ~80 gözlənilir.
