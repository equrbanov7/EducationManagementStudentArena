"""«Lab qrupları» kabinet bölməsi — jurnal seçimi, süzgəclər, KPI (sahib 2026-11-07, yalnız OXU).

Sahib: «lab qruplarını yarat … sidebarda qruplar olan yerdə yerləşsin … mövcud dizayna uyğun modern UX/UI».
Əvvəl ekran yalnız jurnal başlığındakı «Lab qrupları» çipindən açılırdı (/jurnal/<id>/lab-qruplari/). İndi kabinetin
sol menyusundakı bölmədir: jurnalı seç → qruplar, qrupsuz tələbələr, köçürmə. Bu modul yalnız SEÇİLƏ BİLƏN
jurnalları verir; qrupların özünü dəyişən qaydalar (yaratmaq, ad, yerləşdirmə, silmə, kilid) dəyişmədən
:mod:`apps.registrar.lab_groups_manage`-dədir və hər yazıda orada yenidən yoxlanılır.

ƏHATƏ (:func:`resolve_scope`, ``lab_groups_manage.can_manage`` ilə EYNİ mənbələr, fail-closed):

* superadmin / RİM rəhbəri / təşkilat sahibi — təşkilatın bütün jurnalları;
* ``workload.distribute`` (kafedra müdiri) — təşkilat miqyasında hamısı, UNIT rolunda isə kafedrası əhatədə olan
  açılışlar (``offering_chairs`` — «Praktiki məşğələ» açarı ilə eyni tərif);
* müəllim — canlı ``grade.input`` səlahiyyəti varsa öz açılışları və «lab» növünü daşıyan aktiv payları.

Siyahıda yalnız laboratoriya saatı olan jurnallar görünür (:func:`lab_capable`): plan / dərs yükü / dil səviyyəsi /
cədvəl / balı olan lab dərsi (``activity_kinds.bits_expression``) VƏ YA artıq lab qrupu, qruplu tələbəsi və ya lab
dərsi olan jurnal. Ləğv edilmiş açılış (``is_active=False``) çıxır — ona yazı getmir.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace

from django.apps import apps as django_apps
from django.db.models import Count, Exists, F, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, Greatest
from django.utils.translation import pgettext, pgettext_lazy

from core.constants import OrgUnitType
from core.search_text import tolerant_q

from . import activity_kinds
from . import lab_groups_manage as service
from .journal_hygiene_rows import period_label
from .models import CourseOffering, Enrollment, JournalShare, LabGroup, Lesson, LessonKind
from .offering_chairs import CHAIR_TYPES, kafedra_q, offering_chairs

CTX = "registrar.lab_groups"
PREFIX = "lg_"
PAGE_SIZE = 20
FACULTY_TYPES = (OrgUnitType.FACULTY,)
_PRIVILEGED_FLAGS = ("is_superuser", "is_superadmin", "is_ikt_rehber")
_SEARCH_FIELDS = (
    "subject__name",
    "subject__code",
    "group__name",
    "instructor__first_name",
    "instructor__last_name",
    "instructor__username",
)

STATUS_SPLIT = "split"
STATUS_UNSPLIT = "unsplit"
STATUS_PENDING = "pending"
STATUS_CHOICES = (
    (STATUS_SPLIT, pgettext_lazy(CTX, "Qruplara bölünüb")),
    (STATUS_UNSPLIT, pgettext_lazy(CTX, "Bölünməyib")),
    (STATUS_PENDING, pgettext_lazy(CTX, "Qrupsuz tələbəsi var")),
)


# ── Əhatə ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Scope:
    """Aktorun jurnal əhatəsi: ``org_wide`` — hamısı; ``chair_units`` — kafedra alt-ağacı; ``own`` — öz / pay."""

    org_wide: bool = False
    chair_units: frozenset = frozenset()
    own: bool = False

    @property
    def has_access(self) -> bool:
        return self.org_wide or bool(self.chair_units) or self.own

    @property
    def is_personal(self) -> bool:
        """Yalnız öz jurnalları (müəllim) — struktur süzgəcləri (fakültə / kafedra / müəllim) lazım deyil."""
        return not self.org_wide and not self.chair_units


NO_ACCESS = Scope()


def _instructor_ok(user, organization) -> bool:
    """Canlı ``grade.input`` səlahiyyəti (``journal_shares._has_instructor_authority`` ilə eyni: snapshot → sorğu)."""
    from .integrity import is_authorized_instructor
    from .journal_access import _snapshot_grade_input

    verdict = _snapshot_grade_input(user, organization)
    if verdict is not None:
        return verdict
    return is_authorized_instructor(organization=organization, instructor=user)


def resolve_scope(user, organization) -> Scope:
    """Sorğu üçün əhatə; heç vaxt exception atmır (fail-closed)."""
    from .journal_scope import permission_scope_for

    if organization is None or not getattr(user, "is_authenticated", False):
        return NO_ACCESS
    if any(getattr(user, flag, False) for flag in _PRIVILEGED_FLAGS) or organization.owner_id == user.pk:
        return Scope(org_wide=True)
    chair = permission_scope_for(user, organization, service.CHAIR_PERMISSION)
    if chair.has_structure_access and chair.is_org_wide:
        return Scope(org_wide=True)
    units = frozenset()
    if chair.has_structure_access:
        units = frozenset(
            str(pk)
            for pk in django_apps.get_model("organizations", "OrgUnit")
            .objects.filter(organization_id=organization.pk)
            .filter(chair.unit_subtree_q())
            .values_list("pk", flat=True)
        )
    return Scope(chair_units=units, own=_instructor_ok(user, organization))


def _own_q(user) -> Q:
    """Müəllimin öz açılışları + «lab» növlü (və ya növsüz — bütöv) aktiv payları."""
    shares = JournalShare.objects.filter(teacher_id=user.pk, is_active=True).filter(
        Q(kinds=[]) | Q(kinds__contains=[LessonKind.LAB])
    )
    return Q(instructor_id=user.pk) | Q(pk__in=shares.values("offering_id"))


def _scoped(user, organization, scope: Scope, base):
    if scope.org_wide:
        return base
    condition = Q(pk__in=[])
    if scope.own:
        condition |= _own_q(user)
    if scope.chair_units:
        chairs = offering_chairs(base, organization.pk)
        ids = [pk for pk, found in chairs.items() if set(found) & scope.chair_units]
        if ids:
            condition |= Q(pk__in=ids)
    return base.filter(condition)


def lab_capable(queryset):
    """Laboratoriya saatı olan (və ya artıq lab qruplarına bölünmüş) jurnallar."""
    pk = OuterRef("pk")
    bits = activity_kinds.bits_expression().bitand(Value(activity_kinds.LAB_BIT))
    return queryset.annotate(lg_lab=bits).filter(
        Q(lg_lab__gt=0)
        | Exists(LabGroup.objects.filter(offering_id=pk))
        | Exists(Lesson.objects.filter(offering_id=pk, kind=LessonKind.LAB))
        | Exists(Enrollment.objects.filter(offering_id=pk, lab_group__isnull=False))
    )


def teaches_lab(user, organization) -> bool:
    """Ən azı bir lab saatlı öz / «lab» paylı aktiv jurnalı varmı (TƏK ``EXISTS``; ``grade.input`` çağıranda yoxlanır)."""
    if organization is None or not getattr(user, "is_authenticated", False):
        return False
    own = CourseOffering.objects.filter(organization_id=organization.pk, is_active=True).filter(_own_q(user))
    return lab_capable(own).exists()


def visible(user, organization, scope: Scope | None = None) -> bool:
    """Bölmə görünürmü: təşkilat / kafedra əhatəsi və ya ən azı bir lab saatlı öz jurnalı."""
    scope = scope or resolve_scope(user, organization)
    if scope.org_wide or scope.chair_units:
        return True
    return scope.own and teaches_lab(user, organization)


# ── Süzgəclər ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Filters:
    q: str = ""
    period: str = ""
    faculty: str = ""
    chair: str = ""
    group: str = ""
    teacher: str = ""
    status: str = ""
    page: int = 1
    offering: str = ""

    @property
    def is_filtered(self) -> bool:
        return any((self.q, self.faculty, self.chair, self.group, self.teacher, self.status))

    def as_params(self, **overrides) -> dict:
        state = replace(self, **overrides)
        params = {
            f"{PREFIX}q": state.q,
            f"{PREFIX}period": state.period,
            f"{PREFIX}faculty": state.faculty,
            f"{PREFIX}chair": state.chair,
            f"{PREFIX}group": state.group,
            f"{PREFIX}teacher": state.teacher,
            f"{PREFIX}status": state.status,
            f"{PREFIX}page": str(state.page) if state.page > 1 else "",
            f"{PREFIX}offering": state.offering,
        }
        return {key: value for key, value in params.items() if value}


def _uuid_text(raw) -> str:
    try:
        return str(uuid.UUID(str(raw or "").strip()))
    except (TypeError, ValueError, AttributeError):
        return ""


def _int_text(raw) -> str:
    text = str(raw or "").strip()
    return text if text.isdigit() else ""


def _page_number(raw) -> int:
    text = str(raw or "").strip()
    return max(1, min(int(text), 10_000)) if text.isdigit() else 1


def default_period_id(organization, offering_id="") -> str:
    """Seçilmiş jurnalın semestri, yoxsa cari semestr, yoxsa ən yenisi."""
    if offering_id:
        found = (
            CourseOffering.objects.filter(organization_id=organization.pk, pk=offering_id)
            .values_list("period_id", flat=True)
            .first()
        )
        if found:
            return str(found)
    periods = django_apps.get_model("organizations", "AcademicPeriod").objects.filter(organization_id=organization.pk)
    found = periods.filter(is_current=True).values_list("pk", flat=True).first()
    found = found or periods.order_by("-start_date").values_list("pk", flat=True).first()
    return str(found) if found else ""


def parse_filters(params, organization) -> Filters:
    offering = _uuid_text(params.get(f"{PREFIX}offering"))
    period = _uuid_text(params.get(f"{PREFIX}period")) or default_period_id(organization, offering)
    status = str(params.get(f"{PREFIX}status") or "").strip()
    return Filters(
        q=" ".join(str(params.get(f"{PREFIX}q") or "").split())[:100],
        period=period,
        faculty=_uuid_text(params.get(f"{PREFIX}faculty")),
        chair=_uuid_text(params.get(f"{PREFIX}chair")),
        group=_uuid_text(params.get(f"{PREFIX}group")),
        teacher=_int_text(params.get(f"{PREFIX}teacher")),
        status=status if status in dict(STATUS_CHOICES) else "",
        page=_page_number(params.get(f"{PREFIX}page")),
        offering=offering,
    )


def _unit(organization, pk, types):
    if not pk:
        return None
    model = django_apps.get_model("organizations", "OrgUnit")
    return model.objects.filter(organization_id=organization.pk, pk=pk, unit_type__in=types).first()


def base_queryset(user, organization, scope: Scope, filters: Filters):
    """Əhatə + semestr (seçim siyahıları da bundan qurulur — lab annotasiyası yoxdur)."""
    base = CourseOffering.objects.filter(organization_id=organization.pk, is_active=True)
    if filters.period:
        base = base.filter(period_id=filters.period)
    return _scoped(user, organization, scope, base)


def _apply(queryset, organization, filters: Filters):
    if filters.faculty:
        faculty = _unit(organization, filters.faculty, FACULTY_TYPES)
        if faculty is None:
            return queryset.none()
        queryset = queryset.filter(Q(group_id=faculty.pk) | Q(group__path__startswith=f"{faculty.path or faculty.pk}/"))
    if filters.chair:
        chair = _unit(organization, filters.chair, CHAIR_TYPES)
        if chair is None:
            return queryset.none()
        queryset = queryset.filter(kafedra_q(chair, within=queryset))
    if filters.group:
        queryset = queryset.filter(group_id=filters.group)
    if filters.teacher:
        queryset = queryset.filter(instructor_id=int(filters.teacher))
    condition = tolerant_q(filters.q, _SEARCH_FIELDS) if filters.q else None
    if condition is not None:
        queryset = queryset.filter(condition)
    return queryset


def _count(rows):
    """``Enrollment`` alt sorğusunun sayı (``offering`` üzrə)."""
    return Coalesce(
        Subquery(rows.order_by().values("offering_id").annotate(n=Count("pk")).values("n")[:1]),
        Value(0),
        output_field=IntegerField(),
    )


def annotate_rows(queryset):
    pk = OuterRef("pk")
    active = Enrollment.objects.filter(offering_id=pk, status=Enrollment.Status.ENROLLED)
    named = LabGroup.objects.filter(offering_id=pk).order_by().values("offering_id").annotate(n=Count("pk"))
    placed = active.filter(lab_group__isnull=False).order_by().values("offering_id")
    placed_groups = placed.annotate(n=Count("lab_group", distinct=True)).values("n")[:1]
    return queryset.annotate(
        lg_students=_count(active),
        lg_grouped=_count(active.filter(lab_group__isnull=False)),
        lg_groups=Greatest(
            Coalesce(Subquery(named.values("n")[:1]), Value(0)),
            Coalesce(Subquery(placed_groups), Value(0)),
            output_field=IntegerField(),
        ),
    )


_STATUS_Q = {
    STATUS_SPLIT: Q(lg_groups__gt=0),
    STATUS_UNSPLIT: Q(lg_groups=0),
    STATUS_PENDING: Q(lg_groups__gt=0, lg_students__gt=F("lg_grouped")),
}


def journal_queryset(user, organization, scope: Scope, filters: Filters):
    """Süzülmüş, lab saatlı, sayğaclı jurnallar (status süzgəcindən ƏVVƏL — KPI bundan sayılır)."""
    queryset = _apply(base_queryset(user, organization, scope, filters), organization, filters)
    return annotate_rows(lab_capable(queryset))


def page(user, organization, scope: Scope, filters: Filters) -> dict:
    """Siyahı səhifəsi + KPI (iki sorğu: aqreqat və səhifə)."""
    if not scope.has_access:
        return {"rows": [], "total": 0, "page": 1, "has_prev": False, "has_next": False, "kpis": {}}
    queryset = journal_queryset(user, organization, scope, filters)
    pending = Q(lg_groups__gt=0, lg_students__gt=F("lg_grouped"))
    kpis = queryset.aggregate(
        total=Count("pk"),
        split=Count("pk", filter=Q(lg_groups__gt=0)),
        pending=Count("pk", filter=pending),
        ungrouped=Sum(F("lg_students") - F("lg_grouped"), filter=Q(lg_groups__gt=0)),
    )
    if filters.status:
        queryset = queryset.filter(_STATUS_Q[filters.status])
        total = queryset.count()
    else:
        total = kpis["total"] or 0
    last_page = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    number = min(filters.page, last_page)
    start = (number - 1) * PAGE_SIZE
    rows = list(
        queryset.select_related("subject", "group", "instructor", "period").order_by(
            "group__name", "subject__name", "pk"
        )[start : start + PAGE_SIZE]
    )
    return {
        "rows": [_row(item) for item in rows],
        "total": total,
        "page": number,
        "first_index": start + 1 if total else 0,
        "last_index": start + len(rows),
        "has_prev": number > 1,
        "has_next": number < last_page,
        "kpis": {key: int(value or 0) for key, value in kpis.items()},
    }


def _teacher_name(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.get_username()


def _row(offering) -> dict:
    students, grouped = offering.lg_students, offering.lg_grouped
    return {
        "id": str(offering.pk),
        "subject": offering.subject.name,
        "code": offering.subject.code or "",
        "group": offering.group.name if offering.group_id else "",
        "teacher": _teacher_name(offering.instructor),
        "period": period_label(offering.period.name, offering.period.academic_year) if offering.period_id else "",
        "students": students,
        "grouped": grouped,
        "ungrouped": max(0, students - grouped) if offering.lg_groups else 0,
        "groups": offering.lg_groups,
        "pct": round(grouped * 100 / students) if students and offering.lg_groups else 0,
    }


# ── Seçim siyahıları ─────────────────────────────────────────────────────────


def _pairs(rows) -> list:
    return [{"value": str(pk), "label": label} for pk, label in rows if pk and label]


def period_options(organization) -> list:
    rows = (
        django_apps.get_model("organizations", "AcademicPeriod")
        .objects.filter(organization_id=organization.pk)
        .order_by("-start_date")
        .values_list("pk", "name", "academic_year")
    )
    return [{"value": str(pk), "label": period_label(name, year)} for pk, name, year in rows]


def unit_options(organization, types, *, within=None) -> list:
    rows = django_apps.get_model("organizations", "OrgUnit").objects.filter(
        organization_id=organization.pk, unit_type__in=types, is_active=True
    )
    if within is not None:
        rows = rows.filter(pk__in=list(within))
    return _pairs(rows.order_by("name").values_list("pk", "name"))


def group_options(base) -> list:
    rows = base.exclude(group__isnull=True).order_by("group__name").values_list("group_id", "group__name").distinct()
    return _pairs(rows)


def teacher_options(base) -> list:
    rows = (
        base.exclude(instructor__isnull=True)
        .order_by("instructor__last_name", "instructor__first_name")
        .values_list("instructor_id", "instructor__first_name", "instructor__last_name", "instructor__username")
        .distinct()
    )
    return [
        {"value": str(pk), "label": " ".join(part for part in (first, last) if part).strip() or username}
        for pk, first, last, username in rows
    ]


def status_options() -> list:
    return [{"value": value, "label": str(label)} for value, label in STATUS_CHOICES]


# ── Seçilmiş jurnal ──────────────────────────────────────────────────────────


def selected_offering(user, organization, offering_id):
    """``(offering, səbəb)`` — idarə edə bilmirsə ``(None, mətn)``; id yoxdursa ``(None, "")``."""
    if not offering_id:
        return None, ""
    offering = (
        CourseOffering.objects.select_related("organization", "period", "subject", "group", "instructor")
        .filter(organization_id=organization.pk, pk=offering_id)
        .first()
    )
    if offering is None or not service.can_manage(user, offering):
        return None, pgettext(CTX, "Bu jurnalın laboratoriya qruplarını idarə etmək səlahiyyətiniz yoxdur.")
    return offering, ""


def offering_summary(offering) -> dict:
    return {
        "id": str(offering.pk),
        "subject": offering.subject.name,
        "code": offering.subject.code or "",
        "group": offering.group.name if offering.group_id else "",
        "teacher": _teacher_name(offering.instructor),
        "period": period_label(offering.period.name, offering.period.academic_year) if offering.period_id else "",
    }


__all__ = [
    "CHAIR_TYPES",
    "CTX",
    "FACULTY_TYPES",
    "NO_ACCESS",
    "PAGE_SIZE",
    "PREFIX",
    "STATUS_CHOICES",
    "Filters",
    "Scope",
    "base_queryset",
    "default_period_id",
    "group_options",
    "journal_queryset",
    "lab_capable",
    "offering_summary",
    "page",
    "parse_filters",
    "period_options",
    "resolve_scope",
    "selected_offering",
    "status_options",
    "teacher_options",
    "teaches_lab",
    "unit_options",
    "visible",
]
