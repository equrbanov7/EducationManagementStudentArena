"""«Statistika» — TƏLƏBƏ profili: öz akademik mənzərəsi (rəqəmlər, i18n-siz).

Nə göstərilir (sahib tələbi 2026-09-12, dizayn ekran 10 «Tələbə kabineti»):
ECTS tərəqqisi, ÜOMG, davamiyyət, keçilmiş/kəsilmiş fənn, imtahan cəhdləri və
keçid, gözləyən tapşırıq, apellyasiya; semestr üzrə orta bal (əvvəlki
semestrlə müqayisə) və son imtahan nəticələri.

Akademik hissə `registrar.analytics.build_evaluation_maps` + `evaluate_enrollment`
bulk yolunu işlədir — `transcript.student_credit_totals` ilə EYNİ səbəbdən:
sabit ~11 sorğu, yazılış sayından asılı deyil (transkript qurucusu fənn başına
~7 sorğu verir). Riyaziyyat `finals.compute_final_result`-un rəsmi güzgüsüdür.
"""

from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal

from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from ._shared import ROW_LIMIT, attempt_outcome, pct, score_pct_expression

_ZERO = Decimal("0")


def _academic_snapshot(user, organization) -> dict:
    """Yazılışların bulk qiymətləndirilməsi — kredit, ÜOMG, davamiyyət, semestr bölgüsü."""
    from apps.registrar.models import Enrollment, StudentAcademicRecord
    from apps.registrar.public import analytics

    snapshot = {
        "has_record": False,
        "program_name": "",
        "program_ects_total": 0,
        "enrollments": 0,
        "credits_earned": 0,
        "credits_in_progress": 0,
        "graded": 0,
        "passed": 0,
        "failed": 0,
        "barred": 0,
        "gpa": None,
        "attendance_pct": None,
        "absence_hours": 0,
        "lesson_hours": 0,
        "periods": [],
    }
    if organization is None:
        return snapshot

    record = (
        StudentAcademicRecord.objects.filter(organization=organization, student=user, is_active=True)
        .select_related("program")
        .only("id", "program__name", "program__ects_total")
        .first()
    )
    if record is not None:
        snapshot["has_record"] = True
        snapshot["program_name"] = record.program.name if record.program_id else ""
        snapshot["program_ects_total"] = int(getattr(record.program, "ects_total", 0) or 0)

    enrollments = list(
        Enrollment.objects.filter(organization=organization, student=user)
        .exclude(status=Enrollment.Status.DROPPED)
        .select_related("offering", "offering__subject", "offering__period")
    )
    snapshot["enrollments"] = len(enrollments)
    if not enrollments:
        return snapshot

    maps = analytics.build_evaluation_maps(organization, enrollments)
    today = timezone.localdate()
    quality_points = _ZERO
    gpa_credits = 0
    absence_hours = 0
    lesson_hours = 0
    periods: OrderedDict = OrderedDict()

    for enrollment in enrollments:
        result = analytics.evaluate_enrollment(enrollment, maps)
        period = enrollment.offering.period
        bucket = periods.setdefault(
            str(period.pk),
            {
                "label": f"{period.name} {period.academic_year}".strip(),
                "start_date": period.start_date,
                "enrollments": 0,
                "graded": 0,
                "passed": 0,
                "failed": 0,
                "credits": 0,
                "total_sum": _ZERO,
            },
        )
        bucket["enrollments"] += 1
        credit = int(result["credit"] or 0)
        if result["passed"]:
            snapshot["credits_earned"] += credit
            snapshot["passed"] += 1
            bucket["passed"] += 1
        else:
            # `transcript.student_credit_totals` ilə EYNİ qayda: bitməmiş dövrün
            # hələ keçilməmiş yazılışı «davam edir» (kəsilmə burada süzülmür).
            end_date = getattr(period, "end_date", None)
            if end_date is None or end_date >= today:
                snapshot["credits_in_progress"] += credit
        if result["graded"]:
            snapshot["graded"] += 1
            bucket["graded"] += 1
            bucket["total_sum"] += Decimal(result["total"] or 0)
            quality_points += Decimal(result["gpa"] or 0) * credit
            gpa_credits += credit
        if result["failed"]:
            snapshot["failed"] += 1
            bucket["failed"] += 1
        if result["barred"]:
            snapshot["barred"] += 1
        bucket["credits"] += credit
        # Davamiyyət yalnız saatı məlum olan (bitmiş/canlı) açılışlar üzrə.
        hours = int(result["lesson_hours"] or 0)
        if hours > 0:
            lesson_hours += hours
            absence_hours += int(result["absence_hours"] or 0)

    if gpa_credits:
        snapshot["gpa"] = float((quality_points / Decimal(gpa_credits)).quantize(Decimal("0.01")))
    snapshot["absence_hours"] = absence_hours
    snapshot["lesson_hours"] = lesson_hours
    if lesson_hours:
        snapshot["attendance_pct"] = round(100.0 - float(absence_hours) * 100.0 / float(lesson_hours), 1)

    ordered = sorted(periods.values(), key=lambda b: (b["start_date"] or today), reverse=True)
    snapshot["periods"] = [
        {
            "label": b["label"],
            "enrollments": b["enrollments"],
            "graded": b["graded"],
            "passed": b["passed"],
            "failed": b["failed"],
            "credits": b["credits"],
            "avg_total": round(float(b["total_sum"] / b["graded"]), 1) if b["graded"] else None,
        }
        for b in ordered[:6]
    ]
    return snapshot


def student_metrics(user, *, organization) -> dict:
    """Tələbənin metrik modeli — sabit sayda sorğu (bax modul docstring-i)."""
    from apps.appeals.models import Appeal
    from apps.appeals.public import APPEAL_STATUS_PENDING, APPEAL_STATUS_UNDER_REVIEW
    from apps.assignments.models import Assignment, Submission
    from apps.exams.models import ExamAttempt

    now = timezone.now()
    academic = _academic_snapshot(user, organization)

    attempts = ExamAttempt.objects.filter(user=user, exam__is_deleted=False)
    if organization is not None:
        attempts = attempts.filter(exam__organization=organization)
    exams = attempt_outcome(attempts)

    recent_attempts = list(
        attempts.filter(status__in=("submitted", "expired"), is_trial=False)
        .annotate(score_pct=score_pct_expression())
        .order_by("-finished_at", "-started_at")
        .values("exam__title", "exam__exam_type", "finished_at", "started_at", "score_pct", "checked_by_teacher")[
            :ROW_LIMIT
        ]
    )

    assignments = Assignment.objects.filter(
        course__memberships__user=user,
        course__memberships__role="student",
        status__in=("published", "active"),
    )
    if organization is not None:
        assignments = assignments.filter(course__organization=organization)
    assignment_agg = assignments.annotate(
        has_submission=Exists(Submission.objects.filter(assignment=OuterRef("pk"), user=user))
    ).aggregate(
        total=Count("id", distinct=True),
        pending=Count(
            "id",
            distinct=True,
            filter=Q(has_submission=False) & (Q(due_date__isnull=True) | Q(due_date__gte=now)),
        ),
        overdue=Count("id", distinct=True, filter=Q(has_submission=False, due_date__lt=now)),
    )

    submissions = Submission.objects.filter(user=user)
    if organization is not None:
        submissions = submissions.filter(assignment__course__organization=organization)
    submission_agg = submissions.aggregate(
        total=Count("id"),
        graded=Count("id", filter=Q(status="graded")),
        late=Count("id", filter=Q(is_late=True)),
    )

    appeals = Appeal.objects.filter(student=user)
    if organization is not None:
        appeals = appeals.filter(organization=organization)
    appeal_agg = appeals.aggregate(
        total=Count("id"),
        open=Count("id", filter=Q(status__in=(APPEAL_STATUS_PENDING, APPEAL_STATUS_UNDER_REVIEW))),
    )

    return {
        "profile": "student",
        "academic": academic,
        "exams": exams,
        "recent_attempts": [
            {
                "title": row["exam__title"] or "—",
                "exam_type": row["exam__exam_type"],
                "finished_at": (
                    (row["finished_at"] or row["started_at"]).isoformat()
                    if (row["finished_at"] or row["started_at"])
                    else ""
                ),
                "score_pct": round(float(row["score_pct"]), 1) if row["score_pct"] is not None else None,
                "checked": bool(row["checked_by_teacher"]),
            }
            for row in recent_attempts
        ],
        "assignments": {
            "total": int(assignment_agg["total"] or 0),
            "pending": int(assignment_agg["pending"] or 0),
            "overdue": int(assignment_agg["overdue"] or 0),
            "submitted": int(submission_agg["total"] or 0),
            "graded": int(submission_agg["graded"] or 0),
            "late": int(submission_agg["late"] or 0),
            "graded_pct": pct(submission_agg["graded"], submission_agg["total"]),
        },
        "appeals": {
            "total": int(appeal_agg["total"] or 0),
            "open": int(appeal_agg["open"] or 0),
        },
    }
