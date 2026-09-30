"""«Təşkilat paneli» (kabinet bölməsi ``org-overview``) — təşkilat-domen rəqəmləri (2026-10-01).

Sahib: «Panel, Üzvlər, Rollar səhifələrini yenidən redizayn et». Köhnə müstəqil
``/organizations/<slug>/`` səhifəsi yalnız 3 COUNT + audit axını göstərirdi və
kabinetdən kənarda idi. Bu modul panelin TƏŞKİLAT tərəfini qurur: üzv KPI-ləri,
rol paylanması, son qoşulanlar və struktur sayları. Dövr (registrar), audit izi
və keçidlər accounts bölmə qurucusunda əlavə olunur
(``accounts/views/profile/_sections/org_overview.py``).

ƏHATƏ ``resolve_members_access`` ilə EYNİDİR («Struktur üzvləri» reyestri):
org-wide aktor bütün təşkilatı, bölməyə bağlı aktor (dekan, tyutor) yalnız öz
alt-ağacını, əhatəsiz unit-rolu HEÇ NƏ görür (fail-closed). Üzv reyestrinə girişi
olmayan aktor (məs. yalnız ``unit.view``) üzv rəqəmlərini ümumiyyətlə almır.

SORĞU BÜDCƏSİ sabitdir (üzv sayından asılı deyil): struktur sayları 1 GROUP BY,
üzv KPI-ləri 1 aqreqat (şərti COUNT DISTINCT), rol paylanması 1 GROUP BY, son
qoşulanlar 1 SELECT (``select_related``) — üstəgəl giriş/əhatə həlli.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from core.constants import OrgUnitType

from .models import OrgUnit
from .structure_views.constants import KAFEDRA_UNIT_TYPES
from .structure_views.members_base import (
    NON_STAFF_ROLE_NAMES,
    STUDENT_ROLE_NAMES,
    TEACHING_ROLE_NAMES,
    format_date,
    is_leader_role,
    resolve_members_access,
    role_text,
)
from .structure_views.registry_people import display_name, initials

#: Rol paylanmasında ayrıca göstərilən sətir sayı (qalanı «Digər»).
ROLE_ROWS = 7
#: «Son qoşulanlar» siyahısının ölçüsü.
RECENT_LIMIT = 8
#: «Yeni» KPI-si — son N gündə qoşulan fərqli şəxs.
NEW_WINDOW_DAYS = 30


def structure_counts(organization) -> dict:
    """Aktiv vahidlərin tip üzrə sayı — TƏK ``GROUP BY`` (org-wide struktur metadatası)."""
    rows = (
        OrgUnit.objects.filter(organization=organization, is_active=True)
        .order_by()
        .values_list("unit_type")
        .annotate(total=Count("id"))
    )
    by_type = {unit_type: total for unit_type, total in rows}
    return {
        "faculties": by_type.get(OrgUnitType.FACULTY, 0),
        "kafedras": sum(by_type.get(code, 0) for code in KAFEDRA_UNIT_TYPES),
        "specialties": by_type.get(OrgUnitType.SPECIALTY, 0),
        "groups": by_type.get(OrgUnitType.GROUP, 0),
        "units": sum(by_type.values()),
    }


def _member_kpis(memberships) -> dict:
    since = timezone.now() - timedelta(days=NEW_WINDOW_DAYS)
    distinct = "user_id"
    return memberships.order_by().aggregate(
        total=Count(distinct, distinct=True),
        students=Count(distinct, distinct=True, filter=Q(role__name__in=STUDENT_ROLE_NAMES)),
        teachers=Count(distinct, distinct=True, filter=Q(role__name__in=TEACHING_ROLE_NAMES)),
        staff=Count(distinct, distinct=True, filter=~Q(role__name__in=NON_STAFF_ROLE_NAMES)),
        inactive=Count(distinct, distinct=True, filter=Q(user__is_active=False)),
        recent=Count(distinct, distinct=True, filter=Q(created_at__gte=since)),
    )


def _role_distribution(memberships) -> dict:
    rows = list(
        memberships.order_by()
        .values_list("role__name", "role__display_name", "role__level")
        .annotate(total=Count("user_id", distinct=True))
        .order_by("-total", "-role__level", "role__name")
    )
    top = rows[:ROLE_ROWS]
    rest = rows[ROLE_ROWS:]
    peak = max((row[3] for row in rows), default=0) or 1
    items = [
        {
            "name": name,
            "label": role_text(name, display),
            "count": total,
            "pct": round(total * 100 / peak, 1),
        }
        for name, display, _level, total in top
    ]
    return {
        "rows": items,
        "other_count": sum(row[3] for row in rest),
        "other_roles": len(rest),
        "peak": peak,
        "role_total": len(rows),
    }


def _recent_members(memberships) -> list:
    """Son qoşulan şəxslər — bir nəfər bir dəfə (ən yeni üzvlüyü ilə)."""
    rows, seen = [], set()
    queryset = memberships.select_related("user", "role", "scope_unit").order_by("-created_at", "-pk")
    for membership in queryset[: RECENT_LIMIT * 2]:
        if membership.user_id in seen:
            continue
        seen.add(membership.user_id)
        user = membership.user
        name = display_name(user)
        rows.append(
            {
                "name": name,
                "initials": initials(name),
                "username": user.username,
                "is_user_active": bool(user.is_active),
                "role_label": role_text(membership.role.name, membership.role.display_name),
                "is_leader": is_leader_role(membership.role),
                "is_student": membership.role.name in STUDENT_ROLE_NAMES,
                "unit_name": membership.scope_unit.name if membership.scope_unit_id else "",
                "joined": format_date(membership.created_at),
                "profile_url": reverse("accounts:public_profile", kwargs={"username": user.username}),
            }
        )
        if len(rows) >= RECENT_LIMIT:
            break
    return rows


def build_overview_data(request, organization) -> dict:
    """Panelin təşkilat rəqəmləri — əhatə «Struktur üzvləri» reyestri ilə EYNİDİR."""
    access = resolve_members_access(request, organization)
    data = {
        "structure": structure_counts(organization),
        "members_access": bool(access.has_access),
        "is_org_wide": bool(access.is_org_wide),
        "scope_unset": bool(access.scope_unset),
        "members": None,
        "roles": None,
        "recent": [],
    }
    if not access.has_access:
        return data
    memberships = access.memberships
    data["members"] = _member_kpis(memberships)
    data["roles"] = _role_distribution(memberships)
    data["recent"] = _recent_members(memberships)
    return data


__all__ = ["build_overview_data", "structure_counts"]
