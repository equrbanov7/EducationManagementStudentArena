"""«Statistika» — TƏŞKİLAT profili: rektor / prorektor / org_admin / RİM rəhbəri
(org-wide) və dekan / kafedra müdiri / tyutor (unit-scoped, `scoped_unit_ids`).

Nə göstərilir (dizayn ekran 17 «Rektor — ümumi baxış» ritmi): üzvlər rol üzrə,
tələbələr ixtisas/qrup üzrə, cari dövrün fənn açılışları, jurnal bağlanması,
sillabus təsdiqi, dərs yükü bölgüsü, dövrün imtahan cəhdləri və apellyasiyalar.
Köhnə 8 kart («0 Kurslar · 0 · 0/0 · 0 · 0» — sahibin ekran görüntüsü) yerinə
hər kart məxrəcli və mənalıdır. Hər rəqəm aqreqatdır (~12 sorğu).

Unit əhatəsi: üzvlər `Membership.scope_unit`, akademik qeydlər `group`,
açılışlar `group`, sillabus `chair_unit`, dərs yükü `chair`, apellyasiya
`org_unit`, kurslar `unit`, imtahanlar kurs unit-i VƏ YA scoped müəllif —
köhnə `get_org_admin_statistics` ilə eyni qayda.
"""

from __future__ import annotations

from django.db.models import Count, Q

from ._shared import (
    STUDENT_ROLE_NAMES,
    TEACHER_ROLE_NAMES,
    Window,
    attempt_outcome,
    distribution,
    pct,
)


def org_metrics(*, organization, window: Window, period=None, scoped_unit_ids=None) -> dict:
    """Təşkilat / struktur vahidi metrik modeli — sabit sayda sorğu."""
    from apps.appeals.models import Appeal
    from apps.appeals.public import APPEAL_STATUS_PENDING, APPEAL_STATUS_UNDER_REVIEW
    from apps.courses.models import Course
    from apps.exams.models import ExamAttempt
    from apps.organizations.models import Membership
    from apps.registrar.models import CourseOffering, StudentAcademicRecord
    from apps.syllabus.models import Syllabus
    from apps.workload.models import TeachingTask

    scoped = scoped_unit_ids is not None
    unit_ids = list(scoped_unit_ids or [])

    memberships = Membership.objects.filter(organization=organization, is_active=True)
    if scoped:
        memberships = memberships.filter(scope_unit_id__in=unit_ids)
    member_agg = memberships.aggregate(
        members=Count("user", distinct=True),
        students=Count("user", distinct=True, filter=Q(role__name__in=STUDENT_ROLE_NAMES)),
        teachers=Count("user", distinct=True, filter=Q(role__name__in=TEACHER_ROLE_NAMES)),
    )
    members = int(member_agg["members"] or 0)
    students = int(member_agg["students"] or 0)
    teachers = int(member_agg["teachers"] or 0)
    roles_rows = memberships.values("role__display_name").annotate(n=Count("user", distinct=True)).order_by("-n")

    records = StudentAcademicRecord.objects.filter(organization=organization, is_active=True)
    if scoped:
        records = records.filter(group_id__in=unit_ids)
    record_agg = records.aggregate(
        total=Count("id"),
        enrolled=Count("id", filter=Q(status="enrolled")),
        on_leave=Count("id", filter=Q(status="academic_leave")),
        programs=Count("program_id", distinct=True),
    )
    group_field = "group__name" if scoped else "program__name"
    students_rows = (
        records.filter(status="enrolled").values(group_field).annotate(n=Count("id")).order_by("-n", group_field)
    )

    offerings = CourseOffering.objects.filter(organization=organization, is_active=True)
    syllabi = Syllabus.objects.filter(organization=organization, is_active=True)
    tasks = TeachingTask.objects.filter(organization=organization)
    if period is not None:
        offerings = offerings.filter(period=period)
        syllabi = syllabi.filter(period=period)
        tasks = tasks.filter(academic_year=period.academic_year)
    if scoped:
        offerings = offerings.filter(group_id__in=unit_ids)
        syllabi = syllabi.filter(chair_unit_id__in=unit_ids)
        tasks = tasks.filter(chair_id__in=unit_ids)
    offering_agg = offerings.aggregate(
        total=Count("id"),
        groups=Count("group_id", distinct=True),
        instructors=Count("instructor_id", distinct=True),
        journals_published=Count("assessment_scheme", filter=Q(assessment_scheme__is_published=True)),
    )
    syllabus_agg = syllabi.aggregate(
        total=Count("id"),
        approved=Count("id", filter=Q(current_version__status="approved")),
        pending=Count("id", filter=Q(current_version__status__in=("submitted", "review"))),
    )
    task_agg = tasks.aggregate(
        total=Count("id"),
        distributed=Count("id", filter=Q(status__in=("distributed", "amended"))),
        in_progress=Count("id", filter=Q(status__in=("distributing", "pending_final_approval", "approved"))),
    )

    courses = Course.objects.filter(organization=organization)
    if scoped:
        courses = courses.filter(unit_id__in=unit_ids)
    course_agg = courses.aggregate(total=Count("id"), published=Count("id", filter=Q(status="published")))

    attempts = ExamAttempt.objects.filter(exam__organization=organization, exam__is_deleted=False)
    if scoped:
        attempts = attempts.filter(
            Q(exam__course__unit_id__in=unit_ids) | Q(exam__author_id__in=memberships.values("user_id"))
        )
    outcome = attempt_outcome(window.apply(attempts, "started_at"))

    appeals = window.apply(Appeal.objects.filter(organization=organization), "created_at")
    if scoped:
        appeals = appeals.filter(org_unit_id__in=unit_ids)
    appeal_agg = appeals.aggregate(
        total=Count("id"),
        open=Count("id", filter=Q(status__in=(APPEAL_STATUS_PENDING, APPEAL_STATUS_UNDER_REVIEW))),
    )

    return {
        "profile": "unit_manager" if scoped else "org_admin",
        "window": window.as_dict(),
        "period": {"label": f"{period.name} {period.academic_year}".strip() if period else ""},
        "members": {
            "total": members,
            "students": students,
            "teachers": teachers,
            "staff": max(members - students - teachers, 0),
            "by_role": distribution(roles_rows, label_key="role__display_name"),
        },
        "records": {
            "total": int(record_agg["total"] or 0),
            "enrolled": int(record_agg["enrolled"] or 0),
            "on_leave": int(record_agg["on_leave"] or 0),
            "programs": int(record_agg["programs"] or 0),
            "grouped_by": "group" if scoped else "program",
            "distribution": distribution(students_rows, label_key=group_field),
        },
        "offerings": {
            "total": int(offering_agg["total"] or 0),
            "groups": int(offering_agg["groups"] or 0),
            "instructors": int(offering_agg["instructors"] or 0),
            "journals_published": int(offering_agg["journals_published"] or 0),
            "journals_pct": pct(offering_agg["journals_published"], offering_agg["total"]),
        },
        "syllabi": {
            "total": int(syllabus_agg["total"] or 0),
            "approved": int(syllabus_agg["approved"] or 0),
            "pending": int(syllabus_agg["pending"] or 0),
            "approved_pct": pct(syllabus_agg["approved"], syllabus_agg["total"]),
        },
        "workload": {
            "total": int(task_agg["total"] or 0),
            "distributed": int(task_agg["distributed"] or 0),
            "in_progress": int(task_agg["in_progress"] or 0),
            "distributed_pct": pct(task_agg["distributed"], task_agg["total"]),
        },
        "courses": {
            "total": int(course_agg["total"] or 0),
            "published": int(course_agg["published"] or 0),
        },
        "outcome": outcome,
        "appeals": {
            "total": int(appeal_agg["total"] or 0),
            "open": int(appeal_agg["open"] or 0),
        },
    }
