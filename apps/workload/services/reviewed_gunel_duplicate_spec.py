"""One exact social-work duplicate, with original assignments retained in receipt."""

from . import reviewed_two_catalog_spec as common

SCHEMA = common.SCHEMA

PINS = common._load(
    "reviewed_gunel_duplicate_pins.json", "89adbf38e314e8f3f475257b40ac1bb6996e07390fc450f6c3ca51045f125c88"
)
ORG = PINS["organization_id"]
PERIOD = PINS["period_id"]
YEAR = PINS["academic_year"]
CASE = PINS["case"]
KEEPER = PINS["keeper"]
DUPLICATE = PINS["duplicate"]
RESOURCE = "workload.reviewed_gunel_duplicate_v1"

GUNEL_SAFE_GUARDS = frozenset(
    [
        "gunel_academic_fingerprint_changed",
        "gunel_assignment_uuid_reused",
        "gunel_corrected_without_receipt",
        "gunel_exact_assignments_changed",
        "gunel_exact_receipt_required",
        "gunel_exact_rows_required",
        "gunel_exact_undo_restore_failed",
        "gunel_fixed_shared_tasks_missing",
        "gunel_fresh_baseline_required",
        "gunel_full_graph_preservation_failed",
        "gunel_partial_or_unreviewed_row_state",
        "gunel_period_locked_or_changed",
        "gunel_postgresql_required",
        "gunel_prior_undo_state_changed",
        "gunel_redundant_named_journal_has_activity",
        "gunel_released_shared_task_changed",
        "gunel_reviewed_guard_failed",
        "gunel_row_groups_changed",
        "gunel_row_write_conflict",
        "gunel_snapshot_failed",
        "gunel_source_row_invariants_changed",
        "gunel_tenant_superadmin_required",
        "gunel_undo_scope_changed",
        "gunel_undo_state_changed",
        "gunel_unreviewed_relation_schema",
        "gunel_unreviewed_rival_row",
        "gunel_unreviewed_row_reference",
    ]
)

SAFE_GUARDS = common.SAFE_GUARDS | GUNEL_SAFE_GUARDS
