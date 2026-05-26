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

from apps.accounts.models import ProfileRole
from apps.notifications.models import (
    InAppNotification,
    MembershipRequestRoleType,
    NotificationType,
    StudentOrganizationRequest,
    StudentOrganizationRequestStatus,
)
from apps.organizations.models import Membership

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
        "link_label": "Bildirişləri aç",
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
        title=f"Təşkilat müraciəti baxışdadır: {organization.name}",
        message=(
            f'"{organization.name}" təşkilatınız yaradıldı və hazırda superadmin tərəfindən '
            "təsdiq gözləyir. Təsdiqdən sonra idarəetmə bölmələri aktiv olacaq."
        ),
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


def notify_user_invited_to_organization(
    *, invited_user, organization, invited_by=None, role_label: str = ""
) -> InAppNotification:
    """
    Notify a user that they have been invited to join an organization.
    """
    actor_name = _display_name(invited_by) if invited_by is not None else ""
    role_label = (role_label or "").strip() or "üzv"
    message = (
        f"{organization.name} təşkilatından sizə {role_label} kimi dəvət göndərildi. "
        'Profildəki "Təşkilata qoşul" bölməsindən dəvəti qəbul edə bilərsiniz.'
    )
    if actor_name:
        message = f"{message} Dəvəti göndərən: {actor_name}."

    return create_notification(
        recipient=invited_user,
        title=f"Yeni təşkilat dəvəti: {organization.name}",
        message=message,
        link=f"{reverse('accounts:profile')}?{urlencode({'section': 'student-organization-request'})}",
        notification_type=NotificationType.APPROVAL,
        metadata={
            "organization_id": getattr(organization, "id", None),
            "organization_name": getattr(organization, "name", ""),
            "invited_by_id": getattr(invited_by, "id", None),
            "role_label": role_label,
            "link_label": "Dəvəti aç və cavablandır",
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
            "organization_id": _task_organization_id(task),
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
        title=task_meta["graded_title"].format(title=getattr(task, "title", "")),
        message=task_meta["graded_message"].format(title=getattr(task, "title", "")),
        link=_task_result_link(task, task_kind, metadata),
        notification_type=NotificationType.GRADE,
        metadata=metadata,
    )
