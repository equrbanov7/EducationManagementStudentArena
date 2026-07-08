"""
Notification event functions.

One ``notify_*`` function per domain event (membership requests, removals,
invitations, course/group/task assignments, submissions, feedback). Each
builds on the ``crud`` primitives and the ``helpers`` link/message builders.
"""

from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import pgettext

from apps.notifications.models import (
    InAppNotification,
    MembershipRequestRoleType,
    NotificationType,
    StudentOrganizationRequest,
    StudentOrganizationRequestStatus,
)
from apps.organizations.models import Membership
from core.roles import ProfileRole

from .constants import (
    MEMBERSHIP_REQUEST_STATUS_TITLES,
    PENDING_ORG_OWNER_NOTIFICATION_EVENT,
    TASK_NOTIFICATION_META,
)
from .crud import create_notification, create_notification_for_users
from .helpers import (
    _display_name,
    _membership_request_management_link,
    _membership_request_notification_message,
    _task_detail_link,
    _task_organization_id,
    _task_result_link,
    _task_review_link,
    _task_teacher,
    get_membership_request_role_label,
)


def notify_org_owner_pending_approval(*, organization) -> InAppNotification | None:
    """
    Ensure the organization owner sees a pending-approval notification.

    The helper is idempotent: if the same pending-approval notification already
    exists for the owner and organization, it is reused instead of duplicated.
    """
    owner = getattr(organization, "owner", None)
    owner_id = getattr(organization, "owner_id", None)
    if owner is None or owner_id is None:
        return None

    metadata = {
        "event": PENDING_ORG_OWNER_NOTIFICATION_EVENT,
        "organization_id": str(getattr(organization, "id", "")),
        "organization_name": getattr(organization, "name", ""),
        "status": "pending",
        "link_label": pgettext("notifications.event", "Open notifications"),
    }
    existing = (
        InAppNotification.objects.filter(
            recipient=owner,
            deleted_at__isnull=True,
            metadata__event=PENDING_ORG_OWNER_NOTIFICATION_EVENT,
            metadata__organization_id=str(getattr(organization, "id", "")),
        )
        .order_by("-created_at")
        .first()
    )
    if existing is not None:
        return existing

    return create_notification(
        recipient=owner,
        title=pgettext("notifications.event", "Organization request is under review: {organization}").format(
            organization=organization.name
        ),
        message=pgettext(
            "notifications.event",
            '"{organization}" has been created and is currently awaiting superadmin approval. '
            "Management sections will become active after approval.",
        ).format(organization=organization.name),
        link=f"{reverse('accounts:profile')}?{urlencode({'section': 'notifications'})}",
        notification_type=NotificationType.APPROVAL,
        metadata=metadata,
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
        title=pgettext("notifications.event", "New {role_label} request: {actor_name}").format(
            role_label=role_label, actor_name=actor_name
        ),
        message=_membership_request_notification_message(request_obj),
        link=_membership_request_management_link(request_obj),
        notification_type=NotificationType.APPROVAL,
        metadata={
            "organization_id": request_obj.organization_id,
            "request_id": request_obj.id,
            "role_type": request_obj.role_type,
            "user_id": request_obj.user_id,
            "link_label": pgettext("notifications.event", "Open request and respond"),
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
    status_title = str(MEMBERSHIP_REQUEST_STATUS_TITLES[request_obj.status])
    resolution_note = (request_obj.resolution_note or "").strip()
    message = pgettext(
        "notifications.event",
        "{organization} organization: a response was added to your {role_label} request.",
    ).format(organization=request_obj.organization.name, role_label=role_label)
    if request_obj.status == StudentOrganizationRequestStatus.APPROVED:
        message = pgettext(
            "notifications.event",
            "{organization} organization: your {role_label} request was approved.",
        ).format(organization=request_obj.organization.name, role_label=role_label)
    elif request_obj.status == StudentOrganizationRequestStatus.REJECTED:
        message = pgettext(
            "notifications.event",
            "{organization} organization: your {role_label} request was rejected.",
        ).format(organization=request_obj.organization.name, role_label=role_label)
    elif request_obj.status == StudentOrganizationRequestStatus.AUTO_CLOSED:
        message = pgettext(
            "notifications.event",
            "{organization} organization: your {role_label} request was closed automatically.",
        ).format(organization=request_obj.organization.name, role_label=role_label)
    if resolution_note:
        note_text = pgettext("notifications.event", "Note: {note}").format(note=resolution_note)
        message = f"{message} {note_text}"

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
    message = pgettext(
        "notifications.event",
        'You were removed from {organization}. You can submit a new request from the "Join organization" '
        "section in your profile.",
    ).format(organization=organization.name)
    if actor_name:
        actor_text = pgettext("notifications.event", "Action performed by: {actor}.").format(actor=actor_name)
        message = f"{message} {actor_text}"
    if reason:
        reason_text = pgettext("notifications.event", "Reason: {reason}").format(reason=reason.strip())
        message = f"{message} {reason_text}"

    return create_notification(
        recipient=removed_user,
        title=pgettext("notifications.event", "You were removed from the organization"),
        message=message,
        link=f"{reverse('accounts:profile')}?{urlencode({'section': 'student-organization-request'})}",
        notification_type=NotificationType.SYSTEM,
        metadata={
            "organization_id": getattr(organization, "id", None),
            "organization_name": getattr(organization, "name", ""),
            "removed_by_id": getattr(removed_by, "id", None),
            "link_label": pgettext("notifications.event", "Open Join organization section"),
            "removal_reason": reason.strip(),
        },
    )


def notify_user_invited_to_organization(
    *, invited_user, organization, invited_by=None, role_label: str = ""
) -> InAppNotification:
    """
    Notify a user that they have been invited to join an organization.
    """
    actor_name = _display_name(invited_by) if invited_by is not None else ""
    role_label = (role_label or "").strip() or pgettext("membership_request.role", "Member").lower()
    message = pgettext(
        "notifications.event",
        '{organization} sent you an invitation as {role_label}. You can accept the invitation from the "Join '
        'organization" section in your profile.',
    ).format(organization=organization.name, role_label=role_label)
    if actor_name:
        invited_by_text = pgettext("notifications.event", "Invited by: {actor}.").format(actor=actor_name)
        message = f"{message} {invited_by_text}"

    return create_notification(
        recipient=invited_user,
        title=pgettext("notifications.event", "New organization invitation: {organization}").format(
            organization=organization.name
        ),
        message=message,
        link=f"{reverse('accounts:profile')}?{urlencode({'section': 'student-organization-request'})}",
        notification_type=NotificationType.APPROVAL,
        metadata={
            "organization_id": getattr(organization, "id", None),
            "organization_name": getattr(organization, "name", ""),
            "invited_by_id": getattr(invited_by, "id", None),
            "role_label": role_label,
            "link_label": pgettext("notifications.event", "Open invitation and respond"),
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
        title = pgettext("notifications.event", "New course assigned: {course}").format(course=course_title)
        message = pgettext("notifications.event", "You were added to {course} course.").format(course=course_title)
        if current_group_name:
            group_text = pgettext("notifications.event", "Group: {group}.").format(group=current_group_name)
            message = f"{message} {group_text}"
    elif current_group_name and current_group_name != previous_group_name:
        title = pgettext("notifications.event", "Course group updated: {course}").format(course=course_title)
        message = pgettext(
            "notifications.event",
            "Your group in {course} course was updated to {group}.",
        ).format(course=course_title, group=current_group_name)
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
                title=pgettext("notifications.event", "You were added to a group: {group}").format(group=group.name),
                message=pgettext("notifications.event", "You were added to {group} group.").format(group=group.name),
                link=f"{reverse('accounts:profile')}?{urlencode({'section': 'profile-info'})}",
                notification_type=NotificationType.COURSE,
                metadata={"group_id": group.id, "organization_id": group.organization_id},
            )
        )

    if teacher_ids:
        notifications.extend(
            create_notification_for_users(
                recipients=UserModel.objects.filter(pk__in=teacher_ids, is_active=True),
                title=pgettext("notifications.event", "New group assigned: {group}").format(group=group.name),
                message=pgettext(
                    "notifications.event",
                    "{group} group was assigned to you and you can now manage it.",
                ).format(group=group.name),
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
    title = str(task_meta["assigned_title"]).format(title=getattr(task, "title", ""))
    message = str(task_meta["assigned_message"]).format(
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
            "organization_id": _task_organization_id(task),
        },
    )


def get_exam_assigned_user_ids(exam) -> set[int]:
    assigned_user_ids = set(exam.allowed_users.values_list("id", flat=True))
    group_student_ids = exam.allowed_groups.values_list("students__id", flat=True)
    assigned_user_ids.update(student_id for student_id in group_student_ids if student_id)
    if exam.course_id:
        assigned_user_ids.update(exam.course.memberships.filter(role="student").values_list("user_id", flat=True))
    assigned_user_ids.difference_update(exam.excluded_users.values_list("id", flat=True))
    return assigned_user_ids


def get_lab_assigned_user_ids(lab) -> set[int]:
    # M2 (2026-07-02): statik import əvəzinə lazy get_model — courses↔notifications
    # dövri asılılığı əridilir (davranış eyni).
    from django.apps import apps as django_apps

    CourseMembership = django_apps.get_model("courses", "CourseMembership")

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
        title=str(task_meta["submission_title"]).format(student=_display_name(student)),
        message=str(task_meta["submission_message"]).format(
            student=_display_name(student),
            title=getattr(task, "title", ""),
        ),
        link=_task_review_link(task, task_kind),
        notification_type=task_meta["notification_type"],
        metadata={
            "task_kind": task_kind,
            "task_id": task.id,
            "student_id": getattr(student, "id", None),
            "organization_id": _task_organization_id(task),
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
        "organization_id": _task_organization_id(task),
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    return create_notification(
        recipient=student,
        title=str(task_meta["graded_title"]).format(title=getattr(task, "title", "")),
        message=str(task_meta["graded_message"]).format(title=getattr(task, "title", "")),
        link=_task_result_link(task, task_kind, metadata),
        notification_type=NotificationType.GRADE,
        metadata=metadata,
    )
