"""Only Nigar534DBI and Aruz510/5E source-bound load rows; credits remain held."""

import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _load(name, expected):
    raw = (BASE / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("two_catalog_fixed_source_packet_changed")
    return json.loads(raw)


PINS = _load("reviewed_two_catalog_pins.json", "c658fdbdb82b61db8638e7ddd252fad6579ba5c20e33b7ed26af9e034f0cf5a3")
SCHEMA = _load(
    "reviewed_two_catalog_schema_pins.json", "bccf59512fbec92d1793e1c2edf69f5be3169da788cb242b3c7c78f7aef82f78"
)
ORG = PINS["organization_id"]
PERIOD = PINS["period_id"]
YEAR = PINS["academic_year"]
CASES = PINS["cases"]

SAFE_GUARDS = frozenset(
    [
        "leyla_graph_budget",
        "leyla_reverse_graph_tenant_changed",
        "leyla_reverse_relation_budget",
        "leyla_reverse_relation_not_supported",
        "leyla_row_budget",
        "two_catalog_active_tenant_required",
        "two_catalog_actor_profile_inactive",
        "two_catalog_actor_tenant_required",
        "two_catalog_ambiguous_course",
        "two_catalog_approved_own_source_required",
        "two_catalog_approved_source_body_changed",
        "two_catalog_corrected_without_exact_receipt",
        "two_catalog_course_identity_changed",
        "two_catalog_donor_binding_changed",
        "two_catalog_donor_identity_changed",
        "two_catalog_exact_allocations_changed",
        "two_catalog_exact_receipt_required",
        "two_catalog_exact_roster_changed",
        "two_catalog_exact_undo_restore_failed",
        "two_catalog_existing_canonical_workload_authority",
        "two_catalog_fixed_courses_missing",
        "two_catalog_fixed_source_packet_changed",
        "two_catalog_fresh_baseline_required",
        "two_catalog_fixed_scope_required",
        "two_catalog_full_graph_preservation_failed",
        "two_catalog_group_budget",
        "two_catalog_group_identity_changed",
        "two_catalog_named_journal_not_empty",
        "two_catalog_official_chair_changed",
        "two_catalog_partial_relink_state",
        "two_catalog_period_locked_or_changed",
        "two_catalog_postgresql_required",
        "two_catalog_prior_undo_state_changed",
        "two_catalog_released_task_changed",
        "two_catalog_row_fields_changed",
        "two_catalog_row_groups_changed",
        "two_catalog_row_write_conflict",
        "two_catalog_schedule_budget",
        "two_catalog_source_content_fingerprint_changed",
        "two_catalog_subject_identity_changed",
        "two_catalog_target_schedule_conflict",
        "two_catalog_teacher_permission_changed",
        "two_catalog_tenant_superadmin_required",
        "two_catalog_typed_source_bridge_changed",
        "two_catalog_undo_receipt_scope_changed",
        "two_catalog_undo_state_changed",
        "two_catalog_unreviewed_relation_schema",
        "two_catalog_unreviewed_workload_graph",
    ]
)

SAFE_GUARDS = SAFE_GUARDS | frozenset(
    [
        "catalog_chain_exact_receipt_required",
        "catalog_chain_fixed_disjoint_contracts_required",
        "catalog_chain_fresh_baseline_required",
        "catalog_chain_native_apply_required",
        "catalog_chain_native_repeat_required",
        "catalog_chain_partial_existing_state",
        "catalog_chain_protected_graph_changed",
        "catalog_chain_reviewed_guard_failed",
        "catalog_chain_snapshot_failed",
    ]
)
