"""
Notification aggregation service.

This app is intentionally started as a service layer first so future
notification channels (in-app, email, push, websocket) can be added
without coupling UI logic to accounts views.
"""

import logging
from urllib.parse import urlencode
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.accounts.models import ProfileRole
from apps.accounts.policies.roles import map_org_role_to_profile_role
from apps.notifications.models import (
    InAppNotification,
    MembershipRequestRoleType,
    NotificationType,
    StudentOrganizationRequest,
    StudentOrganizationRequestStatus,
)
from apps.organizations.models import Membership

logger = logging.getLogger(__name__)

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


# ────────────────────────────────────────────────────────────────────────────
# In-App Notification Service
# ────────────────────────────────────────────────────────────────────────────


def create_notification(
    *,
    recipient,
    title: str,
    message: str = "",
    link: str = "",
    notification_type: str = NotificationType.SYSTEM,
    metadata: dict | None = None,
) -> InAppNotification:
    """
    Create a single in-app notification for *recipient*.

    Args:
        recipient: User instance that will receive the notification.
        title: Short notification title (max 255 chars).
        message: Optional full notification body.
        link: Optional URL the notification points to.
        notification_type: One of the ``NotificationType`` choices.
        metadata: Optional free-form dict stored as JSON.

    Returns:
        The newly created :class:`InAppNotification` instance.
    """
    return InAppNotification.objects.create(
        recipient=recipient,
        title=title,
        message=message,
        link=link,
        notification_type=notification_type,
        metadata=_serialize_metadata(metadata or {}),
    )


def create_notification_for_users(
    *,
    recipients,
    title: str,
    message: str = "",
    link: str = "",
    notification_type: str = NotificationType.SYSTEM,
    metadata: dict | None = None,
) -> list[InAppNotification]:
    """
    Create the same notification for multiple users in a single bulk insert.

    Args:
        recipients: Iterable of User instances.
        title: Short notification title.
        message: Optional notification body.
        link: Optional target URL.
        notification_type: One of the ``NotificationType`` choices.
        metadata: Optional free-form dict (shared across all recipients).

    Returns:
        List of created :class:`InAppNotification` instances.
    """
    payload = _serialize_metadata(metadata or {})
    notifications = [
        InAppNotification(
            recipient=user,
            title=title,
            message=message,
            link=link,
            notification_type=notification_type,
            metadata=payload,
        )
        for user in recipients
    ]
    return InAppNotification.objects.bulk_create(notifications)


# ────────────────────────────────────────────────────────────────────────────
# Read / Unread helpers
# ────────────────────────────────────────────────────────────────────────────


def mark_notification_read(*, notification: InAppNotification, user) -> bool:
    """
    Mark *notification* as read for *user*.

    Returns True if the state changed, False if it was already read.
    Raises PermissionError if *notification* does not belong to *user*.
    """
    _assert_owner(notification, user)
    if notification.is_read:
        return False
    notification.mark_read()
    return True


def mark_notification_unread(*, notification: InAppNotification, user) -> bool:
    """
    Mark *notification* as unread for *user*.

    Returns True if the state changed, False if it was already unread.
    Raises PermissionError if *notification* does not belong to *user*.
    """
    _assert_owner(notification, user)
    if not notification.is_read:
        return False
    notification.mark_unread()
    return True


def mark_all_notifications_read(*, user) -> int:
    """
    Mark all non-deleted, unread notifications for *user* as read.

    Returns the number of notifications updated.
    """
    now = timezone.now()
    updated = InAppNotification.objects.filter(
        recipient=user,
        deleted_at__isnull=True,
        is_read=False,
    ).update(is_read=True, read_at=now)
    return updated


# ────────────────────────────────────────────────────────────────────────────
# Delete helpers
# ────────────────────────────────────────────────────────────────────────────


def delete_notification(*, notification: InAppNotification, user) -> None:
    """
    Soft-delete *notification* for *user*.

    Raises PermissionError if *notification* does not belong to *user*.
    """
    _assert_owner(notification, user)
    notification.soft_delete()


def bulk_delete_notifications(*, notification_ids: list[int], user) -> int:
    """
    Soft-delete all notifications whose IDs are in *notification_ids* and
    that belong to *user*.  Unknown or other-user IDs are silently ignored.

    Returns the number of notifications deleted.
    """
    now = timezone.now()
    updated = InAppNotification.objects.filter(
        pk__in=notification_ids,
        recipient=user,
        deleted_at__isnull=True,
    ).update(deleted_at=now)
    return updated


# ────────────────────────────────────────────────────────────────────────────
# Query helpers
# ────────────────────────────────────────────────────────────────────────────


def get_user_notifications(*, user, filter_by: str = "all", notification_type: str = ""):
    """
    Return a QuerySet of non-deleted notifications for *user*, ordered
    newest-first.

    Args:
        user: The recipient user.
        filter_by: ``"all"`` | ``"unread"`` | ``"read"``
        notification_type: Optional ``NotificationType`` value to narrow results.
    """
    qs = InAppNotification.objects.filter(
        recipient=user,
        deleted_at__isnull=True,
    ).order_by("-created_at")

    if filter_by == "unread":
        qs = qs.filter(is_read=False)
    elif filter_by == "read":
        qs = qs.filter(is_read=True)

    if notification_type:
        qs = qs.filter(notification_type=notification_type)

    return qs


def get_unread_count(*, user) -> int:
    """Return the number of non-deleted unread notifications for *user*."""
    return InAppNotification.objects.filter(
        recipient=user,
        deleted_at__isnull=True,
        is_read=False,
    ).count()


def get_membership_request_role_label(role_type: str) -> str:
    return pgettext(
        "membership_request.role",
        MEMBERSHIP_REQUEST_ROLE_LABELS.get(role_type, "Member"),
    )


def notify_org_admins_of_new_request(*, request_obj: StudentOrganizationRequest) -> list[InAppNotification]:
    """
    Send a membership-request notification to organization owners/admins/HR.
    """
    UserModel = get_user_model()
    actor_name = _display_name(request_obj.user)
    role_label = get_membership_request_role_label(request_obj.role_type).lower()
    admin_user_ids = list(
        Membership.objects.filter(
            organization=request_obj.organization,
            is_active=True,
            role__name__in=["org_owner", "org_admin", "hr"],
        ).values_list("user_id", flat=True)
    )
    if request_obj.organization.owner_id and request_obj.organization.owner_id not in admin_user_ids:
        admin_user_ids.append(request_obj.organization.owner_id)

    if request_obj.role_type in {MembershipRequestRoleType.TEACHER, MembershipRequestRoleType.STAFF}:
        admin_user_ids.extend(
            UserModel.objects.filter(Q(is_superuser=True) | Q(profile__role=ProfileRole.SUPERADMIN)).values_list(
                "id", flat=True
            )
        )

    admin_user_ids = sorted({user_id for user_id in admin_user_ids if user_id and user_id != request_obj.user_id})

    if not admin_user_ids:
        return []

    return create_notification_for_users(
        recipients=UserModel.objects.filter(pk__in=admin_user_ids, is_active=True).distinct(),
        title=f"Yeni {role_label} müraciəti: {actor_name}",
        message=_membership_request_notification_message(request_obj),
        link=_membership_request_management_link(request_obj),
        notification_type=NotificationType.APPROVAL,
        metadata={
            "organization_id": request_obj.organization_id,
            "request_id": request_obj.id,
            "role_type": request_obj.role_type,
            "user_id": request_obj.user_id,
            "link_label": "Müraciəti aç və cavablandır",
            "organization_name": request_obj.organization.name,
            "applicant_name": request_obj.user.get_full_name() or request_obj.user.username,
            "applicant_username": request_obj.user.username,
            "applicant_email": request_obj.user.email,
        },
    )


def notify_membership_request_resolution(*, request_obj: StudentOrganizationRequest) -> InAppNotification | None:
    """
    Notify the applicant when their membership request receives a response.
    """
    if request_obj.status not in MEMBERSHIP_REQUEST_STATUS_TITLES:
        return None

    if (
        request_obj.status == StudentOrganizationRequestStatus.CANCELLED
        and request_obj.responded_by_id == request_obj.user_id
    ):
        return None

    role_label = get_membership_request_role_label(request_obj.role_type).lower()
    status_title = MEMBERSHIP_REQUEST_STATUS_TITLES[request_obj.status]
    resolution_note = (request_obj.resolution_note or "").strip()
    message = f"{request_obj.organization.name} təşkilatına {role_label} müraciətiniz üzrə cavab əlavə olundu."
    if request_obj.status == StudentOrganizationRequestStatus.APPROVED:
        message = f"{request_obj.organization.name} təşkilatına {role_label} müraciətiniz qəbul edildi."
    elif request_obj.status == StudentOrganizationRequestStatus.REJECTED:
        message = f"{request_obj.organization.name} təşkilatına {role_label} müraciətiniz rədd edildi."
    elif request_obj.status == StudentOrganizationRequestStatus.AUTO_CLOSED:
        message = f"{request_obj.organization.name} təşkilatına {role_label} müraciətiniz avtomatik bağlandı."
    if resolution_note:
        message = f"{message} Qeyd: {resolution_note}"

    return create_notification(
        recipient=request_obj.user,
        title=status_title,
        message=message,
        link=f"{reverse('accounts:profile')}?{urlencode({'section': 'notifications'})}",
        notification_type=NotificationType.APPROVAL,
        metadata={
            "organization_id": request_obj.organization_id,
            "request_id": request_obj.id,
            "role_type": request_obj.role_type,
            "status": request_obj.status,
        },
    )


def notify_member_removed_from_organization(
    *, removed_user, organization, removed_by=None, reason: str = ""
) -> InAppNotification:
    """
    Notify a user that they were removed from an organization by an admin.
    """
    actor_name = _display_name(removed_by) if removed_by is not None else ""
    message = (
        f"Siz {organization.name} təşkilatından uzaqlaşdırıldınız. "
        'İstəsəniz profilinizdəki "Təşkilata qoşul" bölməsindən yenidən müraciət göndərə bilərsiniz.'
    )
    if actor_name:
        message = f"{message} Əməliyyatı icra edən: {actor_name}."
    if reason:
        message = f"{message} Səbəb: {reason.strip()}"

    return create_notification(
        recipient=removed_user,
        title="Təşkilatdan uzaqlaşdırıldınız",
        message=message,
        link=f"{reverse('accounts:profile')}?{urlencode({'section': 'student-organization-request'})}",
        notification_type=NotificationType.SYSTEM,
        metadata={
            "organization_id": getattr(organization, "id", None),
            "organization_name": getattr(organization, "name", ""),
            "removed_by_id": getattr(removed_by, "id", None),
            "link_label": "Təşkilata qoşul bölməsini aç",
            "removal_reason": reason.strip(),
        },
    )


def notify_course_membership_assigned(
    *, membership, created: bool, previous_group_name: str = ""
) -> InAppNotification | None:
    """
    Notify a student when they are added to a course or moved to a group.
    """
    role_name = getattr(membership, "role", "")
    if role_name != "student":
        return None

    course_title = getattr(getattr(membership, "course", None), "title", "")
    current_group_name = (membership.group_name or "").strip()
    previous_group_name = (previous_group_name or "").strip()

    if created:
        title = f"Yeni kurs təyin olundu: {course_title}"
        message = f"Siz {course_title} kursuna əlavə olundunuz."
        if current_group_name:
            message = f"{message} Qrup: {current_group_name}."
    elif current_group_name and current_group_name != previous_group_name:
        title = f"Kurs qrupu yeniləndi: {course_title}"
        message = f"{course_title} kursunda qrupunuz {current_group_name} olaraq yeniləndi."
    else:
        return None

    return create_notification(
        recipient=membership.user,
        title=title,
        message=message,
        link=reverse("courses:course_dashboard", args=[membership.course_id]),
        notification_type=NotificationType.COURSE,
        metadata={
            "course_id": membership.course_id,
            "organization_id": getattr(membership.course, "organization_id", None),
            "group_name": current_group_name,
        },
    )


def notify_group_assignment(*, group, student_ids=None, teacher_ids=None) -> list[InAppNotification]:
    """
    Notify newly assigned students/teachers about a student-group assignment.
    """
    UserModel = get_user_model()
    notifications: list[InAppNotification] = []
    student_ids = sorted({int(user_id) for user_id in (student_ids or [])})
    teacher_ids = sorted({int(user_id) for user_id in (teacher_ids or [])})

    if student_ids:
        notifications.extend(
            create_notification_for_users(
                recipients=UserModel.objects.filter(pk__in=student_ids, is_active=True),
                title=f"Qrupa əlavə olundunuz: {group.name}",
                message=f"Siz {group.name} qrupuna əlavə olundunuz.",
                link=f"{reverse('accounts:profile')}?{urlencode({'section': 'profile-info'})}",
                notification_type=NotificationType.COURSE,
                metadata={"group_id": group.id, "organization_id": group.organization_id},
            )
        )

    if teacher_ids:
        notifications.extend(
            create_notification_for_users(
                recipients=UserModel.objects.filter(pk__in=teacher_ids, is_active=True),
                title=f"Yeni qrup təyin olundu: {group.name}",
                message=f"{group.name} qrupu sizə təyin olundu və artıq idarə edə bilərsiniz.",
                link=reverse("exams:teacher_group_list"),
                notification_type=NotificationType.COURSE,
                metadata={"group_id": group.id, "organization_id": group.organization_id},
            )
        )

    return notifications


def notify_task_assignment(*, task, user_ids, task_kind: str) -> list[InAppNotification]:
    """
    Notify users about a newly assigned task/exam/lab.
    """
    UserModel = get_user_model()
    task_meta = TASK_NOTIFICATION_META.get(task_kind)
    if not task_meta:
        return []

    unique_user_ids = sorted({int(user_id) for user_id in (user_ids or [])})
    if not unique_user_ids:
        return []

    course_title = getattr(getattr(task, "course", None), "title", "")
    title = task_meta["assigned_title"].format(title=getattr(task, "title", ""))
    message = task_meta["assigned_message"].format(
        title=getattr(task, "title", ""),
        course=course_title,
    )
    return create_notification_for_users(
        recipients=UserModel.objects.filter(pk__in=unique_user_ids, is_active=True),
        title=title,
        message=message,
        link=_task_detail_link(task, task_kind),
        notification_type=task_meta["notification_type"],
        metadata={
            "task_kind": task_kind,
            "task_id": task.id,
            "course_id": getattr(task, "course_id", None),
        },
    )


def get_exam_assigned_user_ids(exam) -> set[int]:
    assigned_user_ids = set(exam.allowed_users.values_list("id", flat=True))
    group_student_ids = exam.allowed_groups.values_list("students__id", flat=True)
    assigned_user_ids.update(student_id for student_id in group_student_ids if student_id)
    if exam.course_id:
        assigned_user_ids.update(exam.course.memberships.filter(role="student").values_list("user_id", flat=True))
    return assigned_user_ids


def get_lab_assigned_user_ids(lab) -> set[int]:
    from apps.courses.models import CourseMembership

    assigned_user_ids = set(lab.allowed_students.values_list("id", flat=True))
    group_names = lab.get_allowed_groups_list()
    if group_names:
        assigned_user_ids.update(
            CourseMembership.objects.filter(
                course=lab.course,
                role="student",
                group_name__in=group_names,
            ).values_list("user_id", flat=True)
        )
    elif not assigned_user_ids:
        assigned_user_ids.update(
            CourseMembership.objects.filter(course=lab.course, role="student").values_list("user_id", flat=True)
        )
    return assigned_user_ids


def notify_teacher_about_submission(*, task, student, task_kind: str) -> InAppNotification | None:
    task_meta = TASK_NOTIFICATION_META.get(task_kind)
    if not task_meta:
        return None

    teacher = _task_teacher(task, task_kind)
    if teacher is None or teacher.pk == getattr(student, "pk", None):
        return None

    return create_notification(
        recipient=teacher,
        title=task_meta["submission_title"].format(student=_display_name(student)),
        message=task_meta["submission_message"].format(
            student=_display_name(student),
            title=getattr(task, "title", ""),
        ),
        link=_task_review_link(task, task_kind),
        notification_type=task_meta["notification_type"],
        metadata={
            "task_kind": task_kind,
            "task_id": task.id,
            "student_id": getattr(student, "id", None),
        },
    )


def notify_student_about_feedback(*, task, student, task_kind: str, extra_metadata=None) -> InAppNotification | None:
    task_meta = TASK_NOTIFICATION_META.get(task_kind)
    if not task_meta or student is None:
        return None

    metadata = {
        "task_kind": task_kind,
        "task_id": task.id,
        "student_id": getattr(student, "id", None),
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    return create_notification(
        recipient=student,
        title=task_meta["graded_title"].format(title=getattr(task, "title", "")),
        message=task_meta["graded_message"].format(title=getattr(task, "title", "")),
        link=_task_result_link(task, task_kind, metadata),
        notification_type=NotificationType.GRADE,
        metadata=metadata,
    )


# ────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────────────


def _assert_owner(notification: InAppNotification, user) -> None:
    if notification.recipient_id != user.pk:
        raise PermissionError("You can only manage your own notifications.")


def _serialize_metadata(value):
    if isinstance(value, dict):
        return {str(key): _serialize_metadata(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_metadata(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat()
        except TypeError:
            return str(value)
    return value


def build_profile_notification_state(*, user, profile):
    pending_student_invites = list(
        Membership.objects.filter(
            user=user,
            is_active=False,
            title=STUDENT_PENDING_INVITE_TITLE,
            organization__is_active=True,
            organization__status="active",
        )
        .select_related("organization", "assigned_by", "role")
        .order_by("organization__name")
    )
    for pending_invite in pending_student_invites:
        invite_role_name = getattr(getattr(pending_invite, "role", None), "name", "")
        if invite_role_name in {
            "teacher",
            "instructor",
            "professor",
            "associate_professor",
            "assistant_teacher",
            "assistant",
        }:
            pending_invite.role_label = get_membership_request_role_label(MembershipRequestRoleType.TEACHER)
        elif invite_role_name == "student":
            pending_invite.role_label = get_membership_request_role_label(MembershipRequestRoleType.STUDENT)
        else:
            pending_invite.role_label = get_membership_request_role_label(MembershipRequestRoleType.STAFF)
        pending_invite.role_label_lower = str(pending_invite.role_label).lower()

    pending_student_join_requests = []
    pending_student_join_org_name = ""
    pending_student_join_message = ""
    if profile.organization is None:
        pending_student_join_requests = list(
            StudentOrganizationRequest.objects.filter(
                user=user,
                status=StudentOrganizationRequestStatus.PENDING,
                organization__is_active=True,
                organization__status="active",
            )
            .select_related("organization")
            .order_by("-created_at")
        )

        for pending_request in pending_student_join_requests:
            pending_request.role_label = get_membership_request_role_label(pending_request.role_type)
            pending_request.role_label_lower = str(pending_request.role_label).lower()
            pending_request.can_cancel = True

        if pending_student_join_requests:
            latest_request = pending_student_join_requests[0]
            pending_student_join_org_name = latest_request.organization.name
            pending_student_join_message = (latest_request.message or "").strip()

    active_membership = None
    membership_profile_role = None
    if profile.organization:
        active_membership = (
            Membership.objects.filter(
                user=user,
                organization=profile.organization,
                is_active=True,
            )
            .select_related("role")
            .order_by("-is_primary", "-role__level")
            .first()
        )
        membership_profile_role = map_org_role_to_profile_role(getattr(active_membership, "role", None))

    student_can_leave_org = bool(
        profile.organization
        and getattr(profile.organization, "owner_id", None) != user.id
        and (
            membership_profile_role
            in {
                ProfileRole.STUDENT,
                ProfileRole.LEAD_STUDENT,
                ProfileRole.TEACHER,
                ProfileRole.ASSISTANT_TEACHER,
                ProfileRole.MEMBER,
                ProfileRole.HR,
            }
            or (
                active_membership is None
                and profile.role
                in {
                    ProfileRole.STUDENT,
                    ProfileRole.LEAD_STUDENT,
                    ProfileRole.TEACHER,
                    ProfileRole.ASSISTANT_TEACHER,
                    ProfileRole.MEMBER,
                    ProfileRole.HR,
                }
            )
        )
    )

    unread_count = len(pending_student_invites) + len(pending_student_join_requests)

    return {
        "pending_student_invites": pending_student_invites,
        "pending_student_join_requests": pending_student_join_requests,
        "pending_student_join_org_name": pending_student_join_org_name,
        "pending_student_join_message": pending_student_join_message,
        "student_can_leave_org": student_can_leave_org,
        "unread_count": unread_count,
    }


def _display_name(user) -> str:
    return (user.get_full_name() or getattr(user, "username", "") or str(user)).strip()


def _membership_request_management_link(request_obj: StudentOrganizationRequest) -> str:
    profile_query = {
        "section": "student-organization-management",
        "management_view": "students",
        "student_tab": "pending",
        "highlight_request": request_obj.id,
    }

    if request_obj.role_type == MembershipRequestRoleType.TEACHER:
        profile_query.update(
            {
                "management_view": "teachers",
                "teacher_tab": "requests",
            }
        )
        profile_query.pop("student_tab", None)
    elif request_obj.role_type == MembershipRequestRoleType.STAFF:
        profile_query.update(
            {
                "management_view": "staff",
                "staff_tab": "requests",
            }
        )
        profile_query.pop("student_tab", None)

    next_url = f"{reverse('accounts:profile')}?{urlencode(profile_query)}"
    return f"{reverse('organizations:switch', kwargs={'slug': request_obj.organization.slug})}?{urlencode({'next': next_url})}"


def _membership_request_notification_message(request_obj: StudentOrganizationRequest) -> str:
    profile = getattr(request_obj.user, "profile", None)
    role_label = get_membership_request_role_label(request_obj.role_type)
    full_name = (request_obj.user.get_full_name() or "").strip() or request_obj.user.username
    lines = [
        f"Təşkilat: {request_obj.organization.name}",
        f"Ad soyad: {full_name}",
        f"Username: @{request_obj.user.username}",
        f"Email: {request_obj.user.email}",
        f"Müraciət növü: {role_label}",
    ]

    if profile is not None:
        department = (getattr(profile, "department", "") or "").strip()
        staff_position = (getattr(profile, "staff_position", "") or "").strip()
        student_specialization = (getattr(profile, "student_specialization", "") or "").strip()
        student_group_number = (getattr(profile, "student_group_number", "") or "").strip()

        if department:
            lines.append(f"Kafedra / Departament: {department}")
        if staff_position:
            lines.append(f"Vəzifə: {staff_position}")
        if request_obj.role_type == MembershipRequestRoleType.STUDENT and student_specialization:
            lines.append(f"İxtisas / Fakültə: {student_specialization}")
        if request_obj.role_type == MembershipRequestRoleType.STUDENT and student_group_number:
            lines.append(f"Qrup / Sinif: {student_group_number}")

    if request_obj.message:
        lines.append(f"Müraciət mesajı: {request_obj.message}")

    return "\n".join(lines)


def _task_detail_link(task, task_kind: str) -> str:
    if task_kind == "assignment":
        return reverse("assignments:assignment_detail", args=[task.id])
    if task_kind == "project":
        return reverse("projects:project_detail", args=[task.id])
    if task_kind == "lab":
        return reverse("labs:lab_detail", args=[task.id])
    if task_kind == "exam":
        return reverse("exams:assigned_exam_list")
    return ""


def _task_review_link(task, task_kind: str) -> str:
    if task_kind == "assignment":
        return reverse("assignments:review_assignment_submissions", args=[task.id])
    if task_kind == "project":
        return reverse("projects:review_project_submissions", args=[task.id])
    if task_kind == "lab":
        return reverse("labs:lab_submissions", args=[task.id])
    if task_kind == "exam":
        return reverse("exams:teacher_exam_results", args=[task.slug])
    return ""


def _task_result_link(task, task_kind: str, metadata: dict) -> str:
    if task_kind == "assignment":
        return reverse("assignments:my_submissions", args=[task.id])
    if task_kind == "project":
        return reverse("projects:my_submissions", args=[task.id])
    if task_kind == "lab":
        return reverse("labs:my_lab_answers", args=[task.id])
    if task_kind == "exam":
        attempt_id = metadata.get("attempt_id")
        if attempt_id:
            return reverse("exams:exam_result", args=[task.slug, attempt_id])
        return reverse("exams:assigned_exam_list")
    return ""


def _task_teacher(task, task_kind: str):
    if task_kind == "assignment":
        return getattr(getattr(task, "course", None), "owner", None)
    if task_kind == "project":
        return getattr(getattr(task, "course", None), "owner", None)
    if task_kind == "lab":
        return getattr(task, "created_by", None) or getattr(getattr(task, "course", None), "owner", None)
    if task_kind == "exam":
        return getattr(task, "author", None)
    return None
