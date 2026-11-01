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


# Source-pinned chair complaints and Master journals; encrypted read-only evidence.
OFFERINGS += (
    "7effa191-f9c6-420c-9a6d-bd2b75f872a7",
    "86236c69-0011-46e3-88a4-0e5124290d0f",
    "4fee5132-a7ff-4f9f-b4d9-93c22f54bdfc",
    "dfb06cc3-4b48-47ea-a90d-d15ef5e840ca",
    "0ad85d3e-a9a3-480e-926a-68a384cb2435",
    "e3071d54-4e9a-48fb-8243-5fcd293f590e",
    "0b3f8a13-b8b7-4afb-8d35-9facea3678b4",
    "7f30c5fb-aaca-4ed6-8e24-23cad8e43b1d",
    "e7db7b1c-a775-49de-819d-f7d6cc2a94fd",
    "3e6597d9-aa93-4fb9-9123-5663641e5581",
    "4f390c8b-1630-4bb4-899d-7673457a0fcb",
    "b3698474-9c59-4ef2-b364-84f160de3be3",
    "760fab98-7f67-4049-8ea1-665c7a163f60",
    "aaa64164-02e7-45f6-9c9d-f684ad8823f5",
    "994ac851-2f8b-488f-ae41-68ffd02806bd",
    "60845028-cddf-4d4a-b0ad-a722a084ca15",
)


# Exact philosophy, economics and social-work complaint targets.
OFFERINGS += (
    "1d94cef9-fe09-4d46-937c-2b0279e6d250",
    "2f101bc7-c75e-415f-acfe-c60d74b26404",
    "7b489442-42f5-4aa1-871e-acd9402db691",
    "031fb43f-bf48-49c6-a04a-36472784835a",
    "1f52c763-543d-4762-b13f-d02742a069cb",
    "33359d6c-8e0b-466d-888b-7513057beb61",
    "9059f58d-83ca-4047-81f4-df9091274082",
    "a80d79bc-8c21-4d8a-890c-9e5de2c65e2f",
    "c356236c-da58-431f-a5a4-95a1c736e293",
    "fb9a5106-77db-40d7-9909-553796de8bf7",
    "6b97fff8-9c2a-411c-b386-2abfd01dddfe",
    "be5cde33-7633-4676-a2e0-b42384b4536a",
    "cf633af0-7fc7-4f10-92ee-5d8e0f0428c3",
    "d67ff30e-8492-40c1-b57b-bb4a6a75f128",
    "e465b53a-3c5e-48fe-b5cf-ef303d645362",
    "f2b78ecb-7a30-4b23-a8a8-863423d17c57",
    "195f0bf3-64cf-4af2-a933-a48e3d2d7c59",
    "3f4f9d58-25f4-40ca-b585-e1a8c79cb33c",
    "95666bd3-9583-424a-bd6a-7eef0dd772c8",
    "0fed458d-abae-4846-a00d-d94d55ac5ae2",
    "236dea8a-80b9-4bf5-a00e-3761255e0aca",
    "72742613-1575-455f-805a-513f077abbbd",
    "a41adc2d-7b67-4339-8f3a-d87bffb8c04a",
)


# Exact Economics source82 handover review: retained owner8132 history, source owner9551.
# Evidence only; do not infer a teacher/date reassignment from missing attribution.
ECONOMICS_INTRO_OFFERINGS = (
    "9e2322c8-06e9-40e8-ac72-100a83f4e821",
    "af39bfdc-ce5d-4fd3-9983-e0e29792909f",
    "7a62f438-d684-4710-a29c-ed867f7ee30b",
    "de94fc77-9188-4bc1-9527-5c240a5d56c8",
)
OFFERINGS += ECONOMICS_INTRO_OFFERINGS


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
    from .repair_evidence import collect_repair_evidence

    return {
        **collect_repair_evidence(organization_id=ORG),
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
