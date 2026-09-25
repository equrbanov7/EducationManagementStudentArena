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

import datetime as _dt
import uuid

from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.syllabus.public import (
    QUEUE_STATUSES,
    STATUS_SORT_INDEX,
    SyllabusStatus,
    build_syllabus_list_context,
    sla_days,
)
from core.search_text import tolerant_q

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
    """Müəllimin sillabusu OLMAYAN açılışları — «Sillabus yarat» sətirləri.

    ``syllabi`` — görünən dəstin QUERYSET-i. Perf auditi 2026-09-13 F-12:
    əvvəl bütün dəst ikinci dəfə ``list()`` ilə Python-a çəkilirdi (rektorda
    4 926 sətir, 66 ms təkrar sorğu + disk sort); indi yalnız müəllimin
    açılışlarına dəyən ``(offering, subject, period)`` üçlükləri
    ``values_list`` ilə oxunur, açılış yoxdursa heç sorğu getmir.
    """
    from apps.registrar.models import CourseOffering

    queryset = (
        CourseOffering.objects.filter(organization=organization, is_active=True, instructor=user)
        .select_related("subject", "period")
        .order_by("subject__code")
    )
    if academic_year:
        queryset = queryset.filter(period__academic_year=academic_year)
    if semester:
        queryset = queryset.filter(period__name=semester)
    subject_q = tolerant_q(search, ("subject__name",), compact_fields=("subject__code",))
    if subject_q is not None:
        queryset = queryset.filter(subject_q)
    offerings = list(queryset)
    if not offerings:
        return []

    covered = (
        syllabi.order_by()
        .filter(
            Q(offering_id__in=[offering.pk for offering in offerings])
            | Q(subject_id__in={offering.subject_id for offering in offerings})
        )
        .values_list("offering_id", "subject_id", "period_id")
    )
    covered_offerings, covered_pairs = set(), set()
    for offering_id, subject_id, period_id in covered:
        if offering_id:
            covered_offerings.add(offering_id)
        covered_pairs.add((subject_id, period_id))

    rows = []
    for offering in offerings:
        if offering.pk in covered_offerings:
            continue
        if (offering.subject_id, offering.period_id) in covered_pairs:
            continue
        rows.append(build_missing_row(offering, can_copy=offering.subject_id in copyable))
    return rows


def _copyable_subjects(syllabi) -> set:
    """Keçmiş (təsdiqlənmiş/arxivlənmiş) versiyası olan fənlər — «köçür» mənbəyi.

    F-12: dəst QUERYSET-dir — yalnız uyğun ``subject_id``-lər oxunur
    (``values_list``), sətirlərin özü yox.
    """
    done = [SyllabusStatus.APPROVED.value, SyllabusStatus.ARCHIVED.value]
    return set(
        syllabi.order_by()
        .filter(Q(approved_version__isnull=False) | Q(current_version__status__in=done))
        .values_list("subject_id", flat=True)
        .distinct()
    )


def _chair_units(syllabi):
    """Görünən sillabusların kafedraları — filtr açılışı üçün (təkrarsız).

    F-12: ``values_list(..).distinct()`` — dəst Python-a gəlmir.
    """
    rows = [
        {"key": str(unit_id), "label": name}
        for unit_id, name in syllabi.order_by()
        .filter(chair_unit__isnull=False)
        .values_list("chair_unit_id", "chair_unit__name")
        .distinct()
    ]
    return sorted(rows, key=lambda item: item["label"])


def _overdue_filter(*, now, sla: int) -> Q:
    """`overdue_syllabus_ids` ilə EYNİ qayda, SQL-də.

    Python: ``(now - submitted_at).days > sla`` — ``timedelta.days`` aşağı
    yuvarlaqlaşdırır, yəni fərq ≥ (sla + 1) tam gün ⇔
    ``submitted_at <= now - (sla + 1) gün``.
    """
    cutoff = now - _dt.timedelta(days=sla + 1)
    return Q(current_version__status__in=sorted(QUEUE_STATUSES), current_version__submitted_at__lte=cutoff)


class _MissingThenSyllabi:
    """«Sillabussuz» sətirlər + sillabus QUERYSET-i — ``Paginator`` üçün tək ardıcıllıq.

    Perf auditi 2026-09-13 F-12: əvvəl bütün dəst (rektorda 4 926 sillabus)
    Python-a yüklənib HAMISI üçün ``build_row`` qurulur, sonra
    ``Paginator(rows)`` ilə 10-u seçilirdi (1 244 ms). İndi ``Paginator``
    uzunluğu ``len(missing) + queryset.count()`` kimi alır, dilimi isə
    ``missing[…] + queryset[LIMIT/OFFSET]`` kimi — ``build_row`` yalnız
    səhifənin sətirləri üçün çağırılır. Sıra əvvəlki kimi: əvvəl
    «sillabussuz» sətirlər, sonra sıralanmış sillabuslar.
    """

    def __init__(self, missing, queryset, *, now, copyable):
        self._missing = list(missing)
        self._queryset = queryset
        self._now = now
        self._copyable = copyable
        self._count = None

    def __len__(self):
        if self._count is None:
            self._count = len(self._missing) + self._queryset.count()
        return self._count

    def __getitem__(self, item):
        if not isinstance(item, slice):
            raise TypeError("yalnız dilim dəstəklənir")
        start, stop = item.start or 0, item.stop if item.stop is not None else len(self)
        head = self._missing[start:stop]
        offset = max(0, start - len(self._missing))
        limit = max(0, stop - len(self._missing)) - offset
        if limit <= 0:
            return head
        page_syllabi = list(
            self._queryset.select_related("current_version__approved_by", "current_version__reviewer")[
                offset : offset + limit
            ]
        )
        return head + [build_row(row, now=self._now, can_copy=row.subject_id in self._copyable) for row in page_syllabi]


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
        # «sla»/«missing» REAL status deyil — sorğuya ötürülsə heç nə uyğun
        # gəlməzdi; süzgəc aşağıda tətbiq olunur. Audit 2026-09-13 (perf F-12
        # yan tapıntısı): «missing» ötürüləndə dəst boşalır və sillabusu OLAN
        # açılışlar da «sillabussuz» görünürdü, KPI-lar sıfırlanırdı.
        statuses=[status] if status and status not in VIRTUAL_STATUS_KEYS else None,
        search=search,
        sort=sort if sort in SORT_LABELS else "recent",
    )
    # Perf auditi 2026-09-13 F-12: dəst DAHA Python-a yüklənmir — semestr/kafedra
    # süzgəcləri, SLA seçimi, «köçür» mənbəyi və kafedra siyahısı SQL-dədir;
    # `build_row` yalnız səhifənin sətirləri üçün (`_MissingThenSyllabi`).
    visible = context["syllabi"]
    # Kafedra siyahısı GÖRÜNƏN dəstdən çıxarılır — ayrıca struktur sorğusu
    # açmırıq ki, əhatəsiz istifadəçiyə bütün org-un kafedraları sızmasın.
    units = _chair_units(visible)
    syllabi = visible
    if semester:
        syllabi = syllabi.filter(period__name=semester)
    if unit:
        try:
            syllabi = syllabi.filter(chair_unit_id=uuid.UUID(unit))
        except ValueError:
            syllabi = syllabi.none()

    now = timezone.now()
    sla = sla_days(organization)
    overdue_q = _overdue_filter(now=now, sla=sla)
    overdue_count = syllabi.filter(overdue_q).count()
    if status == "sla":
        syllabi = syllabi.filter(overdue_q)
    copyable = _copyable_subjects(syllabi)

    missing = (
        _missing_rows(
            organization=organization,
            user=request.user,
            syllabi=visible,
            academic_year=academic_year,
            semester=semester,
            search=search,
            copyable=copyable,
        )
        if status in ("", "missing")
        else []
    )
    if status == "missing":
        sequence = _MissingThenSyllabi(missing, syllabi.none(), now=now, copyable=copyable)
    else:
        sequence = _MissingThenSyllabi(missing, syllabi, now=now, copyable=copyable)

    paginator = Paginator(sequence, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page") or 1)
    years, seasons = academic_filter_options(organization)

    return {
        "syllabus_list_section": {
            "has_access": True,
            "access_denied_message": "",
            "can_create": context["can_create"],
            "kpis": _kpis(context["counts"], len(missing), status, overdue_count=overdue_count, sla=sla),
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
            "empty": paginator.count == 0,
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
