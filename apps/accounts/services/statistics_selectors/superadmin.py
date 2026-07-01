"""statistics_selectors paketi — superadmin."""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count, Q

from ._shared import (
    User,
    _apply_date_filter,
    _content_type_enabled,
    _parse_date,
)


def get_superadmin_statistics(*, filters=None):
    """Platform-wide analytics for superadmins — cross-organization."""
    from apps.assignments.models import Submission
    from apps.courses.models import Course
    from apps.exams.models import Exam, ExamAttempt
    from apps.labs.models import LabSubmission
    from apps.organizations.models import Membership, Organization
    from apps.projects.models import ProjectSubmission

    filters = filters or {}
    date_from = _parse_date(filters.get("date_from"))
    date_to = _parse_date(filters.get("date_to"))
    org_id = filters.get("organization")
    course_id = filters.get("course")
    content_type = filters.get("content_type", "all")

    # ── Organizations ─────────────────────────────────────────────
    orgs = Organization.objects.filter(is_active=True, status="active")
    scoped_orgs = orgs.filter(id=org_id) if org_id else orgs
    total_orgs = scoped_orgs.count()

    # ── Users ─────────────────────────────────────────────────────
    total_memberships = Membership.objects.filter(is_active=True, organization__in=scoped_orgs).count()
    if org_id:
        total_users = (
            Membership.objects.filter(is_active=True, organization_id=org_id).values("user").distinct().count()
        )
    else:
        total_users = User.objects.filter(is_active=True).count()

    courses = Course.objects.all()
    if org_id:
        courses = courses.filter(organization_id=org_id)
    if course_id:
        courses = courses.filter(id=course_id)
    total_courses = courses.count()

    exam_qs = Exam.objects.all()
    if org_id:
        exam_qs = exam_qs.filter(organization_id=org_id)
    if course_id:
        exam_qs = exam_qs.filter(course_id=course_id)

    # ── Exams ─────────────────────────────────────────────────────
    attempts = ExamAttempt.objects.none()
    attempt_agg = {"total": 0, "submitted": 0, "checked": 0}
    total_exams = 0
    if _content_type_enabled(content_type, "exam"):
        attempts = ExamAttempt.objects.filter(exam__in=exam_qs)
        attempts = _apply_date_filter(attempts, "started_at", date_from, date_to)
        attempt_agg = attempts.aggregate(
            total=Count("id"),
            submitted=Count("id", filter=Q(status="submitted")),
            checked=Count("id", filter=Q(checked_by_teacher=True)),
        )
        total_exams = exam_qs.count()

    # ── Assignments ───────────────────────────────────────────────
    asn_qs = Submission.objects.none()
    asn_agg = {"total": 0, "graded": 0}
    if _content_type_enabled(content_type, "assignment"):
        asn_qs = Submission.objects.all()
        if org_id:
            asn_qs = asn_qs.filter(assignment__course__organization_id=org_id)
        if course_id:
            asn_qs = asn_qs.filter(assignment__course_id=course_id)
        asn_qs = _apply_date_filter(asn_qs, "submitted_at", date_from, date_to)
        asn_agg = asn_qs.aggregate(
            total=Count("id"),
            graded=Count("id", filter=Q(status="graded")),
        )

    # ── Labs + Projects ───────────────────────────────────────────
    lab_qs = LabSubmission.objects.none()
    lab_agg = {"total": 0, "graded": 0}
    if _content_type_enabled(content_type, "lab"):
        lab_qs = LabSubmission.objects.all()
        if org_id:
            lab_qs = lab_qs.filter(assignment__lab__course__organization_id=org_id)
        if course_id:
            lab_qs = lab_qs.filter(assignment__lab__course_id=course_id)
        lab_qs = _apply_date_filter(lab_qs, "submitted_at", date_from, date_to)
        lab_agg = lab_qs.aggregate(total=Count("id"), graded=Count("id", filter=Q(status="graded")))

    proj_qs = ProjectSubmission.objects.none()
    proj_agg = {"total": 0, "graded": 0}
    if _content_type_enabled(content_type, "project"):
        proj_qs = ProjectSubmission.objects.all()
        if org_id:
            proj_qs = proj_qs.filter(project__course__organization_id=org_id)
        if course_id:
            proj_qs = proj_qs.filter(project__course_id=course_id)
        proj_qs = _apply_date_filter(proj_qs, "submitted_at", date_from, date_to)
        proj_agg = proj_qs.aggregate(total=Count("id"), graded=Count("id", filter=Q(status="graded")))

    # ── Org comparison ────────────────────────────────────────────
    # Org comparison — əvvəl hər org üçün 6 ayrı sorğu idi (×60 org = ~360 sorğu, N+1).
    # İndi organization_id üzrə qruplaşmış 4 aqreqat (member/teacher/student tək
    # sorğuda filtered Count ilə; course/exam/attempt ayrıca qruplaşma).
    org_list = list(scoped_orgs[:60])
    org_ids = [o.id for o in org_list]

    _member_by_org = {
        row["organization_id"]: row
        for row in (
            Membership.objects.filter(organization_id__in=org_ids, is_active=True)
            .values("organization_id")
            .annotate(
                members=Count("user", distinct=True),
                teachers=Count("user", distinct=True, filter=Q(role__level__gte=55)),
                students=Count("user", distinct=True, filter=Q(role__level__lte=30)),
            )
        )
    }
    _courses_by_org = dict(
        Course.objects.filter(organization_id__in=org_ids)
        .values("organization_id")
        .annotate(c=Count("id"))
        .values_list("organization_id", "c")
    )
    _exams_by_org = dict(
        Exam.objects.filter(organization_id__in=org_ids)
        .values("organization_id")
        .annotate(c=Count("id"))
        .values_list("organization_id", "c")
    )
    _attempts_by_org = dict(
        ExamAttempt.objects.filter(exam__organization_id__in=org_ids)
        .values("exam__organization_id")
        .annotate(c=Count("id"))
        .values_list("exam__organization_id", "c")
    )

    org_comparison = []
    for org in org_list:
        m = _member_by_org.get(org.id) or {}
        org_comparison.append(
            {
                "id": org.id,
                "name": org.name,
                "org_type": org.org_type,
                "members": m.get("members", 0),
                "teachers": m.get("teachers", 0),
                "students": m.get("students", 0),
                "courses": _courses_by_org.get(org.id, 0),
                "exams": _exams_by_org.get(org.id, 0),
                "attempts": _attempts_by_org.get(org.id, 0),
            }
        )
    org_comparison.sort(key=lambda row: (-row["attempts"], row["name"].lower()))

    # ── Submission trend ──────────────────────────────────────────
    trend_data = defaultdict(int)
    for a in attempts.filter(started_at__isnull=False).values("started_at"):
        month = a["started_at"].strftime("%Y-%m")
        trend_data[month] += 1
    trend_labels = sorted(trend_data.keys())[-12:]
    trend_values = [trend_data[m] for m in trend_labels]

    return {
        "summary": {
            "total_orgs": total_orgs,
            "total_users": total_users,
            "total_memberships": total_memberships,
            "total_courses": total_courses,
            "total_exams": total_exams,
            "total_attempts": attempt_agg["total"] or 0,
            "submitted_attempts": attempt_agg["submitted"] or 0,
            "checked_attempts": attempt_agg["checked"] or 0,
            "assignment_total": asn_agg["total"] or 0,
            "assignment_graded": asn_agg["graded"] or 0,
            "lab_total": lab_agg["total"] or 0,
            "lab_graded": lab_agg["graded"] or 0,
            "project_total": proj_agg["total"] or 0,
            "project_graded": proj_agg["graded"] or 0,
        },
        "trend": {
            "labels": trend_labels,
            "values": trend_values,
        },
        "org_comparison": org_comparison,
    }
