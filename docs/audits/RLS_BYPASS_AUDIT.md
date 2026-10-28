# RLS Bypass Audit (FAZA 10)

> Tarix: 2026-05-24 · Sayım yeniləməsi: 2026-10-08 (təhlükəsizlik dizaynı: WS qapısı + final cihaz bağlantısı; 2026-10-07 təhlükəsizlik auditi; əvvəlki 2026-09-13, `access` F-13)
> Status: Analiz sənədi — kod dəyişmir. Gələcək təhlükəsizlik audit-i üçün bələdçi.

## Niyə bu sənəd var

`core.rls.bypass_rls()` / `set_rls_bypass()` PostgreSQL Row-Level Security
siyasətlərini **müvəqqəti söndürür** — yəni sorğu bütün tenant-ların sətirlərini
görür. Hər istifadə potensial cross-tenant sızıntı nöqtəsidir. Kod bazasında
**250 çağırış / 139 fayl** var (test faylları xaric; 2026-10-23, skriptlə sayılıb; CI qapısı `core/tests/test_secaudit_2026_10_07_rls_bypass_inventory.py` — aşağıya bax). Bu sənəd onları kateqoriyalaşdırır
ki, gələcəkdə hər biri qəsdən və əsaslandırılmış qalsın.

## Sayım (fayl üzrə, test xaric) — 2026-10-23 yeniləməsi

> **Mənbə:** `venv/bin/python scripts/rls_bypass_inventory.py --markdown` — cədvəl
> ƏLLƏ yazılmayıb (audit `access` 2026-09-13, F-13: 2026-05 sayımı «~85» əllə
> aparılmışdı və 164/64-ə qədər köhnəlmişdi). Sayım qaydası skriptin
> docstring-indədir (şərh/`def`/`import` sətirləri sayılmır; `_bypass_rls()`
> alias-ları sayılır). Yeni `bypass_rls` əlavə edəndə skripti yenidən işlədib
> bu bölməni əvəz edin; skript təsnif edilməmiş fayl görsə 1 ilə çıxır.

| Fayl | Çağırış | Kateqoriya |
|---|---:|---|
| `apps/exams/tasks.py` | 11 | D — Celery (sorğu konteksti yoxdur; job sətri org FK-lıdır) |
| `apps/blog/services.py` | 9 | A — qlobal blog (tenant-suz) |
| `apps/blog/views/moderator/post_management.py` | 7 | A — qlobal blog (tenant-suz) |
| `apps/exams/services/final_center/entry.py` | 7 | B — final mərkəzi PIN axını |
| `apps/notifications/services/read_state.py` | 7 | A — recipient-scoped bildiriş |
| `apps/organizations/middleware.py` | 6 | D — tenant kontekst qurma |
| `apps/accounts/services/view_as.py` | 5 | C — view-as (hədəf yoxlaması ilə) |
| `apps/exams/services/final_center/device_binding.py` | 5 | B — final mərkəzi PIN axını |
| `apps/notifications/services/crud.py` | 5 | A — recipient-scoped bildiriş |
| `core/rls.py` | 5 | D — RLS infrastrukturunun özü (kontekst menecerləri) |
| `apps/accounts/services/organization_requests.py` | 4 | C — üzvlük sorğusu axını |
| `apps/blog/signals.py` | 4 | A — qlobal blog (tenant-suz) |
| `apps/exams/services/exam_center_gate.py` | 4 | B — imtahan mərkəzi qapısı |
| `apps/live_exam/views/player/join.py` | 4 | B — public PIN/token girişi |
| `apps/subject_folder/tasks.py` | 4 | D — Celery (rls_worker_atomic; sətrin öz təşkilatı) |
| `core/tenancy.py` | 4 | D — tenant kontekst qurma |
| `apps/accounts/views/organization/_management_flow/_invites.py` | 3 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/organization/_management_flow/flow.py` | 3 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/profile/view_as.py` | 3 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/ws_gate.py` | 3 | D — WebSocket giriş qapısı (istifadəçinin öz sətirləri + audit) |
| `apps/live_exam/consumers.py` | 3 | B — public PIN/token girişi |
| `apps/live_exam/scoring.py` | 3 | B — public PIN/token girişi |
| `apps/live_exam/views/player/_shared.py` | 3 | B — public PIN/token girişi |
| `apps/live_exam/views/player/wait.py` | 3 | B — public PIN/token girişi |
| `apps/accounts/management/commands/shrink_avatars.py` | 2 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/password_policy.py` | 2 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/services/rim/activation.py` | 2 | A — recipient-scoped bildiriş (RİM rolları, öz təşkilat) |
| `apps/accounts/tasks.py` | 2 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/_helpers/org_sections/_members_registry.py` | 2 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/organization/_management_flow/_members.py` | 2 | C — superadmin / admin cross-org əməliyyatı |
| `apps/exams/consumers.py` | 2 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/services/center_exams.py` | 2 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/services/final_center/reentry.py` | 2 | B — final mərkəzi PIN axını |
| `apps/exams/views/student/final_center.py` | 2 | B — final mərkəzi PIN axını |
| `apps/live_exam/auth.py` | 2 | B — public PIN/token girişi |
| `apps/live_exam/views/api.py` | 2 | B — public PIN/token girişi |
| `apps/monitoring/permissions.py` | 2 | C — superadmin monitorinq |
| `apps/notifications/management/commands/purge_notifications.py` | 2 | A — recipient-scoped bildiriş |
| `apps/notifications/views.py` | 2 | A — recipient-scoped bildiriş |
| `apps/organizations/holidays.py` | 2 | C — təşkilat idarəetməsi |
| `apps/registrar/management/commands/normalize_interim_components.py` | 2 | C — idarə əmrləri |
| `apps/registrar/management/commands/set_program_official_codes.py` | 2 | C — idarə əmrləri |
| `apps/surveys/services/pending.py` | 2 | D — anonim cavab buferi köçürməsi (artıq icazəli kampaniya id-si) |
| `apps/surveys/tasks.py` | 2 | D — Celery (rls_worker_atomic; sorğunun öz təşkilatı) |
| `apps/accounts/management/commands/blocked_accounts_report.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/management/commands/finalize_university_identity.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/management/commands/import_legacy_staff_positions.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/management/commands/import_students_atis.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/legacy_import/management/commands/legacy_journal_teachers_extract.py` | 1 | C — idarə əmri (yalnız oxu; sübut faylı) |
| `apps/legacy_import/management/commands/build_twin_repair_plans.py` | 1 | C — idarə əmri (yalnız oxu, lokal prod surəti; plan faylında yalnız id-lər) |
| `apps/legacy_import/management/commands/build_practical_flag_plan.py` | 1 | C — idarə əmri (yalnız oxu, lokal prod surəti; plan faylında yalnız açılış id-ləri; 2026-10-28) |
| `apps/legacy_import/management/commands/restore_archived_students.py` | 1 | C — idarə əmri (adla verilən hesablar; auditli `restore_archived_account`, dry-run defolt) |
| `apps/legacy_import/management/commands/build_journal_share_plans.py` | 1 | C — idarə əmri (yalnız oxu, lokal prod surəti; plan faylında yalnız id-lər) |
| `apps/legacy_import/management/commands/chair_journal_health.py` | 1 | C — idarə əmri (yalnız oxu; müəllim id-ləri, adlı Excel yalnız repodan kənar lokal yola) |
| `apps/accounts/management/commands/import_users_from_excel.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/management/commands/issue_staff_credentials.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/management/commands/profile_completion_report.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/management/commands/provision_student_credentials.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/management/commands/reconcile_teacher_roster.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/management/commands/rename_legacy_usernames.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/management/commands/repair_group_leads.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/management/commands/retire_qa_accounts.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/management/commands/seed_staff_roster.py` | 1 | C — idarə əmrləri (prod kill-switch-li) |
| `apps/accounts/middleware.py` | 1 | D — ilk-giriş / sessiya qapısı |
| `apps/accounts/network_zone.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/retention.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/services/account_block_notice.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/services/registration.py` | 1 | C — qeydiyyat (org seçimi öncəsi) |
| `apps/accounts/services/rim/policy.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/_helpers/superadmin_inspector.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/auth/login.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/organization/invitations.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/profile/_sections/exam_rooms.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/profile/_sections/notifications.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/accounts/views/superadmin/exam_rooms.py` | 1 | C — superadmin / admin cross-org əməliyyatı |
| `apps/ai_assistant/retention.py` | 1 | D — dövri log saxlama süpürgəsi (yalnız müddət üzrə DELETE) |
| `apps/audit/views_filters.py` | 1 | C — superadmin audit görünüşü |
| `apps/exams/management/commands/mark_exam_halls.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/management/commands/purge_exam_attempt.py` | 1 | C — idarə əmri (--org + dəqiq --username + cəhd + --expect-exam-slug; dry-run defolt, prod kill-switch-li) |
| `apps/exams/management/commands/purge_trial_exam.py` | 1 | C — idarə əmri (--org + dəqiq --slug + --expect-title; dry-run defolt, prod kill-switch-li) |
| `apps/exams/management/commands/seed_demo_hierarchy.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/management/commands/seed_final_exam_demo.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/management/commands/seed_group_demo_data.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/management/commands/seed_room_monitor_demo.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/management/commands/seed_stress_exam_journal.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/management/commands/seed_stress_test.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/management/commands/sync_midterm_scores.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/management/commands/fix_exam_journal_gaps.py` | 1 | C — idarə əmri (--org + superadmin --actor; yalnız əlavə, dry-run defolt, idempotent) |
| `apps/exams/services/attempts.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/services/exam_network.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/services/final_center/reminders.py` | 1 | B — final mərkəzi PIN axını |
| `apps/exams/services/student_pin_hashing.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/services/student_pins.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/exams/services/sweep_guard.py` | 1 | C — imtahan mərkəzi / müəllim cross-org əməli |
| `apps/hr_contracts/management/commands/send_contract_reminders.py` | 1 | C — idarə əmrləri (--org / --dry-run) |
| `apps/hr_contracts/services/files.py` | 1 | D — commit-dən sonra yetim fayl təmizliyi (yol üzrə EXISTS) |
| `apps/hr_contracts/services/notify.py` | 1 | D — bildiriş alıcıları (açıq təşkilat süzgəcli üzvlük oxusu) |
| `apps/hr_contracts/tasks.py` | 1 | D — Celery (rls_worker_atomic; müqavilənin öz təşkilatı) |
| `apps/live_exam/cache.py` | 1 | B — public PIN/token girişi |
| `apps/live_exam/management/commands/seed_live_demo.py` | 1 | B — public PIN/token girişi |
| `apps/live_exam/poll_cache.py` | 1 | B — public PIN/token girişi |
| `apps/live_exam/socket_coordination.py` | 1 | B — public PIN/token girişi |
| `apps/live_exam/text_safety.py` | 1 | B — public PIN/token girişi |
| `apps/monitoring/security_ip.py` | 1 | C — superadmin monitorinq |
| `apps/notifications/management/commands/dedupe_notifications.py` | 1 | A — recipient-scoped bildiriş |
| `apps/notifications/retention.py` | 1 | A — recipient-scoped bildiriş |
| `apps/notifications/services/profile_state.py` | 1 | A — recipient-scoped bildiriş |
| `apps/notifications/services/queries.py` | 1 | A — recipient-scoped bildiriş |
| `apps/notifications/tasks.py` | 1 | A — recipient-scoped bildiriş |
| `apps/organizations/management/commands/apply_org_structure.py` | 1 | C — təşkilat idarəetməsi |
| `apps/organizations/management/commands/backfill_admin_memberships.py` | 1 | C — təşkilat idarəetməsi |
| `apps/organizations/management/commands/create_sample_orgs.py` | 1 | C — təşkilat idarəetməsi |
| `apps/organizations/management/commands/seed_ci_e2e_scenario.py` | 1 | C — təşkilat idarəetməsi |
| `apps/organizations/management/commands/seed_ci_e2e_user.py` | 1 | C — təşkilat idarəetməsi |
| `apps/organizations/services.py` | 1 | C — təşkilat idarəetməsi |
| `apps/registrar/management/commands/apply_journal_shares.py` | 1 | C — idarə əmri (bölünmüş jurnal payları; --actor superadmin, dry-run defolt, 2026-10-26) |
| `apps/registrar/management/commands/archive_junk_groups.py` | 1 | C — idarə əmrləri |
| `apps/registrar/management/commands/archive_non_program_rows.py` | 1 | C — idarə əmrləri |
| `apps/registrar/management/commands/backfill_teacher_lessons.py` | 1 | C — idarə əmrləri |
| `apps/registrar/management/commands/ensure_parent_groups.py` | 1 | C — idarə əmrləri |
| `apps/registrar/management/commands/import_timetable_docx.py` | 1 | C — idarə əmrləri |
| `apps/registrar/management/commands/merge_subjects.py` | 1 | C — idarə əmrləri |
| `apps/registrar/management/commands/report_duplicate_subjects.py` | 1 | C — idarə əmrləri |
| `apps/registrar/management/commands/seed_western_caspian.py` | 1 | C — idarə əmrləri |
| `apps/registrar/management/commands/undo_subject_merge.py` | 1 | C — idarə əmrləri |
| `apps/registrar/page_contexts.py` | 1 | D — tenant konteksti itmiş səhifə fallback-i (şərhli) |
| `apps/subject_folder/management/commands/subject_folder_digest.py` | 1 | C — idarə əmrləri |
| `apps/subject_folder/management/commands/subject_folder_similarity.py` | 1 | C — idarə əmrləri |
| `apps/subject_folder/management/commands/subject_folder_sync_journal.py` | 1 | C — idarə əmrləri |
| `apps/subject_folder/services/plagiarism/dispatch.py` | 1 | D — Celery/sinxron oxşarlıq (engine org süzgəcli) |
| `apps/surveys/management/commands/surveys_ensure_template.py` | 1 | C — idarə əmrləri |
| `apps/surveys/management/commands/surveys_notify_due.py` | 1 | C — idarə əmrləri |
| `apps/surveys/management/commands/surveys_open_campaign.py` | 1 | C — idarə əmrləri |
| `apps/surveys/management/commands/surveys_shuffle_responses.py` | 1 | C — idarə əmrləri |
| `apps/surveys/services/survey_buffer.py` | 1 | D — anonim cavab buferi köçürməsi (artıq icazəli sorğu id-si) |
| `apps/syllabus/management/commands/recompute_syllabus_completion.py` | 1 | C — idarə əmrləri |
| `apps/syllabus/management/commands/syllabus_repair_chair_units.py` | 1 | C — idarə əmrləri |
| `apps/timetable/tasks.py` | 1 | D — Celery (cədvəl generatoru, run sətrinin təşkilatı) |
| `apps/verification/lookup.py` | 1 | B — public sənəd yoxlaması (kod üzrə tək sətir) |
| `apps/workload/management/commands/assign_task_rows_from_timetable.py` | 1 | C — idarə əmrləri (--org ilə) |
| `apps/workload/management/commands/fix_task_row_hours.py` | 1 | C — idarə əmrləri (--org ilə) |
| `apps/workload/management/commands/import_teaching_load_form1.py` | 1 | C — idarə əmrləri (--org ilə) |
| `apps/workload/management/commands/import_teaching_task_workbook.py` | 1 | C — idarə əmrləri (--org ilə) |
| `apps/workload/management/commands/resync_task_offerings.py` | 1 | C — idarə əmrləri (--org ilə) |
| `apps/workload/management/commands/sync_plan_offerings.py` | 1 | C — idarə əmrləri (--org ilə) |
| `core/batch_purge.py` | 1 | D — infrastruktur |
| `core/moderation/enforcement.py` | 1 | D — infrastruktur |
| `core/rls_pooling.py` | 1 | D — infrastruktur |

**Cəmi:** 250 çağırış / 139 fayl · kateqoriya üzrə — A: 43, B: 47, C: 111, D: 49.

Yeni böyük istifadəçilər (2026-05-dən sonra): `apps/exams/tasks.py` (Celery —
sorğu konteksti yoxdur, job sətirləri `ExamExportJob`/`AIGenerationJob` org FK ilə
işləyir, D), `apps/exams/services/final_center/entry.py` + `views/student/final_center.py`
(public PIN axını, B), `apps/audit/views.py` (`_run_scoped` yalnız superadmin, C, şərhli),
`apps/monitoring/permissions.py` (superadmin, C), `apps/accounts/services/view_as.py`
(hədəf yoxlaması, C), `apps/notifications/services/read_state.py` (recipient-scoped, A).
Nümunə yoxlaması (audit `access` §5): hər yeni yerdə çağırışdan əvvəl
superadmin/credential/recipient yoxlaması var.

**RLS əhatəsi (CI):** `core/tests/test_audit_2026_09_13_rls_coverage.py` hər
`organization_id` sütunlu cədvəlin RLS siyasəti olduğunu yoxlayır (istisna:
`accounts_userprofile`, açıq siyahı ilə). `registrar_guestrosterdocument` (0069)
məhz belə test olmadığı üçün siyasətsiz qalmışdı — 0074 ilə bağlandı (F-05).

## Kateqoriyalar və risk dərəcəsi

### A — recipient/owner-scoped yazma və qlobal məzmun  → RİSK: AŞAĞI
Sorğu onsuz da `recipient=user` / `owner=user` kimi güclü, atlanmaz bir filtrlə
məhdudlaşdırılıb, VƏ YA məlumat qəsdən qlobaldır (blog).
- `notifications/services.py`, `notifications/views.py` — bildiriş həmişə bir
  konkret `recipient`-ə bağlıdır; bypass yalnız istifadəçinin öz inbox-unu
  bütün org-lar üzrə görməsi üçündür (FAZA 4-də sənədləşdirildi).
- `blog/services.py`, `post_management.py` — blog qəsdən qlobaldır, RLS-dən
  kənardadır (FAZA 3-də sənədləşdirildi).
- **Tövsiyə:** saxla. Bu nümunələr təhlükəsizdir, çünki `recipient`/`owner`
  yoxlaması RLS-dən asılı deyil.

### B — public canlı imtahan (PIN/token girişi)  → RİSK: AŞAĞI-ORTA
Canlı imtahana PIN/token ilə qoşulan istifadəçinin hələ tenant konteksti yoxdur
(login olmaya bilər). PIN/token özü kriptoqrafik giriş yoxlamasıdır.
- `live_exam/views/player.py`, `scoring.py`, `consumers.py`, `auth.py`.
- **Tövsiyə:** saxla, amma hər çağırışda yoxla ki, PIN/token doğrulaması
  bypass-dan ƏVVƏL baş verir. Şərh əlavə et: niyə bypass lazımdır.

### C — cross-org superadmin / admin əməliyyatı  → RİSK: ORTA
Superadmin və ya org-admin bilərəkdən tenant sərhədini keçir (idarəetmə paneli,
üzvlük sorğuları).
- `accounts/views/organization.py`, `_helpers.py`, `services/organization_requests.py`.
- **Tövsiyə:** hər çağırışda təsdiqlə ki, çağırışdan ƏVVƏL `is_superadmin` /
  rol-səviyyə yoxlaması var. Bypass-dan sonra sorğu nəticələri istifadəçiyə
  qaytarılmazdan əvvəl yenidən filtrlənməlidir.

### D — tenant kontekst qurma (middleware infrastrukturu)  → RİSK: AŞAĞI
`OrganizationMiddleware` və `core/tenancy.py` hələ tenant kontekst təyin
olunmamış mərhələdə istifadəçinin hansı org-lara aid olduğunu öyrənir.
- **Tövsiyə:** saxla. Bu, RLS sisteminin özünü qurması üçün zəruridir
  (yumurta-toyuq problemi).

## Ümumi tövsiyələr

1. **Hər `bypass_rls()` çağırışına bir sətirlik şərh əlavə et** — niyə lazımdır,
   hansı yoxlama onu təhlükəsiz edir. Hazırda əksəriyyətində şərh yoxdur.
2. **Yeni `bypass_rls` əlavə edəndə** bu sənədi yenilə və kateqoriyasını seç.
3. **Kateqoriya C-dəki çağırışlar** ən diqqətlə nəzərdən keçirilməlidir —
   FAZA 11 (test) onlar üçün cross-tenant sızıntı testləri əlavə etməlidir.
4. **Mümkün olan yerlərdə** `bypass_rls`-i daha dar `set_rls_tenant(other_org)`
   ilə əvəz et — bütün tenant-ları açmaqdansa konkret hədəf org-a keç.

## Nəticə

156 çağırışın (2026-09-13) 64-ü (kateqoriya A və D — ~41%) **təhlükəsizdir** —
recipient-scoped, qlobal məzmun, və ya infrastruktur. Əsas diqqət kateqoriya
C-dədir (59 çağırış, ~38%; B — public PIN/token — 33): superadmin/admin cross-org əməliyyatları. Onların hamısının
çağırışdan əvvəl rol yoxlaması olduğu FAZA 11 testləri ilə təsdiqlənməlidir.
