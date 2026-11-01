"""Exact English-sector two-group diagnostic course alias, never a body repair."""

from . import reviewed_two_catalog_spec as common

PINS = common._load(
    "reviewed_aida_catalog_pins.json", "3a81b7f9de5ec6187d10f744c0d5994f3ae58213a8a3a520de50bdc68fe02c62"
)
SCHEMA = common.SCHEMA
ORG = PINS["organization_id"]
PERIOD = PINS["period_id"]
YEAR = PINS["academic_year"]
CASE = PINS["case"]
ROW = PINS["row_id"]
KING = PINS["king"]
RESOURCE = "workload.reviewed_aida_catalog_v1"

AIDA_SAFE_GUARDS = frozenset(
    [
        "aida_all_three_academic_fingerprints_changed",
        "aida_corrected_without_receipt",
        "aida_effective_student_credits_changed",
        "aida_exact_known_43_of_45_source_required",
        "aida_exact_official_allocations_changed",
        "aida_exact_receipt_required",
        "aida_exact_source_roster_changed",
        "aida_exact_source_share_undo_failed",
        "aida_exact_subject_write_conflict",
        "aida_exact_undo_restore_failed",
        "aida_existing_approved_source_share_refused",
        "aida_existing_canonical_king_course_requires_review",
        "aida_existing_own_source_share_changed",
        "aida_extra_student_identity_changed",
        "aida_extra_student_provenance_changed",
        "aida_fresh_baseline_required",
        "aida_full_graph_preservation_failed",
        "aida_named_journal_new_real_activity",
        "aida_new_king_syllabus_requires_explicit_review",
        "aida_official_row_budget_or_credit_changed",
        "aida_original_row_or_king_course_missing",
        "aida_partial_alias_state",
        "aida_period_locked_or_changed",
        "aida_postgresql_required",
        "aida_prior_undo_state_changed",
        "aida_released_official_task_changed",
        "aida_reviewed_guard_failed",
        "aida_shared_official_group_scope_changed",
        "aida_snapshot_failed",
        "aida_tenant_superadmin_required",
        "aida_three_retained_source_students_changed",
        "aida_undo_scope_changed",
        "aida_undo_state_changed",
        "aida_unreviewed_duplicate_workload_row",
        "aida_unreviewed_relation_schema",
        "aida_unreviewed_row_reference",
    ]
)
SAFE_GUARDS = common.SAFE_GUARDS | AIDA_SAFE_GUARDS
