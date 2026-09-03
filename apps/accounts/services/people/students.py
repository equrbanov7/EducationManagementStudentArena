"""«Tələbələr» kataloqunun siyahı sorğusu.

**BAZA SEÇİMİ: ``User`` + ``StudentAcademicRecord`` ``Exists``.**
``StudentAcademicRecord`` üzərində birbaşa qursaydıq, iki proqrama yazılmış
tələbə cədvəldə iki dəfə görünərdi (unikal məhdudiyyət
``(organization, student, program)``-dır, `student` deyil). Müəllim kataloqu ilə
eyni naxış: üzvlük/qeyd ``Exists`` ilə FİLTRƏ, göstərilən sahələr ``Subquery``
ilə SÜTUNA çevrilir.

**Görünürlük qeydi (sənədli məhdudiyyət):** kataloqun mənbəyi akademik qeyddir,
ona görə akademik qeydi OLMAYAN hesab burada görünmür. Belə hesablar RİM
mərkəzində (bütün hesablar üzrə axtarış) tapılır. Qrupu təyin edilməmiş tələbə
isə unit-scope-lu istifadəçiyə görünmür (fail-closed) — org-wide istifadəçi onu
görür və qrupsuz olduğunu cədvəldə açıq oxuyur.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce, NullIf

from core.program_codes import program_code_search_q, program_display_label

from . import filters as people_filters
from .constants import DEFAULT_PAGE_SIZE, STUDENT_SORT_OPTIONS
from .permissions import PERM_VIEW_STUDENTS
from .rows import identity_row, resolve_unit_ancestors
from .scoping import structure_filter_q

User = get_user_model()

#: Bir neçə akademik qeyd olduqda hansı sütunlara baxılır (ən son qəbul).
RECORD_PICK_ORDER = ("-is_active", "-admission_year", "created_at")

#: ``None`` ÖZÜ mənalı dəyərdir (scope yoxdur → fail-closed), ona görə
#: «ötürülməyib» halı ayrı sentinel ilə göstərilir.
_UNSET = object()


def student_records_qs(organization):
    """Təşkilatın akademik qeydləri (scope tətbiq olunmadan)."""
    from apps.registrar.models import StudentAcademicRecord

    return StudentAcademicRecord.objects.filter(organization=organization)


def scoped_student_records(actor, *, request=None, filters=None):
    """Scope + struktur/qrup/ixtisas filtri tətbiq olunmuş akademik qeydlər.

    ``None`` = scope yoxdur (fail-closed). Analitika bu queryset üzərində
    bölgüləri hesablayır ki, siyahı ilə eyni dəsti saysın.
    """
    organization = actor.organization
    if organization is None or not actor.can_view_students:
        return None

    scope = actor.scope_for(PERM_VIEW_STUDENTS, request=request)
    if not scope.has_structure_access:
        return None

    records = student_records_qs(organization)
    if not scope.is_org_wide:
        records = records.filter(scope.unit_subtree_q(path_field="group__path", id_field="group_id"))

    if filters is not None:
        structure_q = structure_filter_q(organization, filters, path_field="group__path", id_field="group_id")
        if structure_q:
            records = records.filter(structure_q)
        if filters.group:
            records = records.filter(group_id=filters.group)
        if filters.program:
            records = records.filter(program_id=filters.program)
    return records


def visible_students_qs(actor, *, request=None, filters=None, records=_UNSET):
    """Aktorun görə bildiyi tələbələrin baza queryset-i (fail-closed).

    Scope-suz UNIT rolu → BOŞ nəticə (bütün təşkilat DEYİL).

    ``records`` — artıq hesablanmış scope dəsti. ``scoped_student_records``
    ucuz DEYİL (``unit_subtree_q`` ağac yolunu SORĞU ilə açır), ona görə həm
    siyahını, həm axtarış ``Exists``-ini quran çağıran onu BİR DƏFƏ hesablayıb
    ötürür — əks halda kataloqun sorğu büdcəsi 5 → 6 olurdu.
    """
    if records is _UNSET:
        records = scoped_student_records(actor, request=request, filters=filters)
    if records is None:
        return User.objects.none()

    correlated = records.filter(student=OuterRef("pk"))
    picked = correlated.order_by(*RECORD_PICK_ORDER)

    return (
        User.objects.filter(Exists(correlated))
        .exclude(is_superuser=True)
        .select_related("profile")
        .annotate(
            group_id=Subquery(picked.values("group_id")[:1]),
            group_name=Subquery(picked.values("group__name")[:1]),
            program_name=Subquery(picked.values("program__name")[:1]),
            # Rəsmi şifr: cari (NK 503) varsa cari, yoxsa ƏVVƏLKİ nəsil şifr —
            # ``Program.display_code`` ilə eyni qayda, amma SQL-də (annotasiya).
            program_code=Coalesce(
                NullIf(Subquery(picked.values("program__official_code")[:1]), Value("")),
                Subquery(picked.values("program__legacy_official_code")[:1]),
                Value(""),
            ),
            admission_year=Subquery(picked.values("admission_year")[:1]),
            academic_status=Subquery(picked.values("status")[:1]),
        )
    )


def _program_search_matcher(records):
    """Token → «bu tələbənin qeydlərindən biri həmin ixtisasa uyğundur?».

    AXTARIŞ İNVARİANTI: cədvəl sətri ``program_label``-i («Ad · şifr») GÖSTƏRİR,
    ona görə həmin ad və şifr axtarıla da bilməlidir — əks halda operator
    ekranda «Dünya iqtisadiyyatı · 050401» görüb «050401» yazanda SIFIR nəticə
    alır. ``program_code`` annotasiyası üzərindən süzmək əvəzinə ``Exists``
    işlədilir: annotasiya ``Coalesce(NullIf(Subquery…))``-dur və onu ``WHERE``-ə
    salmaq korrelyasiyalı alt sorğunu token başına TƏKRARLAYARDI.
    """

    def matcher(token):
        return Exists(
            records.filter(student=OuterRef("pk")).filter(
                Q(program__name__icontains=token) | program_code_search_q(token, prefix="program__")
            )
        )

    return matcher


def _apply_filters(queryset, actor, filters, *, records=None):
    organization = actor.organization

    search = people_filters.search_q(
        filters.query,
        prefix="",
        extra=_program_search_matcher(records) if records is not None else None,
    )
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
        from apps.registrar.models import Enrollment

        enrollments = Enrollment.objects.filter(organization=organization, student=OuterRef("pk"))
        if filters.subject:
            enrollments = enrollments.filter(offering__subject_id=filters.subject)
        if filters.year:
            enrollments = enrollments.filter(offering__period__academic_year=filters.year)
        if filters.season:
            enrollments = enrollments.filter(offering__period__name=filters.season)
        queryset = queryset.filter(Exists(enrollments))

    return queryset


def filtered_students_qs(*, actor, filters, request=None):
    """Cədvəlin GÖRDÜYÜ dəqiq dəst (müəllim kataloqu ilə eyni müqavilə).

    Analitika bunu çağırır — göstəricilər həmişə cari filtr dəstinə aiddir.
    """
    # Scope BİR dəfə hesablanır və hər iki istehlakçıya ötürülür (sorğu büdcəsi).
    records = scoped_student_records(actor, request=request, filters=filters)
    queryset = visible_students_qs(actor, request=request, filters=filters, records=records)
    return _apply_filters(queryset, actor, filters, records=records)


def build_students_page(*, actor, filters, request=None, today=None) -> dict:
    """Səhifələnmiş tələbə cədvəli — müəllim cədvəli ilə EYNİ zərf strukturu."""
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
    if not actor.can_view_students or actor.organization is None:
        return empty

    queryset = filtered_students_qs(actor=actor, filters=filters, request=request)
    queryset = queryset.order_by(*STUDENT_SORT_OPTIONS.get(filters.sort, STUDENT_SORT_OPTIONS["name"]))

    page_size = filters.page_size or DEFAULT_PAGE_SIZE
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(filters.page)
    users = list(page_obj.object_list)

    ancestors = _ancestors_for(users, organization=actor.organization)

    results = []
    for user in users:
        row = identity_row(user, actor=actor, today=today)
        unit = ancestors.get(getattr(user, "group_id", None), {})
        program_code = getattr(user, "program_code", "") or ""
        program_name = getattr(user, "program_name", "") or ""
        row.update(
            {
                "kind": "student",
                "group_name": getattr(user, "group_name", "") or "",
                "program_name": program_name,
                # Etiket ƏL İLƏ birləşdirilmir — ``Program.display_label`` ilə eyni
                # saf qayda (``program_code`` annotasiyası onsuz da köhnə şifrə
                # geri çəkilmiş TƏK şifrdir).
                "program_label": program_display_label(program_name, program_code),
                "admission_year": getattr(user, "admission_year", None),
                "academic_status": getattr(user, "academic_status", "") or "",
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
    """Səhifədəki tələbələrin qrupları üçün fakültə/kafedra adları — 2 sorğu."""
    group_ids = {getattr(user, "group_id", None) for user in users}
    group_ids.discard(None)
    if not group_ids:
        return {}

    from apps.organizations.models import OrgUnit

    units = list(
        OrgUnit.objects.filter(organization=organization, pk__in=group_ids).only("id", "name", "path", "unit_type")
    )
    return resolve_unit_ancestors(units, organization=organization)


__all__ = [
    "RECORD_PICK_ORDER",
    "build_students_page",
    "filtered_students_qs",
    "scoped_student_records",
    "student_records_qs",
    "visible_students_qs",
]
