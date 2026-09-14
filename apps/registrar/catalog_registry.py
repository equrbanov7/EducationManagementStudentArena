"""Akademik kataloq REYESTRLƏRİ — ekran 03 «İxtisaslar» + ekran 04 «Fənn kataloqu».

OXU tərəfi (yazı tərəfi: :mod:`apps.registrar.catalog_actions`).

QAYDALAR (dizayn handoff §8):
* filtr semantikası — `applied` state SERVER sorğusuna çevrilir; sıralama və
  səhifələmə də server tərəfdədir (qayda 14). Draft filtr sorğu göndərmir;
  bunu ``static/js/ems_ui/filter_bar.js`` təmin edir.
* silmə yoxdur — arxivləmə var (qayda 5): reyestr default olaraq YALNIZ aktiv
  yazıları göstərir, `arch=1` filtri arxivi açır.
* aqreqasiya aşağıdan yuxarı (qayda 13): «Plan yoxdur» bayrağı, «Planlarda
  istifadə» sayğacı və dublikat xəbərdarlığı SAXLANILMIR — hər sorğuda
  hesablanır.

İCAZƏ: ``catalog.view`` (oxu) / ``catalog.manage`` (yazı). Qapı ROL ADINA
baxmır — açar permission-editordan istənilən rola verilə bilər.

MODUL SƏRHƏDİ: bu modul ``apps.organizations``-ı STATİK import ETMİR
(``scripts/module_deps.py``) — OrgUnit-ə string-ref FK və ``django_apps.get_model``
ilə çıxılır.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils.translation import pgettext

from core.permissions import has_permission

from .models import Curriculum, CurriculumSubject, Program, Subject
from .models.academic import DegreeLevel
from .models.catalog_meta import EducationForm, SubjectKind

_CTX = "accounts.catalog"

PERM_VIEW = "catalog.view"
PERM_MANAGE = "catalog.manage"

PAGE_SIZE = 25

#: Sıralama açarı → ORM sahələri. Naməlum açar default-a düşür (fail-safe).
PROGRAM_SORTS: dict[str, tuple[str, ...]] = {
    "name": ("name",),
    "-name": ("-name",),
    "code": ("official_code", "name"),
    "-code": ("-official_code", "-name"),
    "degree": ("degree_level", "name"),
    "-degree": ("-degree_level", "-name"),
}
SUBJECT_SORTS: dict[str, tuple[str, ...]] = {
    "code": ("code",),
    "-code": ("-code",),
    "name": ("name", "code"),
    "-name": ("-name", "-code"),
    "ects": ("ects", "code"),
    "-ects": ("-ects", "-code"),
    "usage": ("plan_usage", "code"),
    "-usage": ("-plan_usage", "-code"),
}


def actor_permissions(request) -> list:
    return list(getattr(request, "org_permissions", []) or [])


def can_view_catalog(request) -> bool:
    return has_permission(actor_permissions(request), PERM_VIEW)


def can_manage_catalog(request) -> bool:
    return has_permission(actor_permissions(request), PERM_MANAGE)


def _org_unit_model():
    return django_apps.get_model("organizations", "OrgUnit")


def chair_options(organization) -> list:
    """Kafedra seçicisi — `chair` və `department` tipli aktiv vahidlər."""
    OrgUnit = _org_unit_model()
    return [
        {"value": str(unit.id), "label": unit.name}
        for unit in OrgUnit.objects.filter(
            organization=organization, is_active=True, unit_type__in=("chair", "department")
        ).order_by("name")
    ]


def _chair_and_faculty(unit):
    """İxtisas vahidindən (specialty) kafedra və fakültə adlarını çıxarır."""
    chair = getattr(unit, "parent", None)
    faculty = getattr(chair, "parent", None) if chair is not None else None
    return (getattr(chair, "name", "") or "", getattr(faculty, "name", "") or "")


def _clean_sort(value, table):
    return value if value in table else next(iter(table))


# --------------------------------------------------------------------------- #
# Ekran 03 — İxtisaslar
# --------------------------------------------------------------------------- #


def _group_counts_for_units(organization, units) -> dict:
    """Səhifədəki ixtisasların AKTİV qrup sayı — TƏK aqreqat sorğu.

    Audit 2026-09-10 P1-8 (düzəliş 2026-09-12): əvvəl hər ixtisas üçün ayrıca
    ``COUNT`` atılırdı (25-lik səhifə = 25 əlavə sorğu) və yollar üçün də
    əlavə ``SELECT`` gedirdi — halbuki ixtisas vahidi ``select_related`` ilə
    onsuz da yüklüdür. ``OrgUnit.path`` materiallaşdırılmış yoldur
    (``<ata-yol>/<id>``): «ixtisasın altındakı bütün qruplar» = ``path``
    prefiksi, ona görə dərin yuvalanmış qrup (ixtisas → bölmə → qrup) da
    sayılır. Bütün prefikslər bir ``WHERE``-də (OR) + hər ixtisas üçün şərti
    ``Count(filter=…)`` — nəticə səhifə ölçüsündən asılı olmayaraq 1 sorğudur.

    Qaytarır: ``{ixtisas_id(str): say}``; bu təşkilata aid olmayan / yolsuz
    vahid siyahıya düşmür (çağıran ``.get(…, 0)`` ilə oxuyur).
    """
    paths = {
        str(unit.id): unit.path
        for unit in units
        if unit is not None and unit.path and unit.organization_id == organization.id
    }
    if not paths:
        return {}
    scope = Q()
    aggregates = {}
    for index, path in enumerate(paths.values()):
        prefix = Q(path__startswith=f"{path}/")
        scope |= prefix
        aggregates[f"n{index}"] = Count("id", filter=prefix)
    totals = (
        _org_unit_model()
        .objects.filter(organization=organization, is_active=True, unit_type="group")
        .filter(scope)
        .aggregate(**aggregates)
    )
    return {unit_id: int(totals[f"n{index}"] or 0) for index, unit_id in enumerate(paths)}


def build_programs_registry(request, organization) -> dict:
    """«İxtisaslar» reyestri: filtr + sıralama + səhifələmə (hamısı serverdə)."""
    if not can_view_catalog(request):
        return {
            "has_access": False,
            "access_denied_message": pgettext(
                _CTX, "Kataloqa baxış üçün səlahiyyətiniz yoxdur. Administratora müraciət edin."
            ),
        }

    search = (request.GET.get("pg_q") or "").strip()[:120]
    degree = (request.GET.get("pg_degree") or "").strip()
    form = (request.GET.get("pg_form") or "").strip()
    chair = (request.GET.get("pg_chair") or "").strip()
    only_no_plan = (request.GET.get("pg_noplan") or "") == "1"
    show_archived = (request.GET.get("pg_arch") or "") == "1"
    sort = _clean_sort((request.GET.get("pg_sort") or "").strip(), PROGRAM_SORTS)

    queryset = Program.objects.filter(organization=organization).select_related(
        "specialty_unit", "specialty_unit__parent", "specialty_unit__parent__parent"
    )
    total_count = queryset.count()
    queryset = queryset.filter(is_archived=show_archived) if show_archived else queryset.filter(is_archived=False)

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(official_code__icontains=search) | Q(legacy_official_code__icontains=search)
        )
    if degree in dict(DegreeLevel.choices):
        queryset = queryset.filter(degree_level=degree)
    if form in dict(EducationForm.choices):
        queryset = queryset.filter(education_form=form)
    if chair:
        queryset = queryset.filter(specialty_unit__parent_id=chair)

    # «Plan yoxdur» — TƏSDİQLƏNMİŞ plan anlayışı Mərhələ 2-də (`Curriculum.status`)
    # gəlir; Mərhələ 1-də meyar AKTİV planın mövcudluğudur. Saxlanılmır, hər
    # sorğuda hesablanır (handoff §8 qayda 13).
    planned_ids = set(
        Curriculum.objects.filter(organization=organization, is_active=True)
        .values_list("program_id", flat=True)
        .distinct()
    )
    if only_no_plan:
        queryset = queryset.exclude(pk__in=planned_ids)

    queryset = queryset.order_by(*PROGRAM_SORTS[sort])
    page_obj = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("pg_page"))

    # Qrup sayları: səhifənin bütün ixtisasları üçün BİR sorğu (P1-8).
    group_counts = _group_counts_for_units(
        organization, [program.specialty_unit for program in page_obj.object_list if program.specialty_unit_id]
    )

    rows = []
    for program in page_obj.object_list:
        chair_name, faculty_name = _chair_and_faculty(program.specialty_unit)
        rows.append(
            {
                "id": str(program.id),
                "official_code": program.official_code or "",
                "legacy_official_code": program.legacy_official_code or "",
                "name": program.name,
                "degree_label": program.get_degree_level_display(),
                "degree_level": program.degree_level,
                "education_form": program.education_form,
                "form_label": program.get_education_form_display(),
                "chair_name": chair_name,
                "faculty_name": faculty_name,
                "specialty_unit_id": str(program.specialty_unit_id) if program.specialty_unit_id else "",
                "group_count": group_counts.get(str(program.specialty_unit_id), 0),
                "ects_total": program.ects_total,
                "absence_limit_percent": program.absence_limit_percent,
                "has_plan": program.id in planned_ids,
                "is_archived": program.is_archived,
                "archived_reason": program.archived_reason,
                "status_key": "archived" if program.is_archived else ("open" if program.id in planned_ids else "open"),
            }
        )

    no_plan_total = (
        Program.objects.filter(organization=organization, is_archived=False).exclude(pk__in=planned_ids).count()
    )
    archived_total = Program.objects.filter(organization=organization, is_archived=True).count()

    return {
        "has_access": True,
        "rows": rows,
        "page_obj": page_obj,
        "table_state": "ready" if rows else "empty",
        "total_count": total_count,
        "filtered_count": page_obj.paginator.count,
        "no_plan_total": no_plan_total,
        "archived_total": archived_total,
        "filters": {
            "search": search,
            "degree": degree,
            "form": form,
            "chair": chair,
            "only_no_plan": only_no_plan,
            "show_archived": show_archived,
            "sort": sort,
        },
        "degree_options": [{"value": value, "label": str(label)} for value, label in DegreeLevel.choices],
        "form_options": [{"value": value, "label": str(label)} for value, label in EducationForm.choices],
        "chair_options": chair_options(organization),
        "can_manage": can_manage_catalog(request),
    }


# --------------------------------------------------------------------------- #
# Ekran 04 — Fənn kataloqu
# --------------------------------------------------------------------------- #


def _normalized_subject_name(name) -> str:
    """Dublikat açarı: boşluqlar sıxılır, ``casefold`` (reqistrsiz)."""
    return " ".join((name or "").split()).casefold()


def subject_name_index(organization) -> tuple[dict, dict]:
    """Arxivlənməmiş fənn adları — TƏK ``GROUP BY name`` sorğusu ilə dublikat indeksi.

    Audit 2026-09-10 P1-8 (düzəliş 2026-09-12): əvvəl BÜTÜN fənn adları sətir-sətir
    Python-a çəkilirdi, ``sb_dup=1`` isə eyni cədvəli İKİNCİ dəfə tam skan edirdi.
    İndi DB xam ad üzrə qruplaşdırır (``values("name").annotate(Count("id"))`` —
    yalnız fərqli adlar gəlir), Python isə yalnız bu fərqli adları
    normallaşdırıb toplayır; süzgəc eyni nəticədəki xam variantları işlədir.

    Normallaşdırma QƏSDƏN Python-da qalır: SQL ``LOWER`` Azərbaycan «İ/I»
    hərflərini eyniləşdirir və Unicode boşluqları (NBSP) sıxmır — DB tərəfinə
    köçürsək «AD DUBLİKATI» rəqəmi köhnə ilə fərqlənərdi.

    Qaytarır: ``(duplicates, variants)`` — ``duplicates``: normallaşdırılmış ad →
    say (yalnız >1); ``variants``: həmin açar → DB-dəki xam ad variantları.
    """
    counter: dict[str, int] = {}
    variants: dict[str, list] = {}
    grouped = (
        Subject.objects.filter(organization=organization, is_archived=False)
        .values("name")
        .annotate(n=Count("id"))
        .order_by()  # Meta.ordering (`code`) GROUP BY-a düşməsin
    )
    for item in grouped:
        key = _normalized_subject_name(item["name"])
        if not key:
            continue
        counter[key] = counter.get(key, 0) + int(item["n"] or 0)
        variants.setdefault(key, []).append(item["name"])
    duplicates = {key: value for key, value in counter.items() if value > 1}
    return duplicates, {key: variants[key] for key in duplicates}


def duplicate_subject_names(organization) -> dict:
    """Ad üzrə dublikatlar: normallaşdırılmış ad → say (yalnız >1).

    Post-migration auditində 9 ad dublikatı tapılıb; ekran onları xəbərdarlıq
    kimi göstərir. BİRLƏŞDİRMƏ (merge) Mərhələ 1-ə DAXİL DEYİL — destruktiv
    əməldir, plan sətirlərinin və sillabusların köçürülməsini tələb edir
    (bax hesabatdakı «təxirə salınanlar»).
    """
    return subject_name_index(organization)[0]


def build_subject_catalog(request, organization) -> dict:
    """«Fənn kataloqu» reyestri: filtr + sıralama + səhifələmə (hamısı serverdə)."""
    if not can_view_catalog(request):
        return {
            "has_access": False,
            "access_denied_message": pgettext(
                _CTX, "Kataloqa baxış üçün səlahiyyətiniz yoxdur. Administratora müraciət edin."
            ),
        }

    search = (request.GET.get("sb_q") or "").strip()[:120]
    chair = (request.GET.get("sb_chair") or "").strip()
    kind = (request.GET.get("sb_kind") or "").strip()
    only_duplicates = (request.GET.get("sb_dup") or "") == "1"
    show_archived = (request.GET.get("sb_arch") or "") == "1"
    sort = _clean_sort((request.GET.get("sb_sort") or "").strip(), SUBJECT_SORTS)

    # Sorğu başına BİR dəfə: həm KPI, həm sətir bayrağı, həm `sb_dup=1` süzgəci buradan.
    duplicates, duplicate_variants = subject_name_index(organization)

    queryset = Subject.objects.filter(organization=organization).select_related("chair_unit")
    total_count = queryset.count()
    queryset = queryset.filter(is_archived=show_archived) if show_archived else queryset.filter(is_archived=False)

    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))
    if chair:
        queryset = queryset.filter(chair_unit_id=chair)
    if kind in dict(SubjectKind.choices):
        queryset = queryset.filter(kind=kind)
    if only_duplicates:
        # Dublikat adlar azdır (onluqlarla) — `name__in` sorğusu təhlükəsizdir.
        # Xam variantlar eyni indeksdən gəlir: ikinci tam skan YOXDUR (P1-8).
        duplicate_names = [name for names in duplicate_variants.values() for name in names]
        queryset = queryset.filter(name__in=duplicate_names)

    queryset = queryset.annotate(plan_usage=Count("curriculum_rows", distinct=True))
    queryset = queryset.order_by(*SUBJECT_SORTS[sort])
    page_obj = Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("sb_page"))

    rows = []
    for subject in page_obj.object_list:
        name_key = _normalized_subject_name(subject.name)
        rows.append(
            {
                "id": str(subject.id),
                "code": subject.code,
                "name": subject.name,
                "ects": subject.ects,
                "kind": subject.kind,
                "kind_label": subject.get_kind_display(),
                "chair_name": subject.chair_unit.name if subject.chair_unit_id else "",
                "chair_id": str(subject.chair_unit_id) if subject.chair_unit_id else "",
                "plan_usage": getattr(subject, "plan_usage", 0),
                "is_duplicate": name_key in duplicates,
                "is_archived": subject.is_archived,
                "archived_reason": subject.archived_reason,
            }
        )

    archived_total = Subject.objects.filter(organization=organization, is_archived=True).count()
    in_use_total = CurriculumSubject.objects.filter(organization=organization).values("subject_id").distinct().count()

    return {
        "has_access": True,
        "rows": rows,
        "page_obj": page_obj,
        "table_state": "ready" if rows else "empty",
        "total_count": total_count,
        "filtered_count": page_obj.paginator.count,
        "duplicate_total": sum(duplicates.values()),
        "duplicate_name_total": len(duplicates),
        "archived_total": archived_total,
        "in_use_total": in_use_total,
        "filters": {
            "search": search,
            "chair": chair,
            "kind": kind,
            "only_duplicates": only_duplicates,
            "show_archived": show_archived,
            "sort": sort,
        },
        "kind_options": [{"value": value, "label": str(label)} for value, label in SubjectKind.choices],
        "chair_options": chair_options(organization),
        "can_manage": can_manage_catalog(request),
    }


__all__ = [
    "PERM_MANAGE",
    "PERM_VIEW",
    "build_programs_registry",
    "build_subject_catalog",
    "can_manage_catalog",
    "can_view_catalog",
    "chair_options",
    "duplicate_subject_names",
    "subject_name_index",
]
