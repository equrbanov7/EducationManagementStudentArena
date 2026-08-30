"""«Müəllimlər» kataloqunun siyahı sorğusu.

**BAZA SEÇİMİ: ``User``, ``Membership`` DEYİL.** Bir müəllimin eyni təşkilatda
bir neçə aktiv üzvlüyü ola bilər (məs. həm `teacher`, həm `lab_assistant`, ya da
iki kafedrada). Membership üzərində qursaydıq cədvəldə eyni adam bir neçə dəfə
görünərdi və səhifələmə saymanı təhrif edərdi. Ona görə üzvlük ``Exists`` ilə
FİLTRƏ, göstərilən üzvlük məlumatı isə ``Subquery`` ilə SÜTUNA çevrilir —
nəticədə hər müəllim üçün DƏQİQ BİR sətir olur.

**N+1 yoxdur:** sorğu sayı sətir sayından ASILI DEYİL (bax
``apps/accounts/tests/test_people_directory.py`` sorğu-sayı testi).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Subquery

from apps.organizations.scoping import scope_memberships_by_unit

from . import filters as people_filters
from .constants import DEFAULT_PAGE_SIZE, TEACHER_ROLE_NAMES, TEACHER_SORT_OPTIONS
from .permissions import PERM_VIEW_TEACHERS
from .rows import identity_row, resolve_unit_ancestors
from .scoping import structure_filter_q

User = get_user_model()

#: Üzvlük sütunları hansı sıra ilə seçilir — ən yüksək səviyyəli/əsas üzvlük.
MEMBERSHIP_PICK_ORDER = ("-is_primary", "-role__level", "created_at")


def teacher_memberships_qs(organization):
    """Təşkilatın müəllim sayılan AKTİV üzvlükləri (scope tətbiq olunmadan)."""
    from apps.organizations.models import Membership

    return Membership.objects.filter(
        organization=organization,
        is_active=True,
        role__is_active=True,
        role__organization=organization,
        role__name__in=TEACHER_ROLE_NAMES,
    )


def scoped_teacher_memberships(actor, *, request=None, filters=None):
    """Aktorun scope-u + struktur filtri tətbiq olunmuş üzvlük queryset-i.

    ``visible_teachers_qs`` da, analitika da MƏHZ bunu işlədir — «hansı üzvlük
    sayılır» sualının tək cavabı olsun deyə. ``None`` qaytarır: scope yoxdur
    (fail-closed), yəni çağıran boş nəticə verməlidir.
    """
    organization = actor.organization
    if organization is None or not actor.can_view_teachers:
        return None

    scope = actor.scope_for(PERM_VIEW_TEACHERS, request=request)
    if not scope.has_structure_access:
        return None

    memberships = scope_memberships_by_unit(
        teacher_memberships_qs(organization),
        scope,
        organization=organization,
    )

    if filters is not None:
        structure_q = structure_filter_q(organization, filters, path_field="scope_unit__path", id_field="scope_unit_id")
        if structure_q:
            memberships = memberships.filter(structure_q)
    return memberships


def visible_teachers_qs(actor, *, request=None, filters=None):
    """Aktorun görə bildiyi müəllimlərin baza queryset-i (fail-closed).

    Scope YOXDURSA (``EMPTY_SCOPE``) — məsələn ``scope_unit`` təyin edilməmiş
    dekan — nəticə BOŞDUR, bütün təşkilat DEYİL. Bu, əvvəllər BLOKER tapıntı
    olmuş davranışın qarşısını alan yeganə yerdir.
    """
    memberships = scoped_teacher_memberships(actor, request=request, filters=filters)
    if memberships is None:
        return User.objects.none()

    correlated = memberships.filter(user=OuterRef("pk"))
    picked = correlated.order_by(*MEMBERSHIP_PICK_ORDER)

    queryset = (
        User.objects.filter(Exists(correlated))
        .exclude(is_superuser=True)
        .select_related("profile")
        .annotate(
            unit_id=Subquery(picked.values("scope_unit_id")[:1]),
            unit_name=Subquery(picked.values("scope_unit__name")[:1]),
            role_name=Subquery(picked.values("role__name")[:1]),
            role_label=Subquery(picked.values("role__display_name")[:1]),
            member_title=Subquery(picked.values("title")[:1]),
        )
    )
    return queryset


def _apply_filters(queryset, actor, filters, *, request=None):
    organization = actor.organization

    search = people_filters.search_q(filters.query, prefix="")
    if search:
        queryset = queryset.filter(search)

    status = people_filters.status_q(filters.status, prefix="")
    if status:
        queryset = queryset.filter(status)

    if actor.can_view_demographics:
        gender = people_filters.gender_q(filters.gender, prefix="")
        if gender:
            queryset = queryset.filter(gender)
        age = people_filters.age_q(filters, prefix="")
        if age:
            queryset = queryset.filter(age)

    if filters.subject or filters.year or filters.season:
        from apps.registrar.models import CourseOffering

        offerings = CourseOffering.objects.filter(
            organization=organization,
            is_active=True,
            instructor=OuterRef("pk"),
        )
        if filters.subject:
            offerings = offerings.filter(subject_id=filters.subject)
        if filters.year:
            offerings = offerings.filter(period__academic_year=filters.year)
        if filters.season:
            offerings = offerings.filter(period__name=filters.season)
        queryset = queryset.filter(Exists(offerings))

    return queryset


def filtered_teachers_qs(*, actor, filters, request=None):
    """Cədvəlin GÖRDÜYÜ dəqiq dəst — scope + struktur + axtarış/status/demoqrafiya.

    Analitika məhz bu funksiyanı çağırır ki, göstəricilər cədvəldən AYRILMASIN:
    filtr məntiqi tək yerdə qalır, «rəqəmlər siyahıya uyğun gəlmir» sinfi
    xətalar mümkün olmur.
    """
    queryset = visible_teachers_qs(actor, request=request, filters=filters)
    return _apply_filters(queryset, actor, filters, request=request)


def build_teachers_page(*, actor, filters, request=None, today=None) -> dict:
    """Səhifələnmiş müəllim cədvəli — context müqaviləsi `docs`-da sənədlidir."""
    empty = {
        "has_access": False,
        "results": [],
        "page": 1,
        "num_pages": 1,
        "total": 0,
        "has_next": False,
        "has_previous": False,
        "filters": filters.as_dict(),
    }
    if not actor.can_view_teachers or actor.organization is None:
        return empty

    queryset = filtered_teachers_qs(actor=actor, filters=filters, request=request)
    queryset = queryset.order_by(*TEACHER_SORT_OPTIONS.get(filters.sort, TEACHER_SORT_OPTIONS["name"]))

    page_size = filters.page_size or DEFAULT_PAGE_SIZE
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(filters.page)
    users = list(page_obj.object_list)

    ancestors = _ancestors_for(users, organization=actor.organization)

    results = []
    for user in users:
        row = identity_row(user, actor=actor, today=today)
        unit = ancestors.get(getattr(user, "unit_id", None), {})
        row.update(
            {
                "kind": "teacher",
                "role_name": getattr(user, "role_name", "") or "",
                "role_label": getattr(user, "role_label", "") or "",
                "title": getattr(user, "member_title", "") or "",
                "unit_name": unit.get("unit", "") or (getattr(user, "unit_name", "") or ""),
                "faculty_name": unit.get("faculty", ""),
                "kafedra_name": unit.get("kafedra", ""),
            }
        )
        results.append(row)

    return {
        "has_access": True,
        "results": results,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "total": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "filters": filters.as_dict(),
    }


def _ancestors_for(users, *, organization):
    """Səhifədəki müəllimlərin unitləri üçün fakültə/kafedra adları — 2 sorğu."""
    unit_ids = {getattr(user, "unit_id", None) for user in users}
    unit_ids.discard(None)
    if not unit_ids:
        return {}

    from apps.organizations.models import OrgUnit

    units = list(
        OrgUnit.objects.filter(organization=organization, pk__in=unit_ids).only("id", "name", "path", "unit_type")
    )
    return resolve_unit_ancestors(units, organization=organization)


__all__ = [
    "MEMBERSHIP_PICK_ORDER",
    "build_teachers_page",
    "filtered_teachers_qs",
    "scoped_teacher_memberships",
    "teacher_memberships_qs",
    "visible_teachers_qs",
]
