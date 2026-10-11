"""«Jurnal təmizliyi» — TƏQDİMAT qatı: səhifə sətirləri, sübut sayları, süzgəc seçimləri, tarixçə.

Ayrı modul, çünki :mod:`apps.registrar.journal_hygiene` sorğu qatıdır və modul-ölçü büdcəsinə (600)
yaxınlaşırdı. Burada SORĞU MƏNTİQİ YOXDUR — yalnız hazır querysetin bir səhifəsi ``values()`` ilə oxunur
(model instansı qurulmur, N+1 yoxdur) və UI-ın JSON formasına salınır.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Count, Q
from django.utils import timezone

from . import journal_hygiene as hygiene
from .models import Enrollment, HygieneCategory, JournalHygieneDecision

PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
#: Bir tətbiq əməlinin (və «hamısını seç» düyməsinin) yuxarı həddi.
MAX_BATCH = 500

_ROW_FIELDS = (
    "pk",
    "status",
    "kind",
    "absence_hours",
    "student_id",
    "student__username",
    "student__first_name",
    "student__last_name",
    "student__profile__patronymic",
    "offering_id",
    "offering__subject__code",
    "offering__subject__name",
    "offering__group__name",
    "offering__period__name",
    "offering__period__academic_year",
    "offering__is_active",
    "offering__assessment_scheme__is_published",
)
_FLAGS = {
    hygiene.LEFT: ("jh_reason", "jh_strong", "jh_has_evidence", "jh_group_changed"),
    hygiene.EMPTY: ("jh_strong", "jh_closed", *hygiene.SOURCE_FLAGS.values()),
    hygiene.NOT_HELD: ("jh_strong", "jh_has_evidence", "jh_taught", "jh_legacy", "jh_size"),
}


def student_name(row: dict, prefix: str = "student__") -> str:
    """«Soyad Ad Ata adı» (jurnal başlığı ilə eyni sıra); boşdursa istifadəçi adı."""
    parts = (
        row.get(f"{prefix}last_name") or "",
        row.get(f"{prefix}first_name") or "",
        row.get(f"{prefix}profile__patronymic") or "",
    )
    return " ".join(part.strip() for part in parts if part and part.strip()) or (row.get(f"{prefix}username") or "")


def period_label(name, academic_year) -> str:
    year = django_apps.get_model("organizations", "AcademicPeriod").format_year(academic_year or "")
    name = (name or "").strip()
    if not year or year in name:
        return name or year
    return f"{year} · {name}" if name else year


def status_label(value) -> str:
    try:
        return str(Enrollment.Status(value).label)
    except ValueError:
        return str(value or "")


def _tags(row: dict, category: str) -> list:
    if category == hygiene.LEFT:
        codes = [hygiene.TAG_GROUP_CHANGED] if row.get("jh_group_changed") else []
    elif category == hygiene.NOT_HELD:
        codes = hygiene.not_held.tags_for(row)
    else:
        codes = [code for code, flag in hygiene.SOURCE_FLAGS.items() if row.get(flag)]
        codes = codes or [hygiene.SOURCE_UNEXPLAINED]
    return [{"code": code, "label": hygiene.label(code)} for code in codes]


def serialize_row(row: dict, category: str) -> dict:
    strong = bool(row.get("jh_strong"))
    item = {
        "id": str(row["pk"]),
        "offering_id": str(row.get("offering_id") or ""),
        "student_id": row.get("student_id"),
        "absence_hours": int(row.get("absence_hours") or 0),
        "student": student_name(row),
        "username": row.get("student__username") or "",
        "subject": " — ".join(
            part for part in (row.get("offering__subject__code"), row.get("offering__subject__name")) if part
        ),
        "group": row.get("offering__group__name") or "",
        "period": period_label(row.get("offering__period__name"), row.get("offering__period__academic_year")),
        "status": row.get("status") or "",
        "status_label": status_label(row.get("status")),
        "kind": row.get("kind") or "",
        "strong": strong,
        "strength_label": hygiene.label(hygiene.STRENGTH_STRONG if strong else hygiene.STRENGTH_REVIEW),
        "journal_closed": bool(row.get("offering__assessment_scheme__is_published")),
        "offering_active": bool(row.get("offering__is_active")),
        "tags": _tags(row, category),
    }
    if category == hygiene.LEFT:
        item["reason"] = row.get("jh_reason") or ""
        item["reason_label"] = hygiene.label(item["reason"])
        item["has_evidence"] = bool(row.get("jh_has_evidence"))
    elif category == hygiene.NOT_HELD:
        # Vahid açılışdır: səbəb həmişə «keçirilməyib», etiketlər giriş balı / dərs izi / köhnə sistem.
        item["reason"] = hygiene.not_held.REASON_NOT_HELD
        item["reason_label"] = hygiene.label(item["reason"])
        item["has_evidence"] = bool(row.get("jh_has_evidence"))
        item["group_size"] = int(row.get("jh_size") or 0)
    else:
        item["reason"] = item["tags"][0]["code"]
        item["reason_label"] = item["tags"][0]["label"]
        item["has_evidence"] = False
    return item


def rows_for(queryset, category: str) -> list:
    """Hazır (süzgəclənmiş, sıralanmış, ola bilsin dilimlənmiş) querysetin sətirləri."""
    return [serialize_row(row, category) for row in queryset.values(*_ROW_FIELDS, *_FLAGS[category])]


def page_total(chip_counts: dict, category_code: str) -> int:
    """Kateqoriya süzgəcli siyahının cəmi — çip saylarından (əlavə COUNT sorğusu yoxdur)."""
    code = (category_code or "").strip()
    if code == hygiene.STRENGTH_REVIEW:
        return max(0, chip_counts.get("total", 0) - chip_counts.get("strong", 0))
    if code == hygiene.STRENGTH_STRONG:
        return chip_counts.get("strong", 0)
    if code and code in chip_counts and code not in ("total", "empty"):
        return chip_counts[code]
    return chip_counts.get("total", 0)


def page(queryset, category: str, *, number: int, size: int, total: int) -> dict:
    size = max(1, min(int(size or PAGE_SIZE), MAX_PAGE_SIZE))
    num_pages = max(1, (int(total) + size - 1) // size)
    number = max(1, min(int(number or 1), num_pages))
    offset = (number - 1) * size
    return {
        "results": rows_for(queryset[offset : offset + size], category),
        "page": number,
        "num_pages": num_pages,
        "total": int(total),
        "has_next": number < num_pages,
        "has_previous": number > 1,
    }


def evidence_counts(enrollment_ids) -> dict:
    """``{enrollment_id(str): {mənbə: say}}`` — yalnız sıfırdan böyük saylar; mənbə başına BİR sorğu."""
    ids = [pk for pk in enrollment_ids if pk]
    result = {str(pk): {} for pk in ids}
    if not ids:
        return result
    for key, model, field, extra in hygiene.evidence_sources():
        queryset = model.objects.filter(**{f"{field}__in": ids})
        if extra is not None:
            queryset = queryset.filter(extra)
        for owner, total in queryset.order_by().values_list(field).annotate(n=Count("pk")):
            if owner is not None and str(owner) in result and total:
                result[str(owner)][key] = int(total)
    return result


# ── Süzgəc seçimləri (panel çərçivəsi) ───────────────────────────────────────


def period_options(organization, *, today=None) -> list:
    today = today or timezone.localdate()
    model = django_apps.get_model("organizations", "AcademicPeriod")
    rows = model.objects.filter(organization=organization).order_by("-start_date")
    return [
        {
            "value": str(period.pk),
            "label": period_label(period.name, period.academic_year),
            "open": bool(period.is_active and (period.is_current or period.start_date > today)),
            "current": bool(period.is_current),
        }
        for period in rows.only("id", "name", "academic_year", "start_date", "is_current", "is_active")
    ]


def unit_options(organization, unit_type: str) -> list:
    model = django_apps.get_model("organizations", "OrgUnit")
    rows = model.objects.filter(organization=organization, unit_type=unit_type, is_active=True).order_by("name")
    return [{"value": str(pk), "label": name} for pk, name in rows.values_list("pk", "name")]


# ── Tarixçə ──────────────────────────────────────────────────────────────────

_HISTORY_FIELDS = (
    "pk",
    "batch",
    "category",
    "reason_code",
    "from_status",
    "to_status",
    "reason",
    "decided_by_name",
    "created_at",
    "reverted_at",
    "reverted_by_name",
    "revert_reason",
    "enrollment_id",
    "enrollment__status",
    "enrollment__student__username",
    "enrollment__student__first_name",
    "enrollment__student__last_name",
    "enrollment__student__profile__patronymic",
    "enrollment__offering__subject__code",
    "enrollment__offering__subject__name",
    "enrollment__offering__group__name",
    "enrollment__offering__period__name",
    "enrollment__offering__period__academic_year",
)

HISTORY_STATES = ("active", "reverted")


def history_queryset(organization, filters=None):
    """Qərar jurnalı — ən yenisi əvvəl; süzgəclər: dövr, fakültə, qrup, kateqoriya, vəziyyət, axtarış."""
    from core.search_text import tolerant_q

    filters = filters or {}
    queryset = JournalHygieneDecision.objects.filter(organization=organization)
    period = hygiene.parse_uuid(filters.get("period"))
    if period:
        queryset = queryset.filter(enrollment__offering__period_id=period)
    group = hygiene.parse_uuid(filters.get("group"))
    if group:
        queryset = queryset.filter(enrollment__offering__group_id=group)
    faculty = hygiene.parse_uuid(filters.get("faculty"))
    if faculty:
        unit = (
            django_apps.get_model("organizations", "OrgUnit")
            .objects.filter(organization=organization, pk=faculty)
            .values_list("path", flat=True)
            .first()
        )
        prefix = f"{unit or faculty}/"
        queryset = queryset.filter(
            Q(enrollment__offering__group_id=faculty) | Q(enrollment__offering__group__path__startswith=prefix)
        )
    category = str(filters.get("category") or "").strip()
    if category in hygiene.CATEGORIES:
        queryset = queryset.filter(category=category)
    state = str(filters.get("state") or "").strip()
    if state == "active":
        queryset = queryset.filter(reverted_at__isnull=True)
    elif state == "reverted":
        queryset = queryset.filter(reverted_at__isnull=False)
    search = tolerant_q(
        str(filters.get("q") or "")[:100],
        fields=(
            "enrollment__student__first_name",
            "enrollment__student__last_name",
            "enrollment__student__username",
            "enrollment__offering__subject__name",
        ),
    )
    if search is not None:
        queryset = queryset.filter(search)
    return queryset.order_by("-created_at", "pk")


def _stamp(value) -> str:
    return timezone.localtime(value).strftime("%d.%m.%Y %H:%M") if value else ""


def serialize_history(row: dict) -> dict:
    reverted = row.get("reverted_at") is not None
    return {
        "id": str(row["pk"]),
        "batch": str(row.get("batch") or ""),
        "category": row.get("category") or "",
        "category_label": _category_label(row.get("category")),
        "reason_code": row.get("reason_code") or "",
        "reason_label": hygiene.label(row.get("reason_code")),
        "from_status": row.get("from_status") or "",
        "from_label": status_label(row.get("from_status")),
        "to_status": row.get("to_status") or "",
        "to_label": status_label(row.get("to_status")),
        "reason": row.get("reason") or "",
        "decided_by": row.get("decided_by_name") or "",
        "decided_at": _stamp(row.get("created_at")),
        "reverted": reverted,
        "reverted_at": _stamp(row.get("reverted_at")),
        "reverted_by": row.get("reverted_by_name") or "",
        "revert_reason": row.get("revert_reason") or "",
        # Geri qaytarıla bilir: qərar qüvvədədir VƏ status o vaxtdan dəyişməyib.
        "can_revert": (not reverted) and row.get("enrollment__status") == row.get("to_status"),
        "enrollment_id": str(row.get("enrollment_id") or ""),
        "student": student_name(row, prefix="enrollment__student__"),
        "subject": " — ".join(
            part
            for part in (row.get("enrollment__offering__subject__code"), row.get("enrollment__offering__subject__name"))
            if part
        ),
        "group": row.get("enrollment__offering__group__name") or "",
        "period": period_label(
            row.get("enrollment__offering__period__name"), row.get("enrollment__offering__period__academic_year")
        ),
    }


def _category_label(value) -> str:
    try:
        return str(HygieneCategory(value).label)
    except ValueError:
        return str(value or "")


def history_page(queryset, *, number: int, size: int) -> dict:
    size = max(1, min(int(size or PAGE_SIZE), MAX_PAGE_SIZE))
    total = queryset.count()
    num_pages = max(1, (total + size - 1) // size)
    number = max(1, min(int(number or 1), num_pages))
    offset = (number - 1) * size
    rows = queryset.values(*_HISTORY_FIELDS)[offset : offset + size]
    return {
        "results": [serialize_history(row) for row in rows],
        "page": number,
        "num_pages": num_pages,
        "total": total,
        "has_next": number < num_pages,
        "has_previous": number > 1,
    }


def history_counts(organization) -> dict:
    totals = JournalHygieneDecision.objects.filter(organization=organization).aggregate(
        total=Count("pk"), reverted=Count("pk", filter=Q(reverted_at__isnull=False))
    )
    return {key: int(value or 0) for key, value in totals.items()}


__all__ = [
    "HISTORY_STATES",
    "MAX_BATCH",
    "MAX_PAGE_SIZE",
    "PAGE_SIZE",
    "evidence_counts",
    "history_counts",
    "history_page",
    "history_queryset",
    "page",
    "page_total",
    "period_label",
    "period_options",
    "rows_for",
    "serialize_history",
    "serialize_row",
    "status_label",
    "student_name",
    "unit_options",
]
