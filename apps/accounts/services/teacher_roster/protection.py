"""Hesab indeksinin DB-dən qurulması və BLOKLAMA QORUMASI qaydaları (sahib 2026-10-11).

Sahib: siyahıda olmayan MÜƏLLİM hesabları dayandırılır. HEÇ VAXT bloklanmır:

* superuser / ``is_staff`` hesablar, təşkilatın sahibi, ``--protect`` ilə verilən hesablar;
* İSTƏNİLƏN təşkilatda müəllimlikdən başqa inzibati/heyət rolu daşıyanlar (RİM, İKT, dekan, kafedra müdiri,
  rektor, HR, imtahan mərkəzi, tədris şöbəsi, tyutor …) — rol adı ``TEACHING_ROLE_NAMES``/tələbə rolları
  xaricindədirsə qorunur; ``member`` rolu yalnız vəzifə yazılıbsa (heyət) qoruyur;
* bölmə rəhbəri (``OrgUnit.head``), profil rolu inzibati olanlar;
* tələbələr (tələbə/məzun rolu və ya profil rolu) — onlar müəllim kimi heç vaxt namizəd deyil;
* bu tədris ilində DƏRS YÜKÜ bölgüsü və ya cari semestrdə aktiv JURNALI olanlar (sahib 2026-10-25: «aktiv
  olmayanları blokla» — dərs deyən müəllim siyahıda olmasa da bloklanmır, hesabatda ayrıca göstərilir).
"""

from __future__ import annotations

from apps.organizations.models import Membership, OrgUnit

from ..people.constants import TEACHER_ROLE_NAMES
from .matching import Account

TEACHING_ROLE_NAMES = frozenset(TEACHER_ROLE_NAMES) | {"professor", "associate_professor"}
STUDENT_ROLE_NAMES = frozenset({"student", "lead_student", "alumni", "parent", "applicant"})
STUDENT_PROFILE_ROLES = frozenset({"student", "lead_student"})
ADMIN_PROFILE_ROLES = frozenset(
    {
        "superadmin",
        "org_owner",
        "org_admin",
        "hr",
        "exam_center",
        "exam_center_head",
        "exam_center_staff",
        "ikt_rehber",
        "rim_staff",
    }
)
#: Profildəki ``staff_position`` bu sözlərdən biridirsə inzibati vəzifə sayılmır.
_TEACHING_POSITION_WORDS = ("muellim", "dosent", "professor", "assistent", "laborant")

PROTECT_SUPERUSER = "superuser"
PROTECT_OWNER = "org_owner"
PROTECT_EXPLICIT = "explicit"
PROTECT_STAFF_ROLE = "staff_role"
PROTECT_PROFILE_ROLE = "profile_role"
PROTECT_UNIT_HEAD = "unit_head"
PROTECT_STAFF_POSITION = "staff_position"
PROTECT_STUDENT = "student"
PROTECT_TEACHING_NOW = "teaching_now"


def is_student(account: Account) -> bool:
    """Müəllim sətrinə bağlana bilməyən hesab: müəllim rolu YOXDUR, tələbə/məzun rolu və ya profili VAR."""
    roles = account.roles | account.foreign_roles
    if roles & TEACHING_ROLE_NAMES:
        return False
    return account.profile_role in STUDENT_PROFILE_ROLES or bool(roles & STUDENT_ROLE_NAMES)


def is_teaching(account: Account) -> bool:
    return bool(account.roles & TEACHING_ROLE_NAMES)


def _position_is_staff(text: str) -> bool:
    from .parsing import fold

    folded = fold(text)
    return bool(folded) and not any(word in folded for word in _TEACHING_POSITION_WORDS)


def protection_reasons(account: Account, *, owner_ids=(), explicit_ids=(), teaching_ids=()) -> list:
    """Hesabın bloklanmasına MANE olan səbəblər (boş siyahı = qoruma yoxdur)."""
    reasons = []
    if account.user_id in teaching_ids:
        reasons.append(PROTECT_TEACHING_NOW)
    if account.is_superuser or account.is_staff:
        reasons.append(PROTECT_SUPERUSER)
    if account.user_id in owner_ids:
        reasons.append(PROTECT_OWNER)
    if account.user_id in explicit_ids:
        reasons.append(PROTECT_EXPLICIT)
    roles = account.roles | account.foreign_roles
    staff_roles = sorted(roles - TEACHING_ROLE_NAMES - STUDENT_ROLE_NAMES - {"member"})
    if staff_roles:
        reasons.append(f"{PROTECT_STAFF_ROLE}:{','.join(staff_roles)}")
    if "member" in roles and (any(account.membership_titles) or _position_is_staff(account.staff_position)):
        reasons.append(f"{PROTECT_STAFF_ROLE}:member")
    if account.profile_role in ADMIN_PROFILE_ROLES:
        reasons.append(f"{PROTECT_PROFILE_ROLE}:{account.profile_role}")
    if account.is_unit_head:
        reasons.append(PROTECT_UNIT_HEAD)
    if _position_is_staff(account.staff_position) and not any(r.startswith(PROTECT_STAFF_ROLE) for r in reasons):
        reasons.append(PROTECT_STAFF_POSITION)
    if is_student(account) or roles & STUDENT_ROLE_NAMES:
        reasons.append(PROTECT_STUDENT)
    return reasons


def _chair_resolver(organization):
    from apps.organizations.public import kafedra_unit_types

    chair_types = kafedra_unit_types(organization)
    units = {
        row[0]: row
        for row in OrgUnit.objects.filter(organization=organization).values_list("id", "unit_type", "parent_id")
    }

    def chair_of(unit_id):
        seen = set()
        while unit_id is not None and unit_id not in seen:
            seen.add(unit_id)
            row = units.get(unit_id)
            if row is None:
                return None
            if row[1] in chair_types:
                return unit_id
            unit_id = row[2]
        return None

    return chair_of


def load_accounts(organization) -> list:
    """Təşkilatda aktiv üzvlüyü olan bütün hesablar → ``[Account]`` (RLS bypass altında çağırılır)."""
    from django.contrib.auth import get_user_model

    chair_of = _chair_resolver(organization)
    memberships = Membership.objects.filter(
        organization=organization, is_active=True, role__is_active=True
    ).values_list("user_id", "role__name", "scope_unit_id", "title")
    by_user: dict = {}
    for user_id, role_name, unit_id, title in memberships:
        bucket = by_user.setdefault(user_id, {"roles": set(), "chairs": set(), "titles": set()})
        bucket["roles"].add(role_name)
        chair = chair_of(unit_id)
        if chair is not None:
            bucket["chairs"].add(chair)
        if (title or "").strip():
            bucket["titles"].add(title.strip())
    foreign: dict = {}
    for user_id, role_name in (
        Membership.objects.filter(user_id__in=list(by_user), is_active=True, role__is_active=True)
        .exclude(organization=organization)
        .values_list("user_id", "role__name")
    ):
        foreign.setdefault(user_id, set()).add(role_name)
    heads = set(OrgUnit.objects.filter(head__isnull=False, is_active=True).values_list("head_id", flat=True))

    accounts = []
    fields = (
        "id",
        "username",
        "first_name",
        "last_name",
        "is_active",
        "is_superuser",
        "is_staff",
        "profile__patronymic",
        "profile__role",
        "profile__staff_position",
        "profile__academic_title",
        "profile__academic_degree",
        "profile__is_deleted",
    )
    for row in get_user_model().objects.filter(pk__in=list(by_user)).values_list(*fields):
        user_id, username, first, last, active, superuser, staff, patronymic, role, position, title, degree, deleted = (
            row
        )
        first_tokens = (first or "").split()
        if len(first_tokens) == 2 and not (patronymic or "").strip():
            first, patronymic = first_tokens[0], first_tokens[1]
        bucket = by_user[user_id]
        accounts.append(
            Account(
                user_id=user_id,
                username=username,
                last=last or "",
                first=first or "",
                patronymic=patronymic or "",
                is_active=bool(active),
                is_superuser=bool(superuser),
                is_staff=bool(staff),
                is_deleted=bool(deleted),
                profile_role=role or "",
                staff_position=position or "",
                title=title or "",
                degree=degree or "",
                roles=bucket["roles"],
                foreign_roles=foreign.get(user_id, set()),
                membership_titles=bucket["titles"],
                chairs=bucket["chairs"],
                is_unit_head=user_id in heads,
            )
        )
    return accounts


def teaching_now_ids(organization, academic_year: str) -> set:
    """Tədris ilində dərs yükü bölgüsü və ya cari semestrdə aktiv jurnalı olan istifadəçilər (bloklanmır)."""
    from ..staff_placement.facts import current_period_ids, teaching_user_ids

    return teaching_user_ids(organization, academic_year, current_period_ids(organization))


__all__ = [
    "ADMIN_PROFILE_ROLES",
    "PROTECT_TEACHING_NOW",
    "STUDENT_ROLE_NAMES",
    "TEACHING_ROLE_NAMES",
    "is_student",
    "is_teaching",
    "load_accounts",
    "protection_reasons",
    "teaching_now_ids",
]
