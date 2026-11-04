"""«Jurnaldan çıxarılmalar» — mərkəzi siyahı, süzgəclər və Excel ixracı (sahib 2026-11-04).

Sahib: «Daha sonra mən harada isə onda baxa bilim o tip hadisələrə — nəyə görə olub.»

Mənbə :class:`~apps.registrar.models.JournalRemoval` (append-only). Bu modul YALNIZ OXUYUR və AKTOR QAPISI
QOYMUR — qapı çağıranındır (kabinet bölməsi: ``apps.accounts.views.journal_removals``, RİM rəhbəri və
superadmin). Təşkilat izolyasiyası həm sorğuda (``organization=``), həm RLS-dədir.

Süzgəclər (``jr_`` prefiksi — kabinet filtr panelinin ad fəzası): səbəb, əməl, tarix aralığı, fakültə (açılışın
qrupu fakültənin alt-ağacında), kafedra (``offering_chairs.kafedra_q`` — fənnin tədris yükünün kafedrası),
müəllim (açılışın müəllimi, dözümlü axtarış), tələbə (ad / istifadəçi adı, dözümlü axtarış).
Sorğu sayı sətir sayından asılı deyil (sayğaclar + bir səhifə + seçim siyahıları).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace

from django.apps import apps as django_apps
from django.db.models import Count, Q
from django.utils import timezone

from core.constants import OrgUnitType
from core.search_text import tolerant_q

from . import journal_removal
from .journal_hygiene_rows import period_label
from .journal_names import journal_student_name
from .models import JournalRemoval, RemovalAction, RemovalReason
from .offering_chairs import CHAIR_TYPES, kafedra_q

PREFIX = "jr_"
PAGE_SIZE = 50
MAX_PAGE = 400
#: Tək Excel faylında ən çox sətir (yaddaş tavanı).
MAX_EXPORT_ROWS = 10000

_STUDENT_FIELDS = (
    "enrollment__student__first_name",
    "enrollment__student__last_name",
    "enrollment__student__username",
    "enrollment__student__profile__patronymic",
)
_TEACHER_FIELDS = (
    "enrollment__offering__instructor__first_name",
    "enrollment__offering__instructor__last_name",
    "enrollment__offering__instructor__username",
)


@dataclass(frozen=True)
class Filters:
    reason: str = ""
    action: str = ""
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    faculty: str = ""
    chair: str = ""
    teacher: str = ""
    student: str = ""
    page: int = 1

    @property
    def is_filtered(self) -> bool:
        return any(
            (
                self.reason,
                self.action,
                self.date_from,
                self.date_to,
                self.faculty,
                self.chair,
                self.teacher,
                self.student,
            )
        )

    def as_params(self, *, page=None) -> dict:
        """URL parametrləri (boşlar atılır) — səhifələmə və ixrac linkləri."""
        params = {
            f"{PREFIX}reason": self.reason,
            f"{PREFIX}action": self.action,
            f"{PREFIX}from": self.date_from.isoformat() if self.date_from else "",
            f"{PREFIX}to": self.date_to.isoformat() if self.date_to else "",
            f"{PREFIX}faculty": self.faculty,
            f"{PREFIX}chair": self.chair,
            f"{PREFIX}teacher": self.teacher,
            f"{PREFIX}q": self.student,
        }
        page = self.page if page is None else page
        if page and page > 1:
            params[f"{PREFIX}page"] = str(page)
        return {key: value for key, value in params.items() if value}


def _date(raw):
    try:
        return dt.date.fromisoformat(str(raw or "").strip()[:10])
    except ValueError:
        return None


def _uuid_text(raw) -> str:
    import uuid

    try:
        return str(uuid.UUID(str(raw or "").strip()))
    except (TypeError, ValueError, AttributeError):
        return ""


def _text(raw, limit=100) -> str:
    return " ".join(str(raw or "").split())[:limit]


def parse_filters(params) -> Filters:
    """``request.GET``-dən süzgəclər — yanlış dəyər səssizcə süzgəcsiz sayılır."""
    reason = str(params.get(f"{PREFIX}reason") or "").strip()
    action = str(params.get(f"{PREFIX}action") or "").strip()
    try:
        page = int(params.get(f"{PREFIX}page") or 1)
    except (TypeError, ValueError):
        page = 1
    return Filters(
        reason=reason if reason in RemovalReason.values else "",
        action=action if action in RemovalAction.values else "",
        date_from=_date(params.get(f"{PREFIX}from")),
        date_to=_date(params.get(f"{PREFIX}to")),
        faculty=_uuid_text(params.get(f"{PREFIX}faculty")),
        chair=_uuid_text(params.get(f"{PREFIX}chair")),
        teacher=_text(params.get(f"{PREFIX}teacher")),
        student=_text(params.get(f"{PREFIX}q")),
        page=max(1, min(page, MAX_PAGE)),
    )


def _unit(organization, pk, types):
    if not pk:
        return None
    model = django_apps.get_model("organizations", "OrgUnit")
    return model.objects.filter(organization=organization, pk=pk, unit_type__in=types).first()


def _day_start(day):
    return timezone.make_aware(dt.datetime.combine(day, dt.time.min))


def filtered_queryset(organization, filters: Filters):
    """Süzülmüş sətirlər (sıralama: yenidən köhnəyə). Faculty / kafedra təşkilatda tapılmasa — boş nəticə."""
    queryset = JournalRemoval.objects.filter(organization=organization)
    if filters.reason:
        queryset = queryset.filter(reason=filters.reason)
    if filters.action:
        queryset = queryset.filter(action=filters.action)
    # Tarix — yerli günün sərhədləri ilə (``__date`` UTC-yə düşüb gecə yarısı sətrini qonşu günə atmasın).
    if filters.date_from:
        queryset = queryset.filter(created_at__gte=_day_start(filters.date_from))
    if filters.date_to:
        queryset = queryset.filter(created_at__lt=_day_start(filters.date_to + dt.timedelta(days=1)))
    if filters.faculty:
        faculty = _unit(organization, filters.faculty, (OrgUnitType.FACULTY,))
        if faculty is None:
            return queryset.none()
        queryset = queryset.filter(
            Q(enrollment__offering__group_id=faculty.pk)
            | Q(enrollment__offering__group__path__startswith=f"{faculty.path or faculty.pk}/")
        )
    if filters.teacher:
        teacher_q = tolerant_q(filters.teacher, _TEACHER_FIELDS)
        if teacher_q is not None:
            queryset = queryset.filter(teacher_q)
    if filters.student:
        student_q = tolerant_q(filters.student, _STUDENT_FIELDS)
        if student_q is not None:
            queryset = queryset.filter(student_q)
    if filters.chair:
        chair = _unit(organization, filters.chair, CHAIR_TYPES)
        if chair is None:
            return queryset.none()
        queryset = queryset.filter(kafedra_q(chair, offering="enrollment__offering__", within=queryset))
    return queryset.order_by("-created_at", "-pk")


def _with_relations(queryset):
    return queryset.select_related(
        "enrollment__student__profile",
        "enrollment__offering__subject",
        "enrollment__offering__group",
        "enrollment__offering__period",
        "enrollment__offering__instructor",
        "hygiene_decision",
    )


def _teacher_name(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.get_username()


def _state(item) -> str:
    """``restored`` — «Fəndən azad» bərpa olunub; ``active`` — çıxarılma qüvvədədir."""
    decision = item.hygiene_decision
    if decision is not None and decision.reverted_at is not None:
        return "restored"
    return "active"


def serialize(item) -> dict:
    enrollment = item.enrollment
    offering = enrollment.offering
    period = offering.period
    return {
        "id": str(item.pk),
        "created_at": item.created_at,
        "student": journal_student_name(enrollment.student),
        "student_username": enrollment.student.get_username(),
        "subject_code": offering.subject.code,
        "subject_name": offering.subject.name,
        "group": getattr(offering.group, "name", "") or "",
        "period": period_label(period.name, period.academic_year) if period is not None else "",
        "teacher": _teacher_name(offering.instructor),
        "action": item.action,
        "action_label": journal_removal.action_label(item.action),
        "reason": item.reason,
        "reason_label": journal_removal.reason_label(item.reason),
        "note": item.note,
        "actor": item.actor_name,
        "state": _state(item),
        "offering_id": str(offering.pk),
    }


def reason_counts(organization, filters: Filters) -> list:
    """Səbəb üzrə saylar (səbəb süzgəci istisna — digər süzgəclərlə) — «nəyə görə» xülasəsi."""
    base = filtered_queryset(organization, replace(filters, reason="", page=1))
    counts = dict(base.order_by().values_list("reason").annotate(total=Count("pk")))
    return [
        {"value": choice.value, "label": str(choice.label), "count": counts.get(choice.value, 0)}
        for choice in RemovalReason
    ]


def page(organization, filters: Filters) -> dict:
    """Bir səhifə + ümumi say."""
    queryset = filtered_queryset(organization, filters)
    total = queryset.count()
    last_page = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    current = min(filters.page, last_page)
    start = (current - 1) * PAGE_SIZE
    rows = [serialize(item) for item in _with_relations(queryset)[start : start + PAGE_SIZE]]
    return {
        "rows": rows,
        "total": total,
        "page": current,
        "last_page": last_page,
        "has_prev": current > 1,
        "has_next": current < last_page,
        "first_index": start + 1 if rows else 0,
        "last_index": start + len(rows),
    }


def export_rows(organization, filters: Filters) -> tuple[list, bool]:
    """İxrac sətirləri (səhifələməsiz, ``MAX_EXPORT_ROWS`` tavanı) + kəsilibmi."""
    queryset = _with_relations(filtered_queryset(organization, filters))
    items = list(queryset[: MAX_EXPORT_ROWS + 1])
    truncated = len(items) > MAX_EXPORT_ROWS
    return [serialize(item) for item in items[:MAX_EXPORT_ROWS]], truncated


def unit_options(organization, types) -> list:
    model = django_apps.get_model("organizations", "OrgUnit")
    rows = model.objects.filter(organization=organization, unit_type__in=types, is_active=True).order_by("name")
    return [{"value": str(pk), "label": name} for pk, name in rows.values_list("pk", "name")]


def reason_options() -> list:
    return [{"value": choice.value, "label": str(choice.label)} for choice in RemovalReason]


def action_options() -> list:
    return [{"value": choice.value, "label": str(choice.label)} for choice in RemovalAction]


def faculty_options(organization) -> list:
    return unit_options(organization, (OrgUnitType.FACULTY,))


def chair_options(organization) -> list:
    return unit_options(organization, CHAIR_TYPES)


__all__ = [
    "MAX_EXPORT_ROWS",
    "PAGE_SIZE",
    "PREFIX",
    "Filters",
    "action_options",
    "chair_options",
    "export_rows",
    "faculty_options",
    "filtered_queryset",
    "page",
    "parse_filters",
    "reason_counts",
    "reason_options",
    "serialize",
]
