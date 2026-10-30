"""Exact, encrypted-only evidence for five source-verified journal targets."""

from django.apps import apps

from .data import ORG

# MR27, MR118's two duplicate-subject openings, and reviewed sources22/51.
OFFERINGS = (
    "567a6fc3-df03-4cac-beca-7f0674ea9137",
    "2241fd3f-735a-4a78-a2c2-14ec7a7edf92",
    "0858f3cf-76eb-47b3-8842-4098e32c17a2",
    "2bcf2c6e-817e-4ac0-a54b-9c78820f60b2",
    "1206a0f5-1483-4b67-b820-9f976f335231",
)


def collect_request_content():
    """Called only inside the parent repeatable-read read-only RLS transaction.

    Numeric student keys are needed to join the authorized legacy recovery.
    No names, usernames, contacts, passwords or unrestricted roster is exported.
    The parent encrypts the complete payload before writing anything to disk.
    """
    offerings = apps.get_model("registrar", "CourseOffering").objects.filter(organization_id=ORG, pk__in=OFFERINGS)
    ids = list(offerings.values_list("id", flat=True))
    enrollments = apps.get_model("registrar", "Enrollment").objects.filter(organization_id=ORG, offering_id__in=ids)
    lessons = apps.get_model("registrar", "Lesson").objects.filter(organization_id=ORG, offering_id__in=ids)
    marks = apps.get_model("registrar", "LessonMark").objects.filter(
        organization_id=ORG,
        lesson__organization_id=ORG,
        lesson__offering_id__in=ids,
        enrollment__organization_id=ORG,
        enrollment__offering_id__in=ids,
    )
    return {
        "request_content_offerings": list(
            offerings.order_by("id").values("id", "subject_id", "group_id", "period_id", "instructor_id", "is_active")
        ),
        "request_content_enrollments": list(
            enrollments.order_by("id").values("id", "offering_id", "student_id", "status", "superseded_by_id")
        ),
        "request_content_lessons": list(
            lessons.order_by("id").values(
                "id", "offering_id", "date", "start_time", "end_time", "kind", "hours", "instructor_id"
            )
        ),
        "request_content_marks": list(
            marks.order_by("id").values("id", "lesson_id", "enrollment_id", "status", "score")
        ),
    }
