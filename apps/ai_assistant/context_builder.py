"""
Build permission-filtered context for the AI assistant.

Collects only the data the authenticated user is allowed to access,
scoped to their current organization (tenant). The resulting context
string is injected into the Gemini system prompt so the AI can answer
accurately without hallucinating or leaking cross-tenant data.
"""

from __future__ import annotations

import logging

from django.urls import reverse
from django.utils.translation import get_language

from core.permissions import is_superadmin_user, request_has_permission

logger = logging.getLogger(__name__)


def build_user_context(request) -> str:
    """Assemble a concise context block describing what this user can access."""
    user = request.user
    organization = getattr(request, "organization", None)
    memberships = list(getattr(request, "org_memberships", []) or [])
    permissions = list(getattr(request, "org_permissions", []) or [])

    sections: list[str] = []

    # ── Basic identity ────────────────────────────────────────────────
    sections.append(_user_identity_section(user, organization, memberships))

    # ── Role-specific accessible pages ────────────────────────────────
    sections.append(
        _navigation_section(user, organization, memberships, permissions)
    )

    # ── Courses the user is enrolled in or owns ───────────────────────
    if organization:
        sections.append(_courses_section(user, organization, memberships, permissions))

    # ── Exam information (only what the user can see) ─────────────────
    if organization:
        sections.append(_exams_section(user, organization, memberships, permissions))

    # ── Platform language ─────────────────────────────────────────────
    lang = get_language() or "az"
    sections.append(f"[Platform Language]\nCurrent UI language: {lang}")

    return "\n\n".join(s for s in sections if s)


def _user_identity_section(user, organization, memberships) -> str:
    lines = [
        "[User Identity]",
        f"Name: {user.get_full_name() or user.username}",
        f"Username: {user.username}",
        f"Email: {user.email}",
    ]

    if is_superadmin_user(user):
        lines.append("Role: Platform Superadmin")
    elif organization:
        role_names = list({m.role.display_name for m in memberships if hasattr(m, "role") and m.role})
        lines.append(f"Organization: {organization.name}")
        if role_names:
            lines.append(f"Roles: {', '.join(role_names)}")
        else:
            owner_id = getattr(organization, "owner_id", None)
            if owner_id and owner_id == user.id:
                lines.append("Role: Organization Owner")
    else:
        lines.append("Role: Individual User (no organization selected)")

    return "\n".join(lines)


def _navigation_section(user, organization, memberships, permissions) -> str:
    """Build a list of pages the user can visit, with real URLs."""
    lines = ["[Accessible Pages]"]

    # Pages available to all authenticated users
    lines.append(f"- Profile settings: /accounts/profile/")
    lines.append(f"- Home page: /")

    if not organization:
        lines.append(f"- Organization selection: /organizations/select/")
        return "\n".join(lines)

    slug = organization.slug

    lines.append(f"- Organization dashboard: /organizations/{slug}/dashboard/")

    if request_has_permission_from_list(permissions, "course.view"):
        lines.append(f"- My courses: /courses/")

    if request_has_permission_from_list(permissions, "course.create"):
        lines.append(f"- Create course: /courses/create/")

    if request_has_permission_from_list(permissions, "exam.view"):
        lines.append(f"- Exams: /exams/")

    if request_has_permission_from_list(permissions, "exam.create"):
        lines.append(f"- Create exam: /exams/create/")

    if request_has_permission_from_list(permissions, "member.view"):
        lines.append(f"- Members: /organizations/{slug}/members/")

    if request_has_permission_from_list(permissions, "unit.view"):
        lines.append(f"- Organization structure: /organizations/{slug}/structure/")

    if request_has_permission_from_list(permissions, "role.view"):
        lines.append(f"- Roles: /organizations/{slug}/roles/")

    if request_has_permission_from_list(permissions, "grade.view"):
        lines.append(f"- Grades: (accessible from course dashboard)")

    # Student-specific pages
    is_student = _has_student_role(memberships)
    if is_student:
        lines.append(f"- Available exams: /exams/available/")
        lines.append(f"- Assigned exams: /exams/assigned/")
        lines.append(f"- Exam history: /exams/my-history/")

    # Teacher-specific pages
    is_teacher = _has_teacher_role(memberships)
    if is_teacher:
        lines.append(f"- Pending exam reviews: /exams/pending-work/")
        lines.append(f"- Exam groups: /exams/groups/")

    # Superadmin
    if is_superadmin_user(user):
        lines.append(f"- Admin panel: (superadmin access)")

    return "\n".join(lines)


def _courses_section(user, organization, memberships, permissions) -> str:
    """List courses the user participates in (max 20 for context size)."""
    from apps.courses.models import Course, CourseMembership

    lines = ["[My Courses]"]

    if request_has_permission_from_list(permissions, "course.view") or is_superadmin_user(user):
        # Teachers / admins: courses they own in this org
        owned = (
            Course.objects.filter(organization=organization, owner=user)
            .values_list("title", "slug", "status")[:20]
        )
        if owned:
            lines.append("Courses I teach:")
            for title, slug, status in owned:
                lines.append(f"  - {title} (/{slug}/) [{status}]")

    # Enrolled courses (as student)
    enrolled_course_ids = (
        CourseMembership.objects
        .filter(user=user, course__organization=organization, role="student")
        .values_list("course_id", flat=True)[:20]
    )
    if enrolled_course_ids:
        enrolled = (
            Course.objects.filter(id__in=enrolled_course_ids)
            .values_list("title", "slug", "status")
        )
        if enrolled:
            lines.append("Courses I'm enrolled in:")
            for title, slug, status in enrolled:
                lines.append(f"  - {title} (/{slug}/)")

    if len(lines) == 1:
        lines.append("No courses found.")

    return "\n".join(lines)


def _exams_section(user, organization, memberships, permissions) -> str:
    """Summarise the user's exam data (results for students, created exams for teachers)."""
    from apps.exams.domain.attempts import ExamAttempt
    from apps.exams.domain.exam_definition import Exam

    lines = ["[My Exams]"]

    is_teacher = _has_teacher_role(memberships) or request_has_permission_from_list(permissions, "exam.create")

    if is_teacher or is_superadmin_user(user):
        created = (
            Exam.objects.filter(organization=organization, author=user)
            .values_list("title", "slug")[:15]
        )
        if created:
            lines.append("Exams I created:")
            for title, slug in created:
                lines.append(f"  - {title} (/exams/{slug}/)")

    # Student exam results — tenant-scoped via the exam's organization FK
    attempts = (
        ExamAttempt.objects
        .filter(user=user, exam__organization=organization)
        .select_related("exam")
        .order_by("-created_at")[:10]
    )
    if attempts:
        lines.append("My recent exam results:")
        for a in attempts:
            score_display = f"{a.correct_count}/{a.correct_count + a.wrong_count}" if (a.correct_count + a.wrong_count) > 0 else "N/A"
            status = a.get_status_display() if hasattr(a, "get_status_display") else a.status
            lines.append(f"  - {a.exam.title}: {score_display} ({status})")

    if len(lines) == 1:
        lines.append("No exam data found.")

    return "\n".join(lines)


def _has_student_role(memberships) -> bool:
    for m in memberships:
        role = getattr(m, "role", None)
        if role and getattr(role, "name", "").lower() in ("student", "tələbə"):
            return True
    return False


def _has_teacher_role(memberships) -> bool:
    for m in memberships:
        role = getattr(m, "role", None)
        if role and getattr(role, "name", "").lower() in ("teacher", "müəllim", "instructor"):
            return True
    return False


def request_has_permission_from_list(permissions: list, permission: str) -> bool:
    """Check if a permission string is in the flat permissions list.

    Supports wildcard matching consistent with the RBAC permission system.
    """
    from apps.organizations.permissions import has_permission

    return has_permission(permissions, permission)
