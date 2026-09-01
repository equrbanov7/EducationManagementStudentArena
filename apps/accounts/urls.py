"""
URL patterns for accounts app.
"""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .views import academic_records as academic_records_views

app_name = "accounts"

urlpatterns = [
    # Authentication
    path("register/", views.register_view, name="register"),
    path("verify-code/", views.verify_code_view, name="verify_code"),
    path("verify-email/", views.verify_email_link_view, name="verify_email_link"),
    path("resend-code/", views.resend_code_view, name="resend_code"),
    path("send-otp/", views.send_otp_api_view, name="send_otp_api"),
    path("verify-otp/", views.verify_otp_api_view, name="verify_otp_api"),
    path("resend-otp/", views.resend_otp_api_view, name="resend_otp_api"),
    # First-login: provisioned users set their own password + verify email.
    path("set-password/", views.set_initial_password_view, name="set_initial_password"),
    # Login: generic /login/ artıq PORTAL SEÇİMİ (tələbə vs müəllim/əməkdaş);
    # əsl login formaları ayrı, ROL-QAPILI URL-lərdədir.
    path(
        "login/",
        views.login_portal,
        name="login",
    ),
    path(
        "login/muellim/",
        views.CustomLoginView.as_view(audience="staff"),
        name="staff_login",
    ),
    path(
        "login/telebe/",
        views.CustomLoginView.as_view(audience="student"),
        name="student_login",
    ),
    path("logout/", views.logout_view, name="logout"),
    # Password reset
    path(
        "password-reset/",
        views.NamespacedPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        views.NamespacedPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        views.NamespacedPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    # Cabinet entries — canonical role-aware entry plus visible audience aliases.
    path("kabinet/", views.cabinet_entry, name="cabinet"),
    path("kabinet/telebe/", views.student_cabinet_entry, name="student_cabinet"),
    path("kabinet/muellim/", views.staff_cabinet_entry, name="staff_cabinet"),
    # Dashboards
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/student/", views.student_dashboard, name="student_dashboard"),
    path("dashboard/teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    # Global search (⌘K command palette) — role/tenant-aware JSON.
    path("search/", views.global_search, name="global_search"),
    # Profile
    path("profile/", views.user_profile, name="profile"),
    path("profile/statistics/export-csv/", views.statistics_export_csv, name="statistics_export_csv"),
    # Staff iyerarxik akademik-qeyd icmalı ("Akademik qeydlər" profil bölməsi) —
    # cross-domain (registrar nəticələr + organizations strukturu) inteqrasiya
    # endpoint-ləri accounts-dadır (modul-sərhəd dövrünü önləmək üçün).
    path("profile/academic-records/data/", academic_records_views.records_overview_data, name="records_overview_data"),
    path(
        "profile/academic-records/summary/",
        academic_records_views.records_overview_summary,
        name="records_overview_summary",
    ),
    path(
        "profile/academic-records/student/",
        academic_records_views.records_student_detail,
        name="records_student_detail",
    ),
    path(
        "profile/academic-records/search/faculty/", academic_records_views.faculty_search, name="records_faculty_search"
    ),
    path(
        "profile/academic-records/search/department/",
        academic_records_views.department_search,
        name="records_department_search",
    ),
    path(
        "profile/academic-records/search/program/", academic_records_views.program_search, name="records_program_search"
    ),
    path("profile/academic-records/search/group/", academic_records_views.group_search, name="records_group_search"),
    path(
        "profile/academic-records/search/student/", academic_records_views.student_search, name="records_student_search"
    ),
    # Elektron jurnal siyahısının müəllim filtri (İKT rəhbəri/admin) — searchable picker.
    path(
        "profile/academic-records/search/teacher/",
        academic_records_views.journal_teacher_search,
        name="journal_teacher_search",
    ),
    # P3.1 + P3.2 — progressive enhancement endpoints. Heç bir mövcud URL
    # toxunulmur; bunlar JS-li klientlər üçün lazy-load üçündür.
    path(
        "profile/api/sections/<str:section>/",
        views.profile_section_fragment,
        name="profile_section_fragment",
    ),
    path(
        "profile/api/badges/",
        views.profile_badges_api,
        name="profile_badges_api",
    ),
    # «Akademik fəaliyyət» qeydləri (profil redaktəsi) + şifrə-dəyişmə OTP.
    path(
        "profile/api/academic-items/",
        views.academic_items_api,
        name="academic_items_api",
    ),
    path(
        "profile/api/password-otp/",
        views.change_password_otp_request,
        name="change_password_otp_request",
    ),
    path("profile-avatar/<int:user_id>/", views.profile_avatar, name="profile_avatar"),
    # "View as" — səlahiyyətli rolların başqa istifadəçinin profilinə baxışı
    path("view-as/search/", views.view_as_search, name="view_as_search"),
    path("view-as/start/", views.view_as_start, name="view_as_start"),
    path("view-as/stop/", views.view_as_stop, name="view_as_stop"),
    path("users/<str:username>/", views.public_user_profile, name="public_profile"),
    # Role management
    path("manage-roles/", views.manage_roles, name="manage_roles"),
    # Grading
    path("grading-queue/", views.grading_queue, name="grading_queue"),
    # Assigned items
    path("assigned-exams/", views.assigned_exams, name="assigned_exams"),
    path("assigned-courses/", views.assigned_courses, name="assigned_courses"),
    path("my-results/", views.my_results, name="my_results"),
    path("pending-answers/", views.pending_answers, name="pending_answers"),
    path("my-results/<str:item_type>/<int:item_id>/", views.my_result_detail, name="my_result_detail"),
    # Pending review
    path("pending-review/", views.pending_review, name="pending_review"),
    path(
        "pending-review/<str:item_type>/<int:item_id>/",
        views.pending_review_detail,
        name="pending_review_detail",
    ),
    path("review-results/", views.review_results, name="review_results"),
    path(
        "review-results/<str:item_type>/<int:item_id>/",
        views.review_result_detail,
        name="review_result_detail",
    ),
    # RBAC management
    path("role-assignment/", views.role_assignment, name="role_assignment"),
    path(
        "student-organization-management/",
        views.student_organization_management,
        name="student_organization_management",
    ),
    path(
        "student-organization-request/",
        views.student_organization_request,
        name="student_organization_request",
    ),
    path(
        "student-organization-invitation/",
        views.student_org_invitation_action,
        name="student_org_invitation_action",
    ),
    path(
        "student-leave-organization/",
        views.student_leave_organization,
        name="student_leave_organization",
    ),
    path("permission-editor/", views.permission_editor, name="permission_editor"),
    # Superadmin oversight
    path("superadmin/organizations/", views.superadmin_organizations, name="superadmin_organizations"),
    path("superadmin/ai-settings/", views.superadmin_ai_settings, name="superadmin_ai_settings"),
    path("superadmin/exam-rooms/", views.superadmin_exam_rooms, name="superadmin_exam_rooms"),
    path("kollokvium-windows/", views.kollokvium_windows, name="kollokvium_windows"),
    path("exam-chance/", views.exam_chance, name="exam_chance"),
    # İmtahan Mərkəzi — kağız (yazılı/praktiki) imtahan balının daxil edilməsi
    path("imtahan-bali/", views.exam_score_entry, name="exam_score_entry"),
    # RİM — semestr sonu toplu jurnal bağlaması + bağlanma xəbərdarlığı
    path("jurnal-baglama/", views.journal_close, name="journal_close"),
    # Account management
    path("delete-account/", views.delete_account, name="delete_account"),
    path("superadmin/users/", views.superadmin_user_management, name="superadmin_user_management"),
    # RİM mərkəzi — hesab idarəetməsi (icazə-qapılı: `user.*`, bax
    # apps/organizations/permissions.py «users» kateqoriyası). Superadmin
    # bölməsindən FƏRQLİ: burada rol icazəsi olan istənilən əməkdaş işləyir.
    path("rim/search/", views.rim_user_search, name="rim_user_search"),
    path("rim/user/<int:user_id>/", views.rim_user_detail, name="rim_user_detail"),
    path("rim/action/", views.rim_action, name="rim_action"),
    # «Müəllimlər» / «Tələbələr» kataloqu — icazə-qapılı (`people.*`) VƏ struktur
    # scope-una tabe. RİM-dən FƏRQİ: burada dekan/kafedra müdiri yalnız öz
    # alt-ağacını görür (bax apps/accounts/services/people/permissions.py).
    path("people/<str:kind>/list/", views.people_list, name="people_list"),
    path("people/<str:kind>/options/", views.people_options, name="people_options"),
    path("people/person/<int:user_id>/", views.people_detail, name="people_detail"),
    path("people/action/", views.people_action, name="people_action"),
    # Tələbə idarəetməsi (`people.manage_academic`) — kataloqun ÜSTÜNDƏ oturur,
    # paralel ikinci siyahı yaratmır. Hədəf: kart → user id, ön baxış → akademik
    # QEYD id-si (bir tələbənin bir neçə proqram qeydi ola bilər).
    path("people/student/<int:user_id>/card/", views.people_student_card, name="people_student_card"),
    path("people/academic/groups/", views.people_academic_groups, name="people_academic_groups"),
    path(
        "people/academic/<uuid:record_id>/transfer-preview/",
        views.people_transfer_preview,
        name="people_transfer_preview",
    ),
    # Analitika — cədvəldən AYRI endpoint (qrafik + göstəricilər eyni filtrlə).
    path("people/<str:kind>/analytics/", views.people_analytics, name="people_analytics"),
    path("people/<str:kind>/analytics/ai/", views.people_analytics_ai, name="people_analytics_ai"),
    # «Fənn təhvili» (`journal.reassign`) — dərs açılışının başqa müəllimə
    # verilməsi. Domen məntiqi registrar-dadır (apps/registrar/handover*.py);
    # burada yalnız profil bölməsinin JSON səthi var. Hamısı fail-closed:
    # icazəsiz aktor `has_access: false` alır, POST isə 403.
    path("handover/teachers/", views.handover_teachers, name="handover_teachers"),
    path("handover/offerings/", views.handover_offerings, name="handover_offerings"),
    path("handover/options/", views.handover_options, name="handover_options"),
    path("handover/history/", views.handover_history, name="handover_history"),
    path("handover/action/", views.handover_action, name="handover_action"),
    # «Köçürülmüş imtahan nəticələrinin dəqiqləşdirilməsi» (İmtahan Mərkəzi).
    # Növbə bazadakı sübut qatından (LegacyGradeFact + canlı FinalGrade güzgüsü)
    # hesablanır — domen məntiqi registrar-dadır (legacy_grade_review*.py).
    # Qərar/düzəliş qapısı `final_score.entry`; `journal.correct` yalnız OXU verir.
    path("legacy-review/queue/", views.legacy_review_queue, name="legacy_review_queue"),
    path("legacy-review/options/", views.legacy_review_options, name="legacy_review_options"),
    path("legacy-review/units/<str:kind>/", views.legacy_review_units, name="legacy_review_units"),
    path("legacy-review/groups/", views.legacy_review_groups, name="legacy_review_groups"),
    path("legacy-review/subjects/", views.legacy_review_subjects, name="legacy_review_subjects"),
    path("legacy-review/teachers/", views.legacy_review_teachers, name="legacy_review_teachers"),
    path("legacy-review/action/", views.legacy_review_action, name="legacy_review_action"),
    # Sillabus (müəllim səthi) — profil bölməsinin JSON endpoint-ləri.
    # Cross-domain glue accounts-dadır: `apps.syllabus` registrar/organizations
    # modullarını import etmir (modul-sərhəd dövrü yaranmır).
    path("profile/syllabus/action/", views.syllabus_action, name="syllabus_action"),
    path(
        "profile/syllabus/version/<uuid:version_id>/section/",
        views.syllabus_section_save,
        name="syllabus_section_save",
    ),
    path("profile/syllabus/<uuid:syllabus_id>/preview/", views.syllabus_preview, name="syllabus_preview"),
    # Sillabusun AYRICA TAM SƏHİFƏSİ — siyahıdan/təsdiq növbəsindən
    # `target="_blank"` ilə yeni tabda açılır. Profil bölməsi DEYİL, ona görə
    # `profile/` prefiksi yoxdur və `SECTION_PARTIALS`-a qeyd olunmur.
    path("syllabus/<uuid:syllabus_id>/", views.syllabus_detail, name="syllabus_detail"),
    path("syllabus/<uuid:syllabus_id>/pdf/", views.syllabus_detail_pdf, name="syllabus_detail_pdf"),
    # Kafedra təsdiq səthi: baxışı açmaq (SUBMITTED → REVIEW) və qərar yazmaq.
    path(
        "profile/syllabus/version/<uuid:version_id>/review/",
        views.syllabus_review_open,
        name="syllabus_review_open",
    ),
    path(
        "profile/syllabus/version/<uuid:version_id>/decision/",
        views.syllabus_decision,
        name="syllabus_decision",
    ),
    # Post management
    path("superadmin/post-management/", views.superadmin_post_management, name="superadmin_post_management"),
    path(
        "superadmin/post-management/<int:post_id>/delete/",
        views.superadmin_delete_post,
        name="superadmin_delete_post",
    ),
    path("org-post-management/", views.org_post_management, name="org_post_management"),
    path(
        "org-post-management/<int:post_id>/moderate/",
        views.org_moderate_post,
        name="org_moderate_post",
    ),
]
