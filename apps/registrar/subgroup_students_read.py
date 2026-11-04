"""«Alt qrup tələbələri» — alt qrupdan jurnala əlavə olunmuş tələbələrin mərkəzi reyestri (sahib 2026-11-05).

Sahib: «alt qrupa əlavə olunmuş tələbələr — hansı qrupdandır əsli, hansı qrupda alt qrupdur, kredit sayı və s. —
hər şey görünsün. Və əlavə olunarkən sənədin özü də.»

Mənbə — mövcud qeydiyyat sətri :class:`~apps.registrar.models.Enrollment` (``source_group`` dolu: «alt qrupdan
əlavə», :mod:`apps.registrar.guest_roster`; intensiv kursun tələbələri də eyni yolla yazılır). Hər sətrə toplu
(sətir sayından asılı olmayan) sorğularla bağlanır:

* sənəd — :class:`GuestRosterDocument` (qorunan media linki, kim yüklədi) və ya yerləşdirmə hadisəsindəki sərəncam
  (``SubgroupPlacementEvent.order_number`` / ``order_date``); superadmin / RİM rəhbərinin sənədsiz keçidi
  (:mod:`core.superadmin_waiver` qeydi və ya ``SA-…`` sərəncamı) ayrıca «sənədsiz» vəziyyətidir;
* kredit — yerləşdirmə anında kredit qapısının saydığı dəyər (``details.credits``), hadisə yoxdursa ``Subject.ects``;
* səbəb / aktor / tarix — son ``place`` hadisəsi, yoxdursa qeydiyyatın ``added_by`` / ``added_at``-ı.

Bu modul YALNIZ OXUYUR və AKTOR QAPISI QOYMUR — qapı və struktur əhatəsi çağıranındır (kabinet bölməsi
``apps.accounts.views.subgroup_students``): ``scope`` — ``None`` (təşkilat miqyası) və ya aktorun əhatəsindəki
qrup id-lərinin queryset-i (tələbənin ÖZ qrupu VƏ YA hədəf jurnalın qrupu əhatədədirsə sətir görünür).
Süzgəclər ``ss_`` prefiksi ilə gəlir (kabinet filtr panelinin ad fəzası).
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, replace

from django.apps import apps as django_apps
from django.db.models import Exists, F, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy

from core.constants import OrgUnitType
from core.search_text import tolerant_q
from core.superadmin_waiver import NOTE_PREFIX, ORDER_PREFIX, RIM_NOTE_PREFIX

from .journal_hygiene_rows import period_label
from .journal_names import journal_student_name
from .models import (
    CourseFormat,
    Enrollment,
    EnrollmentKind,
    GuestRosterDocument,
    StudentAcademicRecord,
    SubgroupPlacementEvent,
    SubgroupPlacementKind,
)
from .offering_chairs import CHAIR_TYPES, kafedra_q

CTX = "registrar.subgroup_students"
PREFIX = "ss_"
PAGE_SIZE = 50
MAX_PAGE = 400
#: Tək Excel faylında ən çox sətir (yaddaş tavanı).
MAX_EXPORT_ROWS = 10000
DEFAULT_SORT = "-added"

STATUS_CHOICES = (
    ("active", pgettext_lazy(CTX, "Aktiv")),
    ("completed", pgettext_lazy(CTX, "Tamamlanıb")),
    ("suspended", pgettext_lazy(CTX, "Dondurulub")),
    ("removed", pgettext_lazy(CTX, "Jurnaldan çıxarılıb")),
    ("superseded", pgettext_lazy(CTX, "Köçürmə ilə əvəzlənib")),
    ("released", pgettext_lazy(CTX, "Öz jurnalından azad edilib")),
)
KIND_CHOICES = (
    ("subgroup", pgettext_lazy(CTX, "Alt qrup")),
    ("intensive", pgettext_lazy(CTX, "İntensiv kurs")),
    ("retake", pgettext_lazy(CTX, "Təkrar tədris")),
)
DOCUMENT_CHOICES = (
    ("present", pgettext_lazy(CTX, "Sənəd var (fayl və ya sərəncam)")),
    ("file", pgettext_lazy(CTX, "Fayl yüklənib")),
    ("order", pgettext_lazy(CTX, "Sərəncam nömrəsi")),
    ("waived", pgettext_lazy(CTX, "Sənədsiz — superadmin / RİM rəhbəri düzəlişi")),
    ("absent", pgettext_lazy(CTX, "Sənəd yoxdur")),
)

#: Sıralama açarı → sahələr (``-açar`` — azalan). Hər sətirdə son ayırıcı ``pk``-dır.
SORTS = {
    "added": ("added_on",),
    "student": ("student__last_name", "student__first_name", "student__username"),
    "home": ("source_group__name",),
    "target": ("offering__group__name",),
    "subject": ("offering__subject__name",),
    "teacher": ("offering__instructor__last_name", "offering__instructor__first_name"),
    "period": ("offering__period__start_date",),
    "credits": ("credits",),
    "status": ("status",),
    "actor": ("added_by__last_name", "added_by__first_name"),
}

_STUDENT_FIELDS = ("student__first_name", "student__last_name", "student__username", "student__profile__patronymic")
_TEACHER_FIELDS = (
    "offering__instructor__first_name",
    "offering__instructor__last_name",
    "offering__instructor__username",
)


@dataclass(frozen=True)
class Filters:
    q: str = ""
    faculty: str = ""
    chair: str = ""
    home_group: str = ""
    target_group: str = ""
    subject: str = ""
    teacher: str = ""
    period: str = ""
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    status: str = ""
    kind: str = ""
    document: str = ""
    sort: str = DEFAULT_SORT
    page: int = 1

    @property
    def is_filtered(self) -> bool:
        return any(value for key, value in self._filter_params().items())

    def _filter_params(self) -> dict:
        return {
            f"{PREFIX}q": self.q,
            f"{PREFIX}faculty": self.faculty,
            f"{PREFIX}chair": self.chair,
            f"{PREFIX}home": self.home_group,
            f"{PREFIX}target": self.target_group,
            f"{PREFIX}subject": self.subject,
            f"{PREFIX}teacher": self.teacher,
            f"{PREFIX}period": self.period,
            f"{PREFIX}from": self.date_from.isoformat() if self.date_from else "",
            f"{PREFIX}to": self.date_to.isoformat() if self.date_to else "",
            f"{PREFIX}status": self.status,
            f"{PREFIX}kind": self.kind,
            f"{PREFIX}doc": self.document,
        }

    def as_params(self, *, page=None, sort=None) -> dict:
        """URL parametrləri (boşlar və defolt sıralama atılır) — səhifələmə, sıralama və ixrac linkləri."""
        params = self._filter_params()
        sort = self.sort if sort is None else sort
        if sort and sort != DEFAULT_SORT:
            params[f"{PREFIX}sort"] = sort
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
    try:
        return str(uuid.UUID(str(raw or "").strip()))
    except (TypeError, ValueError, AttributeError):
        return ""


def _text(raw, limit=100) -> str:
    return " ".join(str(raw or "").split())[:limit]


def _choice(raw, choices) -> str:
    value = str(raw or "").strip()
    return value if value in {key for key, _label in choices} else ""


def _sort(raw) -> str:
    value = str(raw or "").strip()
    return value if value.lstrip("-") in SORTS else DEFAULT_SORT


def parse_filters(params) -> Filters:
    """``request.GET``-dən süzgəclər — yanlış dəyər səssizcə süzgəcsiz sayılır."""
    try:
        page = int(params.get(f"{PREFIX}page") or 1)
    except (TypeError, ValueError):
        page = 1
    return Filters(
        q=_text(params.get(f"{PREFIX}q")),
        faculty=_uuid_text(params.get(f"{PREFIX}faculty")),
        chair=_uuid_text(params.get(f"{PREFIX}chair")),
        home_group=_uuid_text(params.get(f"{PREFIX}home")),
        target_group=_uuid_text(params.get(f"{PREFIX}target")),
        subject=_uuid_text(params.get(f"{PREFIX}subject")),
        teacher=_text(params.get(f"{PREFIX}teacher")),
        period=_uuid_text(params.get(f"{PREFIX}period")),
        date_from=_date(params.get(f"{PREFIX}from")),
        date_to=_date(params.get(f"{PREFIX}to")),
        status=_choice(params.get(f"{PREFIX}status"), STATUS_CHOICES),
        kind=_choice(params.get(f"{PREFIX}kind"), KIND_CHOICES),
        document=_choice(params.get(f"{PREFIX}doc"), DOCUMENT_CHOICES),
        sort=_sort(params.get(f"{PREFIX}sort")),
        page=max(1, min(page, MAX_PAGE)),
    )


# ── Sorğu ────────────────────────────────────────────────────────────────────


def base_queryset(organization, scope=None):
    """Təşkilatın bütün «alt qrupdan əlavə» qeydiyyatları (aktorun əhatəsi ilə), annotasiyalarla."""
    queryset = Enrollment.objects.filter(organization=organization, source_group__isnull=False)
    if scope is not None:
        queryset = queryset.filter(Q(source_group_id__in=scope) | Q(offering__group_id__in=scope))
    return _annotate(queryset)


def _annotate(queryset):
    places = SubgroupPlacementEvent.objects.filter(enrollment=OuterRef("pk"), kind=SubgroupPlacementKind.PLACE)
    waiver = (
        Q(reason__contains=NOTE_PREFIX) | Q(reason__contains=RIM_NOTE_PREFIX) | Q(order_number__startswith=ORDER_PREFIX)
    )
    credit = (
        places.order_by("-created_at")
        .annotate(_credit=Cast(KeyTextTransform("credits", "details"), IntegerField()))
        .values("_credit")[:1]
    )
    return queryset.annotate(
        has_file=Exists(GuestRosterDocument.objects.filter(enrollment=OuterRef("pk"))),
        has_order=Exists(places.exclude(order_number="").exclude(order_number__startswith=ORDER_PREFIX)),
        waived=Exists(places.filter(waiver)),
        merged=Exists(Enrollment.objects.filter(superseded_by=OuterRef("pk"))),
        credits=Coalesce(
            Subquery(credit, output_field=IntegerField()),
            F("offering__subject__ects"),
            Value(0),
            output_field=IntegerField(),
        ),
        added_on=Coalesce("added_at", "created_at"),
    )


def _unit(organization, pk, types):
    if not pk:
        return None
    model = django_apps.get_model("organizations", "OrgUnit")
    return model.objects.filter(organization=organization, pk=pk, unit_type__in=types).first()


def _day_start(day):
    return timezone.make_aware(dt.datetime.combine(day, dt.time.min))


_STATUS_Q = {
    "active": Q(status=Enrollment.Status.ENROLLED),
    "completed": Q(status=Enrollment.Status.COMPLETED),
    "suspended": Q(status=Enrollment.Status.SUSPENDED),
    "removed": Q(status=Enrollment.Status.DROPPED, superseded_by__isnull=True),
    "superseded": Q(status=Enrollment.Status.DROPPED, superseded_by__isnull=False),
    "released": Q(merged=True),
}
_KIND_Q = {
    "subgroup": Q(offering__course_format=CourseFormat.REGULAR) & ~Q(kind=EnrollmentKind.RETAKE),
    "intensive": Q(offering__course_format=CourseFormat.INTENSIVE),
    "retake": Q(kind=EnrollmentKind.RETAKE),
}
_DOCUMENT_Q = {
    "present": Q(has_file=True) | Q(has_order=True),
    "file": Q(has_file=True),
    "order": Q(has_order=True),
    "waived": Q(waived=True, has_file=False, has_order=False),
    "absent": Q(waived=False, has_file=False, has_order=False),
}


def _apply_simple(queryset, filters: Filters):
    if filters.home_group:
        queryset = queryset.filter(source_group_id=filters.home_group)
    if filters.target_group:
        queryset = queryset.filter(offering__group_id=filters.target_group)
    if filters.subject:
        queryset = queryset.filter(offering__subject_id=filters.subject)
    if filters.period:
        queryset = queryset.filter(offering__period_id=filters.period)
    # Tarix — yerli günün sərhədləri ilə (``__date`` UTC-yə düşüb gecə yarısı sətrini qonşu günə atmasın).
    if filters.date_from:
        queryset = queryset.filter(added_on__gte=_day_start(filters.date_from))
    if filters.date_to:
        queryset = queryset.filter(added_on__lt=_day_start(filters.date_to + dt.timedelta(days=1)))
    for value, mapping in ((filters.status, _STATUS_Q), (filters.kind, _KIND_Q), (filters.document, _DOCUMENT_Q)):
        if value:
            queryset = queryset.filter(mapping[value])
    for raw, fields in ((filters.q, _STUDENT_FIELDS), (filters.teacher, _TEACHER_FIELDS)):
        condition = tolerant_q(raw, fields) if raw else None
        if condition is not None:
            queryset = queryset.filter(condition)
    return queryset


def filtered_queryset(organization, filters: Filters, scope=None):
    """Süzülmüş, sıralanmış sətirlər. Fakültə / kafedra təşkilatda tapılmasa — boş nəticə."""
    queryset = _apply_simple(base_queryset(organization, scope), filters)
    if filters.faculty:
        faculty = _unit(organization, filters.faculty, (OrgUnitType.FACULTY,))
        if faculty is None:
            return queryset.none()
        # Fakültə — tələbənin ÖZ (mənbə) qrupunun fakültəsi.
        queryset = queryset.filter(
            Q(source_group_id=faculty.pk) | Q(source_group__path__startswith=f"{faculty.path or faculty.pk}/")
        )
    if filters.chair:
        chair = _unit(organization, filters.chair, CHAIR_TYPES)
        if chair is None:
            return queryset.none()
        # Kafedra — hədəf jurnalın fənnini tədris edən kafedra (``offering_chairs``).
        queryset = queryset.filter(kafedra_q(chair, offering="offering__", within=queryset))
    return _ordered(queryset, filters.sort)


def _ordered(queryset, sort: str):
    descending = sort.startswith("-")
    fields = SORTS.get(sort.lstrip("-"), SORTS["added"])
    order = [F(name).desc(nulls_last=True) if descending else F(name).asc(nulls_last=True) for name in fields]
    return queryset.order_by(*order, "-pk")


def _with_relations(queryset):
    return queryset.select_related(
        "student__profile",
        "source_group",
        "offering__subject",
        "offering__group",
        "offering__period",
        "offering__instructor",
        "added_by",
    )


# ── Sətirlər ─────────────────────────────────────────────────────────────────


def _person(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.get_username()


def _latest_by_enrollment(rows) -> dict:
    """``created_at`` artan sırada gələn sətirlərdən hər qeydiyyat üçün ən sonuncusu + say."""
    latest: dict = {}
    for row in rows:
        previous = latest.get(row.enrollment_id)
        latest[row.enrollment_id] = (row, (previous[1] if previous else 0) + 1)
    return latest


def _attachments(organization, items) -> tuple[dict, dict, dict]:
    """Səhifənin sənədləri, yerləşdirmə hadisələri və tələbələrin CARİ qrupları — üç toplu sorğu."""
    ids = [item.pk for item in items]
    if not ids:
        return {}, {}, {}
    documents = _latest_by_enrollment(
        GuestRosterDocument.objects.filter(organization=organization, enrollment_id__in=ids).order_by("created_at")
    )
    events = _latest_by_enrollment(
        SubgroupPlacementEvent.objects.filter(
            organization=organization, enrollment_id__in=ids, kind=SubgroupPlacementKind.PLACE
        ).order_by("created_at")
    )
    current: dict = {}
    records = (
        StudentAcademicRecord.objects.filter(
            organization=organization, student_id__in={item.student_id for item in items}, is_active=True
        )
        .order_by("student_id", "-created_at")
        .values_list("student_id", "group_id", "group__name")
    )
    for student_id, group_id, group_name in records:
        current.setdefault(student_id, (group_id, group_name or ""))
    return documents, events, current


def status_value(item) -> str:
    if item.status == Enrollment.Status.DROPPED:
        return "superseded" if item.superseded_by_id else "removed"
    return {
        Enrollment.Status.ENROLLED: "active",
        Enrollment.Status.COMPLETED: "completed",
        Enrollment.Status.SUSPENDED: "suspended",
    }.get(item.status, "active")


def label_of(value, choices) -> str:
    return str(dict(choices).get(value, value or ""))


def kind_value(item) -> str:
    if item.offering.course_format == CourseFormat.INTENSIVE:
        return "intensive"
    return "retake" if item.kind == EnrollmentKind.RETAKE else "subgroup"


def _document(item, doc_entry, event) -> dict:
    from core.media_urls import protected_media_url

    doc, count = doc_entry if doc_entry else (None, 0)
    order_number = getattr(event, "order_number", "") or ""
    is_auto_order = order_number.startswith(ORDER_PREFIX)
    if doc is not None:
        state = "file"
    elif order_number and not is_auto_order:
        state = "order"
    elif item.waived:
        state = "waived"
    else:
        state = "none"
    return {
        "state": state,
        "label": label_of({"none": "absent"}.get(state, state), DOCUMENT_CHOICES),
        "url": protected_media_url(doc.document) if doc is not None else "",
        "count": count,
        "uploaded_by": getattr(doc, "uploaded_by_name", "") or "",
        "uploaded_at": getattr(doc, "created_at", None),
        "order_number": order_number,
        "order_date": getattr(event, "order_date", None),
    }


def serialize(item, *, doc_entry=None, event_entry=None, current=None) -> dict:
    offering = item.offering
    period = offering.period
    event = event_entry[0] if event_entry else None
    doc = doc_entry[0] if doc_entry else None
    current_id, current_name = current or (None, "")
    status = status_value(item)
    kind = kind_value(item)
    target = getattr(offering.group, "name", "") or ""
    return {
        "id": str(item.pk),
        "student": journal_student_name(item.student),
        "student_username": item.student.get_username(),
        "home_group": getattr(item.source_group, "name", "") or "",
        "current_group": current_name,
        "moved_since": bool(current_id and current_id != item.source_group_id),
        "target_group": target or (pgettext(CTX, "İntensiv kurs") if kind == "intensive" else ""),
        "subject_code": offering.subject.code,
        "subject_name": offering.subject.name,
        "teacher": _person(offering.instructor),
        "period": period_label(period.name, period.academic_year) if period is not None else "",
        "offering_id": str(offering.pk),
        "status": status,
        "status_label": label_of(status, STATUS_CHOICES),
        "released": bool(item.merged),
        "kind": kind,
        "kind_label": label_of(kind, KIND_CHOICES),
        "credits": int(item.credits or 0),
        "reason": (getattr(event, "reason", "") or getattr(doc, "note", "") or "").strip(),
        "document": _document(item, doc_entry, event),
        "actor": _person(item.added_by) or getattr(event, "actor_name", "") or getattr(doc, "uploaded_by_name", ""),
        "added_on": item.added_on,
    }


def _rows(organization, items) -> list:
    documents, events, current = _attachments(organization, items)
    return [
        serialize(
            item,
            doc_entry=documents.get(item.pk),
            event_entry=events.get(item.pk),
            current=current.get(item.student_id),
        )
        for item in items
    ]


def page(organization, filters: Filters, scope=None) -> dict:
    """Bir səhifə + ümumi say (sorğu sayı sətir sayından asılı deyil)."""
    queryset = filtered_queryset(organization, filters, scope)
    total = queryset.count()
    last_page = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    current = min(filters.page, last_page)
    start = (current - 1) * PAGE_SIZE
    items = list(_with_relations(queryset)[start : start + PAGE_SIZE])
    rows = _rows(organization, items)
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


def export_rows(organization, filters: Filters, scope=None) -> tuple[list, bool]:
    """İxrac sətirləri (səhifələməsiz, ``MAX_EXPORT_ROWS`` tavanı) + kəsilibmi."""
    queryset = _with_relations(filtered_queryset(organization, replace(filters, page=1), scope))
    items = list(queryset[: MAX_EXPORT_ROWS + 1])
    truncated = len(items) > MAX_EXPORT_ROWS
    return _rows(organization, items[:MAX_EXPORT_ROWS]), truncated


# ── Seçim siyahıları ─────────────────────────────────────────────────────────


def _pairs(rows) -> list:
    return [{"value": str(pk), "label": label} for pk, label in rows if pk]


def unit_options(organization, types) -> list:
    model = django_apps.get_model("organizations", "OrgUnit")
    rows = model.objects.filter(organization=organization, unit_type__in=types, is_active=True).order_by("name")
    return _pairs(rows.values_list("pk", "name"))


def faculty_options(organization) -> list:
    return unit_options(organization, (OrgUnitType.FACULTY,))


def chair_options(organization) -> list:
    return unit_options(organization, CHAIR_TYPES)


def _distinct(organization, scope, pk_field, *label_fields, order=None):
    queryset = Enrollment.objects.filter(organization=organization, source_group__isnull=False)
    if scope is not None:
        queryset = queryset.filter(Q(source_group_id__in=scope) | Q(offering__group_id__in=scope))
    queryset = queryset.exclude(**{f"{pk_field}__isnull": True})
    return queryset.order_by(*(order or label_fields)).values_list(pk_field, *label_fields).distinct()


def home_group_options(organization, scope=None) -> list:
    return _pairs(_distinct(organization, scope, "source_group_id", "source_group__name"))


def target_group_options(organization, scope=None) -> list:
    return _pairs(_distinct(organization, scope, "offering__group_id", "offering__group__name"))


def subject_options(organization, scope=None) -> list:
    rows = _distinct(organization, scope, "offering__subject_id", "offering__subject__name", "offering__subject__code")
    return [{"value": str(pk), "label": f"{name} ({code})" if code else name} for pk, name, code in rows if pk]


def period_options(organization, scope=None) -> list:
    rows = _distinct(
        organization,
        scope,
        "offering__period_id",
        "offering__period__name",
        "offering__period__academic_year",
        "offering__period__start_date",
        order=("-offering__period__start_date",),
    )
    return [{"value": str(pk), "label": period_label(name, year)} for pk, name, year, _start in rows if pk]


def choice_options(choices) -> list:
    return [{"value": value, "label": str(label)} for value, label in choices]


__all__ = [
    "DEFAULT_SORT",
    "DOCUMENT_CHOICES",
    "KIND_CHOICES",
    "MAX_EXPORT_ROWS",
    "PAGE_SIZE",
    "PREFIX",
    "SORTS",
    "STATUS_CHOICES",
    "Filters",
    "base_queryset",
    "chair_options",
    "choice_options",
    "export_rows",
    "faculty_options",
    "filtered_queryset",
    "home_group_options",
    "label_of",
    "page",
    "parse_filters",
    "period_options",
    "serialize",
    "subject_options",
    "target_group_options",
]
