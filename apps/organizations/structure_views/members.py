"""«Struktur üzvləri» kabinet bölməsi — üzv reyestri context-i (2026-09-08).

Sahib şikayəti: köhnə bölmə Bootstrap-dövrü formadan («Filtrlə» düyməsi) və
düz cədvəldən ibarət idi — kimin dekan, kafedra müdiri, proqram koordinatoru
olduğu görünmürdü. Bölmə `ems_ui` komponentləri ilə yenidən qurulur:

* KPI sırası — üzv · heyət · müəllim · tələbə · rəhbərlik · bölməsiz
  (kartlar KLİK EDİLƏ BİLƏN filtrdir — `om_kind`);
* AVTO filtr — axtarış · rol · bölmə (axtarışlı) · növ · sıralama
  («Tətbiq et» yoxdur, «Sıfırla» qalır);
* cədvəl — üzv · rol · vəzifə · bölmə · qoşulma; sətir əməlləri «Profil» və
  «Ətraflı» («Üzv kartı» çekmecəsi, JSON — bax `members_registry_actions.py`).

GİRİŞ QAYDASI köhnə `build_organization_members_context` ilə EYNİDİR:
  * superadmin / təşkilat sahibi / idarəetmə səviyyəli rol
    (`_can_manage_organization`), VƏ YA
  * `member.view` + (bölmə əhatəsi VƏ YA rol səviyyəsi ≥ 65).

ƏHATƏ `member.view` açarını DAŞIYAN üzvlükdən çıxır (`get_permission_scope`,
2026-09-12 P1-11): bölməyə bağlı aktor (dekan, kafedra müdiri) yalnız öz
alt-ağacını; `member.view`-lu ORGANIZATION rolu (HR, RİM, prorektor…) hamısını;
`scope_unit`-i TƏYİN EDİLMƏMİŞ unit-rolu HEÇ NƏ (fail-closed, QA B-2). Köhnə
`get_unit_scope` HƏR üzvlüyün unitini toplayırdı — dekanın əlaqəsiz müəllim
təyinatı başqa kafedranın üzvlərini siyahıya salırdı; o resolver silinib.

RƏHBƏRLİK iki mənbədən çıxarılır və cədvəldə tac nişanı + mətn ilə seçilir:
  1. `OrgUnit.head` — fakültə → «Dekan · <fakültə>», kafedra → «Kafedra
     müdiri · <kafedra>», qrup → «Kurator · <qrup>»;
  2. rol adı (`LEADERSHIP_ROLE_NAMES`) və ya rol səviyyəsi ≥ 80.

SORĞU BÜDCƏSİ səhifə ölçüsündən asılı deyil: bütün aktiv vahidlər (ad · tip ·
valideyn · rəhbər) BİR sorğu ilə gəlir və bölmə zənciri / rəhbərlik sətirləri
Python-da qurulur; KPI-lər sabit sayda COUNT sorğusudur; səhifə sətirləri
`select_related` ilə TƏK sorğudur.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from core.constants import OrgUnitType, RoleScopeType
from core.staff_position import visible_role_label

from ..models import Membership, OrgUnit
from ..scoping import get_permission_scope, scope_memberships_by_unit
from ..services import get_user_org_role_level
from ..views import _can_manage_organization, _has_org_permission, _visible_units_queryset
from ..views.org_admin.context import _has_org_wide_membership
from .constants import KAFEDRA_UNIT_TYPES, TEACHER_ROLE_NAMES
from .registry import ROLE_LABELS, _display_name, _initials, unit_type_label

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


# ─── Filtr köməkçiləri ──────────────────────────────────────────────────────


def _kind_options():
    return [
        {"value": "", "label": pgettext(_CTX, "Hamısı")},
        {"value": "leaders", "label": pgettext(_CTX, "Rəhbərlər")},
        {"value": "staff", "label": pgettext(_CTX, "Heyət")},
        {"value": "teachers", "label": pgettext(_CTX, "Müəllimlər")},
        {"value": "students", "label": pgettext(_CTX, "Tələbələr")},
        {"value": "unscoped", "label": pgettext(_CTX, "Bölməsiz")},
    ]


def _sort_options():
    return [
        {"value": "role", "label": pgettext(_CTX, "Rol (yuxarıdan aşağı)")},
        {"value": "name", "label": pgettext(_CTX, "Ad (A→Z)")},
        {"value": "-name", "label": pgettext(_CTX, "Ad (Z→A)")},
        {"value": "newest", "label": pgettext(_CTX, "Ən yeni")},
        {"value": "oldest", "label": pgettext(_CTX, "Ən köhnə")},
    ]


def _apply_kind(queryset, kind, head_user_ids):
    if kind == "leaders":
        return queryset.filter(_leader_q(head_user_ids))
    if kind == "staff":
        return queryset.exclude(role__name__in=NON_STAFF_ROLE_NAMES)
    if kind == "teachers":
        return queryset.filter(role__name__in=TEACHING_ROLE_NAMES)
    if kind == "students":
        return queryset.filter(role__name__in=STUDENT_ROLE_NAMES)
    if kind == "unscoped":
        return queryset.filter(role__scope_type=RoleScopeType.UNIT, scope_unit__isnull=True)
    return queryset


def _role_options(base):
    """Görünən üzvlüklərdə RAST GƏLİNƏN rollar + fərqli şəxs sayı — TƏK sorğu."""
    rows = (
        base.order_by()
        .values_list("role__name", "role__display_name", "role__level")
        .annotate(n=Count("user_id", distinct=True))
        .order_by("-role__level", "role__name")
    )
    return [{"value": name, "label": f"{role_text(name, display)} ({n})"} for name, display, _level, n in rows]


def _unit_options(units):
    """Fakültələr və (altında) kafedralar — axtarışlı seçici üçün."""
    rows = list(
        units.filter(unit_type__in=(OrgUnitType.FACULTY, *KAFEDRA_UNIT_TYPES))
        .order_by()
        .values_list("id", "name", "unit_type", "parent_id")
    )
    faculties = sorted((r for r in rows if r[2] == OrgUnitType.FACULTY), key=lambda r: r[1].lower())
    chairs_by_parent = defaultdict(list)
    for row in rows:
        if row[2] != OrgUnitType.FACULTY:
            chairs_by_parent[row[3]].append(row)
    options, placed = [], set()
    for faculty in faculties:
        options.append({"value": str(faculty[0]), "label": faculty[1]})
        for chair in sorted(chairs_by_parent.get(faculty[0], ()), key=lambda r: r[1].lower()):
            options.append({"value": str(chair[0]), "label": f"{chair[1]} — {faculty[1]}"})
            placed.add(chair[0])
    leftovers = sorted(
        (r for r in rows if r[2] != OrgUnitType.FACULTY and r[0] not in placed), key=lambda r: r[1].lower()
    )
    options.extend({"value": str(row[0]), "label": row[1]} for row in leftovers)
    return options


def _clean_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value)) if value else ""
    except (ValueError, AttributeError, TypeError):
        return ""


def _denied():
    return {
        "has_access": False,
        "access_denied_message": pgettext(
            _CTX,
            "Üzv siyahısına baxış üçün `member.view` səlahiyyəti (bölmə əhatəsi ilə) və ya idarəetmə rolu lazımdır.",
        ),
    }


# ─── Bölmə ──────────────────────────────────────────────────────────────────


def build_members_section(request, organization) -> dict:
    access = resolve_members_access(request, organization)
    if not access.has_access:
        return _denied()
    slug = organization.slug

    search = (request.GET.get("om_q") or "").strip()[:120]
    role = (request.GET.get("om_role") or "").strip()[:100]
    unit_id = _clean_uuid((request.GET.get("om_unit") or "").strip())
    kind = (request.GET.get("om_kind") or "").strip()
    kind = kind if kind in KINDS else ""
    sort = (request.GET.get("om_sort") or "").strip()
    sort = sort if sort in SORTS else "role"

    visible_ids = None if access.is_org_wide else set(access.units.order_by().values_list("id", flat=True))
    index = UnitIndex(organization, visible_ids)
    head_user_ids = set(index.heads)
    base = access.memberships

    # ── KPI — sabit sayda COUNT (səhifə ölçüsündən asılı deyil). `order_by()`
    # MƏCBURİDİR: Membership-in defolt sıralaması DISTINCT-ə sütun əlavə edərdi.
    def distinct_users(queryset) -> int:
        return queryset.order_by().values("user_id").distinct().count()

    total = distinct_users(base)
    staff = distinct_users(base.exclude(role__name__in=NON_STAFF_ROLE_NAMES))
    teachers = distinct_users(base.filter(role__name__in=TEACHING_ROLE_NAMES))
    students = distinct_users(base.filter(role__name__in=STUDENT_ROLE_NAMES))
    leaders = distinct_users(base.filter(_leader_q(head_user_ids)))
    unscoped = base.filter(role__scope_type=RoleScopeType.UNIT, scope_unit__isnull=True).order_by().count()

    # ── Filtr + səhifə
    queryset = base.select_related("user", "role", "scope_unit")
    if search:
        queryset = queryset.filter(
            Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(user__username__icontains=search)
            | Q(user__email__icontains=search)
            | Q(title__icontains=search)
        )
    if role:
        queryset = queryset.filter(role__name=role)
    unit = access.units.filter(pk=unit_id).only("id", "path").first() if unit_id else None
    if unit is not None:
        queryset = queryset.filter(Q(scope_unit_id=unit.id) | Q(scope_unit__path__startswith=f"{unit.path}/"))
    else:
        unit_id = ""
    queryset = _apply_kind(queryset, kind, head_user_ids).order_by(*SORTS[sort], "pk")
    page_obj = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("om_page"))

    rows = []
    for membership in page_obj.object_list:
        user = membership.user
        name = _display_name(user)
        head_lines = index.head_lines(user.id)
        scope_unit = membership.scope_unit
        scope_missing = scope_unit is None and membership.role.scope_type == RoleScopeType.UNIT
        trail = index.trail(scope_unit.id) if scope_unit is not None else []
        rows.append(
            {
                "id": str(membership.id),
                "user_id": user.id,
                "name": name,
                "initials": _initials(name),
                "username": user.username,
                "email": user.email or "",
                "is_user_active": bool(user.is_active),
                "role": membership.role.name,
                "role_label": role_label(membership.role),
                "is_leader": is_leader_role(membership.role) or bool(head_lines),
                "is_student": membership.role.name in STUDENT_ROLE_NAMES,
                "head_lines": head_lines,
                "head_preview": head_lines[:HEAD_PREVIEW],
                "head_more": max(0, len(head_lines) - HEAD_PREVIEW),
                "title": membership.title or "",
                "employee_id": membership.employee_id or "",
                "is_primary": bool(membership.is_primary),
                "unit_id": str(scope_unit.id) if scope_unit is not None else "",
                "unit_name": scope_unit.name if scope_unit is not None else "",
                "unit_type_label": unit_type_label(scope_unit.unit_type) if scope_unit is not None else "",
                "unit_trail": " · ".join(trail),
                "unit_chain": " › ".join([scope_unit.name, *trail]) if scope_unit is not None else "",
                "scope_missing": scope_missing,
                "scope_all": scope_unit is None and not scope_missing,
                "joined": format_date(membership.created_at),
                "profile_url": reverse("accounts:public_profile", kwargs={"username": user.username}),
                "detail_url": reverse("organizations:structure_member_detail", args=[slug, user.id]),
            }
        )

    cell_dir = "accounts/profile/sections/org_members/"
    columns = [
        {"key": "member", "label": pgettext(_CTX, "Üzv")},
        {"key": "role", "label": pgettext(_CTX, "Rol")},
        {"key": "title", "label": pgettext(_CTX, "Vəzifə")},
        {"key": "unit", "label": pgettext(_CTX, "Bölmə")},
        {"key": "joined", "label": pgettext(_CTX, "Qoşulma")},
        # P2-8 (2026-09-12): boş `<th>` a11y pozuntusudur — etiket ekran oxuyucu üçün
        # gizli (`sr_only`) yazılır; msgid mövcud `organizations.roles_registry`-dəndir.
        {"key": "actions", "label": pgettext("organizations.roles_registry", "Əməllər"), "sr_only": True},
    ]
    table_rows = [
        {
            "row_head": row["name"],
            "head_include": f"{cell_dir}_cell_member.html",
            "cells": [
                {"include": f"{cell_dir}_cell_role.html"},
                {"include": f"{cell_dir}_cell_position.html"},
                {"include": f"{cell_dir}_cell_unit.html"},
                {"text": row["joined"] or "—", "nowrap": True, "muted": not row["joined"]},
            ],
            "actions_include": f"{cell_dir}_row_actions.html",
            "data": row,
        }
        for row in rows
    ]

    kpi_tiles = [
        {
            "label": pgettext(_CTX, "Üzv"),
            "value": total,
            "tone": "primary",
            "note": pgettext(_CTX, "fərqli şəxs (bir neçə rolu olan bir dəfə sayılır)"),
        },
        {
            "label": pgettext(_CTX, "Heyət"),
            "value": staff,
            "filter": "staff",
            "pressed": kind == "staff",
            "note": pgettext(_CTX, "tələbə olmayan rollar"),
        },
        {"label": pgettext(_CTX, "Müəllim"), "value": teachers, "filter": "teachers", "pressed": kind == "teachers"},
        {"label": pgettext(_CTX, "Tələbə"), "value": students, "filter": "students", "pressed": kind == "students"},
        {
            "label": pgettext(_CTX, "Rəhbərlik"),
            "value": leaders,
            "filter": "leaders",
            "pressed": kind == "leaders",
            "tone": "accent-primary",
            "note": pgettext(_CTX, "dekan, müdir, koordinator, rəhbər rollar"),
        },
        {
            "label": pgettext(_CTX, "Bölməsiz"),
            "value": unscoped,
            "filter": "unscoped",
            "pressed": kind == "unscoped",
            "tone": "accent-warning" if unscoped else "accent-success",
            "note": (
                pgettext(_CTX, "bölmə rolu var, bölmə təyin edilməyib")
                if unscoped
                else pgettext(_CTX, "hər bölmə rolunun bölməsi var")
            ),
        },
    ]

    filter_fields = [
        {
            "name": "om_q",
            "label": pgettext(_CTX, "Axtarış"),
            "kind": "search",
            "value": search,
            "wide": True,
            "placeholder": pgettext(_CTX, "Ad, e-poçt, istifadəçi adı və ya vəzifə"),
        },
        {
            "name": "om_role",
            "label": pgettext(_CTX, "Rol"),
            "kind": "select",
            "options": [{"value": "", "label": pgettext(_CTX, "Bütün rollar")}] + _role_options(base),
            "value": role,
        },
        {
            "name": "om_unit",
            "label": pgettext(_CTX, "Bölmə"),
            "kind": "select",
            "options": [{"value": "", "label": pgettext(_CTX, "Bütün bölmələr")}] + _unit_options(access.units),
            "value": unit_id,
            "searchable": True,
        },
        {
            "name": "om_kind",
            "label": pgettext(_CTX, "Növ"),
            "kind": "select",
            "options": _kind_options(),
            "value": kind,
        },
        {
            "name": "om_sort",
            "label": pgettext(_CTX, "Sıralama"),
            "kind": "select",
            "options": _sort_options(),
            "value": sort,
            "default": "role",
        },
    ]
    base_params = {
        "section": "org-members",
        "om_q": search,
        "om_role": role,
        "om_unit": unit_id,
        "om_kind": kind,
        "om_sort": sort if sort != "role" else "",
    }
    filtered = bool(search or role or unit_id or kind)

    if access.scope_unset:
        state_title = pgettext(_CTX, "Əhatəniz təyin edilməyib")
        state_body = pgettext(
            _CTX,
            "Rolunuz bölməyə bağlıdır, amma bölmə (fakültə/kafedra) təyin edilməyib — Tədris şöbəsi və ya HR ilə əlaqə saxlayın.",
        )
    elif filtered:
        state_title = pgettext(_CTX, "Filtrə uyğun üzv yoxdur")
        state_body = pgettext(_CTX, "Axtarışı dəyişin və ya «Sıfırla» ilə bütün siyahıya qayıdın.")
    else:
        state_title = pgettext(_CTX, "Hələ üzv yoxdur")
        state_body = pgettext(_CTX, "Təşkilata üzv əlavə olunduqda burada görünəcək.")

    return {
        "has_access": True,
        "access_denied_message": "",
        "organization": organization,
        "is_org_wide": access.is_org_wide,
        "scope_unset": access.scope_unset,
        "rows": rows,
        "table_rows": table_rows,
        "columns": columns,
        "table_state": "ready" if rows else "empty",
        "page_obj": page_obj,
        "pagination_query": urlencode({k: v for k, v in base_params.items() if v}),
        "total_count": total,
        "filtered_count": page_obj.paginator.count,
        "kpi_tiles": kpi_tiles,
        "filter_fields": filter_fields,
        "filter_count_label": pgettext(_CTX, "Nəticə: %(n)d üzvlük") % {"n": page_obj.paginator.count},
        "state_title": state_title,
        "state_body": state_body,
        "subtitle": pgettext(
            _CTX,
            "Təşkilatın üzvləri — rol, vəzifə və bölmə ilə. Rəhbər heyət (rektor, dekan, kafedra müdiri, "
            "koordinator) tac nişanı ilə seçilir; «Ətraflı» şəxsin bütün rollarını və rəhbərlik etdiyi bölmələri açır.",
        ),
        "profile_base_url": reverse("accounts:profile"),
        "embedded_in_profile": False,
    }


__all__ = [
    "MembersAccess",
    "UnitIndex",
    "build_members_section",
    "format_date",
    "head_label",
    "is_leader_role",
    "resolve_members_access",
    "role_label",
    "role_text",
    "LEADERSHIP_ROLE_NAMES",
    "STUDENT_ROLE_NAMES",
    "TEACHING_ROLE_NAMES",
    "PAGE_SIZE",
]
