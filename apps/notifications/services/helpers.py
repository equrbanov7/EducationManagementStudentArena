"""
Internal helpers for the notification service layer.

Pure-ish utilities: organization-id resolution, metadata serialization,
ownership assertion, display-name formatting, role-label lookup and the
link/message builders used by the event functions.
"""

from urllib.parse import urlencode
from uuid import UUID

from django.urls import reverse
from django.utils.translation import pgettext

from apps.notifications.models import (
    InAppNotification,
    MembershipRequestRoleType,
    StudentOrganizationRequest,
)

from .constants import MEMBERSHIP_REQUEST_ROLE_LABELS


def _resolve_organization_id(organization, metadata: dict | None):
    """Resolve the tenant-scope organization id for a notification.

    Priority: explicit *organization* argument, then a legacy
    ``organization_id`` key inside *metadata*. Returns ``None`` for
    deliberately global notifications (platform/system, blog, etc.).
    """
    if organization is not None:
        org_id = getattr(organization, "pk", organization)
        return org_id or None
    if metadata:
        raw = metadata.get("organization_id")
        if raw not in (None, "", "None"):
            return raw
    return None


def _assert_owner(notification: InAppNotification, user) -> None:
    if notification.recipient_id != user.pk:
        raise PermissionError(pgettext("notifications.error", "You can only manage your own notifications."))


def _task_organization_id(task):
    org_id = getattr(task, "organization_id", None)
    if org_id:
        return org_id

    course = getattr(task, "course", None)
    if course is not None:
        return getattr(course, "organization_id", None)

    return None


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


def _display_name(user) -> str:
    return (user.get_full_name() or getattr(user, "username", "") or str(user)).strip()


def get_membership_request_role_label(role_type: str) -> str:
    return pgettext(
        "membership_request.role",
        MEMBERSHIP_REQUEST_ROLE_LABELS.get(role_type, "Member"),
    )


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


def org_scoped_link(link, organization) -> str:
    """Org-scoped hədəfi ``organizations:switch`` sıçrayışına sarı.

    Bildirişin keçidi yaradılan anda donur, amma hədəf view-lar obyekti
    SESSİYADAKI aktiv təşkilata görə scope-lanmış queryset-də axtarır
    (``tenant_scoped_exams`` → başqa org-da ``.none()``). Nəticədə çox-org
    istifadəçisi (və ya aktiv org-u sürüşmüş sessiya) tamamilə etibarlı
    keçiddə 404 alırdı.

    Üzvlük müraciəti bildirişləri bunu ARTIQ düzgün edir (yuxarıdakı
    ``_membership_request_management_link``) — burada həmin nümunə bütün
    bildirişlər üçün ümumiləşdirilir. ``organizations:switch`` özü üzvlüyü
    yoxlayır (üzv olmayan org seçiminə yönləndirilir, içəri buraxılmır) və
    ``next``-i same-origin kimi doğrulayır, yəni nə səlahiyyət artımı,
    nə də open-redirect yaranır.
    """

    slug = getattr(organization, "slug", None)
    if not link or not slug or not str(link).startswith("/"):
        return link
    if str(link).startswith("/organizations/switch/"):
        return link  # artıq sarınıb (üzvlük müraciətləri)
    return "{}?{}".format(
        reverse("organizations:switch", kwargs={"slug": slug}),
        urlencode({"next": link}),
    )


def _membership_request_notification_message(request_obj: StudentOrganizationRequest) -> str:
    profile = getattr(request_obj.user, "profile", None)
    role_label = get_membership_request_role_label(request_obj.role_type)
    full_name = (request_obj.user.get_full_name() or "").strip() or request_obj.user.username
    lines = [
        pgettext("notifications.event", "Organization: {organization}").format(
            organization=request_obj.organization.name
        ),
        pgettext("notifications.event", "Full name: {full_name}").format(full_name=full_name),
        pgettext("notifications.event", "Username: @{username}").format(username=request_obj.user.username),
        pgettext("notifications.event", "Email: {email}").format(email=request_obj.user.email),
        pgettext("notifications.event", "Request type: {role_label}").format(role_label=role_label),
    ]

    if profile is not None:
        department = (getattr(profile, "department", "") or "").strip()
        staff_position = (getattr(profile, "staff_position", "") or "").strip()
        student_specialization = (getattr(profile, "student_specialization", "") or "").strip()
        student_group_number = (getattr(profile, "student_group_number", "") or "").strip()

        if department:
            lines.append(
                pgettext("notifications.event", "Department / Faculty: {department}").format(department=department)
            )
        if staff_position:
            lines.append(pgettext("notifications.event", "Position: {position}").format(position=staff_position))
        if request_obj.role_type == MembershipRequestRoleType.STUDENT and student_specialization:
            lines.append(
                pgettext("notifications.event", "Specialization / Faculty: {specialization}").format(
                    specialization=student_specialization
                )
            )
        if request_obj.role_type == MembershipRequestRoleType.STUDENT and student_group_number:
            lines.append(
                pgettext("notifications.event", "Group / Class: {group_number}").format(
                    group_number=student_group_number
                )
            )

    if request_obj.message:
        lines.append(pgettext("notifications.event", "Request message: {message}").format(message=request_obj.message))

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
