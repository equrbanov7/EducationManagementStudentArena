"""Sərhədli yük bərpaları üçün akademik məzmunun tam-sahə müqayisəsi."""

from django.db.models import Q

from .sbio235_state import digest, model, records


def academic_fingerprint(*, organization_id, offerings, lock=False):
    """Hər bütün-sahə məzmununun yalnız count+SHA-sı auditə gedir."""
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
    result = {}
    for key, qs in queries.items():
        data = records(qs, lock=lock)
        result[key] = {"count": len(data), "sha256": digest(data)}
    return result
