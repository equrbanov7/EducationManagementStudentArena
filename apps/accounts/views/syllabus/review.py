"""«Kafedra müdiri — Sillabus təsdiqi» bölməsinin CONTEXT MÜQAVİLƏSİ (§3.3).

⚠️ Ekran profil shell-inin İÇİNDƏ açılır — SOL SIDEBAR QALIR (``SECTION_PARTIALS``
arxitekturası); ayrıca tam-səhifə səth DEYİL.

ƏHATƏ (fail-closed, README §3.3 `noscope`): görünən hər şey
``apps.syllabus.services.coverage`` və ``review_queue`` tərəfindən aktorun
``syllabus.review`` scope-u ilə daraldılır. Struktur əhatəsi tapılmayan
istifadəçi «əhatə təyin edilməyib» boş vəziyyətini görür — bütün təşkilat
AÇILMIR.

──────────────────────────────────────────────────────────────────────────────
CONTEXT — ``syllabus_review_section`` (dict)
──────────────────────────────────────────────────────────────────────────────
    has_access      bool     — `syllabus.review` açarı var
    has_scope       bool     — struktur əhatəsi var (False → boş vəziyyət)
    scope_mode      str      — "chair" | "wide" | "noscope" (yalnız göstəriş)
    identity        {panel,person,role,scope}          — yuxarı zolaq
    intro           str
    tab             "queue" | "coverage"
    kpis            [{key,label,value,note,tone}]      — 4 kart (növbə)
    filters         {q,status,unit,sort,year,tab}
    filter_options  {statuses,units,sorts,years,unit_label}
    rows            [row]    — bax :mod:`.review_rows`
    page            {number,count,total,start,end,has_prev,has_next,numbers}
    coverage        {col_label,title,rows,totals,kpis,trend,policy}
    can_approve / can_revise / can_reject   bool
    urls            {open,decision}
    empty           bool
"""

from __future__ import annotations

from django.core.paginator import Paginator
from django.urls import reverse
from django.utils import timezone

from apps.syllabus.constants import PERM_REVIEW, QUEUE_STATUSES, SELFWORK_OPTIONS, SectionKey, SyllabusStatus
from apps.syllabus.models import SyllabusSection
from apps.syllabus.public import build_review_queue_context

from .labels import STATUS_TONES
from .lookup import safe_uuid
from .review_rows import LATE_DAYS, build_queue_row, waiting_days
from .review_text import (
    ACCESS_DENIED,
    COVERAGE_KPI_LABELS,
    IDENTITY,
    INTRO,
    KPI_LABELS,
    MIN_DECISION_REASON,
    NOSCOPE,
    POLICY_ROWS,
    QUEUE_SORT_LABELS,
    READ_ONLY,
    SCOPE_COUNT,
    STATUS_FILTER_ALL,
    UNIT_FILTER_ALL,
    UNIT_FILTER_LABELS,
    YEAR_FILTER_ALL,
    coverage_titles,
    dialog_payload,
    panel_payload,
)
from .section import academic_filter_options

#: Növbə səhifəsində sətir sayı — siyahı ekranı ilə eyni ritm.
PAGE_SIZE = 10

#: `reverse(...)` üçün sıfır UUID — JS şablon URL-də bunu real id ilə əvəzləyir.
_URL_PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000"

_EMPTY_SECTION = {
    "has_access": False,
    "has_scope": False,
    "scope_mode": "noscope",
    "rows": [],
    "kpis": [],
    "can_decide": False,
    "coverage": {"rows": [], "kpis": [], "trend": [], "policy": []},
}


def _text(request, key: str, default: str = "") -> str:
    return (request.GET.get(key) or default).strip()


def _policy_breaches(versions) -> set:
    """Sərbəst iş strukturu SİYASƏTƏ UYĞUN OLMAYAN versiyalar (məs. 3×5).

    Yalnız cari SƏHİFƏNİN versiyaları üçün TƏK sorğu atılır — N+1 yoxdur.
    Boş seçim «pozuntu» sayılmır: o, `çatışmayan bölmə` riski ilə onsuz da
    göstərilir, iki çip eyni şeyi təkrarlamamalıdır.
    """
    ids = [version.pk for version in versions]
    if not ids:
        return set()
    rows = SyllabusSection.objects.filter(version_id__in=ids, section_id=SectionKey.SELF.value).values_list(
        "version_id", "data"
    )
    breached = set()
    for version_id, data in rows:
        option = (data or {}).get("option") if isinstance(data, dict) else None
        if isinstance(option, str) and option.strip() and option.strip() not in SELFWORK_OPTIONS:
            breached.add(version_id)
    return breached


def _kpis(versions, *, now):
    """4 kart (dizayn §3.3): növbə · SLA pozuntusu · çatışmayan · orta gözləmə."""
    days = [waiting_days(version, now=now) for version in versions]
    late = sum(1 for value in days if value >= LATE_DAYS)
    incomplete = sum(1 for version in versions if (version.completion_percent or 0) < 100)
    average = round(sum(days) / len(days)) if days else 0
    values = {
        "queued": len(versions),
        "late": late,
        "incomplete": incomplete,
        "average": average,
    }
    cards = []
    for key, tone in (("queued", "neutral"), ("late", "danger"), ("incomplete", "warning"), ("average", "primary")):
        label, note, suffix = KPI_LABELS[key]
        cards.append(
            {
                "key": key,
                "label": label,
                "note": note,
                "value": f"{values[key]} {suffix}".strip() if suffix else values[key],
                "tone": tone,
            }
        )
    return cards


def _status_options(active: str):
    rows = [{"key": "", "label": STATUS_FILTER_ALL, "active": not active}]
    for status in sorted(QUEUE_STATUSES):
        rows.append(
            {
                "key": status,
                "label": SyllabusStatus(status).label,
                "tone": STATUS_TONES.get(status, "neutral"),
                "active": active == status,
            }
        )
    return rows


def _unit_options(coverage_rows, active: str):
    """Filtr açılışı GÖRÜNƏN dəstdən qurulur — əhatədən kənar ad sızmır.

    ``bucket["label"]`` cədvəldəki ilə EYNİ etiketdir (proqramda «Ad · şifr»),
    ona görə açılışda da rəsmi ixtisas şifri görünür — istifadəçi cədvəldə
    gördüyü şifri seçicidə də tanıyır.
    """
    rows = [{"key": "", "label": UNIT_FILTER_ALL}]
    for bucket in coverage_rows:
        if bucket["key"] is None or not bucket["name"]:
            continue
        rows.append({"key": str(bucket["key"]), "label": bucket["label"]})
    for row in rows:
        row["active"] = row["key"] == active
    return rows


def _coverage_kpis(totals: dict):
    values = {
        "percent": f"{totals.get('percent', 0)}%",
        "approved": totals.get("approved", 0),
        "in_review": totals.get("in_review", 0),
        "revision": totals.get("revision", 0),
        "late": totals.get("late", 0),
    }
    cards = []
    for key, tone in (
        ("percent", "success"),
        ("approved", "neutral"),
        ("in_review", "primary"),
        ("revision", "warning"),
        ("late", "danger"),
    ):
        label, note = COVERAGE_KPI_LABELS[key]
        cards.append({"key": key, "label": label, "note": note, "value": values[key], "tone": tone})
    return cards


def _page_numbers(page):
    total = page.paginator.num_pages
    current = page.number
    window = {1, total, current, current - 1, current + 1}
    return [number for number in sorted(window) if 1 <= number <= total]


def _identity(request, *, scope_mode: str, coverage_rows):
    """Yuxarı zolaq: panel adı · şəxs · rol · əhatə (dizayn §3.3 başlığı)."""
    panel, role = IDENTITY[scope_mode]
    user = getattr(request, "user", None)
    person = ""
    if user is not None:
        person = (user.get_full_name() or "").strip() or getattr(user, "username", "")
    units = [bucket["label"] for bucket in coverage_rows if bucket["name"]]
    if scope_mode == "chair" and units:
        scope = units[0]
    else:
        scope = str(SCOPE_COUNT) % {"count": len(units)}
    return {"panel": panel, "person": person, "role": role, "scope": scope}


def _has_review_permission(request) -> bool:
    from core.permissions import has_permission, is_superadmin_user

    if is_superadmin_user(getattr(request, "user", None)):
        return True
    return has_permission(list(getattr(request, "org_permissions", None) or []), PERM_REVIEW)


def build_syllabus_review_section(request, *, organization) -> dict:
    """«Sillabus təsdiqi» bölməsinin context-i (profil shell-i içində)."""
    if organization is None or not _has_review_permission(request):
        return {"syllabus_review_section": {**_EMPTY_SECTION, "access_denied_message": ACCESS_DENIED}}

    tab = "coverage" if _text(request, "tab") == "coverage" else "queue"
    search = _text(request, "q")
    status = _text(request, "status")
    unit = _text(request, "unit")
    sort = _text(request, "sort", "wait")
    year = _text(request, "year")

    context = build_review_queue_context(
        request,
        organization=organization,
        statuses=[status] if status in QUEUE_STATUSES else None,
        search=search,
        sort=sort if sort in QUEUE_SORT_LABELS else "wait",
        academic_year=year or None,
    )
    scope_mode = context["scope_mode"]
    coverage = context["coverage"]

    if not context["has_scope"]:
        return {
            "syllabus_review_section": {
                **_EMPTY_SECTION,
                "has_access": True,
                "access_denied_message": "",
                "noscope": NOSCOPE,
            }
        }

    # Kafedra rejimində filtr PROQRAM üzrə, geniş rejimdə KAFEDRA üzrədir.
    # ⚠️ `unit` istifadəçi girişidir — xam mətnlə filtr Django-da `ValidationError`
    # (500) verərdi, ona görə əvvəlcə UUID-ə çevrilir; yanlış format sadəcə
    # filtrsiz nəticə deməkdir (əhatə onsuz da yuxarıda daralıb).
    queue = context["queue"]
    unit_id = safe_uuid(unit) if unit else None
    if unit_id is not None:
        field = "syllabus__chair_unit_id" if scope_mode == "wide" else "syllabus__program_id"
        queue = queue.filter(**{field: unit_id})

    versions = list(queue)
    paginator = Paginator(versions, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page") or 1)
    page_versions = list(page.object_list)
    breached = _policy_breaches(page_versions)
    now = timezone.now()
    rows = [build_queue_row(version, now=now, policy_breach=version.pk in breached) for version in page_versions]
    years, _seasons = academic_filter_options(organization)
    titles = coverage_titles(scope_mode)

    return {
        "syllabus_review_section": {
            "has_access": True,
            "has_scope": True,
            "scope_mode": scope_mode,
            "access_denied_message": "",
            "identity": _identity(request, scope_mode=scope_mode, coverage_rows=coverage["rows"]),
            "intro": INTRO[scope_mode],
            "tab": tab,
            "kpis": _kpis(versions, now=now),
            "rows": rows,
            "filters": {"q": search, "status": status, "unit": unit, "sort": sort, "year": year, "tab": tab},
            "filter_options": {
                "statuses": _status_options(status),
                "units": _unit_options(coverage["rows"], unit),
                "unit_label": UNIT_FILTER_LABELS[scope_mode],
                "sorts": [{"key": key, "label": label} for key, label in QUEUE_SORT_LABELS.items()],
                "years": [{"key": "", "label": YEAR_FILTER_ALL}]
                + [{"key": row["key"], "label": row["label"]} for row in years],
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
            "coverage": {
                "col_label": titles["col"],
                "title": titles["title"],
                "subtitle": titles["subtitle"],
                "rows": coverage["rows"],
                "totals": coverage["totals"],
                "kpis": _coverage_kpis(coverage["totals"]),
                "trend": context["trend"],
                "policy": POLICY_ROWS,
            },
            "dialogs": dialog_payload(),
            "texts": panel_payload(min_reason=MIN_DECISION_REASON),
            "can_approve": context["can_approve"],
            "can_revise": context["can_revise"],
            "can_reject": context["can_reject"],
            # Sahibin qərarı (2026-09-03): qərar KAFEDRA MÜDİRİNİNDİR. Qərar
            # əhatəsi olmayan aktor (dekan) növbəni oxuyur — düymə əvəzinə
            # AÇIQ QEYD görür, düymə səssizcə yox olmur.
            "can_decide": context["can_decide"],
            "read_only": None if context["can_decide"] else READ_ONLY,
            "urls": {
                # Şablon URL-i: JS «0…0» UUID-ini konkret versiya id-si ilə əvəzləyir.
                "open": reverse("accounts:syllabus_review_open", kwargs={"version_id": _URL_PLACEHOLDER_UUID}),
                "decision": reverse("accounts:syllabus_decision", kwargs={"version_id": _URL_PLACEHOLDER_UUID}),
            },
            "empty": not rows,
        }
    }


__all__ = ["PAGE_SIZE", "build_syllabus_review_section"]
