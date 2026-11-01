"""Exactly two reviewed load rows; source catalog codes are never guessed from Named IDs."""

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"

TEACHER = 8302

PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"

TASK = "b27fed69-e18d-4f33-b183-f46810c13d29"

YEAR = "2026/2027"
CHAIR = "141fb422-d679-439b-96cb-fde5324c644a"

SOURCE = {
    "package_sha256": "745f28c72ba254b1c535f76c52aca07c5d1ca5345aa44b4e9a001e560ea89df5",
    "case_plan_sha256": "9ae2135d21cd49645f164b35ccc23511f3c6641c7df07462d9ceb727566910b7",
    "declared_source_bindings": [
        {
            "case": "leyla-2690-804",
            "named_subject": "b7e2b8b9-6de9-459b-b505-97cee35a9461",
            "canonical_subject": "b5cb7489-372b-482b-b0a9-1a377c92ddd1",
            "group": "d01bed77-fb68-42af-91b2-1c0f76ded413",
            "journal_ids": [15049],
        },
        {
            "case": "leyla-2693-599",
            "named_subject": "11e49bcc-2cea-4092-9af7-e8756fcefcf9",
            "canonical_subject": "5978ae05-0e59-4d65-a072-cd660faf49e9",
            "group": "7b6fa0ae-d8d5-49ee-95b1-a8e0d64fb371",
            "journal_ids": [14880],
        },
        {
            "case": "leyla-2690-846",
            "named_subject": "b7e2b8b9-6de9-459b-b505-97cee35a9461",
            "canonical_subject": "b5cb7489-372b-482b-b0a9-1a377c92ddd1",
            "group": "a20f282e-e127-4aa4-89c1-c05d956e6632",
            "journal_ids": [15050],
        },
    ],
    "note": "Reviewed synthetic Named catalog declarations only; QKU2690/2693 are not raw MariaDB IDs.",
}

ROWS = {
    "02d98bd9-e176-43a8-a9ed-8f1da41adf07": {
        "before_subject": "11e49bcc-2cea-4092-9af7-e8756fcefcf9",
        "after_subject": "5978ae05-0e59-4d65-a072-cd660faf49e9",
        "fields": {
            "consult_hours": 0,
            "credits": "",
            "degree_level": "bachelor",
            "education_form": "eyani",
            "exam_hours": 0,
            "groups_text": "233 İ",
            "lab_plan": 0,
            "lab_total": 0,
            "lecture_plan": 0,
            "lecture_total": 30,
            "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
            "postgrad_hours": 0,
            "practice_production_hours": 0,
            "practice_research_hours": 0,
            "row_kind": "teaching",
            "season": "fall",
            "seminar_plan": 0,
            "seminar_total": 15,
            "specialty_id": "ffd7816f-9905-45d2-81f3-3a2157c0db7d",
            "student_count": 28,
            "subgroup_count": 1,
            "subject_text": "ATMF XI blok:\n"
            "1. Vo İP sistemlərinin təhlükəsizliyi "
            "+\n"
            "2. Blokçeyn texnologiyaları",
            "task_id": "b27fed69-e18d-4f33-b183-f46810c13d29",
            "thesis_hours": 0,
            "total_hours": 45,
            "union_count": 1,
        },
        "groups": ["7b6fa0ae-d8d5-49ee-95b1-a8e0d64fb371"],
    },
    "da34a218-839f-4e76-90b9-dd79f6270772": {
        "before_subject": "b7e2b8b9-6de9-459b-b505-97cee35a9461",
        "after_subject": "b5cb7489-372b-482b-b0a9-1a377c92ddd1",
        "fields": {
            "consult_hours": 0,
            "credits": "",
            "degree_level": "bachelor",
            "education_form": "eyani",
            "exam_hours": 0,
            "groups_text": "235 İ",
            "lab_plan": 0,
            "lab_total": 0,
            "lecture_plan": 0,
            "lecture_total": 30,
            "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
            "postgrad_hours": 0,
            "practice_production_hours": 0,
            "practice_research_hours": 0,
            "row_kind": "teaching",
            "season": "fall",
            "seminar_plan": 0,
            "seminar_total": 30,
            "specialty_id": "ffd7816f-9905-45d2-81f3-3a2157c0db7d",
            "student_count": 29,
            "subgroup_count": 1,
            "subject_text": "ATMF II  blok: \n"
            "1.Korporativ şəbəkə (informasiya) "
            "sistemlərinin təhlükəsizliyi\n"
            "2.Zərərverici proqram vasitələrinin "
            "təhlili (Malware analysis) +",
            "task_id": "b27fed69-e18d-4f33-b183-f46810c13d29",
            "thesis_hours": 0,
            "total_hours": 60,
            "union_count": 1,
        },
        "groups": ["a20f282e-e127-4aa4-89c1-c05d956e6632", "d01bed77-fb68-42af-91b2-1c0f76ded413"],
    },
}

ASSIGNMENTS = [
    {
        "id": "39f0e6b2-f9ed-4e49-b173-d74bf45f8c3e",
        "row_id": "da34a218-839f-4e76-90b9-dd79f6270772",
        "teacher_id": 8302,
        "activity": "seminar",
        "hours": 30,
    },
    {
        "id": "8bc6cc48-cc28-4cac-ac68-99ef74ef847c",
        "row_id": "da34a218-839f-4e76-90b9-dd79f6270772",
        "teacher_id": 8302,
        "activity": "lecture",
        "hours": 30,
    },
    {
        "id": "8d2834a9-fe41-4284-8497-b6a1da898ee1",
        "row_id": "02d98bd9-e176-43a8-a9ed-8f1da41adf07",
        "teacher_id": 8302,
        "activity": "lecture",
        "hours": 30,
    },
    {
        "id": "e44d7112-acd6-4b7a-aced-e1b713859066",
        "row_id": "02d98bd9-e176-43a8-a9ed-8f1da41adf07",
        "teacher_id": 8302,
        "activity": "seminar",
        "hours": 15,
    },
]

OFFERINGS = {
    "670324f8-13e4-4011-854a-0f873e30bf38": {
        "group_id": "d01bed77-fb68-42af-91b2-1c0f76ded413",
        "id": "670324f8-13e4-4011-854a-0f873e30bf38",
        "instructor_id": 8302,
        "is_active": True,
        "lesson_hours": 60,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "subject_id": "b7e2b8b9-6de9-459b-b505-97cee35a9461",
    },
    "07cbecc2-6f7e-4207-adb6-53932d960d57": {
        "group_id": "d01bed77-fb68-42af-91b2-1c0f76ded413",
        "id": "07cbecc2-6f7e-4207-adb6-53932d960d57",
        "instructor_id": 8302,
        "is_active": True,
        "lesson_hours": 60,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "subject_id": "b5cb7489-372b-482b-b0a9-1a377c92ddd1",
    },
    "b362b194-81ae-424e-ba4f-ccc1231226f6": {
        "group_id": "7b6fa0ae-d8d5-49ee-95b1-a8e0d64fb371",
        "id": "b362b194-81ae-424e-ba4f-ccc1231226f6",
        "instructor_id": 8302,
        "is_active": True,
        "lesson_hours": 45,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "subject_id": "11e49bcc-2cea-4092-9af7-e8756fcefcf9",
    },
    "73b15d03-e3c1-4834-a9cc-6d4d2e099554": {
        "group_id": "7b6fa0ae-d8d5-49ee-95b1-a8e0d64fb371",
        "id": "73b15d03-e3c1-4834-a9cc-6d4d2e099554",
        "instructor_id": 8302,
        "is_active": True,
        "lesson_hours": 45,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "subject_id": "5978ae05-0e59-4d65-a072-cd660faf49e9",
    },
    "bad814fd-a7a5-4e24-8722-6e0d33e9ee13": {
        "group_id": "a20f282e-e127-4aa4-89c1-c05d956e6632",
        "id": "bad814fd-a7a5-4e24-8722-6e0d33e9ee13",
        "instructor_id": 8302,
        "is_active": True,
        "lesson_hours": 60,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "subject_id": "b7e2b8b9-6de9-459b-b505-97cee35a9461",
    },
    "c52bc071-f4de-468a-8fd4-56e51d55dde0": {
        "group_id": "a20f282e-e127-4aa4-89c1-c05d956e6632",
        "id": "c52bc071-f4de-468a-8fd4-56e51d55dde0",
        "instructor_id": 8302,
        "is_active": True,
        "lesson_hours": 60,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "subject_id": "b5cb7489-372b-482b-b0a9-1a377c92ddd1",
    },
}

FILLED = [
    "07cbecc2-6f7e-4207-adb6-53932d960d57",
    "73b15d03-e3c1-4834-a9cc-6d4d2e099554",
    "c52bc071-f4de-468a-8fd4-56e51d55dde0",
]

EMPTY = [
    "670324f8-13e4-4011-854a-0f873e30bf38",
    "b362b194-81ae-424e-ba4f-ccc1231226f6",
    "bad814fd-a7a5-4e24-8722-6e0d33e9ee13",
]

GROUPS = {
    "7b6fa0ae-d8d5-49ee-95b1-a8e0d64fb371": {
        "name": "233 İ az",
        "parent_id": "ffd7816f-9905-45d2-81f3-3a2157c0db7d",
        "unit_type": "group",
        "settings": {"degree_level": "bachelor", "education_form": "full_time", "sector": "az"},
        "is_active": True,
    },
    "a20f282e-e127-4aa4-89c1-c05d956e6632": {
        "name": "235 İ-2 az",
        "parent_id": "ffd7816f-9905-45d2-81f3-3a2157c0db7d",
        "unit_type": "group",
        "settings": {
            "degree_level": "bachelor",
            "education_form": "full_time",
            "parent_group": "c1dae2ab-f8bb-4a61-b87b-c84caa46eefc",
            "sector": "az",
        },
        "is_active": True,
    },
    "d01bed77-fb68-42af-91b2-1c0f76ded413": {
        "name": "235 İ-1 az",
        "parent_id": "ffd7816f-9905-45d2-81f3-3a2157c0db7d",
        "unit_type": "group",
        "settings": {
            "degree_level": "bachelor",
            "education_form": "full_time",
            "parent_group": "c1dae2ab-f8bb-4a61-b87b-c84caa46eefc",
            "sector": "az",
        },
        "is_active": True,
    },
}

SUBJECTS = {
    "11e49bcc-2cea-4092-9af7-e8756fcefcf9": {"code": "QKU-2693", "name": "Vo İP sistemlərinin təhlükəsizliyi"},
    "5978ae05-0e59-4d65-a072-cd660faf49e9": {"code": "QKU-2577", "name": "VoİP sistemlərinin təhlükəsizliyi"},
    "b5cb7489-372b-482b-b0a9-1a377c92ddd1": {"code": "QKU-2422", "name": "Zərərverici proqram vasitələrinin təhlili"},
    "b7e2b8b9-6de9-459b-b505-97cee35a9461": {
        "code": "QKU-2690",
        "name": "Zərərverici proqram vasitələrinin təhlili (Malware " "analysis)",
    },
}

BRIDGE = [
    {
        "entity_type": "group_unit",
        "legacy_pk": "846",
        "target_pk": "a20f282e-e127-4aa4-89c1-c05d956e6632",
        "target_model_label": "organizations.orgunit",
        "state": "migrated",
        "source_row_hash": "9c4e3b06280dae3cfddc4841cf271a0bd2da7eba3ec94d7fd6bcb1bca0a08942",
    },
    {
        "entity_type": "worker",
        "legacy_pk": "863",
        "target_pk": "8302",
        "target_model_label": "auth.user",
        "state": "migrated",
        "source_row_hash": "1dcc10c61af700ab4147772bb6f69c904424d14f51930d69a636f0b518c411cd",
    },
    {
        "entity_type": "group_unit",
        "legacy_pk": "599",
        "target_pk": "7b6fa0ae-d8d5-49ee-95b1-a8e0d64fb371",
        "target_model_label": "organizations.orgunit",
        "state": "migrated",
        "source_row_hash": "e9bc4f332d0afa15c054045feb673eba5d89887b2733ee444d80e97b046dc397",
    },
    {
        "entity_type": "group_unit",
        "legacy_pk": "804",
        "target_pk": "d01bed77-fb68-42af-91b2-1c0f76ded413",
        "target_model_label": "organizations.orgunit",
        "state": "migrated",
        "source_row_hash": "d2b42730a8b1c9e75388336280367632a1a27050778ec8cb31c498b271fc00a2",
    },
    {
        "entity_type": "lesson_subject",
        "legacy_pk": "2577",
        "target_pk": "5978ae05-0e59-4d65-a072-cd660faf49e9",
        "target_model_label": "registrar.subject",
        "state": "migrated",
        "source_row_hash": "c5162a94832f32fb640b7d67387e37fa889507e5bc4369b19589afd67a1c2a5b",
    },
    {
        "entity_type": "lesson_subject",
        "legacy_pk": "2422",
        "target_pk": "b5cb7489-372b-482b-b0a9-1a377c92ddd1",
        "target_model_label": "registrar.subject",
        "state": "migrated",
        "source_row_hash": "035010f87e40d785290785bd73155e6880d0192e69e7ce719aa0d75554a85c3c",
    },
    {
        "entity_type": "worker_materialisation",
        "legacy_pk": "863",
        "target_pk": "8302",
        "target_model_label": "auth.user",
        "state": "migrated",
        "source_row_hash": "30c0bdeb4cb8f0337005841308f47658ad14f089ea43af32e77cae7ffce46484",
    },
]

SYLLABI = [
    {
        "offering_id": "07cbecc2-6f7e-4207-adb6-53932d960d57",
        "syllabus_id": "8cacbb10-a777-4653-803c-c4a9f123cb67",
        "version_id": "bbefc0da-76d4-4d86-b546-22e227c20806",
        "canonical_body_sha256": "46e6550ae0daf54c17b7539852743c9cf7e6d0154b75e2ec2fc1c40f10148292",
    },
    {
        "offering_id": "73b15d03-e3c1-4834-a9cc-6d4d2e099554",
        "syllabus_id": "9ccd497e-5314-4d68-b1e8-03a45b1a8766",
        "version_id": "2d32079f-beb1-42bc-8295-4c30bb7fa25d",
        "canonical_body_sha256": "4eeee8d4bb2ce4cf6ed2792c5433ce6b5d78b20980f8ea23d8cc1e901a70c388",
    },
    {
        "offering_id": "c52bc071-f4de-468a-8fd4-56e51d55dde0",
        "syllabus_id": "b8718031-85a9-4c55-b4d1-47096b43b978",
        "version_id": "c2bcaf3d-21e6-45ae-af28-aceedc03f0d9",
        "canonical_body_sha256": "46e6550ae0daf54c17b7539852743c9cf7e6d0154b75e2ec2fc1c40f10148292",
    },
]

MARK_FIELDS = ("id", "organization_id", "lesson_id", "enrollment_id", "status", "score", "entered_by_id")

MARK_COUNT = 550

MARK_SHA256 = "689508a4d18cdd5e29bd0d323e43349786c04764fd5b5e5451729b7cef48e4d1"

ROSTERS = {
    "d01bed77-fb68-42af-91b2-1c0f76ded413": {
        "count": 13,
        "sha256": "865283671d0da6de31d0e54cb0d1918f46c88971568d66868ba6d81cad41b55a",
    },
    "7b6fa0ae-d8d5-49ee-95b1-a8e0d64fb371": {
        "count": 28,
        "sha256": "4505ec3b34a23ade324b33a6f7716aad4da64f0be56a0f0fc9e562fef8bb89b2",
    },
    "a20f282e-e127-4aa4-89c1-c05d956e6632": {
        "count": 15,
        "sha256": "6709b48b1093b6a8aede8ba3c2b695d75a08b972530d079ff03717f64b1116f8",
    },
}

PAIRS = {
    "670324f8-13e4-4011-854a-0f873e30bf38": "07cbecc2-6f7e-4207-adb6-53932d960d57",
    "b362b194-81ae-424e-ba4f-ccc1231226f6": "73b15d03-e3c1-4834-a9cc-6d4d2e099554",
    "bad814fd-a7a5-4e24-8722-6e0d33e9ee13": "c52bc071-f4de-468a-8fd4-56e51d55dde0",
}
SCHEDULE_SOURCE_COUNT = 6

SAFE_GUARDS = frozenset(
    [
        "leyla_active_roster_changed",
        "leyla_active_tenant_superadmin_required",
        "leyla_actor_profile_inactive",
        "leyla_actor_tenant_required",
        "leyla_approved_syllabus_binding_changed",
        "leyla_approved_syllabus_body_changed",
        "leyla_assignment_tenant_changed",
        "leyla_atomic_required",
        "leyla_canonical_cell_count_changed",
        "leyla_canonical_cells_changed",
        "leyla_canonical_course_ambiguous",
        "leyla_canonical_plan_hours_conflict",
        "leyla_canonical_schedule_already_present",
        "leyla_canonical_schedule_copy_changed",
        "leyla_corrected_without_matching_receipt",
        "leyla_current_schedule_conflict",
        "leyla_exact_allocations_changed",
        "leyla_exact_receipt_required",
        "leyla_exact_six_source_slots_required",
        "leyla_existing_canonical_workload_authority",
        "leyla_existing_teacher_permission_required",
        "leyla_fixed_offerings_missing",
        "leyla_fixed_rows_missing",
        "leyla_fresh_baseline_required",
        "leyla_fresh_schedule_review_required",
        "leyla_graph_budget",
        "leyla_group_budget",
        "leyla_group_identity_changed",
        "leyla_named_enrollment_content_requires_review",
        "leyla_named_journal_no_longer_empty",
        "leyla_named_reference_requires_review",
        "leyla_named_syllabus_requires_explicit_review",
        "leyla_offering_identity_changed",
        "leyla_official_chair_changed",
        "leyla_official_row_fields_changed",
        "leyla_official_row_groups_changed",
        "leyla_original_schedule_changed",
        "leyla_original_schedule_restore_failed",
        "leyla_partial_relink_state",
        "leyla_period_identity_changed",
        "leyla_planning_period_locked",
        "leyla_postgresql_required",
        "leyla_preservation_failed",
        "leyla_prior_undo_state_changed",
        "leyla_proposed_schedule_overlap_requires_review",
        "leyla_released_task_changed",
        "leyla_retained_exam_attempt_student_unmatched",
        "leyla_retained_exam_catalog_pair_changed",
        "leyla_retained_exam_course_identity_changed",
        "leyla_retained_exam_exact_links_required",
        "leyla_retained_exam_identity_changed",
        "leyla_retained_exam_pair_students_changed",
        "leyla_retained_exam_reference_changed",
        "leyla_retained_exam_roster_identity_changed",
        "leyla_retained_exam_student_target_ambiguous",
        "leyla_reverse_graph_tenant_changed",
        "leyla_reverse_relation_budget",
        "leyla_reverse_relation_not_supported",
        "leyla_rival_row_budget",
        "leyla_row_budget",
        "leyla_row_subject_changed",
        "leyla_row_write_conflict",
        "leyla_schedule_parking_failed",
        "leyla_schedule_scope_changed",
        "leyla_schedule_undo_conflict",
        "leyla_slot_has_actual_links",
        "leyla_slot_reverse_relation_not_supported",
        "leyla_source_schedule_parked",
        "leyla_source_schedule_shape_changed",
        "leyla_source_schedule_teacher_or_delete_changed",
        "leyla_source_whole_kind_schedule_changed",
        "leyla_subject_identity_changed",
        "leyla_teacher_profile_inactive",
        "leyla_typed_source_bridge_changed",
        "leyla_undo_canonical_schedule_active",
        "leyla_undo_receipt_scope_changed",
        "leyla_undo_schedule_conflict",
        "leyla_undo_state_changed",
    ]
)
