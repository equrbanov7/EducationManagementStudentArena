"""Sərhədli yük bərpaları üçün akademik məzmunun tam-sahə müqayisəsi."""

from django.core.exceptions import EmptyResultSet
from django.db import connection
from django.db.models import Q

from .sbio235_state import digest, model, records


def academic_queries(*, organization_id, offerings):
    """Eyni bounded məzmun xəritəsi Python və DB-də hesablanan fingerprintlər üçün."""
    offering_ids = [o.pk for o in offerings]
    syllabus_scope = Q(pk__in=[])
    for offering in offerings:
        syllabus_scope |= Q(subject_id=offering.subject_id, period_id=offering.period_id)
    queries = {
        "offering": model("registrar.CourseOffering").objects.filter(
            organization_id=organization_id, pk__in=offering_ids
        ),
        "lesson": model("registrar.Lesson").objects.filter(
            organization_id=organization_id, offering_id__in=offering_ids
        ),
        "enrollment": model("registrar.Enrollment").objects.filter(
            organization_id=organization_id, offering_id__in=offering_ids
        ),
        "syllabus": model("syllabus.Syllabus").objects.filter(syllabus_scope, organization_id=organization_id),
        "journal_share": model("registrar.JournalShare").objects.filter(
            organization_id=organization_id, offering_id__in=offering_ids
        ),
        "handover": model("registrar.TeachingHandover").objects.filter(
            organization_id=organization_id, offering_id__in=offering_ids
        ),
    }
    lesson_ids = queries["lesson"].values("pk")
    enrollment_ids = queries["enrollment"].values("pk")
    queries["mark"] = model("registrar.LessonMark").objects.filter(
        organization_id=organization_id, lesson_id__in=lesson_ids
    )
    queries["selfwork_topic"] = model("registrar.SelfWorkTopic").objects.filter(
        organization_id=organization_id, offering_id__in=offering_ids
    )
    queries["selfwork"] = model("registrar.SelfWorkMark").objects.filter(
        organization_id=organization_id, enrollment_id__in=enrollment_ids
    )
    for name in ("ComponentScore", "CriterionScore", "CourseWork", "FinalGrade", "ResitRecord"):
        queries[name.lower()] = model("registrar." + name).objects.filter(
            organization_id=organization_id, enrollment_id__in=enrollment_ids
        )
    for name in ("AssessmentScheme", "AssessmentComponent", "ScheduleSlot"):
        queries[name.lower()] = model("registrar." + name).objects.filter(
            organization_id=organization_id, offering_id__in=offering_ids
        )
    syllabus_ids = queries["syllabus"].values("pk")
    queries["syllabus_share"] = model("syllabus.SyllabusShare").objects.filter(
        organization_id=organization_id, syllabus_id__in=syllabus_ids
    )
    queries["version"] = model("syllabus.SyllabusVersion").objects.filter(syllabus_id__in=syllabus_ids)
    queries["section"] = model("syllabus.SyllabusSection").objects.filter(
        version_id__in=queries["version"].values("pk")
    )
    queries["review"] = model("syllabus.SyllabusReview").objects.filter(version_id__in=queries["version"].values("pk"))
    return queries


def academic_fingerprint(*, organization_id, offerings, lock=False):
    """Hər bütün-sahə məzmununun yalnız count+SHA-sı auditə gedir."""
    result = {}
    for key, qs in academic_queries(organization_id=organization_id, offerings=offerings).items():
        data = records(qs, lock=lock)
        result[key] = {"count": len(data), "sha256": digest(data)}
    return result


def academic_database_fingerprint(*, organization_id, offerings, exclude=()):
    """Tam row JSON hashı DB-də qalır; bütün kafedraların markları Python-a yüklənmir."""
    result = {}
    for key, qs in academic_queries(organization_id=organization_id, offerings=offerings).items():
        if key in exclude:
            continue
        try:
            sql, params = qs.order_by().query.sql_with_params()
        except EmptyResultSet:
            result[key] = {"count": 0, "md5": ""}
            continue
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*), md5(coalesce(string_agg(md5(row_to_json(state)::text), '' ORDER BY id), '')) "
                "FROM (" + sql + ") state",
                params,
            )
            count, md5 = cursor.fetchone()
        result[key] = {"count": count, "md5": md5}
    return result
