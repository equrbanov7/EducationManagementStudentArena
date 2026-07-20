"""Dekan/kafedra analitika paneli (U10) — read-only batched aggregation.

Aggregates one academic period's results into faculty-level metrics: pass rate
(keçid %), credit-weighted average GPA, attendance (qayıb %) — overall and per
program / group — plus the highest-fail-rate "at-risk" subjects.

**Performance contract:** the whole dashboard is built from a FIXED number of
queries (~7) regardless of enrollment count — per-enrollment results are
recomputed here from bulk maps instead of calling
:func:`finals.compute_final_result` N times (which issues several queries per
enrollment). The math intentionally mirrors ``compute_final_result`` /
``gradebook.entry_score_for``; ``test_analytics.py`` contains a consistency
test that locks the two implementations together.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Cast, Least

from apps.registrar import finals
from apps.registrar.models import (
    AssessmentComponent,
    AssessmentScheme,
    ComponentScore,
    Enrollment,
    FinalGrade,
    LessonMark,
    ResitRecord,
    StudentAcademicRecord,
)

_TWO = Decimal("0.01")
_DEFAULT_ENTRY_MAX = 50
_DEFAULT_PASS = 51
_DEFAULT_MIN_EXAM = 17
_DEFAULT_ABSENCE_LIMIT = 25
_AT_RISK_LIMIT = 8


def _round2(value) -> Decimal:
    return Decimal(value).quantize(_TWO, rounding=ROUND_HALF_UP)


def _pct(part, whole) -> Decimal:
    if not whole:
        return Decimal("0.00")
    return _round2(Decimal(part) * 100 / Decimal(whole))


# ── Bulk maps (one query each) ───────────────────────────────────────────────


def _scheme_map(offering_ids):
    return {
        s.offering_id: s
        for s in AssessmentScheme.objects.filter(offering_id__in=offering_ids).only(
            "offering_id", "entry_score_max", "pass_threshold", "min_final_exam_score"
        )
    }


def _component_offerings(offering_ids) -> set:
    """Yalnız GENERIC komponentli offering-lər lesson-cəmi əvəz edir
    (kollokvium/sərbəst iş ÜSTƏGƏLdir — gradebook.entry_score_for güzgüsü)."""
    return set(
        AssessmentComponent.objects.filter(offering_id__in=offering_ids, kind="generic").values_list(
            "offering_id", flat=True
        )
    )


def _capped_component_sum(enrollment_ids, *, kinds):
    decimal_field = DecimalField(max_digits=8, decimal_places=2)
    capped = Least(F("score"), Cast(F("component__max_score"), decimal_field), output_field=decimal_field)
    rows = (
        ComponentScore.objects.filter(enrollment_id__in=enrollment_ids, component__kind__in=kinds)
        .values("enrollment_id")
        .annotate(total=Sum(capped))
    )
    return {r["enrollment_id"]: r["total"] or Decimal("0") for r in rows}


def _component_sum_map(enrollment_ids):
    return _capped_component_sum(enrollment_ids, kinds=["generic"])


def _kollokvium_sum_map(enrollment_ids):
    return _capped_component_sum(enrollment_ids, kinds=["kollokvium"])


def _selfwork_map(enrollment_ids):
    """enrollment_id → təhvil verilmiş sərbəst iş sayı (hər biri 1 bal, ≤10)."""
    from django.db.models import Count

    from apps.registrar.models import SelfWorkMark

    rows = (
        SelfWorkMark.objects.filter(enrollment_id__in=enrollment_ids, done=True)
        .values("enrollment_id")
        .annotate(total=Count("id"))
    )
    return {r["enrollment_id"]: min(Decimal(r["total"]), Decimal(10)) for r in rows}


def _lesson_sum_map(enrollment_ids):
    rows = (
        LessonMark.objects.filter(enrollment_id__in=enrollment_ids, score__isnull=False)
        .values("enrollment_id")
        .annotate(total=Sum("score"))
    )
    return {r["enrollment_id"]: r["total"] or Decimal("0") for r in rows}


def _exam_map(enrollment_ids):
    """enrollment_id → (exam_score, bonus) — bir sorğuda hər ikisi (U15)."""
    return {
        e_id: (score, bonus)
        for e_id, score, bonus in FinalGrade.objects.filter(enrollment_id__in=enrollment_ids).values_list(
            "enrollment_id", "exam_score", "bonus"
        )
    }


def _resit_map(enrollment_ids):
    return {
        e_id: score
        for e_id, score in ResitRecord.objects.filter(
            enrollment_id__in=enrollment_ids, resit_score__isnull=False
        ).values_list("enrollment_id", "resit_score")
    }


def _record_map(organization, student_ids):
    return {
        r.student_id: r
        for r in StudentAcademicRecord.objects.filter(
            organization=organization, student_id__in=student_ids
        ).select_related("program", "group")
    }


# ── Per-enrollment result (mirrors finals.compute_final_result) ─────────────


def _evaluate(enrollment, maps):
    offering = enrollment.offering
    scheme = maps["schemes"].get(offering.id)
    entry_max = scheme.entry_score_max if scheme else _DEFAULT_ENTRY_MAX
    pass_threshold = scheme.pass_threshold if scheme else _DEFAULT_PASS
    min_exam = scheme.min_final_exam_score if scheme else _DEFAULT_MIN_EXAM

    if offering.id in maps["component_offerings"]:
        raw_entry = maps["component_sums"].get(enrollment.id, Decimal("0"))
    else:
        raw_entry = maps["lesson_sums"].get(enrollment.id, Decimal("0"))
    # Kollokvium + sərbəst iş həmişə üstəgəl (gradebook.entry_score_for güzgüsü).
    raw_entry += maps["kollokvium_sums"].get(enrollment.id, Decimal("0"))
    raw_entry += maps["selfwork_sums"].get(enrollment.id, Decimal("0"))
    entry = min(raw_entry, Decimal(entry_max))

    exam, bonus = maps["exams"].get(enrollment.id, (None, Decimal("0")))
    resit = maps["resits"].get(enrollment.id)
    resit_done = resit is not None
    effective = resit if resit_done else exam

    record = maps["records"].get(enrollment.student_id)
    limit = record.program.absence_limit_percent if record and record.program_id else _DEFAULT_ABSENCE_LIMIT
    lesson_hours = offering.lesson_hours or 0
    barred = lesson_hours > 0 and enrollment.absence_hours > lesson_hours * limit / 100.0 and not resit_done

    graded = effective is not None
    total = entry + (effective or Decimal("0")) + (bonus or Decimal("0"))
    total = max(Decimal("0"), min(Decimal("100"), total))  # compute_final_result güzgüsü (U15)
    letter, gpa = finals.score_to_letter(total, maps.get("organization"))
    exam_ok = graded and effective >= min_exam
    passed = graded and not barred and total >= pass_threshold and exam_ok
    failed = barred or (graded and not passed)

    return {
        "graded": graded,
        "total": total,
        "gpa": gpa,
        "passed": passed,
        "failed": failed,
        "barred": barred,
        "credit": int(getattr(offering.subject, "ects", 0) or 0),
        "absence_hours": enrollment.absence_hours or 0,
        "lesson_hours": lesson_hours,
    }


# ── Bucketed aggregation ─────────────────────────────────────────────────────


class _Bucket:
    __slots__ = (
        "key",
        "label",
        "sublabel",
        "students",
        "enrollments",
        "graded",
        "passed",
        "failed",
        "barred",
        "quality_points",
        "gpa_credits",
        "total_sum",
        "absence_hours",
        "lesson_hours",
    )

    def __init__(self, key, label, sublabel=""):
        self.key = key
        self.label = label
        self.sublabel = sublabel
        self.students = set()
        self.enrollments = 0
        self.graded = 0
        self.passed = 0
        self.failed = 0
        self.barred = 0
        self.quality_points = Decimal("0")
        self.gpa_credits = 0
        self.total_sum = Decimal("0")
        self.absence_hours = 0
        self.lesson_hours = 0

    def add(self, student_id, result):
        self.students.add(student_id)
        self.enrollments += 1
        self.absence_hours += result["absence_hours"]
        self.lesson_hours += result["lesson_hours"]
        if result["barred"]:
            self.barred += 1
        if result["graded"]:
            self.graded += 1
            self.total_sum += result["total"]
        if result["passed"] or result["failed"]:
            # ÜOMG 100 bal üzərindən: Σ(yekun_bal × kredit) / Σ(kredit) (transcript ilə eyni).
            self.quality_points += result["total"] * result["credit"]
            self.gpa_credits += result["credit"]
        if result["passed"]:
            self.passed += 1
        elif result["failed"]:
            self.failed += 1

    def summary(self) -> dict:
        definite = self.passed + self.failed
        return {
            "key": self.key,
            "label": self.label,
            "sublabel": self.sublabel,
            "students": len(self.students),
            "enrollments": self.enrollments,
            "graded": self.graded,
            "passed": self.passed,
            "failed": self.failed,
            "in_progress": self.enrollments - definite,
            "barred": self.barred,
            "pass_rate": _pct(self.passed, definite),
            "fail_rate": _pct(self.failed, definite),
            "definite": definite,
            "avg_gpa": _round2(self.quality_points / self.gpa_credits) if self.gpa_credits else Decimal("0.00"),
            "avg_total": _round2(self.total_sum / self.graded) if self.graded else Decimal("0.00"),
            "absence_rate": _pct(self.absence_hours, self.lesson_hours),
        }


def build_evaluation_maps(organization, enrollments) -> dict:
    """Verilmiş enrollment siyahısı üçün bütün bulk map-ları qurur (sabit sorğu
    sayı — hər map bir sorğu). Həm :func:`build_period_analytics` (dövr analitikası),
    həm də akademik-qeyd icmalı (:mod:`apps.registrar.records_overview`) eyni
    riyaziyyatı (``_evaluate``) bölüşsün deyə çıxarılıb — beləcə iki kod yolu
    ``compute_final_result``-dan fərqlənmir (``test_analytics.py`` konsistensiya
    testi ilə kilidlənib)."""
    enrollment_ids = [e.id for e in enrollments]
    offering_ids = list({e.offering_id for e in enrollments})
    student_ids = list({e.student_id for e in enrollments})
    return {
        "schemes": _scheme_map(offering_ids),
        "component_offerings": _component_offerings(offering_ids),
        "component_sums": _component_sum_map(enrollment_ids),
        "kollokvium_sums": _kollokvium_sum_map(enrollment_ids),
        "selfwork_sums": _selfwork_map(enrollment_ids),
        "lesson_sums": _lesson_sum_map(enrollment_ids),
        "exams": _exam_map(enrollment_ids),
        "resits": _resit_map(enrollment_ids),
        "records": _record_map(organization, student_ids),
        "organization": organization,  # U17: tenant hərf şkalası
    }


def evaluate_enrollment(enrollment, maps) -> dict:
    """Bir enrollment-in nəticəsi (``compute_final_result`` güzgüsü) — public ad
    (records_overview modulu üçün). Bax :func:`_evaluate`."""
    return _evaluate(enrollment, maps)


def build_period_analytics(*, organization, period) -> dict:
    """Full dashboard payload for one org + period (fixed query count)."""
    enrollments = list(
        Enrollment.objects.filter(organization=organization, offering__period=period)
        .exclude(status=Enrollment.Status.DROPPED)
        .select_related("offering", "offering__subject", "offering__group")
    )
    if not enrollments:
        return {"has_data": False, "period": period, "totals": None, "programs": [], "groups": [], "at_risk": []}

    maps = build_evaluation_maps(organization, enrollments)

    overall = _Bucket("overall", "")
    programs: dict = {}
    groups: dict = {}
    subjects: dict = {}

    for enrollment in enrollments:
        result = _evaluate(enrollment, maps)
        overall.add(enrollment.student_id, result)

        record = maps["records"].get(enrollment.student_id)
        if record is not None and record.program_id:
            bucket = programs.get(record.program_id)
            if bucket is None:
                bucket = programs[record.program_id] = _Bucket(
                    record.program_id, record.program.name, record.program.code
                )
            bucket.add(enrollment.student_id, result)

        group = enrollment.offering.group
        if group is not None:
            bucket = groups.get(group.id)
            if bucket is None:
                bucket = groups[group.id] = _Bucket(group.id, group.name)
            bucket.add(enrollment.student_id, result)

        subject = enrollment.offering.subject
        bucket = subjects.get(enrollment.offering_id)
        if bucket is None:
            bucket = subjects[enrollment.offering_id] = _Bucket(enrollment.offering_id, subject.name, subject.code)
        bucket.add(enrollment.student_id, result)

    at_risk = [b.summary() for b in subjects.values()]
    at_risk = sorted(
        (s for s in at_risk if s["definite"] and s["fail_rate"] > 0),
        key=lambda s: (s["fail_rate"], s["failed"]),
        reverse=True,
    )[:_AT_RISK_LIMIT]

    return {
        "has_data": True,
        "period": period,
        "totals": overall.summary(),
        "programs": sorted((b.summary() for b in programs.values()), key=lambda s: s["label"]),
        "groups": sorted((b.summary() for b in groups.values()), key=lambda s: s["label"]),
        "at_risk": at_risk,
    }
