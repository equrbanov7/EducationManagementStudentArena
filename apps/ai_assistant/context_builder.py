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

from core.academic_rules import available_exams_page_enabled
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
        r"/exams/my-history/?$",
        {
            "name": "İmtahan Tarixçəsi / Exam History",
            "description": "Shows the user's past exam attempts and results.",
            "hints": "User can review scores, see correct/wrong answers, track progress over time, and retake exams if allowed.",
        },
    ),
    (
        r"/exams/groups/?$",
        {
            "name": "İmtahan Qrupları / Exam Groups (köhnə kohortlar)",
            "description": "Legacy exam cohorts; exams are now assigned to registry groups (Qruplar reyestri) in the exam wizard.",
            "hints": "Point users to the exam wizard's registry-group picker; this page only matters for organisations that still keep legacy cohorts.",
        },
    ),
    (
        r"/exams/create/?$",
        {
            "name": "İmtahan Yaratmaq / Create Exam",
            "description": "Redirects to the profile My exams section where the create exam modal is opened.",
            "hints": "Users create exams from My exams using the modal form for title, duration, question count, access, and other settings.",
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
        r"/courses/create_course/?$",
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


def mask_email(email: str) -> str:
    """E-poçtu `***@domain` şəklinə salır — provayderə yalnız domen gedir.

    2026-09-14 (audit F-08, §27 «AI PII/retention»): əvvəl hər sorğuda tam
    e-poçt Gemini-yə göndərilirdi. Persona üçün domen (universitet/şəxsi) kifayət
    edir; lokal hissə üçüncü tərəfə lazım deyil.
    """
    email = (email or "").strip()
    if "@" not in email:
        return ""
    domain = email.rsplit("@", 1)[1]
    return f"***@{domain}" if domain else ""


#: Köməkçi rejimi üçün rol ailələri (sahib 2026-10-01: «hər kəs öz rolu çərçivəsində kömək alsın»).
#: ``apps/accounts/network_zone.py`` ilə eyni adlar (modul sərhədi səbəbindən burada təkrarlanır).
_STUDENT_ROLE_NAMES = frozenset({"student", "lead_student", "alumni"})
_TEACHER_ROLE_NAMES = frozenset(
    {"teacher", "assistant_teacher", "instructor", "professor", "associate_professor", "assistant", "lab_assistant"}
)
_NEUTRAL_ROLE_NAMES = frozenset({"member"})


def assistant_modes(user, memberships) -> list[str]:
    """``["student"]``, ``["teacher"]``, ``["staff", "teacher"]`` … — köməkçinin davranış rejimləri."""
    if is_superadmin_user(user):
        return ["staff"]
    names = {m.role.name for m in memberships if getattr(m, "role", None) is not None} - _NEUTRAL_ROLE_NAMES
    modes = []
    if names - _STUDENT_ROLE_NAMES - _TEACHER_ROLE_NAMES:
        modes.append("staff")
    if names & _TEACHER_ROLE_NAMES:
        modes.append("teacher")
    if names & _STUDENT_ROLE_NAMES and not modes:
        modes.append("student")
    return modes or ["general"]


def _user_identity_section(user, organization, memberships) -> str:
    lines = [
        "[User Identity]",
        f"Name: {user.get_full_name() or user.username}",
        f"Username: {user.username}",
    ]
    masked_email = mask_email(getattr(user, "email", ""))
    if masked_email:
        lines.append(f"Email: {masked_email}")

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

    lines.append(f"Assistant mode: {', '.join(assistant_modes(user, memberships))}")
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

    # Sahib 2026-10-11: köhnə müstəqil təşkilat səhifələri (`/organizations/<slug>/…`)
    # silindi — yalnız kabinetə yönləndirir; köməkçi kanonik kabinet bölmələrini təklif edir.
    lines.append("- Organization panel: /accounts/profile/?section=org-overview")

    # URL auditi A8/A12/§4 (2026-10-10): köhnə müstəqil siyahılar (`/courses/my-courses/`,
    # `/courses/my-enrolled/`, `/exams/assigned/`, `/exams/pending-work/`) silindi və ya
    # yönləndirir — köməkçi kanonik kabinet bölmələrini təklif edir.
    if request_has_permission_from_list(permissions, "course.view"):
        lines.append("- My courses: /accounts/profile/?section=my-courses")

    if request_has_permission_from_list(permissions, "course.create"):
        lines.append("- Create course: /courses/create_course/")

    if request_has_permission_from_list(permissions, "exam.view"):
        lines.append("- Exams: /exams/")

    if request_has_permission_from_list(permissions, "exam.create"):
        lines.append("- Create exam: /accounts/profile/?section=my-exams")

    if request_has_permission_from_list(permissions, "member.view"):
        # Rol auditi 2026-10-13 B10: `member.view` əhatəsi AKADEMİK QRUP olan aktor (baş tələbə) «Üzvlər»
        # bölməsini aça bilmir (rol bayrağı ilə qapalıdır) — ona kabinetin «Qrupum» bölməsi təklif olunur.
        group_scoped, other_scoped = _member_view_scopes(memberships)
        if group_scoped:
            lines.append("- My group (classmates + attendance, read-only): /accounts/profile/?section=my-group")
        if other_scoped or not group_scoped:
            lines.append("- Members: /accounts/profile/?section=org-members")

    if request_has_permission_from_list(permissions, "unit.view"):
        lines.append("- Organization structure: /accounts/profile/?section=org-structure-tree")

    if request_has_permission_from_list(permissions, "role.view"):
        lines.append("- Roles: /accounts/profile/?section=org-roles")

    if request_has_permission_from_list(permissions, "grade.view"):
        lines.append("- Grades: (accessible from course dashboard)")

    # Student-specific pages
    is_student = _has_student_role(memberships)
    if is_student:
        # Sahib 2026-10-10: «Mövcud imtahanlar» bağlıdırsa köməkçi onu təklif etməsin.
        if available_exams_page_enabled():
            lines.append("- Available exams: /exams/available/")
        lines.append("- Assigned exams: /accounts/profile/?section=assigned-exams")
        lines.append("- Assigned courses: /accounts/profile/?section=assigned-courses")
        lines.append("- Exam history: /exams/my-history/")

    # Teacher-specific pages
    is_teacher = _has_teacher_role(memberships)
    if is_teacher:
        lines.append("- Pending reviews: /accounts/profile/?section=pending-review")
        # 2026-09-14: imtahanlar reyestr qruplarına təyin olunur; köhnə kohort səhifəsi
        # yalnız kohortu olan tenantlar üçündür — köməkçi reyestrə yönləndirir.
        lines.append("- Groups registry (exam assignment via wizard): /accounts/profile/?section=groups-registry")

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
        # NOTE: values_list() must match the loop unpacking below. Previously this
        # selected ("title", "slug", "status") but the loop unpacked only two
        # values, raising ValueError for every user with an enrolled course.
        enrolled = Course.objects.filter(id__in=enrolled_course_ids).values_list("title", "slug")
        if enrolled:
            lines.append("Courses I'm enrolled in:")
            for title, slug in enrolled:
                lines.append(f"  - {title} (/{slug}/)")

    if len(lines) == 1:
        lines.append("No courses found.")

    return "\n".join(lines)


def _exams_section(user, organization, memberships, permissions) -> str:
    """Summarise the user's exam data (results for students, created exams for teachers)."""
    from apps.exams.models import Exam, ExamAttempt
    from apps.exams.public import ATTEMPT_FINISHED_STATUSES

    lines = ["[My Exams]"]

    is_teacher = _has_teacher_role(memberships) or request_has_permission_from_list(permissions, "exam.create")

    if is_teacher or is_superadmin_user(user):
        created = Exam.objects.filter(organization=organization, author=user).values_list("title", "slug")[:15]
        if created:
            lines.append("Exams I created:")
            for title, slug in created:
                lines.append(f"  - {title} (/exams/{slug}/)")

    # Student exam results — tenant-scoped via the exam's organization FK.
    # Təhlükəsizlik auditi 2026-10-05: YALNIZ bitmiş cəhdlər və nəticəsi gizlədilməmiş
    # imtahanlar — açıq cəhdin balı (``save_draft`` onu yenidən hesablayır) AI-dan
    # soruşulub imtahan ZAMANI doğru cavab oracle-ı kimi istifadə olunurdu.
    attempts = (
        ExamAttempt.objects.filter(
            user=user,
            exam__organization=organization,
            status__in=ATTEMPT_FINISHED_STATUSES,
            exam__results_hidden_from_students=False,
        )
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


def _member_view_scopes(memberships) -> tuple[bool, bool]:
    """``(qrup əhatəli, başqa əhatəli)`` — `member.view` daşıyan üzvlüklərin əhatə növü (B10, 2026-10-13).

    Kabinetin «Qrupum» qapısı (``accounts/views/_helpers/rbac_my_group.py``) ilə eyni qayda: UNIT rolu +
    ``scope_unit`` akademik qrupdur. Modul sərhədi səbəbindən burada təkrarlanır; üzvlük sətirləri
    middleware-dən ``scope_unit`` yüklü gəlir (əlavə sorğu yoxdur).
    """
    from core.constants import OrgUnitType, RoleScopeType
    from core.permissions import has_permission

    group_scoped = other_scoped = False
    for membership in memberships:
        role = getattr(membership, "role", None)
        if role is None or not has_permission(list(getattr(role, "permissions", None) or []), "member.view"):
            continue
        unit = getattr(membership, "scope_unit", None)
        if getattr(role, "scope_type", None) == RoleScopeType.UNIT and getattr(unit, "unit_type", None) == (
            OrgUnitType.GROUP
        ):
            group_scoped = True
        else:
            other_scoped = True
    return group_scoped, other_scoped


def request_has_permission_from_list(permissions: list, permission: str) -> bool:
    """Check if a permission string is in the flat permissions list.

    Supports wildcard matching consistent with the RBAC permission system.
    """
    from core.permissions import has_permission

    return has_permission(permissions, permission)
