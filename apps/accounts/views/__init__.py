"""
Accounts views package.

This package contains all account-related views split into logical modules:
- auth.py: Authentication views (register, login, logout, verification)
- profile.py: User profile views (profile management, avatar)
- dashboard.py: Dashboard views (teacher/student dashboards, grading, results)
- roles.py: Role management views (manage roles, role assignment, permissions)
- organization.py: Organization management views (student requests, invitations)
- superadmin.py: Superadmin views (organization oversight)

All views are re-exported here for backward compatibility with existing URLs.
"""

# Account management views
from .account_management import (
    delete_account,
    superadmin_user_management,
)

# «Müraciətlərim» — «Təyin et» dialoqunun namizəd siyahısı
from .applications import applications_assignees

# Authentication views
from .auth import (
    CustomLoginView,
    NamespacedPasswordResetConfirmView,
    NamespacedPasswordResetDoneView,
    NamespacedPasswordResetView,
    login_portal,
    logout_view,
    register_view,
    resend_code_view,
    resend_otp_api_view,
    send_otp_api_view,
    set_initial_password_view,
    verify_code_view,
    verify_email_link_view,
    verify_otp_api_view,
)

# Dashboard views
from .dashboard import (
    assigned_courses,
    assigned_exams,
    cabinet_entry,
    dashboard,
    grading_queue,
    my_result_detail,
    my_results,
    pending_answers,
    pending_review,
    pending_review_detail,
    review_result_detail,
    review_results,
    staff_cabinet_entry,
    student_cabinet_entry,
    student_dashboard,
    teacher_dashboard,
)

# İmtahan Mərkəzi — kollokvium bal-yazma pəncərələri
from .exam_chance import exam_chance

# İmtahan Mərkəzi — kağız imtahan balının əl ilə daxil edilməsi
from .exam_score_entry import exam_score_entry

# Fənn təhvili — dərs açılışının başqa müəllimə verilməsi (`journal.reassign`)
from .handover import (
    handover_action,
    handover_history,
    handover_offerings,
    handover_options,
    handover_teachers,
)

# RİM — semestr sonu jurnal bağlaması
from .journal_close import journal_close
from .kollokvium_windows import kollokvium_windows

# İmtahan Mərkəzi — köçürülmüş imtahan nəticələrinin dəqiqləşdirilməsi
from .legacy_review import (
    legacy_review_action,
    legacy_review_groups,
    legacy_review_options,
    legacy_review_queue,
    legacy_review_subjects,
    legacy_review_teachers,
    legacy_review_units,
)

# Organization views
from .organization import (
    student_leave_organization,
    student_org_invitation_action,
    student_organization_management,
    student_organization_request,
)

# RİM mərkəzi — hesab idarəetməsi (icazə-qapılı, superadmin-only DEYİL)
from .people import (
    people_academic_groups,
    people_action,
    people_analytics,
    people_analytics_ai,
    people_detail,
    people_list,
    people_options,
    people_student_card,
    people_transfer_preview,
)

# Post management views
from .post_management import (
    org_moderate_post,
    org_post_management,
    superadmin_delete_post,
    superadmin_post_management,
)

# Profile views
from .profile import (
    academic_items_api,
    change_password_otp_request,
    profile_avatar,
    profile_badges_api,
    profile_section_fragment,
    public_user_profile,
    statistics_export_csv,
    user_profile,
    view_as_search,
    view_as_start,
    view_as_stop,
)
from .rim import rim_action, rim_user_detail, rim_user_search

# Role management views
from .roles import (
    manage_roles,
    permission_editor,
    role_assignment,
)

# Cədvəl idarəetməsi (`schedule.manage`) JSON səthi
from .schedule_manage import schedule_manage_action, schedule_manage_check
from .student_intake import student_intake_apply, student_intake_preview, student_intake_template

# Global search (⌘K command palette)
from .search import global_search

# Superadmin views
from .superadmin import (
    superadmin_ai_settings,
    superadmin_exam_rooms,
    superadmin_organizations,
)

# Sillabus — müəllim səthi (siyahı + redaktor) profil bölməsi kimi açılır
from .syllabus import (
    syllabus_action,
    syllabus_decision,
    syllabus_detail,
    syllabus_detail_pdf,
    syllabus_preview,
    syllabus_review_open,
    syllabus_section_save,
)

__all__ = [
    # Authentication
    "CustomLoginView",
    "login_portal",
    "NamespacedPasswordResetView",
    "NamespacedPasswordResetDoneView",
    "NamespacedPasswordResetConfirmView",
    "register_view",
    "verify_code_view",
    "verify_email_link_view",
    "resend_code_view",
    "send_otp_api_view",
    "set_initial_password_view",
    "verify_otp_api_view",
    "resend_otp_api_view",
    "logout_view",
    # Profile
    "user_profile",
    "academic_items_api",
    "change_password_otp_request",
    "public_user_profile",
    "profile_avatar",
    "statistics_export_csv",
    "profile_section_fragment",
    "profile_badges_api",
    # "View as" — istifadəçi profilinə baxış
    "view_as_search",
    "view_as_start",
    "view_as_stop",
    # Global search (⌘K)
    "global_search",
    # Dashboard
    "dashboard",
    "cabinet_entry",
    "student_cabinet_entry",
    "staff_cabinet_entry",
    "teacher_dashboard",
    "student_dashboard",
    "grading_queue",
    "assigned_exams",
    "assigned_courses",
    "my_results",
    "pending_answers",
    "my_result_detail",
    "pending_review",
    "pending_review_detail",
    "review_results",
    "review_result_detail",
    # Roles
    "manage_roles",
    "role_assignment",
    "permission_editor",
    # Organization
    "student_organization_management",
    "student_organization_request",
    "student_org_invitation_action",
    "student_leave_organization",
    # Account management
    "delete_account",
    "superadmin_user_management",
    # RİM mərkəzi — hesab idarəetməsi (axtarış/parol/blok/silmə/redaktə)
    "people_list",
    "people_options",
    "people_detail",
    "people_action",
    "people_analytics",
    "people_analytics_ai",
    "people_student_card",
    "people_academic_groups",
    "people_transfer_preview",
    # Fənn təhvili (`journal.reassign`)
    "handover_teachers",
    "handover_offerings",
    "handover_options",
    "handover_history",
    "handover_action",
    "applications_assignees",
    "schedule_manage_check",
    "schedule_manage_action",
    "student_intake_template",
    "student_intake_preview",
    "student_intake_apply",
    # Köçürülmüş imtahan nəticələrinin dəqiqləşdirilməsi (`final_score.entry`)
    "legacy_review_queue",
    "legacy_review_options",
    "legacy_review_units",
    "legacy_review_groups",
    "legacy_review_subjects",
    "legacy_review_teachers",
    "legacy_review_action",
    "rim_user_search",
    "rim_user_detail",
    "rim_action",
    # Sillabus — müəllim səthi (autosave / əməllər / baxış paneli)
    "syllabus_action",
    "syllabus_decision",
    "syllabus_detail",
    "syllabus_detail_pdf",
    "syllabus_preview",
    "syllabus_review_open",
    "syllabus_section_save",
    # Post management
    "superadmin_post_management",
    "superadmin_delete_post",
    "org_post_management",
    "org_moderate_post",
    # Superadmin
    "superadmin_organizations",
    "superadmin_ai_settings",
    "superadmin_exam_rooms",
    "exam_chance",
    "kollokvium_windows",
    "exam_score_entry",
    "journal_close",
]
