"""One reviewed missing seminar, 28 PRESENT only; remaining 58 QB stay deferred."""

import json

from .scoped_snapshot.history_scope import CompiledHistoryScope

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
TARGET = "1aca3f3c-5677-494e-af12-5622d2c1ea0a"
LESSON = "a4519e29-a241-5f2a-95be-82e2c10466fb"
DATE = "2026-10-29"
START = "15:15:00"
TOPIC = "Meşələrin formalaşmasına təsir edən ekoloji amillər"
SOURCE_SHA = "ce94b0cfc7a35f5d4595005474283492854f690b8532e9c57463f3a5ff377bc3"
PAYLOAD_DIGEST = "0739a1464aa102f45df1fd084404f9dcc3b09cc56075a89a5c307e8a71de00fb"
SOURCE_REVIEW_SHA = "4c96c3229d3a3ba27a547f2a0caa3293940fdf3afed34b1df31d4dd3d71ae777"
SOURCE_METADATA_ID = 315602
SOURCE_CALENDAR_IDS = (385260,)
WORKLOAD_ROW = "52c43acb-d2dd-43c5-8e27-19f482941a4a"
WORKLOAD_ASSIGNMENT = "9453f900-8177-41df-84c9-53381f956479"
SPEC = {
    "group_id": "019ec66e-27e4-484a-bd28-06f8a0371e55",
    "journal_id": 14434,
    "journal_uniqid": "JCACImygnA",
    "legacy_group_id": 782,
    "legacy_subject_id": 1806,
    "legacy_teacher_id": 686,
    "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
    "selection_id": 0,
    "special": False,
    "subject_id": "1b844ff4-e94a-4f53-9fac-41d18fdfaf7b",
    "teacher_id": 8149,
}
RECORDS = {
    5489082: (5868, 8121, "5eab521f-499f-4f91-8104-cc7dd4393cab"),
    5489083: (5869, 8122, "c493c8fc-3de4-4882-8d89-326ca5e77cbe"),
    5489084: (5915, 8168, "08985048-a434-4435-9dfe-33c694d9ae99"),
    5489085: (6081, 8335, "c4664bf0-b921-4273-baa3-fbbe4282e6d2"),
    5489086: (6086, 8340, "5f9f24a5-6af9-4dad-82b0-d69e879d4097"),
    5489087: (6083, 8337, "acbcd480-4092-49f2-968d-8f729d65a457"),
    5489088: (6101, 8355, "499a4851-9ac6-41fc-8d06-3cdfe18cbb4e"),
    5489089: (6104, 8358, "2706a5f2-2299-4714-a9b0-78cd04c0d713"),
    5489090: (6106, 8360, "5f867cd0-55f7-4b69-bbed-cf197090d653"),
    5489091: (6130, 8384, "ec6dcd68-546a-47b3-92cf-9343a0a1be5f"),
    5489092: (6135, 8389, "58468151-cfec-44a3-9c8e-2b8997bb48e5"),
    5489093: (6138, 8392, "c3394be6-43b6-44f8-bf13-776f2f28d421"),
    5489094: (6142, 8396, "71ef5433-d4f6-4c32-b920-db084e0b8eed"),
    5489095: (6148, 8402, "b505e7db-96c5-4913-bf99-bdb8a5903614"),
    5489096: (6170, 8424, "d50d4aad-537a-4a00-aac8-322edc84b146"),
    5489097: (6174, 8428, "65947186-6f42-47f3-88a0-32f77d906b42"),
    5489098: (6179, 8433, "5aa2c8f6-6d22-4b27-a014-a17559e335bc"),
    5489099: (6188, 8442, "7cdc8162-e4ae-4a9d-806f-c1c84f33c608"),
    5489100: (6191, 8445, "fa6b07b8-1a4f-4828-bbd6-6b1130c954c3"),
    5489101: (6195, 8449, "467cc8b5-a06d-4e8a-8acc-cbab90550198"),
    5489102: (6200, 8454, "be9da92c-b1a7-4afb-a3a1-d42ae5f778da"),
    5489103: (6210, 8464, "244f346f-392a-4634-81d6-ff93484658c6"),
    5489104: (6204, 8458, "0d855802-6c9c-4a56-a338-9496c9b9d879"),
    5489105: (6215, 8469, "91e2e6ba-a649-4538-8712-ab2c3d68fe4c"),
    5489106: (6219, 8473, "f40bbfc7-a697-463d-8f47-b6a630b9569f"),
    5489107: (6223, 8477, "06760c1d-096b-44cc-81bb-b7633dd3a4e4"),
    5489108: (6230, 8484, "51da6ab2-485d-4498-a04e-fa71e4a35a0a"),
    5489109: (6601, 8855, "cc99fff6-ed6b-4d7f-9175-64d783f44ca1"),
}
CASES = {
    point: {
        "student_id": uid,
        "source_student_id": sid,
        "source_worker_id": SPEC["legacy_teacher_id"],
        "source_subject_id": SPEC["legacy_subject_id"],
        "source_group_id": SPEC["legacy_group_id"],
        "offering_id": TARGET,
        "enrollment_id": enrollment,
        "lesson_id": LESSON,
        "date": DATE,
        "start_time": START,
        "kind": "seminar",
    }
    for point, (uid, sid, enrollment) in RECORDS.items()
}
SOURCE_KEYS = {
    "worker": [str(SPEC["legacy_teacher_id"])],
    "student": [str(c["source_student_id"]) for c in CASES.values()],
    "lesson_subject": [str(SPEC["legacy_subject_id"])],
    "group_unit": [str(SPEC["legacy_group_id"])],
    "course_offering": [f"{SPEC['journal_uniqid']}:{SPEC['legacy_group_id']}"],
    "journal_enrollment": [f"{SPEC['journal_uniqid']}:{c['source_student_id']}" for c in CASES.values()],
    "journal_marks": [SPEC["journal_uniqid"]],
}

WORKLOAD_TASK = "f9e57565-648f-4365-b533-db04007796d2"
WORKLOAD_CHAIR = "6cb37f21-4d0f-4858-8c53-1f09d4d0efda"


def source28_recovery_spec():
    """Return the one compiled case; caller has no selector or mutable authority."""
    return {
        "target": TARGET,
        "spec": dict(SPEC),
        "cases": json.loads(json.dumps(CASES)),
        "lesson": LESSON,
        "date": DATE,
        "start": START,
        "topic": TOPIC,
        "source_sha": SOURCE_SHA,
        "payload_digest": PAYLOAD_DIGEST,
        "source_review_sha": SOURCE_REVIEW_SHA,
        "calendar_ids": SOURCE_CALENDAR_IDS,
        "metadata_id": SOURCE_METADATA_ID,
        "workload_row": WORKLOAD_ROW,
        "workload_assignment": WORKLOAD_ASSIGNMENT,
    }


HISTORY_SCOPE = CompiledHistoryScope(
    prefix="source28_history",
    undo_operation="fixed_source28_undo",
    cases_json=json.dumps(CASES, sort_keys=True),
    source_keys_json=json.dumps(SOURCE_KEYS, sort_keys=True),
)


def history_scope():
    return HISTORY_SCOPE
