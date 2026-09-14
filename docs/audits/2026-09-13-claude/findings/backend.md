# AUDIT — BACKEND · API · ARXİTEKTURA · BİZNES-MƏNTİQ · AUDİT-LOG (slug `backend`)

Tarix: 2026-09-13 (ikinci buraxılış, RESUME). HEAD: `96016cff` (Develop). Auditor: read-only.
Sandbox DB: `ems_audit_backend` (@127.0.0.1:55432). Real DB-yə toxunulmayıb.
Artefaktlar: `probes/api_inventory.tsv` (946 route), `probes/except_inventory.txt` (446 blok),
`probes/dead_code.txt`, `probes/json_200_on_failure.txt`, + bu buraxılışda əlavə olunanlar.

## 0. Xülasə
1. HEAD `96016cff`; 946 route inventarı, 446 except bloku, 23 «ölü» namizəd (hamısı test sinifi) — əvvəlki buraxılışın artefaktları şərh edildi və nümunəvi yoxlandı.
2. Yeni probe dəsti `probes/test_backend_probes.py` (35 test, sandbox `ems_audit_backend`): state-machine 9/9 PASS, malformed-input 20/24 PASS, F-06 repro 1/1; mövcud state-machine dəstləri 228/228 PASS.
3. **P0 yoxdur.** P1 = 1: rol təyinatı audit-loglanmır (F-02).
4. P2 = 7: qeyri-UUID/int pk → 500 (F-01, 4 endpoint-də təkrarlandı), əlavə cəhd hüququ audit-siz (F-03), təşkilat statusu/GPA şkalası audit-siz (F-04), ÜOMG iki düstur (F-05), davamiyyət limiti iki mənbə (F-06, repro), 31 atomic-siz çoxyazılı view (F-07), jurnal körpüsündə səssiz istisna (F-08).
5. P3 = 7: on_commit-siz `.delay` (F-09), 200-on-failure zərfi (F-10), ölü apellyasiya keçid cədvəli (F-11), README↔kod sillabus qapısı (F-12), güzgü qaydalar parity-siz (F-13), qapıya sığdırılmış modullar + console.log (F-14), yazı endpoint-lərində rate-limit yoxdur (F-15).
6. PASS: jurnal kilidi tək mənbə (`journal_is_locked`, 20+ çağıran), müəllim sahibliyi, enrollment/dövr kilidləri, apellyasiya pəncərəsi, siqnallar (m2m `on_commit`), Celery idempotentlik/time-limit, `select_for_update` həmişə atomic çağıranlarda, settings fail-closed (SECRET_KEY/ALLOWED_HOSTS/TLS/2FA), middleware sırası, per-tenant keş açarları.
7. Sahə balı **74/100**; ən zəif: Audit logging 68, Business-logic consistency 70.
8. NOT TESTED: bitmiş cəhdin yenidən açılması (S17), `StudentAcademicRecord.status` keçidləri, `notify_upcoming_final_exams` dublikat qorunması, `correction_views` pk-parse 500-ü (icazə qapısı probe-u dayandırdı).

## 1. Struktur qoxuları (fat views, dublikat servis, ölü kod, TODO)
Mənbə: `probes/api_inventory.tsv` (`lines`, `writes` sütunları), `probes/dead_code.txt`, grep.

| Yoxlama | Nəticə | Sübut |
|---|---|---|
| Fat view (>150 sətir və ya ≥5 yazı) | **PARTIAL** — 22 view >150 sətir; ən böyükləri: `apps/exams/views/teacher/statistics.py:82 teacher_exam_statistics` (400 sətir, 0 yazı), `apps/accounts/views/dashboard/review.py:70 pending_review_detail` (351, 4 yazı, atomic-siz), `apps/exams/views/teacher/results/_results_views.py:47` (324), `apps/exams/views/teacher/question_bank/_views_misc.py:97 test_question_bank` (322, 4 yazı), `apps/exams/views/teacher/questions/bank.py:38` (298), `apps/courses/views/shared/dashboard.py:126` (258), `apps/exams/views/student/results.py:133` (248). ≥5 yazı: `blog/views/moderator/posts.py:129 teacher_moderate_post`, `accounts/views/organization/requests.py:43`, `accounts/views/superadmin/endpoints.py:120` (hamısı atomic-siz — bax §2). | TSV `lines>150` |
| Biznes məntiqi template/JS-də | **PASS (nümunəvi)** — bal/keçid/davamiyyət hesabı yalnız servislərdə (`registrar/finals.py`, `exam_eligibility.py`); JS-də hesab tapılmadı (grep `pass_threshold|absence_limit` static/ → 0). | grep |
| Dublikat qayda (eyni qayda 2+ yerdə) | **PARTIAL** — (a) cəhd limiti 3 implementasiya: `apps/exams/domain/exam_definition.py:330 Exam.attempts_left_for`, `apps/exams/services/attempt_budget.py:26`, `apps/exams/services/student_list_batch.py:243` («güzgü», parity testi yoxdur — `test_student_list_query_budget.py` yalnız sorğu sayını ölçür); (b) yekun nəticə düsturu: `registrar/finals.py:87 compute_final_result` və `registrar/analytics_fast.py:268-300` (sürətli yol, sənədləşdirilmiş güzgü); (c) davamiyyət limiti mənbəyi 2 yol (bax §6 F-06); (d) GPA/ÜOMG 2 düstur (bax §6 F-05); (e) apellyasiya keçid cədvəli `APPEAL_STATUS_TRANSITIONS` + `assert_transition` heç yerdə çağırılmır — faktiki status `recompute_appeal_status` ilə item-lərdən törənir (ölü state-machine). | fayl:sətir yuxarıda |
| God-modul (600 sətir qapısına yaxın) | **PARTIAL (P3)** — 23 modul 590–600 sətir arasında, 7-si düz 600 (`apps/registrar/views.py`, `apps/organizations/models.py`, `apps/exams/views/student/coding.py`, `apps/exams/services/import_media.py`, `apps/accounts/academic_records.py`, `legacy_import/services/rehearsal_contracts.py`, `field_contracts.py`) — «qapıya sığdırma» qoxusu; grandfathered (>600): `apps/audit/views.py` 1019, `organizations/structure_registry_actions.py` 776, `structure_views/registry.py` 710, `structure_views/members.py` 649, `registrar/lessons_log.py` 634, `exams/domain/final_center.py` 625. | `wc -l`, `scripts/module_size_budget.json` |
| Ölü kod | **PASS** — `probes/dead_code.py`: 3 869 modul-səviyyə tərif, 23 istinadsız — hamısı `tests.py` test sinifləridir (yalan-pozitiv; pytest onları adla tapır). Real ölü kod: `apps/appeals/services/state_machine.py` (`assert_transition`/`can_transition` yalnız `__init__`-də re-export olunur, istehlakçı yoxdur). | `probes/dead_code.txt` |
| `print(` / `breakpoint` / `pdb` | **PASS** — 0 (management command-lar xaric). | grep |
| `console.log` | **PARTIAL (P3)** — 8 hit: `apps/courses/static/courses/js/topic_edit_modal.js:45,66,130` (debug log-lar, «✓ Topic Edit Modal initialized»), `apps/live_exam/static/js/host_lobby/utils.js:278` `[HOST]` logger, `host_lobby_shell.js` 4× `console.debug` (məqbul). | grep |
| TODO/FIXME/HACK | **PASS** — 1 hit: `apps/accounts/templates/accounts/profile/sections/_courses.html:38` «TODO: Gələcəkdə yenidən aktiv ediləcək» (şərhə alınmış bölmə; təsnifat: məhsul qərarı, texniki borc deyil). | grep |

## 2. Tranzaksiya · siqnal · Celery task
Probe: `probes/celery_in_atomic.py` → `probes/celery_in_atomic.txt` (AST: `.delay/.apply_async` konteksti, `select_for_update` leksik konteksti).

| Yoxlama | Nəticə | Sübut |
|---|---|---|
| `ATOMIC_REQUESTS` | **OFF** (default) — yalnız `RLS_TRANSACTION_SCOPED=1` olanda açılır | `config/settings/production.py:323-326` |
| View-lərdə ≥2 yazı, `atomic`-siz | **PARTIAL** — 31 view (probes/api_inventory.tsv `writes>=2 & atomic=False`); riskli olanlar: `apps/accounts/views/organization/requests.py:43 student_organization_request (5 yazı)`, `apps/accounts/views/superadmin/endpoints.py:120 superadmin_organizations (5)`, `apps/blog/views/moderator/posts.py:129 teacher_moderate_post (5)`, `apps/accounts/views/dashboard/review.py:70 pending_review_detail (4)`, `apps/exams/views/teacher/question_library/crud.py:264 question_bank_detail (4)`, `apps/exams/views/teacher/question_bank/_views_create.py:119 process_question_bank (4)`, `apps/exams/views/teacher/exams/attempt_grants.py:31 grant_extra_attempt (2)`. Servis qatında olanlar (registrar/finals, workload, appeals) atomic-dir — bax §6. | TSV sütunları `writes`, `atomic` |
| Siqnallarda DB yazısı | **PASS (nəzarətli)** — 7 signals modulu; yazan receiver-lər: `accounts.ensure_user_profile` (get_or_create, idempotent), `organizations.create_default_roles` (yalnız `created`), `courses.sync_group_*` (m2m → `transaction.on_commit(do_sync)` ✅), `blog.notify_*` (bildiriş yaradır, except→log), `audit.log_*` (AuditLog.create) | `apps/*/signals.py` |
| Celery `.delay` atomic içində on_commit-siz | **FAIL (P3)** — `apps/blog/signals.py:180` `send_new_post_notification_email.delay(...)` `post_save` içində, `rls_worker_atomic()` blokunda; Post view-də atomic çağırılsa task commit-dən əvvəl işə düşür (task `Post.objects.get` ilə pk oxuyur — `autoretry_for=(Exception,)` ilə 2 retry var, yəni özünü bərpa edir, amma bilinən antipattern). | `apps/blog/signals.py:169-184`, `core/email_tasks.py:240-246` |
| `.delay` view-lərdə (extract_jobs) | **PASS** — job sətri `create` olunduqdan sonra `delay`; ATOMIC_REQUESTS OFF olduğu üçün commit artıq baş verib. `RLS_TRANSACTION_SCOPED=1` açılsa bu 3 çağırış (`apps/exams/views/teacher/extract_jobs.py:103,163,209`) `on_commit`-ə keçirilməlidir — task `filter(status=PENDING).update(...)` ilə claim edir, sətir hələ görünmürsə claim 0 qaytarır → job "pending"də ilişir, `reap_stuck_extraction_jobs` yalnız PROCESSING-i reaplayır. | `apps/exams/tasks.py:187,300,401` |
| `select_for_update` atomic-dən kənar | **PASS** — 111 istifadə; 45 leksik "kənar" halın hamısı `_lock_*` köməkçiləridir, çağıranları `@transaction.atomic` (spot: `registrar/finals.py:249`, `handover_actions.py:113`, `applications/services/submit.py:41`, `final_center/sessions.py:163`, `labs/lab_grading_service.py:48`). Django autocommit-də kənar istifadə `TransactionManagementError` atar — testlər tutardı. | probes/celery_in_atomic.txt |
| Task idempotentliyi | **PASS** — `run_text_extraction_job/run_ai_generation_job/run_export_job` şərti `filter(status=PENDING).update(status=PROCESSING)` ilə claim; `time_limit=900/soft 840`; qlobal `CELERY_TASK_TIME_LIMIT=300`, `ACKS_LATE=True`, `PREFETCH=1`. E-mail taskları `autoretry_for=(Exception,)`, `max_retries=3`, backoff. Extraction taskları retry-sız (job status + `reap_stuck_extraction_jobs` lease=1200s ilə kompensasiya). | `apps/exams/tasks.py`, `core/email_tasks.py`, `config/settings/components/celery_cache.py:58-77` |
| Beat taskları (`expire_*`, `auto_close_daily_room_sessions`, `notify_upcoming_final_exams`) | **PASS** — hamısı `filter(...).update()`/servis çağırışı ilə idempotent; `notify_upcoming_final_exams` dublikat bildiriş mühafizəsi: NOT TESTED | `apps/exams/tasks.py:19-160` |

## 3. Validasiya · səhv emalı
### 3.1 `except Exception` inventarı — `probes/except_inventory.txt`
446 geniş `except` (apps+core+config, testsiz): **LOGGED 188 · RAISE 102 · SILENT 155 · FAKE_OK? 1**.
SILENT paylanması: exams 50 · legacy_import 29 · accounts 19 · registrar 16 · organizations 7 · live_exam 7 · labs 6 · core/upload_security 6.

Spot-yoxlama (bal yolları):
| Yer | Davranış | Qiymət |
|---|---|---|
| `apps/exams/services/journal_sync.py:63,69,82` | `_written_attempt_max_score` / `_attempt_percent` istisnada səssiz `[]`/`0`/`None` → körpü faizi `None` → **jurnala yazılmır, log yoxdur** | **FAIL (P2)** — F-08 |
| `apps/registrar/grade_audit.py:174` | tarixçə oxunuşu → `[]` (yalnız göstərmə) | məqbul |
| `apps/exams/services/result_calculation.py:8` | `Decimal(str(x))` → default | məqbul (parse) |
| `apps/live_exam/views/host/game.py:83` (FAKE_OK?) | `int(raw)` xətası → `JsonResponse(status=400)` | yalan-pozitiv, PASS |
| `core/upload_security.py:103-330` (6 SILENT) | fayl imzası/decoder xətası → «etibarsız» kimi rədd | fail-closed, PASS |

### 3.2 200-on-failure JsonResponse — `probes/json_200_on_failure.txt`
8 yer: `accounts/views/people/analytics.py:92 (no_access→200!)`, `:103 (generation_failed)`, `accounts/views/profile/_sections/statistics.py:241`, `accounts/views/schedule_editor.py:101 (validasiya)`, `appeals/views/teacher/endpoints.py:348 (status=200 açıq yazılıb)`, `labs/views/student/submissions.py:44,117,126 (lab_closed/attempts_exhausted)`.
`static/js/core/http.js:67-81` `fetchJSON` yalnız `!response.ok`-da reject edir → bu 8 cavabda promise **resolve** olur, hər istehlakçı `payload.ok`/`payload.success` yoxlamalıdır; açar adı da qarışıqdır (`ok` vs `success`). **PARTIAL (P3)** — F-10. Ən vacibi `analytics.py:92` — icazəsizlik 403 əvəzinə 200.

### 3.3 HTTP semantika (siyahı endpoint-ləri)
| Hal | Cavab | Sübut |
|---|---|---|
| Anonim JSON endpoint | 302 → login (`login_required`) | probe `test_m20` PASS |
| Yad/mövcud olmayan int ID | 404 | `test_m06`, `test_m09`, `test_m14` PASS |
| Yad UUID (URL-də `<uuid:>`) | 404 | `test_m12` PASS |
| **Non-UUID string body/POST parametri UUID pk-ya** | **500** | `test_m01/m02/m21/m23` FAIL — F-01 |
| Naməlum `kind` (`people/<kind>/list`) | 404/400 | `test_m08` PASS |
| Pozuq JSON gövdə | 400 | `test_m10` PASS |
| Uzun/pozuq filtr parametrləri (stats/data, search q=10 000 simvol) | <500 | `test_m15`, `test_m19` PASS |
| Bal xanasına `NaN`/`1e999`/`7.5`/`９`/5 000 simvol | rədd, DB-də 0–10 aralığı | `test_m17` PASS |
| Stack-trace sızması | prod `DEBUG=False`, `handler500` custom | §8 PASS |

## 4. API inventarı — `probes/api_inventory.tsv`
945 route (Django resolver), **522** layihə kodu (`apps/`+`core/`), onlardan **250 JSON** cavab verən. Sütunlar: path · urlname · fayl:sətir · JSON? · CBV? · auth dekorator · gövdədə auth · mixin · metod məhdudiyyəti · perm izi · tenant izi · validasiya izi · rate-limit · csrf_exempt · yazı sayı · atomic · sətir.

Aqreqat (heuristik, sonra əl ilə yoxlanılıb):
| Sütun | Say | Şərh |
|---|---|---|
| JSON endpoint auth-suz (dekorator/mixin/gövdə) | 24 | Hamısı əl ilə yoxlanıb: 3 OTP API (anonim, dizayn), 5 live_exam oyunçu (PIN ilə anonim, dizayn), 13 monitoring (`@superadmin_monitoring_required` — heuristik siyahıda yox idi; `apps/monitoring/permissions.py`: `is_superadmin_user` + rate-limit 240/1m + SecurityEvent), `health/`, `ping/`. **PASS** |
| JSON, perm izi tapılmayan | 89 | Nümunə yoxlama: `exam_center/monitor.py` → `get_center_session_or_404(for_supervision=True)`; `workload/distribution_api.py` → `actor_for()` + servis `WorkloadDenied`; `notifications/views.py` → `_get_own_notification_or_404`; `people/api.py` → `people.*` servisləri `RimAccessError`. İcazə köməkçi funksiyalarda — heuristik yalan-pozitiv. **PASS (nümunəvi)** |
| Metod məhdudiyyətsiz + yazı | 6 | hamısı CBV (`courses/views/teacher/topics.py:134`, `resources.py:68`, `membership.py:212,286,373`, `live_exam/views/host/session.py:27`) — `post()` metodu ilə; **PASS** |
| `csrf_exempt` | 1 | `monitoring/views.py:351 alertmanager_webhook` — bearer/HMAC (Codex remediasiyası) **PASS** |
| Rate-limit izi olan JSON | 10 | OTP, monitoring, AI; **bal yazan/ixrac edən endpoint-lərdə rate-limit yoxdur** (məs. `workload:assign`, `student_registry_action`, `exam_score_import_apply`) — P3 qeyd |
| ≥2 yazı, atomic-siz | 31 | bax §2 |

Malformed-input probe-ları (sandbox, `probes/test_backend_probes.py::MalformedInputProbes*`, 24 test): **20 PASS · 4 FAIL** (F-01).

## 5. Status sahələri / state machine
### 5.1 Cədvəl (kodda tətbiq olunan keçidlər)
| Model.sahə | Dəyərlər | Keçid mənbəyi | Qadağan keçidin qorunması |
|---|---|---|---|
| `syllabus.SyllabusVersion.status` | draft·submitted·review·revision·approved·rejected·archived | `apps/syllabus/state_machine.py:80-140 TRANSITIONS` (sources/target/permission/reason/author_only) | approved→yalnız archive; rejected/archived terminal; `save_section` `EDITABLE_STATUSES` yoxlayır (`services/drafts.py:364`) |
| `appeals.Appeal.status` | pending·under_review·accepted·rejected·partially_accepted | **Törəmə**: `services/decisions.py:367 recompute_appeal_status` (item statuslarından) | `APPEAL_STATUS_TRANSITIONS`/`assert_transition` **istifadə olunmur**; item-lər yenidən qərar verilə bilər (accept↔reject idempotent, ledger `ScoreAdjustment` ilə) — dizayn |
| `appeals.AppealItem.status` | pending·accepted·rejected | `accept_appeal_item` / `reject_appeal_item` (`select_for_update`, atomic) | yaradılış pəncərəsi `APPEAL_WINDOW_DAYS` (`services/window.py`) |
| `applications.Application.status` | submitted·in_review·assigned·forwarded·waiting_info·returned·resolved·rejected | `apps/applications` state machine (test_state_machine.py: legal/illegal/terminal) | testlə |
| `exams.ExamAttempt.status` | draft·in_progress·submitted·expired (+ `supervision_status` active·warned·locked·removed·resumed) | `views/student/attempts.py:313,484 is_finished` → nəticəyə yönləndirmə; `tasks.expire_*` | bitmiş cəhdə cavab yazılmır (redirect) |
| `exams.ExamRoomSession.state` | prepared·entry_open·active·ended·cancelled | `services/final_center/sessions.py` (`RoomSessionStateError`, şərti UPDATE) | test_final_center_flow (73 test) |
| `registrar.AssessmentScheme.approval_status`+`is_published` | draft / **approved+published = KİLİD** | `journal_close.close_journals/reopen_journals` (RİM toplu) | `gradebook.journal_is_locked` — **tək mənbə**, 20+ çağıran |
| `registrar.Enrollment.status` | enrolled·completed·dropped | `guest_roster`, `services.enroll_*` | `finals._is_current_enrollment`, `save_marks` yalnız ENROLLED |
| `registrar.StudentAcademicRecord.status` | AcademicStatus (qeydiyyatlı/məzuniyyət/xaric/məzun) | `accounts/services/people/movements.py` | NOT TESTED |
| `workload.TeachingTask.status` | draft·submitted·returned·pending_final_approval·approved·distributing·distributed·amended·cancelled | `services/tasks.py`, `EDITABLE_STATUSES`/`LOCKED_STATUSES` (`constants.py:55,62`) | `services/tasks.py:251` |
| `organizations.Organization.status` | active·pending·suspended | superadmin endpoint | `SuspendedOrganizationMiddleware` |
| `organizations.AcademicPeriod` (`SemesterLockMixin`) | kilid sahələri | `organizations/semester_meta.py:39` | guest_roster «keçmiş dövr» testləri |

### 5.2 Qadağan keçid sınaqları (sandbox `ems_audit_backend`)
Yeni probe: `probes/test_backend_probes.py::JournalLockStateMachineProbes` (9 test, **hamısı PASS**); mövcud dəstlər: `probes/existing_state_tests.txt` (**228 passed**).

| # | Sınaq | Nəticə | Sübut |
|---|---|---|---|
| S1 | Bağlı jurnala `gradebook.save_marks` | PASS — 0 yazı, LessonMark yoxdur | `test_p2` |
| S2 | Bağlı jurnala HTTP POST (müəllim) | PASS — 302 + xəta mesajı, yazı yoxdur | `test_p3` |
| S3 | Bağlı jurnala dərs əlavəsi | PASS — `LessonRuleError` | `test_p4` |
| S4 | Bağlı jurnalda `set_resit_score` / `set_final_extras` | PASS — `None` | `test_p5` |
| S5 | Bağlı jurnalda `set_exam_score` | **İCAZƏLİ (sahib qərarı, `finals.py:253-266`)** — sənədləşdirilib, audit-loglanır | `test_p5` |
| S6 | DROPPED enrollment-ə imtahan balı / xana | PASS — rədd | `test_p6` |
| S7 | Sahib olmayan müəllim jurnal POST | PASS — 404 | `test_p7` |
| S8 | reopen → kilid açılır | PASS | `test_p8` |
| S9 | Suspended org → müəllim səhifəsi | PASS — login-ə yönləndirmə (middleware) | `test_p9`, `test_middleware.py` |
| S10 | approved sillabus → submit/withdraw/revision (archive xaric) | PASS | `test_approved_version_is_locked_against_every_transition_but_archive` |
| S11 | rejected/archived sillabus → hər keçid | PASS | `test_rejected_and_archived_are_terminal` |
| S12 | Application qadağan keçidlər / terminal | PASS | `applications/tests/test_state_machine.py` |
| S13 | RoomSession ended/cancelled → start | PASS | `test_final_center_flow.py` |
| S14 | Workload icazəsiz submit / yad fakültə | PASS | `test_stage4_workflow.py` |
| S15 | Apellyasiya pəncərəsi bağlandıqdan sonra yaradılış | PASS | `appeals/tests/test_window.py` |
| S16 | Qərar verilmiş apellyasiya item-i yenidən qərar | **İCAZƏLİ (dizayn)** — revert+yenidən tətbiq, ledger; sənədli `APPEAL_STATUS_TRANSITIONS` cədvəli ilə uyğunsuz (cədvəl ölüdür) — F-11 (P3) | `decisions.py:152-305` |
| S17 | Bitmiş cəhdin yenidən açılması | NOT TESTED (kod: `is_finished` → redirect; `exam_center_ticket_reentry` yalnız mərkəz üçün) | `attempts.py:313,484` |

## 6. Biznes-qayda ardıcıllığı
| Qayda | Kod nə edir | Verdikt |
|---|---|---|
| Müəllim jurnal yazmazdan əvvəl açılışa sahib olmalıdır | `registrar/journal_access.py:117 is_direct_editor` = superuser ∨ (offering.instructor_id == user ∧ `integrity.is_authorized_instructor`) ∨ org sahibi; korrektor (İKT) yalnız sənədli düzəliş; təhvil verən köhnə müəllim read-only (`can_observe_journal`) | **PASS** (S7) |
| Sillabus təsdiqi akademik istifadədən əvvəl | `registrar/journal_policy.py:89 require_approved_syllabus` — **org siyasəti, default SÖNDÜRÜLÜ**; açıq olduqda `SyllabusGateError`. Tələbə kartı yalnız approved versiyanı göstərir (Codex §17). README-də «jurnal təsdiqlənmiş sillabus olmadan bloklanır» iddiası default davranışla uyğun deyil | **PARTIAL** — sənəd ↔ kod (F-12, P3) |
| Bal dərci | Jurnal təsdiq zənciri yoxdur (sahib, 2026-08); RİM semestr sonunda `close_journals` (audit ilə); yekun imtahan balı kilidə tabe deyil (sənədli) | **PASS (sənədləşdirilmiş)** |
| Apellyasiya pəncərəsi | `APPEAL_WINDOW_DAYS` (constants) — `is_within_appeal_window` yaradılışda və `permissions.py`-də; təqvim günü əsaslı | **PASS** |
| Semestr/dövr kilidi | `SemesterLockMixin` (`organizations/semester_meta.py`) + guest_roster «keçmiş dövr» rədd; `journal_close` dövr üzrə | **PASS** (test_guest_roster_locks) |
| Enrollment statusunun təsiri | `save_marks` yalnız ENROLLED; `finals.set_*` `_is_current_enrollment` | **PASS** (S6) |
| **Davamiyyət limiti (25 %) — vahid mənbə** | Defolt `exam_eligibility.DEFAULT_LIMIT_PERCENT=25` = `analytics._DEFAULT_ABSENCE_LIMIT=25` = `catalog_actions` fallback 25 ✅. Amma **limitin həlli 2 yolla**: (A) tələbənin ÖZ proqramı — `registrar/services.py:285`, `cabinet_policy.py:117`, `transcript`; (B) **açılışın qrupundakı İLK `StudentAcademicRecord`-un proqramı** — `gradebook.absence_limit_percent_for(offering)` (`gradebook.py:103-110`, `.first()` sırasız) → `exam_bridge.py:74` (**imtahana start qapısı**) və `registrar/public.py:377`. Alt-qrup/qonaq tələbə (başqa proqram, fərqli `absence_limit_percent`) üçün kabinet «buraxılır», imtahan qapısı «kəsilib» (və ya əksinə) deyə bilər; qrup boşdursa/`group=None` isə defolt 25 | **FAIL (P2)** — F-06 |
| **Yuvarlaqlaşdırma / GPA — vahid mənbə** | Yuvarlaqlaşdırma: `gradebook.round_score` ROUND_HALF_UP (tam), `transcript._round2` HALF_UP, `exam_bridge:252` HALF_UP, `attendance.py:87` ROUND_DOWN (qəsdən, davamiyyət balı) ✅. Hərf/GPA nöqtəsi: `registrar/grading_scale.score_to_letter` — tək mənbə (tenant şkalası) ✅. **ÜOMG isə 2 düstur**: transkript `transcript._summarize` → `exam_eligibility.uomg_from` = Σ(yekun_bal×kredit)/Σkredit **100 bal**, məxrəc `passed∨failed`; tələbə statistikası `accounts/services/statistics_metrics/student.py:112-127` = Σ(**4.0 GPA nöqtəsi**×kredit)/Σkredit, məxrəc `graded`, `quantize(0.01)` (HALF_EVEN) — və eyni «ÜOMG (GPA)» etiketi ilə göstərilir (`presenter.py:216`). Eyni tələbə iki ekranda iki fərqli «ÜOMG» görür (məs. 3.50 vs 78.40) | **FAIL (P2)** — F-05 |
| Akademik il sərhədləri | `AcademicPeriod.is_current` + `start_date/end_date`; `transcript.student_credit_totals` «bitməmiş dövr» qaydası statistika ilə eyni (şərh `student.py:103`) | **PASS** |
| Cəhd limiti | 3 güzgü implementasiya, parity testi yoxdur | **PARTIAL (P3)** — F-13 |

## 7. Audit-log əhatəsi
`core/audit.py:16 log_action` (+ `apps/audit/public.py`), `registrar/grade_audit.log_grade_changes`, domen ledger-ləri (`ExamGradeEvent`, `ScoreAdjustment`, `JournalCorrection`).

| Yüksək riskli əməl | Audit çağırışı | Fayl | Verdikt |
|---|---|---|---|
| Jurnal xanası/komponent/yekun bal dəyişikliyi | `grade_audit.log_grade_changes` | `registrar/gradebook.py`, `gradebook_components.py`, `finals.py` (3), `journal_extras.py` (2), `corrections.py` (6) | PASS |
| Jurnal bağlama/açma | `journal_close._audit` (4) | `registrar/journal_close.py:124` | PASS |
| Tələbə hərəkəti/arxiv/silinmə | `log_action` | `accounts/services/people/movements.py`, `actions.py` (3), `academic_actions.py` (2), `identity_archive.py` (2) | PASS |
| Müəllim təyinatı / təhvil | `log_action` | `registrar/handover_actions.py` (4), `catalog_actions.py` (4), `workload/services/assignments.py` (2), `tasks.py` (3) | PASS |
| **Rol təyinatı / silinməsi (`manage_roles`)** | **YOXDUR** — `_sync_user_role_memberships` (`accounts/views/_helpers/membership.py:59`) Membership-ləri deaktiv/yaradır, `manage.py:58-226` yalnız `messages.success` | `accounts/views/roles/manage.py` | **FAIL (P1)** — F-02 |
| İcazə redaktoru | `log_action` (1) | `accounts/views/roles/permissions.py` | PASS |
| Struktur reyestri (vahid/üzv) | `log_action` (7) | `organizations/structure_registry_actions.py` | PASS |
| İmtahan publish/unpublish/arxiv/silmə | `log_action` | `exams/services/lifecycle.py:37`, `views/teacher/exams/actions.py:138` | PASS |
| İmtahan nəticəsi dəyişikliyi (manual grading) | `ExamGradeEvent` ledger (3 yer) | `exams/services/manual_grading.py:80,118,199` | PASS (domen ledger) |
| Nəticə saxlama/silmə (retention) | `log_action` (2) | `exams/services/retention.py` | PASS |
| **Əlavə cəhd hüququ (`grant_extra_attempt`)** | **YOXDUR** — `StudentExamAttemptGrant.get_or_create` + bildiriş | `exams/views/teacher/exams/attempt_grants.py:71,109` | **FAIL (P2)** — F-03 |
| Zal oturumu start/end/cancel | `log_action` (monitor.py import), `sessions.py` (1) | `exams/views/exam_center/monitor.py` | PASS |
| Apellyasiya qərarı | `_audit_score_change` / `_audit_score_revert` + `ScoreAdjustment` | `appeals/services/decisions.py:47-105` | PASS |
| Sillabus keçidləri | `log_action` (4) | `syllabus/services/workflow.py` | PASS |
| Üzv çıxarılması / dəvət | `log_action` | `_management_flow/_members.py` (1), `_invites.py` (2), `organizations/services.py` (2) | PASS |
| **Təşkilat approve/suspend/reactivate (superadmin)** | **YOXDUR** — yalnız `_notify_org_owner_of_approval`; `organization.status=` 4 yerdə | `accounts/views/superadmin/endpoints.py:144,169,193,212` | **FAIL (P2)** — F-04 |
| **Hərf/GPA şkalasının dəyişdirilməsi (`set_bands`/`reset_bands`)** | **YOXDUR** | `accounts/views/superadmin/endpoints.py:261,275`, `registrar/grading_scale.py` | **FAIL (P2)** — F-04 |
| Giriş/çıxış/admin | `apps/audit/signals.py` (login/logout/LogEntry) | | PASS |
| Log məzmununda sirr | `log_action` `old_values/new_values` üçün redaksiya yoxdur; yeganə parol-bağlı çağırış `profile/post_handler.py:39` yalnız `reason="Password changed via …"` (dəyər yox). grep `password|secret|token|api_key` log_action arqumentlərində → 0 | PASS (redaksiya qatı olmasa da) |

## 8. Django settings gigiyenası
| Yoxlama | Nəticə | Sübut |
|---|---|---|
| `SECRET_KEY` | PASS — prod `os.environ["SECRET_KEY"]` (KeyError → başlamır); local boş olsa `ImproperlyConfigured` | `config/settings/production.py:238`, `local.py:206-218` |
| `DEBUG` | PASS — prod sabit `False`; local `_env_bool("DEBUG", True)` | `production.py:246` |
| `ALLOWED_HOSTS` | PASS — boşdursa `ImproperlyConfigured` | `production.py:299-301` |
| TLS/kuki | PASS — `SECURE_SSL_REDIRECT/SESSION_COOKIE_SECURE/CSRF_COOKIE_SECURE` default True; söndürmək üçün yalnız `INSECURE_TRANSPORT_OK=1` açıq bayrağı (Codex P1-08 cavabı) | `production.py:331-360` |
| HSTS | PASS — 31536000, subdomains+preload SSL_REDIRECT-ə bağlı | `production.py:379-381` |
| Admin | PASS — `/admin/` prefiksi qadağan, `ADMIN_2FA_REQUIRED` məcburi | `production.py:283,294` |
| `DATABASES` | PASS — `conn_max_age` env (default 0 → PgBouncer ilə uyğun), `conn_health_checks=True`; `ATOMIC_REQUESTS` yalnız `RLS_TRANSACTION_SCOPED` ilə (şüurlu) | `production.py:306-326` |
| `MIDDLEWARE` sırası | PASS — RequestId→Metrics→Security→SecurityHeaders→WhiteNoise→CSP→AdminSecurity→Session→Locale→Common→CSRF→Auth→AdminOTPGate→RequestQueue→SessionTimeout→Messages→PostLoginGuard→XFrame→ViewAs→Organization→SuspendedOrg→FirstLoginPassword. `ViewAs` `Organization`-dan əvvəl (şərh edilib), `SuspendedOrganization` `Organization`-dan sonra ✅ | `config/settings/components/apps.py:47-78` |
| Cache açar namespace | PASS (per-tenant) — `core/cache.py` bütün açarlar `_PREFIX` + `org_id`/`scope_id` (`_profile_badge_counts_key`, `_statistics_key` role+scope_id+filters; Codex P1-06 scope-id əlavəsi mövcud) | `core/cache.py:162-290` |
| Celery | PASS — JSON serializer, `TASK_TIME_LIMIT=300`, `ACKS_LATE`, `PREFETCH=1`, `RESULT_EXPIRES=3600` | `celery_cache.py:53-77` |
| TZ/locale | PASS — `TIME_ZONE="Asia/Baku"`, `USE_TZ=True`, `LANGUAGE_CODE="az"`, `CELERY_TIMEZONE` eyni | `i18n_static.py:13-25`, `celery_cache.py:57` |
| Error handlers / stack-trace sızması | PASS — `handler403/404/500` `core.views`-dən; prod DEBUG=False | `config/urls.py:21-23` |
| Session | PASS — HttpOnly, SameSite=Lax, 7 gün; `SESSION_COOKIE_AGE` env | `security.py:59-103` |

## 9. Tapıntılar (P0–P3) və minimal düzəlişlər
Say: **P0 0 · P1 1 · P2 7 · P3 7**. Hər tapıntı üçün ən kiçik təhlükəsiz düzəliş (fix agenti üçün).

| ID | Sev | Tapıntı | Sübut | Minimal düzəliş |
|---|---|---|---|---|
| F-01 | P2 | Gövdə/POST parametrindən gələn **qeyri-UUID/qeyri-int pk** ORM filtrinə düşür → `ValidationError`/`ValueError` → **HTTP 500** (autentifikasiyalı istifadəçi; Sentry səs-küyü, «server xətası» səhifəsi). Sandbox-da təkrarlandı: `workload:assign`, `workload:row_save` (`row_id="abc"`), `registrar:schedule` add-slot (`offering_id="abc"`), `accounts:superadmin_organizations` (`organization_id="abc"`). Eyni naxış: `distribution_api.py:57,255,277,296,304,335`, `schedule_views.py:73`, `superadmin/endpoints.py:131`; `correction_views.py:138-308`, `journal_actions.py:312`, `exam_rooms.py:175,190`, `languages.py:116` (`get_object_or_404(Model, pk=request.POST.get(...))` — icazə qapısı əvvəl gəldiyi üçün probe-da 500 alınmadı, amma naxış eynidir) | `probes/test_backend_probes.py::MalformedInputProbes::test_m01/m02`, `::MalformedInputProbesExtra::test_m21/m23` FAIL | `core/utils.py`-a `parse_uuid(value) -> UUID|None` / `parse_int` köməkçisi; sadalanan yerlərdə `pk=parse_uuid(payload.get("row_id"))` (None → 404/`error(...,404)`). Alternativ (bir yerdə): `core/middleware.py`-da `process_exception` ilə `django.core.exceptions.ValidationError` (UUID mesajı) → 400 JSON/HTML |
| F-02 | **P1** | **Rol təyinatı/silinməsi audit-loglanmır.** `manage_roles` POST (`apps/accounts/views/roles/manage.py:58-226`) → `_sync_user_role_memberships` (`views/_helpers/membership.py:59`: Membership deaktiv/`update_or_create`) — nə `log_action`, nə tarixçə modeli; yalnız `messages.success`. Rol dəyişikliyi icazə səthini dəyişir (ROL_MATRISI) — kimin kimə nə vaxt hansı rolu verdiyi bərpa edilə bilmir | grep `log_action` manage.py/membership.py → 0; `organizations/signals.py:65` yalnız keş | `manage.py` ~sətir 183 (`_sync_user_role_memberships` çağırışından sonra): `log_action("role_change", user=request.user, request=request, resource_type="Membership", resource_id=str(target_user.pk), old_values={"roles": sorted(current_roles)}, new_values={"roles": sorted(effective_roles)}, reason=" / ".join(diff_parts), organization=user_org)` |
| F-03 | P2 | Əlavə imtahan cəhdi hüququ (`grant_extra_attempt`, `grant_extra_attempt_group`) audit-siz — müəllim tələbəyə limitdən artıq cəhd verir, iz yoxdur | `apps/exams/views/teacher/exams/attempt_grants.py:71,109` | `_upsert_grant` içində `log_action("exam_attempt_grant", resource_type="StudentExamAttemptGrant", new_values={"exam": exam.pk, "student": student.pk, "extra": extra})` |
| F-04 | P2 | Superadmin **təşkilat approve/suspend/reactivate** (`organization.status=` ×4) və **hərf/GPA şkalası** `set_bands/reset_bands` audit-siz — tenant-səviyyəli, bütün qiymətlərə təsir edən parametr | `apps/accounts/views/superadmin/endpoints.py:144,169,193,212,261,275` | Hər budaqda `log_superadmin_cross_org_action`/`log_action(..., old_values={"status": old}, new_values={"status": new})`; `grading_scale.set_bands` içində `log_action("grading_scale_change", old_values={"bands": bands_for(org)}, new_values={"bands": bands})` |
| F-05 | P2 | **ÜOMG iki düstur, eyni etiket.** Transkript: Σ(yekun_bal×kredit)/Σkredit (100 bal, məxrəc passed∨failed) — `registrar/transcript.py:73-101` → `exam_eligibility.uomg_from`. Tələbə statistikası: Σ(4.0-GPA×kredit)/Σkredit (məxrəc graded, HALF_EVEN) — `accounts/services/statistics_metrics/student.py:112-127`, etiket «ÜOMG (GPA)» `presenter.py:216` | kod oxunuşu | `student.py:112`: `quality_points += Decimal(result["total"]) * credit` və məxrəc `result["passed"] or result["failed"]`; `snapshot["gpa"] = exam_eligibility.uomg_from(quality_points, gpa_credits)[0]`; və ya etiketi «Orta GPA (4.0)» edib transkript ÜOMG-ni ayrıca göstərmək |
| F-06 | P2 | **Davamiyyət limiti iki mənbədən həll olunur.** İmtahana start qapısı (`registrar/exam_bridge.py:74`) və `registrar/public.py:377` → `gradebook.absence_limit_percent_for(offering)` = açılış **qrupunun ilk** `StudentAcademicRecord`-unun proqramı (`gradebook.py:103-110`, sırasız `.first()`); kabinet/transkript → tələbənin **öz** proqramı. Qonaq/alt-qrup tələbə fərqli proqramdandırsa qapı və kabinet ayrı limit görür. Sandbox repro: eyni tələbə üçün gate=25, cabinet=10 | `probes/test_backend_probes.py::AttendanceLimitSourceProbe` PASS (fərqi sənədləşdirir) | `gradebook.absence_limit_percent_for(offering, *, enrollment=None)`: `enrollment` verilibsə `StudentAcademicRecord.objects.filter(student=enrollment.student, organization=...).select_related("program").first()` istifadə et; `exam_bridge.py:74` və `public.py:377` enrollment ötürsün |
| F-07 | P2 | `ATOMIC_REQUESTS=False` olduğu halda 31 view ≥2 DB yazısını `transaction.atomic`-siz edir; yarımçıq yazı riski ən yüksək: `accounts/views/organization/requests.py:43` (5 yazı), `accounts/views/superadmin/endpoints.py:120` (5), `blog/views/moderator/posts.py:129` (5), `accounts/views/dashboard/review.py:70` (4), `exams/views/teacher/question_library/crud.py:264` (4), `exams/views/teacher/question_bank/_views_create.py:119` (4), `exams/views/teacher/exams/attempt_grants.py:31` (2) | `probes/api_inventory.tsv` (`writes>=2`, `atomic=False`) | Hər birində POST budağını `with transaction.atomic():` ilə sar (ən sadə: view-a `@transaction.atomic` dekoratoru — yalnız POST üçün `transaction.atomic()` blokuna üstünlük ver) |
| F-08 | P2 | `exams/services/journal_sync.py:63,69,82` — maksimum bal/faiz hesabında istisna **səssiz** `[]/0/None` → cəhd jurnala **sinxronlaşmır, log yoxdur** (Codex «bal itkisi» remediasiyası bu yolu əhatə etmir) | kod oxunuşu; except_inventory SILENT | `except Exception: logger.exception("journal_sync: max score alınmadı attempt=%s", attempt.pk)` + eyni `return`; `_attempt_percent` `None` qaytaranda `logger.warning` |
| F-09 | P3 | `apps/blog/signals.py:180` `send_new_post_notification_email.delay` `post_save`+atomic içində `on_commit`-siz; `exams/views/teacher/extract_jobs.py:103,163,209` `.delay` — `RLS_TRANSACTION_SCOPED=1` (ATOMIC_REQUESTS) açılanda job commit-dən əvvəl claim edilə bilməz və `pending`-də ilişər (reaper yalnız PROCESSING) | §2 | `transaction.on_commit(lambda: task.delay(...))` (4 yer) |
| F-10 | P3 | 8 JSON cavab `ok/success=False` ilə **HTTP 200**; `fetchJSON` resolve edir; `people/analytics.py:92` icazəsizlik 200. Açar adı qarışıq (`ok` / `success`) | `probes/json_200_on_failure.txt` | `status=403` (analytics no_access), `status=400/409/422` digərləri; uzun müddətdə `core/http` tərəfində `payload.ok===false` → reject |
| F-11 | P3 | `appeals/constants.py:53 APPEAL_STATUS_TRANSITIONS` + `services/state_machine.py` ölü — status item-lərdən törənir; sənədləşdirilmiş keçid cədvəli faktiki davranışla (qərar verilmiş item yenidən qərar oluna bilər) uyğun deyil | grep → yalnız re-export | Ya `recompute_appeal_status`-da `assert_transition(previous_status, new_status)` çağır (qaydanı canlandır), ya modulu sil və docstring-i düzəlt |
| F-12 | P3 | Sənəd↔kod: «jurnal təsdiqlənmiş sillabus olmadan bloklanır» (README §8/2) — kodda org siyasəti **default söndürülü** (`registrar/journal_policy.py:89`) | kod | README-də «opsional siyasət (`organization.settings.journal.require_approved_syllabus`), default off» yaz |
| F-13 | P3 | Güzgü implementasiyalar parity testsiz: cəhd limiti ×3 (`exam_definition.py:330`, `attempt_budget.py:26`, `student_list_batch.py:243`); `analytics_fast` vs `finals.compute_final_result` | §1 | Bir parametrik test: eyni fixture üzərində 3 funksiyanın nəticəsini bərabərlə |
| F-14 | P3 | 23 modul 590–600 sətir (7-si düz 600) — ölçü qapısına «sığdırma»; `courses/static/courses/js/topic_edit_modal.js:45,66,130` `console.log` debug qalıqları | §1 | Debug log-ları sil; 600-lük modulları növbəti toxunuşda böl |
| F-15 | P3 | Bal yazan/idxal edən JSON endpoint-lərdə rate-limit yoxdur (`workload:assign`, `student_registry_action`, `exam_score_import_apply`, `rim_action`) — yalnız OTP/monitoring/AI limitlidir | TSV `rl` | `core/rate_limit.is_rate_limited` ilə per-user 60/1m (bal/idxal POST-larına) |

## 10. Ballar (0–100)
| Sahə | Bal | Əsaslandırma |
|---|---:|---|
| Backend | 76 | Servis qatı güclü (kilid tək mənbə, `select_for_update`, idempotent tasklar, state-machine sınaqları 100 % keçdi); mənfi: 31 atomic-siz çoxyazılı view, səssiz körpü istisnası (F-08), 500 verən pk parse (F-01) |
| API Design | 72 | 250 JSON endpoint auth/perm baxımından təmiz (24 auth-suz halın hamısı dizayn); mənfi: qeyri-vahid xəta zərfi (`ok`/`success`, 200-on-failure), UUID/int parse 500-ləri, yazı endpoint-lərində rate-limit yoxdur, OpenAPI yoxdur |
| Architecture | 80 | Modul sərhədləri/fasadlar (Codex §8 təsdiqi), icazə köməkçilərə mərkəzləşib, siqnallar nəzarətli, `on_commit` m2m-də düzgün; mənfi: ölü appeal state-machine, güzgü implementasiyalar |
| Code Quality | 78 | print/pdb 0, TODO 1, ölü kod praktiki 0; 446 geniş except-in 155-i səssiz (əksəri fail-closed parse), 3 debug `console.log` |
| Maintainability | 74 | 23 modul qapıya sığdırılıb (7×600), 6 grandfathered >600 (audit/views.py 1019), 22 view >150 sətir, 3 nüsxə cəhd-limiti qaydası |
| Business-logic consistency | 70 | Jurnal kilidi, müəllim sahibliyi, enrollment statusu, dövr kilidi, apellyasiya pəncərəsi — hamısı PASS; **iki P2 uyğunsuzluq**: ÜOMG iki düstur (F-05), davamiyyət limiti iki mənbə (F-06, repro); README↔kod sillabus qapısı |
| Audit logging | 68 | Bal/jurnal/tələbə hərəkəti/təhvil/sillabus/apellyasiya/imtahan lifecycle loglanır; **rol təyinatı (P1)**, əlavə cəhd, təşkilat statusu və GPA şkalası loglanmır; log məzmununda sirr tapılmadı |
| **Sahə üzrə ümumi** | **74** | Çəkili orta (Backend 25 %, Business-logic 20 %, Audit 15 %, API 15 %, Arch 10 %, CQ 10 %, Maint 5 %) ≈ 74 |
