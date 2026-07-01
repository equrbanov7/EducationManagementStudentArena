"""statistics_selectors paketi — org_admin."""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count, Q

from ._shared import (
    User,
    _apply_date_filter,
    _content_type_enabled,
    _parse_date,
    _safe_avg,
)


def get_org_admin_statistics(*, organization, filters=None, scoped_unit_ids=None):
    """
    Organization-scoped analytics for org admins.

    ``scoped_unit_ids`` (Faza 2 — unit scoping): verilərsə (dekan / kafedra
    müdürü), bütün göstəricilər yalnız həmin unit alt-ağacına aid datanı
    əhatə edir — üzvlər ``Membership.scope_unit``, kurslar ``Course.unit``,
    imtahanlar kurs unit-i və ya scoped müəllif üzərindən filtrlənir.
    """
    from apps.assignments.models import Submission
    from apps.courses.models import Course, CourseMembership
    from apps.exams.models import Exam, ExamAttempt
    from apps.labs.models import LabSubmission
    from apps.organizations.models import Membership
    from apps.projects.models import ProjectSubmission

    filters = filters or {}
    date_from = _parse_date(filters.get("date_from"))
    date_to = _parse_date(filters.get("date_to"))
    course_id = filters.get("course")
    content_type = filters.get("content_type", "all")
    is_unit_scoped = scoped_unit_ids is not None

    # ── Active members ────────────────────────────────────────────
    memberships = Membership.objects.filter(organization=organization, is_active=True)
    if is_unit_scoped:
        memberships = memberships.filter(scope_unit_id__in=scoped_unit_ids)
    total_members = memberships.values("user").distinct().count()
    teacher_count = memberships.filter(role__level__gte=55).values("user").distinct().count()
    student_count = memberships.filter(role__level__lte=30).values("user").distinct().count()

    # Scoped istifadəçi id-ləri — imtahan müəllif filtri üçün subquery
    # (materiallaşdırmadan, tək kombinə olunmuş sorğu).
    scoped_member_user_ids = memberships.values("user_id") if is_unit_scoped else None

    # ── Courses ───────────────────────────────────────────────────
    courses = Course.objects.filter(organization=organization)
    if is_unit_scoped:
        courses = courses.filter(unit_id__in=scoped_unit_ids)
    if course_id:
        courses = courses.filter(id=course_id)
    total_courses = courses.count()
    active_courses = courses.filter(status="published").count()

    # course_ids = list(courses.values_list("id", flat=True))

    # ── Exams ─────────────────────────────────────────────────────
    exams = Exam.objects.none()
    attempts = ExamAttempt.objects.none()
    total_exams = 0
    attempt_agg = {"total": 0, "submitted": 0, "checked": 0}
    if _content_type_enabled(content_type, "exam"):
        exams = Exam.objects.filter(organization=organization)
        if is_unit_scoped:
            # Kursu scoped unitə aid olan VƏ YA müəllifi scoped üzv olan imtahanlar.
            exams = exams.filter(Q(course__unit_id__in=scoped_unit_ids) | Q(author_id__in=scoped_member_user_ids))
        if course_id:
            exams = exams.filter(course_id=course_id)
        total_exams = exams.count()

        attempts = ExamAttempt.objects.filter(exam__in=exams)
        attempts = _apply_date_filter(attempts, "started_at", date_from, date_to)
        attempt_agg = attempts.aggregate(
            total=Count("id"),
            submitted=Count("id", filter=Q(status="submitted")),
            checked=Count("id", filter=Q(checked_by_teacher=True)),
        )

    # ── Assignments ───────────────────────────────────────────────
    assignment_subs = Submission.objects.none()
    asn_agg = {"total": 0, "graded": 0, "late": 0}
    if _content_type_enabled(content_type, "assignment"):
        assignment_subs = Submission.objects.filter(assignment__course__organization=organization)
        if is_unit_scoped:
            assignment_subs = assignment_subs.filter(assignment__course__unit_id__in=scoped_unit_ids)
        if course_id:
            assignment_subs = assignment_subs.filter(assignment__course_id=course_id)
        assignment_subs = _apply_date_filter(assignment_subs, "submitted_at", date_from, date_to)
        asn_agg = assignment_subs.aggregate(
            total=Count("id"),
            graded=Count("id", filter=Q(status="graded")),
            late=Count("id", filter=Q(is_late=True)),
        )

    # ── Labs ──────────────────────────────────────────────────────
    lab_subs = LabSubmission.objects.none()
    lab_agg = {"total": 0, "graded": 0}
    if _content_type_enabled(content_type, "lab"):
        lab_subs = LabSubmission.objects.filter(assignment__lab__course__organization=organization)
        if is_unit_scoped:
            lab_subs = lab_subs.filter(assignment__lab__course__unit_id__in=scoped_unit_ids)
        if course_id:
            lab_subs = lab_subs.filter(assignment__lab__course_id=course_id)
        lab_subs = _apply_date_filter(lab_subs, "submitted_at", date_from, date_to)
        lab_agg = lab_subs.aggregate(
            total=Count("id"),
            graded=Count("id", filter=Q(status="graded")),
        )

    # ── Projects ──────────────────────────────────────────────────
    proj_subs = ProjectSubmission.objects.none()
    proj_agg = {"total": 0, "graded": 0}
    if _content_type_enabled(content_type, "project"):
        proj_subs = ProjectSubmission.objects.filter(project__course__organization=organization)
        if is_unit_scoped:
            proj_subs = proj_subs.filter(project__course__unit_id__in=scoped_unit_ids)
        if course_id:
            proj_subs = proj_subs.filter(project__course_id=course_id)
        proj_subs = _apply_date_filter(proj_subs, "submitted_at", date_from, date_to)
        proj_agg = proj_subs.aggregate(
            total=Count("id"),
            graded=Count("id", filter=Q(status="graded")),
        )

    # ── Submission trend ──────────────────────────────────────────
    trend_data = defaultdict(int)
    for a in attempts.filter(started_at__isnull=False).values("started_at"):
        month = a["started_at"].strftime("%Y-%m")
        trend_data[month] += 1
    for s in assignment_subs.filter(submitted_at__isnull=False).values("submitted_at"):
        month = s["submitted_at"].strftime("%Y-%m")
        trend_data[month] += 1
    trend_labels = sorted(trend_data.keys())[-12:]
    trend_values = [trend_data[m] for m in trend_labels]

    # ── Course rankings / drill-down ──────────────────────────────
    course_memberships = CourseMembership.objects.filter(course__organization=organization, role="student")
    if is_unit_scoped:
        course_memberships = course_memberships.filter(course__unit_id__in=scoped_unit_ids)
    if course_id:
        course_memberships = course_memberships.filter(course_id=course_id)
    course_student_counts = dict(
        course_memberships.values("course_id")
        .annotate(student_count=Count("user", distinct=True))
        .values_list("course_id", "student_count")
    )
    course_exam_counts = dict(
        exams.values("course_id").annotate(exam_count=Count("id")).values_list("course_id", "exam_count")
    )
    course_attempt_counts = dict(
        attempts.values("exam__course_id")
        .annotate(attempt_count=Count("id"))
        .values_list("exam__course_id", "attempt_count")
    )
    course_assignment_counts = dict(
        assignment_subs.values("assignment__course_id")
        .annotate(assignment_total=Count("id"))
        .values_list("assignment__course_id", "assignment_total")
    )
    course_rankings = []
    for course in courses.select_related("owner").order_by("title"):
        owner_name = f"{course.owner.first_name} {course.owner.last_name}".strip() if course.owner_id else ""
        course_rankings.append(
            {
                "course__id": course.id,
                "course__title": course.title,
                "teacher_name": owner_name or getattr(course.owner, "username", ""),
                "student_count": course_student_counts.get(course.id, 0),
                "exam_count": course_exam_counts.get(course.id, 0),
                "attempt_count": course_attempt_counts.get(course.id, 0),
                "assignment_total": course_assignment_counts.get(course.id, 0),
            }
        )
    course_rankings.sort(key=lambda row: (-row["student_count"], row["course__title"].lower()))

    # ── Teacher overview ──────────────────────────────────────────
    teacher_user_ids = memberships.filter(role__level__gte=55).values_list("user_id", flat=True)
    teacher_course_counts = dict(
        Course.objects.filter(organization=organization, owner_id__in=teacher_user_ids)
        .values("owner_id")
        .annotate(course_count=Count("id"))
        .values_list("owner_id", "course_count")
    )
    teacher_student_counts = dict(
        CourseMembership.objects.filter(
            course__organization=organization, role="student", course__owner_id__in=teacher_user_ids
        )
        .values("course__owner_id")
        .annotate(student_count=Count("user", distinct=True))
        .values_list("course__owner_id", "student_count")
    )
    teacher_exam_counts = dict(
        exams.values("author_id").annotate(exam_count=Count("id")).values_list("author_id", "exam_count")
    )
    teacher_attempt_counts = dict(
        attempts.values("exam__author_id")
        .annotate(attempt_count=Count("id"))
        .values_list("exam__author_id", "attempt_count")
    )
    teacher_scores = defaultdict(list)
    for attempt in attempts.filter(status__in=["submitted", "expired"]).values(
        "exam__author_id",
        "exam__exam_type",
        "correct_count",
        "wrong_count",
        "teacher_score",
    ):
        total = (attempt["correct_count"] or 0) + (attempt["wrong_count"] or 0)
        score = (
            float(attempt["teacher_score"] or 0)
            if attempt["exam__exam_type"] == "written"
            else (round((attempt["correct_count"] or 0) * 100 / total, 1) if total else 0)
        )
        teacher_scores[attempt["exam__author_id"]].append(score)
    teacher_overview = []
    _teacher_ids = list(teacher_user_ids)[:20]
    # Əvvəl hər teacher üçün ayrıca User sorğusu idi (20-yə qədər N+1). İndi tək
    # id__in sorğusu + dict lookup.
    _users_by_id = {
        u["id"]: u for u in User.objects.filter(id__in=_teacher_ids).values("id", "username", "first_name", "last_name")
    }
    for tid in _teacher_ids:
        t_user = _users_by_id.get(tid)
        if t_user:
            teacher_overview.append(
                {
                    "user_id": tid,
                    "username": t_user["username"],
                    "name": f"{t_user['first_name']} {t_user['last_name']}".strip() or t_user["username"],
                    "exam_count": teacher_exam_counts.get(tid, 0),
                    "course_count": teacher_course_counts.get(tid, 0),
                    "student_count": teacher_student_counts.get(tid, 0),
                    "attempt_count": teacher_attempt_counts.get(tid, 0),
                    "avg_score": _safe_avg(teacher_scores.get(tid, [])),
                }
            )
    teacher_overview.sort(key=lambda row: (-row["attempt_count"], row["name"].lower()))

    return {
        "summary": {
            "total_members": total_members,
            "teacher_count": teacher_count,
            "student_count": student_count,
            "total_courses": total_courses,
            "active_courses": active_courses,
            "total_exams": total_exams,
            "total_attempts": attempt_agg["total"] or 0,
            "submitted_attempts": attempt_agg["submitted"] or 0,
            "checked_attempts": attempt_agg["checked"] or 0,
            "assignment_total": asn_agg["total"] or 0,
            "assignment_graded": asn_agg["graded"] or 0,
            "assignment_late": asn_agg["late"] or 0,
            "lab_total": lab_agg["total"] or 0,
            "lab_graded": lab_agg["graded"] or 0,
            "project_total": proj_agg["total"] or 0,
            "project_graded": proj_agg["graded"] or 0,
        },
        "trend": {
            "labels": trend_labels,
            "values": trend_values,
        },
        "course_rankings": course_rankings,
        "teacher_overview": teacher_overview,
    }
