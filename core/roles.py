"""Platforma-səviyyə rol sabitləri və PURE rol helper-ləri (shared kernel).

M2 (2026-07-02): `ProfileRole` və aşağıdakı yan-təsirsiz helper-lər
apps/accounts-dan köçürülüb — accounts↔{exams,organizations,notifications,blog}
dövri asılılıqlarının kökü idi. accounts.models və accounts.policies geriyə-uyğun
re-export saxlayır (AGENTS §1); YENİ kod bu modulu import etməlidir.

QAYDA: bu fayl heç bir app modulunu import edə bilməz (core→apps qadağandır) —
yalnız sabitlər və istifadəçi obyektinin attribute-ları üzərində pure məntiq.
"""


class ProfileRole:
    """Role constants for UserProfile.role field."""

    SUPERADMIN = "superadmin"
    ORG_OWNER = "org_owner"
    ORG_ADMIN = "org_admin"
    MEMBER = "member"
    HR = "hr"
    TEACHER = "teacher"
    ASSISTANT_TEACHER = "assistant_teacher"
    LEAD_STUDENT = "lead_student"
    STUDENT = "student"

    CHOICES = [
        (SUPERADMIN, "Super Admin"),
        (ORG_OWNER, "Təşkilat Sahibi"),
        (ORG_ADMIN, "Təşkilat Admini"),
        (MEMBER, "Üzv"),
        (HR, "HR"),
        (TEACHER, "Müəllim"),
        (ASSISTANT_TEACHER, "Müəllim Köməkçisi"),
        (LEAD_STUDENT, "Baş Tələbə"),
        (STUDENT, "Tələbə"),
    ]

    # Level mapping for hierarchy checks
    LEVELS = {
        SUPERADMIN: 100,
        ORG_OWNER: 90,
        ORG_ADMIN: 80,
        MEMBER: 20,
        HR: 65,
        TEACHER: 60,
        ASSISTANT_TEACHER: 55,
        LEAD_STUDENT: 30,
        STUDENT: 10,
    }

    ROLE_NAME_NORMALIZATION = {
        "deputy_director": "vice_director",
        "chair_head": "department_head",
        "section_head": "department_head",
    }

    MEMBERSHIP_ROLE_ALIASES = {
        MEMBER: {MEMBER},
        STUDENT: {STUDENT},
        LEAD_STUDENT: {LEAD_STUDENT, STUDENT},
        HR: {HR},
        TEACHER: {TEACHER},
        "instructor": {TEACHER, "instructor"},
        "professor": {TEACHER, "professor"},
        "associate_professor": {TEACHER, "associate_professor"},
        ASSISTANT_TEACHER: {ASSISTANT_TEACHER},
        "assistant": {ASSISTANT_TEACHER, "assistant"},
        "lab_assistant": {ASSISTANT_TEACHER, "lab_assistant"},
        "exam_center": {"exam_center"},
        "tutor": {"tutor"},
    }

    # Yüksək level-ə baxmayaraq avtomatik org_admin aliası ALMAMALI rollar.
    # Bunların səlahiyyəti rol permission-ları ilə müəyyən olunur (məs. imtahan
    # mərkəzi yalnız imtahan sahəsini idarə edir, üzv/struktur idarəetməsi yox).
    ADMIN_ALIAS_EXEMPT_ROLE_NAMES = {"exam_center", "hr"}

    ADMIN_EQUIVALENT_ROLE_NAMES = {
        ORG_ADMIN,
        ORG_OWNER,
        "rector",
        "vice_rector",
        "dean",
        "vice_dean",
        "department_head",
        "director",
        "vice_director",
        "manager",
        "senior_instructor",
    }

    @classmethod
    def normalize_membership_role_name(cls, role_name):
        normalized = (role_name or "").strip().lower()
        return cls.ROLE_NAME_NORMALIZATION.get(normalized, normalized)

    @classmethod
    def aliases_for_membership_role(cls, role_name, *, level=0, is_org_owner=False):
        normalized = cls.normalize_membership_role_name(role_name)
        aliases = set()

        if normalized:
            aliases.add(normalized)
            aliases.update(cls.MEMBERSHIP_ROLE_ALIASES.get(normalized, set()))

        if is_org_owner:
            aliases.update({cls.ORG_OWNER, cls.ORG_ADMIN})

        if normalized not in cls.ADMIN_ALIAS_EXEMPT_ROLE_NAMES and (
            normalized in cls.ADMIN_EQUIVALENT_ROLE_NAMES or level >= cls.LEVELS.get(cls.ORG_ADMIN, 80)
        ):
            aliases.add(cls.ORG_ADMIN)

        return aliases


def is_superadmin_user(user):
    """Return whether the user has superadmin privileges."""
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and (user.is_superuser or getattr(user, "is_superadmin", False))
    )


def get_user_role_level(user):
    """Return the user's effective role level."""
    if not user or not getattr(user, "is_authenticated", False):
        return 0
    if is_superadmin_user(user):
        return 999
    if hasattr(user, "_highest_role_level"):
        return int(user._highest_role_level())

    return 0


def user_has_any_role(user, role_names):
    """Return whether the user has any role from the provided set."""
    if not user or not getattr(user, "is_authenticated", False):
        return False

    normalized = set(role_names or [])
    if not normalized:
        return False
    if hasattr(user, "has_role"):
        return any(user.has_role(role_name) for role_name in normalized)

    return False


def get_profile_role_label(role):
    """Return the display label for a profile role."""
    return dict(ProfileRole.CHOICES).get(role, role)


def map_signup_role_to_profile_role(initial_role):
    """Normalize signup roles to profile roles."""
    role_mapping = {
        ProfileRole.STUDENT: ProfileRole.STUDENT,
        ProfileRole.LEAD_STUDENT: ProfileRole.LEAD_STUDENT,
        ProfileRole.TEACHER: ProfileRole.TEACHER,
        ProfileRole.ASSISTANT_TEACHER: ProfileRole.ASSISTANT_TEACHER,
        ProfileRole.HR: ProfileRole.HR,
        ProfileRole.MEMBER: ProfileRole.MEMBER,
        ProfileRole.ORG_ADMIN: ProfileRole.ORG_ADMIN,
        ProfileRole.ORG_OWNER: ProfileRole.ORG_OWNER,
    }
    return role_mapping.get(initial_role, ProfileRole.MEMBER)


def map_org_role_to_profile_role(role):
    """Map an organization membership role to a profile role."""
    role_name = ProfileRole.normalize_membership_role_name(getattr(role, "name", ""))
    if role_name == ProfileRole.MEMBER:
        return ProfileRole.MEMBER
    if role_name == ProfileRole.LEAD_STUDENT:
        return ProfileRole.LEAD_STUDENT
    if role_name == ProfileRole.STUDENT:
        return ProfileRole.STUDENT
    if role_name == ProfileRole.HR:
        return ProfileRole.HR
    if role_name in {ProfileRole.ASSISTANT_TEACHER, "assistant", "lab_assistant"}:
        return ProfileRole.ASSISTANT_TEACHER
    if role_name in {ProfileRole.TEACHER, "instructor", "professor", "associate_professor"}:
        return ProfileRole.TEACHER
    if getattr(role, "level", 0) >= ProfileRole.LEVELS.get(ProfileRole.ORG_ADMIN, 80):
        return ProfileRole.ORG_ADMIN
    return ProfileRole.MEMBER
