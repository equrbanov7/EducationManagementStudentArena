"""«Bölmə imtahanları» — əhatə (scope), imtahan↔vahid bağlantısı, filtr və aqreqat sorğuları.

OXU-ONLY. Bütün sorğular təşkilatla (tenant) və dekanın/müdirin alt-ağacı ilə daraldılır.

ƏHATƏ (``resolve_unit_subtree``)
  * ``exam.view`` açarını daşıyan UNIT rolunun ``scope_unit`` alt-ağacı (P1-11 qaydası).
  * Açar ORG-wide həll olunursa (məs. ``member`` / imtahan mərkəzi rolu da var) bölmə
    BÜTÜN təşkilatı açmır — bu bölmə «mənim vahidim»dir: yalnız UNIT rollarının
    ``scope_unit``-i götürülür; yoxdursa ``None`` (fail-closed, «əhatə yoxdur»).
    2026-10-14-ə qədər bu halda bölmə səssizcə BOŞ qalırdı.

BAĞLANTI (``exam_subtree_q``) — imtahanın ÖZ bağlantısı:
  fənnin kafedrası · kursun vahidi · təyin olunmuş reyestr qrupu · köhnə kohortun
  vahidi · müəllifin həmin fənni alt-ağacdakı qrupa OXUTDUĞU açılış (CourseOffering).
  Sahibi bilinməyən imtahan (fənnin kafedrası və kursun vahidi yoxdur) əlavə olaraq
  müəllifin «ev» (ƏSAS) üzvlüyü ilə bağlanır — B19 qaydası (əlavə Forma 1 üzvlüyü sayılmır).
"""

from __future__ import annotations

from datetime import date, datetime, time

from django.db.models import Avg, Case, CharField, Count, Exists, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.accounts.services.statistics_metrics._shared import PASS_MARK, score_pct_expression
from core.constants import OrgUnitType, RoleScopeType
from core.permissions import has_permission
from core.search_text import tolerant_q

FINISHED = ("submitted", "expired")
STATUS_KEYS = ("active", "scheduled", "finished", "draft")
KIND_KEYS = ("final", "midterm", "quiz", "practice", "placement")
FORM_KEYS = ("test", "written", "coding")
#: Orta nəticə / keçmə faizi yalnız ən azı bu qədər bitirən olduqda göstərilir —
#: 1–2 tələbəlik imtahanda «orta bal» fərdi balı açardı (məxfilik).
MIN_GROUP_FOR_AVG = 3
CHAIR_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)
SORT_KEYS = ("title", "subject", "author", "date", "participants", "avg")
DEFAULT_SORT = "-date"


# --------------------------------------------------------------------------- #
# Əhatə
# --------------------------------------------------------------------------- #


def _unit_role_unit_ids(user, org) -> set:
    """ORG-wide həll olunan halda: yalnız ``exam.view`` daşıyan UNIT rollarının vahidləri."""
    from apps.organizations.models import Membership

    rows = Membership.objects.filter(
        user=user,
        organization=org,
        is_active=True,
        role__is_active=True,
        role__organization=org,
        role__scope_type=RoleScopeType.UNIT,
        scope_unit__isnull=False,
    ).values_list("scope_unit_id", "role__permissions")
    return {unit_id for unit_id, perms in rows if has_permission(list(perms or []), "exam.view")}


def resolve_unit_subtree(request, org):
    """Alt-ağac ``OrgUnit`` queryset-i və ya ``None`` (əhatə yoxdur — fail-closed)."""
    from apps.organizations.models import OrgUnit
    from apps.organizations.public import get_permission_scope

    scope = get_permission_scope(request.user, org, "exam.view", request=request)
    units = OrgUnit.objects.filter(organization=org)
    if scope.is_unit_scoped:
        return units.filter(scope.unit_subtree_q())
    if not scope.is_org_wide:
        return None
    unit_ids = _unit_role_unit_ids(request.user, org)
    roots = list(units.filter(pk__in=unit_ids, is_active=True).values_list("pk", "path"))
    if not roots:
        return None
    condition = Q(pk__in=[pk for pk, _ in roots])
    for _pk, path in roots:
        if path:
            condition |= Q(path__startswith=f"{path}/")
    return units.filter(condition)


# --------------------------------------------------------------------------- #
# Bağlantı
# --------------------------------------------------------------------------- #


def _ownerless_q() -> Q:
    """Sahibi (kafedra/kurs vahidi) bilinməyən imtahan."""
    return Q(subject__chair_unit__isnull=True) & (Q(course__isnull=True) | Q(course__unit__isnull=True))


def _home_authors(org, unit_ids):
    """«Ev» üzvlüyü ``unit_ids``-də olan müəlliflər (B19: əsas üzvlük; əsassız köhnə hesabda hər üzvlük)."""
    from apps.organizations.models import Membership

    active = Membership.objects.filter(organization=org, is_active=True)
    with_unit_primary = active.filter(is_primary=True, scope_unit__isnull=False).values("user_id")
    return (
        active.filter(scope_unit__in=unit_ids)
        .filter(Q(is_primary=True) | ~Q(user_id__in=with_unit_primary))
        .values("user_id")
    )


def exam_subtree_q(org, subtree_ids) -> Q:
    """İmtahan ``subtree_ids`` (OrgUnit pk subquery) alt-ağacına aiddirmi."""
    from django.apps import apps as django_apps

    from apps.exams.models import Exam

    # registrar modellərinə birbaşa import yoxdur (kontekst qapısı) — model registr ilə alınır.
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")

    group_link = Exam.allowed_units.through.objects.filter(exam_id=OuterRef("pk"), orgunit_id__in=subtree_ids)
    cohort_link = Exam.allowed_groups.through.objects.filter(
        exam_id=OuterRef("pk"), studentgroup__org_unit_id__in=subtree_ids
    )
    offering_link = CourseOffering.objects.filter(
        organization=org,
        subject_id=OuterRef("subject_id"),
        instructor_id=OuterRef("author_id"),
        group_id__in=subtree_ids,
    )
    own_link = (
        Q(subject__chair_unit__in=subtree_ids)
        | Q(course__unit__in=subtree_ids)
        | Exists(group_link)
        | Exists(cohort_link)
        | (Q(subject__isnull=False) & Exists(offering_link))
    )
    return own_link | (_ownerless_q() & Q(author_id__in=_home_authors(org, subtree_ids)))


def chair_q(org, chair_id) -> Q:
    """«Kafedra» filtri: fənnin kafedrası və ya (sahibsiz imtahanda) müəllifin ev kafedrası."""
    return Q(subject__chair_unit_id=chair_id) | (_ownerless_q() & Q(author_id__in=_home_authors(org, [chair_id])))


# --------------------------------------------------------------------------- #
# Annotasiyalar
# --------------------------------------------------------------------------- #


def status_expression(now=None):
    """Hesablanmış status: finished → draft → scheduled → active (saxlanılmır)."""
    now = now or timezone.now()
    return Case(
        When(end_datetime__lt=now, then=Value("finished")),
        When(is_active=False, then=Value("draft")),
        When(start_datetime__gt=now, then=Value("scheduled")),
        default=Value("active"),
        output_field=CharField(),
    )


def _attempt_subquery(aggregate, *, finished_only=True, extra=None):
    from apps.exams.models import ExamAttempt

    qs = ExamAttempt.objects.filter(exam_id=OuterRef("pk"), is_trial=False)
    if finished_only:
        qs = qs.filter(status__in=FINISHED)
    qs = qs.annotate(ue_pct=score_pct_expression())
    if extra is not None:
        qs = qs.filter(extra)
    return Subquery(qs.order_by().values("exam_id").annotate(v=aggregate).values("v")[:1])


def annotate_rows(qs):
    """Səhifə sətirləri üçün sayğaclar — korrelyasiyalı subquery (sətir başına sorğu YOX)."""
    from apps.exams.models import ExamQuestion

    questions = (
        ExamQuestion.objects.filter(exam_id=OuterRef("pk"))
        .order_by()
        .values("exam_id")
        .annotate(v=Count("pk"))
        .values("v")[:1]
    )
    return qs.annotate(
        ue_questions=Coalesce(Subquery(questions), 0, output_field=IntegerField()),
        ue_participants=Coalesce(
            _attempt_subquery(Count("user", distinct=True), finished_only=False), 0, output_field=IntegerField()
        ),
        ue_finished=Coalesce(_attempt_subquery(Count("user", distinct=True)), 0, output_field=IntegerField()),
        ue_attempts=Coalesce(_attempt_subquery(Count("pk")), 0, output_field=IntegerField()),
        ue_passed=Coalesce(
            _attempt_subquery(Count("pk"), extra=Q(ue_pct__gte=PASS_MARK)), 0, output_field=IntegerField()
        ),
        ue_avg=_attempt_subquery(Avg("ue_pct")),
    )


# --------------------------------------------------------------------------- #
# Filtrlər
# --------------------------------------------------------------------------- #


def _parse_date(raw) -> date | None:
    try:
        return date.fromisoformat((raw or "").strip()[:10])
    except ValueError:
        return None


def read_filters(request) -> dict:
    get = request.GET

    def pick(name, allowed):
        value = (get.get(name) or "").strip()
        return value if value in allowed else ""

    sort = (get.get("ue_sort") or "").strip()
    if sort.lstrip("-") not in SORT_KEYS:
        sort = DEFAULT_SORT
    return {
        "search": (get.get("ue_q") or get.get("unit_exam_q") or "").strip()[:120],
        "chair": (get.get("ue_chair") or "").strip()[:64],
        "kind": pick("ue_kind", KIND_KEYS),
        "form": pick("ue_form", FORM_KEYS),
        "status": pick("ue_status", STATUS_KEYS),
        "period": (get.get("ue_period") or "").strip()[:64],
        "date_from": _parse_date(get.get("ue_from")),
        "date_to": _parse_date(get.get("ue_to")),
        "sort": sort,
    }


def _aware(day: date, *, end=False) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.max if end else time.min))


def apply_filters(qs, org, filters, *, chair_ids, periods):
    """İstifadəçi filtrlərini tətbiq edir. Naməlum kafedra/dövr id-si SƏSSİZ atılır (əhatədən çıxmır)."""
    search_q = tolerant_q(
        filters["search"],
        (
            "title",
            "author__first_name",
            "author__last_name",
            "author__username",
            "subject__name",
            "subject__code",
            "course__title",
        ),
    )
    if search_q is not None:
        qs = qs.filter(search_q)
    if filters["chair"] and filters["chair"] in chair_ids:
        qs = qs.filter(chair_q(org, filters["chair"]))
    if filters["kind"]:
        qs = qs.filter(exam_type_extended=filters["kind"])
    if filters["form"]:
        qs = qs.filter(exam_type=filters["form"])
    if filters["status"]:
        qs = qs.filter(ue_status=filters["status"])
    period = periods.get(filters["period"]) if filters["period"] else None
    if period is not None:
        qs = qs.filter(ue_date__gte=_aware(period.start_date), ue_date__lte=_aware(period.end_date, end=True))
    if filters["date_from"]:
        qs = qs.filter(ue_date__gte=_aware(filters["date_from"]))
    if filters["date_to"]:
        qs = qs.filter(ue_date__lte=_aware(filters["date_to"], end=True))
    return qs


_ORDER = {
    "title": ("title",),
    "subject": ("subject__name", "title"),
    "author": ("author__last_name", "author__first_name"),
    "date": ("ue_date",),
    "participants": ("ue_participants",),
    "avg": ("ue_avg",),
}


def order_rows(qs, sort: str):
    desc = sort.startswith("-")
    fields = _ORDER.get(sort.lstrip("-"), _ORDER["date"])
    ordering = [F(name).desc(nulls_last=True) if desc else F(name).asc(nulls_last=True) for name in fields]
    return qs.order_by(*ordering, "-pk")


# --------------------------------------------------------------------------- #
# Əsas sorğu + KPI
# --------------------------------------------------------------------------- #


def scoped_exams(org, subtree):
    """Alt-ağacın imtahanları (silinməmiş) + ``ue_status`` / ``ue_date`` annotasiyası."""
    from apps.exams.models import Exam

    return (
        Exam.objects.filter(organization=org, is_deleted=False)
        .filter(exam_subtree_q(org, subtree.values("pk")))
        .annotate(ue_status=status_expression(), ue_date=Coalesce("start_datetime", "created_at"))
    )


def kpi_counts(scoped) -> dict:
    """Bütün əhatə üzrə (filtrsiz) iki aqreqat sorğusu: imtahanlar + cəhdlər."""
    from apps.exams.models import ExamAttempt

    exams = scoped.order_by().aggregate(
        total=Count("pk"),
        **{key: Count("pk", filter=Q(ue_status=key)) for key in STATUS_KEYS},
        final=Count("pk", filter=Q(exam_type_extended="final")),
        midterm=Count("pk", filter=Q(exam_type_extended="midterm")),
    )
    attempts = (
        ExamAttempt.objects.filter(exam__in=scoped.order_by().values("pk"), is_trial=False)
        .annotate(ue_pct=score_pct_expression())
        .aggregate(
            participants=Count("user", distinct=True),
            finished_attempts=Count("pk", filter=Q(status__in=FINISHED)),
            avg=Avg("ue_pct", filter=Q(status__in=FINISHED)),
        )
    )
    exams.update(attempts)
    if (exams.get("finished_attempts") or 0) < MIN_GROUP_FOR_AVG:
        exams["avg"] = None
    return exams


__all__ = [
    "DEFAULT_SORT",
    "FINISHED",
    "FORM_KEYS",
    "KIND_KEYS",
    "MIN_GROUP_FOR_AVG",
    "STATUS_KEYS",
    "annotate_rows",
    "apply_filters",
    "chair_q",
    "exam_subtree_q",
    "kpi_counts",
    "order_rows",
    "read_filters",
    "resolve_unit_subtree",
    "scoped_exams",
    "status_expression",
]
