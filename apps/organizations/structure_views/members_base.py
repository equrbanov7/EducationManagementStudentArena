"""«Struktur üzvləri» bölməsi — sabitlər, etiketlər, giriş/əhatə və vahid xəritəsi.

``members.py``-dan ayrılıb (modul-ölçü qapısı, 2026-09-21): rol dəstləri,
``head_label`` / ``role_text``, ``MembersAccess`` + ``resolve_members_access``
(fail-closed əhatə) və ``UnitIndex`` (TƏK sorğu). Bölmə qurucusu
``members.py``-da qalır və bu adları yenidən ixrac edir.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import pgettext

from core.constants import OrgUnitType
from core.staff_position import visible_role_label

from ..models import Membership, OrgUnit
from ..scoping import get_permission_scope, scope_memberships_by_unit
from ..services import get_user_org_role_level
from ..views import _can_manage_organization, _has_org_permission, _visible_units_queryset
from ..views.org_admin.context import _has_org_wide_membership
from .constants import TEACHER_ROLE_NAMES
from .registry import ROLE_LABELS, unit_type_label

_CTX = "organizations.members"

PAGE_SIZE = 25
#: Cədvəl sətrində göstərilən rəhbərlik sətri sayı (qalanı «+N»).
HEAD_PREVIEW = 2
#: Bu səviyyədən (org_admin həddi) yuxarı hər rol rəhbər heyət sayılır.
LEADERSHIP_MIN_LEVEL = 80
#: `member.view` daşıyan, bölməyə bağlı OLMAYAN aktor üçün minimum rol səviyyəsi.
MEMBER_VIEW_MIN_LEVEL = 65

#: Adına görə rəhbər heyət sayılan rollar (seed kataloqu + köhnə adlar).
LEADERSHIP_ROLE_NAMES = frozenset(
    {
        "rector",
        "vice_rector",
        "dean",
        "vice_dean",
        "chair_head",
        "department_head",
        "section_head",
        "program_coordinator",
        "teaching_office_head",
        "exam_center_head",
        "ikt_rehber",
        "director",
        "deputy_director",
        "vice_director",
        "admin_unit_head",
        "org_admin",
        "owner",
        "manager",
        "branch_manager",
    }
)
STUDENT_ROLE_NAMES = frozenset({"student", "lead_student"})
#: «Heyət» KPI-sindən çıxarılan rollar — tələbə, məzun, valideyn və doldurucu «member».
NON_STAFF_ROLE_NAMES = frozenset({"student", "lead_student", "alumni", "parent", "member"})
TEACHING_ROLE_NAMES = frozenset(TEACHER_ROLE_NAMES) | frozenset(
    {"lab_assistant", "professor", "associate_professor", "senior_instructor"}
)

#: `om_kind` filtrinin dəyərləri (KPI kartları da bunları göndərir).
KINDS = ("leaders", "staff", "teachers", "students", "unscoped")

SORTS = {
    "role": ("-role__level", "user__first_name", "user__last_name", "user__username"),
    "name": ("user__first_name", "user__last_name", "user__username"),
    "-name": ("-user__first_name", "-user__last_name", "-user__username"),
    "newest": ("-created_at", "user__username"),
    "oldest": ("created_at", "user__username"),
}

#: Rəhbərlik sətirlərinin sırası — əvvəl böyük vahidlər.
_HEAD_ORDER = (
    OrgUnitType.RECTORATE,
    OrgUnitType.VICE_RECTORATE,
    OrgUnitType.INSTITUTE,
    OrgUnitType.FACULTY,
    OrgUnitType.DEANERY,
    OrgUnitType.CHAIR,
    OrgUnitType.DEPARTMENT,
    OrgUnitType.CENTER,
    OrgUnitType.LAB,
    OrgUnitType.SPECIALTY,
    OrgUnitType.GROUP,
)


# ─── Etiketlər ──────────────────────────────────────────────────────────────


def head_label(unit_type: str) -> str:
    """`OrgUnit.head` üçün vəzifə etiketi — vahidin tipinə görə."""
    labels = {
        OrgUnitType.FACULTY: pgettext(_CTX, "Dekan"),
        OrgUnitType.CHAIR: pgettext(_CTX, "Kafedra müdiri"),
        OrgUnitType.DEPARTMENT: pgettext(_CTX, "Kafedra müdiri"),
        OrgUnitType.GROUP: pgettext(_CTX, "Kurator"),
        OrgUnitType.RECTORATE: pgettext(_CTX, "Rektor"),
        OrgUnitType.VICE_RECTORATE: pgettext(_CTX, "Prorektor"),
        OrgUnitType.DEANERY: pgettext(_CTX, "Dekanlıq rəhbəri"),
        OrgUnitType.SPECIALTY: pgettext(_CTX, "İxtisas rəhbəri"),
        OrgUnitType.CENTER: pgettext(_CTX, "Mərkəz rəhbəri"),
        OrgUnitType.INSTITUTE: pgettext(_CTX, "İnstitut direktoru"),
        OrgUnitType.LAB: pgettext(_CTX, "Laboratoriya müdiri"),
    }
    return labels.get(unit_type) or pgettext(_CTX, "Rəhbər")


def role_text(role_name: str, display_name: str = "") -> str:
    """Rol etiketi — reyestr etiketləri → seed/admin etiketi → «Üzv»."""
    return ROLE_LABELS.get(role_name) or visible_role_label(role_name, display_name) or pgettext(_CTX, "Üzv")


def role_label(role) -> str:
    return role_text(role.name, role.display_name)


def is_leader_role(role) -> bool:
    return role.name in LEADERSHIP_ROLE_NAMES or int(role.level or 0) >= LEADERSHIP_MIN_LEVEL


def format_date(value) -> str:
    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%d.%m.%Y")


def _leader_q(head_user_ids) -> Q:
    return (
        Q(role__name__in=LEADERSHIP_ROLE_NAMES)
        | Q(role__level__gte=LEADERSHIP_MIN_LEVEL)
        | Q(user_id__in=list(head_user_ids))
    )


# ─── Giriş + əhatə ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MembersAccess:
    """Aktorun üzv reyestrinə girişi və görə bildiyi üzvlük/vahid sorğuları."""

    has_access: bool
    is_org_wide: bool
    #: Unit-rolu var, amma `scope_unit` təyin edilməyib — heç nə görmür (fail-closed).
    scope_unset: bool
    memberships: object
    units: object


def resolve_members_access(request, organization) -> MembersAccess:
    """Köhnə `build_organization_members_context` ilə EYNİ qapı + əhatə (fail-closed)."""
    scope = get_permission_scope(request.user, organization, "member.view", request=request)
    can_manage = _can_manage_organization(request.user, organization)
    has_access = bool(
        can_manage
        or (
            _has_org_permission(request, "member.view")
            and (scope.is_unit_scoped or get_user_org_role_level(request.user, organization) >= MEMBER_VIEW_MIN_LEVEL)
        )
    )
    memberships = Membership.objects.filter(organization=organization, is_active=True)
    if scope.is_unit_scoped:
        return MembersAccess(
            has_access=has_access,
            is_org_wide=False,
            scope_unset=False,
            memberships=scope_memberships_by_unit(memberships, scope, organization),
            units=_visible_units_queryset(organization, scope),
        )
    if scope.is_org_wide or _has_org_wide_membership(request.user, organization):
        return MembersAccess(
            has_access=has_access,
            is_org_wide=True,
            scope_unset=False,
            memberships=memberships,
            units=OrgUnit.objects.filter(organization=organization, is_active=True),
        )
    # QA B-2: `scope_unit`-i təyin edilməmiş unit-rolu (dekan, müdir) əvvəllər
    # filtrsiz keçib bütün təşkilatı görürdü — sahəsi müəyyən olmayan rol heç nə görmür.
    return MembersAccess(
        has_access=has_access,
        is_org_wide=False,
        scope_unset=True,
        memberships=memberships.none(),
        units=OrgUnit.objects.none(),
    )


# ─── Vahid xəritəsi (TƏK sorğu) ─────────────────────────────────────────────


class UnitIndex:
    """Aktiv vahidlərin (ad · tip · valideyn) və rəhbərlərinin yaddaş xəritəsi.

    Bölmə zənciri («Kafedra · Fakültə») və rəhbərlik sətirləri («Dekan · X»)
    buradan qurulur — səhifədəki sətir sayı ilə artan sorğu YOXDUR.
    ``visible_ids`` verilibsə rəhbərlik yalnız həmin (əhatədəki) vahidlər üzrə
    yığılır; adlar/zəncir üçün bütün aktiv vahidlər saxlanılır (əcdad adları).
    """

    def __init__(self, organization, visible_ids=None):
        self.units: dict = {}
        self.heads: dict = defaultdict(list)
        rows = (
            OrgUnit.objects.filter(organization=organization, is_active=True)
            .order_by()
            .values_list("id", "name", "unit_type", "parent_id", "head_id")
        )
        for unit_id, name, unit_type, parent_id, head_id in rows:
            self.units[unit_id] = (name, unit_type, parent_id)
            if head_id and (visible_ids is None or unit_id in visible_ids):
                self.heads[head_id].append(unit_id)

    def trail(self, unit_id, limit: int = 3) -> list:
        """Vahidin əcdad adları — yaxından uzağa (valideyn, baba, …)."""
        names, seen = [], set()
        current = self.units.get(unit_id)
        while current is not None and current[2] is not None and len(names) < limit:
            parent_id = current[2]
            if parent_id in seen:
                break
            seen.add(parent_id)
            parent = self.units.get(parent_id)
            if parent is None:
                break
            names.append(parent[0])
            current = parent
        return names

    def head_lines(self, user_id) -> list:
        """Şəxsin rəhbərlik etdiyi vahidlər — `[{label, unit, unit_id, type_label}]`."""
        lines = []
        for unit_id in self.heads.get(user_id, ()):
            name, unit_type, _parent_id = self.units[unit_id]
            lines.append(
                {
                    "unit_id": str(unit_id),
                    "label": head_label(unit_type),
                    "unit": name,
                    "unit_type": unit_type,
                    "type_label": unit_type_label(unit_type),
                }
            )
        rank = {code: index for index, code in enumerate(_HEAD_ORDER)}
        lines.sort(key=lambda item: (rank.get(item["unit_type"], len(rank)), item["unit"].lower()))
        return lines
