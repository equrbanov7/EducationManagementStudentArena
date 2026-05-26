"""
Constants for the notification service layer.

Role labels, status titles, the task-notification metadata table and the
pending-org-owner event key, shared across the service modules.
"""

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
    StudentOrganizationRequestStatus.APPROVED: "Müraciətiniz təsdiqləndi",
    StudentOrganizationRequestStatus.REJECTED: "Müraciətiniz rədd edildi",
    StudentOrganizationRequestStatus.CANCELLED: "Müraciətiniz ləğv edildi",
    StudentOrganizationRequestStatus.AUTO_CLOSED: "Müraciətiniz bağlandı",
}

TASK_NOTIFICATION_META = {
    "assignment": {
        "label": "sərbəst iş",
        "assigned_title": "Yeni sərbəst iş təyin olundu: {title}",
        "assigned_message": '{course} kursunda "{title}" işi sizə təyin olundu.',
        "submission_title": "Yeni sərbəst iş cavabı: {student}",
        "submission_message": '"{title}" işi üçün {student} cavab göndərdi.',
        "graded_title": "Sərbəst iş nəticəniz hazırdır: {title}",
        "graded_message": '"{title}" işi üçün müəllim rəy və ya bal əlavə etdi.',
        "notification_type": NotificationType.ASSIGNMENT,
    },
    "project": {
        "label": "layihə",
        "assigned_title": "Yeni layihə təyin olundu: {title}",
        "assigned_message": '{course} kursunda "{title}" layihəsi sizə təyin olundu.',
        "submission_title": "Yeni layihə cavabı: {student}",
        "submission_message": '"{title}" layihəsi üçün {student} cavab göndərdi.',
        "graded_title": "Layihə nəticəniz hazırdır: {title}",
        "graded_message": '"{title}" layihəsi üçün müəllim rəy və ya bal əlavə etdi.',
        "notification_type": NotificationType.ASSIGNMENT,
    },
    "lab": {
        "label": "lab",
        "assigned_title": "Yeni lab təyin olundu: {title}",
        "assigned_message": '{course} kursunda "{title}" lab işi sizin üçün aktivdir.',
        "submission_title": "Yeni lab göndərişi: {student}",
        "submission_message": '"{title}" labı üçün {student} cavab göndərdi.',
        "graded_title": "Lab nəticəniz hazırdır: {title}",
        "graded_message": '"{title}" labı üçün müəllim rəy və ya bal əlavə etdi.',
        "notification_type": NotificationType.ASSIGNMENT,
    },
    "exam": {
        "label": "imtahan",
        "assigned_title": "Yeni imtahan təyin olundu: {title}",
        "assigned_message": '"{title}" imtahanı sizin üçün aktivdir.',
        "submission_title": "Yeni imtahan cəhdi: {student}",
        "submission_message": '"{title}" imtahanı üçün {student} cavabını göndərdi.',
        "graded_title": "İmtahan nəticəniz yeniləndi: {title}",
        "graded_message": '"{title}" imtahanı üçün müəllim rəy və ya bal əlavə etdi.',
        "notification_type": NotificationType.EXAM,
    },
}

PENDING_ORG_OWNER_NOTIFICATION_EVENT = "organization_pending_approval"
