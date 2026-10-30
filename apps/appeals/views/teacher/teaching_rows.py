"""«Fənnimə aid apellyasiyalar» — süzgəclər, bal xülasəsi və sətir bəzəkləri (kabinet bölməsi, sahib 2026-10-27).

Panel (:mod:`.teaching_panel`), çekməcə və Excel ixracı (:mod:`.teaching`) eyni süzgəc qaydasını və eyni bal
xülasəsini işlədir — ekranda görünən siyahı ilə yüklənən fayl ayrılmasın.

BAL: «ilkin → yeni» qərar yazılarından (``AppealDecisionRecord.score_before`` / ``score_after``) gəlir; köhnə
qərarlarda yazı yoxdursa geri alınmamış bal düzəlişlərindən (``ScoreAdjustment``). Gözləyən apellyasiyada bal
dəyişməyib — «—». Ortalama dəyişmə: süzülmüş dəstdə geri alınmamış düzəlişlərin cəmi / qərarlı apellyasiya sayı.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Prefetch, Sum
from django.utils.dateparse import parse_date
from django.utils.translation import pgettext

from core.person_names import user_display_name_with_patronymic
from core.search_text import tolerant_q

from ...constants import (
    APPEAL_ITEM_STATUS_ACCEPTED,
    APPEAL_ITEM_STATUS_REJECTED,
    APPEAL_STATUS_ACCEPTED,
    APPEAL_STATUS_CHOICES,
    APPEAL_STATUS_FINAL,
    APPEAL_STATUS_PARTIALLY_ACCEPTED,
    APPEAL_STATUS_VALUES,
)
from ...models import AppealDecisionRecord, ScoreAdjustment
from ...services.student_identity import student_group_map

CTX = "appeals.teaching"
PREFIX = "ta_"
SECTION = "teaching-appeals"
#: KPI «Qəbul / qismən» kartının süzgəci — tam və qismən qəbul birlikdə.
STATUS_ACCEPTED_ANY = "accepted_any"
CATEGORIES = ("midterm", "final", "quiz")
FILTER_KEYS = ("q", "status", "subject", "group", "category", "from", "to")


def _param(request, key, limit=120) -> str:
    return (request.GET.get(PREFIX + key) or "").strip()[:limit]


def read_filters(request) -> dict:
    """URL-dən süzgəclər (etibarsız dəyər → boş)."""
    status = _param(request, "status")
    if status not in APPEAL_STATUS_VALUES and status != STATUS_ACCEPTED_ANY:
        status = ""
    category = _param(request, "category")
    subject = _param(request, "subject")
    date_from, date_to = _param(request, "from", 10), _param(request, "to", 10)
    return {
        "q": _param(request, "q"),
        "status": status,
        "subject": subject if subject.isascii() and subject.isdigit() and len(subject) <= 12 else "",
        "group": _param(request, "group", 160),
        "category": category if category in CATEGORIES else "",
        "from": date_from if _valid_date(date_from) else "",
        "to": date_to if _valid_date(date_to) else "",
    }


def _valid_date(text) -> bool:
    """``parse_date`` formatı düz, tarixi səhv dəyərdə (``2026-02-30``) ``ValueError`` atır — 500 olmasın."""
    try:
        return bool(text) and parse_date(text) is not None
    except ValueError:
        return False


def apply_filters(queryset, filters, *, group_map=None, with_status=True):
    """Status xaricindəki süzgəclər həmişə; status yalnız ``with_status`` (KPI sayğacları statussuz dəstdən)."""
    search_q = tolerant_q(
        filters["q"],
        (
            "student__first_name",
            "student__last_name",
            "student__username",
            "student__profile__patronymic",
            "exam__title",
        ),
    )
    if search_q is not None:
        queryset = queryset.filter(search_q)
    if filters["subject"]:
        queryset = queryset.filter(exam__subject_id=int(filters["subject"]))
    if filters["category"]:
        queryset = queryset.filter(exam__exam_type_extended=filters["category"])
    if filters["from"]:
        queryset = queryset.filter(created_at__date__gte=parse_date(filters["from"]))
    if filters["to"]:
        queryset = queryset.filter(created_at__date__lte=parse_date(filters["to"]))
    if filters["group"]:
        groups = group_map if group_map is not None else student_group_map(queryset)
        queryset = queryset.filter(student_id__in=[pk for pk, name in groups.items() if name == filters["group"]])
    if with_status and filters["status"]:
        if filters["status"] == STATUS_ACCEPTED_ANY:
            queryset = queryset.filter(status__in=[APPEAL_STATUS_ACCEPTED, APPEAL_STATUS_PARTIALLY_ACCEPTED])
        else:
            queryset = queryset.filter(status=filters["status"])
    return queryset


def with_row_data(queryset):
    """Sətir üçün lazım olan hər şey — sətir başına əlavə sorğu yoxdur."""
    return queryset.select_related(
        "exam", "exam__subject", "exam__course", "student", "student__profile", "reviewed_by"
    ).prefetch_related(
        "items__decided_by_teacher",
        "items__score_adjustment",
        Prefetch(
            "decision_records",
            queryset=AppealDecisionRecord.objects.order_by("created_at", "id").select_related("decided_by_teacher"),
        ),
    )


def points(value) -> str:
    if value is None:
        return ""
    text = f"{Decimal(value):.2f}"
    return text.rstrip("0").rstrip(".") or "0"


def signed_points(value) -> str:
    if value is None:
        return ""
    return ("+" if value > 0 else "") + points(value)


def _adjustments(appeal) -> list:
    rows = []
    for item in appeal.items.all():
        try:
            adjustment = item.score_adjustment
        except ObjectDoesNotExist:
            continue
        if adjustment is not None and not adjustment.reverted:
            rows.append(adjustment)
    return sorted(rows, key=lambda row: (row.applied_at, row.pk))


def score_summary(appeal) -> dict:
    """``{"before", "after", "delta"}`` (Decimal və ya None) — qərar yazıları, yoxdursa bal düzəlişləri."""
    records = list(appeal.decision_records.all())
    adjustments = _adjustments(appeal)
    delta_sum = sum((row.delta_points for row in adjustments), Decimal("0")) if adjustments else None
    before = next((row.score_before for row in records if row.score_before is not None), None)
    after = next((row.score_after for row in reversed(records) if row.score_after is not None), None)
    if before is None and adjustments:
        before = adjustments[0].previous_score
    if after is None and adjustments:
        after = adjustments[-1].new_score
    if before is not None and after is not None:
        delta = Decimal(after) - Decimal(before)
    else:
        delta = delta_sum
    return {"before": before, "after": after, "delta": delta}


def _decided_at(appeal, records):
    moments = [appeal.reviewed_at] + [row.created_at for row in records]
    moments += [item.resolved_at for item in appeal.items.all()]
    moments = [moment for moment in moments if moment]
    return max(moments) if moments else None


def _person(user) -> str:
    return (user.get_full_name() or user.get_username()).strip() if user is not None else ""


def decided_by(appeal) -> str:
    """Qərarı verən müəllim(lər) — sual qərarlarından, yoxdursa qərar yazılarından (təkrarsız, sıra ilə)."""
    names = []
    for user in [item.decided_by_teacher for item in appeal.items.all()] + [
        row.decided_by_teacher for row in appeal.decision_records.all()
    ]:
        name = _person(user)
        if name and name not in names:
            names.append(name)
    return ", ".join(names)


def _initials(user) -> str:
    letters = ((user.first_name or "")[:1] + (user.last_name or "")[:1]).strip()
    return (letters or (user.username or "?")[:2]).upper()


def _subject(exam) -> str:
    if exam.subject_id and exam.subject is not None:
        return exam.subject.name
    return exam.course.title if exam.course_id and exam.course is not None else ""


def _delta_tone(delta) -> str:
    if delta is None or delta == 0:
        return "neutral"
    return "success" if delta > 0 else "danger"


def build_row(appeal, group_map) -> dict:
    """Bir apellyasiyanın ekran / ixrac sətri (sorğusuz — ``with_row_data`` prefetch-i ilə)."""
    items = list(appeal.items.all())
    records = list(appeal.decision_records.all())
    scores = score_summary(appeal)
    student = appeal.student
    exam = appeal.exam
    return {
        "appeal": appeal,
        "id": appeal.pk,
        "student_name": user_display_name_with_patronymic(student),
        "student_username": student.username,
        "patronymic": (getattr(getattr(student, "profile", None), "patronymic", "") or "").strip(),
        "student_short": student.get_full_name() or student.username,
        "initials": _initials(student),
        "group": group_map.get(student.pk, ""),
        "exam_title": exam.title,
        "category": exam.exam_type_extended or "",
        "category_label": exam.get_exam_type_extended_display() if exam.exam_type_extended else "",
        "subject": _subject(exam),
        "item_count": len(items),
        "accepted": sum(1 for item in items if item.status == APPEAL_ITEM_STATUS_ACCEPTED),
        "rejected": sum(1 for item in items if item.status == APPEAL_ITEM_STATUS_REJECTED),
        "status": appeal.status,
        "status_label": appeal.get_status_display(),
        "is_final": appeal.status in APPEAL_STATUS_FINAL,
        "score_before": points(scores["before"]),
        "score_after": points(scores["after"]),
        "delta": scores["delta"],
        "delta_display": signed_points(scores["delta"]),
        "delta_tone": _delta_tone(scores["delta"]),
        "created_at": appeal.created_at,
        "decided_at": _decided_at(appeal, records) if appeal.status in APPEAL_STATUS_FINAL else None,
        "decided_by": decided_by(appeal),
        "reviewer": _person(appeal.reviewed_by),
        "note": appeal.reviewer_note or "",
    }


def kpi_tiles(base_queryset, active_status) -> list:
    """Status süzgəcindən ƏVVƏLKİ dəst üzrə sayğaclar (TƏK GROUP BY) + orta bal dəyişməsi (TƏK SUM)."""
    from django.db.models import Count

    counts = {row["status"]: row["n"] for row in base_queryset.order_by().values("status").annotate(n=Count("id"))}
    total = sum(counts.values())
    accepted = counts.get(APPEAL_STATUS_ACCEPTED, 0) + counts.get(APPEAL_STATUS_PARTIALLY_ACCEPTED, 0)
    decided = sum(counts.get(status, 0) for status in APPEAL_STATUS_FINAL)
    delta_total = ScoreAdjustment.objects.filter(
        appeal_item__appeal__in=base_queryset.order_by().values("pk"), reverted=False
    ).aggregate(total=Sum("delta_points"))["total"]
    average = (Decimal(delta_total or 0) / decided) if decided else None
    labels = dict(APPEAL_STATUS_CHOICES)

    def tile(label, value, *, status="", tone="", note=""):
        entry = {"label": label, "value": value, "tone": tone, "note": note}
        if status:
            entry.update({"filter": status, "pressed": active_status == status})
        return entry

    return [
        tile(pgettext(CTX, "Cəmi"), total, tone="accent-primary", note=pgettext(CTX, "süzgəcə uyğun müraciət")),
        tile(str(labels["pending"]), counts.get("pending", 0), status="pending", tone="accent-warning"),
        tile(str(labels["under_review"]), counts.get("under_review", 0), status="under_review"),
        tile(
            pgettext(CTX, "Qəbul / qismən"),
            accepted,
            status=STATUS_ACCEPTED_ANY,
            tone="accent-success",
            note=pgettext(CTX, "qismən: %(n)s") % {"n": counts.get(APPEAL_STATUS_PARTIALLY_ACCEPTED, 0)},
        ),
        tile(str(labels["rejected"]), counts.get("rejected", 0), status="rejected", tone="accent-danger"),
        tile(
            pgettext(CTX, "Orta bal dəyişməsi"),
            signed_points(average.quantize(Decimal("0.01"))) if average is not None else "—",
            note=pgettext(CTX, "qərarlı müraciət başına"),
        ),
    ]


__all__ = [
    "CATEGORIES",
    "FILTER_KEYS",
    "PREFIX",
    "SECTION",
    "STATUS_ACCEPTED_ANY",
    "apply_filters",
    "build_row",
    "decided_by",
    "kpi_tiles",
    "points",
    "read_filters",
    "score_summary",
    "signed_points",
    "student_group_map",
    "with_row_data",
]
