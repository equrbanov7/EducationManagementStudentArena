"""Authoritative language-level policy; raw earned scores are never rewritten."""

from collections import defaultdict
from collections.abc import Mapping
from copy import copy
from decimal import Decimal

from django.db.models import Count, F, Sum

from core.language_level_rule import (  # noqa: F401 — ATTENDANCE_MAX bu modulun açıq sabitidir (çağıranlar oxuyur)
    ABSENCE_LIMIT,
    ACTIVITY_MAX,
    ATTENDANCE_MAX,
    ENTRY_MAX,
    EXAM_MAX,
    MIDTERM_MAX,
)

from .language_levels import level_of

#: Tavanlar :mod:`core.language_level_rule`-dadır (TƏK reyestr): 10 + 10 + 10 = 30, imtahan 70.
SEMINAR_MAX = ACTIVITY_MAX


def is_level_name(subject_name):
    return bool(level_of(subject_name))


def is_level(offering):
    """Səviyyə qaydası (10+10+10 / 70) yalnız Midterm dövrünün (2026/2027+) açılışlarına aiddir.

    Cari semestrdə həmişə qüvvədədir. Köçürülmüş (keçmiş, cari olmayan) semestrlərdə səviyyə adlı fənlər köhnə sistemdə universitet standartı ilə
    (giriş 0–50) aparılıb və imtahansız qalıb — sahib 2026-11-09: onlar adi fənn kimi oxunur, yekun = giriş balı
    (bax :func:`apps.registrar.finals.compute_final_result`). Ad yoxlaması üçün :func:`is_level_name` qalır.
    """
    subject = getattr(offering, "subject", None)
    if subject is None or not is_level_name(getattr(subject, "name", "")):
        return False
    return level_era(offering)


#: Dövr qapısının keşi: ``period_id → (vaxt, qüvvədədir)``. Açılış başına sorğu OLMASIN deyə (döngülərdə 37 çağırış
#: yeri var) dövr sahələri dövr başına bir dəfə oxunur və qısa müddət saxlanılır (semestr dəyişəndə ≤ TTL gecikmə).
_ERA_TTL_SECONDS = 120
_era_cache: dict = {}


def level_era(offering) -> bool:
    """Səviyyə qaydası bu açılışın dövründə qüvvədədirmi: cari semestr və ya Midterm dövrü (2026/2027+)."""
    import time

    from . import entry_standard, interim_assessment

    state = getattr(offering, "_state", None)
    period = state.fields_cache.get("period") if state is not None else None
    if period is not None:  # FK artıq yüklənib — sorğusuz
        return bool(getattr(period, "is_current", False)) or (
            interim_assessment.mode_for_period(period, getattr(offering, "organization", None))
            == interim_assessment.MODE_MIDTERM
        )
    period_id = getattr(offering, "period_id", None)
    if period_id is None:
        return True  # dövrsüz (yazılmamış) nümunə — cari qayda
    now = time.monotonic()
    hit = _era_cache.get(period_id)
    if hit is not None and now - hit[0] < _ERA_TTL_SECONDS:
        return hit[1]
    from django.apps import apps as django_apps

    row = (
        django_apps.get_model("organizations", "AcademicPeriod")
        .objects.filter(pk=period_id)
        .values_list(
            "is_current", "academic_year", "start_date", "organization__settings__registrar__midterm_from_year"
        )
        .first()
    )
    if row is None:
        value = True
    else:
        is_current, academic_year, start_date, from_year_raw = row
        value = bool(is_current) or entry_standard.is_midterm_fields(
            academic_year, start_date, from_year_raw=from_year_raw
        )
    _era_cache[period_id] = (now, value)
    return value


def entry_cap(subject_name, configured):
    return ENTRY_MAX if is_level_name(subject_name) else configured


def exam_cap(subject_name, configured_entry):
    return EXAM_MAX if is_level_name(subject_name) else max(0, 100 - configured_entry)


def normalized_scheme(scheme, *, offering=None):
    if scheme is None or getattr(scheme, "_language_level_normalized", False):
        return scheme
    offering = offering or scheme.offering
    if not is_level(offering):
        scheme._language_level_normalized = True
        return scheme
    result = copy(scheme)
    result.entry_score_max = ENTRY_MAX
    result._language_level_normalized = True
    result._state.fields_cache["offering"] = offering
    return result


def absence_counts(enrollments, *, marks_by_enrollment=None, carry_counts=None):
    """Exactly the grid's ABSENT-cell count plus direct supersession carry-over.

    Aggregate hour credits do not alter this displayed count. EXCUSED cells do
    not count. Distinct lesson hours never turn one displayed q/b into two.
    """
    from .enrollment_history import predecessors
    from .models import LessonMark

    groups = defaultdict(list)
    for enrollment in enrollments:
        groups[enrollment.organization_id].append(enrollment.pk)
    result = {}
    for organization_id, ids in groups.items():
        result.update({pk: 0 for pk in ids})
        if marks_by_enrollment is not None:
            for pk in ids:
                result[pk] = sum(mark.status == "absent" for mark in marks_by_enrollment.get(pk, []))
        else:
            own = (
                LessonMark.objects.filter(
                    organization_id=organization_id,
                    enrollment__organization_id=organization_id,
                    lesson__organization_id=organization_id,
                    lesson__offering_id=F("enrollment__offering_id"),
                    enrollment_id__in=ids,
                    status="absent",
                )
                .values("enrollment_id")
                .annotate(count=Count("pk"))
            )
            for row in own:
                result[row["enrollment_id"]] = row["count"]
        if carry_counts is not None:
            for pk in ids:
                value = carry_counts.get(pk, 0)
                result[pk] += value.get("absence_count", 0) if isinstance(value, dict) else value
        else:
            carried = (
                LessonMark.objects.filter(
                    organization_id=organization_id,
                    enrollment__organization_id=organization_id,
                    lesson__organization_id=organization_id,
                    lesson__offering_id=F("enrollment__offering_id"),
                    enrollment_id__in=predecessors().filter(superseded_by_id__in=ids).values("pk"),
                    status="absent",
                )
                .values("enrollment__superseded_by_id")
                .annotate(count=Count("pk"))
            )
            for row in carried:
                result[row["enrollment__superseded_by_id"]] += row["count"]
    return result


def absence_metrics(enrollments):
    """Grid-identical count and effective hours, in three queries per tenant."""
    from .absence_credit_read import credit_hours_map, effective_hours
    from .enrollment_history import predecessors
    from .models import LessonMark

    grouped = defaultdict(list)
    for enrollment in enrollments:
        grouped[enrollment.organization_id].append(enrollment.pk)
    result = {}
    for organization_id, ids in grouped.items():
        result.update({pk: {"count": 0, "hours": 0} for pk in ids})
        base = LessonMark.objects.filter(
            organization_id=organization_id,
            enrollment__organization_id=organization_id,
            lesson__organization_id=organization_id,
            lesson__offering_id=F("enrollment__offering_id"),
            status="absent",
        )
        own = list(
            base.filter(enrollment_id__in=ids)
            .values("enrollment_id")
            .annotate(count=Count("pk"), hours=Sum("lesson__hours"))
        )
        sources = list(
            base.filter(enrollment_id__in=predecessors().filter(superseded_by_id__in=ids).values("pk"))
            .values("enrollment_id", "enrollment__superseded_by_id")
            .annotate(count=Count("pk"), hours=Sum("lesson__hours"))
        )
        credits = credit_hours_map([*ids, *[row["enrollment_id"] for row in sources]])
        for row in own:
            result[row["enrollment_id"]] = {"count": row["count"], "hours": row["hours"] or 0}
        for row in sources:
            target = result[row["enrollment__superseded_by_id"]]
            target["count"] += row["count"]
            target["hours"] += effective_hours(row["hours"] or 0, credits.get(row["enrollment_id"]))
        for pk in ids:
            result[pk]["hours"] = effective_hours(result[pk]["hours"], credits.get(pk))
    return result


def midterm_total(components, component_scores):
    ids = {component.pk for component in components if component.kind == "kollokvium"}
    if isinstance(component_scores, Mapping):
        raw = [component_scores.get(pk, component_scores.get(str(pk), 0)) for pk in ids]
        values = [getattr(value, "score", value) for value in raw]
    else:
        values = [score.score for score in component_scores if score.component_id in ids]
    total = sum((max(Decimal(0), Decimal(str(value or 0))) for value in values), Decimal(0))
    return min(Decimal(MIDTERM_MAX), total)


def eligibility(
    enrollment,
    *,
    absence_count=None,
    absence_hours=None,
    lesson_hours=None,
    exempt=False,
    resit_done=False,
    frozen=False,
):
    from . import exam_eligibility

    if absence_count is None or absence_hours is None:
        metrics = absence_metrics([enrollment])[enrollment.pk]
        absence_count = metrics["count"] if absence_count is None else absence_count
        absence_hours = metrics["hours"] if absence_hours is None else absence_hours
    hours = lesson_hours if lesson_hours is not None else exam_eligibility.lesson_hours_for(enrollment.offering)
    absent = enrollment.absence_hours if absence_hours is None else absence_hours
    # Retain the canonical proportional attendance score, while the admission
    # decision uses the displayed count. A historical freeze cannot bypass 11.
    result = exam_eligibility.resolve(absence_hours=absent, lesson_hours=hours, exempt=True, frozen=False)
    over_limit = absence_count > ABSENCE_LIMIT
    barred = over_limit and not exempt and not resit_done
    # 11 q/b qaydası tarixi semestrdə də qərar verir (yuxarıda). Qadağa YOXDURSA isə donmuş (köçürülmüş) dilimin
    # statusu adi fənlərlə eynidir: imtahan yoxdursa «köhnə sistemdə nəticə yoxdur», «Davam edir» DEYİL (SYS-1).
    legacy = bool(frozen) and not barred
    result.update(
        barred=barred,
        over_limit=over_limit,
        attendance_score=None if barred else result["attendance_score"],
        exempt=bool(exempt),
        resit_done=bool(resit_done),
        frozen=legacy,
        source=exam_eligibility.SOURCE_LEGACY if legacy else result["source"],
        frozen_badge=exam_eligibility.FROZEN_BADGE if legacy else None,
        allowed_hours=Decimal(ABSENCE_LIMIT),
        hours_known=True,
        limit_percent=None,
        absence_count=absence_count,
        limit_count=ABSENCE_LIMIT,
        limit_unit="qb_count",
    )
    return result


def parts_for(
    enrollment,
    *,
    components=None,
    component_scores=None,
    marks=None,
    rule=None,
    absence_count=None,
    absence_hours=None,
    **_unused,
):
    from . import activity_kinds, entry_standard
    from .gradebook_components import round_score
    from .models import AssessmentComponent, ComponentScore, LessonMark

    if not is_level(enrollment.offering):
        return None
    if components is None:
        components = list(
            AssessmentComponent.objects.filter(
                organization_id=enrollment.organization_id, offering_id=enrollment.offering_id
            )
        )
    if marks is None:
        marks = list(
            activity_kinds.annotate_kind(
                LessonMark.objects.filter(
                    organization_id=enrollment.organization_id,
                    enrollment=enrollment,
                )
            )
        )
    else:
        marks = list(marks)
    seminar = [
        Decimal(str(mark.score))
        for mark in marks
        if mark.score is not None and activity_kinds.mark_kind(mark) == "seminar"
    ]
    activity = activity_kinds.pooled_mean(sum(seminar, Decimal(0)), len(seminar)) if seminar else Decimal(0)
    activity = max(Decimal(0), activity)
    midterm_ids = {component.pk for component in components if component.kind == "kollokvium"}
    if component_scores is None:
        component_scores = ComponentScore.objects.filter(
            organization_id=enrollment.organization_id, enrollment=enrollment, component_id__in=midterm_ids
        )
    midterm = midterm_total(components, component_scores)
    if absence_count is None or absence_hours is None:
        metrics = absence_metrics([enrollment])[enrollment.pk]
        absence_count = metrics["count"] if absence_count is None else absence_count
        absence_hours = metrics["hours"] if absence_hours is None else absence_hours
    exempt = getattr(rule, "exempt", None)
    if exempt is None:
        from .finals import athlete_exemption

        exempt = athlete_exemption(enrollment)
    check = eligibility(
        enrollment,
        absence_count=absence_count,
        absence_hours=absence_hours,
        lesson_hours=getattr(rule, "lesson_hours", None),
        exempt=bool(exempt),
    )
    attendance = check["attendance_score"]
    attendance = Decimal(0) if attendance is None else attendance
    return entry_standard.EntryParts(
        attendance=attendance,
        activity=activity,
        midterm=max(Decimal(0), midterm),
        selfwork=Decimal(0),
        total=round_score(attendance + activity + max(Decimal(0), midterm)),
        attendance_barred=check["barred"],
        midterm_max=Decimal(MIDTERM_MAX),
        selfwork_active=False,
        practical=True,
    )


def component_cap(component):
    return MIDTERM_MAX if component.kind == "kollokvium" and is_level(component.offering) else component.max_score


def component_input_state(component, offering, raw, existing=None, *, require_all=False):
    """Reject new over-cap input while leaving an untouched legacy value intact."""
    from django.core.exceptions import ValidationError

    if component.kind != "kollokvium" or not is_level(offering) or raw in (None, ""):
        return "normal"
    try:
        value = Decimal(str(raw))
    except (ArithmeticError, TypeError, ValueError):
        return "normal"
    if not value.is_finite() or value <= MIDTERM_MAX:
        return "normal"
    if existing is not None and value == existing.score:
        return "unchanged"
    if require_all:
        raise ValidationError(
            "Komponent balı 0 ilə komponentin maksimum balı arasında olmalıdır.", code="component_score_batch_rejected"
        )
    return "rejected"
