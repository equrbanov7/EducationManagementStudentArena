"""
Build permission-filtered context for the AI assistant.

Collects only the data the authenticated user is allowed to access,
scoped to their current organization (tenant). The resulting context
string is injected into the Gemini system prompt so the AI can answer
accurately without hallucinating or leaking cross-tenant data.
"""

from __future__ import annotations

import logging

from django.utils.translation import get_language

from core.permissions import is_superadmin_user

logger = logging.getLogger(__name__)


def build_user_context(request, current_page: str = "") -> str:
    """Assemble a concise context block describing what this user can access."""
    user = request.user
    organization = getattr(request, "organization", None)
    memberships = list(getattr(request, "org_memberships", []) or [])
    permissions = list(getattr(request, "org_permissions", []) or [])

    sections: list[str] = []

    # ── Basic identity ────────────────────────────────────────────────
    sections.append(_user_identity_section(user, organization, memberships))

    # ── Current page context ──────────────────────────────────────────
    if current_page:
        page_section = _current_page_section(current_page, organization, memberships, permissions)
        if page_section:
            sections.append(page_section)

    # ── Role-specific accessible pages ────────────────────────────────
    sections.append(_navigation_section(user, organization, memberships, permissions))

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


_PAGE_CONTEXT_MAP = [
    (
        r"^/$",
        {
            "name": "Ana Səhifə / Home",
            "description": "The main landing page of the platform.",
            "hints": "From here users can navigate to their organization dashboard, courses, or exams.",
        },
    ),
    (
        r"/dashboard/?$",
        {
            "name": "Təşkilat İdarə Paneli / Organization Dashboard",
            "description": "Overview of the organization with key metrics and quick links.",
            "hints": "Shows organization statistics, recent activity, and quick navigation to courses, exams, members, and structure.",
        },
    ),
    (
        r"/exams/available/?$",
        {
            "name": "Mövcud İmtahanlar / Available Exams",
            "description": "Lists all exams the user is eligible to participate in.",
            "hints": "User can browse available exams, see exam details (duration, question count), and start an exam. Exams may be filtered by course or category.",
        },
    ),
    (
        r"/exams/assigned/?$",
        {
            "name": "Təyin Edilmiş İmtahanlar / Assigned Exams",
            "description": "Shows exams specifically assigned to this user by a teacher or admin.",
            "hints": "These are mandatory exams the user must complete. Shows deadline, status, and allows starting the exam.",
        },
    ),
    (
        r"/exams/my-history/?$",
        {
            "name": "İmtahan Tarixçəsi / Exam History",
            "description": "Shows the user's past exam attempts and results.",
            "hints": "User can review scores, see correct/wrong answers, track progress over time, and retake exams if allowed.",
        },
    ),
    (
        r"/exams/pending-work/?$",
        {
            "name": "Gözləyən Yoxlamalar / Pending Reviews",
            "description": "Exams waiting for teacher review and grading.",
            "hints": "Teachers can review submitted exam attempts, grade open-ended questions, and provide feedback.",
        },
    ),
    (
        r"/exams/groups/?$",
        {
            "name": "İmtahan Qrupları / Exam Groups",
            "description": "Manage exam groups for organizing and assigning exams.",
            "hints": "Teachers can create exam groups, add students, assign exams to groups, and track group performance.",
        },
    ),
    (
        r"/exams/create/?$",
        {
            "name": "İmtahan Yaratmaq / Create Exam",
            "description": "Form to create a new exam.",
            "hints": "User can set exam title, duration, question count, passing score, add questions, and configure exam settings.",
        },
    ),
    (
        r"/exams/[^/]+/?$",
        {
            "name": "İmtahan Detalları / Exam Details",
            "description": "Detailed view of a specific exam.",
            "hints": "Shows exam info, questions, settings. Teachers can edit the exam. Students can start or view results.",
        },
    ),
    (
        r"/courses/?$",
        {
            "name": "Kurslarım / My Courses",
            "description": "Lists courses the user teaches or is enrolled in.",
            "hints": "Users can view course materials, access course exams, see enrolled students (teachers), and track progress.",
        },
    ),
    (
        r"/courses/create/?$",
        {
            "name": "Kurs Yaratmaq / Create Course",
            "description": "Form to create a new course.",
            "hints": "User can set course title, description, add materials, and configure course settings.",
        },
    ),
    (
        r"/members/?$",
        {
            "name": "Üzvlər / Members",
            "description": "Lists all members of the organization.",
            "hints": "Admins can view members, manage roles, invite new members, or remove members.",
        },
    ),
    (
        r"/structure/?$",
        {
            "name": "Təşkilat Strukturu / Organization Structure",
            "description": "View and manage the organizational unit hierarchy.",
            "hints": "Admins can create/edit departments, teams, and organizational units. Assign members to units.",
        },
    ),
    (
        r"/roles/?$",
        {
            "name": "Rollar / Roles",
            "description": "Manage roles and their permissions.",
            "hints": "Admins can create custom roles, assign permissions, and manage role assignments.",
        },
    ),
    (
        r"/accounts/profile/?$",
        {
            "name": "Profil Ayarları / Profile Settings",
            "description": "User's personal profile settings.",
            "hints": "User can update name, email, password, language preference, and notification settings.",
        },
    ),
]


def _current_page_section(current_page: str, organization, memberships, permissions) -> str:
    """Describe the page the user is currently viewing and what they can do there."""
    import re
    from urllib.parse import urlparse

    path = urlparse(current_page).path if "://" in current_page else current_page
    if not path:
        return ""

    lines = [f"[Current Page]\nThe user is currently on: {path}"]

    for pattern, info in _PAGE_CONTEXT_MAP:
        if re.search(pattern, path):
            lines.append(f"Page: {info['name']}")
            lines.append(f"Description: {info['description']}")
            lines.append(f"What the user can do here: {info['hints']}")
            break
    else:
        lines.append("This is a platform page. Help the user based on the URL path and their permissions.")

    return "\n".join(lines)


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
    lines.append("- Profile settings: /accounts/profile/")
    lines.append("- Home page: /")

    if not organization:
        lines.append("- Organization selection: /organizations/select/")
        return "\n".join(lines)

    slug = organization.slug

    lines.append(f"- Organization dashboard: /organizations/{slug}/dashboard/")

    if request_has_permission_from_list(permissions, "course.view"):
        lines.append("- My courses: /courses/")

    if request_has_permission_from_list(permissions, "course.create"):
        lines.append("- Create course: /courses/create/")

    if request_has_permission_from_list(permissions, "exam.view"):
        lines.append("- Exams: /exams/")

    if request_has_permission_from_list(permissions, "exam.create"):
        lines.append("- Create exam: /exams/create/")

    if request_has_permission_from_list(permissions, "member.view"):
        lines.append(f"- Members: /organizations/{slug}/members/")

    if request_has_permission_from_list(permissions, "unit.view"):
        lines.append(f"- Organization structure: /organizations/{slug}/structure/")

    if request_has_permission_from_list(permissions, "role.view"):
        lines.append(f"- Roles: /organizations/{slug}/roles/")

    if request_has_permission_from_list(permissions, "grade.view"):
        lines.append("- Grades: (accessible from course dashboard)")

    # Student-specific pages
    is_student = _has_student_role(memberships)
    if is_student:
        lines.append("- Available exams: /exams/available/")
        lines.append("- Assigned exams: /exams/assigned/")
        lines.append("- Exam history: /exams/my-history/")

    # Teacher-specific pages
    is_teacher = _has_teacher_role(memberships)
    if is_teacher:
        lines.append("- Pending exam reviews: /exams/pending-work/")
        lines.append("- Exam groups: /exams/groups/")

    # Superadmin
    if is_superadmin_user(user):
        lines.append("- Admin panel: (superadmin access)")

    return "\n".join(lines)


def _courses_section(user, organization, memberships, permissions) -> str:
    """List courses the user participates in (max 20 for context size)."""
    from apps.courses.models import Course, CourseMembership

    lines = ["[My Courses]"]

    if request_has_permission_from_list(permissions, "course.view") or is_superadmin_user(user):
        # Teachers / admins: courses they own in this org
        owned = Course.objects.filter(organization=organization, owner=user).values_list("title", "slug", "status")[:20]
        if owned:
            lines.append("Courses I teach:")
            for title, slug, status in owned:
                lines.append(f"  - {title} (/{slug}/) [{status}]")

    # Enrolled courses (as student)
    enrolled_course_ids = CourseMembership.objects.filter(
        user=user, course__organization=organization, role="student"
    ).values_list("course_id", flat=True)[:20]
    if enrolled_course_ids:
        enrolled = Course.objects.filter(id__in=enrolled_course_ids).values_list("title", "slug", "status")
        if enrolled:
            lines.append("Courses I'm enrolled in:")
            for title, slug in enrolled:
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
        created = Exam.objects.filter(organization=organization, author=user).values_list("title", "slug")[:15]
        if created:
            lines.append("Exams I created:")
            for title, slug in created:
                lines.append(f"  - {title} (/exams/{slug}/)")

    # Student exam results — tenant-scoped via the exam's organization FK
    attempts = (
        ExamAttempt.objects.filter(user=user, exam__organization=organization)
        .select_related("exam")
        .order_by("-started_at")[:10]
    )
    if attempts:
        lines.append("My recent exam results:")
        for a in attempts:
            score_display = (
                f"{a.correct_count}/{a.correct_count + a.wrong_count}"
                if (a.correct_count + a.wrong_count) > 0
                else "N/A"
            )
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
