"""Exact, encrypted-only evidence for source-verified journal targets."""

from django.apps import apps

from .data import ORG

# MR27, MR118's two duplicate-subject openings, and reviewed sources22/51.
OFFERINGS = (
    "567a6fc3-df03-4cac-beca-7f0674ea9137",
    "2241fd3f-735a-4a78-a2c2-14ec7a7edf92",
    "0858f3cf-76eb-47b3-8842-4098e32c17a2",
    "2bcf2c6e-817e-4ac0-a54b-9c78820f60b2",
    "1206a0f5-1483-4b67-b820-9f976f335231",
    # MR113: exact teacher, subject and group in the authorized snapshot.
    "a083cf1a-a7d0-452f-9c7e-597fb52dd490",
    "3df416e9-68e1-45c4-87c6-ba327f77b3e8",
    "bf4e4637-e084-4801-aae0-0b9829ce8117",
    "56e3ef8e-94f8-4b09-9d58-8523752f5281",
    # MR78, MR87, MR103 and MR105 respectively.
    "6b4fc624-06f3-4358-b24f-e420138c66ad",
    "7ed9430b-0c40-452f-b771-8bb3e4f31a03",
    "ca1bcf85-5d38-4c02-a2e5-b1ece0f5b6b9",
    "1f9b5a6a-e6d2-422d-bc5e-4c006af8ad1d",
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
