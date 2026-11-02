"""One reviewed source13980/own7456 subject correction; no account or content writes."""

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
TARGET = "73d33235-e875-4100-8ce4-4ae4b42a9a8a"
GROUP = "f41f6e05-c245-43d9-bb5b-09e438163da7"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
OLD_SUBJECT = "e3e63883-9808-4de7-8aad-0b0b6d4f1638"
NEW_SUBJECT = "2721e9cf-16b9-4bee-bf4d-e48834a76778"
TEACHER = 8388
SEPARATE_ACCOUNT = 7730
CURRENT_OWNER = 7730
HANDOVER_ACTOR = 8216
# Authenticated current UI handover export41376827844; preserve exact event IDs.
HANDOVER_IDS = {
    "4d33dcb4-6605-472c-ac9e-793d5461aa25": "48946fe4-89ac-4563-9834-eaabf9418e1e",
    "123c0134-fb83-4337-99b2-13a4f18430b5": "53cd7b4a-4703-4c6e-9f3a-92313337fa77",
    "73d33235-e875-4100-8ce4-4ae4b42a9a8a": "9085d6d2-980f-4f49-8160-9ee2ea322e60",
    "7182d9c2-4bbf-4475-9603-97eb59f4e6e7": "a1fe9492-2ce0-48ac-a352-54f1ffe0a81c",
}
HANDOVER_REASON_SHA256 = "5f09bd74d8cb4e63c819c744d0ebe0506f0a9dc09af7515ba6913ce85c10a99a"
FULL_COUNTS = {"registrar.Enrollment": 55, "registrar.Lesson": 66, "registrar.LessonMark": 616}
SOURCE_SYLLABUS = "e9e60484-61e1-4bed-a608-0c3249ee474c"
SOURCE_VERSION = "337215a5-8b91-4d1a-b2d9-518dea55439b"
SOURCE_BODY_SHA = "7467042c71c304cfcaa4ecd0807b747bd8271fe1b0dc09e01f1ce113cdeee890"
SOURCE = {
    "journal_id": 13980,
    "journal_uniqid": "BABKFcJR8M",
    "legacy_teacher": 949,
    "legacy_group": 884,
    "legacy_syllabus": 7456,
    "legacy_syllabus_subject": 2295,
    "wrong_journal_subject": 1797,
    "linked_sibling_journals": [13979, 13981, 14002],
    "nonblank_language_topics": 120,
    "source_syllabus_hours": 145,
    "journal_hours_unchanged": 150,
    "read_only_source_sha256": "dc452f403b06597128c220dd7779e7d58ece85546199bb735b4d282aff1902f4",
    "source_topics_sha256": "60e44371cf3325b139b1a5bebc2c1cd82fd7088b815a093fe9125a14f1b63572",
}
OFFERINGS = {
    TARGET: GROUP,
    "7182d9c2-4bbf-4475-9603-97eb59f4e6e7": "b47c5858-e255-4cc2-8ca8-1aa95b852553",
    "4d33dcb4-6605-472c-ac9e-793d5461aa25": "e0dc0132-b039-42a7-b7cf-6ec7b529157c",
    "123c0134-fb83-4337-99b2-13a4f18430b5": "42fdc747-b16a-4a9f-bfb9-d70344930817",
}
COUNTS = {"registrar.Enrollment": 15, "registrar.Lesson": 15, "registrar.LessonMark": 106}
WORKER_HASH = "5f71597c04df0ffbfd165b2663c87cbc69ef0f0ab09633ef12086dede3aa84e4"

SAFE_GUARDS = (
    "jale_actor_scope_refused",
    "jale_corrected_without_receipt",
    "jale_course_scope_changed",
    "jale_exact_journal_shares_changed",
    "jale_exact_receipt_required",
    "jale_fixed_course_identity_changed",
    "jale_current_owner_not_eligible",
    "jale_exact_handover_chain_changed",
    "jale_fresh_baseline_required",
    "jale_new_subject_collision",
    "jale_own_source_topics_changed",
    "jale_period_locked",
    "jale_postgresql_required",
    "jale_preservation_failed",
    "jale_prior_undo_changed",
    "jale_protected_counts_changed",
    "jale_readonly_source_anchor_changed",
    "jale_readonly_source_approval_changed",
    "jale_readonly_source_body_changed",
    "jale_reviewed_guard_failed",
    "jale_scoped_superadmin_required",
    "jale_separate_accounts_changed",
    "jale_snapshot_or_rebind_failed",
    "jale_subject_changed",
    "jale_subject_inactive",
    "jale_target_content_requires_separate_review",
    "jale_undo_preservation_changed",
    "jale_undo_state_changed",
    "jale_worker_bridge_changed",
    "jale_worker_bridge_missing",
    "jale_write_conflict",
)
