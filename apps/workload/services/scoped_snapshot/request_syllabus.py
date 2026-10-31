"""MR83: exact syllabus identities/shares, without exporting authored text."""

from django.apps import apps
from django.db.models import Q

from .data import ORG

OFFERINGS = (
    "bc43c298-975e-4a1e-9b5a-f53cb7e845e1",
    "8daaec47-1ba2-4507-a57f-52d6a406fabc",
)
SYLLABI = (
    "4e0a8d4a-2e22-4111-819b-79d9c0218919",
    "3f12a9dd-3fac-48db-8545-af533efd2321",
)


def collect_request_syllabus():
    offerings = apps.get_model("registrar.CourseOffering").objects.filter(organization_id=ORG, pk__in=OFFERINGS)
    shares = apps.get_model("syllabus.SyllabusShare").objects.filter(
        organization_id=ORG, offering__in=offerings, syllabus__organization_id=ORG
    )
    syllabi = (
        apps.get_model("syllabus.Syllabus")
        .objects.filter(organization_id=ORG)
        .filter(Q(pk__in=SYLLABI) | Q(offering__in=offerings) | Q(pk__in=shares.values("syllabus_id")))
    )
    versions = syllabi.values("current_version_id")
    sections = apps.get_model("syllabus.SyllabusSection").objects.filter(organization_id=ORG, version_id__in=versions)
    topic_counts = {}
    for section in sections.filter(section_id="week"):
        topic_counts[str(section.version_id)] = sum(
            bool(str(row.get("topic") or "").strip())
            for row in (section.data or {}).get("rows", [])
            if isinstance(row, dict)
        )
    return {
        "request_syllabus_topic_counts": topic_counts,
        "request_syllabus_offerings": list(
            offerings.order_by("pk").values("id", "subject_id", "period_id", "instructor_id", "group_id", "is_active")
        ),
        "request_syllabi": list(
            syllabi.order_by("pk").values(
                "id",
                "offering_id",
                "author_id",
                "subject_id",
                "period_id",
                "is_active",
                "current_version_id",
                "approved_version_id",
                "reused_from_id",
            )
        ),
        "request_syllabus_shares": list(shares.order_by("pk").values("id", "offering_id", "syllabus_id", "source")),
    }
