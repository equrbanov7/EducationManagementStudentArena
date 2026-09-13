# AUDIT — PERFORMANS · SORĞU BÜDCƏLƏRİ · NƏZARƏTLİ YÜK SINAĞI (slug `perf`)

Tarix: 2026-09-13 · Repo HEAD: `7c5dc612` (Develop) · Auditor: read-only (bu audit heç bir tracked faylı dəyişməyib; iş ağacındakı `docker/prometheus/alerts.yml` dəyişikliyi başqa agentindir)
Sandbox DB: `ems_audit_perf` (:55432) · Klon (yalnız SELECT/EXPLAIN): `emsarena_rehearsal_a0d170000901` (:55433) · Yük sınağı: yalnız dev-clone :8011

Əvvəlki sübutlar (təkrar edilməyib): `audit/exams/query_budget.json` (imtahan start/take/autosave/finish),
`audit/data/out/hot_queries.json` + `14_explain_hot.out` (7 isti səhifə + 9 EXPLAIN). Kabinet-shell memoizasiyası (Codex §14/§21) HEAD-də mövcuddur.

## 0. Xülasə

1. **Sorğu büdcəsi (§1):** 62 endpoint × 2 miqyas (SMALL 2 tələbə / FULL 150 tələbə, 12 açılış, 40 sual) — 58-i sabit; 4 N+1 (`group_students`, `group_individual_plan`, `teacher_group_list`, `appeal_stats_data`) + jurnal detalında 12 dublikat sillabus sorğusu + finish-də +1 sorğu/sual.
2. **Yük sınağı (§5):** dev-clone (DEBUG=False, klon DB) 5→20→50 VU, 30 s: **xəta 0**, p50 70–86 ms, p95 200/420/410 ms, p99 230/670/490 ms, 26 RPS; dayanma şərti işləmədi; darboğaz app prosesi (GIL, tək nüvənin ~60 %), DB boşdur.
3. **Tək-istifadəçi ağır səhifələr (klon):** `/exams/groups/` **2.0 s / 2.5 MB**, sillabus siyahısı 1.24 s, dərs jurnalı (lessons-log) 1.04 s, `/jurnal/` (rektor) 0.45 s — hamısı org-geniş rol üçün, hamısı sorğu forması/keş məsələsi (F-10/12/13/14).
4. **Paralellik (§5b):** eyni imtahanda 20 tələbə + eyni tələbədən 5 paralel start — itkisiz, dublikatsız. PASS.
5. **EXPLAIN (§6):** 10 sorğu; seq scan yalnız `registrar_lesson` tarix-aralığında (indeks təklifi `(organization_id, date)`), qalanı sorğu formasıdır (aqreqat-paginasiyadan-əvvəl, planner səhv təxmini, disk sort 4.7 MB). Klonda imtahan cəhdi 0 sətir → imtahan yolları real həcmdə NOT TESTED.
6. **Keş (§3):** tenant-namespaced açarlar, `noeviction`, invalidasiya qismən (badge/bank/switcher); ağır org-geniş hesablamalar keşsiz.
7. **Statik (§4):** 44 fayl / 709 KB xam / 165 KB gzip + FA font 146 KB; prod manifest+immutable+gzip_static düzgün; `jsi18n` hər səhifədə dinamik (83 KB).
8. **Çərçivə yükü:** hər səhifədə 10–15 təkrar sorğu (RLS `set_config` ×4–12, `access_state` ×3, `membership` ×3–5) — P3, amma bütün trafikə vurulur.
9. **P0/P1 yoxdur; P2 = 8, P3 = 8.** Ən böyük qazanc: F-10 (yönləndirmə, 1 sətir), F-14 (mövcud helper ilə), F-13 (keş), F-05 (bulk_create).
10. **Ballar:** Performans **72**, Miqyaslanma **64**, Redis/Keşləmə **70**.

## 1. Endpoint sorğu büdcəsi cədvəli (sandbox, CaptureQueriesContext)

**Metod.** `audit/perf/test_budget.py` — iki miqyas eyni kodla: SMALL = 1 fakültə · 1 qrup × 2 tələbə · 2 açılış · 5 sual · 2 dərs;
FULL = 2 fakültə · 6 qrup × 25 tələbə (150) · 12 açılış (6 qrup × 2 fənn) · 40 suallıq imtahan (hər qrupa StudentGroup ilə təyin) ·
5 dərs/açılış + qeydlər · 75 təqdim edilmiş cəhd · 5 apellyasiya · 15 bildiriş. Hər endpoint əvvəl 1 dəfə «isidilir», sonra
`CaptureQueriesContext` ilə ölçülür (LocMem keş, `config.settings.test`, sandbox `ems_audit_perf`). **N+1 meyarı:** FULL − SMALL ≥ 5 sorğu.
Wall-ms sandbox-dakı (DEBUG şablon render + kiçik DB) dəyərdir — mütləq deyil, nisbi müqayisə üçündür.
Nəticə faylları: `budget_small.json`, `budget_full.json`, `html/` (render olunmuş səhifələr).

**Qeyd (istisna edilənlər):** imtahan start/take/autosave/finish/result büdcəsi `audit/exams/query_budget.json`-dan götürülüb
(5→25 sual: start 51→48, take 32→32, autosave 27→27, finish **47→67** — finish sual sayı ilə +1/sual artır, bax §2 F-05).

| Endpoint (rol) | Status | Sorğu SMALL | Sorğu FULL | ms (FULL, wall) | SQL ms | N+1? | Ən ağır / təkrar sorğu |
|---|---|---|---|---|---|---|---|
| login_post_student | 200 | 11 | 11 | 19.9 | 5.0 | yox | 1.0 ms `SELECT "auth_user"."id", "auth_user"."password", "auth_user"."last_log…` |
| dashboard_student | 200 | 24 | 24 | 45.1 | 14.0 | yox | 4× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| dashboard_teacher | 200 | 31 | 31 | 51.2 | 14.0 | yox | 4× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| dashboard_dean | 200 | 33 | 33 | 103.3 | 52.0 | yox | 4× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| dashboard_owner | 200 | 36 | 36 | 69.4 | 32.0 | yox | 4× `SELECT SUM("workload_teacherassignment"."hours") AS "total" FROM "work…` |
| dashboard_exam_center | 200 | 29 | 29 | 44.6 | 12.0 | yox | 4× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| statistics_student | 200 | 21 | 21 | 41.8 | 17.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| statistics_teacher | 200 | 24 | 24 | 43.7 | 16.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| statistics_dean | 200 | 25 | 25 | 44.5 | 14.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| statistics_owner | 200 | 21 | 21 | 38.0 | 8.0 | yox | 1.0 ms `SELECT "auth_user"."id", "auth_user"."password", "auth_user"."last_log…` |
| statistics_exam_center | 200 | 23 | 23 | 35.0 | 8.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| people_students_owner | 200 | 21 | 21 | 75.0 | 19.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| people_students_dean | 200 | 25 | 25 | 66.6 | 21.0 | yox | 4× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| groups_registry_owner | 200 | 30 | 30 | 57.3 | 15.0 | yox | 4× `SELECT "organizations_orgunit"."created_at", "organizations_orgunit"."…` |
| people_teachers_owner | 200 | 21 | 21 | 37.9 | 8.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| org_members_owner | 200 | 24 | 24 | 29.1 | 8.0 | yox | 2.0 ms `SELECT "organizations_membership"."created_at", "organizations_members…` |
| org_dashboard_owner | 200 | 21 | 21 | 42.9 | 19.0 | yox | 2.0 ms `SELECT "organizations_membership"."created_at", "organizations_members…` |
| group_students_owner | 200 | 16 | 39 | 55.1 | 23.0 | **BƏLİ** | 26× `SELECT "organizations_orgunit"."created_at", "organizations_orgunit"."…` |
| courses_my_courses_teacher | 200 | 21 | 21 | 20.8 | 6.0 | yox | 2.0 ms `SELECT "organizations_membership"."created_at", "organizations_members…` |
| my_courses_teacher | 200 | 23 | 23 | 61.9 | 25.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| exam_list_teacher | 302 | 11 | 11 | 14.0 | 8.0 | yox | 2.0 ms `SELECT "organizations_membership"."created_at", "organizations_members…` |
| my_exams_teacher | 200 | 26 | 26 | 90.9 | 35.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| my_appeals_student | 200 | 25 | 25 | 63.1 | 22.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| exam_list_student | 200 | 34 | 34 | 67.0 | 30.0 | yox | 8.0 ms `SELECT DISTINCT "exams_exam"."id", "exams_exam"."author_id", "exams_ex…` |
| exam_detail_teacher | 200 | 26 | 26 | 43.5 | 15.0 | yox | 1.0 ms `SELECT "django_session"."session_key", "django_session"."session_data"…` |
| exam_results_teacher | 200 | 29 | 29 | 36.5 | 7.0 | yox | 1.0 ms `SELECT "organizations_membership"."created_at", "organizations_members…` |
| exam_history_student | 200 | 27 | 27 | 35.3 | 12.0 | yox | 2.0 ms `SELECT "exams_examattempt"."id", "exams_examattempt"."checked_by_teach…` |
| schedule_student | 200 | 34 | 34 | 56.1 | 24.0 | yox | 2.0 ms `SELECT "registrar_scheduleslot"."created_at", "registrar_scheduleslot"…` |
| schedule_teacher | 200 | 29 | 29 | 57.7 | 23.0 | yox | 4.0 ms `SELECT "registrar_scheduleslot"."created_at", "registrar_scheduleslot"…` |
| my_schedule_student | 200 | 37 | 37 | 64.6 | 23.0 | yox | 5× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| journal_list_teacher | 200 | 28 | 28 | 33.7 | 7.0 | yox | 2.0 ms `SELECT "registrar_courseoffering"."created_at", "registrar_courseoffer…` |
| journal_detail_teacher | 200 | 71 | 71 | 333.1 | 149.0 | yox | 12× `SELECT "syllabus_syllabus"."created_at", "syllabus_syllabus"."updated_…` |
| my_journal_student | 200 | 37 | 37 | 79.1 | 34.0 | yox | 5× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| my_subjects_student | 200 | 37 | 37 | 76.2 | 27.0 | yox | 5× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| my_transcript_student | 200 | 37 | 37 | 69.0 | 25.0 | yox | 5× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| transcript_pdf_student | 404 | 12 | 12 | 17.3 | 9.0 | yox | 2.0 ms `SELECT "accounts_userprofile"."id", "accounts_userprofile"."user_id", …` |
| journal_analytics_owner | 200 | 21 | 21 | 25.1 | 9.0 | yox | 1.0 ms `SELECT 1 AS "a" FROM "accounts_userprofile" WHERE ("accounts_userprofi…` |
| lessons_log_owner | 200 | 29 | 29 | 66.5 | 18.0 | yox | 4.0 ms `SELECT "registrar_lesson"."created_at", "registrar_lesson"."updated_at…` |
| notifications_list_student | 200 | 29 | 29 | 58.4 | 31.0 | yox | 16.0 ms `SELECT "notifications_inappnotification"."id", "notifications_inappnot…` |
| notifications_section_student | 200 | 26 | 26 | 40.0 | 9.0 | yox | 2.0 ms `SELECT COUNT(*) FROM (SELECT DISTINCT "exams_exam"."id" AS "col1", "ex…` |
| notifications_unread_count | 200 | 15 | 15 | 14.7 | 7.0 | yox | 1.0 ms `SELECT "django_session"."session_key", "django_session"."session_data"…` |
| applications_owner | 200 | 30 | 30 | 55.3 | 18.0 | yox | 5× `SELECT COUNT(*) FROM (SELECT DISTINCT "applications_application"."crea…` |
| applications_student | 200 | 32 | 32 | 61.9 | 22.0 | yox | 5× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| workload_distribution_owner | 200 | 23 | 23 | 41.1 | 15.0 | yox | 1.0 ms `SELECT "django_session"."session_key", "django_session"."session_data"…` |
| workload_overview_owner | 200 | 24 | 24 | 38.9 | 11.0 | yox | 1.0 ms `SELECT 1 AS "a" FROM "accounts_userprofile" WHERE ("accounts_userprofi…` |
| syllabus_list_teacher | 200 | 27 | 27 | 58.8 | 20.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| academic_records_owner | 200 | 25 | 25 | 58.0 | 20.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| records_overview_data_owner | 200 | 26 | 26 | 75.5 | 39.0 | yox | 13.0 ms `SELECT "registrar_studentacademicrecord"."created_at", "registrar_stud…` |
| pin_search_ec | 200 | 12 | 12 | 23.0 | 9.0 | yox | 2.0 ms `SELECT "organizations_membership"."created_at", "organizations_members…` |
| exam_center_pins_ec | 200 | 22 | 22 | 34.4 | 7.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| ec_rooms_ec | 200 | 25 | 25 | 35.7 | 20.0 | yox | 1.0 ms `SELECT "django_session"."session_key", "django_session"."session_data"…` |
| appeals_manage_ec | 302 | 11 | 11 | 19.1 | 9.0 | yox | 2.0 ms `SELECT 1 AS "a" FROM "accounts_userprofile" WHERE ("accounts_userprofi…` |
| appeals_manage_teacher | 403 | 12 | 12 | 18.3 | 10.0 | yox | 2.0 ms `SELECT "auth_user"."id", "auth_user"."password", "auth_user"."last_log…` |
| appeals_my_student | 302 | 11 | 11 | 8.4 | 2.0 | yox | 1.0 ms `SELECT "django_session"."session_key", "django_session"."session_data"…` |
| manage_appeals_section_ec | 200 | 27 | 27 | 57.2 | 18.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| grading_queue_teacher | 200 | 27 | 27 | 34.1 | 15.0 | yox | 1.0 ms `SELECT "django_session"."session_key", "django_session"."session_data"…` |
| pending_answers_teacher | 302 | 13 | 13 | 14.6 | 7.0 | yox | 1.0 ms `SELECT 1 AS "a" FROM "accounts_userprofile" WHERE ("accounts_userprofi…` |
| assigned_exams_student | 200 | 29 | 29 | 44.9 | 13.0 | yox | 3.0 ms `SELECT DISTINCT "exams_exam"."id", "exams_exam"."author_id", "exams_ex…` |
| my_results_student | 200 | 40 | 40 | 73.6 | 28.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| audit_log_owner | 200 | 27 | 27 | 89.5 | 31.0 | yox | 3.0 ms `SELECT "audit_auditlog"."id", "audit_auditlog"."user_id", "audit_audit…` |
| org_structure_owner | 200 | 26 | 26 | 41.9 | 16.0 | yox | 3× `SELECT "organizations_orgunit"."created_at", "organizations_orgunit"."…` |
| profile_info_student | 200 | 37 | 37 | 53.7 | 15.0 | yox | 5× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| people_list_students_owner | 200 | 15 | 15 | 24.6 | 13.0 | yox | 5.0 ms `SELECT "auth_user"."id", "auth_user"."password", "auth_user"."last_log…` |
| people_list_students_p100_owner | 200 | 15 | 15 | 34.2 | 19.0 | yox | 12.0 ms `SELECT "auth_user"."id", "auth_user"."password", "auth_user"."last_log…` |
| people_list_students_dean | 200 | 18 | 18 | 42.0 | 22.0 | yox | 7.0 ms `SELECT "auth_user"."id", "auth_user"."password", "auth_user"."last_log…` |
| people_list_teachers_owner | 200 | 13 | 13 | 24.7 | 14.0 | yox | 3.0 ms `SELECT "auth_user"."id", "auth_user"."password", "auth_user"."last_log…` |
| people_options_students_owner | 200 | 20 | 20 | 36.8 | 18.0 | yox | 3.0 ms `SELECT COUNT("auth_user"."id") FILTER (WHERE ("auth_user"."is_active" …` |
| people_analytics_students_owner | 200 | 18 | 18 | 50.3 | 24.0 | yox | 5.0 ms `SELECT "registrar_studentacademicrecord"."status" AS "status", COUNT("…` |
| people_student_card_owner | 200 | 20 | 20 | 31.2 | 14.0 | yox | 2.0 ms `SELECT "registrar_enrollment"."created_at", "registrar_enrollment"."up…` |
| people_detail_owner | 200 | 33 | 33 | 44.6 | 16.0 | yox | 3× `SELECT "registrar_studentacademicrecord"."created_at", "registrar_stud…` |
| people_academic_groups_owner | 200 | 12 | 12 | 14.6 | 5.0 | yox | 1.0 ms `SELECT 1 AS "a" FROM "accounts_userprofile" WHERE ("accounts_userprofi…` |
| workload_rows_owner | 200 | 11 | 11 | 9.2 | 2.0 | yox | 1.0 ms `SELECT "organizations_membership"."created_at", "organizations_members…` |
| workload_options_owner | 403 | 11 | 11 | 22.1 | 11.0 | yox | 3.0 ms `SELECT "organizations_membership"."created_at", "organizations_members…` |
| workload_teachers_owner | 403 | 11 | 11 | 14.5 | 7.0 | yox | 1.0 ms `SELECT "django_session"."session_key", "django_session"."session_data"…` |
| section_fragment_dashboard_owner | 200 | 36 | 36 | 65.2 | 35.0 | yox | 4× `SELECT SUM("workload_teacherassignment"."hours") AS "total" FROM "work…` |
| section_fragment_statistics_owner | 200 | 21 | 21 | 28.4 | 10.0 | yox | 2.0 ms `SELECT "organizations_membership"."created_at", "organizations_members…` |
| section_fragment_people_students_owner | 200 | 21 | 21 | 30.8 | 14.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| badges_api_owner | 200 | 18 | 18 | 17.3 | 6.0 | yox | 3× `SELECT "organizations_membership"."created_at", "organizations_members…` |
| global_search_owner | 200 | 14 | 14 | 30.5 | 12.0 | yox | 3.0 ms `SELECT "registrar_studentacademicrecord"."created_at", "registrar_stud…` |
| group_student_candidates_owner | 200 | 14 | 14 | 16.5 | 5.0 | yox | 2.0 ms `SELECT "registrar_studentacademicrecord"."created_at", "registrar_stud…` |
| structure_faculties_owner | 200 | 29 | 29 | 26.3 | 5.0 | yox | 2.0 ms `SELECT "organizations_membership"."created_at", "organizations_members…` |
| records_overview_summary_owner | 200 | 11 | 11 | 8.4 | 1.0 | yox | 1.0 ms `SELECT "organizations_membership"."created_at", "organizations_members…` |
| exam_center_stats_data_ec | 200 | 23 | 23 | 35.1 | 12.0 | yox | 4.0 ms `SELECT DISTINCT "exams_examattempt"."id", "exams_examattempt"."checked…` |
| appeal_stats_data_ec | 200 | 19 | 27 | 25.3 | 7.0 | **BƏLİ** | 5× `SELECT "exams_studentgroup"."id", "exams_studentgroup"."teacher_id", "…` |
| teacher_exam_statistics | 200 | 26 | 26 | 34.3 | 11.0 | yox | 1.0 ms `SELECT "organizations_membership"."created_at", "organizations_members…` |
| teacher_pending_attempts | 200 | 21 | 21 | 39.3 | 7.0 | yox | 1.0 ms `SELECT "django_session"."session_key", "django_session"."session_data"…` |
| question_bank_list_teacher | 302 | 11 | 11 | 9.4 | 3.0 | yox | 1.0 ms `SELECT "django_session"."session_key", "django_session"."session_data"…` |
| teacher_group_list | 200 | 38 | 48 | 109.5 | 47.0 | **BƏLİ** | 12× `SELECT "exams_studentgroup"."id", "exams_studentgroup"."teacher_id" FR…` |
| journal_xlsx_teacher | 200 | 37 | 37 | 63.8 | 16.0 | yox | 2.0 ms `SELECT "registrar_studentacademicrecord"."created_at", "registrar_stud…` |
| group_individual_plan_owner | 200 | 19 | 65 | 157.4 | 43.0 | **BƏLİ** | 26× `SELECT "organizations_academicperiod"."created_at", "organizations_aca…` |

**Oxunuş.**
- 62 səhifə/endpoint-dən **58-i miqyasdan asılı deyil** (SMALL = FULL) — 2026-09-10 və Codex düzəlişləri (tələbə imtahan siyahısı, üzv reyestri, kataloq, jurnal) təsdiqlənir. Tələbə/müəllim kataloqu (`people_list`, 25 və 100 sətir) 15 sorğu — sabit. Jurnal detalı 71 sorğu — sabit, amma mütləq say yüksəkdir (12× eyni `syllabus_syllabus` SELECT-i, §2 F-04).
- **N+1 (FULL-da artan) — 4 endpoint:** `organizations:group_students` 16→39 (26× `organizations_orgunit` SELECT — hər tələbə üçün qrup), `registrar:group_individual_plan` (.docx) 19→65 (26× `academicperiod` + 25× `curriculumsubject`), `exams:teacher_group_list` 38→48 (12× `exams_studentgroup` — hər qrup üçün 2 sorğu), `appeals:appeal_stats_data` 19→27 (hər apellyasiya üçün `studentgroup` + `COUNT(appealitem)`). Bax §7 F-01…F-03, F-06.
- **Ağır tək sorğu:** `exams:student_exam_list` 34 sorğu, amma SQL 274 ms (sandbox!) — `SELECT DISTINCT exams_exam.* … 4 sub-plan` 100 ms + `COUNT(DISTINCT) FILTER ×4` 73 ms; klonda EXPLAIN: icra 1.1 ms, **planlama 9.2 ms** (data agentinin H5-i). Geniş DISTINCT + 4 korrelyasiyalı subplan — §6.
- **Çərçivə yükü (hər sorğuda):** `SELECT set_config(app.current_org_id…)` 4–10 dəfə + `SELECT current_setting(…)` 3–5 dəfə + `accounts_userprofile.access_state` yoxlaması 3 dəfə + `organizations_membership` SELECT 3–5 dəfə — hər səhifədə ~10–15 «boş» round-trip (§7 F-07, F-08).
- Yönləndirmələr (302): `exams:teacher_exam_list`, `appeals:manage_appeals`, `appeals:my_appeals`, `accounts:pending_answers`, `exams:question_bank_list` — köhnə URL-lər kabinet bölmələrinə yönləndirir (11 sorğu = auth + RLS + yönləndirmə). `registrar:my_transcript_pdf` 404 (tələbədə final qiymət/transkript şərti yoxdur — fixture məhdudiyyəti, NOT TESTED).

## 2. ORM nümunələri — N+1 / select_related / paginasiyasız inventar

**Metod.** `orm_scan.py` (AST: `for`/comprehension gövdəsində `.objects.get/filter/exists/count/first/aggregate/values…`) → 91 hit
(`orm_loop_hits.json`), onlardan legacy-import/monitoring/management/yazı-yolu (create/get_or_create toplu əməliyyatlar) çıxıldıqda
oxu yolunda qalan namizədlər aşağıda; hər biri §1 ölçüsü və ya `test_trace.py` (execute_wrapper + Python stack) ilə təsdiqlənib/rədd edilib.

### 2.1 Təsdiqlənmiş N+1 (oxu yolu)

| # | Yer | Nümunə | Ölçü (SMALL→FULL) | Sev. |
|---|---|---|---|---|
| F-01 | `apps/organizations/group_students.py:48` `_row()` → `record.group.name`; queryset `:91-95` `select_related("student","program")` — `group` yoxdur | hər tələbə üçün `SELECT organizations_orgunit … WHERE id=?` | `organizations:group_students` 16→39 (25 tələbə = +25 sorğu; stack: `group_students.py:100 → :48`) | P2 |
| F-02 | `apps/exams/forms/group.py:190-195` — `Prefetch("student_groups"/"student_groups_as_teacher", queryset=StudentGroup….only("id","name","organization_id"))`: tərs-FK prefetch-in uyğunlaşdırma açarı `teacher_id` `.only()`-də yoxdur → Django hər qrup üçün `refresh_from_db(fields=["teacher_id"])` atır (`related_descriptors.py:802 get_prefetch_querysets → query_utils.py:270 DeferredAttribute`) | `SELECT id, teacher_id FROM exams_studentgroup WHERE id=? LIMIT 21` × (qrup sayı × 2 sahə) | `exams:teacher_group_list` 38→48 (6 qrup → 12 sorğu; klonda qrup sayı qədər ×2) | P2 |
| F-03 | `apps/registrar/individual_plan.py:191-213` `build_student_plan()` — hər tələbə üçün `_season_periods(organization, raw_year)` (AcademicPeriod) + `CurriculumSubject.objects.filter(curriculum=record.curriculum, semester_number__in=…)`; eyni qrup/eyni kurikulum → eyni nəticə | 2 sorğu × tələbə | `registrar:group_individual_plan` (.docx) 19→65 (25 tələbə = +46) | P3 |
| F-06 | `apps/appeals/views/teacher/statistics.py:188-210` `_row()` — `exam.allowed_groups.all()` + `appeal.items.count()` hər apellyasiya üçün; `_filtered_appeals` (`:103`) `select_related` var, `prefetch_related("exam__allowed_groups")`/`annotate(Count("items"))` yoxdur | 2 sorğu × sətir (səhifə 15 → ≤30) | `appeals:appeal_stats_data` 19→27 (5 apellyasiya = +8) | P3 |
| F-05 | `apps/exams/views/student/attempts.py:264-283` — finish/autosave döngüsündə `ExamAnswer.objects.get_or_create(attempt, question)` cavabı olmayan hər sual üçün (`answers_by_qid` boşdursa) | +1 sorğu/sual | `audit/exams/query_budget.json`: finish 47 (5 sual) → 67 (25 sual) — **+1/sual**; 40 suallıq imtahanda ~85 sorğu, 5000 tələbə eyni dəqiqədə təqdim edəndə DB-yə 400k+ kiçik sorğu | P2 |

### 2.2 Təkrarlanan (dublikat) sorğular — eyni request-də eyni SQL

| # | Yer | Nümunə | Ölçü | Sev. |
|---|---|---|---|---|
| F-04 | `apps/syllabus/services/offerings.py:60-87` `syllabus_for_offering()` — 3 pilləli axtarış, hər pillə ayrı `.first()`; jurnal detalı onu 4 yerdən çağırır (`registrar/syllabus_notice.py:114`, `journal_topics.py:37`, `journal_policy.py:104`, `public.py:462`) → sillabus olmayan açılışda 4×3 = **12 eyni sorğu** (hər biri 6 cədvəllik `select_related`, sandbox-da 9 ms) | `registrar:journal_detail` 71 sorğunun 12-si; SQL 163 ms-in ~60 ms-i | P2 |
| F-07 | RLS tenant set-up: `core/rls.py:182/253-258` → `SELECT set_config(app.current_org_id…)` + `SELECT current_setting(…)` **hər `set_rls_tenant`/`rls_worker_atomic` çağırışında** — middleware (`organizations/middleware.py:150,321,350,370`) + `notifications/services/read_state.py:74` (naviqasiya badge-i, 2-3 dəfə) | səhifədə 4–12 `set_config` + 1–5 `current_setting` round-trip (§1 dup sütunu; `trace_origins.txt`) | P3 |
| F-08 | `accounts_userprofile.access_state` yoxlaması 3 dəfə: `apps/accounts/backends.py:68` (auth backend `get_user`), `core/middleware.py:183`, `apps/accounts/context_processors.py:35` (view_as) — hər biri ayrıca `SELECT 1 … LIMIT 1` | 3 sorğu/səhifə (hər səhifədə) | P3 |
| F-09 | `organizations_membership` tam sətir SELECT-i 3–5 dəfə: `accounts/middleware.py:96`, `organizations/scoping.py:224` (`get_permission_scope` hər çağırışda), `registrar/journal_access.py:96/126`, `guest_roster.py:133`, `profile/context_builder/builder.py:34/56` | 3–5 sorğu/səhifə; kabinet-shell memoizasiyası (Codex §14) `request` səviyyəsində hamısını əhatə etmir | P3 |
| — | `section_fragment_dashboard_owner`: `apps/workload/services/queries.py:231-234` 4 ayrı `SUM(hours)` (4 status üçün) → tək `aggregate(… filter=Q(status=…))` | 4→1 | P3 |

### 2.3 Rədd edilən / nəzarətdə olan namizədlər (PASS)
- `apps/accounts/services/statistics_selectors/teacher.py:175-181` — `groups_qs[:50]` döngüsündə `ExamAttempt.filter(user__in=grp.students.all())`: `prefetch_related("students")` var, lakin `user__in=<prefetched qs>` **yenə subquery kimi SQL-ə gedir** (prefetch keşi `__in`-də istifadə olunmur) → 1 sorğu/qrup (≤50). §1: `statistics_teacher` 24 sorğu, fixture-da 6 StudentGroup (exam content-type filtri ilə passiv) — klonda müəllim statistikası üçün ≤50 əlavə sorğu. Kiçik fix: `user_id__in=[s.id for s in grp.students.all()]`. P3 (qeyd).
- `apps/exams/views/teacher/statistics.py:283-296` — eyni naxış (`compare_group_ids`, istifadəçi seçdiyi qruplar, adətən ≤5). PASS.
- `people_list` (tələbə/müəllim kataloqu) 25 və 100 sətir: 15 sorğu sabit — PASS (2026-09-10 P1-7 təsdiq).
- `members_registry`, `groups_registry`, `catalog`, `journal_list` (20/səhifə), `audit_log` (25), `notifications` (15), `my_exams` (12), `appeal_stats` (15), `handover_history` (20): hamısı `Paginator`/limit ilə — PASS.
- `len(queryset)`/`.count() > 0`/`if qs.count():` antipattern-ləri: `grep` — 2 hit, hər ikisi kiçik (`exams/services/randomizer.py:349` seçilmiş sual siyahısı; `exams/services/utils.py:33`). PASS.

### 2.4 Paginasiyasız render (tenant ölçülü cədvəl)
| Yer | Nə render olunur | Qiymət |
|---|---|---|
| `exams:teacher_group_list` (`/exams/groups/`, `apps/exams/views/teacher/groups.py:176-192`) — `_group_form_for_request` **`defer_choices` OLMADAN** | Formanın `students` seçicisi təşkilatın BÜTÜN tələbələrini (`students_qs` + 2 Prefetch), `primary_teacher`/`assigned_teachers` bütün müəllimləri `<option>` kimi render edir. Kabinet bölməsi (`accounts/views/profile/_sections/groups.py:46`) `defer_choices=True` ilə düzəldilib (2026-09-02 F4), köhnə tam səhifə isə **düzəldilməyib** və `teacher_create_group`/`teacher_update_group` `next` olmadan ora yönləndirir (`:266`). Naviqasiyada link yoxdur. Klon (7 700 tələbə): §5-də ölçülüb. | P2 (F-10) |
| `registrar:journal_detail` grid | açılışın bütün tələbələri × bütün dərslər (FULL: 25 × 5) — struktur olaraq məhdud (qrup ölçüsü), paginasiya tələb olunmur | PASS |
| `registrar:group_individual_plan` | qrupun bütün tələbələri (docx) — məhdud | PASS |

## 3. Keşləmə (core/cache.py, Redis DB indeksləri, invalidasiya)

**Redis topologiyası** (`config/settings/components/celery_cache.py`, `docker-compose.prod.yml:312-333`): DB0 = Channels (WS fan-out), DB1 = Django cache
(`RedisCache`, socket timeout 2 s, max_connections 100) + **sessiyalar** (`cached_db`) + rate-limit + imtahan-start/request-queue kilidləri, DB2 = Celery broker + nəticələr.
`maxmemory 3gb` + **`noeviction`** (Codex P2-08 düzəlişi) — limitə çatanda `cache.set` xəta verir (helper-lər `try/except` ilə tolerant), amma **sessiya yazısı** (`cached_db`) da eyni DB1-dədir: cache-i dolduran bir açar ailəsi sessiya yazılarını da bloklayar. Lokal/dev (`USE_REDIS=False`): LocMem + DB sessiyaları (klon serveri belədir).

| Keş | Açar | Tenant/istifadəçi namespace | TTL | Yazıda invalidasiya | Stampede | Qiymət |
|---|---|---|---|---|---|---|
| Statistika (`core/cache.py:159-236` `get_or_set_cached_statistics`) | `emsarena:accounts:statistics:v2:<profile>:<scope_id>:<md5(filters)>`; org_admin → `org.pk`; unit-scoped → `org.pk:user.pk` + `units` siyahısı (Codex P1-06) | ✅ org + (unit-scoped) user | 180 s | ❌ yalnız TTL (bal/qeyd/cəhd yazıları invalidasiya etmir — sənədləşdirilmiş «kiçik köhnəlmə») | get→compute→set, kilid yoxdur; org-geniş açar bir neçə admin arasında paylaşılır → eyni anda açanda çox-hesab (compute 20–50 sorğu). Risk aşağı-orta | PARTIAL |
| Profil badge sayğacları (`:254-294`) | `…profile_badges:<user>:<org>` | ✅ | 45 s | ✅ applications notify, attempt grants, chair review (`invalidate_profile_badge_counts_cache` 3 çağıran) — bildiriş/gözləyən cavab yazıları invalidasiya etmir (45 s köhnəlmə) | per-user | PASS |
| Bank analizi (`:303-329`) | `…bank_analysis:<bank>:<lang>:<fingerprint>` | ✅ (bank id) | 900 s | ✅ məzmun barmaq izi (P1-6) | per-bank | PASS |
| Org switcher (`organizations/middleware.py:50-70`) | `…org_switcher:<user>` | ✅ user | 60 s | ✅ `Membership` post_save/delete siqnalı (`signals.py:65-74`) | — | PASS |
| Akademik qeydlər (`accounts/academic_records_cache.py`) | `scope_key(org, scope, filters)` → summary/count | ✅ org+scope | 300 s | ❌ TTL | — | PARTIAL |
| Jurnal analitikası (`registrar/analytics_cache.py`) | `analytics_cache_key(org, period, scope_q)` | ✅ | 300 s | ❌ TTL | — | PARTIAL |
| Signup lookup (`core/cache.py:185-213`) | qlobal | n/a | 600 s | ✅ Organization/Country siqnalı | — | PASS |
| Blog selectors (`blog/selectors.py`) | qlobal (kateqoriya ağacı, navbar) | n/a (tenant-siz modul) | 120–300 s | ✅ siqnal | — | PASS |
| Live-exam session settings/question ids/metadata (`core/cache.py:72-146`) | pk-əsaslı | ✅ | 120/300/600 s | ✅ `invalidate_*` | — | PASS |
| Kilidlər: `exams/services/attempts.py:95-126` (exam-start actor lease), `core/middleware.py:255-273` (request-queue token), `student_pins` rate, `coding_throttle` | actor/exam açarı | ✅ | lease | `cache.add` + token müqayisəsi ilə düzgün buraxma | — | PASS |
| Kabinet-shell memoizasiyası (Codex §14/§21, HEAD-də) | request-scoped | — | — | — | — | PASS (§1: dashboard 24–36 sorğu, sabit) — lakin F-07/F-08/F-09 göstərir ki, middleware/backend/context-processor qatları hələ də 8–15 təkrar sorğu atır |

**Nəticə:** açarlar tenant-namespaced (keçmiş P1-06 sızması bağlı), TTL-lər qısa; yazıda invalidasiya yalnız badge/bank/switcher-də var — statistika/analitika/akademik qeydlər «3–5 dəq köhnəlmə» siyasəti ilə işləyir (qəbul edilən, sənədləşdirilib). Stampede mühafizəsi (lock/`cache.add`) yalnız kilid ssenarilərində; dashboard hesablamaları üçün yoxdur — 5000 tələbənin eyni anda statistika açması ehtimalı azdır (tələbə statistikası per-user açar: `scope_id=user.pk`? — `_compute_dashboard`-da tələbə profili `role=v2:student`, `scope_id=user.pk` → per-user, stampede yox, amma keşin faydası da yalnız təkrar açılışda).

## 4. Statik aktivlər (base.html çəkisi, cache-busting, gzip, defer)

**Ölçü** (`templates/base.html`-dəki 44 `{% static %}` istinadı, `static/` diskdən, gzip-6 ilə hesablanmış — `python` skript, faktiki nginx `gzip_static` eyni nisbətdədir):

| Göstərici | Dəyər | Qeyd |
|---|---|---|
| Qlobal fayl sayı | **44** (20 CSS + 24 JS) | əvvəlki audit: 43 / 699 KB → indi 44 / **709 KB xam, 165 KB gzip** |
| Ən ağır | `vendor/bootstrap/css/bootstrap.min.css` 227 KB (30 KB gz) · `vendor/fontawesome/css/all.min.css` 100 KB (22 KB gz) · `bootstrap.bundle.min.js` 78 KB (23 KB gz) | Bootstrap tam; FA tam CSS (353 fərqli `fa-*` sinfi istifadə olunur → subset asan deyil) |
| FA webfont | `fa-solid-900.woff2` 146 KB (hər səhifə), `fa-regular-400` 24 KB, `fa-brands-400` 105 KB (yalnız 1 şablonda `fab` → lazımi səhifədə yüklənir), `fa-v4compatibility` 4 KB | `font-display` FA-nın öz CSS-ində `block` (default) — FOIT riski; `preload` yoxdur |
| Cache-busting | Prod: `whitenoise.storage.CompressedManifestStaticFilesStorage` (`production.py:388`) → hash-lı ad + nginx `/static/ expires 30d, Cache-Control public, immutable, gzip_static on` (`docker/nginx/nginx.conf:91-95`) ✅. Şablondakı 35 `?v=YYYYMMDD` suffiksi prod-da artıqdır (zərərsiz), dev-də (`StaticFilesStorage`) yeganə busting mexanizmidir — **əl ilə** yenilənir (`pagination.css`, `ai_assistant.css`, `skeleton.css`, `search_controls.js`, `footer_year.js` suffikssizdir → dev/klon brauzerində köhnə keş riski, prod-a təsir etmir) | PASS (prod) / PARTIAL (dev) |
| Sıxılma | nginx `gzip on` (level 5, min 1 KB, css/js/json/svg) + `gzip_static` — **brotli yoxdur** (`nginx:alpine` brotli modulu yoxdur); HTTP/2 açıq (`:57`) | PASS (gzip) |
| Render-bloklayan | `<head>`-də 3 sinxron skript (`ems_early.js` 1 KB, `searchable_select_keys.js`, `searchable_select.js` 21 KB) — qəsdən (EMSReady stub + widget ilkinləşmə, QA 2026-09-05 P1-1). Body sonunda 21 skript, yalnız `pagination.js` `defer`; `javascript-catalog` (`{% url 'javascript-catalog' %}`) — **dinamik Django view, hər səhifədə** (`Cache-Control: private, no-store` `nginx.conf:134` proxy qatı üçün) → hər səhifə yükündə ~1 əlavə app sorğusu + JS kataloqu render | P3 (F-11) |
| Dublikat kitabxana | Bootstrap 1 nüsxə, jQuery yoxdur, FA 1 nüsxə; `bootstrap_select.js` (öz komponent) + `searchable_select.js` (öz) — funksional üst-üstə düşmə var, lakin ayrı rollar (sənədləşdirilib) | PASS |
| Şəkillər | base.html-də yalnız SVG/logo (`navbar_brand`); tələbə avatarları `accounts:profile_avatar` view-dan (`?v=`) — ayrıca yoxlanmayıb | NOT TESTED |

**Nəticə:** prod statik boru xətti düzgündür (manifest hash + immutable + gzip_static + HTTP/2). Qalan yük: 165 KB gzip CSS/JS + 146–170 KB font hər ilk açılışda; keşdən sonra yalnız HTML + `javascript-catalog` (dinamik). Kritik düzəliş yoxdur.

## 5. Nəzarətli yük sınağı (dev-clone :8011)

**Hədəf/metod.** `emsarena-dev-clone` (`.claude/launch.json`): `manage.py runserver 8011 --noreload`, `config.settings.local`, `.env`-dən **`DEBUG=False`**,
`USE_REDIS=False` (LocMem keş, DB sessiyaları), DB = klon `emsarena_rehearsal_a0d170000901` (:55433, 8 644 istifadəçi, 150k enrollment). Eyni maşında
(11 nüvə) locust 2.43 headless: `locustfile_perf.py` — hər VU bir dəfə portal-a görə login (`/accounts/login/telebe/` | `/muellim/`), sonra dövri GET:
dashboard → imtahan siyahısı → jurnal → statistika → bildirişlər, `wait_time 1–3 s`. Hesab hovuzu: 9 işləyən QA hesabı (`qa.student ×3 slot, qa.teacher ×2,
qa.dean, qa.rector, qa.chair_head, qa.tutor, qa.program_coordinator, qa.ikt_rehber, qa.exam_center_head`; `qa.sec.*`, `qa.lead_student`, `qa.exam_center`, `qa.teaching_office_*`, `qa.student_services` parolu qəbul etmir → hovuzdan çıxarıldı). Mərhələlər ayrıca 30 s çağırış: 5 → 20 → 50 VU
(`-r` 5/10/10). Dayanma şərti (xəta > 1 % və ya p95 > 3 s) heç bir mərhələdə baş vermədi → 50 VU limitinə qədər gedildi. **Bu, production throughput deyil:** tək-proses
runserver (thread-per-request, GIL), lokal Postgres, eyni maşında locust; prod = Daphne (1 proses, `ASGI_THREADS=12`) + PgBouncer + nginx.

| Mərhələ | VU | Sorğu | Xəta | avg | p50 | p90 | p95 | p99 | max | RPS | Server |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5 | 83 | 0 (0 %) | 85 ms | 70 | 180 | 200 | 230 | 231 | 2.9 | CPU ~5 % |
| 2 | 20 | 314 | 0 (0 %) | 137 ms | 82 | 360 | 420 | 670 | 877 | 10.8 | — |
| 3 | 50 | 759 | 0 (0 %) | 134 ms | 86 | 320 | 410 | 490 | 562 | 26.1 | app proses **55–68 % (1 nüvə)**, PG aktiv bağlantı ≤4 (cəmi ≤19) |

Endpoint üzrə (50 VU, p50/p95 ms): login_post **320/410** (parol hash — gözlənilən), staff:dashboard 160/390, staff:journal 120/490, teacher:dashboard 160/380,
student:dashboard 120/350, student:exam_list 80/150, *:statistics 60–70/120–140, *:notifications 40–50/95–140 (`load/stage50_stats.csv`).

**Darboğaz qiymətləndirməsi.** 50 VU-da DB demək olar boşdur (≤4 aktiv sorğu, hər səhifə 20–40 qısa sorğu); app prosesi tək nüvənin ~60 %-ində — yəni bu konfiqurasiyada
tavan ~40–45 RPS (GIL) olardı; 50 VU × 1–3 s düşünmə vaxtı onu doldurmur. p95-in 400 ms-ə çıxması növbə/GIL gözləməsidir (tək-istifadəçi eyni səhifələr 50–160 ms). Prod
Daphne 12 thread-lik sync hovuzu ilə eyni GIL sərhədinə tabedir → **1 replika ≈ 30–45 RPS səhifə yükü**; 5000 tələbənin eyni 10 dəqiqədə login-i (8/s × ~0.3 s CPU hash) tək
replikanın CPU-sunun ~2.5 nüvəsini tələb edir → `APP_REPLICAS ≥ 3` (compose «scale-ready» qeyd olunub, defolt 1). Codex-in 5 VU/783 ms p95 (DEBUG runserver) nəticəsi ilə
müqayisədə DEBUG=False klonda 5 VU p95 200 ms.

**Tək-istifadəçi ağır səhifələr (klon, `sweep.sh`, `load/sweep_rector.txt`):**

| Səhifə (rol) | Vaxt | Ölçü | Səbəb |
|---|---|---|---|
| `/exams/groups/` (rektor və müəllim) | **2 008 ms** | **2.5 MB** HTML | F-10: forma bütün tələbə/müəllim `<option>`-larını render edir |
| `?section=syllabus-list` (rektor) | **1 244 ms** (SQL 194, Python ~880) | 205 KB | F-12: 4 926 sillabusun hamısı Python-a, 2 dəfə (`section.py:250, 271`), sonra `Paginator(list)` |
| `?section=lessons-log` (rektor) | **1 038 ms** (SQL 661) | 309 KB | F-13: `range_totals` — 35 159 dərs Python-a + 509 833 qeyd üzrə aqreqat, keşsiz (dekan: 187 ms) |
| `/jurnal/analitika/` (rektor) | 1 073 ms → **53 ms** (keş 300 s) | 177 KB | `analytics_cache` işləyir; soyuq hesab 1 s |
| `/jurnal/` (rektor) | 426–472 ms (SQL 324) | 111 KB | F-14: `annotate(student_count)` LEFT JOIN 150k enrollment + GROUP BY 11 115 açılış, SONRA LIMIT 20 (295 ms) + paginator COUNT eyni join ilə (70 ms) |
| `/accounts/profile/academic-records/data/` | 282–303 ms | 9.5 KB | 25 tələbə üçün enrollment/lesson/lessonmark aqreqatları; `registrar_lesson` seq scan (Q10) |
| `/accounts/people/students/analytics/` | 269 ms | 6 KB | SAR GROUP BY + korrelyasiyalı «son qeyd» subquery (Q4, Q9: 296 / 75 ms) — keşsiz |
| `?section=registrar-catalog` | 162 ms | **711 KB** HTML | səhifə ölçüsü (statik render), sorğu 44 |
| `?section=groups-registry` | 165 ms | 477 KB | — |
| digərləri (dashboard, statistics, people_list 25/100, members, my-exams, notifications) | 40–165 ms | 18–184 KB | PASS |

## 5b. Eyni imtahanda 20 paralel tələbə (sandbox, thread-lər)

`test_concurrent_exam.py` (`TransactionTestCase`, hər thread öz DB bağlantısı, `is_public` quiz, 10 sual, `max_attempts_per_user=1`):
- **20 tələbə paralel** `start → take GET → 3 × autosave (4 təsadüfi sual, revision zənciri) → finish` — 3.2 s, **0 xəta**; hər tələbə üçün tam **1 cəhd**; hər sualın DB-dəki seçimi = tələbənin son göndərdiyi (itən yeniləmə yoxdur); `correct_count` gözlənilənlə eynidir; `(attempt, question)` dublikat `ExamAnswer` yoxdur. **PASS.**
- **Eyni tələbədən 5 paralel `start_exam`** → 5 × 302, **1 cəhd** (`exams/services/attempts.py:95-126` actor-lease + `SELECT … FOR UPDATE`, `audit/exams/query_budget.json` F01). **PASS.**

## 6. EXPLAIN (klon, read-only) və indeks təklifləri

**Metod.** `clone_capture.py` — Django test client ilə klon DB-də (55433) 22 səhifənin ORM sorğuları **tək transaction içində, sonda `set_rollback(True)`** (sessiya/`last_login`
yazıları qalmadı; `django_session` sayı dəyişmədi) → `clone_queries.json`; oradan ən yavaş 10 sorğu `EXPLAIN (ANALYZE, BUFFERS)` ilə `BEGIN READ ONLY … ROLLBACK`
+ `SET LOCAL app.current_org_id` (RLS real şərtdə) → `explain_perf.sql` / `explain_perf.out`. Cədvəl ölçüləri (klon): `registrar_lessonmark` **3.92 M**, `registrar_lesson` 305 k,
`registrar_enrollment` 150 k, `registrar_finalgrade` 115 k, `auth_user` 8.6 k, `registrar_studentacademicrecord` 7.8 k, `syllabus_syllabus` 4.9 k; **`exams_examattempt`/`exams_examanswer` = 0 sətir**
(klonda imtahan cəhdi yoxdur → imtahan yollarının real-həcm EXPLAIN-i mümkün deyil — NOT TESTED; data agentinin H5-i: planlama 9.2 ms, 0 sətir). `work_mem` = 4 MB.

| # | Sorğu (səhifə) | ORM ms | EXPLAIN icra | Plan qeydi | Səbəb / təklif |
|---|---|---|---|---|---|
| Q1 | `lessons-log` KPI: `COUNT FILTER` × 4 `FROM registrar_lessonmark WHERE lesson_id IN (35 159 dərs)` | 321 | **513 ms** | Nested Loop 509 833 qeyd, index `lessonmark_lesson_id` + heap (buffers 210 k hit + 10 k read) | Seq scan yoxdur; həcm problemidir → **F-13 keş** (300 s, `analytics_cache` kimi). İkinci dərəcəli: covering indeks `registrar_lessonmark (lesson_id) INCLUDE (organization_id, status, score)` → index-only scan (RLS filtri `organization_id` oxuduğu üçün INCLUDE-a daxil olmalıdır) |
| Q2 | `/jurnal/` (rektor) açılış siyahısı `annotate(student_count) … GROUP BY … ORDER BY … LIMIT 20` | 224 | **296 ms** | LEFT JOIN enrollment → **150 307 sətir**, Incremental Sort + GroupAggregate 11 115 qrup, sonra top-N 20 | Şəkil problemi: aqreqat paginasiyadan ƏVVƏL bütün açılışlara tətbiq olunur → **F-14**: `student_count`-u `Subquery(Enrollment…OuterRef)` və ya səhifənin 20 id-si üçün ayrıca `values('offering').annotate(Count)` ilə; paginator COUNT-u (Q7, 71 ms, `Seq Scan registrar_enrollment 150 157`) da JOIN-siz olur |
| Q3 | `lessons-log` dərs sətirləri `annotate(marks_count, first_mark)` org + tarix aralığı | 140 | 141 ms | **Parallel Seq Scan `registrar_lesson`** (Rows Removed by Filter 89 880 / worker), 35 159 dərs × lessonmark index | Mövcud indeks `(organization_id, offering_id, date)` tarix-aralığı üçün işləmir (offering yoxdur). **İndeks:** `CREATE INDEX CONCURRENTLY registrar_lesson_org_date_idx ON registrar_lesson (organization_id, date) INCLUDE (offering_id, hours);` — Q3, Q5, Q8, Q10-a kömək; əsas fix yenə F-13 keş |
| Q4 | `people/students/analytics/` qrup bucket-ları: SAR `student_id IN (SELECT user WHERE EXISTS(SAR))` + «son qeyd» korrelyasiyalı subquery + LEFT JOIN orgunit | 106 | **296 ms** | Planner səhv təxmini: rows=39 (faktiki 7 807) → Nested Loop + Materialize orgunit (880) → **Rows Removed by Join Filter 4 123 658** | Sorğu forması: `student_id__in=<User subquery with EXISTS>` təxmini pozur; `organization_user_queryset`-i sadə `SAR.objects.filter(organization=…)` ilə əvəz etmək və/yaxud `ANALYZE registrar_studentacademicrecord` (statistika köhnədirsə). Cache (300 s) da uyğundur (analitik panel). P3 |
| Q5 | `lessons-log` 90 sətir siyahısı (`build_rows`, `[:90]`) 5 cədvəl `select_related` | 82 | 94 ms | top-N heapsort 364 kB; kiçik cədvəllərdə seq scan (period 13, subject 2 501, orgunit 880, user 8 644 — hash join, normal) | Q3 indeksi ilə birlikdə yaxşılaşır; əks halda qəbul edilən |
| Q6 | `syllabus-list` bütün sillabuslar `select_related` × 6 + versiya CASE sıralaması | 79 (+66 təkrar) | 33 ms | **Sort Method: external merge Disk 4 680 kB** (4 926 sətir × 2 013 B genişlik > work_mem 4 MB); `syllabus_syllabus` seq scan (kiçik) | Fix F-12 (DB-də LIMIT/OFFSET, yalnız səhifənin sətirləri) — külli disk sort itir. İndeks lazım deyil |
| Q7 | `/jurnal/` paginator COUNT (JOIN enrollment GROUP BY) | 61 | 71 ms | `Seq Scan registrar_enrollment` 150 157 (JOIN üçün) | F-14 ilə itir |
| Q8 | `lessons-log` açılış/fənn `DISTINCT` (filtr seçimləri) | 59 | 46 ms | Parallel Seq Scan `registrar_lesson` 305 k | Q3 indeksi |
| Q9 | `people/students/analytics/` proqram bucket-ları | 42 | 75 ms | Q4 ilə eyni subquery forması (SAR seq scan 7 807) | Q4 kimi |
| Q10 | `academic-records/data/` `SUM(hours)` lesson WHERE offering IN (25 tələbənin enrollment-ləri) | 42 | 41 ms | Parallel Seq Scan `registrar_lesson` (IN-siyahı böyükdür) | Q3 indeksi (`organization_id, date`) burada kömək etmir; `registrar_lesson(offering_id)` indeksi var — planner seq scan seçib (çox offering); qəbul edilən (41 ms) |

**Data agentinin H1–H9-u (14_explain_hot.out):** jurnal grid 3.5 ms, jurnal siyahısı (müəllim) 1.0 ms, komponent balları 5 ms, müəllim açılışları 1.4 ms, üzv reyestri 23 ms, statistika 4.8/4.6 ms — hamısı indeksli, **PASS**; yalnız
`organizations_role`/`academicperiod`/`registrar_program` kiçik cədvəl seq scan-ları (normal).

**İndeks təklifi (icra EDİLMƏYİB, migration olaraq `AddIndexConcurrently` ilə):**
```sql
-- registrar/migrations: Lesson.Meta.indexes-ə əlavə (mövcud: organization_id+offering_id+date)
CREATE INDEX CONCURRENTLY registrar_lesson_org_date_idx
    ON registrar_lesson (organization_id, date) INCLUDE (offering_id, hours);          -- Q3/Q5/Q8 (lessons-log, dövr üzrə seçimlər)
-- opsional, yalnız F-13 keşi kifayət etməsə:
CREATE INDEX CONCURRENTLY registrar_lessonmark_lesson_cover_idx
    ON registrar_lessonmark (lesson_id) INCLUDE (organization_id, status, score, created_at);  -- Q1 index-only (3.9 M sətir → ~150 MB indeks; ölçü/yazı qiyməti nəzərə alınsın)
```
Mövcud `registrar_lessonmark_lesson_id_51ea32c5` covering versiya ilə əvəz oluna bilər (dublikat saxlamamaq üçün). `registrar_enrollment`, `registrar_finalgrade`, `auth_user` üçün seq scan tapılmadı (yalnız Q2/Q7-də JOIN-ə görə — sorğu forması ilə həll olunur).

## 7. Tapıntılar (P0–P3) və minimal düzəlişlər

P0: **yoxdur** (data itkisi / yarış / istifadəyə yararsızlıq tapılmadı — §5b PASS). P1: **yoxdur** (heç bir səhifə tək istifadəçi üçün 3 s-i keçmir; 50 VU-da xəta 0). Aşağıdakılar P2/P3.

| # | Sev. | Vəziyyət | Tapıntı (sübut) | Minimal təhlükəsiz düzəliş (fayl · funksiya) |
|---|---|---|---|---|
| F-10 | **P2** | FAIL | `exams:teacher_group_list` (`/exams/groups/`) formanı `defer_choices`-siz qurur → təşkilatın bütün tələbə/müəllim `<option>`-ları render olunur: klonda **2 008 ms, 2.5 MB** (rektor və müəllim; `load/sweep_rector.txt`). Kabinet bölməsi (`?section=groups`) 2026-09-02-də lazy edilib, bu köhnə tam səhifə isə qalıb; `teacher_create_group`/`teacher_update_group` `next`-siz ora yönləndirir (`groups.py:266`) | `apps/exams/views/teacher/groups.py` · `teacher_group_list`: səhifəni kabinet bölməsinə yönləndir — `return redirect(f"{reverse('accounts:profile')}?section=groups")` (şablonun JS-i lazy namizəd yükləməyi dəstəkləmir, ona görə `defer_choices=True` tək başına modalı boş qoyar); `_resolve_next_url` boş olanda eyni hədəf. Yoxlanılıb: klonda `?section=groups` rektor üçün **148 ms / 133 KB** (2 008 ms / 2.5 MB əvəzinə). Test: `GET /exams/groups/` → 302 |
| F-12 | **P2** | FAIL | `syllabus-list` bölməsi (rektor): 4 926 sillabusun HAMISI Python-a (`apps/accounts/views/syllabus/section.py:250` `list(context["syllabi"]…)` + `:271` `list(context["syllabi"])` — eyni 79/66 ms sorğu iki dəfə, disk sort 4.7 MB), hamısı üçün `build_row`, sonra `Paginator(rows, PAGE_SIZE)` (`:283`) → **1 244 ms wall / 194 ms SQL** (Python ~880 ms). Dekan (əhatəli) 120 ms | `section.py` · `build_syllabus_list_section`: (1) `context["syllabi"]`-ni bir dəfə `list()`-lə (271-də təkrar sorğunu sil); (2) `semester`/`unit` süzgəclərini queryset-ə köçür (`period__name=`, `chair_unit_id=`); (3) `Paginator`-u queryset üzərində qur, `build_row` yalnız `page.object_list` üçün; `overdue`/`counts`/`missing` üçün ayrıca `values_list("pk","updated_at",…)` (yüngül) və ya `aggregate`. Hədəf: rektor < 250 ms |
| F-13 | **P2** | FAIL | `lessons-log` bölməsi (rektor): `apps/registrar/lessons_log.py:356-394` `range_totals()` hər açılışda dövrün BÜTÜN dərslərini (35 159) `values_list` ilə Python-a çəkir (Q3 141 ms + döngü) və 509 833 qeyd üzrə `COUNT FILTER` (Q1 **513 ms**) — keşsiz; səhifə **1 038 ms** (dekan 187 ms) | `lessons_log.py` · `range_totals`: (1) nəticəni `cache` ilə 300 s saxla — açar `emsarena:registrar:lessons_log_totals:<org>:<md5(lessons_qs.query)>` (`registrar/analytics_cache.py` nümunəsi); (2) `note_state` təsnifatını SQL-ə keçir: `annotate(marks_count=Count("marks"), first_mark=Min("marks__created_at"))` üzərinə `Case/When(marks_count=0 → empty; first_mark__date > date + N → late)` + `aggregate(Count(...filter))` — 35k sətrin Python-a gəlməsi itir. Əlavə: §6 `registrar_lesson (organization_id, date)` indeksi |
| F-14 | **P2** | FAIL | `/jurnal/` org-geniş rol (rektor/İKT): `apps/registrar/page_contexts.py:223` `annotate(student_count=Count("enrollments", filter=…))` paginasiyadan ƏVVƏL → LEFT JOIN 150k enrollment + GROUP BY 11 115 açılış, sonra `LIMIT 20` (Q2 **296 ms**) + paginator COUNT eyni JOIN ilə (Q7 71 ms); səhifə 426–472 ms (müəllim: 18 ms) | `page_contexts.py` · `journal_list_context`: `annotate(student_count=…)`-i sil; `page_obj` alındıqdan sonra mövcud `_offering_student_counts(page_obj.object_list)` (`:574`, tək sorğu) ilə `counts_map` qur və şablona ötür (şablonda `offering.student_count` → `counts_map` lookup və ya obyektlərə `setattr`). Hədəf: < 60 ms |
| F-05 | **P2** | FAIL | İmtahan finish/autosave: `apps/exams/views/student/attempts.py:264-283` — cavabı olmayan hər sual üçün `ExamAnswer.objects.get_or_create` → finish 47 (5 sual) → 67 (25 sual), **+1 sorğu/sual** (`audit/exams/query_budget.json`); 40 suallıq final + 5000 tələbə eyni pəncərədə → ~10⁵–10⁶ kiçik INSERT/SELECT sorğusu | `attempts.py` · finish/autosave döngüsündən əvvəl: çatışmayan sualların `ExamAnswer(attempt=…, question=…)` siyahısını `bulk_create(ignore_conflicts=True)` ilə bir sorğuda yarat, sonra `answers_by_qid`-i yenidən yüklə (1 sorğu). Alternativ: `start_exam`-da bütün suallar üçün boş cavabları öncədən yarat (attempt yaradılanda bulk) |
| F-01 | P2 | FAIL | `organizations:group_students` 16→39 sorğu (25 tələbə): `apps/organizations/group_students.py:48` `record.group` `select_related`-də yoxdur | `group_students.py:93` · `group_students`: `.select_related("student", "program", "group")` |
| F-02 | P2 | FAIL | `exams/forms/group.py:190-195` Prefetch queryset `.only("id","name","organization_id")` tərs-FK açarı `teacher_id`-ni buraxır → hər qrup üçün `refresh_from_db` (`teacher_group_list` 38→48; klonda qrup sayı × 2). `students`-ə `student_groups_as_student` (M2M) prefetch-də problem yoxdur | `group.py` · `StudentGroupForm.__init__`: `.only("id", "name", "organization_id", "teacher_id")` |
| F-04 | P2 | FAIL | `registrar:journal_detail` 71 sorğunun 12-si eyni `syllabus_syllabus` SELECT-i: `syllabus_for_offering()` 4 çağıran × 3 pillə (`syllabus/services/offerings.py:60-87`) | `offerings.py` · `syllabus_for_offering`: 3 pilləni tək sorğuya birləşdir — `base.filter(Q(offering_id=…) \| Q(subject_id=…, period_id=…, offering__isnull=True) \| Q(subject_id=…, author_id=…, offering__isnull=True, period__isnull=True))` + `annotate(rank=Case(...))`.`order_by("rank").first()`; əlavə olaraq `journal_detail`-də nəticəni bir dəfə hesablayıb `syllabus_notice`/`journal_topics`/`journal_policy`-yə parametr kimi ötür (və ya `offering._syllabus_cache`) |
| F-03 | P3 | FAIL | `registrar:group_individual_plan` 19→65 (`individual_plan.py:191-213`: hər tələbə üçün `_season_periods` + `CurriculumSubject` sorğusu) | `individual_plan.py` · `build_group_document`: `teachers_cache` kimi `rows_cache[(curriculum_id, course)]` və `seasons_cache[raw_year]` dict-ləri ötür |
| F-06 | P3 | FAIL | `appeals:appeal_stats_data` sətir başına 2 sorğu (`appeals/views/teacher/statistics.py:188-210`) | `statistics.py` · `_filtered_appeals`: `.prefetch_related("exam__allowed_groups").annotate(item_count=Count("items", distinct=True))`; `_row`-da `appeal.item_count` |
| F-07 | P3 | PARTIAL | RLS `set_config`/`current_setting` hər səhifədə 5–17 round-trip (`core/rls.py:182,253-258`; `notifications/services/read_state.py:74` badge üçün 2–3 dəfə) | `core/rls.py` · `set_rls_tenant`: eyni bağlantıda eyni org üçün təkrar `set_config`-i atla (connection-level `_ems_rls_org` işarəsi, transaction bitəndə sıfırla); `read_state.py:74`-də badge sayğaclarını request-scoped memoizasiya (Codex §14 üslubu) |
| F-08 | P3 | PARTIAL | `accounts_userprofile.access_state` 3 ayrı yoxlama (`accounts/backends.py:68`, `core/middleware.py:183`, `accounts/context_processors.py:35`) | `request`-ə bir dəfə `request._ems_access_state` yaz, digər ikisi oxusun |
| F-09 | P3 | PARTIAL | `organizations_membership` tam SELECT 3–5 dəfə (`accounts/middleware.py:96`, `scoping.py:224`, `registrar/journal_access.py:96/126`, `guest_roster.py:133`, `context_builder/builder.py:34/56`) | `organizations/scoping.py` · `get_permission_scope`: `request` verilirsə `(user, org, permission)` açarı ilə request-scoped keş; `journal_access` çağırışları `request.active_memberships`-i işlətsin |
| F-11 | P3 | PARTIAL | `{% url 'javascript-catalog' %}` (`/jsi18n/`) hər səhifədə dinamik render (83 KB, 19 ms, `Cache-Control` yoxdur, ETag yoxdur → brauzer keşləmir) | `config/urls.py:62`: `cache_page(60*60)(vary_on_cookie(JavaScriptCatalog.as_view()))` və ya `last_modified` — dil cookie-sinə görə `Vary` |
| F-15 | P3 | PARTIAL | `people/students/analytics/` 246 ms: Q4/Q9 planner səhv təxmini (`student_id__in=<User + EXISTS subquery>` → rows 39 vs 7 807, Nested Loop 4.1 M süzülmüş sətir) | `apps/accounts/services/people/analytics*.py`: bucket sorğularını `StudentAcademicRecord.objects.filter(organization=…, is_active=…)` üzərində birbaşa qur (User subquery-siz) və ya nəticəni 300 s keşlə |
| F-16 | P3 | PARTIAL | Ölçülü səhifələr: `registrar-catalog` 711 KB, `groups-registry` 477 KB, `audit-log` 259 KB, `lessons-log` 309 KB HTML (gzip ~1/8) — 25–90 sətirlik səhifə üçün çox; kabinet shell + bütün bölmə skeletləri hər səhifədə | uzunmüddətli: bölmə fragment-lərini `profile_section_fragment` ilə yükləmək (mövcud endpoint), shell-də yalnız aktiv bölmə |
| — | P3 | qeyd | `statistics_selectors/teacher.py:175-181` qrup döngüsü ≤50 sorğu (prefetch `__in`-də işləmir) | `user_id__in=[s.id for s in grp.students.all()]` |
| — | P3 | qeyd | `workload/services/queries.py:231-234` 4 ayrı `SUM` | tək `aggregate(a=Sum(..., filter=Q(status=…)), …)` |
| — | info | PASS | `people_list` 25/100 sətir 15 sorğu; `members`, `groups_registry`, `catalog`, `audit_log`, `notifications`, `my_exams`, `journal_detail` (71, sabit), `exam_list_student` (34, sabit), dashboard-lar 24–36 sabit; 20 paralel tələbə/5 paralel start PASS; Redis `noeviction` + DB ayrımı PASS; statik boru xətti PASS |

## 8. Ballar

| Sahə | Bal | Əsaslandırma |
|---|---|---|
| **Performans** | **72 / 100** | Tələbə/müəllim əsas axını (dashboard, imtahan siyahısı, jurnal, statistika, bildirişlər) klonda 40–160 ms, 50 VU-da p95 410 ms, xəta 0; 58/62 endpoint miqyasdan asılı deyil; 20 paralel tələbə itkisiz. Çıxılan: 4 org-geniş səhifə 1–2 s (F-10 2.0 s/2.5 MB, F-12, F-13, F-14), 4 N+1 (F-01/02/03/06), jurnal detalı 71 sorğu (12 dublikat), finish +1/sual (F-05), hər səhifədə 10–15 çərçivə sorğusu (F-07/08/09). P0/P1 yoxdur. |
| **Miqyaslanma** | **64 / 100** | Prod = 1 Daphne prosesi (12 sync thread, GIL) → ~30–45 RPS/replika; `APP_REPLICAS` defolt 1 (compose «scale-ready»); login 320 ms CPU (hash) → 5000 tələbənin 10 dəq login-i ≥3 replika tələb edir. DB tərəfi sağlamdır (50 VU-da ≤4 aktiv bağlantı, PgBouncer session + `CONN_MAX_AGE=0` uyğun), indekslər əsas yollarda var; `registrar_lessonmark` 3.9 M sətirdə org-geniş aqreqatlar keşsiz (F-13) və `registrar_lesson` tarix-aralığı üçün indeks yoxdur. İmtahan cəhdi cədvəlləri klonda boşdur → 5000 paralel cəhd real-həcm EXPLAIN-i NOT TESTED (F-05 riski qalır). |
| **Redis / Keşləmə** | **70 / 100** | DB ayrımı (0 WS / 1 cache+sessiya / 2 celery), `noeviction`, socket timeout, tenant-namespaced açarlar (P1-06 bağlı), badge/bank/switcher invalidasiyası, kilidlərdə `cache.add`+token — düzgün. Çıxılan: statistika/analitika/akademik qeydlər yalnız TTL (yazıda invalidasiya yox); stampede mühafizəsi yoxdur; ağır org-geniş hesablamalar (lessons-log KPI, tələbə analitikası, sillabus siyahısı) heç keşlənmir; `jsi18n` HTTP keşsiz; sessiya + cache eyni DB1-də `noeviction` altında (cache dolarsa sessiya yazısı da xəta verir — monitorinq lazımdır). |

**Sayım:** P0 = 0 · P1 = 0 · **P2 = 8** (F-10, F-12, F-13, F-14, F-05, F-01, F-02, F-04) · **P3 = 8** (F-03, F-06, F-07, F-08, F-09, F-11, F-15, F-16) + 2 qeyd.

## Əlavə — artefaktlar (`audit/perf/`)
- `test_budget.py` → `budget_small.json`, `budget_full.json`, `budget_table.md`, `budget_full.log`, `html/` (render nümunələri)
- `test_trace.py` → `trace_origins.txt` (təkrar sorğuların Python stack-i)
- `orm_scan.py` → `orm_loop_hits.json`
- `test_concurrent_exam.py` (20 paralel tələbə + 5 paralel start) — 2 passed
- `locustfile_perf.py`, `load/stage{5,20,50}_*.csv`, `load/stage50_cpu.txt`, `load/stage50_pg.txt`, `sweep.sh`, `load/sweep_rector.txt`
- `clone_capture.py` → `clone_queries.json`; `explain_perf.sql` → `explain_perf.out`
- `urls.txt` (945 URL nümunəsi)

Təkrar icra: sandbox testləri `DATABASE_URL="postgres://emsarena_agent:emsarena_agent_password@127.0.0.1:55432/ems_audit_perf" USE_REDIS=False venv/bin/python -m pytest <fayl> --ds=config.settings.test --rootdir=/Users/elvin/Developer/EMSArena -q --reuse-db -p no:cacheprovider -o addopts="" -s`.
