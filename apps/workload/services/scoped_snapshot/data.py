"""WCU workload reconciliation: explicit field allowlists, no student-level data."""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Count, Q, Sum

from core.permissions import has_permission

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
YEAR = "2026/2027"


def rows(label, fields, **filters):
    """All domain reads carry the fixed tenant even when the DB role bypasses RLS."""
    return list(apps.get_model(label).objects.filter(organization_id=ORG, **filters).order_by("pk").values(*fields))


def collect():
    tasks = rows("workload.TeachingTask", ("id", "chair_id", "academic_year", "status", "revision"), academic_year=YEAR)
    task_ids = [r["id"] for r in tasks]
    plans = rows(
        "workload.TeachingTaskRow",
        (
            "id",
            "task_id",
            "subject_id",
            "subject_text",
            "period_id",
            "season",
            "row_kind",
            "groups_text",
            "specialty_id",
            "education_form",
            "degree_level",
            "student_count",
            "union_count",
            "subgroup_count",
            "lecture_plan",
            "lecture_total",
            "seminar_plan",
            "seminar_total",
            "lab_plan",
            "lab_total",
            "consult_hours",
            "exam_hours",
            "thesis_hours",
            "postgrad_hours",
            "practice_research_hours",
            "practice_production_hours",
            "total_hours",
            "credits",
        ),
        task_id__in=task_ids,
    )
    plan_ids = [r["id"] for r in plans]
    groups = rows("organizations.OrgUnit", ("id", "name", "code", "parent_id", "unit_type", "is_active", "settings"))
    for group in groups:
        group["settings"] = {
            k: v
            for k, v in (group["settings"] or {}).items()
            if k in {"parent_group", "degree_level", "education_form", "language", "sector"}
            and isinstance(v, (str, int, bool))
        }
    links = list(
        apps.get_model("workload.TeachingTaskRow")
        .objects.filter(organization_id=ORG, id__in=plan_ids, groups__organization_id=ORG)
        .order_by("id", "groups__id")
        .values("id", "groups__id")
    )
    assignments = rows(
        "workload.TeacherAssignment",
        ("id", "row_id", "teacher_id", "activity", "hours", "is_hourly_paid"),
        row_id__in=plan_ids,
    )
    periods = rows(
        "organizations.AcademicPeriod",
        ("id", "name", "academic_year", "period_type", "start_date", "end_date", "is_active"),
        academic_year=YEAR,
    )
    period_ids = [r["id"] for r in periods]
    offerings = rows(
        "registrar.CourseOffering",
        ("id", "subject_id", "period_id", "group_id", "instructor_id", "lesson_hours", "is_active"),
        period_id__in=period_ids,
    )
    offering_ids = [r["id"] for r in offerings]
    subjects = rows(
        "registrar.Subject",
        ("id", "name", "code", "chair_unit_id"),
        id__in={r["subject_id"] for r in plans + offerings if r["subject_id"]},
    )
    syllabi = rows(
        "syllabus.Syllabus",
        (
            "id",
            "author_id",
            "offering_id",
            "period_id",
            "subject_id",
            "is_active",
            "current_version_id",
            "approved_version_id",
            "reused_from_id",
        ),
        period_id__in=period_ids,
    )
    syllabus_versions = rows(
        "syllabus.SyllabusVersion",
        ("id", "syllabus_id", "major", "minor", "status", "locked_at"),
        syllabus_id__in=[r["id"] for r in syllabi],
    )
    lesson_teacher_hours = list(
        apps.get_model("registrar.Lesson")
        .objects.filter(organization_id=ORG, offering__organization_id=ORG, offering_id__in=offering_ids)
        .values("offering_id", "instructor_id", "kind")
        .annotate(count=Count("id"), hours=Sum("hours"))
        .order_by("offering_id", "instructor_id", "kind")
    )
    enrollment_status_counts = list(
        apps.get_model("registrar.Enrollment")
        .objects.filter(organization_id=ORG, offering__organization_id=ORG, offering_id__in=offering_ids)
        .values("offering_id", "status")
        .annotate(count=Count("id"))
        .order_by("offering_id", "status")
    )
    roles = rows("organizations.Role", ("id", "name", "permissions", "is_active"))
    teaching_roles = {r["id"] for r in roles if has_permission(r["permissions"] or [], "grade.input")}
    memberships = rows(
        "organizations.Membership",
        ("id", "user_id", "role_id", "scope_unit_id", "is_active"),
        role_id__in=teaching_roles,
    )
    teacher_ids = {r["teacher_id"] for r in assignments if r["teacher_id"]}
    teacher_ids |= {r["instructor_id"] for r in offerings if r["instructor_id"]}
    teacher_ids |= {r["user_id"] for r in memberships}
    teacher_ids |= {r["instructor_id"] for r in lesson_teacher_hours if r["instructor_id"]}
    # Global auth table has no tenant column. Restrict by tenant-derived teacher IDs;
    # never load auth model objects (which would select password hashes).
    teachers = list(
        get_user_model()
        .objects.filter(Q(memberships__organization_id=ORG) | Q(profile__organization_id=ORG), id__in=teacher_ids)
        .distinct()
        .order_by("id")
        .values("id", "username", "first_name", "last_name", "is_active")
    )
    profiles = {
        r["user_id"]: r["patronymic"]
        for r in rows("accounts.UserProfile", ("user_id", "patronymic"), user_id__in=teacher_ids)
    }
    for teacher in teachers:
        teacher["patronymic"] = profiles.get(teacher["id"], "")
    stats = list(
        apps.get_model("registrar.StudentAcademicRecord")
        .objects.filter(organization_id=ORG, group__organization_id=ORG)
        .values("group_id", "status")
        .annotate(count=Count("id"))
        .order_by("group_id", "status")
    )
    return {
        "tasks": tasks,
        "rows": plans,
        "row_groups": links,
        "groups": groups,
        "assignments": assignments,
        "periods": periods,
        "offerings": offerings,
        "subjects": subjects,
        "syllabi": syllabi,
        "memberships": memberships,
        "teaching_roles": [{k: r[k] for k in ("id", "name", "is_active")} for r in roles if r["id"] in teaching_roles],
        "teachers": teachers,
        "academic_record_counts": stats,
        "offering_counts": offering_counts(offering_ids),
        "lesson_teacher_hours": lesson_teacher_hours,
        "enrollment_status_counts": enrollment_status_counts,
        "syllabus_versions": syllabus_versions,
    }


def offering_counts(offering_ids):
    """Opaque state fingerprints computed in DB; no mark/student values leave DB."""
    if not offering_ids:
        return []
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT o.id,
              (SELECT count(*) FROM registrar_enrollment e WHERE e.organization_id=%s AND e.offering_id=o.id),
              (SELECT count(*) FROM registrar_lesson l WHERE l.organization_id=%s AND l.offering_id=o.id),
              (SELECT count(*) FROM registrar_lessonmark m JOIN registrar_lesson l ON l.id=m.lesson_id
                AND l.organization_id=%s WHERE m.organization_id=%s AND l.offering_id=o.id),
              (SELECT md5(coalesce(string_agg(md5(concat_ws('|',e.id,e.status,e.updated_at)),'' ORDER BY e.id),''))
                FROM registrar_enrollment e WHERE e.organization_id=%s AND e.offering_id=o.id),
              (SELECT md5(coalesce(string_agg(md5(concat_ws('|',l.id,l.kind,l.hours,l.instructor_id,l.updated_at)),'' ORDER BY l.id),''))
                FROM registrar_lesson l WHERE l.organization_id=%s AND l.offering_id=o.id),
              (SELECT md5(coalesce(string_agg(md5(concat_ws('|',m.id,m.status,m.score,m.entered_by_id,m.updated_at)),'' ORDER BY m.id),''))
                FROM registrar_lessonmark m JOIN registrar_lesson l ON l.id=m.lesson_id AND l.organization_id=%s
                WHERE m.organization_id=%s AND l.offering_id=o.id)
            FROM registrar_courseoffering o WHERE o.organization_id=%s AND o.id=ANY(%s::uuid[]) ORDER BY o.id
        """,
            [ORG] * 9 + [list(map(str, offering_ids))],
        )
        fields = (
            "offering_id",
            "enrollments",
            "lessons",
            "marks",
            "enrollment_state_md5",
            "lesson_state_md5",
            "mark_state_md5",
        )
        return [dict(zip(fields, row)) for row in cursor.fetchall()]
