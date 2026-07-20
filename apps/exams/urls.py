# exams/urls.py
from django.urls import path

from . import views

app_name = "exams"

urlpatterns = [
    # ==========================
    # STUDENT - Exam Lists (sabit)
    # ==========================
    path("available/", views.student_exam_list, name="student_exam_list"),
    # Final imtahan mərkəzi — ayrıca PIN giriş səhifəsi (imtahan siyahısı YOX).
    # PIN yoxlamasından sonra HƏMİN səhifədə imtahan-öncəsi məlumat/qaydalar
    # modalı açılır → təsdiq → gözləmə otağı → nəzarətçi start-ı → attempt.
    path("final/", views.final_exam_entry, name="final_exam_entry"),
    path("final/waiting/<int:ticket_id>/", views.final_exam_waiting, name="final_exam_waiting"),
    path("final/waiting/<int:ticket_id>/cancel/", views.final_exam_cancel, name="final_exam_cancel"),
    path("final/waiting/<int:ticket_id>/begin/", views.final_exam_begin, name="final_exam_begin"),
    path("final/waiting/<int:ticket_id>/state/", views.final_ticket_state, name="final_ticket_state"),
    path("assigned/", views.assigned_student_exam_list, name="assigned_exam_list"),
    path("my-history/", views.student_exam_history, name="student_exam_history"),
    path("code-check/", views.exam_code_check, name="exam_code_check"),
    # ==========================
    # EXAM CENTER - Zallar / Oturumlar / Monitor / Hesabat (sabit)
    # ==========================
    path("center/rooms/", views.exam_center_room_list, name="exam_center_room_list"),
    # Zal səviyyəli aqreqasiya monitoru (bütün canlı oturumlar birlikdə).
    path("center/rooms/<int:room_id>/monitor/", views.exam_center_room_monitor, name="exam_center_room_monitor"),
    # Zala nəzarətçi təyini (imtahan mərkəzi paneli).
    path(
        "center/rooms/<int:room_id>/invigilators/",
        views.exam_center_room_assign_invigilators,
        name="exam_center_room_assign_invigilators",
    ),
    path(
        "center/rooms/<int:room_id>/api/snapshot/",
        views.exam_center_room_snapshot,
        name="exam_center_room_snapshot",
    ),
    path(
        "center/rooms/<int:room_id>/api/attempts/<int:attempt_id>/violations/",
        views.exam_center_attempt_violations,
        name="exam_center_attempt_violations",
    ),
    path("center/rooms/<int:room_id>/start-all/", views.exam_center_room_start_all, name="exam_center_room_start_all"),
    path("center/rooms/<int:room_id>/end-all/", views.exam_center_room_end_all, name="exam_center_room_end_all"),
    path("center/rooms/<int:room_id>/open-all/", views.exam_center_room_open_all, name="exam_center_room_open_all"),
    path("center/sessions/", views.exam_center_session_list, name="exam_center_session_list"),
    path("center/sessions/create/", views.exam_center_session_create, name="exam_center_session_create"),
    path("center/sessions/<int:session_id>/", views.exam_center_session_detail, name="exam_center_session_detail"),
    path(
        "center/sessions/<int:session_id>/history/",
        views.exam_center_session_history,
        name="exam_center_session_history",
    ),
    # Final təyinatları (imtahan-scoped — zaldan asılı deyil).
    path(
        "center/sessions/<int:session_id>/monitor/",
        views.exam_center_session_monitor,
        name="exam_center_session_monitor",
    ),
    path(
        "center/sessions/<int:session_id>/api/snapshot/",
        views.exam_center_session_snapshot,
        name="exam_center_session_snapshot",
    ),
    path(
        "center/sessions/<int:session_id>/tickets/<int:ticket_id>/snapshot/",
        views.exam_center_ticket_snapshot,
        name="exam_center_ticket_snapshot",
    ),
    path(
        "center/sessions/<int:session_id>/tickets/<int:ticket_id>/resume/",
        views.exam_center_ticket_resume,
        name="exam_center_ticket_resume",
    ),
    path(
        "center/sessions/<int:session_id>/tickets/<int:ticket_id>/reentry/",
        views.exam_center_ticket_reentry,
        name="exam_center_ticket_reentry",
    ),
    path(
        "center/sessions/<int:session_id>/open-entry/",
        views.exam_center_session_open_entry,
        name="exam_center_session_open_entry",
    ),
    path("center/sessions/<int:session_id>/start/", views.exam_center_session_start, name="exam_center_session_start"),
    path("center/sessions/<int:session_id>/end/", views.exam_center_session_end, name="exam_center_session_end"),
    path(
        "center/sessions/<int:session_id>/cancel/",
        views.exam_center_session_cancel,
        name="exam_center_session_cancel",
    ),
    path(
        "center/sessions/<int:session_id>/tickets/<int:ticket_id>/remove/",
        views.exam_center_ticket_remove,
        name="exam_center_ticket_remove",
    ),
    path(
        "center/sessions/<int:session_id>/tickets/<int:ticket_id>/seat/",
        views.exam_center_ticket_seat,
        name="exam_center_ticket_seat",
    ),
    path(
        "center/sessions/<int:session_id>/tickets/<int:ticket_id>/readmit/",
        views.exam_center_ticket_readmit,
        name="exam_center_ticket_readmit",
    ),
    path("center/reports/", views.exam_center_reports, name="exam_center_reports"),
    path("center/stats/data/", views.exam_center_stats_data, name="exam_center_stats_data"),
    path("center/stats/export/", views.exam_center_stats_export, name="exam_center_stats_export"),
    path("center/stats/filters/", views.exam_center_stats_filters, name="exam_center_stats_filters"),
    path("center/stats/charts/", views.exam_center_stats_charts, name="exam_center_stats_charts"),
    path("center/stats/ai/", views.exam_center_stats_ai, name="exam_center_stats_ai"),
    path("center/pin-lookup/", views.exam_center_pin_lookup, name="exam_center_pin_lookup"),
    path("center/pin-lookup/search/", views.exam_center_pin_search, name="exam_center_pin_search"),
    path(
        "center/pin-lookup/student/<int:student_id>/",
        views.exam_center_student_pins,
        name="exam_center_student_pins",
    ),
    # ==========================
    # TEACHER - Exams CRUD (sabit)
    # ==========================
    path("", views.teacher_exam_list, name="teacher_exam_list"),
    path("create/", views.createAndEditExamView, name="create_exam"),
    # Sehrbaz axtarışlı select-ləri üçün AJAX lookup endpoint-ləri.
    path("lookups/subjects/", views.subject_search, name="subject_search"),
    path("lookups/groups/", views.group_search, name="group_search"),
    path("lookups/faculties/", views.stats_faculty_search, name="stats_faculty_search"),
    path("lookups/departments/", views.stats_department_search, name="stats_department_search"),
    path("lookups/teachers/", views.stats_teacher_search, name="stats_teacher_search"),
    path("lookups/users/", views.user_search, name="user_search"),
    path("lookups/invigilators/", views.invigilator_search, name="invigilator_search"),
    path("lookups/assigned-count/", views.assigned_student_count, name="assigned_student_count"),
    path(
        "<slug:slug>/available-question-count/",
        views.exam_available_question_count,
        name="exam_available_question_count",
    ),
    path(
        "<slug:slug>/grant-extra-attempt/",
        views.grant_extra_attempt,
        name="grant_extra_attempt",
    ),
    path(
        "<slug:slug>/grant-extra-attempt-group/",
        views.grant_extra_attempt_group,
        name="grant_extra_attempt_group",
    ),
    path("pending-work/", views.teacher_pending_attempts, name="teacher_pending_attempts"),
    # ==========================
    # TEACHER - Question Bank library (imtahandan asılı olmayan) (sabit)
    # ==========================
    # P3: asinxron mətn-çıxarma (OCR-lı PDF importu üçün status-poll axını)
    path("import/extract-jobs/", views.start_text_extraction, name="start_text_extraction"),
    path("import/extract-jobs/<uuid:job_id>/", views.text_extraction_status, name="text_extraction_status"),
    path("export-jobs/<uuid:job_id>/waiting/", views.export_job_waiting, name="export_job_waiting"),
    path("export-jobs/<uuid:job_id>/download/", views.export_job_download, name="export_job_download"),
    # Müəllim → İmtahan mərkəzi sual göndərişi (elektron axın)
    path("question-submissions/new/", views.question_submission_create, name="question_submission_create"),
    path(
        "question-submissions/ai-generate/",
        views.ai_generate_submission_questions,
        name="ai_generate_submission_questions",
    ),
    path("question-submissions/inbox/", views.question_submission_inbox, name="question_submission_inbox"),
    path(
        "question-submissions/<int:submission_id>/",
        views.question_submission_detail,
        name="question_submission_detail",
    ),
    path(
        "question-submissions/<int:submission_id>/delete/",
        views.question_submission_delete,
        name="question_submission_delete",
    ),
    path(
        "question-submissions/<int:submission_id>/review/",
        views.question_submission_review,
        name="question_submission_review",
    ),
    path(
        "question-submissions/<int:submission_id>/decide/",
        views.question_submission_decide,
        name="question_submission_decide",
    ),
    path("question-bank/", views.question_bank_list, name="question_bank_list"),
    path("question-bank/<int:bank_id>/", views.question_bank_detail, name="question_bank_detail"),
    path("question-bank/<int:bank_id>/update/", views.question_bank_update, name="question_bank_update"),
    path("question-bank/<int:bank_id>/delete/", views.question_bank_delete, name="question_bank_delete"),
    path("question-bank/<int:bank_id>/bulk-add/", views.question_bank_bulk_add, name="question_bank_bulk_add"),
    path(
        "question-bank/<int:bank_id>/bulk-add/template-download/",
        views.question_bank_template_download,
        name="question_bank_template_download",
    ),
    path(
        "question-bank/<int:bank_id>/ai-generate/",
        views.ai_generate_bank_questions,
        name="ai_generate_bank_questions",
    ),
    path(
        "question-bank/<int:bank_id>/export.docx",
        views.question_bank_word_export,
        name="question_bank_word_export",
    ),
    path("question-bank/<int:bank_id>/questions/add/", views.bank_question_add, name="bank_question_add"),
    path(
        "question-bank/<int:bank_id>/questions/<int:question_id>/edit/",
        views.bank_question_edit,
        name="bank_question_edit",
    ),
    # ==========================
    # TEACHER - Student Groups (sabit)
    # ==========================
    path("groups/", views.teacher_group_list, name="teacher_group_list"),
    path("groups/create/form/", views.create_student_group, name="create_student_group"),
    path("groups/create/", views.teacher_create_group, name="teacher_create_group"),
    path(
        "groups/<int:group_id>/update/",
        views.teacher_update_group,
        name="teacher_update_group",
    ),
    path(
        "groups/<int:group_id>/delete/",
        views.teacher_delete_group,
        name="teacher_delete_group",
    ),
    path(
        "groups/<int:group_id>/students/<int:student_id>/remove/",
        views.teacher_remove_student_from_group,
        name="teacher_remove_student_from_group",
    ),
    path(
        "groups/<int:group_id>/students/<int:student_id>/add/",
        views.teacher_add_student_to_group,
        name="teacher_add_student_to_group",
    ),
    # ==========================
    # SLUG - Teacher Attempts (spesifik)
    # ==========================
    path(
        "<slug:slug>/attempt/<int:attempt_id>/check/",
        views.teacher_check_attempt,
        name="teacher_check_attempt",
    ),
    path(
        "<slug:slug>/attempt/<int:attempt_id>/ai-grade/",
        views.ai_grade_answer,
        name="ai_grade_answer",
    ),
    path(
        "<slug:slug>/attempt/<int:attempt_id>/view/",
        views.teacher_view_attempt,
        name="teacher_view_attempt",
    ),
    # ==========================
    # SLUG - Student Taking Exam (spesifik)
    # ==========================
    path("<slug:slug>/start/", views.start_exam, name="start_exam"),
    path(
        "<slug:slug>/attempt/<int:attempt_id>/result/",
        views.exam_result,
        name="exam_result",
    ),
    path(
        "<slug:slug>/attempt/<int:attempt_id>/coding/autosave/",
        views.coding_autosave,
        name="coding_autosave",
    ),
    path(
        "<slug:slug>/attempt/<int:attempt_id>/coding/run/",
        views.coding_run,
        name="coding_run",
    ),
    path(
        "<slug:slug>/attempt/<int:attempt_id>/coding/submit/",
        views.coding_submit,
        name="coding_submit",
    ),
    path(
        "<slug:slug>/attempt/<int:attempt_id>/coding/submissions/<int:submission_id>/download/",
        views.coding_submission_download,
        name="coding_submission_download",
    ),
    path("<slug:slug>/attempt/<int:attempt_id>/", views.take_exam, name="take_exam"),
    path(
        "<slug:slug>/attempt/<int:attempt_id>/question-seen/",
        views.question_seen,
        name="question_seen",
    ),
    # ==========================
    # SLUG - Teacher Question Bank
    # ==========================
    path(
        "<slug:slug>/question-bank/ai-generate/",
        views.ai_generate_question_bank,
        name="ai_generate_question_bank",
    ),
    path("<slug:slug>/test-bank/", views.test_question_bank, name="test_question_bank"),
    path(
        "<slug:slug>/questions/export.docx",
        views.exam_questions_word_export,
        name="exam_questions_word_export",
    ),
    path(
        "<slug:slug>/test-bank/template-download/",
        views.test_question_bank_template_download,
        name="test_question_bank_template_download",
    ),
    path(
        "<slug:slug>/create-bank/",
        views.create_question_bank,
        name="create_question_bank",
    ),
    path(
        "<slug:slug>/process-bank/",
        views.process_question_bank,
        name="process_question_bank",
    ),
    # ==========================
    # SLUG - Teacher Questions
    # ==========================
    path("<slug:slug>/add-question/", views.add_exam_question, name="add_exam_question"),
    path("<slug:slug>/questions-bank/", views.teacher_questions_bank, name="teacher_questions_bank"),
    path(
        "<slug:slug>/questions/<int:question_id>/edit/",
        views.edit_exam_question,
        name="edit_exam_question",
    ),
    path(
        "<slug:slug>/questions/<int:question_id>/delete/",
        views.delete_exam_question,
        name="delete_exam_question",
    ),
    path(
        "<slug:slug>/questions/page/",
        views.teacher_exam_detail_questions_page,
        name="teacher_exam_detail_questions_page",
    ),
    # ==========================
    # SLUG - Teacher Exam Ops
    # ==========================
    path("<slug:slug>/results/", views.teacher_exam_results, name="teacher_exam_results"),
    path("<slug:slug>/statistics/", views.teacher_exam_statistics, name="teacher_exam_statistics"),
    # Çoxdilli imtahan — dil variantlarının idarəsi
    path("<slug:slug>/languages/", views.exam_language_manager, name="exam_language_manager"),
    # Sual bankından imtahana sual əlavə et (picker)
    path("<slug:slug>/bank-picker/", views.exam_bank_picker, name="exam_bank_picker"),
    path(
        "<slug:slug>/results/delete-attempts/",
        views.delete_exam_attempts,
        name="delete_exam_attempts",
    ),
    path(
        "<slug:slug>/results/export.xlsx",
        views.export_exam_results_xlsx,
        name="export_exam_results_xlsx",
    ),
    path(
        "<slug:slug>/toggle-active/",
        views.toggle_exam_active,
        name="toggle_exam_active",
    ),
    path(
        "<slug:slug>/toggle-results-visibility/",
        views.toggle_exam_results_visibility,
        name="toggle_exam_results_visibility",
    ),
    path("<slug:slug>/edit/", views.createAndEditExamView, name="edit_exam"),
    path("<slug:slug>/delete/", views.delete_exam, name="delete_exam"),
    path("deleted/", views.deleted_exams_list, name="deleted_exams_list"),
    path("<slug:slug>/restore/", views.restore_exam, name="restore_exam"),
    path("<slug:slug>/permanent-delete/", views.permanent_delete_exam, name="permanent_delete_exam"),
    path("<slug:slug>/archive/", views.toggle_exam_archive, name="toggle_exam_archive"),
    path("<slug:slug>/duplicate/", views.duplicate_exam, name="duplicate_exam"),
    # ==========================
    # SUPERVISION API & MONITORING
    # ==========================
    path(
        "supervision/monitor/",
        views.supervision_monitor,
        name="supervision_monitor",
    ),
    path(
        "supervision/detail/<int:attempt_id>/",
        views.supervision_detail,
        name="supervision_detail",
    ),
    path(
        "supervision/live/<int:exam_id>/",
        views.exam_live_monitor,
        name="exam_live_monitor",
    ),
    path(
        "supervision/live/<int:exam_id>/poll/",
        views.exam_live_monitor_poll_api,
        name="exam_live_monitor_poll",
    ),
    path(
        "supervision/api/snapshot/<int:attempt_id>/",
        views.attempt_live_snapshot_api,
        name="attempt_live_snapshot",
    ),
    path(
        "supervision/api/log/<int:attempt_id>/",
        views.log_incident_api,
        name="supervision_log_incident",
    ),
    path(
        "supervision/api/status/<int:attempt_id>/",
        views.supervision_status_api,
        name="supervision_status_api",
    ),
    path(
        "supervision/api/resume/<int:attempt_id>/",
        views.teacher_resume_api,
        name="supervision_resume",
    ),
    path(
        "supervision/api/lock/<int:attempt_id>/",
        views.teacher_lock_api,
        name="supervision_lock",
    ),
    path(
        "supervision/api/stop/<int:attempt_id>/",
        views.teacher_stop_api,
        name="supervision_stop",
    ),
    # ✅ ƏN AXIRDA: Teacher exam detail (generic)
    path("<slug:slug>/", views.teacher_exam_detail, name="teacher_exam_detail"),
]
