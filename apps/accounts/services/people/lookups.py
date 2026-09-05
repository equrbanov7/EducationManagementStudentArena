"""Filtr açılışlarının məzmunu — REAL datadan, scope daxilində.

Sahibin tələbi: «Filtr açılışları BOŞ olmamalıdır». Ona görə fakültə/kafedra/
qrup/ixtisas/fənn/tədris ili siyahıları statik sabitlərdən deyil, təşkilatın öz
sətirlərindən gəlir və istifadəçinin scope-u ilə daralır (dekan yalnız öz
fakültəsinin kafedralarını seçim kimi görür).

Bu endpoint cədvəldən AYRIDIR (bax `academic_records` presedenti): açılışlar
səhifədən-səhifəyə dəyişmir, cədvəl isə hər klikdə yenilənir. Ayırmasaydıq hər
səhifə dəyişimi bütün lüğət sorğularını təkrar işlədərdi.
"""

from __future__ import annotations

from django.db.models import Count, Q

from apps.organizations.scoping import scope_org_units
from core.program_codes import program_display_label

from .constants import FACULTY_UNIT_TYPES, GENDER_BUCKETS, GROUP_UNIT_TYPES, KAFEDRA_UNIT_TYPES
from .filters import (
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    STATUS_BLOCKED,
    STATUS_DELETED,
    status_q,
)
from .permissions import PERM_VIEW_STUDENTS, PERM_VIEW_TEACHERS
from .scoping import unit_subtree_q

#: 766 aktiv qrup 500-də kəsilirdi (QA 2026-09-05 PEOPLE-RBAC-06) — açılışlar
#: kliyent-tərəfi axtarışlıdır, ona görə hədd tənzimləndi.
MAX_OPTIONS = 2000

_STATUS_BUCKETS = (STATUS_ACTIVE, STATUS_BLOCKED, STATUS_ARCHIVED, STATUS_DELETED)


def _unit_options(organization, scope, unit_types, *, parent_unit_id=None):
    from apps.organizations.models import OrgUnit

    queryset = OrgUnit.objects.filter(organization=organization, is_active=True, unit_type__in=unit_types)
    queryset = scope_org_units(queryset, scope)
    if parent_unit_id:
        subtree = unit_subtree_q(organization, parent_unit_id, path_field="path", id_field="id")
        queryset = queryset.filter(subtree)
    rows = queryset.order_by("name").values_list("pk", "name")[:MAX_OPTIONS]
    return [{"id": str(pk), "text": name} for pk, name in rows]


def _program_options(organization, scope, *, parent_unit_id=None):
    from apps.registrar.models import Program

    queryset = Program.objects.filter(organization=organization, is_active=True)
    if not scope.is_org_wide:
        queryset = queryset.filter(
            scope.unit_subtree_q(path_field="specialty_unit__path", id_field="specialty_unit_id")
        )
    if parent_unit_id:
        queryset = queryset.filter(
            unit_subtree_q(
                organization, parent_unit_id, path_field="specialty_unit__path", id_field="specialty_unit_id"
            )
        )
    rows = queryset.order_by("name").values_list("pk", "name", "official_code", "legacy_official_code")[:MAX_OPTIONS]
    # Etiket ƏL İLƏ birləşdirilmir: ``core.program_codes`` ``Program.display_label``
    # ilə EYNİ qaydadır — cari (NK 503) şifr yoxdursa KÖHNƏ şifrə geri çəkilir.
    # Əks halda yalnız köhnə şifri olan ixtisaslar (məs. «Dünya iqtisadiyyatı»)
    # filtrdə şifrsiz görünürdü. Daxili ``Program.code`` (``MYEDU-*``) göstərilmir.
    return [
        {"id": str(pk), "text": program_display_label(name, official_code, legacy_code)}
        for pk, name, official_code, legacy_code in rows
    ]


def _subject_options(organization, scope):
    """Fənn seçimləri — təşkilatın dərs açılışlarından (offering) çıxarılır.

    ``Subject`` özü strukturla bağlı deyil (org-wide kataloqdur), ona görə
    scope daralması AÇILIŞ üzərindən tətbiq olunur: unit-scope-lu istifadəçi
    yalnız öz alt-ağacındakı qruplara açılmış fənləri seçim kimi görür.
    """
    from apps.registrar.models import CourseOffering

    offerings = CourseOffering.objects.filter(organization=organization, is_active=True)
    if not scope.is_org_wide:
        offerings = offerings.filter(scope.unit_subtree_q(path_field="group__path", id_field="group_id"))
    rows = (
        offerings.values_list("subject_id", "subject__code", "subject__name")
        .distinct()
        .order_by("subject__name")[:MAX_OPTIONS]
    )
    return [{"id": str(pk), "text": f"{code} — {name}" if code else name} for pk, code, name in rows]


def _period_options(organization):
    from apps.organizations.models import AcademicPeriod

    rows = (
        AcademicPeriod.objects.filter(organization=organization, is_active=True)
        .values_list("academic_year", "name")
        .distinct()
    )
    years, seasons = set(), set()
    for academic_year, name in rows:
        if academic_year:
            years.add(academic_year)
        if name:
            seasons.add(name)
    return (
        [{"id": year, "text": year} for year in sorted(years, reverse=True)],
        [{"id": season, "text": season} for season in sorted(seasons)],
    )


def _gender_facets(queryset, *, include: bool):
    """Cins səbətlərinin sayları.

    «Təyin edilməyib» səbəti HƏMİŞƏ qaytarılır (say 0 olsa belə): mənbədə cins
    tələbələrin yalnız ~21 %-ində doludur və o səbəti gizlətmək istifadəçidə
    «cins filtri işləmir» təəssüratı yaradardı.
    """
    facets = {bucket: 0 for bucket in GENDER_BUCKETS}
    if not include:
        return facets
    rows = queryset.values("profile__gender").annotate(total=Count("pk"))
    for row in rows:
        bucket = row["profile__gender"] or "unspecified"
        if bucket in facets:
            facets[bucket] += row["total"]
        else:
            facets["unspecified"] += row["total"]
    return facets


def _status_facets(queryset):
    aggregates = {f"count_{bucket}": Count("pk", filter=status_q(bucket, prefix="")) for bucket in _STATUS_BUCKETS}
    row = queryset.aggregate(**aggregates)
    return {bucket: row.get(f"count_{bucket}") or 0 for bucket in _STATUS_BUCKETS}


def _demographics_coverage(queryset, *, include: bool):
    """Demoqrafik doldurma faizi — UI «21 % dolu» kimi açıq yaza bilsin."""
    if not include:
        return {"total": 0, "gender_known": 0, "birth_date_known": 0}
    return queryset.aggregate(
        total=Count("pk"),
        gender_known=Count("pk", filter=~Q(profile__gender="unspecified") & Q(profile__gender__isnull=False)),
        birth_date_known=Count("pk", filter=Q(profile__birth_date__isnull=False)),
    )


def build_filter_options(*, actor, kind: str, filters=None, request=None) -> dict:
    """Kataloq üçün bütün filtr açılışları + səbət sayları.

    ``kind`` ``"teachers"`` və ya ``"students"``.  İcazə yoxdursa boş zərf
    qaytarılır (``has_access: False``) — çağıran unutsa belə data sızmır.
    """
    empty = {
        "has_access": False,
        "faculties": [],
        "kafedras": [],
        "groups": [],
        "programs": [],
        "subjects": [],
        "years": [],
        "seasons": [],
        "gender_facets": {},
        "status_facets": {},
        "demographics_coverage": {"total": 0, "gender_known": 0, "birth_date_known": 0},
        "can_filter_demographics": False,
    }

    organization = actor.organization
    if organization is None:
        return empty

    if kind == "teachers":
        if not actor.can_view_teachers:
            return empty
        permission = PERM_VIEW_TEACHERS
        from .teachers import visible_teachers_qs as _visible

    elif kind == "students":
        if not actor.can_view_students:
            return empty
        permission = PERM_VIEW_STUDENTS
        from .students import visible_students_qs as _visible

    else:
        return empty

    scope = actor.scope_for(permission, request=request)
    if not scope.has_structure_access:
        return empty

    base = _visible(actor, request=request)
    faculty_filter = getattr(filters, "faculty", "") if filters is not None else ""

    years, seasons = _period_options(organization)
    demographics = actor.can_view_demographics

    options = {
        "has_access": True,
        "faculties": _unit_options(organization, scope, FACULTY_UNIT_TYPES),
        "kafedras": _unit_options(organization, scope, KAFEDRA_UNIT_TYPES, parent_unit_id=faculty_filter),
        "groups": [],
        "programs": [],
        "subjects": _subject_options(organization, scope),
        "years": years,
        "seasons": seasons,
        "gender_facets": _gender_facets(base, include=demographics),
        "status_facets": _status_facets(base),
        "demographics_coverage": _demographics_coverage(base, include=demographics),
        "can_filter_demographics": demographics,
    }

    if kind == "students":
        parent = getattr(filters, "kafedra", "") or faculty_filter if filters is not None else ""
        options["groups"] = _unit_options(organization, scope, GROUP_UNIT_TYPES, parent_unit_id=parent)
        options["programs"] = _program_options(organization, scope, parent_unit_id=parent)

    return options


__all__ = ["MAX_OPTIONS", "build_filter_options"]
