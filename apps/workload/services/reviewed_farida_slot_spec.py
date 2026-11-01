"""Only the later lesson-inferred AZ1 weekly slot; original DOCX slots remain."""

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"

PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"

SUBJECT = "255a9553-35e4-4603-85c9-17e8cea7d46b"

TEACHER = 8425

TARGET = "68f5682e-7326-4c13-9fb3-2cd88f013808"

ROW = "729e017c-e22d-4439-9f26-a45f17644c69"

RESOURCE = "workload.reviewed_farida_inferred_slot_v1"

SOURCE_SHA = "037d18ad93ea111a34de0ca6699afddabc4a16f73b2d5a70743b226251cea397"

SLOTS = {
    "216179a1-22cd-4031-8014-f02b00abe490": {
        "sha256": "2555316088178ed8361a7f5c741f48ee08e3bd50f6f1ba8c3ae34b247b317e3b",
        "geometry": {
            "organization_id": "526cfa63-4f80-4bba-a7a7-61c8fbb3d918",
            "offering_id": "81f0635b-63bc-43cb-9ceb-7af91febdc42",
            "kind": "lecture",
            "weekday": 3,
            "start_time": "16:55:00",
            "end_time": "18:25:00",
            "week_type": "odd",
            "room": "32",
            "instructor_id": None,
            "created_by_id": 8444,
            "is_parked": False,
            "is_deleted": False,
        },
    },
    "47011bff-2755-46f8-9120-718b7b54c006": {
        "sha256": "09078345dd92328fee6ef74191be8b0cb5ef4144d3d06f22ca367719af7e1f37",
        "geometry": {
            "organization_id": "526cfa63-4f80-4bba-a7a7-61c8fbb3d918",
            "offering_id": "81f0635b-63bc-43cb-9ceb-7af91febdc42",
            "kind": "seminar",
            "weekday": 4,
            "start_time": "15:15:00",
            "end_time": "16:45:00",
            "week_type": "odd",
            "room": "22",
            "instructor_id": None,
            "created_by_id": 8444,
            "is_parked": False,
            "is_deleted": False,
        },
    },
    "68f5682e-7326-4c13-9fb3-2cd88f013808": {
        "sha256": "3e7b1ea35131c2c9f2ba386f9e75d31848d336f94c15962a55f370691170ebbf",
        "geometry": {
            "organization_id": "526cfa63-4f80-4bba-a7a7-61c8fbb3d918",
            "offering_id": "81f0635b-63bc-43cb-9ceb-7af91febdc42",
            "kind": "seminar",
            "weekday": 4,
            "start_time": "16:55:00",
            "end_time": "18:25:00",
            "week_type": "odd",
            "room": "22",
            "instructor_id": None,
            "created_by_id": 8444,
            "is_parked": False,
            "is_deleted": False,
        },
    },
    "658b1237-2e9b-4a85-a2c9-ddd56ebdb05c": {
        "sha256": "a919381ced396c701302814e74f07fd1210d84f84c80a9a0c816c63bc8cbbaff",
        "geometry": {
            "organization_id": "526cfa63-4f80-4bba-a7a7-61c8fbb3d918",
            "offering_id": "9b4eac07-c2b8-49d1-b415-2a6cce779373",
            "kind": "seminar",
            "weekday": 4,
            "start_time": "16:55:00",
            "end_time": "18:25:00",
            "week_type": "odd",
            "room": "22",
            "instructor_id": None,
            "created_by_id": 8444,
            "is_parked": False,
            "is_deleted": False,
        },
    },
    "b656e854-d867-4f0c-ba7a-2c3c25ff0eaf": {
        "sha256": "1fcfbf2e58834f494a2ad325199737b93da694edff104e69575f9e9163f68d2f",
        "geometry": {
            "organization_id": "526cfa63-4f80-4bba-a7a7-61c8fbb3d918",
            "offering_id": "f79fc953-a8c7-4342-a6b6-a8be70cf2784",
            "kind": "lecture",
            "weekday": 3,
            "start_time": "16:55:00",
            "end_time": "18:25:00",
            "week_type": "odd",
            "room": "32",
            "instructor_id": None,
            "created_by_id": 8444,
            "is_parked": False,
            "is_deleted": False,
        },
    },
    "f20d9d17-0c62-4aec-bca9-fc527886c485": {
        "sha256": "2e18e6d3d46adb20d128949618212f4fac15e4badae8c4c09add6874e24f9f61",
        "geometry": {
            "organization_id": "526cfa63-4f80-4bba-a7a7-61c8fbb3d918",
            "offering_id": "f79fc953-a8c7-4342-a6b6-a8be70cf2784",
            "kind": "seminar",
            "weekday": 4,
            "start_time": "15:15:00",
            "end_time": "16:45:00",
            "week_type": "odd",
            "room": "22",
            "instructor_id": None,
            "created_by_id": 8444,
            "is_parked": False,
            "is_deleted": False,
        },
    },
}

CREATION_AUDITS = {
    "36f9a02f-299f-446d-bbcf-1ac2498d536a": {
        "sha256": "486313b6a0ab360472483f3f72d9f2e17ad18f7bb92c37e0e78795fdeb3a4bad",
        "resource_type": "registrar.ScheduleSlot",
        "resource_id": "timetable-docx:timetable_38190301422.docx",
    },
    "53412d1c-b0b6-4b15-859c-21e4a7c390e2": {
        "sha256": "f627dd283076f2c98276c1038ca01488cb1473f8901d62bf22f60c944d2e7884",
        "resource_type": "registrar.ScheduleSlot",
        "resource_id": "infer_timetable_from_lessons",
    },
}

INFERENCE_AUDIT = "53412d1c-b0b6-4b15-859c-21e4a7c390e2"

DOCX_AUDIT = "36f9a02f-299f-446d-bbcf-1ac2498d536a"

LINKED_LESSONS = ["27e2d8eb-0806-4dff-891d-bb912f1cb99d", "32ab9d99-d708-4479-a683-19963215eb5a"]

ROW_FIELDS = {
    "task_id": "b27fed69-e18d-4f33-b183-f46810c13d29",
    "subject_id": "255a9553-35e4-4603-85c9-17e8cea7d46b",
    "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
    "lecture_total": 30,
    "seminar_total": 15,
    "total_hours": 45,
    "subgroup_count": 1,
    "union_count": 1,
}

ASSIGNMENTS = {
    "65134326-501a-4bb2-9789-048df6344e39": (8425, "seminar", 15, False),
    "96f1e7d8-7826-482c-b428-0aa51cc272e8": (8425, "lecture", 30, False),
}

AZ_GROUPS = ["2b471dec-7783-49f1-b17e-cb9acae77f31", "9974b86c-6df9-4565-9002-c67ac2ba18da"]

OFFERINGS = {
    "81f0635b-63bc-43cb-9ceb-7af91febdc42": {
        "subject_id": "255a9553-35e4-4603-85c9-17e8cea7d46b",
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "group_id": "2b471dec-7783-49f1-b17e-cb9acae77f31",
        "instructor_id": 8425,
        "lesson_hours": 45,
        "is_active": True,
    },
    "9b4eac07-c2b8-49d1-b415-2a6cce779373": {
        "subject_id": "255a9553-35e4-4603-85c9-17e8cea7d46b",
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "group_id": "eee00e67-ca42-48b9-8217-dd03027855aa",
        "instructor_id": 8425,
        "lesson_hours": 45,
        "is_active": True,
    },
    "f79fc953-a8c7-4342-a6b6-a8be70cf2784": {
        "subject_id": "255a9553-35e4-4603-85c9-17e8cea7d46b",
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "group_id": "9974b86c-6df9-4565-9002-c67ac2ba18da",
        "instructor_id": 8425,
        "lesson_hours": 45,
        "is_active": True,
    },
}

GROUPS = {
    "2b471dec-7783-49f1-b17e-cb9acae77f31": {
        "parent_id": "167cf0ad-8089-4929-98c1-5405797e229f",
        "unit_type": "group",
        "is_active": True,
        "settings": {
            "degree_level": "bachelor",
            "education_form": "full_time",
            "parent_group": "ba3b395c-699b-471a-9a54-5fbae6092f4b",
            "sector": "az",
        },
    },
    "eee00e67-ca42-48b9-8217-dd03027855aa": {
        "parent_id": "167cf0ad-8089-4929-98c1-5405797e229f",
        "unit_type": "group",
        "is_active": True,
        "settings": {"degree_level": "bachelor", "education_form": "full_time", "sector": "en"},
    },
    "9974b86c-6df9-4565-9002-c67ac2ba18da": {
        "parent_id": "167cf0ad-8089-4929-98c1-5405797e229f",
        "unit_type": "group",
        "is_active": True,
        "settings": {
            "degree_level": "bachelor",
            "education_form": "full_time",
            "parent_group": "ba3b395c-699b-471a-9a54-5fbae6092f4b",
            "sector": "az",
        },
    },
}

GROUP_FAMILY = [
    "2b471dec-7783-49f1-b17e-cb9acae77f31",
    "eee00e67-ca42-48b9-8217-dd03027855aa",
    "9974b86c-6df9-4565-9002-c67ac2ba18da",
    "ba3b395c-699b-471a-9a54-5fbae6092f4b",
]

AUTHORITY_ROWS = ["729e017c-e22d-4439-9f26-a45f17644c69", "f14f2953-5c83-420c-bf64-668c074b0332"]

GUARDS = (
    "farida_slot_academic_preservation_budget",
    "farida_slot_additional_share_authority_requires_review",
    "farida_slot_already_undone_requires_review",
    "farida_slot_assignment_graph_changed",
    "farida_slot_central_audit_material_changed",
    "farida_slot_central_audit_not_exact",
    "farida_slot_control_or_references_changed",
    "farida_slot_course_identity_changed",
    "farida_slot_creation_audit_changed",
    "farida_slot_creation_audit_missing",
    "farida_slot_current_period_locked_or_changed",
    "farida_slot_current_scope_unavailable",
    "farida_slot_exact_receipt_required",
    "farida_slot_fixed_courses_missing",
    "farida_slot_fixed_tenant_required",
    "farida_slot_fresh_baseline_required",
    "farida_slot_fresh_full_row_not_unchanged",
    "farida_slot_geometry_changed",
    "farida_slot_group_identity_changed",
    "farida_slot_group_scope_changed",
    "farida_slot_handover_authority_requires_review",
    "farida_slot_historical_academic_data_changed",
    "farida_slot_inference_origin_not_exact",
    "farida_slot_later_scheduling_override_requires_review",
    "farida_slot_linked_mark_budget",
    "farida_slot_new_group_alias_requires_review",
    "farida_slot_new_immutable_mapping_requires_review",
    "farida_slot_new_intersecting_workload_requires_review",
    "farida_slot_new_linked_lesson_requires_review",
    "farida_slot_new_linked_mark_reference_requires_review",
    "farida_slot_new_reverse_reference_requires_review",
    "farida_slot_official_group_scope_changed",
    "farida_slot_official_positive_row_changed",
    "farida_slot_original_docx_ids_changed",
    "farida_slot_parking_actor_not_exact",
    "farida_slot_partial_assignment_requires_review",
    "farida_slot_planning_state_not_exact",
    "farida_slot_post_action_control_changed",
    "farida_slot_postgresql_required",
    "farida_slot_private_source_required",
    "farida_slot_protected_geometry_changed",
    "farida_slot_receipt_source_scope_changed",
    "farida_slot_receipt_write_failed",
    "farida_slot_review_refused",
    "farida_slot_row_set_changed",
    "farida_slot_sector_or_parent_geometry_changed",
    "farida_slot_six_row_scope_changed",
    "farida_slot_source_bytes_changed",
    "farida_slot_source_sha_required",
    "farida_slot_undo_parking_metadata_not_cleared",
    "farida_slot_unknown_many_to_many_reference",
)

LINKED_MARK_REFS = [
    (
        "24cdfb0b-866d-4462-932b-a43627ea776f",
        "27e2d8eb-0806-4dff-891d-bb912f1cb99d",
        "7c02ef3c-c709-42fe-8ea7-a158ebf23474",
    ),
    (
        "5e3c0335-d1a6-416a-bdb6-fd9233d68945",
        "27e2d8eb-0806-4dff-891d-bb912f1cb99d",
        "f6ab165b-62c5-443c-8191-a6d27d15d738",
    ),
    (
        "6d4272c1-86ee-4f16-b4c9-437a8d3ed554",
        "32ab9d99-d708-4479-a683-19963215eb5a",
        "7c02ef3c-c709-42fe-8ea7-a158ebf23474",
    ),
    (
        "76e87239-fafa-4c7f-aa8c-38536a25e5fd",
        "32ab9d99-d708-4479-a683-19963215eb5a",
        "86fd1810-48d6-4fb0-b8be-9fd7f6b7d561",
    ),
    (
        "89882235-9ff6-494d-a071-e8319de7166b",
        "32ab9d99-d708-4479-a683-19963215eb5a",
        "d48bedc3-069c-4019-9834-41e5c8b5177a",
    ),
    (
        "93d78278-ee6b-459b-b62c-e5d89670d4c4",
        "27e2d8eb-0806-4dff-891d-bb912f1cb99d",
        "d48bedc3-069c-4019-9834-41e5c8b5177a",
    ),
    (
        "a12105d8-8c25-43a6-a3e2-ff143c9b3a5f",
        "27e2d8eb-0806-4dff-891d-bb912f1cb99d",
        "86fd1810-48d6-4fb0-b8be-9fd7f6b7d561",
    ),
    (
        "dc17f404-c307-49cd-b906-12679f8846a0",
        "32ab9d99-d708-4479-a683-19963215eb5a",
        "f6ab165b-62c5-443c-8191-a6d27d15d738",
    ),
]
