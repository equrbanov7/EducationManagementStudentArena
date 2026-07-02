"""notifications modulunun PUBLIC API fasadı (M2/M3-B, 2026-07-02).

Digər modullar bildiriş göndərmək/oxumaq üçün YALNIZ bu fasadı istifadə
etməlidir (birbaşa models/servis-daxili importlar əvəzinə) — bax AGENTS §5.
Status/tip sabitləri üçün modellər (NotificationType və s.) get_model və ya
mövcud model importu ilə qalır; bura yalnız çağırıla bilən API daxildir.
"""

from apps.notifications.services import (  # noqa: F401
    build_profile_notification_state,
    create_notification,
    create_notification_for_users,
    get_exam_assigned_user_ids,
    get_lab_assigned_user_ids,
    get_unread_count,
    get_user_notifications,
    notify_course_membership_assigned,
    notify_group_assignment,
    notify_member_removed_from_organization,
    notify_membership_request_resolution,
    notify_org_admins_of_new_request,
    notify_org_owner_pending_approval,
    notify_student_about_feedback,
    notify_task_assignment,
    notify_teacher_about_submission,
    notify_user_invited_to_organization,
)

__all__ = [
    "build_profile_notification_state",
    "create_notification",
    "create_notification_for_users",
    "get_exam_assigned_user_ids",
    "get_lab_assigned_user_ids",
    "get_unread_count",
    "get_user_notifications",
    "notify_course_membership_assigned",
    "notify_group_assignment",
    "notify_member_removed_from_organization",
    "notify_membership_request_resolution",
    "notify_org_admins_of_new_request",
    "notify_org_owner_pending_approval",
    "notify_student_about_feedback",
    "notify_task_assignment",
    "notify_teacher_about_submission",
    "notify_user_invited_to_organization",
]
