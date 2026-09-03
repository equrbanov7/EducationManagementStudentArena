"""«Müəllim — Sillabuslar» bölməsinin CONTEXT MÜQAVİLƏSİ (dizayn təhvili §3.1).

Ekran profil shell-inin İÇİNDƏ açılır — SOL SIDEBAR QALIR (``SECTION_PARTIALS``
arxitekturası); ayrıca tam-səhifə səth DEYİL.

Cross-domain qlue məhz burada saxlanılır: ``apps.syllabus`` (dosye/versiya) +
``apps.registrar`` (açılış/fənn) + ``apps.organizations`` (semestr/struktur).
Sillabus modulu bu üç tərəfin heç birini import etmir — beləliklə modul-sərhəd
qrafında yeni dövr yaranmır (bax ``scripts/module_deps.py``).

──────────────────────────────────────────────────────────────────────────────
CONTEXT MÜQAVİLƏSİ — ``syllabus_list_section`` (dict)
──────────────────────────────────────────────────────────────────────────────
    has_access      bool                — False → «icazə yoxdur» boş vəziyyəti
    can_create      bool                — `syllabus.edit` açarı var
    kpis            [{key,label,value,note,tone,active}]      — 5 kart
    chips           [{key,label,count,active}]                — «Hamısı» + 7 status
    rows            [row]               — bax :mod:`.rows`
    filters         {q,year,semester,unit,status,sort,view}
    filter_options  {years,semesters,units,sorts}
    page            {number,count,total,start,end,has_prev,has_next,numbers}
    urls            {list,action,preview,editor,section}
    empty           bool
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.syllabus.constants import QUEUE_STATUSES, STATUS_SORT_INDEX, SyllabusStatus
from apps.syllabus.policy import sla_days
from apps.syllabus.public import build_syllabus_list_context

from .labels import STATUS_TONES
from .rows import build_missing_row, build_row

_CTX = "accounts.syllabus"

#: Cədvəl səhifəsində sətir sayı (dizayndakı mock 6 sətirlik nümunə data ilə
#: səhifələməni göstərirdi; real siyahı üçün 10 seçilib).
PAGE_SIZE = 10

#: `reverse(...)` üçün sıfır UUID — JS şablon URL-də bunu real id ilə əvəzləyir.
_URL_PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000"

ACCESS_DENIED = pgettext_lazy(_CTX, "Bu bölmə üçün icazəniz yoxdur.")

SORT_LABELS = {
    "recent": pgettext_lazy(_CTX, "Son dəyişikliyə görə"),
    "subject": pgettext_lazy(_CTX, "Fənn adına görə"),
    "completion": pgettext_lazy(_CTX, "Tamamlanma faizinə görə"),
    "status": pgettext_lazy(_CTX, "Statusa görə"),
}

_KPI_LABELS = {
    "total": (pgettext_lazy(_CTX, "Cari il üzrə fənn"), pgettext_lazy(_CTX, "seçilmiş tədris ili")),
    "approved": (pgettext_lazy(_CTX, "Təsdiqlənib"), pgettext_lazy(_CTX, "jurnal açıla bilər")),
    "pending": (pgettext_lazy(_CTX, "Təsdiq gözləyir"), pgettext_lazy(_CTX, "kafedra növbəsində")),
    "revision": (pgettext_lazy(_CTX, "Düzəliş tələb olunur"), pgettext_lazy(_CTX, "sizdən əməl gözlənilir")),
    "missing": (pgettext_lazy(_CTX, "Sillabussuz fənn"), pgettext_lazy(_CTX, "semestr başına qədər tələb olunur")),
    "sla": (pgettext_lazy(_CTX, "SLA-nı keçib"), pgettext_lazy(_CTX, "%(days)s gündən çox kafedra növbəsindədir")),
}

#: Domen sorğusuna ÖTÜRÜLMƏYƏN, siyahı qatında hesablanan filtr açarları.
#: («missing» — sillabusu olmayan açılış; «sla» — SLA-nı keçmiş təqdimat.)
VIRTUAL_STATUS_KEYS = ("missing", "sla")

ALL_CHIP = pgettext_lazy(_CTX, "Hamısı")


def _text(request, key: str, default: str = "") -> str:
    return (request.GET.get(key) or default).strip()


def _missing_rows(*, organization, user, syllabi, academic_year: str, semester: str, search: str, copyable):
    """Müəllimin sillabusu OLMAYAN açılışları — «Sillabus yarat» sətirləri."""
    from apps.registrar.models import CourseOffering

    covered_offerings = {row.offering_id for row in syllabi if row.offering_id}
    covered_pairs = {(row.subject_id, row.period_id) for row in syllabi}

    queryset = (
        CourseOffering.objects.filter(organization=organization, is_active=True, instructor=user)
        .select_related("subject", "period")
        .order_by("subject__code")
    )
    if academic_year:
        queryset = queryset.filter(period__academic_year=academic_year)
    if semester:
        queryset = queryset.filter(period__name=semester)
    if search:
        queryset = queryset.filter(Q(subject__name__icontains=search) | Q(subject__code__icontains=search))

    rows = []
    for offering in queryset:
        if offering.pk in covered_offerings:
            continue
        if (offering.subject_id, offering.period_id) in covered_pairs:
            continue
        rows.append(build_missing_row(offering, can_copy=offering.subject_id in copyable))
    return rows


def _copyable_subjects(syllabi) -> set:
    """Keçmiş (təsdiqlənmiş/arxivlənmiş) versiyası olan fənlər — «köçür» mənbəyi."""
    done = {SyllabusStatus.APPROVED.value, SyllabusStatus.ARCHIVED.value}
    return {
        row.subject_id
        for row in syllabi
        if row.approved_version_id or (row.current_version is not None and row.current_version.status in done)
    }


def _chair_units(syllabi):
    """Görünən sillabusların kafedraları — filtr açılışı üçün (təkrarsız)."""
    seen, rows = set(), []
    for row in syllabi:
        unit = row.chair_unit if row.chair_unit_id else None
        if unit is None or unit.pk in seen:
            continue
        seen.add(unit.pk)
        rows.append({"key": str(unit.pk), "label": unit.name})
    return sorted(rows, key=lambda item: item["label"])


def academic_filter_options(organization):
    """(illər, semestrlər) — siyahı və təsdiq ekranı EYNİ açılışı işlədir."""
    from apps.organizations.models import AcademicPeriod

    periods = list(
        AcademicPeriod.objects.filter(organization=organization, is_active=True).order_by("-start_date")[:40]
    )
    years, seen_years = [], set()
    seasons, seen_seasons = [], set()
    for period in periods:
        if period.academic_year not in seen_years:
            seen_years.add(period.academic_year)
            years.append({"key": period.academic_year, "label": period.year_display})
        if period.name not in seen_seasons:
            seen_seasons.add(period.name)
            seasons.append({"key": period.name, "label": period.name})
    return years, seasons


def _chips(counts, missing_count: int, active: str):
    chips = [
        {
            "key": "",
            "label": ALL_CHIP,
            "count": counts.get("total", 0) + missing_count,
            "active": not active,
            "tone": "neutral",
        }
    ]
    for status in sorted(SyllabusStatus, key=lambda item: STATUS_SORT_INDEX[item.value]):
        chips.append(
            {
                "key": status.value,
                "label": status.label,
                "count": counts.get(status.value, 0),
                "active": active == status.value,
                "tone": STATUS_TONES[status.value],
            }
        )
    return chips


def overdue_syllabus_ids(syllabi, *, now, sla: int) -> set:
    """Kafedra növbəsində SLA həddini aşmış dosyelərin id-ləri (README §10.4).

    Hədd SİYASƏTDƏN gəlir — kodda gün rəqəmi yoxdur.
    """
    overdue = set()
    for row in syllabi:
        version = row.current_version
        if version is None or version.status not in QUEUE_STATUSES or version.submitted_at is None:
            continue
        if (now - version.submitted_at).days > sla:
            overdue.add(row.pk)
    return overdue


def _kpis(counts, missing_count: int, active: str, *, overdue_count: int = 0, sla: int = 0):
    def card(key, value, tone, chip):
        label, note = _KPI_LABELS[key]
        if key == "sla":
            note = str(note) % {"days": sla}
        return {
            "key": key,
            "label": label,
            "note": note,
            "value": value,
            "tone": tone,
            "chip": chip,
            "active": active == chip,
        }

    pending = counts.get(SyllabusStatus.SUBMITTED.value, 0) + counts.get(SyllabusStatus.REVIEW.value, 0)
    return [
        card("total", counts.get("total", 0) + missing_count, "neutral", ""),
        card("approved", counts.get(SyllabusStatus.APPROVED.value, 0), "success", SyllabusStatus.APPROVED.value),
        card("pending", pending, "primary", SyllabusStatus.SUBMITTED.value),
        card("revision", counts.get(SyllabusStatus.REVISION.value, 0), "warning", SyllabusStatus.REVISION.value),
        card("missing", missing_count, "danger", "missing"),
        card("sla", overdue_count, "warning", "sla"),
    ]


def _page_numbers(page):
    total = page.paginator.num_pages
    current = page.number
    window = {1, total, current, current - 1, current + 1}
    return [number for number in sorted(window) if 1 <= number <= total]


def build_syllabus_list_section(request, *, organization) -> dict:
    """«Sillabuslar» bölməsinin context-i (profil shell-i içində)."""
    if organization is None:
        return {"syllabus_list_section": {"has_access": False, "access_denied_message": ACCESS_DENIED, "rows": []}}

    search = _text(request, "q")
    academic_year = _text(request, "year")
    semester = _text(request, "semester")
    status = _text(request, "status")
    sort = _text(request, "sort", "recent")
    view_mode = "card" if _text(request, "view") == "card" else "table"

    unit = _text(request, "unit")

    context = build_syllabus_list_context(
        request,
        organization=organization,
        academic_year=academic_year or None,
        # «sla» REAL status deyil — sorğuya ötürülsə heç nə uyğun gəlməzdi;
        # süzgəc aşağıda, gözləmə müddəti hesablandıqdan sonra tətbiq olunur.
        statuses=[status] if status and status != "sla" else None,
        search=search,
        sort=sort if sort in SORT_LABELS else "recent",
    )
    # `chair_unit` domen sorğusunun `select_related`-ında yoxdur (siyahı ona görə
    # ehtiyac duymur) — kafedra filtri üçün burada əlavə olunur ki, N+1 olmasın.
    syllabi = list(context["syllabi"].select_related("chair_unit"))
    # Kafedra siyahısı GÖRÜNƏN dəstdən çıxarılır — ayrıca struktur sorğusu
    # açmırıq ki, əhatəsiz istifadəçiyə bütün org-un kafedraları sızmasın.
    units = _chair_units(syllabi)
    if semester:
        syllabi = [row for row in syllabi if row.period_id and row.period.name == semester]
    if unit:
        syllabi = [row for row in syllabi if str(row.chair_unit_id) == unit]

    now = timezone.now()
    sla = sla_days(organization)
    overdue = overdue_syllabus_ids(syllabi, now=now, sla=sla)
    if status == "sla":
        syllabi = [row for row in syllabi if row.pk in overdue]
    copyable = _copyable_subjects(syllabi)
    rows = [build_row(row, now=now, can_copy=row.subject_id in copyable) for row in syllabi]

    missing = (
        _missing_rows(
            organization=organization,
            user=request.user,
            syllabi=list(context["syllabi"]),
            academic_year=academic_year,
            semester=semester,
            search=search,
            copyable=copyable,
        )
        if status in ("", "missing")
        else []
    )
    if status == "missing":
        rows = missing
    else:
        rows = missing + rows

    paginator = Paginator(rows, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page") or 1)
    years, seasons = academic_filter_options(organization)

    return {
        "syllabus_list_section": {
            "has_access": True,
            "access_denied_message": "",
            "can_create": context["can_create"],
            "kpis": _kpis(context["counts"], len(missing), status, overdue_count=len(overdue), sla=sla),
            "chips": _chips(context["counts"], len(missing), status),
            "rows": list(page.object_list),
            "filters": {
                "q": search,
                "year": academic_year,
                "semester": semester,
                "unit": unit,
                "status": status,
                "sort": sort,
                "view": view_mode,
            },
            "filter_options": {
                "years": years,
                "semesters": seasons,
                "units": units,
                "sorts": [{"key": key, "label": label} for key, label in SORT_LABELS.items()],
            },
            "page": {
                "number": page.number,
                "count": paginator.num_pages,
                "total": paginator.count,
                "start": page.start_index(),
                "end": page.end_index(),
                "has_prev": page.has_previous(),
                "has_next": page.has_next(),
                "numbers": _page_numbers(page),
            },
            "urls": {
                "action": reverse("accounts:syllabus_action"),
                # Şablon URL-i: JS «0…0» UUID-ini konkret dosye id-si ilə əvəzləyir.
                "preview": reverse("accounts:syllabus_preview", kwargs={"syllabus_id": _URL_PLACEHOLDER_UUID}),
            },
            "empty": not rows,
        }
    }


__all__ = [
    "ACCESS_DENIED",
    "PAGE_SIZE",
    "SORT_LABELS",
    "VIRTUAL_STATUS_KEYS",
    "academic_filter_options",
    "build_syllabus_list_section",
    "overdue_syllabus_ids",
]
