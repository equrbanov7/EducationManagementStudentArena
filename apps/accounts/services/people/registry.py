"""Tələbə reyestri — ekran 09-un OXU sorğusu (server filtr/sıralama/səhifələmə).

NİYƏ ``students.py``-dan AYRI SORĞU?
``students.py`` ``User`` bazalıdır (kataloq: «kim var»); reyestr isə
``StudentAcademicRecord`` bazalıdır — sətir = BİR QƏBUL (ixtisas + qəbul ili +
forma + maliyyələşmə + status). İki ixtisasa yazılmış tələbə kataloqda BİR,
reyestrdə İKİ sətirdir və bu QƏSDƏNDİR: əmr də konkret qeydə yazılır.

TƏKRAR İSTİFADƏ (dublikat sorğu yazılmır):

* scope       → :func:`.movements.registry_records_qs` (`student.registry_view`)
* axtarış Q   → :func:`.filters.search_q` (kataloqla EYNİ sahə dəsti)
* struktur ad → :func:`.rows.resolve_unit_ancestors` (tək toplu sorğu, N+1 yox)
* ixtisas şifr→ ``core.program_codes.program_display_label``
* kurs/status → ``.academic`` (etiket və kurs qaydası orada TƏK yerdədir)

⚠️ GPA və «borc, fənn» sütunları SİYAHIDA YOXDUR. Onların hesablanması
``registrar.transcript.build_student_transcript``-dir və HƏR SƏTİR üçün ayrıca
semestr aqreqatı tələb edir (25 sətirlik səhifə = 25 transkript qurulması).
Handoff §8/13 «aqreqasiya yalnız aşağıdan yuxarı; yekun rəqəm SAXLANILMIR»
qaydası denormalizasiyanı da qadağan edir, ona görə GPA yalnız DRAWER-də
(bir tələbə üçün) göstərilir.
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.db.models import Count, Q

from core.program_codes import program_display_label

from . import filters as people_filters
from .academic import STATUS_LABELS, STATUS_TONES, _course_label, _current_period
from .constants import DEFAULT_PAGE_SIZE
from .movements import registry_records_qs
from .permissions import PERM_REGISTRY_VIEW
from .rows import full_name_of, initials_of, resolve_unit_ancestors

#: Sıralama allowlist-i — xam GET sahə adı DB-yə düşmür.
REGISTRY_SORT_OPTIONS = {
    "name": ("student__last_name", "student__first_name"),
    "-name": ("-student__last_name", "-student__first_name"),
    "year": ("admission_year", "student__last_name"),
    "-year": ("-admission_year", "student__last_name"),
    "group": ("group__name", "student__last_name"),
    "-group": ("-group__name", "student__last_name"),
    "program": ("program__name", "student__last_name"),
    "-program": ("-program__name", "student__last_name"),
    "status": ("status", "student__last_name"),
    "-status": ("-status", "student__last_name"),
}

#: «Xüsusi statuslu» = qeydiyyatlıdan FƏRQLİ hər status.
SPECIAL_STATUSES = ("academic_leave", "expelled", "graduated")

MAX_PAGE_SIZE = 100


#: Filtr sözlüyünün TAM açar dəsti — `_apply_filters` heç vaxt `KeyError` almır.
FILTER_DEFAULTS = {
    "search": "",
    "faculty": "",
    "program": "",
    "group": "",
    "year": "",
    "sector": "",
    "form": "",
    "funding": "",
    "status": "",
    "sort": "name",
    "page": 1,
}


def normalize_values(values=None, request=None) -> dict:
    """Filtr sözlüyünü tamamlayır (çağıran natamam dict verə bilər)."""
    merged = dict(FILTER_DEFAULTS)
    if values is None and request is not None:
        values = parse_registry_filters(request)
    merged.update({key: value for key, value in (values or {}).items() if key in merged})
    return merged


def parse_registry_filters(request) -> dict:
    """GET-i normallaşdırır — `sr_` ad fəzası (filtr paneli ilə eyni prefiks)."""

    def _get(name, default=""):
        return (request.GET.get(f"sr_{name}") or default).strip()

    try:
        page = max(1, int(request.GET.get("sr_page") or 1))
    except (TypeError, ValueError):
        page = 1
    sort = _get("sort", "name")
    return {
        "search": _get("q")[: people_filters.MAX_QUERY_LENGTH],
        "faculty": _get("faculty"),
        "program": _get("program"),
        "group": _get("group"),
        "year": _get("year"),
        "sector": _get("sector"),
        "form": _get("form"),
        "funding": _get("funding"),
        "status": _get("status"),
        "sort": sort if sort in REGISTRY_SORT_OPTIONS else "name",
        "page": page,
    }


def _apply_filters(records, values, *, organization):
    search = people_filters.search_q(values["search"], prefix="student__")
    if search:
        records = records.filter(
            search
            | Q(student__profile__institutional_identifier__icontains=values["search"])
            | Q(atis_id__icontains=values["search"])
        )
    if values["program"]:
        records = records.filter(program_id=values["program"])
    if values["group"]:
        records = records.filter(group_id=values["group"])
    if values["faculty"]:
        # Materiallaşdırılmış yol: fakültənin bütün alt ağacı. Qrupun `path`-i
        # «kök/…/qrupun özü» olduğu üçün fakültə ya BAŞDA, ya da ORTADADIR.
        faculty_id = values["faculty"]
        records = records.filter(
            Q(group__path__startswith=f"{faculty_id}/") | Q(group__path__contains=f"/{faculty_id}/")
        )
    if values["year"]:
        try:
            records = records.filter(admission_year=int(values["year"]))
        except (TypeError, ValueError):
            pass
    if values["form"]:
        records = records.filter(education_form=values["form"])
    if values["funding"]:
        records = records.filter(funding_type=values["funding"])
    if values["status"]:
        records = records.filter(status=values["status"])
    if values["sector"]:
        # Sektor `OrgUnit.settings` JSON-undadır (tenant-konfiqurasiya olunan) —
        # DB-də indeks yoxdur, ona görə uyğun qrup id-ləri BİR sorğu ilə
        # Python-da seçilir və `IN` olaraq tətbiq olunur.
        from ..student_groups import normalize_sector

        records = records.filter(group_id__in=_sector_group_ids(organization, normalize_sector(values["sector"])))
    return records


def _sector_group_ids(organization, wanted: str) -> list:
    """Sektoru uyğun gələn qrupların id-ləri (JSON sahəsi filtrlənmir — Python)."""
    from apps.organizations.models import OrgUnit
    from core.constants import OrgUnitType

    from ..student_groups import normalize_sector

    units = OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP, is_active=True).values(
        "id", "settings"
    )
    return [
        str(unit["id"]) for unit in units if normalize_sector((unit["settings"] or {}).get("language_sector")) == wanted
    ]


def _row(record, *, ancestors, period, movement_counts) -> dict:
    student = record.student
    unit = ancestors.get(str(record.group_id), {}) if record.group_id else {}
    group = record.group
    sector = str((getattr(group, "settings", None) or {}).get("language_sector") or "") if group else ""
    return {
        "record_id": str(record.pk),
        "user_id": student.pk,
        "initials": initials_of(student),
        "name": full_name_of(student),
        "student_code": str(getattr(getattr(student, "profile", None), "institutional_identifier", "") or ""),
        "fin": str(getattr(getattr(student, "profile", None), "fin", "") or ""),
        "program_label": program_display_label(record.program.name, record.program.display_code),
        "group_name": str(getattr(group, "name", "") or ""),
        "sector": sector,
        "faculty_name": unit.get("faculty", ""),
        "kafedra_name": unit.get("kafedra", ""),
        "course_label": _course_label(record.admission_year, period),
        "admission_year": record.admission_year,
        "form_label": str(record.get_education_form_display()),
        "funding_label": str(record.get_funding_type_display()),
        "status": record.status,
        "status_label": str(STATUS_LABELS.get(record.status, record.status)),
        "status_tone": STATUS_TONES.get(record.status, "info"),
        "movement_count": movement_counts.get(str(record.pk), 0),
        "admission_score": str(record.admission_score) if record.admission_score is not None else "",
    }


def build_registry_page(*, actor, request=None, values=None, page_size: int = DEFAULT_PAGE_SIZE) -> dict:
    """Reyestr səhifəsi — cədvəl sətirləri + KPI + filtr vəziyyəti."""
    empty = {
        "has_access": False,
        "rows": [],
        "page": 1,
        "num_pages": 1,
        "total": 0,
        "kpis": {},
        "filters": values or {},
        "has_scope": False,
    }
    if not actor.can_view_registry or actor.organization is None:
        return empty

    records = registry_records_qs(actor, request=request)
    # §8/8 — «əhatə yoxdur ≠ bütün universitet». Açarı olan, amma `scope_unit`
    # təyin edilməmiş UNIT rolu BOŞ dəst alır; UI bunu adi «nəticə yoxdur»dan
    # FƏRQLİ mesajla göstərməlidir (administrator kanalı).
    has_scope = actor.scope_for(PERM_REGISTRY_VIEW, request=request).has_structure_access
    values = normalize_values(values, request)
    records = _apply_filters(records, values, organization=actor.organization)

    kpis = _kpis(records)

    records = records.select_related("student", "student__profile", "program", "group").order_by(
        *REGISTRY_SORT_OPTIONS.get(values.get("sort", "name"), REGISTRY_SORT_OPTIONS["name"])
    )
    paginator = Paginator(records, min(max(page_size, 1), MAX_PAGE_SIZE))
    page_obj = paginator.get_page(values.get("page", 1))
    page_records = list(page_obj.object_list)

    ancestors = _ancestors_for(page_records, organization=actor.organization)
    period = _current_period(actor.organization)
    movement_counts = _movement_counts(actor.organization, page_records)

    return {
        "has_access": True,
        "rows": [
            _row(record, ancestors=ancestors, period=period, movement_counts=movement_counts) for record in page_records
        ],
        # `page_obj` şablona OLDUĞU KİMİ ötürülür — `partials/_pagination.html`
        # Django Page müqaviləsini gözləyir (yeni pager yazılmır).
        "page_obj": page_obj,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "total": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "kpis": kpis,
        "filters": values,
        "has_scope": bool(has_scope),
    }


def _kpis(records) -> dict:
    """Aqreqatlar — HƏR BİRİ hesablanır, heç biri SAXLANILMIR (§8/13)."""
    from apps.registrar.models import AcademicStatus

    totals = records.aggregate(
        total=Count("id"),
        full_time=Count("id", filter=Q(education_form="full_time")),
        part_time=Count("id", filter=Q(education_form="part_time")),
        special=Count("id", filter=Q(status__in=SPECIAL_STATUSES)),
        state_funded=Count("id", filter=Q(funding_type="state")),
        enrolled=Count("id", filter=Q(status=AcademicStatus.ENROLLED)),
    )
    return {key: value or 0 for key, value in totals.items()}


def _movement_counts(organization, records) -> dict:
    """Səhifədəki qeydlərin əmr sayı — BİR sorğu."""
    from apps.registrar.models import StudentMovement

    ids = [record.pk for record in records]
    if not ids:
        return {}
    rows = (
        StudentMovement.objects.filter(organization=organization, record_id__in=ids)
        .values("record_id")
        .annotate(total=Count("id"))
    )
    return {str(row["record_id"]): row["total"] for row in rows}


def _ancestors_for(records, *, organization):
    from apps.organizations.models import OrgUnit

    group_ids = {record.group_id for record in records if record.group_id}
    if not group_ids:
        return {}
    units = list(
        OrgUnit.objects.filter(organization=organization, pk__in=list(group_ids)).only(
            "id", "name", "path", "unit_type"
        )
    )
    return {str(key): value for key, value in resolve_unit_ancestors(units, organization=organization).items()}


#: Seçicilərin yuxarı həddi — 8 000 tələbəli tenantda qrup sayı böyükdür,
#: amma açılan siyahı sonsuz uzana bilməz (axtarışlı select onu süzür).
OPTION_LIMIT = 500


def registry_options(actor, *, request=None) -> dict:
    """Filtr açılışları — REYESTRİN ÖZ dəstindən (kataloq lookup-u çağırılmır).

    ``lookups.build_filter_options`` QƏSDƏN işlədilmir: o, ``User`` bazalı
    kataloq üçündür və `people.view_students` tələb edir — reyestrin qapısı isə
    `student.registry_view`-dur. Burada seçimlər aktorun REYESTR dəstindən
    törəyir, yəni «görmədiyim qrup seçicidə görünmür» (§8/8).
    """
    if not actor.can_view_registry or actor.organization is None:
        return {"programs": [], "groups": [], "years": [], "faculties": [], "sectors": []}

    records = registry_records_qs(actor, request=request)
    programs = [
        {"value": str(row["program_id"]), "label": row["program__name"]}
        for row in records.values("program_id", "program__name").distinct().order_by("program__name")[:OPTION_LIMIT]
    ]
    groups = [
        {"value": str(row["group_id"]), "label": row["group__name"]}
        for row in records.exclude(group__isnull=True)
        .values("group_id", "group__name")
        .distinct()
        .order_by("group__name")[:OPTION_LIMIT]
    ]
    years = [
        {"value": str(row["admission_year"]), "label": str(row["admission_year"])}
        for row in records.values("admission_year").distinct().order_by("-admission_year")[:OPTION_LIMIT]
        if row["admission_year"]
    ]
    return {
        "programs": programs,
        "groups": groups,
        "years": years,
        "faculties": _faculty_options(actor.organization),
        "sectors": _sector_options(actor.organization),
    }


def _faculty_options(organization) -> list:
    from apps.organizations.models import OrgUnit

    from .constants import FACULTY_UNIT_TYPES

    return [
        {"value": str(unit.pk), "label": unit.name}
        for unit in OrgUnit.objects.filter(
            organization=organization, unit_type__in=list(FACULTY_UNIT_TYPES), is_active=True
        ).order_by("name")[:OPTION_LIMIT]
    ]


def _sector_options(organization) -> list:
    from apps.organizations.models import OrgUnit
    from core.constants import OrgUnitType

    from ..student_groups import normalize_sector

    seen: dict = {}
    for unit in OrgUnit.objects.filter(organization=organization, unit_type=OrgUnitType.GROUP, is_active=True).values(
        "settings"
    ):
        raw = str((unit["settings"] or {}).get("language_sector") or "").strip()
        if not raw:
            continue
        seen.setdefault(normalize_sector(raw), raw)
    return [{"value": key, "label": label} for key, label in sorted(seen.items())]


def export_rows(*, actor, request=None, values=None, limit: int = 10000):
    """CSV ixracının sətirləri — səhifələnmir, LİMİTLİDİR (yaddaş qapısı)."""
    if not actor.can_view_registry or actor.organization is None:
        return []
    records = registry_records_qs(actor, request=request)
    values = normalize_values(values, request)
    records = _apply_filters(records, values, organization=actor.organization)
    records = records.select_related("student", "student__profile", "program", "group").order_by(
        *REGISTRY_SORT_OPTIONS.get(values.get("sort", "name"), REGISTRY_SORT_OPTIONS["name"])
    )[:limit]
    page_records = list(records)
    ancestors = _ancestors_for(page_records, organization=actor.organization)
    period = _current_period(actor.organization)
    return [_row(record, ancestors=ancestors, period=period, movement_counts={}) for record in page_records]


__all__ = [
    "FILTER_DEFAULTS",
    "MAX_PAGE_SIZE",
    "REGISTRY_SORT_OPTIONS",
    "SPECIAL_STATUSES",
    "build_registry_page",
    "export_rows",
    "registry_options",
    "normalize_values",
    "parse_registry_filters",
]
