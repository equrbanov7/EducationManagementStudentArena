"""«Bildiriş göndər» — struktur və şöbə əhatələri (sahib istəyi, 2026-09-08).

Əvvəl bildiriş yalnız BÜTÖV təşkilata (org admin) və müəllimin öz imtahan
qruplarına gedirdi. İndi hədəf kimi bunlar da seçilir:

* ``unit_<uuid>``       — struktur bölməsi: fakültə / kafedra / akademik qrup.
  Alıcılar = bölməyə (və alt-ağacına) əhatəli AKTİV üzvlüklər (müəllim, müavin,
  koordinator…) + alt-ağacdakı qrupların AKTİV tələbə qeydləri + bölmə
  rəhbərləri (dekan / müdir / kurator).
* ``role_<key>_<orgid>`` — şöbə / heyət qrupu: imtahan mərkəzi, tədris şöbəsi,
  RİM, HR, dekanlar, kafedra müdirləri, bütün müəllimlər, bütün tələbələr
  (``ROLE_TARGETS`` kataloqu).

QAPILAR (fail-closed): superadmin hər şeyi görür; təşkilat üzvü olmayan heç nə;
org admin və ya ``unit.view`` üzrə ORG-WIDE əhatəsi olan (RİM, tədris şöbəsi,
prorektor…) bütün bölmə və şöbə hədəflərini; UNIT əhatəli (dekan / kafedra
müdiri) yalnız öz alt-ağacındakı bölmələri; kurator yalnız rəhbəri olduğu
bölməni. Şöbə hədəfləri (``role_``) yalnız org-wide aktora açıqdır.
"""

from __future__ import annotations

from collections import OrderedDict

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import pgettext

from apps.organizations.models import Membership, Organization, OrgUnit
from apps.organizations.scoping import get_permission_scope
from apps.organizations.structure_views.constants import KAFEDRA_UNIT_TYPES, TEACHER_ROLE_NAMES
from apps.organizations.views import _visible_units_queryset
from core.constants import OrgUnitType

_CTX = "profile.publish_notification"

#: Şöbə / heyət hədəfləri: açar → (etiket, rol adları, ikon).
ROLE_TARGETS = OrderedDict(
    [
        (
            "exam_center",
            (pgettext(_CTX, "İmtahan mərkəzi"), ("exam_center_head", "exam_center_staff"), "fa-clipboard-check"),
        ),
        (
            "teaching_office",
            (pgettext(_CTX, "Tədris şöbəsi"), ("teaching_office_head", "teaching_office_staff"), "fa-book-open"),
        ),
        ("rim", (pgettext(_CTX, "RİM mərkəzi"), ("ikt_rehber", "rim_staff"), "fa-network-wired")),
        ("hr", (pgettext(_CTX, "HR / kadrlar"), ("hr",), "fa-id-badge")),
        ("deans", (pgettext(_CTX, "Dekanlar və müavinlər"), ("dean", "vice_dean"), "fa-user-tie")),
        ("chair_heads", (pgettext(_CTX, "Kafedra müdirləri"), ("chair_head",), "fa-user-graduate")),
        ("teachers", (pgettext(_CTX, "Bütün müəllimlər"), tuple(TEACHER_ROLE_NAMES), "fa-chalkboard-user")),
        ("students", (pgettext(_CTX, "Bütün tələbələr"), ("student", "lead_student"), "fa-graduation-cap")),
    ]
)

#: Hədəf kimi seçilə bilən bölmə tipləri — kataloq sırası ilə.
UNIT_TARGET_TYPES = (OrgUnitType.FACULTY, *KAFEDRA_UNIT_TYPES, OrgUnitType.GROUP)

CATEGORY_LABELS = OrderedDict(
    [
        ("org", pgettext(_CTX, "Təşkilat")),
        ("roles", pgettext(_CTX, "Şöbələr və heyət")),
        ("faculty", pgettext(_CTX, "Fakültələr")),
        ("chair", pgettext(_CTX, "Kafedralar")),
        ("group", pgettext(_CTX, "Qruplar")),
        ("exam_group", pgettext(_CTX, "İmtahan qrupları")),
    ]
)

_UNIT_CATEGORY = {
    OrgUnitType.FACULTY: ("faculty", "fa-building-columns"),
    OrgUnitType.CHAIR: ("chair", "fa-landmark"),
    OrgUnitType.DEPARTMENT: ("chair", "fa-landmark"),
    OrgUnitType.GROUP: ("group", "fa-users"),
}


class _Access:
    __slots__ = ("is_member", "org_wide", "scope")

    def __init__(self, is_member, org_wide, scope=None):
        self.is_member = is_member
        self.org_wide = org_wide
        self.scope = scope


def _access(user, capabilities, organization) -> _Access:
    if capabilities.get("is_superadmin"):
        return _Access(True, True, None)
    is_member = Membership.objects.filter(user=user, organization=organization, is_active=True).exists()
    if not is_member:
        return _Access(False, False, None)
    scope = get_permission_scope(user, organization, "unit.view")
    return _Access(True, bool(capabilities.get("is_org_admin")) or scope.is_org_wide, scope)


def _in_scope(unit, scope) -> bool:
    if scope is None or not scope.is_unit_scoped:
        return False
    return any(unit.path == path or unit.path.startswith(f"{path}/") for path in scope.unit_paths)


def _unit_label(unit) -> str:
    parent = unit.parent if unit.parent_id else None
    if unit.unit_type == OrgUnitType.FACULTY:
        return unit.name
    if parent is not None and parent.name:
        return f"{unit.name} · {parent.name}"
    return unit.name


# ─── Hədəf siyahısı ─────────────────────────────────────────────────────────


def organization_targets(user, capabilities, organization) -> list:
    """Aktiv təşkilat üçün bölmə + şöbə hədəfləri (kateqoriyalı, sıralı)."""
    if organization is None:
        return []
    access = _access(user, capabilities, organization)
    if not access.is_member:
        return []

    targets = []
    if access.org_wide:
        for key, (label, _roles, icon) in ROLE_TARGETS.items():
            targets.append(
                {
                    "value": f"role_{key}_{organization.pk}",
                    "label": label,
                    "category": "roles",
                    "category_label": CATEGORY_LABELS["roles"],
                    "icon": icon,
                    "is_exclusive": False,
                }
            )

    base = OrgUnit.objects.filter(organization=organization, is_active=True)
    if access.org_wide:
        units = base.filter(unit_type__in=UNIT_TARGET_TYPES)
    elif access.scope is not None and access.scope.has_structure_access:
        units = _visible_units_queryset(organization, access.scope).filter(unit_type__in=UNIT_TARGET_TYPES)
    else:
        units = base.none()
    # Kurator / rəhbər öz bölməsini həmişə görür (əhatə olmasa da).
    units = units | base.filter(head=user, unit_type__in=UNIT_TARGET_TYPES)
    order = {code: index for index, code in enumerate(UNIT_TARGET_TYPES)}
    unit_rows = sorted(
        units.select_related("parent").distinct(),
        key=lambda u: (order.get(u.unit_type, 99), u.name.lower()),
    )
    for unit in unit_rows:
        category, icon = _UNIT_CATEGORY.get(unit.unit_type, ("group", "fa-users"))
        targets.append(
            {
                "value": f"unit_{unit.pk}",
                "label": _unit_label(unit),
                "category": category,
                "category_label": CATEGORY_LABELS[category],
                "icon": icon,
                "is_exclusive": False,
            }
        )
    return targets


# ─── Alıcıların həlli ───────────────────────────────────────────────────────


def _active_org(org_id):
    try:
        return Organization.objects.get(pk=org_id, is_active=True, status="active")
    except (ValidationError, ValueError, Organization.DoesNotExist):
        return None


def resolve_unit_target(user, capabilities, target: str):
    """``unit_<uuid>`` → alıcı istifadəçilər (queryset) və ya ``None`` (icazə/yoxluq)."""
    from apps.registrar.models import StudentAcademicRecord

    unit_id = target[5:].strip()
    try:
        unit = OrgUnit.objects.select_related("organization").get(pk=unit_id, is_active=True)
    except (ValidationError, ValueError, OrgUnit.DoesNotExist):
        return None
    organization = unit.organization
    if not organization.is_active:
        return None
    access = _access(user, capabilities, organization)
    if not access.is_member:
        return None
    if not (access.org_wide or _in_scope(unit, access.scope) or unit.head_id == user.pk):
        return None

    subtree_members = Q(scope_unit_id=unit.id) | Q(scope_unit__path__startswith=f"{unit.path}/")
    subtree_groups = Q(group_id=unit.id) | Q(group__path__startswith=f"{unit.path}/")
    subtree_units = Q(pk=unit.id) | Q(path__startswith=f"{unit.path}/")
    member_ids = (
        Membership.objects.filter(organization=organization, is_active=True).filter(subtree_members).values("user_id")
    )
    student_ids = (
        StudentAcademicRecord.objects.filter(organization=organization, is_active=True)
        .filter(subtree_groups)
        .values("student_id")
    )
    head_ids = (
        OrgUnit.objects.filter(organization=organization, is_active=True, head_id__isnull=False)
        .filter(subtree_units)
        .values("head_id")
    )
    User = get_user_model()
    return User.objects.filter(is_active=True).filter(Q(pk__in=member_ids) | Q(pk__in=student_ids) | Q(pk__in=head_ids))


def resolve_role_target(user, capabilities, target: str):
    """``role_<key>_<orgid>`` → alıcı istifadəçilər və ya ``None``."""
    from apps.registrar.models import StudentAcademicRecord

    key, _sep, org_id = target[5:].rpartition("_")
    if key not in ROLE_TARGETS or not org_id:
        return None
    organization = _active_org(org_id)
    if organization is None:
        return None
    access = _access(user, capabilities, organization)
    if not access.is_member or not access.org_wide:
        return None
    _label, role_names, _icon = ROLE_TARGETS[key]
    user_filter = Q(
        pk__in=Membership.objects.filter(
            organization=organization, is_active=True, role__is_active=True, role__name__in=role_names
        ).values("user_id")
    )
    if key == "students":
        user_filter |= Q(
            pk__in=StudentAcademicRecord.objects.filter(organization=organization, is_active=True).values("student_id")
        )
    User = get_user_model()
    return User.objects.filter(is_active=True).filter(user_filter)


__all__ = [
    "ROLE_TARGETS",
    "CATEGORY_LABELS",
    "UNIT_TARGET_TYPES",
    "organization_targets",
    "resolve_unit_target",
    "resolve_role_target",
]
