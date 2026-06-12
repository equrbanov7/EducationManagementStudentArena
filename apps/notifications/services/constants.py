"""
Constants for the notification service layer.

Role labels, status titles, the task-notification metadata table and the
pending-org-owner event key, shared across the service modules.
"""

from django.utils.translation import pgettext_lazy

from apps.notifications.models import (
    MembershipRequestRoleType,
    NotificationType,
    StudentOrganizationRequestStatus,
)

STUDENT_PENDING_INVITE_TITLE = "__student_pending_invite__"

MEMBERSHIP_REQUEST_ROLE_LABELS = {
    MembershipRequestRoleType.STUDENT: "Student",
    MembershipRequestRoleType.TEACHER: "Teacher",
    MembershipRequestRoleType.STAFF: "Staff",
}

MEMBERSHIP_REQUEST_STATUS_TITLES = {
    StudentOrganizationRequestStatus.APPROVED: pgettext_lazy("notifications.event", "Your request was approved"),
    StudentOrganizationRequestStatus.REJECTED: pgettext_lazy("notifications.event", "Your request was rejected"),
    StudentOrganizationRequestStatus.CANCELLED: pgettext_lazy("notifications.event", "Your request was cancelled"),
    StudentOrganizationRequestStatus.AUTO_CLOSED: pgettext_lazy("notifications.event", "Your request was closed"),
}

TASK_NOTIFICATION_META = {
    "assignment": {
        "label": pgettext_lazy("notifications.event.task_kind", "assignment"),
        "assigned_title": pgettext_lazy("notifications.event", "New assignment assigned: {title}"),
        "assigned_message": pgettext_lazy(
            "notifications.event",
            '{course} course: "{title}" has been assigned to you.',
        ),
        "submission_title": pgettext_lazy("notifications.event", "New assignment submission: {student}"),
        "submission_message": pgettext_lazy(
            "notifications.event",
            '{student} submitted an answer for "{title}".',
        ),
        "graded_title": pgettext_lazy("notifications.event", "Your assignment result is ready: {title}"),
        "graded_message": pgettext_lazy(
            "notifications.event",
            'The teacher added feedback or a score for "{title}".',
        ),
        "notification_type": NotificationType.ASSIGNMENT,
    },
    "project": {
        "label": pgettext_lazy("notifications.event.task_kind", "project"),
        "assigned_title": pgettext_lazy("notifications.event", "New project assigned: {title}"),
        "assigned_message": pgettext_lazy(
            "notifications.event",
            '{course} course: "{title}" project has been assigned to you.',
        ),
        "submission_title": pgettext_lazy("notifications.event", "New project submission: {student}"),
        "submission_message": pgettext_lazy(
            "notifications.event",
            '{student} submitted an answer for "{title}" project.',
        ),
        "graded_title": pgettext_lazy("notifications.event", "Your project result is ready: {title}"),
        "graded_message": pgettext_lazy(
            "notifications.event",
            'The teacher added feedback or a score for "{title}" project.',
        ),
        "notification_type": NotificationType.ASSIGNMENT,
    },
    "lab": {
        "label": pgettext_lazy("notifications.event.task_kind", "lab"),
        "assigned_title": pgettext_lazy("notifications.event", "New lab assigned: {title}"),
        "assigned_message": pgettext_lazy(
            "notifications.event",
            '{course} course: "{title}" lab is active for you.',
        ),
        "submission_title": pgettext_lazy("notifications.event", "New lab submission: {student}"),
        "submission_message": pgettext_lazy(
            "notifications.event",
            '{student} submitted an answer for "{title}" lab.',
        ),
        "graded_title": pgettext_lazy("notifications.event", "Your lab result is ready: {title}"),
        "graded_message": pgettext_lazy(
            "notifications.event",
            'The teacher added feedback or a score for "{title}" lab.',
        ),
        "notification_type": NotificationType.ASSIGNMENT,
    },
    "exam": {
        "label": pgettext_lazy("notifications.event.task_kind", "exam"),
        "assigned_title": pgettext_lazy("notifications.event", "New exam assigned: {title}"),
        "assigned_message": pgettext_lazy(
            "notifications.event",
            '"{title}" exam is active for you.',
        ),
        "submission_title": pgettext_lazy("notifications.event", "New exam attempt: {student}"),
        "submission_message": pgettext_lazy(
            "notifications.event",
            '{student} submitted an answer for "{title}" exam.',
        ),
        "graded_title": pgettext_lazy("notifications.event", "Your exam result was updated: {title}"),
        "graded_message": pgettext_lazy(
            "notifications.event",
            'The teacher added feedback or a score for "{title}" exam.',
        ),
        "notification_type": NotificationType.EXAM,
    },
}

PENDING_ORG_OWNER_NOTIFICATION_EVENT = "organization_pending_approval"
