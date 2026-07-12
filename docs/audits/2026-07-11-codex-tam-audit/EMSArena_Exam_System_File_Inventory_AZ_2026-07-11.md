# EMSArena imtahan sistemi — tam fayl inventarı

**Audit tarixi:** 2026-07-11  
**Repo:** `/Users/elvin/Desktop/Programming Folders/EMSArena/EMSArena`  
**İnventar ölçüsü:** 1019 unikal mənbə və inteqrasiya faylı

Əlavə indekslər: [bütün Python class/function simvolları](./EMSArena_Exam_All_Python_Symbols_AZ_2026-07-11.md) və [bütün exam model/M2M cədvəlləri, field-lər və constraint-lər](./EMSArena_Exam_Database_Table_Inventory_AZ_2026-07-11.md).

Bu inventar `apps/exams/`, `apps/appeals/`, `apps/live_exam/` və `apps/trial_exams/` ağaclarının bütün fayllarını, həmçinin repo üzrə imtahan inteqrasiyasına toxunan source/config/load fayllarını əhatə edir. Build nəticələri və duplikatlar (`staticfiles/`, `htmlcov/`, `output/`, `node_modules/`, `vendor/`, uyğun tracked orijinalla byte-identical ` 2` suffix-li 71 untracked fayl) qəsdən daxil edilməyib; onlar müstəqil source-of-truth deyil. Kateqoriyalaşdırma fayl yoluna əsaslanır, ona görə çoxfunksiyalı fayl yalnız bir əsas kateqoriyada göstərilir.

## Kateqoriya xülasəsi

| Kateqoriya | Say |
|---|---:|
| Model, domen və verilənlər sxemi | 25 |
| Miqrasiyalar və RLS | 87 |
| Servis, selektor, siyasət və public fasad | 103 |
| View, URL, API, serializer, WebSocket | 142 |
| Form və validasiya | 9 |
| Celery task, management command və fon işi | 17 |
| Şablonlar | 145 |
| JavaScript, CSS və digər frontend assetləri | 229 |
| Testlər, fixture-lər və load-testlər | 125 |
| Deployment, settings, monitorinq və sənədlər | 80 |
| Digər inteqrasiya faylları | 57 |
| **Cəmi** | **1019** |

## Model, domen və verilənlər sxemi (25)

- `apps/accounts/models.py`
- `apps/appeals/models.py`
- `apps/exams/domain/__init__.py`
- `apps/exams/domain/ai_config.py`
- `apps/exams/domain/attempts.py`
- `apps/exams/domain/coding.py`
- `apps/exams/domain/exam_definition.py`
- `apps/exams/domain/final_center.py`
- `apps/exams/domain/grading.py`
- `apps/exams/domain/import_jobs.py`
- `apps/exams/domain/language.py`
- `apps/exams/domain/question_bank/__init__.py`
- `apps/exams/domain/question_bank/bank_question.py`
- `apps/exams/domain/question_bank/exam_question.py`
- `apps/exams/domain/student_access.py`
- `apps/exams/domain/submission_inbox.py`
- `apps/exams/domain/supervision.py`
- `apps/exams/models.py`
- `apps/live_exam/domain/__init__.py`
- `apps/live_exam/domain/session.py`
- `apps/live_exam/models.py`
- `apps/notifications/models.py`
- `apps/organizations/models.py`
- `apps/registrar/models/grading.py`
- `apps/trial_exams/models.py`

## Miqrasiyalar və RLS (87)

- `apps/accounts/migrations/0007_userprofile_can_manage_exam_rooms.py`
- `apps/accounts/migrations/0008_alter_userprofile_role.py`
- `apps/accounts/urls.py`
- `apps/appeals/migrations/0001_initial.py`
- `apps/appeals/migrations/0002_scoreadjustment_previous_answer_score.py`
- `apps/appeals/migrations/0003_alter_appeal_status_alter_appealitem_appeal_type_and_more.py`
- `apps/appeals/migrations/__init__.py`
- `apps/appeals/urls.py`
- `apps/courses/urls.py`
- `apps/exams/migrations/0001_initial.py`
- `apps/exams/migrations/0002_questionblock_enable_paint_examquestion_disable_paint.py`
- `apps/exams/migrations/0003_aiconfiguration.py`
- `apps/exams/migrations/0004_add_supervision_models.py`
- `apps/exams/migrations/0005_alter_exam_exam_type_codingexamquestion_and_more.py`
- `apps/exams/migrations/0006_exam_fair_distribution_ai_balance_and_question_difficulty_source.py`
- `apps/exams/migrations/0007_alter_examquestionoption_text.py`
- `apps/exams/migrations/0008_exam_results_hidden_from_students.py`
- `apps/exams/migrations/0009_exam_indexes.py`
- `apps/exams/migrations/0010_aiconfiguration_assistant_model.py`
- `apps/exams/migrations/0011_examattempt_supervision_resumed_at_and_more.py`
- `apps/exams/migrations/0012_examattempt_supervision_locked_at.py`
- `apps/exams/migrations/0013_examattempt_supervision_manual_lock.py`
- `apps/exams/migrations/0014_backfill_manual_lock_flag.py`
- `apps/exams/migrations/0015_exam_language_variant.py`
- `apps/exams/migrations/0016_backfill_language_variants.py`
- `apps/exams/migrations/0017_question_bank_library.py`
- `apps/exams/migrations/0018_questionbank_default_question_type.py`
- `apps/exams/migrations/0019_alter_questionbank_default_question_type.py`
- `apps/exams/migrations/0020_examattempt_marked_question_ids.py`
- `apps/exams/migrations/0021_examattempt_unique_constraints.py`
- `apps/exams/migrations/0022_exam_archive_state.py`
- `apps/exams/migrations/0023_option_image.py`
- `apps/exams/migrations/0024_textextractionjob.py`
- `apps/exams/migrations/0025_textextractionjob_kind_textextractionjob_payload_and_more.py`
- `apps/exams/migrations/0026_textextractionjob_result_file_and_more.py`
- `apps/exams/migrations/0027_questionsubmission.py`
- `apps/exams/migrations/0028_questionsubmission_group_label_and_more.py`
- `apps/exams/migrations/0029_questionsubmission_teacher_note.py`
- `apps/exams/migrations/0030_examroom_examroomsession_finalexamticket_and_more.py`
- `apps/exams/migrations/0031_alter_finalexamticket_language.py`
- `apps/exams/migrations/0032_finalexamticket_reminder_stage.py`
- `apps/exams/migrations/0033_remove_examroomsession_uniq_active_session_per_room.py`
- `apps/exams/migrations/0034_studentgroup_subjects.py`
- `apps/exams/migrations/0035_studentgroup_org_unit.py`
- `apps/exams/migrations/0036_exam_subject_examstudentpin_studentexamattemptgrant.py`
- `apps/exams/migrations/0037_examattempt_is_trial.py`
- `apps/exams/migrations/0038_examroom_invigilators_examroomcomputer.py`
- `apps/exams/migrations/0039_decouple_exam_from_room_session.py`
- `apps/exams/migrations/0040_qsubmission_multi_groups.py`
- `apps/exams/migrations/0041_exam_excluded_users.py`
- `apps/exams/migrations/0042_examattempt_room_examattempt_room_computer.py`
- `apps/exams/migrations/0043_exam_deleted_at_exam_is_deleted.py`
- `apps/exams/migrations/0044_examanswer_question_snapshot.py`
- `apps/exams/migrations/__init__.py`
- `apps/exams/urls.py`
- `apps/live_exam/api/v1/urls.py`
- `apps/live_exam/migrations/0001_initial.py`
- `apps/live_exam/migrations/0002_liveanswer_liveans_session_question_idx.py`
- `apps/live_exam/migrations/__init__.py`
- `apps/live_exam/urls.py`
- `apps/notifications/migrations/0001_initial.py`
- `apps/notifications/migrations/0002_add_role_type_to_org_request.py`
- `apps/organizations/migrations/0003_rls_policies.py`
- `apps/organizations/migrations/0004_expand_rls_scope.py`
- `apps/organizations/migrations/0006_migrate_legacy_permission_aliases.py`
- `apps/organizations/migrations/0007_rls_question_bank_appeals.py`
- `apps/organizations/migrations/0008_backfill_appeal_permissions.py`
- `apps/organizations/migrations/0009_seed_university_management_roles.py`
- `apps/organizations/migrations/0010_seed_university_tutor_role.py`
- `apps/organizations/migrations/0012_rls_text_extraction_job.py`
- `apps/organizations/migrations/0014_academicperiod_exam_session_end_and_more.py`
- `apps/organizations/migrations/0015_rls_final_center.py`
- `apps/organizations/migrations/0016_rls_exam_room_computer.py`
- `apps/organizations/tests/test_rls.py`
- `apps/organizations/tests/test_rls_transaction_pooling.py`
- `apps/registrar/migrations/0006_courseoffering_instructor_assessmentscheme_and_more.py`
- `apps/registrar/migrations/0008_remove_gradecomponent_organization_and_more.py`
- `apps/registrar/migrations/0012_assessmentscheme_min_final_exam_score_and_more.py`
- `apps/registrar/migrations/0013_rls_finals.py`
- `apps/registrar/migrations/0019_rubric_assessmentcomponent_rubric_rubriccriterion_and_more.py`
- `apps/registrar/tests/test_rls.py`
- `apps/trial_exams/migrations/0001_initial.py`
- `apps/trial_exams/migrations/__init__.py`
- `apps/trial_exams/urls.py`
- `config/urls.py`
- `core/rls.py`
- `docs/RLS_BYPASS_AUDIT.md`

## Servis, selektor, siyasət və public fasad (103)

- `apps/accounts/selectors.py`
- `apps/accounts/services/__init__.py`
- `apps/accounts/services/account_deletion.py`
- `apps/accounts/services/profile_actions.py`
- `apps/accounts/services/statistics_selectors/_shared.py`
- `apps/accounts/services/statistics_selectors/org_admin.py`
- `apps/accounts/services/statistics_selectors/student.py`
- `apps/accounts/services/statistics_selectors/superadmin.py`
- `apps/accounts/services/statistics_selectors/teacher.py`
- `apps/accounts/services/view_as.py`
- `apps/appeals/public.py`
- `apps/appeals/selectors.py`
- `apps/appeals/services/__init__.py`
- `apps/appeals/services/creation.py`
- `apps/appeals/services/decisions.py`
- `apps/appeals/services/permissions.py`
- `apps/appeals/services/scoring.py`
- `apps/appeals/services/state_machine.py`
- `apps/appeals/services/window.py`
- `apps/courses/services.py`
- `apps/exams/domain/access_policy.py`
- `apps/exams/public.py`
- `apps/exams/selectors.py`
- `apps/exams/services/__init__.py`
- `apps/exams/services/access_policy.py`
- `apps/exams/services/ai_grading.py`
- `apps/exams/services/ai_question_generation.py`
- `apps/exams/services/ai_summary.py`
- `apps/exams/services/attempts.py`
- `apps/exams/services/bank_analysis.py`
- `apps/exams/services/bulk_workbench.py`
- `apps/exams/services/coding_definition.py`
- `apps/exams/services/coding_polyfills.py`
- `apps/exams/services/coding_runtime/__init__.py`
- `apps/exams/services/coding_runtime/_shared.py`
- `apps/exams/services/coding_runtime/constants.py`
- `apps/exams/services/coding_runtime/execution.py`
- `apps/exams/services/coding_runtime/files.py`
- `apps/exams/services/coding_runtime/grading.py`
- `apps/exams/services/coding_runtime/submission.py`
- `apps/exams/services/coding_throttle.py`
- `apps/exams/services/difficulty.py`
- `apps/exams/services/duplication.py`
- `apps/exams/services/exam_center_gate.py`
- `apps/exams/services/exam_definition.py`
- `apps/exams/services/final_center/__init__.py`
- `apps/exams/services/final_center/cabinet.py`
- `apps/exams/services/final_center/entry.py`
- `apps/exams/services/final_center/events.py`
- `apps/exams/services/final_center/history.py`
- `apps/exams/services/final_center/monitor.py`
- `apps/exams/services/final_center/permissions.py`
- `apps/exams/services/final_center/pins.py`
- `apps/exams/services/final_center/presence.py`
- `apps/exams/services/final_center/reminders.py`
- `apps/exams/services/final_center/reports.py`
- `apps/exams/services/final_center/room_admin.py`
- `apps/exams/services/final_center/sessions.py`
- `apps/exams/services/final_center/tickets.py`
- `apps/exams/services/grading.py`
- `apps/exams/services/import_media.py`
- `apps/exams/services/language_variants.py`
- `apps/exams/services/parsing/__init__.py`
- `apps/exams/services/parsing/_core.py`
- `apps/exams/services/parsing/extraction/__init__.py`
- `apps/exams/services/parsing/extraction/_deps.py`
- `apps/exams/services/parsing/extraction/constants.py`
- `apps/exams/services/parsing/extraction/highlight.py`
- `apps/exams/services/parsing/extraction/normalize.py`
- `apps/exams/services/parsing/extraction/ocr.py`
- `apps/exams/services/parsing/extraction/pipeline.py`
- `apps/exams/services/parsing/extraction/safety.py`
- `apps/exams/services/pdf_math.py`
- `apps/exams/services/question_bank.py`
- `apps/exams/services/question_bank_attach.py`
- `apps/exams/services/question_submission.py`
- `apps/exams/services/question_word_export.py`
- `apps/exams/services/randomizer.py`
- `apps/exams/services/result_calculation.py`
- `apps/exams/services/review_visibility.py`
- `apps/exams/services/student_pins.py`
- `apps/exams/services/supervision/__init__.py`
- `apps/exams/services/supervision/_shared.py`
- `apps/exams/services/supervision/actions.py`
- `apps/exams/services/supervision/constants.py`
- `apps/exams/services/supervision/incidents.py`
- `apps/exams/services/supervision/monitor.py`
- `apps/exams/services/supervision/snapshot.py`
- `apps/exams/services/teacher_dashboard.py`
- `apps/exams/services/utils.py`
- `apps/live_exam/selectors.py`
- `apps/live_exam/services.py`
- `apps/notifications/public.py`
- `apps/notifications/services/__init__.py`
- `apps/notifications/services/constants.py`
- `apps/notifications/services/events.py`
- `apps/notifications/services/helpers.py`
- `apps/organizations/permissions.py`
- `apps/registrar/public.py`
- `apps/registrar/services.py`
- `apps/trial_exams/public.py`
- `apps/trial_exams/services.py`
- `core/permissions.py`

## View, URL, API, serializer, WebSocket (142)

- `apps/accounts/views/__init__.py`
- `apps/accounts/views/_dashboard_helpers/cheap_counts.py`
- `apps/accounts/views/_dashboard_helpers/evaluated_review.py`
- `apps/accounts/views/_dashboard_helpers/formatters.py`
- `apps/accounts/views/_dashboard_helpers/pending_answers.py`
- `apps/accounts/views/_dashboard_helpers/pending_review.py`
- `apps/accounts/views/_dashboard_helpers/results.py`
- `apps/accounts/views/_helpers/__init__.py`
- `apps/accounts/views/_helpers/constants.py`
- `apps/accounts/views/_helpers/formatting.py`
- `apps/accounts/views/_helpers/rbac.py`
- `apps/accounts/views/_helpers/review_window.py`
- `apps/accounts/views/_helpers/superadmin_inspector.py`
- `apps/accounts/views/_helpers/tenant.py`
- `apps/accounts/views/auth/_shared.py`
- `apps/accounts/views/dashboard/__init__.py`
- `apps/accounts/views/dashboard/results.py`
- `apps/accounts/views/dashboard/review.py`
- `apps/accounts/views/dashboard/student.py`
- `apps/accounts/views/profile/_sections/exam_rooms.py`
- `apps/accounts/views/profile/_sections/exams.py`
- `apps/accounts/views/profile/_sections/groups.py`
- `apps/accounts/views/profile/_sections/labels.py`
- `apps/accounts/views/profile/_sections/question_bank.py`
- `apps/accounts/views/profile/_sections/question_submissions.py`
- `apps/accounts/views/profile/_sections/statistics.py`
- `apps/accounts/views/profile/_sections/superadmin_orgs.py`
- `apps/accounts/views/profile/_sections/unit_exams.py`
- `apps/accounts/views/profile/constants.py`
- `apps/accounts/views/profile/contact_inbox.py`
- `apps/accounts/views/profile/context_builder/_helpers.py`
- `apps/accounts/views/profile/context_builder/_stage1.py`
- `apps/accounts/views/profile/context_builder/_stage2.py`
- `apps/accounts/views/profile/context_builder/_stage3.py`
- `apps/accounts/views/profile/context_builder/_stage4.py`
- `apps/accounts/views/profile/sections_api.py`
- `apps/accounts/views/profile/statistics_export.py`
- `apps/accounts/views/search.py`
- `apps/accounts/views/superadmin/__init__.py`
- `apps/accounts/views/superadmin/endpoints.py`
- `apps/accounts/views/superadmin/exam_rooms.py`
- `apps/appeals/views/__init__.py`
- `apps/appeals/views/shared/__init__.py`
- `apps/appeals/views/shared/_helpers.py`
- `apps/appeals/views/shared/detail.py`
- `apps/appeals/views/student/__init__.py`
- `apps/appeals/views/student/endpoints.py`
- `apps/appeals/views/teacher/__init__.py`
- `apps/appeals/views/teacher/endpoints.py`
- `apps/courses/views/__init__.py`
- `apps/courses/views/shared/dashboard.py`
- `apps/courses/views/teacher/__init__.py`
- `apps/courses/views/teacher/membership.py`
- `apps/exams/consumers.py`
- `apps/exams/routing.py`
- `apps/exams/views/__init__.py`
- `apps/exams/views/exam_center/__init__.py`
- `apps/exams/views/exam_center/_shared.py`
- `apps/exams/views/exam_center/monitor.py`
- `apps/exams/views/exam_center/pin_lookup.py`
- `apps/exams/views/exam_center/reports.py`
- `apps/exams/views/exam_center/room_monitor.py`
- `apps/exams/views/exam_center/rooms.py`
- `apps/exams/views/exam_center/sessions.py`
- `apps/exams/views/exam_center/statistics.py`
- `apps/exams/views/exam_center/statistics_charts.py`
- `apps/exams/views/shared/__init__.py`
- `apps/exams/views/shared/access.py`
- `apps/exams/views/shared/tenant.py`
- `apps/exams/views/student/__init__.py`
- `apps/exams/views/student/_helpers.py`
- `apps/exams/views/student/attempts.py`
- `apps/exams/views/student/coding.py`
- `apps/exams/views/student/final_center.py`
- `apps/exams/views/student/lists.py`
- `apps/exams/views/student/results.py`
- `apps/exams/views/student/script_data.py`
- `apps/exams/views/teacher/__init__.py`
- `apps/exams/views/teacher/exams/__init__.py`
- `apps/exams/views/teacher/exams/_shared.py`
- `apps/exams/views/teacher/exams/actions.py`
- `apps/exams/views/teacher/exams/attempt_grants.py`
- `apps/exams/views/teacher/exams/constants.py`
- `apps/exams/views/teacher/exams/list_detail.py`
- `apps/exams/views/teacher/exams/lookups.py`
- `apps/exams/views/teacher/extract_jobs.py`
- `apps/exams/views/teacher/groups.py`
- `apps/exams/views/teacher/languages.py`
- `apps/exams/views/teacher/question_bank/__init__.py`
- `apps/exams/views/teacher/question_bank/_helpers.py`
- `apps/exams/views/teacher/question_bank/_reports.py`
- `apps/exams/views/teacher/question_bank/_views_create.py`
- `apps/exams/views/teacher/question_bank/_views_misc.py`
- `apps/exams/views/teacher/question_library/__init__.py`
- `apps/exams/views/teacher/question_library/_shared.py`
- `apps/exams/views/teacher/question_library/crud.py`
- `apps/exams/views/teacher/question_library/export.py`
- `apps/exams/views/teacher/question_library/picker.py`
- `apps/exams/views/teacher/question_library/questions.py`
- `apps/exams/views/teacher/questions/__init__.py`
- `apps/exams/views/teacher/questions/_shared.py`
- `apps/exams/views/teacher/questions/bank.py`
- `apps/exams/views/teacher/questions/constants.py`
- `apps/exams/views/teacher/questions/crud.py`
- `apps/exams/views/teacher/results/__init__.py`
- `apps/exams/views/teacher/results/_attempt_views.py`
- `apps/exams/views/teacher/results/_export_builder.py`
- `apps/exams/views/teacher/results/_helpers.py`
- `apps/exams/views/teacher/results/_results_views.py`
- `apps/exams/views/teacher/statistics.py`
- `apps/exams/views/teacher/submission_inbox.py`
- `apps/exams/views/teacher/supervision/__init__.py`
- `apps/exams/views/teacher/supervision/_shared.py`
- `apps/exams/views/teacher/supervision/live.py`
- `apps/exams/views/teacher/supervision/monitor.py`
- `apps/live_exam/api/__init__.py`
- `apps/live_exam/api/v1/__init__.py`
- `apps/live_exam/api/v1/views.py`
- `apps/live_exam/consumers.py`
- `apps/live_exam/routing.py`
- `apps/live_exam/serializers.py`
- `apps/live_exam/views/__init__.py`
- `apps/live_exam/views/_helpers.py`
- `apps/live_exam/views/api.py`
- `apps/live_exam/views/host/__init__.py`
- `apps/live_exam/views/host/_shared.py`
- `apps/live_exam/views/host/constants.py`
- `apps/live_exam/views/host/game.py`
- `apps/live_exam/views/host/session.py`
- `apps/live_exam/views/player/__init__.py`
- `apps/live_exam/views/player/_shared.py`
- `apps/live_exam/views/player/constants.py`
- `apps/live_exam/views/player/join.py`
- `apps/live_exam/views/player/wait.py`
- `apps/live_exam/views/results.py`
- `apps/registrar/views.py`
- `apps/trial_exams/admin_views.py`
- `apps/trial_exams/views.py`
- `core/media_views.py`
- `core/seo_views.py`
- `docs/api.md`
- `docs/api_roadmap.md`

## Form və validasiya (9)

- `apps/exams/forms/__init__.py`
- `apps/exams/forms/bank_question.py`
- `apps/exams/forms/coding.py`
- `apps/exams/forms/exam.py`
- `apps/exams/forms/exam_coding_fields.py`
- `apps/exams/forms/final_center.py`
- `apps/exams/forms/group.py`
- `apps/exams/forms/question.py`
- `apps/trial_exams/forms.py`

## Celery task, management command və fon işi (17)

- `apps/accounts/management/commands/make_user_import_template.py`
- `apps/accounts/views/_dashboard_helpers/assigned_tasks.py`
- `apps/exams/management/commands/__init__.py`
- `apps/exams/management/commands/_final_exam_demo_data.py`
- `apps/exams/management/commands/_seed_helpers/__init__.py`
- `apps/exams/management/commands/_seed_helpers/courses.py`
- `apps/exams/management/commands/_seed_helpers/exams.py`
- `apps/exams/management/commands/_seed_helpers/users.py`
- `apps/exams/management/commands/seed_demo_hierarchy.py`
- `apps/exams/management/commands/seed_final_exam_demo.py`
- `apps/exams/management/commands/seed_group_demo_data.py`
- `apps/exams/tasks.py`
- `apps/notifications/management/commands/purge_notifications.py`
- `apps/organizations/management/commands/create_sample_orgs.py`
- `apps/organizations/management/commands/seed_ci_e2e_scenario.py`
- `apps/organizations/management/commands/seed_western_caspian.py`
- `core/tasks.py`

## Şablonlar (145)

- `apps/accounts/templates/accounts/assigned_exams.html`
- `apps/accounts/templates/accounts/my_results.html`
- `apps/accounts/templates/accounts/partials/_groups_overview_content.html`
- `apps/accounts/templates/accounts/partials/_pending_answers_content.html`
- `apps/accounts/templates/accounts/partials/_pending_review_content.html`
- `apps/accounts/templates/accounts/partials/_permission_editor_content.html`
- `apps/accounts/templates/accounts/partials/_review_results_content.html`
- `apps/accounts/templates/accounts/partials/_superadmin_exam_rooms_content.html`
- `apps/accounts/templates/accounts/profile.html`
- `apps/accounts/templates/accounts/profile/_sidebar.html`
- `apps/accounts/templates/accounts/profile/sections/_assigned_exams.html`
- `apps/accounts/templates/accounts/profile/sections/_exam_center_pins.html`
- `apps/accounts/templates/accounts/profile/sections/_exam_center_stats.html`
- `apps/accounts/templates/accounts/profile/sections/_groups.html`
- `apps/accounts/templates/accounts/profile/sections/_manage_appeals.html`
- `apps/accounts/templates/accounts/profile/sections/_my_appeals.html`
- `apps/accounts/templates/accounts/profile/sections/_my_exams.html`
- `apps/accounts/templates/accounts/profile/sections/_my_results.html`
- `apps/accounts/templates/accounts/profile/sections/_my_subjects.html`
- `apps/accounts/templates/accounts/profile/sections/_my_transcript.html`
- `apps/accounts/templates/accounts/profile/sections/_notifications.html`
- `apps/accounts/templates/accounts/profile/sections/_profile_info_stats.html`
- `apps/accounts/templates/accounts/profile/sections/_publish_notification.html`
- `apps/accounts/templates/accounts/profile/sections/_question_bank.html`
- `apps/accounts/templates/accounts/profile/sections/_question_submissions.html`
- `apps/accounts/templates/accounts/profile/sections/_statistics.html`
- `apps/accounts/templates/accounts/profile/sections/_unit_exams.html`
- `apps/accounts/templates/accounts/profile/sections/partials/_delete_exam_modal.html`
- `apps/accounts/templates/accounts/profile/sections/partials/_my_exams_card.html`
- `apps/accounts/templates/accounts/profile/sections/partials/_my_exams_kpis.html`
- `apps/accounts/templates/accounts/profile/sections/partials/_my_exams_section.html`
- `apps/accounts/templates/accounts/profile/sections/partials/_my_exams_toolbar.html`
- `apps/accounts/templates/accounts/profile/sections/statistics/_filter_bar.html`
- `apps/accounts/templates/accounts/profile/sections/statistics/_summary_cards.html`
- `apps/accounts/templates/accounts/profile/sections/superadmin/_superadmin_contact_messages.html`
- `apps/accounts/templates/accounts/profile/sections/superadmin/_superadmin_exam_rooms.html`
- `apps/accounts/templates/accounts/profile/sections/superadmin/_superadmin_org_inspector.html`
- `apps/accounts/templates/accounts/profile/sidebar/_org_menu_group.html`
- `apps/accounts/templates/accounts/student_dashboard.html`
- `apps/accounts/templates/accounts/teacher_dashboard.html`
- `apps/appeals/templates/appeals/partials/_appeal_detail_body.html`
- `apps/appeals/templates/appeals/partials/_manage_appeals_body.html`
- `apps/appeals/templates/appeals/partials/_my_appeals_body.html`
- `apps/appeals/templates/appeals/partials/_review_appeal_body.html`
- `apps/appeals/templates/appeals/partials/_status_badge.html`
- `apps/appeals/templates/appeals/student/appeal_create.html`
- `apps/courses/templates/courses/course_dashboard.html`
- `apps/courses/templates/courses/partials/_action_confirm_modal.html`
- `apps/exams/templates/exams/components/_exam_modals.html`
- `apps/exams/templates/exams/components/_paint_answer.html`
- `apps/exams/templates/exams/exam_center/_breadcrumb.html`
- `apps/exams/templates/exams/exam_center/_confirm_modal.html`
- `apps/exams/templates/exams/exam_center/_pin_lookup_body.html`
- `apps/exams/templates/exams/exam_center/_snapshot_modal.html`
- `apps/exams/templates/exams/exam_center/finals.html`
- `apps/exams/templates/exams/exam_center/pin_lookup.html`
- `apps/exams/templates/exams/exam_center/reports.html`
- `apps/exams/templates/exams/exam_center/room_list.html`
- `apps/exams/templates/exams/exam_center/room_monitor.html`
- `apps/exams/templates/exams/exam_center/session_detail.html`
- `apps/exams/templates/exams/exam_center/session_form.html`
- `apps/exams/templates/exams/exam_center/session_history.html`
- `apps/exams/templates/exams/exam_center/session_list.html`
- `apps/exams/templates/exams/exam_center/session_monitor.html`
- `apps/exams/templates/exams/student/exam_result.html`
- `apps/exams/templates/exams/student/final_entry.html`
- `apps/exams/templates/exams/student/final_waiting.html`
- `apps/exams/templates/exams/student/partials/_final_langbar.html`
- `apps/exams/templates/exams/student/partials/_student_exam_list_filters_js.html`
- `apps/exams/templates/exams/student/partials/_student_exam_list_scripts.html`
- `apps/exams/templates/exams/student/partials/_take_exam_scripts.html`
- `apps/exams/templates/exams/student/student_exam_history.html`
- `apps/exams/templates/exams/student/student_exam_list.html`
- `apps/exams/templates/exams/student/take_coding_exam.html`
- `apps/exams/templates/exams/student/take_exam.html`
- `apps/exams/templates/exams/teacher/add_exam_question.html`
- `apps/exams/templates/exams/teacher/create_question.html`
- `apps/exams/templates/exams/teacher/create_question_bank.html`
- `apps/exams/templates/exams/teacher/create_student_group.html`
- `apps/exams/templates/exams/teacher/deleted_exams.html`
- `apps/exams/templates/exams/teacher/exam_bank_picker.html`
- `apps/exams/templates/exams/teacher/exam_language_manager.html`
- `apps/exams/templates/exams/teacher/exam_live_monitor.html`
- `apps/exams/templates/exams/teacher/exam_section.html`
- `apps/exams/templates/exams/teacher/export_waiting.html`
- `apps/exams/templates/exams/teacher/partials/_bank_picker_shell.html`
- `apps/exams/templates/exams/teacher/partials/_bulk_question_workbench.html`
- `apps/exams/templates/exams/teacher/partials/_bulk_workbench_scripts.html`
- `apps/exams/templates/exams/teacher/partials/_coding_exam_fields.html`
- `apps/exams/templates/exams/teacher/partials/_create_edit_exam_bs_modal.html`
- `apps/exams/templates/exams/teacher/partials/_create_exam_modal.html`
- `apps/exams/templates/exams/teacher/partials/_create_exam_modal_form.html`
- `apps/exams/templates/exams/teacher/partials/_create_question_bank_scripts.html`
- `apps/exams/templates/exams/teacher/partials/_exam_bank_picker_content.html`
- `apps/exams/templates/exams/teacher/partials/_exam_bank_picker_items.html`
- `apps/exams/templates/exams/teacher/partials/_exam_bank_picker_modal.html`
- `apps/exams/templates/exams/teacher/partials/_exam_detail_question_items.html`
- `apps/exams/templates/exams/teacher/partials/_exam_section_js.html`
- `apps/exams/templates/exams/teacher/partials/_question_bank_list_body.html`
- `apps/exams/templates/exams/teacher/partials/_question_form.html`
- `apps/exams/templates/exams/teacher/partials/_question_form_bs_modal.html`
- `apps/exams/templates/exams/teacher/partials/_question_management.html`
- `apps/exams/templates/exams/teacher/partials/_question_submission_meta.html`
- `apps/exams/templates/exams/teacher/partials/_question_submission_preview.html`
- `apps/exams/templates/exams/teacher/partials/_supervision_monitor_js.html`
- `apps/exams/templates/exams/teacher/partials/_teacher_exam_statistics_js.html`
- `apps/exams/templates/exams/teacher/question_bank_bulk_add.html`
- `apps/exams/templates/exams/teacher/question_bank_detail.html`
- `apps/exams/templates/exams/teacher/question_submission_detail.html`
- `apps/exams/templates/exams/teacher/question_submission_form.html`
- `apps/exams/templates/exams/teacher/question_submission_inbox.html`
- `apps/exams/templates/exams/teacher/question_submission_review.html`
- `apps/exams/templates/exams/teacher/questions_i_can_see.html`
- `apps/exams/templates/exams/teacher/supervision_detail.html`
- `apps/exams/templates/exams/teacher/supervision_monitor.html`
- `apps/exams/templates/exams/teacher/teacher_check_attempt.html`
- `apps/exams/templates/exams/teacher/teacher_exam_detail.html`
- `apps/exams/templates/exams/teacher/teacher_exam_results.html`
- `apps/exams/templates/exams/teacher/teacher_exam_statistics.html`
- `apps/exams/templates/exams/teacher/teacher_group_list.html`
- `apps/exams/templates/exams/teacher/teacher_pending_attempts.html`
- `apps/exams/templates/exams/teacher/teacher_questions_bank.html`
- `apps/exams/templates/exams/teacher/teacher_view_attempt.html`
- `apps/live_exam/templates/liveExam/_host_control_bar.html`
- `apps/live_exam/templates/liveExam/_host_settings_drawer.html`
- `apps/live_exam/templates/liveExam/host_lobby.html`
- `apps/live_exam/templates/liveExam/host_presentation.html`
- `apps/live_exam/templates/liveExam/join.html`
- `apps/live_exam/templates/liveExam/partials/_teacher_live_session_detail_js.html`
- `apps/live_exam/templates/liveExam/pin_entry.html`
- `apps/live_exam/templates/liveExam/player_screen.html`
- `apps/live_exam/templates/liveExam/teacher_live_results.html`
- `apps/live_exam/templates/liveExam/teacher_live_session_detail.html`
- `apps/live_exam/templates/liveExam/wait_room.html`
- `apps/notifications/templates/notifications/notification_detail.html`
- `apps/notifications/templates/notifications/notification_list.html`
- `apps/registrar/templates/registrar/journal_detail.html`
- `apps/registrar/templates/registrar/partials/_calendar_content.html`
- `apps/registrar/templates/registrar/partials/_schedule_content.html`
- `apps/trial_exams/templates/admin/trial_exams/trialexamrequest/reply.html`
- `apps/trial_exams/templates/trial_exams/email/trial_notification.html`
- `apps/trial_exams/templates/trial_exams/email/trial_reply.html`
- `apps/trial_exams/templates/trial_exams/trial_exam_request.html`
- `templates/partials/_footer.html`
- `templates/partials/_navbar.html`

## JavaScript, CSS və digər frontend assetləri (229)

- `apps/accounts/static/accounts/css/profile.css`
- `apps/accounts/static/accounts/css/profile/sections/assigned_exams.css`
- `apps/accounts/static/accounts/css/profile/sections/list_cards.css`
- `apps/accounts/static/accounts/css/profile/sections/my_exams.css`
- `apps/accounts/static/accounts/css/profile/sections/my_subjects.css`
- `apps/accounts/static/accounts/css/profile/sections/pending_review.css`
- `apps/accounts/static/accounts/css/student_dashboard.css`
- `apps/accounts/static/accounts/js/my_exams_dashboard.js`
- `apps/accounts/static/accounts/js/permission_editor/labels.js`
- `apps/accounts/static/accounts/js/profile/ajax.js`
- `apps/accounts/static/accounts/js/profile/assigned_exam.js`
- `apps/accounts/static/accounts/js/profile/create_exam_modal.js`
- `apps/accounts/static/accounts/js/profile/create_exam_selects.js`
- `apps/accounts/static/accounts/js/profile/init.js`
- `apps/accounts/static/accounts/js/profile/namespace.js`
- `apps/accounts/static/accounts/js/profile/ui.js`
- `apps/accounts/static/accounts/js/statistics/charts.js`
- `apps/appeals/static/appeals/css/appeals/_part1.css`
- `apps/appeals/static/appeals/css/appeals/_part2.css`
- `apps/appeals/static/appeals/css/appeals/_part3.css`
- `apps/appeals/static/appeals/js/appeals_form.js`
- `apps/appeals/static/appeals/js/appeals_review.js`
- `apps/appeals/static/appeals/js/appeals_sections.js`
- `apps/courses/static/courses/css/course_dashboard_redesign.css`
- `apps/courses/static/courses/js/course_ai_drawer.js`
- `apps/courses/static/courses/js/course_modals_enhance.js`
- `apps/courses/static/courses/js/course_panel_tabs.js`
- `apps/exams/static/exams/css/_searchable_multi_select.css`
- `apps/exams/static/exams/css/add_exam_question.css`
- `apps/exams/static/exams/css/bank_picker_modal.css`
- `apps/exams/static/exams/css/bulk_workbench_extras/_part1.css`
- `apps/exams/static/exams/css/bulk_workbench_extras/_part2.css`
- `apps/exams/static/exams/css/coding_exam/_part1.css`
- `apps/exams/static/exams/css/coding_exam/_part2.css`
- `apps/exams/static/exams/css/coding_exam/_part3.css`
- `apps/exams/static/exams/css/course_exam_modal.css`
- `apps/exams/static/exams/css/create_question_bank.css`
- `apps/exams/static/exams/css/create_question_bank_addons.css`
- `apps/exams/static/exams/css/create_student_group.css`
- `apps/exams/static/exams/css/exam_create_edit_modal.css`
- `apps/exams/static/exams/css/exam_live_monitor.css`
- `apps/exams/static/exams/css/exam_paint.css`
- `apps/exams/static/exams/css/exam_result/_part1.css`
- `apps/exams/static/exams/css/exam_result/_part2.css`
- `apps/exams/static/exams/css/exam_time_warning.css`
- `apps/exams/static/exams/css/exam_wizard.css`
- `apps/exams/static/exams/css/final_center/center.css`
- `apps/exams/static/exams/css/final_center/history.css`
- `apps/exams/static/exams/css/final_center/monitor.css`
- `apps/exams/static/exams/css/final_center/pin_lookup.css`
- `apps/exams/static/exams/css/final_center/student.css`
- `apps/exams/static/exams/css/paint_answer.css`
- `apps/exams/static/exams/css/profile_group_modal.css`
- `apps/exams/static/exams/css/question_form_modal.css`
- `apps/exams/static/exams/css/question_submission.css`
- `apps/exams/static/exams/css/student_exam_history.css`
- `apps/exams/static/exams/css/student_exam_list.css`
- `apps/exams/static/exams/css/supervision_detail.css`
- `apps/exams/static/exams/css/supervision_monitor.css`
- `apps/exams/static/exams/css/take_exam/_part1.css`
- `apps/exams/static/exams/css/take_exam/_part2.css`
- `apps/exams/static/exams/css/take_exam/_part3.css`
- `apps/exams/static/exams/css/teacher_check_attempt/_part1.css`
- `apps/exams/static/exams/css/teacher_check_attempt/_part2.css`
- `apps/exams/static/exams/css/teacher_exam_detail/_part1.css`
- `apps/exams/static/exams/css/teacher_exam_detail/_part2.css`
- `apps/exams/static/exams/css/teacher_exam_results/_part1.css`
- `apps/exams/static/exams/css/teacher_exam_results/_part2.css`
- `apps/exams/static/exams/css/teacher_exam_statistics.css`
- `apps/exams/static/exams/css/teacher_group_list.css`
- `apps/exams/static/exams/css/teacher_pending_attempts.css`
- `apps/exams/static/exams/css/teacher_questions_bank/_part1.css`
- `apps/exams/static/exams/css/teacher_questions_bank/_part2.css`
- `apps/exams/static/exams/css/teacher_view_attempt.css`
- `apps/exams/static/exams/js/aiQuestionBank.js`
- `apps/exams/static/exams/js/bankManagement.js`
- `apps/exams/static/exams/js/coding_exam.js`
- `apps/exams/static/exams/js/coding_exam/api.js`
- `apps/exams/static/exams/js/coding_exam/coding_exam.entry.js`
- `apps/exams/static/exams/js/coding_exam/context.js`
- `apps/exams/static/exams/js/coding_exam/events.js`
- `apps/exams/static/exams/js/coding_exam/preview.js`
- `apps/exams/static/exams/js/coding_exam/runner.js`
- `apps/exams/static/exams/js/coding_exam/state.js`
- `apps/exams/static/exams/js/coding_exam/ui.js`
- `apps/exams/static/exams/js/coding_exam/utils.js`
- `apps/exams/static/exams/js/course_exam_dashboard.js`
- `apps/exams/static/exams/js/examBankPicker.js`
- `apps/exams/static/exams/js/exam_center_stats_charts.js`
- `apps/exams/static/exams/js/exam_create_edit_modal.js`
- `apps/exams/static/exams/js/exam_create_edit_modal/entry.js`
- `apps/exams/static/exams/js/exam_create_edit_modal/form.js`
- `apps/exams/static/exams/js/exam_create_edit_modal/markup.js`
- `apps/exams/static/exams/js/exam_create_edit_modal/namespace.js`
- `apps/exams/static/exams/js/exam_create_edit_modal/searchable_select.js`
- `apps/exams/static/exams/js/exam_create_edit_modal/subject_select.js`
- `apps/exams/static/exams/js/exam_create_edit_modal/toggles.js`
- `apps/exams/static/exams/js/exam_live_monitor.js`
- `apps/exams/static/exams/js/exam_live_monitor/actions.js`
- `apps/exams/static/exams/js/exam_live_monitor/entry.js`
- `apps/exams/static/exams/js/exam_live_monitor/namespace.js`
- `apps/exams/static/exams/js/exam_live_monitor/polling.js`
- `apps/exams/static/exams/js/exam_live_monitor/render.js`
- `apps/exams/static/exams/js/exam_live_monitor/snapshot_modal.js`
- `apps/exams/static/exams/js/exam_live_monitor/utils.js`
- `apps/exams/static/exams/js/exam_paint.js`
- `apps/exams/static/exams/js/exam_supervision/api.js`
- `apps/exams/static/exams/js/exam_supervision/event_capture.js`
- `apps/exams/static/exams/js/exam_supervision/exam_supervision.entry.js`
- `apps/exams/static/exams/js/exam_supervision/scoring.js`
- `apps/exams/static/exams/js/exam_supervision/state.js`
- `apps/exams/static/exams/js/exam_supervision/ui.js`
- `apps/exams/static/exams/js/exam_supervision/websocket.js`
- `apps/exams/static/exams/js/exam_time_warning.js`
- `apps/exams/static/exams/js/exam_wizard.js`
- `apps/exams/static/exams/js/final_center/confirm_forms.js`
- `apps/exams/static/exams/js/final_center/confirm_modal.js`
- `apps/exams/static/exams/js/final_center/final_entry.js`
- `apps/exams/static/exams/js/final_center/history_filter.js`
- `apps/exams/static/exams/js/final_center/room_aggregate.js`
- `apps/exams/static/exams/js/final_center/room_monitor.js`
- `apps/exams/static/exams/js/final_center/snapshot_modal.js`
- `apps/exams/static/exams/js/final_center/waiting_room.js`
- `apps/exams/static/exams/js/final_result_timeout.js`
- `apps/exams/static/exams/js/paint_answer.js`
- `apps/exams/static/exams/js/profile_group_modal.js`
- `apps/exams/static/exams/js/profile_group_modal/checklist.js`
- `apps/exams/static/exams/js/profile_group_modal/controller.js`
- `apps/exams/static/exams/js/profile_group_modal/entry.js`
- `apps/exams/static/exams/js/profile_group_modal/namespace.js`
- `apps/exams/static/exams/js/questionBankList.js`
- `apps/exams/static/exams/js/questionWorkbench.js`
- `apps/exams/static/exams/js/question_form.js`
- `apps/exams/static/exams/js/question_submission_subjects.js`
- `apps/exams/static/exams/js/take_exam/config.js`
- `apps/exams/static/exams/js/take_exam/draft.js`
- `apps/exams/static/exams/js/take_exam/entry.js`
- `apps/exams/static/exams/js/take_exam/files.js`
- `apps/exams/static/exams/js/take_exam/namespace.js`
- `apps/exams/static/exams/js/take_exam/navigation.js`
- `apps/exams/static/exams/js/take_exam/notifications.js`
- `apps/exams/static/exams/js/take_exam/progress.js`
- `apps/exams/static/exams/js/take_exam/timers.js`
- `apps/exams/static/exams/js/teacher_check_attempt.js`
- `apps/exams/static/exams/js/teacher_exam_detail.js`
- `apps/exams/static/exams/js/teacher_questions_bank.js`
- `apps/exams/static/exams/js/testQuestionBank.js`
- `apps/live_exam/static/css/host_lobby/_part1.css`
- `apps/live_exam/static/css/host_lobby/_part2.css`
- `apps/live_exam/static/css/host_lobby/_part3.css`
- `apps/live_exam/static/css/host_lobby/_part4.css`
- `apps/live_exam/static/css/host_lobby/_part5.css`
- `apps/live_exam/static/css/host_lobby/_part6.css`
- `apps/live_exam/static/css/host_lobby/_part7.css`
- `apps/live_exam/static/css/host_lobby_shell/_part1.css`
- `apps/live_exam/static/css/host_lobby_shell/_part2.css`
- `apps/live_exam/static/css/join/_part1.css`
- `apps/live_exam/static/css/join/_part2.css`
- `apps/live_exam/static/css/live_avatar.css`
- `apps/live_exam/static/css/live_theme.css`
- `apps/live_exam/static/css/pin_entry.css`
- `apps/live_exam/static/css/player/_part1.css`
- `apps/live_exam/static/css/player/_part2.css`
- `apps/live_exam/static/css/player/_part3.css`
- `apps/live_exam/static/css/player/_part4.css`
- `apps/live_exam/static/css/teacher_live_results.css`
- `apps/live_exam/static/css/teacher_live_session_detail.css`
- `apps/live_exam/static/css/wait_room/_part1.css`
- `apps/live_exam/static/css/wait_room/_part2.css`
- `apps/live_exam/static/js/host_lobby.js`
- `apps/live_exam/static/js/host_lobby/api.js`
- `apps/live_exam/static/js/host_lobby/audio.js`
- `apps/live_exam/static/js/host_lobby/constants.js`
- `apps/live_exam/static/js/host_lobby/controller.js`
- `apps/live_exam/static/js/host_lobby/dom.js`
- `apps/live_exam/static/js/host_lobby/events.js`
- `apps/live_exam/static/js/host_lobby/host_lobby.entry.js`
- `apps/live_exam/static/js/host_lobby/lobby.js`
- `apps/live_exam/static/js/host_lobby/options.js`
- `apps/live_exam/static/js/host_lobby/podium.js`
- `apps/live_exam/static/js/host_lobby/presentation.js`
- `apps/live_exam/static/js/host_lobby/question.js`
- `apps/live_exam/static/js/host_lobby/reveal.js`
- `apps/live_exam/static/js/host_lobby/settings.js`
- `apps/live_exam/static/js/host_lobby/snapshot.js`
- `apps/live_exam/static/js/host_lobby/sockets.js`
- `apps/live_exam/static/js/host_lobby/state.js`
- `apps/live_exam/static/js/host_lobby/utils.js`
- `apps/live_exam/static/js/host_lobby_shell.js`
- `apps/live_exam/static/js/join.js`
- `apps/live_exam/static/js/live_avatar_catalog.js`
- `apps/live_exam/static/js/live_avatar_renderer.js`
- `apps/live_exam/static/js/pin_entry.js`
- `apps/live_exam/static/js/player.js`
- `apps/live_exam/static/js/player/answer.js`
- `apps/live_exam/static/js/player/api.js`
- `apps/live_exam/static/js/player/audio.js`
- `apps/live_exam/static/js/player/config.js`
- `apps/live_exam/static/js/player/dom.js`
- `apps/live_exam/static/js/player/events.js`
- `apps/live_exam/static/js/player/flow.js`
- `apps/live_exam/static/js/player/player.entry.js`
- `apps/live_exam/static/js/player/polling.js`
- `apps/live_exam/static/js/player/render.js`
- `apps/live_exam/static/js/player/settings.js`
- `apps/live_exam/static/js/player/sockets.js`
- `apps/live_exam/static/js/player/state.js`
- `apps/live_exam/static/js/player/timers.js`
- `apps/live_exam/static/js/player/ui.js`
- `apps/live_exam/static/js/player/utils.js`
- `apps/live_exam/static/js/wait_room.js`
- `apps/live_exam/static/js/wait_room_accessory_picker.js`
- `apps/live_exam/static/js/wait_room_avatar_picker.js`
- `apps/live_exam/static/js/wait_room_nickname_editor.js`
- `apps/live_exam/static/js/wait_room_page.js`
- `apps/live_exam/static/js/wait_room_reaction_panel.js`
- `apps/notifications/static/notifications/css/notifications.css`
- `apps/registrar/static/registrar/css/calendar.css`
- `apps/registrar/static/registrar/css/schedule.css`
- `apps/trial_exams/static/trial_exams/css/reply.css`
- `apps/trial_exams/static/trial_exams/css/trial_exam.css`
- `apps/trial_exams/static/trial_exams/js/trial_exam.js`
- `static/css/design-tokens.css`
- `static/css/navbar.css`
- `static/js/core/csrf.js`
- `static/js/csp_event_handlers.js`
- `static/js/route_loading.js`
- `static/vendor/codemirror/addon/hint/show-hint.css`
- `static/vendor/codemirror/lib/codemirror.js`

## Testlər, fixture-lər və load-testlər (125)

- `apps/accounts/tests/test_auth_membership.py`
- `apps/accounts/tests/test_auth_otp.py`
- `apps/accounts/tests/test_auth_signup.py`
- `apps/accounts/tests/test_auth_tenant_flows.py`
- `apps/accounts/tests/test_contact_inbox.py`
- `apps/accounts/tests/test_dashboard_refactor_characterization.py`
- `apps/accounts/tests/test_middleware.py`
- `apps/accounts/tests/test_models.py`
- `apps/accounts/tests/test_organization_refactor_characterization.py`
- `apps/accounts/tests/test_otp_api.py`
- `apps/accounts/tests/test_otp_registration_flow.py`
- `apps/accounts/tests/test_pending_registration_cache.py`
- `apps/accounts/tests/test_profile_permissions.py`
- `apps/accounts/tests/test_profile_refactor_characterization.py`
- `apps/accounts/tests/test_profile_views.py`
- `apps/accounts/tests/test_provision_student_credentials.py`
- `apps/accounts/tests/test_roles_refactor_characterization.py`
- `apps/accounts/tests/test_security_controls.py`
- `apps/accounts/tests/test_services.py`
- `apps/accounts/tests/test_superadmin_org_inspector.py`
- `apps/accounts/tests/test_view_as.py`
- `apps/appeals/tests/__init__.py`
- `apps/appeals/tests/test_creation.py`
- `apps/appeals/tests/test_effective_display.py`
- `apps/appeals/tests/test_scoring.py`
- `apps/appeals/tests/test_window.py`
- `apps/courses/tests/test_integrity.py`
- `apps/courses/tests/test_models.py`
- `apps/courses/tests/test_services.py`
- `apps/courses/tests/test_tenant_isolation.py`
- `apps/courses/tests/test_views.py`
- `apps/exams/static/exams/css/test_question_bank/_part1.css`
- `apps/exams/static/exams/css/test_question_bank/_part2.css`
- `apps/exams/static/exams/css/test_question_bank/_part3.css`
- `apps/exams/templates/exams/teacher/test_question_bank.html`
- `apps/exams/tests/__init__.py`
- `apps/exams/tests/test_answer_snapshot.py`
- `apps/exams/tests/test_attempt_constraints.py`
- `apps/exams/tests/test_attempt_timer.py`
- `apps/exams/tests/test_coding_exam.py`
- `apps/exams/tests/test_coding_exam_frontend_assets.py`
- `apps/exams/tests/test_exam_center_policy.py`
- `apps/exams/tests/test_exam_center_stats_charts.py`
- `apps/exams/tests/test_exam_room_admin.py`
- `apps/exams/tests/test_final_center_cabinet.py`
- `apps/exams/tests/test_final_center_consumers.py`
- `apps/exams/tests/test_final_center_flow.py`
- `apps/exams/tests/test_final_center_pins.py`
- `apps/exams/tests/test_final_exam_center_page.py`
- `apps/exams/tests/test_forms.py`
- `apps/exams/tests/test_group_unit_scope.py`
- `apps/exams/tests/test_language_variants.py`
- `apps/exams/tests/test_models.py`
- `apps/exams/tests/test_pin_lookup.py`
- `apps/exams/tests/test_question_bank_attach.py`
- `apps/exams/tests/test_question_submission.py`
- `apps/exams/tests/test_question_word_export.py`
- `apps/exams/tests/test_result_calculation.py`
- `apps/exams/tests/test_results_duration.py`
- `apps/exams/tests/test_services.py`
- `apps/exams/tests/test_student_pin_throttle.py`
- `apps/exams/tests/test_supervision_consumer.py`
- `apps/exams/tests/test_text_extraction_jobs.py`
- `apps/exams/tests/test_views.py`
- `apps/exams/tests/test_wizard_enhancements.py`
- `apps/live_exam/tests/__init__.py`
- `apps/live_exam/tests/test_answer_integrity.py`
- `apps/live_exam/tests/test_architecture.py`
- `apps/live_exam/tests/test_consumers.py`
- `apps/live_exam/tests/test_models.py`
- `apps/live_exam/tests/test_reveal_gating.py`
- `apps/live_exam/tests/test_round_scenario.py`
- `apps/live_exam/tests/test_score_integrity.py`
- `apps/live_exam/tests/test_scoring.py`
- `apps/live_exam/tests/test_services.py`
- `apps/live_exam/tests/test_session_settings.py`
- `apps/live_exam/tests/test_views.py`
- `apps/notifications/tests/test_notification_events.py`
- `apps/notifications/tests/test_notifications.py`
- `apps/notifications/tests/test_purge_command.py`
- `apps/notifications/tests/test_services_refactor_characterization.py`
- `apps/organizations/tests/test_backfill_admin_memberships.py`
- `apps/organizations/tests/test_decorators.py`
- `apps/organizations/tests/test_i18n_smoke.py`
- `apps/organizations/tests/test_models.py`
- `apps/organizations/tests/test_permissions.py`
- `apps/organizations/tests/test_rbac.py`
- `apps/organizations/tests/test_seed_ci_e2e_scenario.py`
- `apps/organizations/tests/test_seed_ci_e2e_user.py`
- `apps/organizations/tests/test_seed_western_caspian.py`
- `apps/organizations/tests/test_structure_views.py`
- `apps/organizations/tests/test_tenant_isolation.py`
- `apps/organizations/tests/test_unit_scoping.py`
- `apps/organizations/tests/test_views.py`
- `apps/registrar/tests/test_analytics.py`
- `apps/registrar/tests/test_cabinet_ui.py`
- `apps/registrar/tests/test_calendar.py`
- `apps/registrar/tests/test_components.py`
- `apps/registrar/tests/test_final_extras.py`
- `apps/registrar/tests/test_finals.py`
- `apps/registrar/tests/test_grade_audit.py`
- `apps/registrar/tests/test_grading_scale.py`
- `apps/registrar/tests/test_journal_export.py`
- `apps/registrar/tests/test_journal_views.py`
- `apps/registrar/tests/test_schedule.py`
- `apps/registrar/tests/test_services.py`
- `apps/registrar/tests/test_transcript.py`
- `apps/registrar/tests/test_transcript_pdf.py`
- `apps/trial_exams/tests/__init__.py`
- `apps/trial_exams/tests/conftest.py`
- `apps/trial_exams/tests/test_forms.py`
- `apps/trial_exams/tests/test_services.py`
- `apps/trial_exams/tests/test_views.py`
- `core/tests/test_admin_2fa.py`
- `core/tests/test_email_tasks.py`
- `core/tests/test_error_handlers.py`
- `core/tests/test_media_views.py`
- `core/tests/test_metrics.py`
- `core/tests/test_permissions.py`
- `k6/dashboard-navigation-test.js`
- `k6/final-exam-center-test.js`
- `k6/lib/emsarena.js`
- `k6/mixed-realistic-load-test.js`
- `k6/student-exam-flow-test.js`
- `scripts/stress_exam_capacity.sh`

## Deployment, settings, monitorinq və sənədlər (80)

- `apps/live_exam/session_settings.py`
- `config/asgi.py`
- `config/settings/base.py`
- `config/settings/components/admin_ratelimit.py`
- `config/settings/components/apps.py`
- `config/settings/components/celery_cache.py`
- `config/settings/components/email.py`
- `config/settings/components/exam.py`
- `config/settings/components/integrations.py`
- `config/settings/components/security.py`
- `config/settings/local.py`
- `config/settings/production.py`
- `config/settings/test.py`
- `core/settings_utils.py`
- `docker-compose.prod.yml`
- `docker/arp-agent/arp_agent.py`
- `docker/nginx/nginx.conf`
- `docker/piston-bootstrap.sh`
- `docker/prometheus/alerts.yml`
- `docs/ACCOUNT_PROVISIONING.md`
- `docs/AJAX_SAFE_JS_PATTERN.md`
- `docs/AKADEMIK_DOVR_SISTEMI_DIZAYN_P3-2.md`
- `docs/CODEX_PROMPT_FRONTEND_REFACTOR.md`
- `docs/CODEX_PROMPT_P0-1_TRANSACTION_POOLING.md`
- `docs/CODEX_PROMPT_P3-1_ACCESSIBILITY.md`
- `docs/DEMO_TEST_USERS.md`
- `docs/FAZA2_3B_TRANSACTION_POOLING.md`
- `docs/FAZA4_BASELINE_RESULTS.md`
- `docs/FAZA4_STAGING_RUNBOOK.md`
- `docs/FAZA4_TASK1_AUDIT.md`
- `docs/FINAL_EXAM_CENTER_REPORT.md`
- `docs/ORGANIZATION_SYSTEM.md`
- `docs/PERFORMANCE_NOTES.md`
- `docs/REFACTOR_PLAN_profile_main.md`
- `docs/UI_COLOR_TOKENS_MIGRASIYA.md`
- `docs/UNIVERSITY_SYSTEM_ROADMAP.md`
- `docs/architecture.md`
- `docs/architecture/access-control/access-control-gaps.md`
- `docs/architecture/access-control/authorization-analysis.md`
- `docs/architecture/access-control/authorization-scope.drawio`
- `docs/architecture/access-control/authorization-scope.mmd`
- `docs/architecture/access-control/permission-matrix.md`
- `docs/architecture/access-control/role-hierarchy.drawio`
- `docs/architecture/access-control/role-hierarchy.md`
- `docs/architecture/access-control/role-hierarchy.mmd`
- `docs/architecture/access-control/role-hierarchy.svg`
- `docs/architecture/architecture-summary.json`
- `docs/architecture/database/data-dictionary.md`
- `docs/architecture/database/database-issues.md`
- `docs/architecture/database/database-overview.md`
- `docs/architecture/database/domains/academic-erd.drawio`
- `docs/architecture/database/domains/academic-erd.mmd`
- `docs/architecture/database/domains/appeals-erd.drawio`
- `docs/architecture/database/domains/appeals-erd.mmd`
- `docs/architecture/database/domains/exams-erd.drawio`
- `docs/architecture/database/domains/exams-erd.mmd`
- `docs/architecture/database/domains/grading-journal-erd.drawio`
- `docs/architecture/database/domains/grading-journal-erd.mmd`
- `docs/architecture/database/domains/organization-structure-hierarchy.drawio`
- `docs/architecture/database/domains/organization-structure-hierarchy.mmd`
- `docs/architecture/database/domains/organization-structure-hierarchy.svg`
- `docs/architecture/database/emsarena-global-erd.drawio`
- `docs/architecture/database/emsarena-global-erd.mmd`
- `docs/architecture/database/emsarena-global-erd.svg`
- `docs/architecture/database/emsarena-relationships-clean.drawio`
- `docs/architecture/database/relationship-report.md`
- `docs/architecture/database/tenant-boundary-report.md`
- `docs/deployment.md`
- `docs/exam_supervision_realtime.md`
- `docs/models.md`
- `docs/otp_auth.md`
- `docs/qa/2026-03-27-e2e-qa-audit.md`
- `docs/qa/SKIP_XFAIL_AUDIT_2026-07-02.md`
- `docs/tenant-isolation-checklist.md`
- `requirements/base.txt`
- `scripts/check_worker_atomic_coverage.py`
- `scripts/i18n_fix4.py`
- `scripts/module_deps_baseline.json`
- `scripts/module_size_budget.json`
- `scripts/sync_contact_about_translations.py`

## Digər inteqrasiya faylları (57)

- `apps/accounts/queries/__init__.py`
- `apps/accounts/queries/assignments.py`
- `apps/accounts/roles.py`
- `apps/appeals/__init__.py`
- `apps/appeals/apps.py`
- `apps/appeals/constants.py`
- `apps/audit/tests.py`
- `apps/courses/signals.py`
- `apps/exams/__init__.py`
- `apps/exams/admin.py`
- `apps/exams/apps.py`
- `apps/exams/constants.py`
- `apps/exams/export_registry.py`
- `apps/exams/features.py`
- `apps/exams/management/__init__.py`
- `apps/exams/navigation.py`
- `apps/exams/score_adjustments.py`
- `apps/exams/signals.py`
- `apps/exams/templatetags/__init__.py`
- `apps/exams/templatetags/exam_filters.py`
- `apps/exams/templatetags/exams_ui.py`
- `apps/exams/validators.py`
- `apps/live_exam/__init__.py`
- `apps/live_exam/admin.py`
- `apps/live_exam/apps.py`
- `apps/live_exam/auth.py`
- `apps/live_exam/cache.py`
- `apps/live_exam/constants.py`
- `apps/live_exam/scoring.py`
- `apps/live_exam/transport.py`
- `apps/notifications/signals.py`
- `apps/organizations/admin.py`
- `apps/organizations/cabinet_modules.py`
- `apps/organizations/default_roles.py`
- `apps/organizations/middleware.py`
- `apps/registrar/admin.py`
- `apps/registrar/analytics.py`
- `apps/registrar/finals.py`
- `apps/registrar/gradebook.py`
- `apps/registrar/journal_export.py`
- `apps/registrar/page_contexts.py`
- `apps/registrar/schedule.py`
- `apps/registrar/transcript.py`
- `apps/registrar/transcript_pdf.py`
- `apps/trial_exams/__init__.py`
- `apps/trial_exams/admin.py`
- `apps/trial_exams/apps.py`
- `core/admin_security.py`
- `core/cache.py`
- `core/constants.py`
- `core/context_processors.py`
- `core/helpers.py`
- `core/mailing.py`
- `core/metrics.py`
- `core/roles.py`
- `core/tenancy.py`
- `pyproject.toml`


---

# Simvol və əməliyyat indeksi

Bu indeks Python AST-si və source-line axtarışı ilə yaradılıb. Private helper-lər view/permission/cache sərhədində daxil edilib; servis indeksində isə public funksiyalar göstərilir.

## Django modelləri (35)

- `apps/appeals/models.py:28` — `Appeal`
- `apps/appeals/models.py:106` — `AppealItem`
- `apps/appeals/models.py:183` — `ScoreAdjustment`
- `apps/exams/domain/access_policy.py:12` — `StudentGroup`
- `apps/exams/domain/ai_config.py:17` — `AIConfiguration`
- `apps/exams/domain/attempts.py:332` — `ExamAnswer`
- `apps/exams/domain/attempts.py:387` — `ExamAnswerFile`
- `apps/exams/domain/attempts.py:16` — `ExamAttempt`
- `apps/exams/domain/attempts.py:411` — `ProctoringLog`
- `apps/exams/domain/coding.py:8` — `CodingExamQuestion`
- `apps/exams/domain/coding.py:290` — `CodingFile`
- `apps/exams/domain/coding.py:166` — `CodingSubmission`
- `apps/exams/domain/coding.py:115` — `CodingTestCase`
- `apps/exams/domain/exam_definition.py:22` — `Exam`
- `apps/exams/domain/exam_definition.py:336` — `QuestionBlock`
- `apps/exams/domain/final_center.py:99` — `ExamRoom`
- `apps/exams/domain/final_center.py:181` — `ExamRoomComputer`
- `apps/exams/domain/final_center.py:284` — `ExamRoomSession`
- `apps/exams/domain/final_center.py:425` — `FinalExamTicket`
- `apps/exams/domain/import_jobs.py:31` — `TextExtractionJob`
- `apps/exams/domain/language.py:19` — `ExamLanguageVariant`
- `apps/exams/domain/question_bank/bank_question.py:25` — `BankQuestion`
- `apps/exams/domain/question_bank/bank_question.py:139` — `BankQuestionOption`
- `apps/exams/domain/question_bank/exam_question.py:137` — `ExamQuestion`
- `apps/exams/domain/question_bank/exam_question.py:379` — `ExamQuestionOption`
- `apps/exams/domain/question_bank/exam_question.py:21` — `QuestionBank`
- `apps/exams/domain/student_access.py:20` — `ExamStudentPin`
- `apps/exams/domain/student_access.py:53` — `StudentExamAttemptGrant`
- `apps/exams/domain/submission_inbox.py:28` — `QuestionSubmission`
- `apps/exams/domain/supervision.py:15` — `ExamSupervisionConfig`
- `apps/exams/domain/supervision.py:192` — `SupervisionIncident`
- `apps/live_exam/models.py:169` — `LiveAnswer`
- `apps/live_exam/models.py:126` — `LivePlayer`
- `apps/live_exam/models.py:26` — `LiveSession`
- `apps/trial_exams/models.py:38` — `TrialExamRequest`

## Form sinifləri (11)

- `apps/exams/forms/bank_question.py:19` — `BankQuestionCreateForm`
- `apps/exams/forms/coding.py:86` — `CodingExamQuestionForm`
- `apps/exams/forms/exam.py:29` — `ExamForm`
- `apps/exams/forms/exam_coding_fields.py:11` — `CodingExamFieldsMixin`
- `apps/exams/forms/final_center.py:83` — `AssignStudentsForm`
- `apps/exams/forms/final_center.py:10` — `ExamRoomForm`
- `apps/exams/forms/final_center.py:34` — `ExamRoomSessionForm`
- `apps/exams/forms/group.py:71` — `StudentGroupForm`
- `apps/exams/forms/group.py:23` — `UserMetadataSelectMultiple`
- `apps/exams/forms/question.py:15` — `ExamQuestionCreateForm`
- `apps/trial_exams/forms.py:37` — `TrialExamRequestForm`

## View və endpoint funksiyaları (431)

- `apps/appeals/views/shared/_helpers.py:4` — `_marked_question_map`
- `apps/appeals/views/shared/detail.py:32` — `_appeal_item_stats`
- `apps/appeals/views/shared/detail.py:56` — `_appeal_positive_bonus`
- `apps/appeals/views/shared/detail.py:46` — `_format_decimal`
- `apps/appeals/views/shared/detail.py:70` — `appeal_detail`
- `apps/appeals/views/student/endpoints.py:54` — `_is_final_exam`
- `apps/appeals/views/student/endpoints.py:36` — `_is_profile_results_request`
- `apps/appeals/views/student/endpoints.py:58` — `_parse_items_from_post`
- `apps/appeals/views/student/endpoints.py:43` — `_result_url`
- `apps/appeals/views/student/endpoints.py:80` — `appeal_create`
- `apps/appeals/views/student/endpoints.py:152` — `build_my_appeals_context`
- `apps/appeals/views/student/endpoints.py:188` — `my_appeals`
- `apps/appeals/views/teacher/endpoints.py:71` — `_appeal_edit_seconds_left`
- `apps/appeals/views/teacher/endpoints.py:50` — `_can_open_appeal_management`
- `apps/appeals/views/teacher/endpoints.py:84` — `_current_review_score`
- `apps/appeals/views/teacher/endpoints.py:45` — `_format_decimal`
- `apps/appeals/views/teacher/endpoints.py:40` — `_format_seconds`
- `apps/appeals/views/teacher/endpoints.py:94` — `build_manage_appeals_context`
- `apps/appeals/views/teacher/endpoints.py:54` — `count_pending_manage_appeals`
- `apps/appeals/views/teacher/endpoints.py:185` — `manage_appeals`
- `apps/appeals/views/teacher/endpoints.py:208` — `review_appeal`
- `apps/exams/views/exam_center/_shared.py:16` — `center_org_or_403`
- `apps/exams/views/exam_center/_shared.py:83` — `center_staff_queryset`
- `apps/exams/views/exam_center/_shared.py:38` — `get_center_session_or_404`
- `apps/exams/views/exam_center/_shared.py:65` — `get_center_ticket_or_404`
- `apps/exams/views/exam_center/_shared.py:57` — `get_session_ticket_or_404`
- `apps/exams/views/exam_center/_shared.py:29` — `supervisor_org_or_403`
- `apps/exams/views/exam_center/_shared.py:77` — `visible_sessions_qs`
- `apps/exams/views/exam_center/monitor.py:252` — `exam_center_session_cancel`
- `apps/exams/views/exam_center/monitor.py:233` — `exam_center_session_end`
- `apps/exams/views/exam_center/monitor.py:34` — `exam_center_session_monitor`
- `apps/exams/views/exam_center/monitor.py:186` — `exam_center_session_open_entry`
- `apps/exams/views/exam_center/monitor.py:52` — `exam_center_session_snapshot`
- `apps/exams/views/exam_center/monitor.py:201` — `exam_center_session_start`
- `apps/exams/views/exam_center/monitor.py:118` — `exam_center_ticket_reentry`
- `apps/exams/views/exam_center/monitor.py:266` — `exam_center_ticket_remove`
- `apps/exams/views/exam_center/monitor.py:94` — `exam_center_ticket_resume`
- `apps/exams/views/exam_center/monitor.py:59` — `exam_center_ticket_snapshot`
- `apps/exams/views/exam_center/pin_lookup.py:53` — `_kafedra_subquery`
- `apps/exams/views/exam_center/pin_lookup.py:65` — `_pin_holder_student_queryset`
- `apps/exams/views/exam_center/pin_lookup.py:37` — `exam_center_pin_lookup`
- `apps/exams/views/exam_center/pin_lookup.py:82` — `exam_center_pin_search`
- `apps/exams/views/exam_center/pin_lookup.py:122` — `exam_center_student_pins`
- `apps/exams/views/exam_center/reports.py:58` — `_export_csv`
- `apps/exams/views/exam_center/reports.py:20` — `exam_center_reports`
- `apps/exams/views/exam_center/room_monitor.py:41` — `_get_room_and_sessions`
- `apps/exams/views/exam_center/room_monitor.py:57` — `_monitor_labels`
- `apps/exams/views/exam_center/room_monitor.py:114` — `_room_computer_grid`
- `apps/exams/views/exam_center/room_monitor.py:36` — `_user_is_room_invigilator`
- `apps/exams/views/exam_center/room_monitor.py:167` — `exam_center_room_assign_invigilators`
- `apps/exams/views/exam_center/room_monitor.py:135` — `exam_center_room_monitor`
- `apps/exams/views/exam_center/room_monitor.py:257` — `exam_center_room_open_all`
- `apps/exams/views/exam_center/room_monitor.py:208` — `exam_center_room_snapshot`
- `apps/exams/views/exam_center/room_monitor.py:216` — `exam_center_room_start_all`
- `apps/exams/views/exam_center/rooms.py:24` — `exam_center_room_list`
- `apps/exams/views/exam_center/sessions.py:209` — `exam_center_assign_students`
- `apps/exams/views/exam_center/sessions.py:170` — `exam_center_finals`
- `apps/exams/views/exam_center/sessions.py:70` — `exam_center_session_create`
- `apps/exams/views/exam_center/sessions.py:111` — `exam_center_session_detail`
- `apps/exams/views/exam_center/sessions.py:136` — `exam_center_session_history`
- `apps/exams/views/exam_center/sessions.py:44` — `exam_center_session_list`
- `apps/exams/views/exam_center/sessions.py:263` — `exam_center_ticket_pin`
- `apps/exams/views/exam_center/sessions.py:313` — `exam_center_ticket_readmit`
- `apps/exams/views/exam_center/sessions.py:297` — `exam_center_ticket_seat`
- `apps/exams/views/exam_center/statistics.py:50` — `_csv_ints`
- `apps/exams/views/exam_center/statistics.py:113` — `_dedup`
- `apps/exams/views/exam_center/statistics.py:64` — `_filtered_attempts`
- `apps/exams/views/exam_center/statistics.py:122` — `_row`
- `apps/exams/views/exam_center/statistics.py:101` — `_sorted`
- `apps/exams/views/exam_center/statistics.py:43` — `_stats_org`
- `apps/exams/views/exam_center/statistics.py:54` — `_unit_ids_with_children`
- `apps/exams/views/exam_center/statistics.py:151` — `exam_center_stats_data`
- `apps/exams/views/exam_center/statistics.py:188` — `exam_center_stats_export`
- `apps/exams/views/exam_center/statistics.py:239` — `exam_center_stats_filters`
- `apps/exams/views/exam_center/statistics_charts.py:96` — `_by_subject`
- `apps/exams/views/exam_center/statistics_charts.py:77` — `_by_type`
- `apps/exams/views/exam_center/statistics_charts.py:114` — `_chart_payload`
- `apps/exams/views/exam_center/statistics_charts.py:43` — `_distribution`
- `apps/exams/views/exam_center/statistics_charts.py:59` — `_monthly`
- `apps/exams/views/exam_center/statistics_charts.py:39` — `_rnd`
- `apps/exams/views/exam_center/statistics_charts.py:34` — `_scored`
- `apps/exams/views/exam_center/statistics_charts.py:143` — `exam_center_stats_ai`
- `apps/exams/views/exam_center/statistics_charts.py:134` — `exam_center_stats_charts`
- `apps/exams/views/shared/access.py:46` — `_is_ajax_request`
- `apps/exams/views/shared/access.py:50` — `_json_redirect_response`
- `apps/exams/views/shared/access.py:30` — `_resolve_exam_failure_redirect`
- `apps/exams/views/shared/access.py:16` — `_safe_same_origin_redirect_path`
- `apps/exams/views/shared/access.py:57` — `exam_code_check`
- `apps/exams/views/shared/tenant.py:33` — `ensure_teacher_exam_tenant_context`
- `apps/exams/views/shared/tenant.py:79` — `exam_in_active_tenant`
- `apps/exams/views/shared/tenant.py:13` — `get_active_organization`
- `apps/exams/views/shared/tenant.py:60` — `get_result_viewable_exam_or_404`
- `apps/exams/views/shared/tenant.py:52` — `get_teacher_exam_or_404`
- `apps/exams/views/shared/tenant.py:17` — `tenant_scoped_exams`
- `apps/exams/views/student/_helpers.py:28` — `annotate_attempt_result_visibility`
- `apps/exams/views/student/_helpers.py:24` — `are_exam_results_hidden_from_student`
- `apps/exams/views/student/_helpers.py:18` — `ensure_student_exam_tenant_context`
- `apps/exams/views/student/attempts.py:41` — `_attempt_answers_queryset`
- `apps/exams/views/student/attempts.py:114` — `_correct_question_option_ids`
- `apps/exams/views/student/attempts.py:63` — `_finished_attempt_response`
- `apps/exams/views/student/attempts.py:316` — `_handle_take_exam_post`
- `apps/exams/views/student/attempts.py:59` — `_is_ajax_request`
- `apps/exams/views/student/attempts.py:209` — `_marked_question_ids_from_request`
- `apps/exams/views/student/attempts.py:77` — `_posted_autosave_question_ids`
- `apps/exams/views/student/attempts.py:249` — `_previous_attempts_for_context`
- `apps/exams/views/student/attempts.py:270` — `_resolve_exam_failure_redirect`
- `apps/exams/views/student/attempts.py:237` — `_save_marked_question_ids_from_request`
- `apps/exams/views/student/attempts.py:118` — `_save_test_answer_if_changed`
- `apps/exams/views/student/attempts.py:149` — `_save_written_answer_if_changed`
- `apps/exams/views/student/attempts.py:91` — `_selected_option_ids_from_request`
- `apps/exams/views/student/attempts.py:110` — `_valid_question_option_ids`
- `apps/exams/views/student/attempts.py:287` — `start_exam`
- `apps/exams/views/student/attempts.py:436` — `take_exam`
- `apps/exams/views/student/coding.py:304` — `_build_submission_input`
- `apps/exams/views/student/coding.py:329` — `_build_submission_items`
- `apps/exams/views/student/coding.py:44` — `_coding_disabled_error`
- `apps/exams/views/student/coding.py:83` — `_get_attempt_coding_question`
- `apps/exams/views/student/coding.py:69` — `_get_attempt_coding_questions`
- `apps/exams/views/student/coding.py:55` — `_get_coding_attempt`
- `apps/exams/views/student/coding.py:151` — `_get_submission_download_attempt`
- `apps/exams/views/student/coding.py:37` — `_json_error`
- `apps/exams/views/student/coding.py:184` — `_latest_draft_submissions_by_question`
- `apps/exams/views/student/coding.py:48` — `_parse_json_body`
- `apps/exams/views/student/coding.py:118` — `_safe_archive_name`
- `apps/exams/views/student/coding.py:199` — `_serialize_coding_question`
- `apps/exams/views/student/coding.py:172` — `_serialize_visible_test_cases`
- `apps/exams/views/student/coding.py:131` — `_submission_file_items`
- `apps/exams/views/student/coding.py:102` — `_submission_payload`
- `apps/exams/views/student/coding.py:377` — `coding_autosave`
- `apps/exams/views/student/coding.py:409` — `coding_run`
- `apps/exams/views/student/coding.py:276` — `coding_submission_download`
- `apps/exams/views/student/coding.py:487` — `coding_submit`
- `apps/exams/views/student/coding.py:225` — `take_coding_exam`
- `apps/exams/views/student/final_center.py:76` — `_ensure_hall_access`
- `apps/exams/views/student/final_center.py:94` — `_entry_error_message`
- `apps/exams/views/student/final_center.py:351` — `_handle_confirm`
- `apps/exams/views/student/final_center.py:212` — `_handle_login`
- `apps/exams/views/student/final_center.py:254` — `_handle_student_pin_login`
- `apps/exams/views/student/final_center.py:106` — `_render_login`
- `apps/exams/views/student/final_center.py:379` — `_resolve_own_ticket`
- `apps/exams/views/student/final_center.py:87` — `_room_access_error`
- `apps/exams/views/student/final_center.py:82` — `_room_access_ok`
- `apps/exams/views/student/final_center.py:132` — `_route_validated_ticket`
- `apps/exams/views/student/final_center.py:164` — `_validated_session_ticket`
- `apps/exams/views/student/final_center.py:450` — `final_exam_begin`
- `apps/exams/views/student/final_center.py:436` — `final_exam_cancel`
- `apps/exams/views/student/final_center.py:177` — `final_exam_entry`
- `apps/exams/views/student/final_center.py:395` — `final_exam_waiting`
- `apps/exams/views/student/final_center.py:480` — `final_ticket_state`
- `apps/exams/views/student/lists.py:259` — `_annotate_exam_list_base`
- `apps/exams/views/student/lists.py:90` — `_apply_exam_type_filter`
- `apps/exams/views/student/lists.py:112` — `_apply_sort`
- `apps/exams/views/student/lists.py:275` — `_build_exam_items`
- `apps/exams/views/student/lists.py:237` — `_build_language_modal_context`
- `apps/exams/views/student/lists.py:127` — `_build_type_counts`
- `apps/exams/views/student/lists.py:208` — `_build_type_tabs`
- `apps/exams/views/student/lists.py:178` — `_display_type`
- `apps/exams/views/student/lists.py:69` — `_exclude_attempt_exhausted`
- `apps/exams/views/student/lists.py:84` — `_exclude_expired_exams`
- `apps/exams/views/student/lists.py:64` — `_live_session_exists_sq`
- `apps/exams/views/student/lists.py:151` — `_live_session_map`
- `apps/exams/views/student/lists.py:107` — `_normalize_sort`
- `apps/exams/views/student/lists.py:328` — `_render_exam_list`
- `apps/exams/views/student/lists.py:191` — `_type_label`
- `apps/exams/views/student/lists.py:50` — `_user_finished_attempt_count_sq`
- `apps/exams/views/student/lists.py:408` — `assigned_student_exam_list`
- `apps/exams/views/student/lists.py:438` — `student_exam_list`
- `apps/exams/views/student/results.py:87` — `_coding_submission_file_items`
- `apps/exams/views/student/results.py:81` — `_default_exam_back_url`
- `apps/exams/views/student/results.py:54` — `_final_entry_url`
- `apps/exams/views/student/results.py:63` — `_final_result_remaining_seconds`
- `apps/exams/views/student/results.py:58` — `_final_result_timeout_url`
- `apps/exams/views/student/results.py:71` — `_format_score_delta`
- `apps/exams/views/student/results.py:46` — `_hide_test_answer_correctness_in_cabinet`
- `apps/exams/views/student/results.py:35` — `_is_final_exam`
- `apps/exams/views/student/results.py:39` — `_is_profile_results_request`
- `apps/exams/views/student/results.py:107` — `_resolve_result_navigation`
- `apps/exams/views/student/results.py:123` — `exam_result`
- `apps/exams/views/student/results.py:327` — `student_exam_history`
- `apps/exams/views/student/script_data.py:6` — `take_exam_script_data`
- `apps/exams/views/teacher/exams/_shared.py:171` — `_bind_selected_organization`
- `apps/exams/views/teacher/exams/_shared.py:270` — `_build_group_student_map`
- `apps/exams/views/teacher/exams/_shared.py:111` — `_ensure_exam_permission`
- `apps/exams/views/teacher/exams/_shared.py:133` — `_exam_detail_question_queryset`
- `apps/exams/views/teacher/exams/_shared.py:215` — `_get_deleted_exam_or_404`
- `apps/exams/views/teacher/exams/_shared.py:204` — `_get_editable_exam_or_404`
- `apps/exams/views/teacher/exams/_shared.py:149` — `_get_exam_detail_question_page`
- `apps/exams/views/teacher/exams/_shared.py:291` — `_get_requested_course_for_exam`
- `apps/exams/views/teacher/exams/_shared.py:52` — `_is_internal_exam_management_path`
- `apps/exams/views/teacher/exams/_shared.py:107` — `_is_superadmin`
- `apps/exams/views/teacher/exams/_shared.py:129` — `_organization_selection_queryset`
- `apps/exams/views/teacher/exams/_shared.py:119` — `_organization_selection_redirect`
- `apps/exams/views/teacher/exams/_shared.py:137` — `_positive_int`
- `apps/exams/views/teacher/exams/_shared.py:75` — `_resolve_profile_navigation`
- `apps/exams/views/teacher/exams/_shared.py:185` — `_resolve_required_organization`
- `apps/exams/views/teacher/exams/_shared.py:163` — `_resolve_selected_superadmin_organization`
- `apps/exams/views/teacher/exams/_shared.py:123` — `_restore_superadmin_profile_organization`
- `apps/exams/views/teacher/exams/_shared.py:30` — `_safe_same_origin_redirect_path`
- `apps/exams/views/teacher/exams/_shared.py:232` — `_selected_access_entities`
- `apps/exams/views/teacher/exams/_shared.py:26` — `_teacher_profile_my_exams_url`
- `apps/exams/views/teacher/exams/actions.py:88` — `delete_exam`
- `apps/exams/views/teacher/exams/actions.py:243` — `deleted_exams_list`
- `apps/exams/views/teacher/exams/actions.py:210` — `duplicate_exam`
- `apps/exams/views/teacher/exams/actions.py:325` — `permanent_delete_exam`
- `apps/exams/views/teacher/exams/actions.py:278` — `restore_exam`
- `apps/exams/views/teacher/exams/actions.py:29` — `toggle_exam_active`
- `apps/exams/views/teacher/exams/actions.py:150` — `toggle_exam_archive`
- `apps/exams/views/teacher/exams/actions.py:58` — `toggle_exam_results_visibility`
- `apps/exams/views/teacher/exams/attempt_grants.py:25` — `_is_ajax`
- `apps/exams/views/teacher/exams/attempt_grants.py:31` — `grant_extra_attempt`
- `apps/exams/views/teacher/exams/list_detail.py:51` — `createAndEditExamView`
- `apps/exams/views/teacher/exams/list_detail.py:268` — `teacher_exam_detail`
- `apps/exams/views/teacher/exams/list_detail.py:321` — `teacher_exam_detail_questions_page`
- `apps/exams/views/teacher/exams/list_detail.py:42` — `teacher_exam_list`
- `apps/exams/views/teacher/exams/lookups.py:74` — `_org_user_queryset`
- `apps/exams/views/teacher/exams/lookups.py:28` — `_page_bounds`
- `apps/exams/views/teacher/exams/lookups.py:46` — `_paginate`
- `apps/exams/views/teacher/exams/lookups.py:221` — `assigned_student_count`
- `apps/exams/views/teacher/exams/lookups.py:252` — `exam_available_question_count`
- `apps/exams/views/teacher/exams/lookups.py:88` — `group_search`
- `apps/exams/views/teacher/exams/lookups.py:165` — `invigilator_search`
- `apps/exams/views/teacher/exams/lookups.py:54` — `subject_search`
- `apps/exams/views/teacher/exams/lookups.py:108` — `user_search`
- `apps/exams/views/teacher/extract_jobs.py:39` — `_ensure_job_progress`
- `apps/exams/views/teacher/extract_jobs.py:28` — `_job_payload`
- `apps/exams/views/teacher/extract_jobs.py:229` — `_serve_export_file`
- `apps/exams/views/teacher/extract_jobs.py:267` — `export_job_download`
- `apps/exams/views/teacher/extract_jobs.py:247` — `export_job_waiting`
- `apps/exams/views/teacher/extract_jobs.py:74` — `start_ai_generation_job`
- `apps/exams/views/teacher/extract_jobs.py:191` — `start_export_job`
- `apps/exams/views/teacher/extract_jobs.py:129` — `start_text_extraction`
- `apps/exams/views/teacher/extract_jobs.py:184` — `text_extraction_status`
- `apps/exams/views/teacher/groups.py:64` — `_can_multi_assign_teachers`
- `apps/exams/views/teacher/groups.py:129` — `_create_group_template_context`
- `apps/exams/views/teacher/groups.py:58` — `_ensure_group_creator`
- `apps/exams/views/teacher/groups.py:23` — `_ensure_group_manager`
- `apps/exams/views/teacher/groups.py:85` — `_get_required_organization`
- `apps/exams/views/teacher/groups.py:118` — `_group_form_for_request`
- `apps/exams/views/teacher/groups.py:97` — `_group_queryset_for_actor`
- `apps/exams/views/teacher/groups.py:19` — `_is_superadmin`
- `apps/exams/views/teacher/groups.py:72` — `_resolve_next_url`
- `apps/exams/views/teacher/groups.py:41` — `_user_can_create_group`
- `apps/exams/views/teacher/groups.py:370` — `create_student_group`
- `apps/exams/views/teacher/groups.py:332` — `teacher_add_student_to_group`
- `apps/exams/views/teacher/groups.py:163` — `teacher_create_group`
- `apps/exams/views/teacher/groups.py:272` — `teacher_delete_group`
- `apps/exams/views/teacher/groups.py:142` — `teacher_group_list`
- `apps/exams/views/teacher/groups.py:301` — `teacher_remove_student_from_group`
- `apps/exams/views/teacher/groups.py:212` — `teacher_update_group`
- `apps/exams/views/teacher/languages.py:40` — `_build_variant_rows`
- `apps/exams/views/teacher/languages.py:53` — `_empty_analysis`
- `apps/exams/views/teacher/languages.py:69` — `_language_workbench_context`
- `apps/exams/views/teacher/languages.py:36` — `_manager_url`
- `apps/exams/views/teacher/languages.py:64` — `_variant_language_options`
- `apps/exams/views/teacher/languages.py:88` — `exam_language_manager`
- `apps/exams/views/teacher/question_bank/_helpers.py:99` — `_append_navigation_query`
- `apps/exams/views/teacher/question_bank/_helpers.py:106` — `_default_exam_language`
- `apps/exams/views/teacher/question_bank/_helpers.py:396` — `_format_int_list`
- `apps/exams/views/teacher/question_bank/_helpers.py:45` — `_is_internal_exam_management_path`
- `apps/exams/views/teacher/question_bank/_helpers.py:119` — `_normalize_exam_language`
- `apps/exams/views/teacher/question_bank/_helpers.py:204` — `_optional_non_negative_int`
- `apps/exams/views/teacher/question_bank/_helpers.py:219` — `_parse_points_payload`
- `apps/exams/views/teacher/question_bank/_helpers.py:215` — `_parse_selected_question_indices`
- `apps/exams/views/teacher/question_bank/_helpers.py:171` — `_parse_written_questions`
- `apps/exams/views/teacher/question_bank/_helpers.py:326` — `_question_bank_feedback`
- `apps/exams/views/teacher/question_bank/_helpers.py:352` — `_question_bank_source_diagnostics`
- `apps/exams/views/teacher/question_bank/_helpers.py:191` — `_question_bank_title_context`
- `apps/exams/views/teacher/question_bank/_helpers.py:322` — `_question_bank_warning_label`
- `apps/exams/views/teacher/question_bank/_helpers.py:68` — `_resolve_question_bank_navigation`
- `apps/exams/views/teacher/question_bank/_helpers.py:23` — `_safe_same_origin_redirect_path`
- `apps/exams/views/teacher/question_bank/_helpers.py:333` — `_split_end_question_source_blocks`
- `apps/exams/views/teacher/question_bank/_helpers.py:223` — `_sync_written_block_questions`
- `apps/exams/views/teacher/question_bank/_helpers.py:127` — `_test_workbench_context`
- `apps/exams/views/teacher/question_bank/_helpers.py:406` — `_warning_reference_text`
- `apps/exams/views/teacher/question_bank/_reports.py:258` — `_build_question_bank_report_docx`
- `apps/exams/views/teacher/question_bank/_reports.py:32` — `_build_question_bank_report_xlsx`
- `apps/exams/views/teacher/question_bank/_reports.py:25` — `_excel_sheet_title`
- `apps/exams/views/teacher/question_bank/_reports.py:21` — `_tx`
- `apps/exams/views/teacher/question_bank/_views_create.py:32` — `ai_generate_question_bank`
- `apps/exams/views/teacher/question_bank/_views_create.py:77` — `create_question_bank`
- `apps/exams/views/teacher/question_bank/_views_create.py:120` — `process_question_bank`
- `apps/exams/views/teacher/question_bank/_views_misc.py:52` — `exam_questions_word_export`
- `apps/exams/views/teacher/question_bank/_views_misc.py:94` — `test_question_bank`
- `apps/exams/views/teacher/question_bank/_views_misc.py:35` — `test_question_bank_template_download`
- `apps/exams/views/teacher/question_library/_shared.py:196` — `_bank_language_stats`
- `apps/exams/views/teacher/question_library/_shared.py:80` — `_empty_analysis`
- `apps/exams/views/teacher/question_library/_shared.py:175` — `_exam_compatible_question_type`
- `apps/exams/views/teacher/question_library/_shared.py:180` — `_first_or_default_block`
- `apps/exams/views/teacher/question_library/_shared.py:72` — `_is_modal_request`
- `apps/exams/views/teacher/question_library/_shared.py:67` — `_normalize_format`
- `apps/exams/views/teacher/question_library/_shared.py:167` — `_render_bank_question_form_html`
- `apps/exams/views/teacher/question_library/_shared.py:91` — `_save_bank_questions`
- `apps/exams/views/teacher/question_library/crud.py:95` — `question_bank_delete`
- `apps/exams/views/teacher/question_library/crud.py:116` — `question_bank_detail`
- `apps/exams/views/teacher/question_library/crud.py:28` — `question_bank_list`
- `apps/exams/views/teacher/question_library/crud.py:63` — `question_bank_update`
- `apps/exams/views/teacher/question_library/export.py:21` — `question_bank_template_download`
- `apps/exams/views/teacher/question_library/export.py:36` — `question_bank_word_export`
- `apps/exams/views/teacher/question_library/picker.py:31` — `exam_bank_picker`
- `apps/exams/views/teacher/question_library/questions.py:148` — `ai_generate_bank_questions`
- `apps/exams/views/teacher/question_library/questions.py:182` — `bank_question_add`
- `apps/exams/views/teacher/question_library/questions.py:228` — `bank_question_edit`
- `apps/exams/views/teacher/question_library/questions.py:36` — `question_bank_bulk_add`
- `apps/exams/views/teacher/questions/_shared.py:93` — `_append_navigation_query`
- `apps/exams/views/teacher/questions/_shared.py:39` — `_is_internal_exam_management_path`
- `apps/exams/views/teacher/questions/_shared.py:13` — `_is_question_modal_request`
- `apps/exams/views/teacher/questions/_shared.py:113` — `_question_form_blocks`
- `apps/exams/views/teacher/questions/_shared.py:127` — `_question_post_data_with_default_block`
- `apps/exams/views/teacher/questions/_shared.py:136` — `_render_question_form_html`
- `apps/exams/views/teacher/questions/_shared.py:100` — `_resequence_exam_questions`
- `apps/exams/views/teacher/questions/_shared.py:62` — `_resolve_question_bank_navigation`
- `apps/exams/views/teacher/questions/_shared.py:17` — `_safe_same_origin_redirect_path`
- `apps/exams/views/teacher/questions/bank.py:33` — `teacher_questions_bank`
- `apps/exams/views/teacher/questions/crud.py:32` — `add_exam_question`
- `apps/exams/views/teacher/questions/crud.py:273` — `delete_exam_question`
- `apps/exams/views/teacher/questions/crud.py:160` — `edit_exam_question`
- `apps/exams/views/teacher/results/_attempt_views.py:344` — `ai_grade_answer`
- `apps/exams/views/teacher/results/_attempt_views.py:44` — `delete_exam_attempts`
- `apps/exams/views/teacher/results/_attempt_views.py:195` — `teacher_check_attempt`
- `apps/exams/views/teacher/results/_attempt_views.py:390` — `teacher_pending_attempts`
- `apps/exams/views/teacher/results/_attempt_views.py:90` — `teacher_view_attempt`
- `apps/exams/views/teacher/results/_export_builder.py:28` — `build_exam_results_xlsx_export`
- `apps/exams/views/teacher/results/_helpers.py:318` — `_appeal_bonus_map_for`
- `apps/exams/views/teacher/results/_helpers.py:121` — `_append_query_params`
- `apps/exams/views/teacher/results/_helpers.py:325` — `_apply_appeal_bonus`
- `apps/exams/views/teacher/results/_helpers.py:355` — `_apply_results_filters`
- `apps/exams/views/teacher/results/_helpers.py:363` — `_apply_results_filters_from_params`
- `apps/exams/views/teacher/results/_helpers.py:306` — `_attempt_effective_duration`
- `apps/exams/views/teacher/results/_helpers.py:280` — `_attempt_effective_finish`
- `apps/exams/views/teacher/results/_helpers.py:272` — `_attempt_time_limit_seconds`
- `apps/exams/views/teacher/results/_helpers.py:255` — `_available_groups_for_exam`
- `apps/exams/views/teacher/results/_helpers.py:245` — `_build_anonymous_name`
- `apps/exams/views/teacher/results/_helpers.py:78` — `_build_answer_review_item`
- `apps/exams/views/teacher/results/_helpers.py:180` — `_build_attempt_timing_context`
- `apps/exams/views/teacher/results/_helpers.py:26` — `_coding_submission_file_items`
- `apps/exams/views/teacher/results/_helpers.py:332` — `_expire_overdue_attempts`
- `apps/exams/views/teacher/results/_helpers.py:199` — `_parse_filter_date`
- `apps/exams/views/teacher/results/_helpers.py:209` — `_resolve_attempt_action_state`
- `apps/exams/views/teacher/results/_helpers.py:151` — `_resolve_profile_navigation`
- `apps/exams/views/teacher/results/_helpers.py:129` — `_safe_same_origin_redirect_path`
- `apps/exams/views/teacher/results/_helpers.py:52` — `_sync_coding_answers_from_final_submissions`
- `apps/exams/views/teacher/results/_helpers.py:22` — `_user_display_name`
- `apps/exams/views/teacher/results/_results_views.py:342` — `export_exam_results_xlsx`
- `apps/exams/views/teacher/results/_results_views.py:42` — `teacher_exam_results`
- `apps/exams/views/teacher/statistics.py:35` — `_build_score_distribution`
- `apps/exams/views/teacher/statistics.py:28` — `_parse_int`
- `apps/exams/views/teacher/statistics.py:58` — `_resolve_navigation`
- `apps/exams/views/teacher/statistics.py:83` — `teacher_exam_statistics`
- `apps/exams/views/teacher/submission_inbox.py:441` — `_detail_context`
- `apps/exams/views/teacher/submission_inbox.py:55` — `_form_state`
- `apps/exams/views/teacher/submission_inbox.py:50` — `_normalize_language`
- `apps/exams/views/teacher/submission_inbox.py:120` — `_preview_context`
- `apps/exams/views/teacher/submission_inbox.py:37` — `_profile_section_url`
- `apps/exams/views/teacher/submission_inbox.py:41` — `_require_organization`
- `apps/exams/views/teacher/submission_inbox.py:101` — `_resolve_groups`
- `apps/exams/views/teacher/submission_inbox.py:72` — `_teacher_groups`
- `apps/exams/views/teacher/submission_inbox.py:85` — `_teacher_subjects`
- `apps/exams/views/teacher/submission_inbox.py:294` — `ai_generate_submission_questions`
- `apps/exams/views/teacher/submission_inbox.py:111` — `annotate_preview_flags`
- `apps/exams/views/teacher/submission_inbox.py:130` — `question_submission_create`
- `apps/exams/views/teacher/submission_inbox.py:528` — `question_submission_decide`
- `apps/exams/views/teacher/submission_inbox.py:416` — `question_submission_delete`
- `apps/exams/views/teacher/submission_inbox.py:326` — `question_submission_detail`
- `apps/exams/views/teacher/submission_inbox.py:469` — `question_submission_inbox`
- `apps/exams/views/teacher/submission_inbox.py:502` — `question_submission_review`
- `apps/exams/views/teacher/supervision/_shared.py:18` — `_ensure_organization_context`
- `apps/exams/views/teacher/supervision/_shared.py:26` — `_ensure_supervision_access`
- `apps/exams/views/teacher/supervision/_shared.py:53` — `_ensure_supervision_feature_enabled`
- `apps/exams/views/teacher/supervision/_shared.py:69` — `_get_scoped_exam_or_404`
- `apps/exams/views/teacher/supervision/_shared.py:82` — `_parse_date_param`
- `apps/exams/views/teacher/supervision/_shared.py:58` — `_supervision_disabled_json`
- `apps/exams/views/teacher/supervision/_shared.py:46` — `_supervision_exam_queryset`
- `apps/exams/views/teacher/supervision/live.py:76` — `attempt_live_snapshot_api`
- `apps/exams/views/teacher/supervision/live.py:28` — `exam_live_monitor`
- `apps/exams/views/teacher/supervision/live.py:60` — `exam_live_monitor_poll_api`
- `apps/exams/views/teacher/supervision/monitor.py:38` — `log_incident_api`
- `apps/exams/views/teacher/supervision/monitor.py:278` — `supervision_detail`
- `apps/exams/views/teacher/supervision/monitor.py:118` — `supervision_monitor`
- `apps/exams/views/teacher/supervision/monitor.py:94` — `supervision_status_api`
- `apps/exams/views/teacher/supervision/monitor.py:446` — `teacher_lock_api`
- `apps/exams/views/teacher/supervision/monitor.py:320` — `teacher_resume_api`
- `apps/exams/views/teacher/supervision/monitor.py:394` — `teacher_stop_api`
- `apps/live_exam/api/v1/views.py:18` — `_versioned`
- `apps/live_exam/api/v1/views.py:24` — `live_state_json_v1`
- `apps/live_exam/views/api.py:183` — `live_answer_submit`
- `apps/live_exam/views/api.py:57` — `live_state_json`
- `apps/live_exam/views/host/_shared.py:15` — `_ensure_host_org_permission`
- `apps/live_exam/views/host/_shared.py:42` — `_host_session_context`
- `apps/live_exam/views/host/game.py:347` — `host_finish`
- `apps/live_exam/views/host/game.py:191` — `host_next_question`
- `apps/live_exam/views/host/game.py:406` — `host_remove_player`
- `apps/live_exam/views/host/game.py:308` — `host_reveal`
- `apps/live_exam/views/host/game.py:249` — `host_skip_question_intro`
- `apps/live_exam/views/host/game.py:53` — `host_start_game`
- `apps/live_exam/views/host/game.py:384` — `host_toggle_lock`
- `apps/live_exam/views/host/game.py:441` — `host_update_settings`
- `apps/live_exam/views/host/session.py:28` — `live_create_session_by_slug`
- `apps/live_exam/views/host/session.py:91` — `live_host_lobby`
- `apps/live_exam/views/host/session.py:104` — `live_host_presentation`
- `apps/live_exam/views/player/_shared.py:169` — `_broadcast_lobby_state`
- `apps/live_exam/views/player/_shared.py:63` — `_candidate_pin_variants`
- `apps/live_exam/views/player/_shared.py:155` — `_ensure_live_client_cookie`
- `apps/live_exam/views/player/_shared.py:41` — `_join_resume_copy`
- `apps/live_exam/views/player/_shared.py:151` — `_live_client_id_key`
- `apps/live_exam/views/player/_shared.py:121` — `_nickname_conflict_message`
- `apps/live_exam/views/player/_shared.py:135` — `_nickname_is_taken`
- `apps/live_exam/views/player/_shared.py:50` — `_normalize_pin`
- `apps/live_exam/views/player/_shared.py:27` — `_pin_entry_copy`
- `apps/live_exam/views/player/_shared.py:32` — `_pin_entry_theme_key`
- `apps/live_exam/views/player/_shared.py:130` — `_random_join_accessory_key`
- `apps/live_exam/views/player/_shared.py:126` — `_random_join_avatar_key`
- `apps/live_exam/views/player/_shared.py:83` — `_resolve_live_session`
- `apps/live_exam/views/player/join.py:162` — `live_join_enter`
- `apps/live_exam/views/player/join.py:139` — `live_join_page`
- `apps/live_exam/views/player/join.py:61` — `live_pin_entry`
- `apps/live_exam/views/player/join.py:306` — `live_qr_png`
- `apps/live_exam/views/player/wait.py:181` — `live_player_screen`
- `apps/live_exam/views/player/wait.py:64` — `live_wait_profile_update`
- `apps/live_exam/views/player/wait.py:122` — `live_wait_reaction`
- `apps/live_exam/views/player/wait.py:38` — `live_wait_room`
- `apps/live_exam/views/results.py:36` — `_build_score_distribution`
- `apps/live_exam/views/results.py:25` — `_ensure_teacher_access`
- `apps/live_exam/views/results.py:61` — `_resolve_exam_navigation`
- `apps/live_exam/views/results.py:89` — `_session_question_ids`
- `apps/live_exam/views/results.py:111` — `_session_questions`
- `apps/live_exam/views/results.py:128` — `_truncate_question_text`
- `apps/live_exam/views/results.py:136` — `teacher_live_exam_results`
- `apps/live_exam/views/results.py:168` — `teacher_live_session_detail`
- `apps/trial_exams/views.py:40` — `_client_ip`
- `apps/trial_exams/views.py:47` — `_initial_from_user`
- `apps/trial_exams/views.py:56` — `trial_exam_request_page`

## Public servis və selektor funksiyaları (260)

- `apps/appeals/selectors.py:29` — `filter_student_appeals`
- `apps/appeals/selectors.py:46` — `paginate_student_appeals`
- `apps/appeals/selectors.py:19` — `student_appeals_queryset`
- `apps/appeals/services/creation.py:90` — `create_appeal`
- `apps/appeals/services/decisions.py:76` — `accept_appeal_item`
- `apps/appeals/services/decisions.py:242` — `recompute_appeal_status`
- `apps/appeals/services/decisions.py:197` — `reject_appeal_item`
- `apps/appeals/services/decisions.py:209` — `revert_item_adjustment`
- `apps/appeals/services/permissions.py:27` — `can_create_appeal`
- `apps/appeals/services/permissions.py:45` — `can_decide_appeal`
- `apps/appeals/services/permissions.py:38` — `can_review_appeal`
- `apps/appeals/services/scoring.py:250` — `appeal_bonus_map`
- `apps/appeals/services/scoring.py:55` — `appeal_item_result_visible_to_student`
- `apps/appeals/services/scoring.py:64` — `appeal_result_hidden_from_student`
- `apps/appeals/services/scoring.py:121` — `appeal_score_state`
- `apps/appeals/services/scoring.py:266` — `apply_bonus_to_test_result`
- `apps/appeals/services/scoring.py:189` — `effective_test_score`
- `apps/appeals/services/scoring.py:258` — `student_visible_appeal_bonus_map`
- `apps/appeals/services/scoring.py:130` — `student_visible_appeal_score_state`
- `apps/appeals/services/scoring.py:139` — `student_visible_appeal_status_by_qid`
- `apps/appeals/services/scoring.py:202` — `student_visible_effective_test_score`
- `apps/appeals/services/state_machine.py:23` — `assert_transition`
- `apps/appeals/services/state_machine.py:17` — `can_transition`
- `apps/appeals/services/window.py:21` — `appeal_deadline`
- `apps/appeals/services/window.py:38` — `is_within_appeal_window`
- `apps/appeals/services/window.py:48` — `remaining_window_seconds`
- `apps/exams/services/access_policy.py:109` — `can_assign_invigilators`
- `apps/exams/services/access_policy.py:139` — `can_create_question_bank`
- `apps/exams/services/access_policy.py:126` — `can_manage_exam_questions`
- `apps/exams/services/access_policy.py:87` — `can_manage_exam_rooms`
- `apps/exams/services/access_policy.py:122` — `can_manage_final_exam_content`
- `apps/exams/services/access_policy.py:22` — `can_user_access_exam`
- `apps/exams/services/access_policy.py:54` — `can_view_attempt_results`
- `apps/exams/services/access_policy.py:143` — `ensure_can_create_question_bank`
- `apps/exams/services/access_policy.py:133` — `ensure_can_manage_exam_questions`
- `apps/exams/services/access_policy.py:103` — `ensure_can_manage_exam_rooms`
- `apps/exams/services/access_policy.py:81` — `is_exam_center_user`
- `apps/exams/services/access_policy.py:7` — `is_teacher_user`
- `apps/exams/services/ai_grading.py:388` — `grade_written_answer`
- `apps/exams/services/ai_grading.py:287` — `has_ai_gradeable_answer_content`
- `apps/exams/services/ai_grading.py:283` — `has_written_answer_content`
- `apps/exams/services/ai_question_generation.py:295` — `generate_question_bank_text`
- `apps/exams/services/ai_summary.py:100` — `check_user_ai_rate_limit`
- `apps/exams/services/ai_summary.py:142` — `generate_exam_statistics_summary`
- `apps/exams/services/ai_summary.py:113` — `get_user_ai_quota_info`
- `apps/exams/services/attempts.py:189` — `can_user_start_new_attempt`
- `apps/exams/services/attempts.py:252` — `create_exam_attempt`
- `apps/exams/services/attempts.py:177` — `get_active_attempt_for_user`
- `apps/exams/services/attempts.py:274` — `get_attempt_limit_result_redirect_url`
- `apps/exams/services/attempts.py:185` — `get_finished_attempts_for_user`
- `apps/exams/services/attempts.py:258` — `submit_exam_attempt`
- `apps/exams/services/bank_analysis.py:294` — `analyze_bank_questions`
- `apps/exams/services/bank_analysis.py:283` — `analyze_question_bank`
- `apps/exams/services/bank_analysis.py:105` — `build_question_meta`
- `apps/exams/services/bulk_workbench.py:190` — `analyze_mcq_bulk`
- `apps/exams/services/bulk_workbench.py:443` — `analyze_written_bulk`
- `apps/exams/services/bulk_workbench.py:134` — `bank_question_fp_map`
- `apps/exams/services/bulk_workbench.py:157` — `bank_written_text_map`
- `apps/exams/services/bulk_workbench.py:112` — `exam_question_fp_map`
- `apps/exams/services/bulk_workbench.py:172` — `exam_written_text_map`
- `apps/exams/services/bulk_workbench.py:43` — `fingerprint_from_texts`
- `apps/exams/services/bulk_workbench.py:37` — `fingerprint_parsed`
- `apps/exams/services/bulk_workbench.py:95` — `parse_points_payload`
- `apps/exams/services/bulk_workbench.py:62` — `parse_selected_indices`
- `apps/exams/services/bulk_workbench.py:415` — `parse_written_bulk`
- `apps/exams/services/coding_definition.py:89` — `build_coding_payload_from_exam_form`
- `apps/exams/services/coding_definition.py:38` — `build_coding_payload_from_exam_question`
- `apps/exams/services/coding_definition.py:108` — `build_coding_payload_from_question_form`
- `apps/exams/services/coding_definition.py:57` — `ensure_coding_question_for_exam_question`
- `apps/exams/services/coding_definition.py:84` — `sync_coding_questions_for_exam`
- `apps/exams/services/coding_definition.py:127` — `sync_coding_test_cases`
- `apps/exams/services/coding_definition.py:147` — `upsert_coding_question`
- `apps/exams/services/coding_polyfills.py:68` — `javascript_main_has_top_level_input_loop`
- `apps/exams/services/coding_runtime/_shared.py:26` — `get_first_coding_question`
- `apps/exams/services/coding_runtime/_shared.py:56` — `normalize_output`
- `apps/exams/services/coding_runtime/_shared.py:36` — `sanitize_filename`
- `apps/exams/services/coding_runtime/_shared.py:43` — `truncate_capture`
- `apps/exams/services/coding_runtime/execution.py:55` — `clean_docker_stderr`
- `apps/exams/services/coding_runtime/execution.py:167` — `execute_code`
- `apps/exams/services/coding_runtime/files.py:51` — `build_starter_files`
- `apps/exams/services/coding_runtime/files.py:43` — `default_starter_code`
- `apps/exams/services/coding_runtime/files.py:35` — `execution_language_for_filename`
- `apps/exams/services/coding_runtime/files.py:18` — `file_language_for_name`
- `apps/exams/services/coding_runtime/files.py:216` — `get_main_file`
- `apps/exams/services/coding_runtime/files.py:220` — `mark_file_as_main`
- `apps/exams/services/coding_runtime/files.py:170` — `normalize_files`
- `apps/exams/services/coding_runtime/files.py:111` — `normalize_python_indentation`
- `apps/exams/services/coding_runtime/files.py:259` — `prepare_files_for_execution`
- `apps/exams/services/coding_runtime/grading.py:81` — `grade_files_against_tests`
- `apps/exams/services/coding_runtime/grading.py:25` — `run_visible_code`
- `apps/exams/services/coding_runtime/submission.py:57` — `create_final_submission`
- `apps/exams/services/coding_runtime/submission.py:13` — `create_or_update_draft_submission`
- `apps/exams/services/coding_runtime/submission.py:78` — `sync_submission_files`
- `apps/exams/services/coding_throttle.py:86` — `acquire_run_slot`
- `apps/exams/services/coding_throttle.py:145` — `release_run_slot`
- `apps/exams/services/difficulty.py:112` — `classify_question_difficulties_with_ai`
- `apps/exams/services/difficulty.py:122` — `ensure_ai_question_difficulties`
- `apps/exams/services/difficulty.py:217` — `schedule_ai_question_difficulty_warmup`
- `apps/exams/services/difficulty.py:191` — `warm_ai_question_difficulties_for_exam`
- `apps/exams/services/duplication.py:59` — `duplicate_exam`
- `apps/exams/services/exam_center_gate.py:207` — `exam_room_isolation_allowed`
- `apps/exams/services/exam_center_gate.py:94` — `final_exam_access_allowed`
- `apps/exams/services/exam_center_gate.py:71` — `get_client_ip`
- `apps/exams/services/exam_center_gate.py:30` — `mac_enforcement_active`
- `apps/exams/services/exam_center_gate.py:168` — `org_computer_access_allowed`
- `apps/exams/services/exam_center_gate.py:35` — `resolve_client_mac`
- `apps/exams/services/exam_center_gate.py:244` — `resolve_room_computer`
- `apps/exams/services/exam_center_gate.py:126` — `room_ip_access_allowed`
- `apps/exams/services/exam_definition.py:1` — `effective_random_question_count`
- `apps/exams/services/final_center/cabinet.py:16` — `student_final_exam_context`
- `apps/exams/services/final_center/entry.py:268` — `attach_ticket_to_room_sitting`
- `apps/exams/services/final_center/entry.py:190` — `clear_entry_session`
- `apps/exams/services/final_center/entry.py:199` — `ensure_open_room_sitting`
- `apps/exams/services/final_center/entry.py:231` — `ensure_pin_ticket`
- `apps/exams/services/final_center/entry.py:186` — `entry_ticket_id`
- `apps/exams/services/final_center/entry.py:182` — `store_entry_session`
- `apps/exams/services/final_center/entry.py:104` — `validate_entry`
- `apps/exams/services/final_center/events.py:47` — `broadcast_to_staff`
- `apps/exams/services/final_center/events.py:51` — `broadcast_to_students`
- `apps/exams/services/final_center/events.py:55` — `notify_ticket`
- `apps/exams/services/final_center/events.py:22` — `staff_group`
- `apps/exams/services/final_center/events.py:26` — `students_group`
- `apps/exams/services/final_center/events.py:30` — `ticket_group`
- `apps/exams/services/final_center/history.py:78` — `session_history`
- `apps/exams/services/final_center/monitor.py:149` — `room_live_sessions`
- `apps/exams/services/final_center/monitor.py:221` — `room_monitor_snapshot`
- `apps/exams/services/final_center/monitor.py:315` — `session_list_annotations`
- `apps/exams/services/final_center/monitor.py:96` — `session_monitor_snapshot`
- `apps/exams/services/final_center/permissions.py:22` — `can_manage_final_center`
- `apps/exams/services/final_center/permissions.py:32` — `can_supervise_session`
- `apps/exams/services/final_center/permissions.py:91` — `can_supervise_session_ws`
- `apps/exams/services/final_center/permissions.py:101` — `can_view_final_history`
- `apps/exams/services/final_center/permissions.py:26` — `ensure_can_manage_final_center`
- `apps/exams/services/final_center/permissions.py:49` — `ensure_can_supervise_session`
- `apps/exams/services/final_center/permissions.py:123` — `ensure_can_view_final_history`
- `apps/exams/services/final_center/permissions.py:75` — `ensure_ticket_owner`
- `apps/exams/services/final_center/permissions.py:64` — `sessions_visible_to`
- `apps/exams/services/final_center/permissions.py:55` — `supervised_sessions_q`
- `apps/exams/services/final_center/permissions.py:81` — `user_is_org_member`
- `apps/exams/services/final_center/permissions.py:129` — `user_supervises_final_sessions`
- `apps/exams/services/final_center/pins.py:108` — `decrypt_ticket_pin`
- `apps/exams/services/final_center/pins.py:174` — `equalize_verification_timing`
- `apps/exams/services/final_center/pins.py:45` — `generate_pin_value`
- `apps/exams/services/final_center/pins.py:92` — `revoke_ticket_pin`
- `apps/exams/services/final_center/pins.py:61` — `set_ticket_pin`
- `apps/exams/services/final_center/pins.py:118` — `student_visible_pin`
- `apps/exams/services/final_center/pins.py:140` — `verify_ticket_pin`
- `apps/exams/services/final_center/pins.py:99` — `wipe_ticket_pin_cipher`
- `apps/exams/services/final_center/presence.py:49` — `connected_count`
- `apps/exams/services/final_center/presence.py:35` — `drop_presence`
- `apps/exams/services/final_center/presence.py:39` — `presence_map`
- `apps/exams/services/final_center/presence.py:27` — `touch_presence`
- `apps/exams/services/final_center/presence.py:53` — `touch_ticket_last_seen`
- `apps/exams/services/final_center/reminders.py:37` — `notify_upcoming_final_exams`
- `apps/exams/services/final_center/reports.py:15` — `filter_sessions`
- `apps/exams/services/final_center/reports.py:46` — `filter_tickets`
- `apps/exams/services/final_center/room_admin.py:64` — `add_computer`
- `apps/exams/services/final_center/room_admin.py:145` — `bulk_add_computers`
- `apps/exams/services/final_center/room_admin.py:101` — `update_computer`
- `apps/exams/services/final_center/sessions.py:233` — `cancel_session`
- `apps/exams/services/final_center/sessions.py:185` — `end_room`
- `apps/exams/services/final_center/sessions.py:257` — `maybe_auto_end`
- `apps/exams/services/final_center/sessions.py:86` — `open_entry`
- `apps/exams/services/final_center/sessions.py:107` — `start_room`
- `apps/exams/services/final_center/sessions.py:61` — `validate_session_plan`
- `apps/exams/services/final_center/tickets.py:79` — `assign_students`
- `apps/exams/services/final_center/tickets.py:265` — `begin_attempt_for_ticket`
- `apps/exams/services/final_center/tickets.py:203` — `enter_waiting`
- `apps/exams/services/final_center/tickets.py:429` — `readmit_student`
- `apps/exams/services/final_center/tickets.py:153` — `regenerate_pin`
- `apps/exams/services/final_center/tickets.py:350` — `remove_student`
- `apps/exams/services/final_center/tickets.py:187` — `resolve_ticket_language`
- `apps/exams/services/final_center/tickets.py:238` — `set_ready`
- `apps/exams/services/final_center/tickets.py:168` — `set_seat`
- `apps/exams/services/final_center/tickets.py:250` — `student_cancel_waiting`
- `apps/exams/services/final_center/tickets.py:325` — `sync_ticket_completion`
- `apps/exams/services/final_center/tickets.py:56` — `transition_ticket`
- `apps/exams/services/grading.py:36` — `bulk_grade_answers`
- `apps/exams/services/grading.py:8` — `calculate_attempt_score`
- `apps/exams/services/grading.py:19` — `grade_exam_answer`
- `apps/exams/services/grading.py:53` — `parse_score_value`
- `apps/exams/services/import_media.py:87` — `attach_math_images`
- `apps/exams/services/import_media.py:123` — `clear_stash`
- `apps/exams/services/import_media.py:58` — `stash_math_images`
- `apps/exams/services/language_variants.py:30` — `active_variants`
- `apps/exams/services/language_variants.py:93` — `auto_language_for_attempt`
- `apps/exams/services/language_variants.py:53` — `available_language_options`
- `apps/exams/services/language_variants.py:177` — `create_questions_for_variant`
- `apps/exams/services/language_variants.py:132` — `create_variant`
- `apps/exams/services/language_variants.py:104` — `effective_needed_count_for_attempt`
- `apps/exams/services/language_variants.py:167` — `ensure_default_variant`
- `apps/exams/services/language_variants.py:77` — `exam_is_multilingual`
- `apps/exams/services/language_variants.py:35` — `get_active_variant`
- `apps/exams/services/language_variants.py:26` — `language_label`
- `apps/exams/services/language_variants.py:82` — `resolve_requested_language`
- `apps/exams/services/language_variants.py:41` — `scoped_active_questions`
- `apps/exams/services/language_variants.py:161` — `set_variant_active`
- `apps/exams/services/parsing/_core.py:407` — `parse_bulk_mcq`
- `apps/exams/services/parsing/extraction/normalize.py:110` — `normalize_pdf_extracted_text`
- `apps/exams/services/parsing/extraction/pipeline.py:32` — `extract_text_from_upload`
- `apps/exams/services/pdf_math.py:459` — `extract_correct_labels`
- `apps/exams/services/pdf_math.py:353` — `extract_math_images`
- `apps/exams/services/pdf_math.py:217` — `remap_symbol_pua`
- `apps/exams/services/question_bank.py:4` — `normalize_question_text`
- `apps/exams/services/question_bank_attach.py:43` — `accessible_banks`
- `apps/exams/services/question_bank_attach.py:161` — `attach_bank_questions_to_exam`
- `apps/exams/services/question_bank_attach.py:55` — `bank_questions_queryset`
- `apps/exams/services/question_bank_attach.py:83` — `count_bank_questions`
- `apps/exams/services/question_bank_attach.py:88` — `create_bank_questions_from_parsed`
- `apps/exams/services/question_submission.py:206` — `accept_submission`
- `apps/exams/services/question_submission.py:29` — `analyze_submission_text`
- `apps/exams/services/question_submission.py:47` — `clean_snapshot_entries`
- `apps/exams/services/question_submission.py:198` — `ensure_can_review_submission`
- `apps/exams/services/question_submission.py:265` — `reject_submission`
- `apps/exams/services/question_submission.py:145` — `resubmit_question_set`
- `apps/exams/services/question_submission.py:100` — `submit_question_set`
- `apps/exams/services/question_word_export.py:79` — `bank_questions_payload`
- `apps/exams/services/question_word_export.py:41` — `build_questions_docx`
- `apps/exams/services/question_word_export.py:97` — `exam_questions_payload`
- `apps/exams/services/randomizer.py:18` — `available_question_count`
- `apps/exams/services/randomizer.py:59` — `build_shuffled_options`
- `apps/exams/services/randomizer.py:253` — `generate_random_questions_for_attempt`
- `apps/exams/services/result_calculation.py:144` — `attach_test_result_summaries`
- `apps/exams/services/result_calculation.py:72` — `calculate_test_attempt_result`
- `apps/exams/services/result_calculation.py:136` — `sync_test_attempt_counts`
- `apps/exams/services/review_visibility.py:45` — `attempt_review_window_locked`
- `apps/exams/services/review_visibility.py:6` — `resolve_exam_attempt_name_visibility`
- `apps/exams/services/review_visibility.py:30` — `resolve_exam_attempt_review_window_seconds`
- `apps/exams/services/student_pins.py:57` — `exam_requires_student_pins`
- `apps/exams/services/student_pins.py:68` — `provision_exam_student_pins`
- `apps/exams/services/student_pins.py:126` — `resolve_student_pin_login`
- `apps/exams/services/student_pins.py:31` — `student_pin_login_rate_limited`
- `apps/exams/services/student_pins.py:103` — `student_visible_pin`
- `apps/exams/services/student_pins.py:116` — `verify_student_pin`
- `apps/exams/services/supervision/_shared.py:30` — `get_supervision_config`
- `apps/exams/services/supervision/_shared.py:43` — `save_supervision_config_from_form`
- `apps/exams/services/supervision/actions.py:215` — `mark_student_returned`
- `apps/exams/services/supervision/actions.py:231` — `sweep_expired_resume_windows`
- `apps/exams/services/supervision/actions.py:112` — `teacher_lock_attempt`
- `apps/exams/services/supervision/actions.py:14` — `teacher_resume_attempt`
- `apps/exams/services/supervision/actions.py:169` — `teacher_stop_attempt`
- `apps/exams/services/supervision/incidents.py:17` — `log_supervision_incident`
- `apps/exams/services/supervision/monitor.py:19` — `get_attempt_supervision_status`
- `apps/exams/services/supervision/monitor.py:190` — `get_exam_live_monitor_data`
- `apps/exams/services/supervision/monitor.py:160` — `get_exam_question_total`
- `apps/exams/services/supervision/monitor.py:337` — `get_exam_session_dates`
- `apps/exams/services/supervision/monitor.py:64` — `get_flagged_students_for_exam`
- `apps/exams/services/supervision/monitor.py:94` — `get_supervision_monitor_data`
- `apps/exams/services/supervision/snapshot.py:231` — `get_attempt_live_snapshot`
- `apps/exams/services/teacher_dashboard.py:40` — `build_teacher_exam_dashboard`
- `apps/live_exam/services.py:153` — `advance_to_next`
- `apps/live_exam/services.py:50` — `create_live_session`
- `apps/live_exam/services.py:224` — `finish_session`
- `apps/live_exam/services.py:258` — `remove_player`
- `apps/live_exam/services.py:199` — `reveal_current`
- `apps/live_exam/services.py:55` — `start_game`
- `apps/live_exam/services.py:235` — `toggle_session_lock`
- `apps/trial_exams/services.py:270` — `create_trial_exam_request`
- `apps/trial_exams/services.py:141` — `dispatch_trial_notifications`
- `apps/trial_exams/services.py:189` — `send_reply_to_trial_request`

## Celery task və management-command entry-pointləri (11)

- `apps/exams/management/commands/_seed_helpers/courses.py:6` — `CoursesSeedMixin`
- `apps/exams/management/commands/_seed_helpers/exams.py:6` — `ExamsSeedMixin`
- `apps/exams/management/commands/_seed_helpers/users.py:13` — `UsersSeedMixin`
- `apps/exams/management/commands/seed_demo_hierarchy.py:72` — `Command`
- `apps/exams/management/commands/seed_final_exam_demo.py:41` — `Command`
- `apps/exams/management/commands/seed_group_demo_data.py:19` — `Command`
- `apps/exams/tasks.py:20` — `expire_stale_resumed_attempts`
- `apps/exams/tasks.py:45` — `notify_upcoming_final_exams`
- `apps/exams/tasks.py:165` — `run_ai_generation_job`
- `apps/exams/tasks.py:269` — `run_export_job`
- `apps/exams/tasks.py:69` — `run_text_extraction_job`

## WebSocket consumer sinifləri (14)

- `apps/exams/consumers.py:24` — `ExamSupervisionConsumer`
- `apps/exams/consumers.py:102` — `FinalExamRoomConsumer`
- `apps/exams/consumers.py:163` — `FinalExamWaitConsumer`
- `apps/exams/tests/test_final_center_consumers.py:40` — `FinalCenterConsumerAuthTests`
- `apps/exams/tests/test_supervision_consumer.py:36` — `ExamSupervisionConsumerAuthTests`
- `apps/live_exam/consumers.py:104` — `LiveLobbyConsumer`
- `apps/live_exam/consumers.py:169` — `LivePlayConsumer`
- `apps/live_exam/consumers.py:84` — `LiveSessionSocketAuthMixin`
- `apps/live_exam/tests/test_consumers.py:1294` — `ForgedWebSocketCommandTest`
- `apps/live_exam/tests/test_consumers.py:480` — `LiveExamAnswerSubmissionConsumerTest`
- `apps/live_exam/tests/test_consumers.py:37` — `LiveExamConsumerAuthTest`
- `apps/live_exam/tests/test_consumers.py:1191` — `WebSocketHostRoleIsolationTest`
- `apps/live_exam/tests/test_consumers.py:1020` — `WebSocketOriginValidationTest`
- `apps/live_exam/tests/test_consumers.py:1416` — `WebSocketRateLimitTest`

## Permission və access-policy simvolları (32)

- `apps/appeals/services/permissions.py:20` — `_same_tenant`
- `apps/appeals/services/permissions.py:27` — `can_create_appeal`
- `apps/appeals/services/permissions.py:45` — `can_decide_appeal`
- `apps/appeals/services/permissions.py:38` — `can_review_appeal`
- `apps/exams/domain/access_policy.py:124` — `ExamAccessPolicyMixin`
- `apps/exams/domain/access_policy.py:12` — `StudentGroup`
- `apps/exams/services/access_policy.py:65` — `_ensure_can_view_attempt_results`
- `apps/exams/services/access_policy.py:48` — `_ensure_teacher`
- `apps/exams/services/access_policy.py:109` — `can_assign_invigilators`
- `apps/exams/services/access_policy.py:139` — `can_create_question_bank`
- `apps/exams/services/access_policy.py:126` — `can_manage_exam_questions`
- `apps/exams/services/access_policy.py:87` — `can_manage_exam_rooms`
- `apps/exams/services/access_policy.py:122` — `can_manage_final_exam_content`
- `apps/exams/services/access_policy.py:22` — `can_user_access_exam`
- `apps/exams/services/access_policy.py:54` — `can_view_attempt_results`
- `apps/exams/services/access_policy.py:143` — `ensure_can_create_question_bank`
- `apps/exams/services/access_policy.py:133` — `ensure_can_manage_exam_questions`
- `apps/exams/services/access_policy.py:103` — `ensure_can_manage_exam_rooms`
- `apps/exams/services/access_policy.py:81` — `is_exam_center_user`
- `apps/exams/services/access_policy.py:7` — `is_teacher_user`
- `apps/exams/services/final_center/permissions.py:22` — `can_manage_final_center`
- `apps/exams/services/final_center/permissions.py:32` — `can_supervise_session`
- `apps/exams/services/final_center/permissions.py:91` — `can_supervise_session_ws`
- `apps/exams/services/final_center/permissions.py:101` — `can_view_final_history`
- `apps/exams/services/final_center/permissions.py:26` — `ensure_can_manage_final_center`
- `apps/exams/services/final_center/permissions.py:49` — `ensure_can_supervise_session`
- `apps/exams/services/final_center/permissions.py:123` — `ensure_can_view_final_history`
- `apps/exams/services/final_center/permissions.py:75` — `ensure_ticket_owner`
- `apps/exams/services/final_center/permissions.py:64` — `sessions_visible_to`
- `apps/exams/services/final_center/permissions.py:55` — `supervised_sessions_q`
- `apps/exams/services/final_center/permissions.py:81` — `user_is_org_member`
- `apps/exams/services/final_center/permissions.py:129` — `user_supervises_final_sessions`

## API/serializer simvolları (12)

- `apps/live_exam/api/v1/views.py:18` — `_versioned`
- `apps/live_exam/api/v1/views.py:24` — `live_state_json_v1`
- `apps/live_exam/serializers.py:221` — `build_options`
- `apps/live_exam/serializers.py:216` — `options_seed`
- `apps/live_exam/serializers.py:107` — `serialize_answer_distribution`
- `apps/live_exam/serializers.py:29` — `serialize_player_identity`
- `apps/live_exam/serializers.py:173` — `serialize_player_question_result`
- `apps/live_exam/serializers.py:38` — `serialize_players`
- `apps/live_exam/serializers.py:255` — `serialize_question`
- `apps/live_exam/serializers.py:139` — `serialize_question_results`
- `apps/live_exam/serializers.py:42` — `serialize_top`
- `apps/live_exam/serializers.py:62` — `serialize_top_before_question`

## URL route və adları (226)

- `apps/appeals/urls.py:15` — `path("<int:appeal_id>/", views.appeal_detail, name="appeal_detail"),`
- `apps/appeals/urls.py:10` — `path("create/<int:attempt_id>/", views.appeal_create, name="appeal_create"),`
- `apps/appeals/urls.py:12` — `path("manage/", views.manage_appeals, name="manage_appeals"),`
- `apps/appeals/urls.py:13` — `path("manage/<int:appeal_id>/", views.review_appeal, name="review_appeal"),`
- `apps/appeals/urls.py:9` — `path("my/", views.my_appeals, name="my_appeals"),`
- `apps/exams/urls.py:195` — `name="ai_generate_bank_questions",`
- `apps/exams/urls.py:288` — `name="ai_generate_question_bank",`
- `apps/exams/urls.py:159` — `name="ai_generate_submission_questions",`
- `apps/exams/urls.py:245` — `name="ai_grade_answer",`
- `apps/exams/urls.py:393` — `name="attempt_live_snapshot",`
- `apps/exams/urls.py:206` — `name="bank_question_edit",`
- `apps/exams/urls.py:264` — `name="coding_autosave",`
- `apps/exams/urls.py:269` — `name="coding_run",`
- `apps/exams/urls.py:279` — `name="coding_submission_download",`
- `apps/exams/urls.py:274` — `name="coding_submit",`
- `apps/exams/urls.py:304` — `name="create_question_bank",`
- `apps/exams/urls.py:343` — `name="delete_exam_attempts",`
- `apps/exams/urls.py:324` — `name="delete_exam_question",`
- `apps/exams/urls.py:319` — `name="edit_exam_question",`
- `apps/exams/urls.py:138` — `name="exam_available_question_count",`
- `apps/exams/urls.py:34` — `name="exam_center_room_assign_invigilators",`
- `apps/exams/urls.py:39` — `name="exam_center_room_snapshot",`
- `apps/exams/urls.py:94` — `name="exam_center_session_cancel",`
- `apps/exams/urls.py:49` — `name="exam_center_session_history",`
- `apps/exams/urls.py:62` — `name="exam_center_session_monitor",`
- `apps/exams/urls.py:87` — `name="exam_center_session_open_entry",`
- `apps/exams/urls.py:67` — `name="exam_center_session_snapshot",`
- `apps/exams/urls.py:122` — `name="exam_center_student_pins",`
- `apps/exams/urls.py:57` — `name="exam_center_ticket_pin",`
- `apps/exams/urls.py:109` — `name="exam_center_ticket_readmit",`
- `apps/exams/urls.py:82` — `name="exam_center_ticket_reentry",`
- `apps/exams/urls.py:99` — `name="exam_center_ticket_remove",`
- `apps/exams/urls.py:77` — `name="exam_center_ticket_resume",`
- `apps/exams/urls.py:104` — `name="exam_center_ticket_seat",`
- `apps/exams/urls.py:72` — `name="exam_center_ticket_snapshot",`
- `apps/exams/urls.py:383` — `name="exam_live_monitor",`
- `apps/exams/urls.py:388` — `name="exam_live_monitor_poll",`
- `apps/exams/urls.py:294` — `name="exam_questions_word_export",`
- `apps/exams/urls.py:259` — `name="exam_result",`
- `apps/exams/urls.py:348` — `name="export_exam_results_xlsx",`
- `apps/exams/urls.py:143` — `name="grant_extra_attempt",`
- `apps/exams/urls.py:309` — `name="process_question_bank",`
- `apps/exams/urls.py:190` — `name="question_bank_template_download",`
- `apps/exams/urls.py:200` — `name="question_bank_word_export",`
- `apps/exams/urls.py:180` — `name="question_submission_decide",`
- `apps/exams/urls.py:170` — `name="question_submission_delete",`
- `apps/exams/urls.py:165` — `name="question_submission_detail",`
- `apps/exams/urls.py:175` — `name="question_submission_review",`
- `apps/exams/urls.py:378` — `name="supervision_detail",`
- `apps/exams/urls.py:413` — `name="supervision_lock",`
- `apps/exams/urls.py:398` — `name="supervision_log_incident",`
- `apps/exams/urls.py:373` — `name="supervision_monitor",`
- `apps/exams/urls.py:408` — `name="supervision_resume",`
- `apps/exams/urls.py:403` — `name="supervision_status_api",`
- `apps/exams/urls.py:418` — `name="supervision_stop",`
- `apps/exams/urls.py:232` — `name="teacher_add_student_to_group",`
- `apps/exams/urls.py:240` — `name="teacher_check_attempt",`
- `apps/exams/urls.py:222` — `name="teacher_delete_group",`
- `apps/exams/urls.py:329` — `name="teacher_exam_detail_questions_page",`
- `apps/exams/urls.py:227` — `name="teacher_remove_student_from_group",`
- `apps/exams/urls.py:217` — `name="teacher_update_group",`
- `apps/exams/urls.py:250` — `name="teacher_view_attempt",`
- `apps/exams/urls.py:299` — `name="test_question_bank_template_download",`
- `apps/exams/urls.py:353` — `name="toggle_exam_active",`
- `apps/exams/urls.py:358` — `name="toggle_exam_results_visibility",`
- `apps/exams/urls.py:31` — `path(`
- `apps/exams/urls.py:36` — `path(`
- `apps/exams/urls.py:46` — `path(`
- `apps/exams/urls.py:54` — `path(`
- `apps/exams/urls.py:59` — `path(`
- `apps/exams/urls.py:64` — `path(`
- `apps/exams/urls.py:69` — `path(`
- `apps/exams/urls.py:74` — `path(`
- `apps/exams/urls.py:79` — `path(`
- `apps/exams/urls.py:84` — `path(`
- `apps/exams/urls.py:91` — `path(`
- `apps/exams/urls.py:96` — `path(`
- `apps/exams/urls.py:101` — `path(`
- `apps/exams/urls.py:106` — `path(`
- `apps/exams/urls.py:119` — `path(`
- `apps/exams/urls.py:135` — `path(`
- `apps/exams/urls.py:140` — `path(`
- `apps/exams/urls.py:156` — `path(`
- `apps/exams/urls.py:162` — `path(`
- `apps/exams/urls.py:167` — `path(`
- `apps/exams/urls.py:172` — `path(`
- `apps/exams/urls.py:177` — `path(`
- `apps/exams/urls.py:187` — `path(`
- `apps/exams/urls.py:192` — `path(`
- `apps/exams/urls.py:197` — `path(`
- `apps/exams/urls.py:203` — `path(`
- `apps/exams/urls.py:214` — `path(`
- `apps/exams/urls.py:219` — `path(`
- `apps/exams/urls.py:224` — `path(`
- `apps/exams/urls.py:229` — `path(`
- `apps/exams/urls.py:237` — `path(`
- `apps/exams/urls.py:242` — `path(`
- `apps/exams/urls.py:247` — `path(`
- `apps/exams/urls.py:256` — `path(`
- `apps/exams/urls.py:261` — `path(`
- `apps/exams/urls.py:266` — `path(`
- `apps/exams/urls.py:271` — `path(`
- `apps/exams/urls.py:276` — `path(`
- `apps/exams/urls.py:285` — `path(`
- `apps/exams/urls.py:291` — `path(`
- `apps/exams/urls.py:296` — `path(`
- `apps/exams/urls.py:301` — `path(`
- `apps/exams/urls.py:306` — `path(`
- `apps/exams/urls.py:316` — `path(`
- `apps/exams/urls.py:321` — `path(`
- `apps/exams/urls.py:326` — `path(`
- `apps/exams/urls.py:340` — `path(`
- `apps/exams/urls.py:345` — `path(`
- `apps/exams/urls.py:350` — `path(`
- `apps/exams/urls.py:355` — `path(`
- `apps/exams/urls.py:370` — `path(`
- `apps/exams/urls.py:375` — `path(`
- `apps/exams/urls.py:380` — `path(`
- `apps/exams/urls.py:385` — `path(`
- `apps/exams/urls.py:390` — `path(`
- `apps/exams/urls.py:395` — `path(`
- `apps/exams/urls.py:400` — `path(`
- `apps/exams/urls.py:405` — `path(`
- `apps/exams/urls.py:410` — `path(`
- `apps/exams/urls.py:415` — `path(`
- `apps/exams/urls.py:127` — `path("", views.teacher_exam_list, name="teacher_exam_list"),`
- `apps/exams/urls.py:421` — `path("<slug:slug>/", views.teacher_exam_detail, name="teacher_exam_detail"),`
- `apps/exams/urls.py:314` — `path("<slug:slug>/add-question/", views.add_exam_question, name="add_exam_question"),`
- `apps/exams/urls.py:365` — `path("<slug:slug>/archive/", views.toggle_exam_archive, name="toggle_exam_archive"),`
- `apps/exams/urls.py:281` — `path("<slug:slug>/attempt/<int:attempt_id>/", views.take_exam, name="take_exam"),`
- `apps/exams/urls.py:339` — `path("<slug:slug>/bank-picker/", views.exam_bank_picker, name="exam_bank_picker"),`
- `apps/exams/urls.py:361` — `path("<slug:slug>/delete/", views.delete_exam, name="delete_exam"),`
- `apps/exams/urls.py:366` — `path("<slug:slug>/duplicate/", views.duplicate_exam, name="duplicate_exam"),`
- `apps/exams/urls.py:360` — `path("<slug:slug>/edit/", views.createAndEditExamView, name="edit_exam"),`
- `apps/exams/urls.py:337` — `path("<slug:slug>/languages/", views.exam_language_manager, name="exam_language_manager"),`
- `apps/exams/urls.py:364` — `path("<slug:slug>/permanent-delete/", views.permanent_delete_exam, name="permanent_delete_exam"),`
- `apps/exams/urls.py:315` — `path("<slug:slug>/questions-bank/", views.teacher_questions_bank, name="teacher_questions_bank"),`
- `apps/exams/urls.py:363` — `path("<slug:slug>/restore/", views.restore_exam, name="restore_exam"),`
- `apps/exams/urls.py:334` — `path("<slug:slug>/results/", views.teacher_exam_results, name="teacher_exam_results"),`
- `apps/exams/urls.py:255` — `path("<slug:slug>/start/", views.start_exam, name="start_exam"),`
- `apps/exams/urls.py:335` — `path("<slug:slug>/statistics/", views.teacher_exam_statistics, name="teacher_exam_statistics"),`
- `apps/exams/urls.py:290` — `path("<slug:slug>/test-bank/", views.test_question_bank, name="test_question_bank"),`
- `apps/exams/urls.py:21` — `path("assigned/", views.assigned_student_exam_list, name="assigned_exam_list"),`
- `apps/exams/urls.py:12` — `path("available/", views.student_exam_list, name="student_exam_list"),`
- `apps/exams/urls.py:52` — `path("center/finals/", views.exam_center_finals, name="exam_center_finals"),`
- `apps/exams/urls.py:53` — `path("center/finals/assign/", views.exam_center_assign_students, name="exam_center_assign_students"),`
- `apps/exams/urls.py:117` — `path("center/pin-lookup/", views.exam_center_pin_lookup, name="exam_center_pin_lookup"),`
- `apps/exams/urls.py:118` — `path("center/pin-lookup/search/", views.exam_center_pin_search, name="exam_center_pin_search"),`
- `apps/exams/urls.py:111` — `path("center/reports/", views.exam_center_reports, name="exam_center_reports"),`
- `apps/exams/urls.py:27` — `path("center/rooms/", views.exam_center_room_list, name="exam_center_room_list"),`
- `apps/exams/urls.py:29` — `path("center/rooms/<int:room_id>/monitor/", views.exam_center_room_monitor, name="exam_center_room_monitor"),`
- `apps/exams/urls.py:42` — `path("center/rooms/<int:room_id>/open-all/", views.exam_center_room_open_all, name="exam_center_room_open_all"),`
- `apps/exams/urls.py:41` — `path("center/rooms/<int:room_id>/start-all/", views.exam_center_room_start_all, name="exam_center_room_start_all"),`
- `apps/exams/urls.py:43` — `path("center/sessions/", views.exam_center_session_list, name="exam_center_session_list"),`
- `apps/exams/urls.py:45` — `path("center/sessions/<int:session_id>/", views.exam_center_session_detail, name="exam_center_session_detail"),`
- `apps/exams/urls.py:90` — `path("center/sessions/<int:session_id>/end/", views.exam_center_session_end, name="exam_center_session_end"),`
- `apps/exams/urls.py:89` — `path("center/sessions/<int:session_id>/start/", views.exam_center_session_start, name="exam_center_session_start"),`
- `apps/exams/urls.py:44` — `path("center/sessions/create/", views.exam_center_session_create, name="exam_center_session_create"),`
- `apps/exams/urls.py:116` — `path("center/stats/ai/", views.exam_center_stats_ai, name="exam_center_stats_ai"),`
- `apps/exams/urls.py:115` — `path("center/stats/charts/", views.exam_center_stats_charts, name="exam_center_stats_charts"),`
- `apps/exams/urls.py:112` — `path("center/stats/data/", views.exam_center_stats_data, name="exam_center_stats_data"),`
- `apps/exams/urls.py:113` — `path("center/stats/export/", views.exam_center_stats_export, name="exam_center_stats_export"),`
- `apps/exams/urls.py:114` — `path("center/stats/filters/", views.exam_center_stats_filters, name="exam_center_stats_filters"),`
- `apps/exams/urls.py:23` — `path("code-check/", views.exam_code_check, name="exam_code_check"),`
- `apps/exams/urls.py:128` — `path("create/", views.createAndEditExamView, name="create_exam"),`
- `apps/exams/urls.py:362` — `path("deleted/", views.deleted_exams_list, name="deleted_exams_list"),`
- `apps/exams/urls.py:153` — `path("export-jobs/<uuid:job_id>/download/", views.export_job_download, name="export_job_download"),`
- `apps/exams/urls.py:152` — `path("export-jobs/<uuid:job_id>/waiting/", views.export_job_waiting, name="export_job_waiting"),`
- `apps/exams/urls.py:16` — `path("final/", views.final_exam_entry, name="final_exam_entry"),`
- `apps/exams/urls.py:17` — `path("final/waiting/<int:ticket_id>/", views.final_exam_waiting, name="final_exam_waiting"),`
- `apps/exams/urls.py:19` — `path("final/waiting/<int:ticket_id>/begin/", views.final_exam_begin, name="final_exam_begin"),`
- `apps/exams/urls.py:18` — `path("final/waiting/<int:ticket_id>/cancel/", views.final_exam_cancel, name="final_exam_cancel"),`
- `apps/exams/urls.py:20` — `path("final/waiting/<int:ticket_id>/state/", views.final_ticket_state, name="final_ticket_state"),`
- `apps/exams/urls.py:211` — `path("groups/", views.teacher_group_list, name="teacher_group_list"),`
- `apps/exams/urls.py:213` — `path("groups/create/", views.teacher_create_group, name="teacher_create_group"),`
- `apps/exams/urls.py:212` — `path("groups/create/form/", views.create_student_group, name="create_student_group"),`
- `apps/exams/urls.py:150` — `path("import/extract-jobs/", views.start_text_extraction, name="start_text_extraction"),`
- `apps/exams/urls.py:151` — `path("import/extract-jobs/<uuid:job_id>/", views.text_extraction_status, name="text_extraction_status"),`
- `apps/exams/urls.py:134` — `path("lookups/assigned-count/", views.assigned_student_count, name="assigned_student_count"),`
- `apps/exams/urls.py:131` — `path("lookups/groups/", views.group_search, name="group_search"),`
- `apps/exams/urls.py:133` — `path("lookups/invigilators/", views.invigilator_search, name="invigilator_search"),`
- `apps/exams/urls.py:130` — `path("lookups/subjects/", views.subject_search, name="subject_search"),`
- `apps/exams/urls.py:132` — `path("lookups/users/", views.user_search, name="user_search"),`
- `apps/exams/urls.py:22` — `path("my-history/", views.student_exam_history, name="student_exam_history"),`
- `apps/exams/urls.py:145` — `path("pending-work/", views.teacher_pending_attempts, name="teacher_pending_attempts"),`
- `apps/exams/urls.py:182` — `path("question-bank/", views.question_bank_list, name="question_bank_list"),`
- `apps/exams/urls.py:183` — `path("question-bank/<int:bank_id>/", views.question_bank_detail, name="question_bank_detail"),`
- `apps/exams/urls.py:186` — `path("question-bank/<int:bank_id>/bulk-add/", views.question_bank_bulk_add, name="question_bank_bulk_add"),`
- `apps/exams/urls.py:185` — `path("question-bank/<int:bank_id>/delete/", views.question_bank_delete, name="question_bank_delete"),`
- `apps/exams/urls.py:202` — `path("question-bank/<int:bank_id>/questions/add/", views.bank_question_add, name="bank_question_add"),`
- `apps/exams/urls.py:184` — `path("question-bank/<int:bank_id>/update/", views.question_bank_update, name="question_bank_update"),`
- `apps/exams/urls.py:161` — `path("question-submissions/inbox/", views.question_submission_inbox, name="question_submission_inbox"),`
- `apps/exams/urls.py:155` — `path("question-submissions/new/", views.question_submission_create, name="question_submission_create"),`
- `apps/live_exam/api/v1/urls.py:14` — `path("live/<str:pin>/state/", views.live_state_json_v1, name="state_json"),`
- `apps/live_exam/urls.py:12` — `name="create_session_slug",`
- `apps/live_exam/urls.py:30` — `name="teacher_live_results",`
- `apps/live_exam/urls.py:35` — `name="teacher_live_session_detail",`
- `apps/live_exam/urls.py:9` — `path(`
- `apps/live_exam/urls.py:27` — `path(`
- `apps/live_exam/urls.py:32` — `path(`
- `apps/live_exam/urls.py:14` — `path("live/", views.live_pin_entry, name="pin_entry"),`
- `apps/live_exam/urls.py:52` — `path("live/<str:pin>/end/", views.host_reveal, name="end_question"),`
- `apps/live_exam/urls.py:53` — `path("live/<str:pin>/finish/", views.host_finish, name="finish_game"),`
- `apps/live_exam/urls.py:50` — `path("live/<str:pin>/next/", views.host_next_question, name="next_question"),`
- `apps/live_exam/urls.py:51` — `path("live/<str:pin>/skip-intro/", views.host_skip_question_intro, name="skip_intro"),`
- `apps/live_exam/urls.py:49` — `path("live/<str:pin>/start/", views.host_start_game, name="start_game"),`
- `apps/live_exam/urls.py:16` — `path("live/host/<str:pin>/", views.live_host_lobby, name="host_lobby"),`
- `apps/live_exam/urls.py:22` — `path("live/host/<str:pin>/finish/", views.host_finish, name="host_finish"),`
- `apps/live_exam/urls.py:23` — `path("live/host/<str:pin>/lock/", views.host_toggle_lock, name="host_toggle_lock"),`
- `apps/live_exam/urls.py:19` — `path("live/host/<str:pin>/next/", views.host_next_question, name="host_next_question"),`
- `apps/live_exam/urls.py:25` — `path("live/host/<str:pin>/players/remove/", views.host_remove_player, name="host_remove_player"),`
- `apps/live_exam/urls.py:17` — `path("live/host/<str:pin>/presentation/", views.live_host_presentation, name="host_presentation"),`
- `apps/live_exam/urls.py:21` — `path("live/host/<str:pin>/reveal/", views.host_reveal, name="host_reveal"),`
- `apps/live_exam/urls.py:24` — `path("live/host/<str:pin>/settings/", views.host_update_settings, name="host_update_settings"),`
- `apps/live_exam/urls.py:20` — `path("live/host/<str:pin>/skip-intro/", views.host_skip_question_intro, name="host_skip_question_intro"),`
- `apps/live_exam/urls.py:18` — `path("live/host/<str:pin>/start/", views.host_start_game, name="host_start_game"),`
- `apps/live_exam/urls.py:38` — `path("live/join/<str:pin>/", views.live_join_page, name="join_page"),`
- `apps/live_exam/urls.py:39` — `path("live/join/<str:pin>/enter/", views.live_join_enter, name="join_enter"),`
- `apps/live_exam/urls.py:40` — `path("live/play/<str:pin>/", views.live_player_screen, name="player_screen"),`
- `apps/live_exam/urls.py:41` — `path("live/play/<str:pin>/answer/", views.live_answer_submit, name="answer_submit"),`
- `apps/live_exam/urls.py:46` — `path("live/qr/<str:pin>.png", views.live_qr_png, name="qr_png"),`
- `apps/live_exam/urls.py:48` — `path("live/state/<str:pin>/", views.live_state_json, name="state_json"),`
- `apps/live_exam/urls.py:42` — `path("live/wait/<str:pin>/", views.live_wait_room, name="wait_room"),`
- `apps/live_exam/urls.py:43` — `path("live/wait/<str:pin>/profile/", views.live_wait_profile_update, name="wait_room_profile"),`
- `apps/live_exam/urls.py:44` — `path("live/wait/<str:pin>/reaction/", views.live_wait_reaction, name="wait_room_reaction"),`
- `apps/trial_exams/urls.py:8` — `path("trial-exam/", trial_exam_request_page, name="request"),`

## Cache/Redis istifadə nöqtələri (187)

- `apps/appeals/tests/test_creation.py:385` — `cache.clear()`
- `apps/appeals/tests/test_creation.py:383` — `from django.core.cache import cache`
- `apps/exams/consumers.py:167` — `Presence Redis cache-də saxlanır (heartbeat başına DB sətri YOX).`
- `apps/exams/domain/ai_config.py:90` — `cache.delete(_CACHE_KEY)`
- `apps/exams/domain/ai_config.py:99` — `cache.set(_CACHE_KEY, obj, _CACHE_TTL)`
- `apps/exams/domain/ai_config.py:95` — `cached = cache.get(_CACHE_KEY)`
- `apps/exams/domain/ai_config.py:9` — `from django.core.cache import cache`
- `apps/exams/domain/ai_config.py:5` — `through ``get_ai_config()`` which caches the row for 60 seconds so`
- `apps/exams/services/ai_grading.py:6` — `2. Per-user rate limiting (only on cache miss)`
- `apps/exams/services/ai_grading.py:466` — `cache.set(cache_key, result, _CACHE_TTL)`
- `apps/exams/services/ai_grading.py:423` — `cache_key = _grade_cache_key_with_attachments(`
- `apps/exams/services/ai_grading.py:430` — `cached = cache.get(cache_key)`
- `apps/exams/services/ai_grading.py:24` — `from django.core.cache import cache`
- `apps/exams/services/ai_summary.py:89` — `"""Deterministic cache key based on the content hash of the input data."""`
- `apps/exams/services/ai_summary.py:8` — `A SHA-256 hash of the stats dict is used as a cache key. When the`
- `apps/exams/services/ai_summary.py:221` — `cache.set(cache_key, text, _CACHE_TTL)`
- `apps/exams/services/ai_summary.py:185` — `cache_key = _stats_cache_key(exam_title, exam_type, stats, lang)`
- `apps/exams/services/ai_summary.py:186` — `cached = cache.get(cache_key)`
- `apps/exams/services/ai_summary.py:10` — `consuming an API call. The cache is invalidated automatically when`
- `apps/exams/services/ai_summary.py:22` — `from django.core.cache import cache`
- `apps/exams/services/attempts.py:78` — `_release_capacity_counter(cache, key)`
- `apps/exams/services/attempts.py:163` — `_release_capacity_counter(cache, key)`
- `apps/exams/services/attempts.py:174` — `_release_capacity_counter(cache, key)`
- `apps/exams/services/attempts.py:93` — `cache = None`
- `apps/exams/services/attempts.py:96` — `cache = _exam_start_cache()`
- `apps/exams/services/attempts.py:134` — `cache = _exam_start_cache()`
- `apps/exams/services/attempts.py:68` — `cache.add(key, 0, timeout=lease_seconds)`
- `apps/exams/services/attempts.py:118` — `cache.delete(cache_key)`
- `apps/exams/services/attempts.py:56` — `cache.delete(key)`
- `apps/exams/services/attempts.py:58` — `cache.delete(key)`
- `apps/exams/services/attempts.py:71` — `cache.touch(key, lease_seconds)`
- `apps/exams/services/attempts.py:87` — `cache_key = f"emsarena:exam-start:actor:{exam_id}:{user_id}"`
- `apps/exams/services/attempts.py:52` — `def _release_capacity_counter(cache, key: str) -> None:`
- `apps/exams/services/attempts.py:63` — `def _try_acquire_capacity_counter(cache, key: str, limit: int, lease_seconds: int) -> str:`
- `apps/exams/services/attempts.py:8` — `from django.core.cache import caches`
- `apps/exams/services/attempts.py:117` — `if acquired and cache is not None and cache.get(cache_key) == token:`
- `apps/exams/services/attempts.py:98` — `if cache.add(cache_key, token, timeout=lease_seconds):`
- `apps/exams/services/attempts.py:136` — `logger.warning("Exam start capacity cache unavailable; continuing without the capacity gate.", exc_info=True)`
- `apps/exams/services/attempts.py:212` — `parallel start requests slip past the cache-based actor lock. Returns a`
- `apps/exams/services/attempts.py:152` — `result = _try_acquire_capacity_counter(cache, key, limit, lease_seconds)`
- `apps/exams/services/attempts.py:37` — `return caches[getattr(settings, "REQUEST_QUEUE_CACHE_ALIAS", "default")]`
- `apps/exams/services/attempts.py:54` — `value = cache.decr(key)`
- `apps/exams/services/attempts.py:69` — `value = cache.incr(key)`
- `apps/exams/services/coding_throttle.py:14` — `Both limits use Django's cache (Redis in production) so they work across`
- `apps/exams/services/coding_throttle.py:102` — `cache.add(bucket, 0, timeout=70)`
- `apps/exams/services/coding_throttle.py:121` — `cache.add(cc_key, 0, timeout=SLOT_TTL_SECONDS * 2)`
- `apps/exams/services/coding_throttle.py:131` — `cache.decr(cc_key)`
- `apps/exams/services/coding_throttle.py:159` — `cache.delete(slot_key)`
- `apps/exams/services/coding_throttle.py:165` — `cache.set(_concurrency_key(user_id), 0, timeout=SLOT_TTL_SECONDS * 2)`
- `apps/exams/services/coding_throttle.py:167` — `cache.set(_concurrency_key(user_id), 0, timeout=SLOT_TTL_SECONDS * 2)`
- `apps/exams/services/coding_throttle.py:141` — `cache.set(_slot_key(token), user_id, timeout=SLOT_TTL_SECONDS)`
- `apps/exams/services/coding_throttle.py:109` — `cache.set(bucket, 1, timeout=70)`
- `apps/exams/services/coding_throttle.py:125` — `cache.set(cc_key, 1, timeout=SLOT_TTL_SECONDS * 2)`
- `apps/exams/services/coding_throttle.py:104` — `current = cache.incr(bucket)`
- `apps/exams/services/coding_throttle.py:33` — `from django.core.cache import cache`
- `apps/exams/services/coding_throttle.py:123` — `in_flight = cache.incr(cc_key)`
- `apps/exams/services/coding_throttle.py:161` — `remaining = cache.decr(_concurrency_key(user_id))`
- `apps/exams/services/coding_throttle.py:156` — `user_id = cache.get(slot_key)`
- `apps/exams/services/final_center/entry.py:64` — `added = cache.add(key, 0, 60)`
- `apps/exams/services/final_center/entry.py:68` — `cache.set(key, 1, 60)`
- `apps/exams/services/final_center/entry.py:66` — `count = cache.incr(key)`
- `apps/exams/services/final_center/entry.py:16` — `from django.core.cache import cache`
- `apps/exams/services/final_center/monitor.py:3` — `Tək sorğu + presence cache oxunuşu ilə qurulur (N+1 yoxdur). Snapshot həm`
- `apps/exams/services/final_center/presence.py:1` — `"""final_center paketi — efemer presence (Redis cache) qatı.`
- `apps/exams/services/final_center/presence.py:3` — `Heartbeat-lər DB-yə YAZILMIR — hər biletin canlı vəziyyəti TTL-li cache`
- `apps/exams/services/final_center/presence.py:4` — `açarında saxlanır (multi-instance mühitdə paylaşılan Redis). DB-də yalnız`
- `apps/exams/services/final_center/presence.py:36` — `cache.delete(_key(session_id, ticket_id))`
- `apps/exams/services/final_center/presence.py:28` — `cache.set(`
- `apps/exams/services/final_center/presence.py:45` — `found = cache.get_many(list(keys.keys()))`
- `apps/exams/services/final_center/presence.py:11` — `from django.core.cache import cache`
- `apps/exams/services/randomizer.py:52` — `cache.set(cache_key, value, ttl)`
- `apps/exams/services/randomizer.py:44` — `cached = cache.get(cache_key)`
- `apps/exams/services/randomizer.py:38` — `def _cached_usage_counts(cache_key: str, builder):`
- `apps/exams/services/randomizer.py:5` — `from django.core.cache import cache`
- `apps/exams/services/student_pins.py:48` — `cache.add(key, 0, window)`
- `apps/exams/services/student_pins.py:52` — `cache.set(key, 1, window)`
- `apps/exams/services/student_pins.py:50` — `count = cache.incr(key)`
- `apps/exams/services/student_pins.py:14` — `from django.core.cache import cache`
- `apps/exams/tests/test_services.py:156` — `cache.clear()`
- `apps/exams/tests/test_services.py:14` — `from django.core.cache import cache`
- `apps/exams/tests/test_student_pin_throttle.py:19` — `CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "sp-throttle-test"}},`
- `apps/exams/tests/test_student_pin_throttle.py:23` — `cache.clear()`
- `apps/exams/tests/test_student_pin_throttle.py:9` — `from django.core.cache import cache`
- `apps/exams/views/teacher/exams/actions.py:360` — `"Exam cache invalidation failed after permanent delete of exam %s",`
- `apps/exams/views/teacher/exams/actions.py:135` — `"Exam cache invalidation failed after soft-delete of exam %s",`
- `apps/exams/views/teacher/exams/actions.py:314` — `"Exam metadata cache invalidation failed after restore of exam %s",`
- `apps/exams/views/teacher/exams/actions.py:191` — `"Exam metadata cache invalidation failed for exam %s",`
- `apps/exams/views/teacher/exams/actions.py:184` — `from core.cache import invalidate_exam_metadata_cache`
- `apps/exams/views/teacher/exams/actions.py:309` — `from core.cache import invalidate_exam_metadata_cache`
- `apps/exams/views/teacher/exams/actions.py:127` — `from core.cache import invalidate_exam_metadata_cache, invalidate_exam_question_ids_cache`
- `apps/exams/views/teacher/exams/actions.py:354` — `from core.cache import invalidate_exam_metadata_cache, invalidate_exam_question_ids_cache`
- `apps/exams/views/teacher/exams/actions.py:356` — `invalidate_exam_metadata_cache(_exam_pk)`
- `apps/exams/views/teacher/exams/actions.py:129` — `invalidate_exam_metadata_cache(exam.pk)`
- `apps/exams/views/teacher/exams/actions.py:186` — `invalidate_exam_metadata_cache(exam.pk)`
- `apps/exams/views/teacher/exams/actions.py:311` — `invalidate_exam_metadata_cache(exam.pk)`
- `apps/exams/views/teacher/exams/actions.py:357` — `invalidate_exam_question_ids_cache(_exam_pk)`
- `apps/exams/views/teacher/exams/actions.py:130` — `invalidate_exam_question_ids_cache(exam.pk)`
- `apps/exams/views/teacher/exams/list_detail.py:209` — `"Exam metadata cache invalidation failed for exam %s",`
- `apps/exams/views/teacher/exams/list_detail.py:201` — `from core.cache import invalidate_exam_metadata_cache`
- `apps/exams/views/teacher/exams/list_detail.py:203` — `invalidate_exam_metadata_cache(exam_instance.pk)`
- `apps/exams/views/teacher/questions/crud.py:84` — `"Exam question-ids cache invalidation failed for exam %s",`
- `apps/exams/views/teacher/questions/crud.py:296` — `"Exam question-ids cache invalidation failed for exam %s",`
- `apps/exams/views/teacher/questions/crud.py:77` — `from core.cache import invalidate_exam_question_ids_cache`
- `apps/exams/views/teacher/questions/crud.py:289` — `from core.cache import invalidate_exam_question_ids_cache`
- `apps/exams/views/teacher/questions/crud.py:79` — `invalidate_exam_question_ids_cache(exam.pk)`
- `apps/exams/views/teacher/questions/crud.py:291` — `invalidate_exam_question_ids_cache(exam.pk)`
- `apps/live_exam/cache.py:1` — `"""Canlı imtahan üçün oxu-tərəfli cache wrapper-ləri.`
- `apps/live_exam/cache.py:75` — `Avoids a cold-cache penalty on the first API poll from the host.`
- `apps/live_exam/cache.py:3` — `M3 (2026-07-02): core/cache.py-dən köçürülüb — get tərəfi live_exam`
- `apps/live_exam/cache.py:73` — `Pre-load session settings into the cache after session creation.`
- `apps/live_exam/cache.py:33` — `cache first and falling through to the DB on a miss.`
- `apps/live_exam/cache.py:65` — `cache.set(key, ids, timeout=EXAM_QUESTION_IDS_TTL)`
- `apps/live_exam/cache.py:44` — `cache.set(key, settings, timeout=SESSION_SETTINGS_TTL)`
- `apps/live_exam/cache.py:19` — `from core.cache import (`
- `apps/live_exam/cache.py:14` — `from django.core.cache import cache`
- `apps/live_exam/cache.py:67` — `logger.warning("Redis unavailable; exam question IDs cache not populated for exam %s", session.exam_id)`
- `apps/live_exam/cache.py:46` — `logger.warning("Redis unavailable; session settings cache not populated for session %s", session.pk)`
- `apps/live_exam/cache.py:53` — `reading from the cache on a hit.`
- `apps/live_exam/cache.py:56` — `removes questions (which should invalidate this cache).`
- `apps/live_exam/cache.py:5` — `və invalidatorlar core.cache-də qalır (yazan tərəflər app-lardan onları`
- `apps/live_exam/session_settings.py:191` — `from core.cache import invalidate_session_settings_cache`
- `apps/live_exam/session_settings.py:193` — `invalidate_session_settings_cache(session)`
- `apps/live_exam/tests/test_views.py:27` — `"BACKEND": "django.core.cache.backends.locmem.LocMemCache",`
- `apps/live_exam/tests/test_views.py:718` — `cache.clear()`
- `apps/live_exam/tests/test_views.py:1097` — `cache.clear()`
- `apps/live_exam/tests/test_views.py:1465` — `cache.clear()`
- `apps/live_exam/tests/test_views.py:2081` — `cache.clear()`
- `apps/live_exam/tests/test_views.py:2133` — `cache.clear()`
- `apps/live_exam/tests/test_views.py:2209` — `cache.clear()`
- `apps/live_exam/tests/test_views.py:2261` — `cache.clear()`
- `apps/live_exam/tests/test_views.py:2351` — `cache.clear()`
- `apps/live_exam/tests/test_views.py:9` — `from django.core.cache import cache`
- `apps/live_exam/views/player/join.py:12` — `from django.views.decorators.cache import never_cache`
- `apps/trial_exams/views.py:26` — `from django.views.decorators.cache import never_cache`
- `config/settings/components/celery_cache.py:29` — `"BACKEND": "django.core.cache.backends.redis.RedisCache",`
- `config/settings/components/celery_cache.py:13` — `REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0").strip()`
- `config/settings/production.py:460` — `from sentry_sdk.integrations.redis import RedisIntegration`
- `core/cache.py:159` — `"""Build a cache key unique to a role + scope + filter combination.`
- `core/cache.py:88` — `"""Remove the session settings cache entry for *session*."""`
- `core/cache.py:132` — `"""Store *metadata* in the cache for exam *exam_pk*."""`
- `core/cache.py:267` — `Degrades gracefully to a direct ``compute()`` call when Redis is down.`
- `core/cache.py:28` — `Each helper that writes to the cache exposes a companion ``_invalidate_*```
- `core/cache.py:224` — `On any Redis error this degrades gracefully — it just calls *compute*.`
- `core/cache.py:8` — `Redis database 1 is used for application-level caching (database 0 is used`
- `core/cache.py:4` — `Redis-backed caching helpers for EMS Arena.`
- `core/cache.py:124` — `Returns ``None`` on a cache miss so that the caller can fetch from the DB`
- `core/cache.py:125` — `and populate the cache.`
- `core/cache.py:142` — `cache.delete(_exam_metadata_key(exam_pk))`
- `core/cache.py:290` — `cache.delete(_profile_badge_counts_key(user_id, org_id))`
- `core/cache.py:90` — `cache.delete(_session_settings_key(session))`
- `core/cache.py:209` — `cache.delete(_signup_lookup_key())`
- `core/cache.py:108` — `cache.delete(f"{_PREFIX}:live_exam:exam_question_ids:{exam_pk}")`
- `core/cache.py:134` — `cache.set(_exam_metadata_key(exam_pk), metadata, timeout=EXAM_METADATA_TTL)`
- `core/cache.py:275` — `cache.set(key, payload, timeout=PROFILE_BADGE_COUNTS_TTL)`
- `core/cache.py:200` — `cache.set(key, payload, timeout=SIGNUP_LOOKUP_TTL)`
- `core/cache.py:232` — `cache.set(key, payload, timeout=STATISTICS_TTL)`
- `core/cache.py:2` — `core/cache.py`
- `core/cache.py:139` — `def invalidate_exam_metadata_cache(exam_pk: int) -> None:`
- `core/cache.py:102` — `def invalidate_exam_question_ids_cache(exam_pk: int) -> None:`
- `core/cache.py:281` — `def invalidate_profile_badge_counts_cache(user_id, org_id=None) -> None:`
- `core/cache.py:87` — `def invalidate_session_settings_cache(session) -> None:`
- `core/cache.py:206` — `def invalidate_signup_lookup_cache() -> None:`
- `core/cache.py:37` — `from core.cache import invalidate_session_settings_cache # yazan tərəf üçün`
- `core/cache.py:49` — `from django.core.cache import cache`
- `core/cache.py:192` — `gracefully to a direct ``compute()`` call if Redis is unavailable.`
- `core/cache.py:39` — `invalidate_session_settings_cache(session)`
- `core/cache.py:64` — `logger.warning("Redis unavailable; cache lookup failed for key %s", key)`
- `core/cache.py:144` — `logger.warning("Redis unavailable; could not invalidate exam metadata cache for exam %s", exam_pk)`
- `core/cache.py:110` — `logger.warning("Redis unavailable; could not invalidate exam question IDs cache for exam %s", exam_pk)`
- `core/cache.py:292` — `logger.warning("Redis unavailable; could not invalidate profile badge counts for user %s", user_id)`
- `core/cache.py:92` — `logger.warning("Redis unavailable; could not invalidate session settings cache for session %s", session.pk)`
- `core/cache.py:211` — `logger.warning("Redis unavailable; could not invalidate signup lookup cache")`
- `core/cache.py:136` — `logger.warning("Redis unavailable; exam metadata cache not populated for exam %s", exam_pk)`
- `core/cache.py:277` — `logger.warning("Redis unavailable; profile badge counts cache not populated for %s", key)`
- `core/cache.py:202` — `logger.warning("Redis unavailable; signup lookup cache not populated")`
- `core/cache.py:234` — `logger.warning("Redis unavailable; statistics cache not populated for %s", key)`
- `core/cache.py:62` — `return cache.get(key)`
- `core/cache.py:222` — `the statistics payload. Only called on a cache miss.`
- `core/tests/test_cache.py:19` — `"""The cache key must be stable per (role, scope, filters)."""`
- `core/tests/test_cache.py:44` — `"""get_or_set_cached_statistics: compute on miss, serve from cache on hit."""`
- `core/tests/test_cache.py:12` — `"BACKEND": "django.core.cache.backends.locmem.LocMemCache",`
- `core/tests/test_cache.py:13` — `"LOCATION": "statistics-cache-tests",`
- `core/tests/test_cache.py:2` — `Tests for core.cache statistics helpers (FAZA 12).`
- `core/tests/test_cache.py:47` — `cache.clear()`
- `core/tests/test_cache.py:50` — `cache.clear()`
- `core/tests/test_cache.py:8` — `from core.cache import _statistics_key, get_or_set_cached_statistics`
- `core/tests/test_cache.py:5` — `from django.core.cache import cache`


---

# Runtime endpoint cədvəlləri

Bu siyahı source mətnindən deyil, Django URL resolver və Channels routing obyektlərindən çıxarılıb; buna görə include/namespace nəticəsini faktiki runtime formasında göstərir.

## Tam HTTP endpoint cədvəli (134)

| URL pattern | URL adı | View/callback |
|---|---|---|
| appeals/create/<int:attempt_id>/ | appeals:appeal_create | apps.appeals.views.student.endpoints.appeal_create |
| appeals/<int:appeal_id>/ | appeals:appeal_detail | apps.appeals.views.shared.detail.appeal_detail |
| appeals/manage/ | appeals:manage_appeals | apps.appeals.views.teacher.endpoints.manage_appeals |
| appeals/my/ | appeals:my_appeals | apps.appeals.views.student.endpoints.my_appeals |
| appeals/manage/<int:appeal_id>/ | appeals:review_appeal | apps.appeals.views.teacher.endpoints.review_appeal |
| exams/<slug:slug>/add-question/ | exams:add_exam_question | apps.exams.views.teacher.questions.crud.add_exam_question |
| exams/question-bank/<int:bank_id>/ai-generate/ | exams:ai_generate_bank_questions | apps.exams.views.teacher.question_library.questions.ai_generate_bank_questions |
| exams/<slug:slug>/question-bank/ai-generate/ | exams:ai_generate_question_bank | apps.exams.views.teacher.question_bank._views_create.ai_generate_question_bank |
| exams/question-submissions/ai-generate/ | exams:ai_generate_submission_questions | apps.exams.views.teacher.submission_inbox.ai_generate_submission_questions |
| exams/<slug:slug>/attempt/<int:attempt_id>/ai-grade/ | exams:ai_grade_answer | apps.exams.views.teacher.results._attempt_views.ai_grade_answer |
| exams/assigned/ | exams:assigned_exam_list | apps.exams.views.student.lists.assigned_student_exam_list |
| exams/lookups/assigned-count/ | exams:assigned_student_count | apps.exams.views.teacher.exams.lookups.assigned_student_count |
| exams/supervision/api/snapshot/<int:attempt_id>/ | exams:attempt_live_snapshot | apps.exams.views.teacher.supervision.live.attempt_live_snapshot_api |
| exams/question-bank/<int:bank_id>/questions/add/ | exams:bank_question_add | apps.exams.views.teacher.question_library.questions.bank_question_add |
| exams/question-bank/<int:bank_id>/questions/<int:question_id>/edit/ | exams:bank_question_edit | apps.exams.views.teacher.question_library.questions.bank_question_edit |
| exams/<slug:slug>/attempt/<int:attempt_id>/coding/autosave/ | exams:coding_autosave | apps.exams.views.student.coding.coding_autosave |
| exams/<slug:slug>/attempt/<int:attempt_id>/coding/run/ | exams:coding_run | apps.exams.views.student.coding.coding_run |
| exams/<slug:slug>/attempt/<int:attempt_id>/coding/submissions/<int:submission_id>/download/ | exams:coding_submission_download | apps.exams.views.student.coding.coding_submission_download |
| exams/<slug:slug>/attempt/<int:attempt_id>/coding/submit/ | exams:coding_submit | apps.exams.views.student.coding.coding_submit |
| exams/create/ | exams:create_exam | apps.exams.views.teacher.exams.list_detail.createAndEditExamView |
| exams/<slug:slug>/create-bank/ | exams:create_question_bank | apps.exams.views.teacher.question_bank._views_create.create_question_bank |
| exams/groups/create/form/ | exams:create_student_group | apps.exams.views.teacher.groups.create_student_group |
| exams/<slug:slug>/delete/ | exams:delete_exam | apps.exams.views.teacher.exams.actions.delete_exam |
| exams/<slug:slug>/results/delete-attempts/ | exams:delete_exam_attempts | apps.exams.views.teacher.results._attempt_views.delete_exam_attempts |
| exams/<slug:slug>/questions/<int:question_id>/delete/ | exams:delete_exam_question | apps.exams.views.teacher.questions.crud.delete_exam_question |
| exams/deleted/ | exams:deleted_exams_list | apps.exams.views.teacher.exams.actions.deleted_exams_list |
| exams/<slug:slug>/duplicate/ | exams:duplicate_exam | apps.exams.views.teacher.exams.actions.duplicate_exam |
| exams/<slug:slug>/edit/ | exams:edit_exam | apps.exams.views.teacher.exams.list_detail.createAndEditExamView |
| exams/<slug:slug>/questions/<int:question_id>/edit/ | exams:edit_exam_question | apps.exams.views.teacher.questions.crud.edit_exam_question |
| exams/<slug:slug>/available-question-count/ | exams:exam_available_question_count | apps.exams.views.teacher.exams.lookups.exam_available_question_count |
| exams/<slug:slug>/bank-picker/ | exams:exam_bank_picker | apps.exams.views.teacher.question_library.picker.exam_bank_picker |
| exams/center/finals/assign/ | exams:exam_center_assign_students | apps.exams.views.exam_center.sessions.exam_center_assign_students |
| exams/center/finals/ | exams:exam_center_finals | apps.exams.views.exam_center.sessions.exam_center_finals |
| exams/center/pin-lookup/ | exams:exam_center_pin_lookup | apps.exams.views.exam_center.pin_lookup.exam_center_pin_lookup |
| exams/center/pin-lookup/search/ | exams:exam_center_pin_search | apps.exams.views.exam_center.pin_lookup.exam_center_pin_search |
| exams/center/reports/ | exams:exam_center_reports | apps.exams.views.exam_center.reports.exam_center_reports |
| exams/center/rooms/<int:room_id>/invigilators/ | exams:exam_center_room_assign_invigilators | apps.exams.views.exam_center.room_monitor.exam_center_room_assign_invigilators |
| exams/center/rooms/ | exams:exam_center_room_list | apps.exams.views.exam_center.rooms.exam_center_room_list |
| exams/center/rooms/<int:room_id>/monitor/ | exams:exam_center_room_monitor | apps.exams.views.exam_center.room_monitor.exam_center_room_monitor |
| exams/center/rooms/<int:room_id>/open-all/ | exams:exam_center_room_open_all | apps.exams.views.exam_center.room_monitor.exam_center_room_open_all |
| exams/center/rooms/<int:room_id>/api/snapshot/ | exams:exam_center_room_snapshot | apps.exams.views.exam_center.room_monitor.exam_center_room_snapshot |
| exams/center/rooms/<int:room_id>/start-all/ | exams:exam_center_room_start_all | apps.exams.views.exam_center.room_monitor.exam_center_room_start_all |
| exams/center/sessions/<int:session_id>/cancel/ | exams:exam_center_session_cancel | apps.exams.views.exam_center.monitor.exam_center_session_cancel |
| exams/center/sessions/create/ | exams:exam_center_session_create | apps.exams.views.exam_center.sessions.exam_center_session_create |
| exams/center/sessions/<int:session_id>/ | exams:exam_center_session_detail | apps.exams.views.exam_center.sessions.exam_center_session_detail |
| exams/center/sessions/<int:session_id>/end/ | exams:exam_center_session_end | apps.exams.views.exam_center.monitor.exam_center_session_end |
| exams/center/sessions/<int:session_id>/history/ | exams:exam_center_session_history | apps.exams.views.exam_center.sessions.exam_center_session_history |
| exams/center/sessions/ | exams:exam_center_session_list | apps.exams.views.exam_center.sessions.exam_center_session_list |
| exams/center/sessions/<int:session_id>/monitor/ | exams:exam_center_session_monitor | apps.exams.views.exam_center.monitor.exam_center_session_monitor |
| exams/center/sessions/<int:session_id>/open-entry/ | exams:exam_center_session_open_entry | apps.exams.views.exam_center.monitor.exam_center_session_open_entry |
| exams/center/sessions/<int:session_id>/api/snapshot/ | exams:exam_center_session_snapshot | apps.exams.views.exam_center.monitor.exam_center_session_snapshot |
| exams/center/sessions/<int:session_id>/start/ | exams:exam_center_session_start | apps.exams.views.exam_center.monitor.exam_center_session_start |
| exams/center/stats/ai/ | exams:exam_center_stats_ai | apps.exams.views.exam_center.statistics_charts.exam_center_stats_ai |
| exams/center/stats/charts/ | exams:exam_center_stats_charts | apps.exams.views.exam_center.statistics_charts.exam_center_stats_charts |
| exams/center/stats/data/ | exams:exam_center_stats_data | apps.exams.views.exam_center.statistics.exam_center_stats_data |
| exams/center/stats/export/ | exams:exam_center_stats_export | apps.exams.views.exam_center.statistics.exam_center_stats_export |
| exams/center/stats/filters/ | exams:exam_center_stats_filters | apps.exams.views.exam_center.statistics.exam_center_stats_filters |
| exams/center/pin-lookup/student/<int:student_id>/ | exams:exam_center_student_pins | apps.exams.views.exam_center.pin_lookup.exam_center_student_pins |
| exams/center/finals/tickets/<int:ticket_id>/pin/ | exams:exam_center_ticket_pin | apps.exams.views.exam_center.sessions.exam_center_ticket_pin |
| exams/center/sessions/<int:session_id>/tickets/<int:ticket_id>/readmit/ | exams:exam_center_ticket_readmit | apps.exams.views.exam_center.sessions.exam_center_ticket_readmit |
| exams/center/sessions/<int:session_id>/tickets/<int:ticket_id>/reentry/ | exams:exam_center_ticket_reentry | apps.exams.views.exam_center.monitor.exam_center_ticket_reentry |
| exams/center/sessions/<int:session_id>/tickets/<int:ticket_id>/remove/ | exams:exam_center_ticket_remove | apps.exams.views.exam_center.monitor.exam_center_ticket_remove |
| exams/center/sessions/<int:session_id>/tickets/<int:ticket_id>/resume/ | exams:exam_center_ticket_resume | apps.exams.views.exam_center.monitor.exam_center_ticket_resume |
| exams/center/sessions/<int:session_id>/tickets/<int:ticket_id>/seat/ | exams:exam_center_ticket_seat | apps.exams.views.exam_center.sessions.exam_center_ticket_seat |
| exams/center/sessions/<int:session_id>/tickets/<int:ticket_id>/snapshot/ | exams:exam_center_ticket_snapshot | apps.exams.views.exam_center.monitor.exam_center_ticket_snapshot |
| exams/code-check/ | exams:exam_code_check | apps.exams.views.shared.access.exam_code_check |
| exams/<slug:slug>/languages/ | exams:exam_language_manager | apps.exams.views.teacher.languages.exam_language_manager |
| exams/supervision/live/<int:exam_id>/ | exams:exam_live_monitor | apps.exams.views.teacher.supervision.live.exam_live_monitor |
| exams/supervision/live/<int:exam_id>/poll/ | exams:exam_live_monitor_poll | apps.exams.views.teacher.supervision.live.exam_live_monitor_poll_api |
| exams/<slug:slug>/questions/export.docx | exams:exam_questions_word_export | apps.exams.views.teacher.question_bank._views_misc.exam_questions_word_export |
| exams/<slug:slug>/attempt/<int:attempt_id>/result/ | exams:exam_result | apps.exams.views.student.results.exam_result |
| exams/<slug:slug>/results/export.xlsx | exams:export_exam_results_xlsx | apps.exams.views.teacher.results._results_views.export_exam_results_xlsx |
| exams/export-jobs/<uuid:job_id>/download/ | exams:export_job_download | apps.exams.views.teacher.extract_jobs.export_job_download |
| exams/export-jobs/<uuid:job_id>/waiting/ | exams:export_job_waiting | apps.exams.views.teacher.extract_jobs.export_job_waiting |
| exams/final/waiting/<int:ticket_id>/begin/ | exams:final_exam_begin | apps.exams.views.student.final_center.final_exam_begin |
| exams/final/waiting/<int:ticket_id>/cancel/ | exams:final_exam_cancel | apps.exams.views.student.final_center.final_exam_cancel |
| exams/final/ | exams:final_exam_entry | apps.exams.views.student.final_center.final_exam_entry |
| exams/final/waiting/<int:ticket_id>/ | exams:final_exam_waiting | apps.exams.views.student.final_center.final_exam_waiting |
| exams/final/waiting/<int:ticket_id>/state/ | exams:final_ticket_state | apps.exams.views.student.final_center.final_ticket_state |
| exams/<slug:slug>/grant-extra-attempt/ | exams:grant_extra_attempt | apps.exams.views.teacher.exams.attempt_grants.grant_extra_attempt |
| exams/lookups/groups/ | exams:group_search | apps.exams.views.teacher.exams.lookups.group_search |
| exams/lookups/invigilators/ | exams:invigilator_search | apps.exams.views.teacher.exams.lookups.invigilator_search |
| exams/<slug:slug>/permanent-delete/ | exams:permanent_delete_exam | apps.exams.views.teacher.exams.actions.permanent_delete_exam |
| exams/<slug:slug>/process-bank/ | exams:process_question_bank | apps.exams.views.teacher.question_bank._views_create.process_question_bank |
| exams/question-bank/<int:bank_id>/bulk-add/ | exams:question_bank_bulk_add | apps.exams.views.teacher.question_library.questions.question_bank_bulk_add |
| exams/question-bank/<int:bank_id>/delete/ | exams:question_bank_delete | apps.exams.views.teacher.question_library.crud.question_bank_delete |
| exams/question-bank/<int:bank_id>/ | exams:question_bank_detail | apps.exams.views.teacher.question_library.crud.question_bank_detail |
| exams/question-bank/ | exams:question_bank_list | apps.exams.views.teacher.question_library.crud.question_bank_list |
| exams/question-bank/<int:bank_id>/bulk-add/template-download/ | exams:question_bank_template_download | apps.exams.views.teacher.question_library.export.question_bank_template_download |
| exams/question-bank/<int:bank_id>/update/ | exams:question_bank_update | apps.exams.views.teacher.question_library.crud.question_bank_update |
| exams/question-bank/<int:bank_id>/export.docx | exams:question_bank_word_export | apps.exams.views.teacher.question_library.export.question_bank_word_export |
| exams/question-submissions/new/ | exams:question_submission_create | apps.exams.views.teacher.submission_inbox.question_submission_create |
| exams/question-submissions/<int:submission_id>/decide/ | exams:question_submission_decide | apps.exams.views.teacher.submission_inbox.question_submission_decide |
| exams/question-submissions/<int:submission_id>/delete/ | exams:question_submission_delete | apps.exams.views.teacher.submission_inbox.question_submission_delete |
| exams/question-submissions/<int:submission_id>/ | exams:question_submission_detail | apps.exams.views.teacher.submission_inbox.question_submission_detail |
| exams/question-submissions/inbox/ | exams:question_submission_inbox | apps.exams.views.teacher.submission_inbox.question_submission_inbox |
| exams/question-submissions/<int:submission_id>/review/ | exams:question_submission_review | apps.exams.views.teacher.submission_inbox.question_submission_review |
| exams/<slug:slug>/restore/ | exams:restore_exam | apps.exams.views.teacher.exams.actions.restore_exam |
| exams/<slug:slug>/start/ | exams:start_exam | apps.exams.views.student.attempts.start_exam |
| exams/import/extract-jobs/ | exams:start_text_extraction | apps.exams.views.teacher.extract_jobs.start_text_extraction |
| exams/my-history/ | exams:student_exam_history | apps.exams.views.student.results.student_exam_history |
| exams/available/ | exams:student_exam_list | apps.exams.views.student.lists.student_exam_list |
| exams/lookups/subjects/ | exams:subject_search | apps.exams.views.teacher.exams.lookups.subject_search |
| exams/supervision/detail/<int:attempt_id>/ | exams:supervision_detail | apps.exams.views.teacher.supervision.monitor.supervision_detail |
| exams/supervision/api/lock/<int:attempt_id>/ | exams:supervision_lock | apps.exams.views.teacher.supervision.monitor.teacher_lock_api |
| exams/supervision/api/log/<int:attempt_id>/ | exams:supervision_log_incident | apps.exams.views.teacher.supervision.monitor.log_incident_api |
| exams/supervision/monitor/ | exams:supervision_monitor | apps.exams.views.teacher.supervision.monitor.supervision_monitor |
| exams/supervision/api/resume/<int:attempt_id>/ | exams:supervision_resume | apps.exams.views.teacher.supervision.monitor.teacher_resume_api |
| exams/supervision/api/status/<int:attempt_id>/ | exams:supervision_status_api | apps.exams.views.teacher.supervision.monitor.supervision_status_api |
| exams/supervision/api/stop/<int:attempt_id>/ | exams:supervision_stop | apps.exams.views.teacher.supervision.monitor.teacher_stop_api |
| exams/<slug:slug>/attempt/<int:attempt_id>/ | exams:take_exam | apps.exams.views.student.attempts.take_exam |
| exams/groups/<int:group_id>/students/<int:student_id>/add/ | exams:teacher_add_student_to_group | apps.exams.views.teacher.groups.teacher_add_student_to_group |
| exams/<slug:slug>/attempt/<int:attempt_id>/check/ | exams:teacher_check_attempt | apps.exams.views.teacher.results._attempt_views.teacher_check_attempt |
| exams/groups/create/ | exams:teacher_create_group | apps.exams.views.teacher.groups.teacher_create_group |
| exams/groups/<int:group_id>/delete/ | exams:teacher_delete_group | apps.exams.views.teacher.groups.teacher_delete_group |
| exams/<slug:slug>/ | exams:teacher_exam_detail | apps.exams.views.teacher.exams.list_detail.teacher_exam_detail |
| exams/<slug:slug>/questions/page/ | exams:teacher_exam_detail_questions_page | apps.exams.views.teacher.exams.list_detail.teacher_exam_detail_questions_page |
| exams/ | exams:teacher_exam_list | apps.exams.views.teacher.exams.list_detail.teacher_exam_list |
| exams/<slug:slug>/results/ | exams:teacher_exam_results | apps.exams.views.teacher.results._results_views.teacher_exam_results |
| exams/<slug:slug>/statistics/ | exams:teacher_exam_statistics | apps.exams.views.teacher.statistics.teacher_exam_statistics |
| exams/groups/ | exams:teacher_group_list | apps.exams.views.teacher.groups.teacher_group_list |
| exams/pending-work/ | exams:teacher_pending_attempts | apps.exams.views.teacher.results._attempt_views.teacher_pending_attempts |
| exams/<slug:slug>/questions-bank/ | exams:teacher_questions_bank | apps.exams.views.teacher.questions.bank.teacher_questions_bank |
| exams/groups/<int:group_id>/students/<int:student_id>/remove/ | exams:teacher_remove_student_from_group | apps.exams.views.teacher.groups.teacher_remove_student_from_group |
| exams/groups/<int:group_id>/update/ | exams:teacher_update_group | apps.exams.views.teacher.groups.teacher_update_group |
| exams/<slug:slug>/attempt/<int:attempt_id>/view/ | exams:teacher_view_attempt | apps.exams.views.teacher.results._attempt_views.teacher_view_attempt |
| exams/<slug:slug>/test-bank/ | exams:test_question_bank | apps.exams.views.teacher.question_bank._views_misc.test_question_bank |
| exams/<slug:slug>/test-bank/template-download/ | exams:test_question_bank_template_download | apps.exams.views.teacher.question_bank._views_misc.test_question_bank_template_download |
| exams/import/extract-jobs/<uuid:job_id>/ | exams:text_extraction_status | apps.exams.views.teacher.extract_jobs.text_extraction_status |
| exams/<slug:slug>/toggle-active/ | exams:toggle_exam_active | apps.exams.views.teacher.exams.actions.toggle_exam_active |
| exams/<slug:slug>/archive/ | exams:toggle_exam_archive | apps.exams.views.teacher.exams.actions.toggle_exam_archive |
| exams/<slug:slug>/toggle-results-visibility/ | exams:toggle_exam_results_visibility | apps.exams.views.teacher.exams.actions.toggle_exam_results_visibility |
| exams/lookups/users/ | exams:user_search | apps.exams.views.teacher.exams.lookups.user_search |
| trial-exam/ | trial_exams:request | apps.trial_exams.views.trial_exam_request_page |

## Tam WebSocket endpoint cədvəli (5)

| URL pattern | Routing modulu | Consumer |
|---|---|---|
| ws/exams/final/room/<int:session_id>/ | apps.exams.routing | apps.exams.consumers.FinalExamRoomConsumer |
| ws/exams/final/wait/<int:ticket_id>/ | apps.exams.routing | apps.exams.consumers.FinalExamWaitConsumer |
| ws/exams/supervision/<int:attempt_id>/ | apps.exams.routing | apps.exams.consumers.ExamSupervisionConsumer |
| ws/live/<str:pin>/lobby/ | apps.live_exam.routing | apps.live_exam.consumers.LiveLobbyConsumer |
| ws/live/<str:pin>/play/ | apps.live_exam.routing | apps.live_exam.consumers.LivePlayConsumer |
