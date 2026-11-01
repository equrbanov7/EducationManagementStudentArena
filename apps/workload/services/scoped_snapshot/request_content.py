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


# MR127: Aruz Mikayılov's five named subject/group journals only.
MR127_OFFERINGS = (
    "1fcdbfff-c3dc-4262-b936-4fc035b60c07",  # Hidrologiya,235EKO
    "484e0ebd-e9d5-4211-8c9e-419a534942c3",  # Hidrologiya,235EM
    "7c3a6803-362e-418f-a18b-34fe80aa468e",  # Coğrafi ekologiya,235EKO
    "41ff13ba-694d-4601-be6c-b12a5959a422",  # Meteorologiya,234SBIO
    "acc97b99-90bc-4fb3-b01b-b56ff630b7d2",  # Kartoqrafiya/GİS,233EKO
)
OFFERINGS += MR127_OFFERINGS


# Exact teacher7851 journal identities reviewed in the encrypted31Octsnapshot.
OFFERINGS += (
    "04ccea06-2104-45dd-9c1b-0e5bbdcd26f1",
    "14909f88-ad8d-4a3c-b356-659765f9f2eb",
    "15eca465-2a0d-486d-a09e-8abf58682b79",
    "286abe77-c3ed-4bfb-95ca-1e021f181b86",
    "31c196bb-32c2-470d-9e6f-06a332c64ac1",
    "4582af04-cb96-4fa9-871f-971b8a02cde5",
    "47a7b785-3148-4bd2-9440-52caaac1b797",
    "4a94b82c-a6f9-4e29-9b07-cbbc4a56fb63",
    "6d46e94a-2471-4ea4-8c45-995106102dd6",
    "96ad224d-9e9b-4a2c-9561-658a126e5dd9",
    "9e06bdee-4f53-4dca-bd8c-e86d7794f9c7",  # reviewed631/5K shared journal, exact missing-cell comparison
    "9d5fd8c9-551e-485e-9186-d94a2f5210ef",
    "b49f7692-f462-4420-9ce3-6243b7219b18",
    "b9978e86-9ccf-4009-9f15-e0570f3b0c6a",
    "c159cc10-0d85-4dcd-ad7f-846d3bc822b7",
    "c406ea18-8cdd-4512-843d-91e4abe597e9",
    "c6699552-e833-4c20-9cb0-78ae4be4352b",
    "cf4831c2-7bfb-48a7-8853-4a23f3732d71",
    "d9a31f8c-3c9d-4906-b8d7-b74226fbd0d4",
)


# Exact cloud-computing joint class: teacher8425, sibling groups only.
OFFERINGS += ("81f0635b-63bc-43cb-9ceb-7af91febdc42", "f79fc953-a8c7-4342-a6b6-a8be70cf2784")


# Exact own-source empty journals: encrypted numeric-roster comparison only.
OFFERINGS += (
    "f418c305-2d54-445f-8007-3e3476230a7f",
    "d16d484e-85ef-40af-8429-04183268116d",
    "6fa5ede4-9ba3-4660-a620-c71d2835a91b",
    "0156cf86-feb7-4c22-b26e-7a57324aebf4",
    "ea2966dd-ecc1-4d55-9368-dd7874032324",
    "2052ed8b-7f35-44e6-b1e9-f8707d6fba08",
    "6a4ffa61-dbb9-464f-80d0-4b99745a081c",
    "cf149729-86ec-4837-b22e-0ad9335253fd",
    "9dd82130-8baa-4f4b-8dcb-540efb5cbc05",
)


# Existing canonical language-level journals: compare before any duplicate import.
OFFERINGS += ("e70d2eab-b4ea-428d-97e3-3d94bb2501d6", "b2559db4-9d18-4f4c-bdab-eac80d2d391d")


# Four reviewed own-source syllabus identities and exact raw-subject counterparts.
# Read-only evidence before any course correction; preserve the other teacher's new records.
OFFERINGS += (
    "1911c5cc-dae5-4e13-ba7d-9784fcc28dd0",
    "2778bb99-6c4a-4ca3-968b-69591771f417",
    "61eca9fe-1a06-47f9-b8a1-f3f1d1494720",
    "77c72001-183b-4874-b6d4-333cbb4b3230",
    "892571e3-7270-4ee3-b580-831731901e9c",
    "9aa8baec-2e45-4aa8-b453-38981b1f0a1d",
    "e8df0411-fc94-4e0f-a945-73b983d949c9",
    "f4380572-e795-46c2-b6d9-3af6a1160999",
)


# Existing source-proven history: no duplicate import into empty sibling journals.
OFFERINGS += (
    "31a04416-e4a8-4fb2-8298-36793660f63d",
    "c8bddaad-99b2-476e-80e0-5d87562ec676",
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
    slots = apps.get_model("registrar", "ScheduleSlot")._base_manager.filter(
        organization_id=ORG, offering__organization_id=ORG, offering_id__in=ids
    )
    return {
        "request_content_slots": list(slots.order_by("id").values()),
        "request_content_offerings": list(
            offerings.order_by("id").values("id", "subject_id", "group_id", "period_id", "instructor_id", "is_active")
        ),
        "request_content_enrollments": list(
            enrollments.order_by("id").values("id", "offering_id", "student_id", "status", "superseded_by_id")
        ),
        "request_content_lessons": list(
            lessons.order_by("id").values(
                "id",
                "offering_id",
                "date",
                "start_time",
                "end_time",
                "kind",
                "hours",
                "instructor_id",
                "topic",
                "is_legacy_synthesised",
                "created_by_id",
            )
        ),
        "request_content_marks": list(
            marks.order_by("id").values("id", "lesson_id", "enrollment_id", "status", "score")
        ),
    }
