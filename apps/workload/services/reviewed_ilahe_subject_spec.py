"""Exactly one reviewed Ilahe subject correction; never infer source535 from fallback6117."""

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"

TEACHER = 7776

PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"

TASK = "9becb08c-5b1a-4893-99fa-e8494d6f6335"

CHAIR = "b588bdfe-198c-4cf9-8fe6-293bcdb75e42"

TARGET = "caad2073-173d-48e1-89fd-3c4405c4b87d"

ROW = "d835f4a8-6b30-4776-b998-6480960cadd1"

OLD_SUBJECT = "4befd3c3-40f0-4276-b90d-d450bd5effc1"

NEW_SUBJECT = "a33a790f-2f40-4645-a666-cea5f6fb82f9"

SOURCE_SYLLABUS = "7aa47674-3329-4f20-97b2-3f32595b33fc"

SOURCE_VERSION = "ab0d9ef9-65b7-416b-b72e-dc6a8fb2e40f"

SOURCE_BODY_SHA = "910bb23debdd8dfe70a4bdf1ed4ff3e40dae746abec2aa81d30f27be3ad73c26"

OFFERINGS = {
    "caad2073-173d-48e1-89fd-3c4405c4b87d": {
        "group_id": "10e6920c-a69d-4117-acc9-8b4c8b033962",
        "instructor_id": 7776,
        "is_active": True,
        "lesson_hours": 75,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "subject_id": "4befd3c3-40f0-4276-b90d-d450bd5effc1",
    },
    "f1882bc7-c5d0-43ac-ba3f-7ce8c30f4e76": {
        "group_id": "0967e0e5-9911-432e-a26e-bc88a76772af",
        "instructor_id": 7776,
        "is_active": True,
        "lesson_hours": 75,
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "subject_id": "a33a790f-2f40-4645-a666-cea5f6fb82f9",
    },
}

ROWS = {
    "686469d1-9653-4ad1-8f2c-2e80a79a26ff": {
        "faculty_id": "99936377-8234-439d-a3cb-feacbfb84855",
        "intensive_offering_id": None,
        "organization_id": "526cfa63-4f80-4bba-a7a7-61c8fbb3d918",
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "specialty_id": "2f1383f2-d8db-450b-85fc-35aebd26b606",
        "subject_id": "a33a790f-2f40-4645-a666-cea5f6fb82f9",
        "task_id": "9becb08c-5b1a-4893-99fa-e8494d6f6335",
    },
    "d835f4a8-6b30-4776-b998-6480960cadd1": {
        "faculty_id": "99936377-8234-439d-a3cb-feacbfb84855",
        "intensive_offering_id": None,
        "organization_id": "526cfa63-4f80-4bba-a7a7-61c8fbb3d918",
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "specialty_id": "2f1383f2-d8db-450b-85fc-35aebd26b606",
        "subject_id": "4befd3c3-40f0-4276-b90d-d450bd5effc1",
        "task_id": "9becb08c-5b1a-4893-99fa-e8494d6f6335",
    },
}

SYLLABI = {
    "7aa47674-3329-4f20-97b2-3f32595b33fc": {
        "offering_id": "f1882bc7-c5d0-43ac-ba3f-7ce8c30f4e76",
        "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
        "subject_id": "a33a790f-2f40-4645-a666-cea5f6fb82f9",
        "version_id": "ab0d9ef9-65b7-416b-b72e-dc6a8fb2e40f",
    },
    "d8f359b1-f5d8-45db-87de-49452e703deb": {
        "offering_id": None,
        "period_id": None,
        "subject_id": "a33a790f-2f40-4645-a666-cea5f6fb82f9",
        "version_id": "6823b1e9-9f38-452d-a4ef-ee24f339d0b6",
    },
    "ecdaf318-12c0-4fd5-be42-d70fda756604": {
        "offering_id": None,
        "period_id": None,
        "subject_id": "4befd3c3-40f0-4276-b90d-d450bd5effc1",
        "version_id": "e51cabb7-24cf-4310-a4ae-4ac2e6d4fcd1",
    },
}

GRAPH_PINS = {
    "registrar.AssessmentComponent": {
        "count": 2,
        "sha256": "431ddd46d380dec0e2a17701555c3cec31f16cb87d44f824b3b0cced14dfc92e",
    },
    "registrar.AssessmentScheme": {
        "count": 2,
        "sha256": "aa2e1a933d7d361f0b9de42d4de24a2cddea07c100fa885f208d89e23ca9018a",
    },
    "registrar.CourseOffering": {
        "count": 2,
        "sha256": "e297c6a4a8962ad173aeba14d7d35caf933b3931de7f82b8e87f7328acecf5e7",
    },
    "registrar.Enrollment": {"count": 31, "sha256": "076b76c7cae10f3a90028b23b672b2fed5aa5bf9212a6ac014f9f2a3b5f59f15"},
    "registrar.Lesson": {"count": 35, "sha256": "15fcff5184a89e43010ca40b42533fa50243c636fd43011e3189811b58afc683"},
    "registrar.LessonMark": {
        "count": 542,
        "sha256": "2586484af92a9f815c7af9d74ea96e6a52c264d6db6222f812b036d960d25658",
    },
    "registrar.ScheduleSlot": {
        "count": 6,
        "sha256": "85f21364a531d18992214d491cf0a203e161a232ea9878f4f600252e3f72e48d",
    },
    "registrar.SubgroupPlacementEvent": {
        "count": 1,
        "sha256": "631e8151c775e95e0c92d6d3a9e866aa22ab424d5ae2f90c92b8c675505f3c17",
    },
    "syllabus.Syllabus": {"count": 3, "sha256": "8a3e8b08814bfe86dbfe2c8553aeaa39d5143bb9e6f8e85529c3b5a59b27f927"},
    "syllabus.SyllabusSection": {
        "count": 30,
        "sha256": "40cf4d301297ba3d79d9ed56ec2171094b5728034d7689863731617825c67519",
    },
    "syllabus.SyllabusVersion": {
        "count": 3,
        "sha256": "a174c417080b3fe0dfa434e20d985700ddce9da2d42db128391180d1219dcb48",
    },
    "workload.TeacherAssignment": {
        "count": 2,
        "sha256": "8e917f451e3875641c7d5aa354ee4662673117d7a4422d6b08641eb702b386ba",
    },
    "workload.TeachingTaskRow": {
        "count": 2,
        "sha256": "aa8ee18b5315c12e6d23cf32004d8d5ffa3d4733af7ca565b0f4770ee3dfd26c",
    },
    "workload.TeachingTaskRow_groups": {
        "count": 2,
        "sha256": "99ea4b1016924871920a086ee247e74c750a1b9bb596dae95e89fa396493a1b1",
    },
}

BRIDGE = [
    {
        "count": 1,
        "entity_type": "worker",
        "legacy_pk": "209",
        "sha256": "ded1743713139253ed0ef2f79a8aea2645ab8f03b87805645fd59b833b15ffe4",
    },
    {
        "count": 1,
        "entity_type": "worker_materialisation",
        "legacy_pk": "209",
        "sha256": "b180831c707a497384c37f7b1a26aab21d79295909036a520f6dbac3d4223825",
    },
    {
        "count": 0,
        "entity_type": "group_unit",
        "legacy_pk": "934",
        "sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    },
    {
        "count": 0,
        "entity_type": "group_unit",
        "legacy_pk": "935",
        "sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    },
    {
        "count": 1,
        "entity_type": "lesson_subject",
        "legacy_pk": "535",
        "sha256": "4bb9fdd4f9d24605333e70759b798d0f63cff264b7bcaa4b1f9ef4c283623ce7",
    },
    {
        "count": 1,
        "entity_type": "lesson_subject",
        "legacy_pk": "536",
        "sha256": "1a49ecb36a2eeb25c962ea2fd82ea7393735d020f77b6216023286e0ceee9a7c",
    },
    {
        "count": 0,
        "entity_type": "course_offering",
        "legacy_pk": "rWlLLOIQn0:934",
        "sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    },
    {
        "count": 0,
        "entity_type": "course_offering",
        "legacy_pk": "ujYj5scjwh:935",
        "sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    },
    {
        "count": 0,
        "entity_type": "syllabus_document",
        "legacy_pk": "8668",
        "sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    },
    {
        "count": 0,
        "entity_type": "syllabus_document",
        "legacy_pk": "6117",
        "sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    },
]

SOURCE = {
    "direct8668_packet_sha256": "e321f62ba22982bdfd505f8a4e018b0708330b528e076e663261da9fd37e2719",
    "fresh_snapshot_sha256": "e08ba889b03413d4594778b2a2786a6898ddea4b125e1491b748fa88200424c1",
    "journal15047": {
        "direct_syllabus": 8668,
        "reviewed_actual_subject": 535,
        "source_group": 934,
        "source_teacher": 209,
        "subject_id_raw": 536,
        "uniqid": "rWlLLOIQn0",
    },
    "journal15051": {
        "direct_syllabus": 8668,
        "source_group": 935,
        "source_teacher": 209,
        "subject_id_raw": 535,
        "uniqid": "ujYj5scjwh",
    },
    "no_new_content_or_approval": True,
    "source70_sha256": "1a1b24629be432e4e81ca19ebfa357353cd2856d031aa83ea2dd7773b5a0ee88",
}

SAFE_GUARDS = [
    "ilahe_active_tenant_required",
    "ilahe_actor_inactive",
    "ilahe_actor_tenant_required",
    "ilahe_corrected_without_receipt",
    "ilahe_course_identity_changed",
    "ilahe_effective_syllabus_changed",
    "ilahe_exact_approved_8668_required",
    "ilahe_exact_receipt_required",
    "ilahe_existing_approved_share_refused",
    "ilahe_existing_teacher_permission_required",
    "ilahe_fixed_courses_missing",
    "ilahe_fresh_baseline_required",
    "ilahe_new_course_cohort_conflict",
    "ilahe_new_reverse_relation_requires_review",
    "ilahe_new_subject_student_collision",
    "ilahe_new_workload_authority_conflict",
    "ilahe_offering_write_conflict",
    "ilahe_partial_subject_state",
    "ilahe_period_locked_or_inactive",
    "ilahe_pinned_protected_content_changed",
    "ilahe_postgresql_required",
    "ilahe_preservation_failed",
    "ilahe_prior_undo_state_changed",
    "ilahe_protected_row_count_changed",
    "ilahe_released_task_changed",
    "ilahe_roster_history_changed",
    "ilahe_scoped_superadmin_required",
    "ilahe_share_undo_changed",
    "ilahe_share_undo_failed",
    "ilahe_source_8668_body_changed",
    "ilahe_source_bridge_changed",
    "ilahe_subject_changed",
    "ilahe_subject_inactive",
    "ilahe_teacher_inactive",
    "ilahe_undo_preservation_changed",
    "ilahe_undo_state_changed",
    "ilahe_unreviewed_syllabus_or_human_draft",
    "ilahe_unreviewed_syllabus_share",
    "ilahe_workload_identity_changed",
    "ilahe_workload_write_conflict",
]
