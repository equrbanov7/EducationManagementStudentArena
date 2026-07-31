"""Platforma-səviyyə rol sabitləri və PURE rol helper-ləri (shared kernel).

M2 (2026-07-02): `ProfileRole` və aşağıdakı yan-təsirsiz helper-lər
apps/accounts-dan köçürülüb — accounts↔{exams,organizations,notifications,blog}
dövri asılılıqlarının kökü idi. accounts.models və accounts.policies geriyə-uyğun
re-export saxlayır (AGENTS §1); YENİ kod bu modulu import etməlidir.

QAYDA: bu fayl heç bir app modulunu import edə bilməz (core→apps qadağandır) —
yalnız sabitlər və istifadəçi obyektinin attribute-ları üzərində pure məntiq.
"""

from django.utils.translation import pgettext_lazy


class ProfileRole:
    """Role constants for UserProfile.role field."""

    SUPERADMIN = "superadmin"
    ORG_OWNER = "org_owner"
    ORG_ADMIN = "org_admin"
    MEMBER = "member"
    HR = "hr"
    # İmtahan mərkəzi rolları: rəhbər (zala nəzarətçi təyin edir + tam imtahan
    # idarəsi) və işçi (monitor / PIN / hesabat, amma nəzarətçi təyin ETMİR).
    # Köhnə tək "exam_center" rolu geriyə-uyğunluq üçün saxlanır (rəhbərə bərabər).
    EXAM_CENTER_HEAD = "exam_center_head"
    EXAM_CENTER_STAFF = "exam_center_staff"
    EXAM_CENTER = "exam_center"
    # İKT Rəhbəri — texniki/akademik super-operator: jurnal limitlərini (2 saat,
    # bitmiş semestr), kollokvium keçmiş-kilidini keçir, səhv qeydləri sənədli
    # düzəliş (correction + PDF) ilə düzəldir/silir. Bütün əməlləri audit olunur.
    IKT_REHBER = "ikt_rehber"
    TEACHER = "teacher"
    ASSISTANT_TEACHER = "assistant_teacher"
    LEAD_STUDENT = "lead_student"
    STUDENT = "student"

    # DİQQƏT: etiketlər `pgettext_lazy` ilə sarınıb — bu adlar profil başlığında,
    # üzv siyahılarında və rol seçicilərində göstərilir. Əvvəllər sabit
    # azərbaycanca sətir idi, yəni EN/RU/TR interfeysdə də «Müəllim»/«Tələbə»
    # çıxırdı (2026-07-31 auditi). `lazy` variantı vacibdir: modul import
    # vaxtında dil hələ seçilməyib.
    CHOICES = [
        (SUPERADMIN, pgettext_lazy("roles.display_name", "superadmin")),
        (ORG_OWNER, pgettext_lazy("roles.display_name", "org_owner")),
        (ORG_ADMIN, pgettext_lazy("roles.display_name", "org_admin")),
        (MEMBER, pgettext_lazy("roles.display_name", "member")),
        (HR, pgettext_lazy("roles.display_name", "hr")),
        (EXAM_CENTER_HEAD, pgettext_lazy("roles.display_name", "exam_center_head")),
        (EXAM_CENTER_STAFF, pgettext_lazy("roles.display_name", "exam_center_staff")),
        (EXAM_CENTER, pgettext_lazy("roles.display_name", "exam_center")),
        (IKT_REHBER, pgettext_lazy("roles.display_name", "ikt_rehber")),
        (TEACHER, pgettext_lazy("roles.display_name", "teacher")),
        (ASSISTANT_TEACHER, pgettext_lazy("roles.display_name", "assistant_teacher")),
        (LEAD_STUDENT, pgettext_lazy("roles.display_name", "lead_student")),
        (STUDENT, pgettext_lazy("roles.display_name", "student")),
    ]

    # Level mapping for hierarchy checks
    LEVELS = {
        SUPERADMIN: 100,
        ORG_OWNER: 90,
        ORG_ADMIN: 80,
        EXAM_CENTER_HEAD: 85,
        EXAM_CENTER: 85,
        IKT_REHBER: 88,
        MEMBER: 20,
        HR: 65,
        EXAM_CENTER_STAFF: 60,
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
        # Köhnə tək "exam_center" = rəhbərə bərabər (geriyə-uyğunluq).
        # Rəhbər/işçi AYRI saxlanır ki, nəzarətçi təyini yalnız rəhbərə açıq olsun
        # (is_exam_center hər üçünü ayrıca yoxlayır — bax accounts/roles.py).
        "exam_center": {"exam_center"},
        EXAM_CENTER_HEAD: {EXAM_CENTER_HEAD},
        EXAM_CENTER_STAFF: {EXAM_CENTER_STAFF},
        # İKT Rəhbəri həm imtahan mərkəzi (final/kollokvium/statistika), həm də
        # org-admin (level 88 ≥ 80 → aşağıdakı alias qaydası ilə org_admin) gücünə malikdir.
        IKT_REHBER: {IKT_REHBER, EXAM_CENTER_HEAD},
        "tutor": {"tutor"},
        # Proqram koordinatoru tyutor-ekvivalentdir (eyni akademik kurasiya işi).
        "program_coordinator": {"program_coordinator", "tutor"},
    }

    # Yüksək level-ə baxmayaraq avtomatik org_admin aliası ALMAMALI rollar.
    # Bunların səlahiyyəti rol permission-ları ilə müəyyən olunur (məs. imtahan
    # mərkəzi yalnız imtahan sahəsini idarə edir, üzv/struktur idarəetməsi yox).
    ADMIN_ALIAS_EXEMPT_ROLE_NAMES = {"exam_center", "exam_center_head", "exam_center_staff", "hr"}

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
