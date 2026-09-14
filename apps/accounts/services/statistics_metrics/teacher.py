"""«Statistika» — MÜƏLLİM profili: öz fənləri, tələbələri, jurnalı, imtahanları.

Əhatə: registrar fənn açılışları (`CourseOffering.instructor`), LMS kursları
(`Course.owner`) və müəllif olduğu imtahanlar (`Exam.author`). Tarix pəncərəsi
YALNIZ fəaliyyət metrikalarına (cəhd, davamiyyət qeydi) tətbiq olunur; jurnal /
açılış sayğacları cari dövrün mənzərəsidir. Hər rəqəm aqreqatdır — sorğu sayı
açılış/cəhd sayından asılı deyil.
"""

from __future__ import annotations

from django.db.models import Count, F, Min, Q
from django.utils import timezone

from ._shared import (
    ROW_LIMIT,
    Window,
    attempt_outcome,
    exam_lifecycle_aggregate,
    pct,
)


def _offering_rows(offerings_qs, window: Window) -> list[dict]:
    """Cari dövrün açılışları — tələbə sayı, davamiyyət, jurnal statusu (2 sorğu, N+1 yox)."""
    from apps.registrar.models import Enrollment, LessonMark

    rows = list(
        offerings_qs.values(
            "id",
            "subject__name",
            "subject__code",
            "group__name",
            "assessment_scheme__is_published",
        )
        .annotate(
            students=Count("enrollments", filter=Q(enrollments__status=Enrollment.Status.ENROLLED), distinct=True),
        )
        .order_by("subject__name", "group__name")[:ROW_LIMIT]
    )
    if not rows:
        return []
    marks = window.apply_date(
        LessonMark.objects.filter(lesson__offering_id__in=[r["id"] for r in rows]), "lesson__date"
    )
    attendance = {
        row["lesson__offering_id"]: row
        for row in marks.values("lesson__offering_id").annotate(
            total=Count("id"),
            present=Count("id", filter=~Q(status="absent")),
        )
    }
    result = []
    for row in rows:
        att = attendance.get(row["id"])
        result.append(
            {
                "id": str(row["id"]),
                "subject": row["subject__name"] or "—",
                "code": row["subject__code"] or "",
                "group": row["group__name"] or "—",
                "students": int(row["students"] or 0),
                "attendance_pct": pct(att["present"], att["total"]) if att else None,
                "journal_published": bool(row["assessment_scheme__is_published"]),
            }
        )
    return result


def teacher_metrics(user, *, organization, window: Window, period=None, course_id=None) -> dict:
    """Müəllimin metrik modeli — sabit sayda sorğu (~11)."""
    from apps.assignments.models import Submission
    from apps.courses.models import Course, CourseMembership
    from apps.exams.models import Exam, ExamAttempt
    from apps.registrar.models import CourseOffering, Enrollment, LessonMark

    now = timezone.now()

    offerings = CourseOffering.objects.filter(instructor=user, is_active=True)
    if organization is not None:
        offerings = offerings.filter(organization=organization)
    if period is not None:
        offerings = offerings.filter(period=period)
    if course_id:
        offerings = offerings.filter(course_id=course_id)
    offering_agg = offerings.aggregate(
        total=Count("id"),
        groups=Count("group_id", distinct=True),
        journals_published=Count("assessment_scheme", filter=Q(assessment_scheme__is_published=True)),
    )
    students_registrar = (
        Enrollment.objects.filter(offering__in=offerings, status=Enrollment.Status.ENROLLED)
        .values("student_id")
        .distinct()
        .count()
    )
    attendance_agg = window.apply_date(
        LessonMark.objects.filter(lesson__offering__in=offerings), "lesson__date"
    ).aggregate(
        total=Count("id"),
        present=Count("id", filter=~Q(status="absent")),
    )

    courses = Course.objects.filter(owner=user)
    if organization is not None:
        courses = courses.filter(organization=organization)
    if course_id:
        courses = courses.filter(id=course_id)
    course_agg = courses.aggregate(total=Count("id"), published=Count("id", filter=Q(status="published")))
    students_lms = (
        CourseMembership.objects.filter(course__in=courses, role="student").values("user_id").distinct().count()
    )

    exams = Exam.objects.filter(author=user, is_deleted=False)
    if organization is not None:
        exams = exams.filter(organization=organization)
    if course_id:
        exams = exams.filter(course_id=course_id)
    lifecycle = exam_lifecycle_aggregate(exams, now=now)
    next_exam = exams.filter(is_active=True, start_datetime__gt=now).aggregate(starts=Min("start_datetime"))["starts"]

    attempts = window.apply(ExamAttempt.objects.filter(exam__in=exams), "started_at")
    outcome = attempt_outcome(attempts)

    ungraded_submissions = Submission.objects.filter(
        assignment__course__in=courses, status__in=("submitted", "grading")
    ).count()

    recent_exams = list(
        exams.annotate(
            attempts_finished=Count(
                "attempts", filter=Q(attempts__status__in=("submitted", "expired"), attempts__is_trial=False)
            ),
            course_title=F("course__title"),
        )
        .order_by(F("start_datetime").desc(nulls_last=True), "-created_at")
        .values(
            "title", "exam_type", "is_active", "start_datetime", "end_datetime", "attempts_finished", "course_title"
        )[:ROW_LIMIT]
    )

    return {
        "profile": "teacher",
        "window": window.as_dict(),
        "offerings": {
            "total": int(offering_agg["total"] or 0),
            "groups": int(offering_agg["groups"] or 0),
            "journals_published": int(offering_agg["journals_published"] or 0),
            "journals_pct": pct(offering_agg["journals_published"], offering_agg["total"]),
            "students": int(students_registrar or 0),
            "attendance_pct": pct(attendance_agg["present"], attendance_agg["total"]),
            "attendance_marks": int(attendance_agg["total"] or 0),
            "rows": _offering_rows(offerings, window),
        },
        "courses": {
            "total": int(course_agg["total"] or 0),
            "published": int(course_agg["published"] or 0),
            "students": int(students_lms or 0),
            "ungraded_submissions": int(ungraded_submissions or 0),
        },
        "exams": {
            **lifecycle,
            "next_start": next_exam.isoformat() if next_exam else "",
            "outcome": outcome,
            "rows": [
                {
                    "title": row["title"] or "—",
                    "exam_type": row["exam_type"],
                    "course": row["course_title"] or "",
                    "is_active": bool(row["is_active"]),
                    "start": row["start_datetime"].isoformat() if row["start_datetime"] else "",
                    "end": row["end_datetime"].isoformat() if row["end_datetime"] else "",
                    "attempts": int(row["attempts_finished"] or 0),
                }
                for row in recent_exams
            ],
        },
    }
