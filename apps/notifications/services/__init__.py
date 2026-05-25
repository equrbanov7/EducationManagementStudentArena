"""
Notification service layer.

Split out of a single ~1,000-line ``services.py`` module. Functions are grouped
by concern (crud, read_state, queries, events, profile_state) with shared
constants and helpers. This ``__init__`` re-exports every public name so
existing ``from apps.notifications.services import ...`` callers keep working
unchanged.

Modules:
* ``constants``      — role labels, status titles, task metadata table
* ``helpers``        — internal utilities (org-id, metadata, links, labels)
* ``crud``           — create / delete notification primitives
* ``read_state``     — read / unread state helpers
* ``queries``        — notification query helpers
* ``events``         — ``notify_*`` domain-event functions
* ``profile_state``  — profile notification state aggregator
"""

from .crud import (
    bulk_delete_notifications,
    create_notification,
    create_notification_for_users,
    delete_notification,
)
from .events import (
    get_exam_assigned_user_ids,
    get_lab_assigned_user_ids,
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
from .helpers import get_membership_request_role_label
from .profile_state import build_profile_notification_state
from .queries import get_user_notifications
from .read_state import (
    get_unread_count,
    mark_all_notifications_read,
    mark_notification_read,
    mark_notification_unread,
)

__all__ = [
    # crud
    "create_notification",
    "create_notification_for_users",
    "delete_notification",
    "bulk_delete_notifications",
    # read state
    "mark_notification_read",
    "mark_notification_unread",
    "mark_all_notifications_read",
    "get_unread_count",
    # queries
    "get_user_notifications",
    # helpers
    "get_membership_request_role_label",
    # events
    "notify_org_owner_pending_approval",
    "notify_org_admins_of_new_request",
    "notify_membership_request_resolution",
    "notify_member_removed_from_organization",
    "notify_user_invited_to_organization",
    "notify_course_membership_assigned",
    "notify_group_assignment",
    "notify_task_assignment",
    "get_exam_assigned_user_ids",
    "get_lab_assigned_user_ids",
    "notify_teacher_about_submission",
    "notify_student_about_feedback",
    # profile state
    "build_profile_notification_state",
]
