"""Closed diagnostics for pinned read-only exports; never exception values."""

import re
import traceback
from pathlib import Path

STAGES = {
    "source28_history",
    "source28_apply",
    "source28_undo",
    "input",
    "capture",
    "encrypt",
    "verify_head",
    "prepare",
    "remote_setup",
    "source_capture",
    "copy_cipher",
    "verify_cipher",
    "write_manifest",
    "publish_output",
}
CLASSES = {
    "contenterror",
    "evidencelimit",
    "restoreerror",
    "exception",
    "valueerror",
    "typeerror",
    "keyerror",
    "attributeerror",
    "overflowerror",
    "programmingerror",
    "operationalerror",
    "databaseerror",
    "integrityerror",
    "dataerror",
    "interfaceerror",
    "internalerror",
    "permissiondenied",
    "validationerror",
    "oserror",
    "fileexistserror",
    "filenotfounderror",
    "snapshoterror",
    "timeouterror",
    "timeoutexpired",
    "invalidtag",
    "runtimeerror",
    "undefinedcolumn",
    "undefinedtable",
    "undefinedfunction",
    "insufficientprivilege",
    "readonlysqltransaction",
    "querycanceled",
    "numericvalueoutofrange",
    "invalidtextrepresentation",
}
GUARDS = {
    "unclassified",
    "four_cell_audit_shape_budget_exceeded",
    "four_cell_history_row_budget_exceeded",
    "four_cell_readonly_pg_required",
    "four_cell_atomic_pg_required",
    "four_cell_audit_byte_budget_exceeded",
    "fixed_workload_receipt_projection_budget",
    "fixed_workload_receipt_row_changed",
    "fixed_workload_receipt_field_hash_changed",
    "fixed_workload_receipt_semantics_unverified",
    "fixed_workload_receipt_protection_mismatch",
    "fixed_workload_receipt_source_baseline_invalid",
    "fixed_workload_receipt_scope_changed",
    "four_cell_change_budget_exceeded",
    "fresh_postgresql_transaction_required",
    "active_fixed_tenant_required",
    "active_fixed_tenant_superuser_required",
    "four_cell_history_output_budget_exceeded",
    "syllabus_query_or_time_budget_exceeded",
    "syllabus_row_budget_exceeded",
    "workflow_run_required",
    "fixed_public_key_required",
    "fixed_history_summary_required",
    "history_ciphertext_invalid",
    "history_ciphertext_sha_changed",
    "followup_transport_failed",
    "followup_executable_missing",
    "release_fixed_scope_required",
    "release_token_required",
    "release_private_target_required",
    "release_redirect_refused",
    "release_http_refused",
    "release_response_budget",
    "release_transport_timeout",
    "release_access_denied",
    "release_asset_missing",
    "release_transport_failed",
    "release_metadata_invalid",
    "release_ciphertext_changed",
    "followup_command_refused",
    "pinned_head_required",
    "deployed_head_changed",
    "fixed_history_actor_required",
    "source_capture_failed",
    "source_diagnostic_output_budget",
}
GUARDS |= {
    "readonly_transaction_required",
    "syllabus_version_enum_unknown",
    "syllabus_closure_tenant_mismatch",
    "syllabus_lineage_reference_missing",
    "syllabus_lineage_budget_exceeded",
    "syllabus_version_owner_mismatch",
    "syllabus_lineage_cycle",
    "syllabus_lineage_depth_exceeded",
    "syllabus_root_scope_invalid",
    "syllabus_root_period_mismatch",
    "syllabus_candidate_budget_exceeded",
    "syllabus_source_body_byte_budget_exceeded",
    "syllabus_body_shape_budget_exceeded",
    "syllabus_topic_budget_exceeded",
    "syllabus_total_row_budget_exceeded",
    "syllabus_output_byte_budget_exceeded",
    "syllabus_envelope_byte_budget_exceeded",
    "syllabus_capture_failed",
    "syllabus_transport_failed",
    "syllabus_ciphertext_invalid",
    "syllabus_summary_invalid",
}
GUARDS |= {
    "reviewed_source28_present_only_must_not_change_existing_qb_counter",
    "reviewed_source28_unchanged_created_rows_required",
    "reviewed_source28_exact_private_source_and_single_target_required",
    "reviewed_source28_only_normal_seminar_present",
    "reviewed_source28_additional_source_claim_requires_review",
    "reviewed_source28_ambiguous_original_recovery_receipt",
    "reviewed_source28_unlocatable_deletion_requires_review",
    "reviewed_source28_existing_content_without_original_recovery_receipt",
    "reviewed_source28_unlocatable_lesson_deletion_requires_review",
    "reviewed_source28_closed_or_locked_target",
    "reviewed_source28_batch_invalid",
    "reviewed_source28_existing_lesson_changed",
    "reviewed_source28_course_ledger_conflict",
    "reviewed_source28_original_recovery_receipt_bindings_changed",
    "reviewed_source28_single_original_receipt_required",
    "reviewed_source28_source_ledger_state_changed",
    "reviewed_source28_tenant_actor_required",
    "reviewed_source28_all_typed_identity_ledgers_required",
    "reviewed_source28_undo_baseline_changed",
    "reviewed_source28_contrary_history_requires_review",
    "reviewed_source28_reviewed_history_fixed_scope_required",
    "reviewed_source28_reviewed_history_anchor_missing",
    "reviewed_source28_reviewed_history_anchor_changed",
    "reviewed_source28_content_changed_after_recovery",
    "reviewed_source28_undo_created_row_has_additional_references",
    "reviewed_source28_undo_repeat_drift",
    "reviewed_source28_undo_original_state_not_restored",
    "reviewed_source28_fresh_history_or_allocation_unavailable",
    "reviewed_source28_typed_source_ledger_conflict",
    "reviewed_source28_canonical_copy_or_current_value_requires_review",
    "reviewed_source28_actual_calendar_seminar_required",
    "reviewed_source28_undo_fresh_baseline_required",
    "reviewed_source28_canonical_course_budget",
    "reviewed_source28_original_source28_receipt_changed",
    "reviewed_source28_undo_protected_content_changed",
    "compiled_history_scope_required",
    "reviewed_source28_history_changed_during_write",
    "reviewed_source28_exact_active_enrollment_changed",
    "source28_exact_current_kind_owner_allocation_changed",
    "reviewed_source28_only_28_present_source_points",
    "reviewed_source28_single_lesson_only",
    "reviewed_source28_current_value_conflict",
    "reviewed_source28_fixed_source28_package_required",
    "reviewed_source28_active_tenant_profiles_required",
    "reviewed_source28_exact_calendar_rows_required",
    "reviewed_source28_exact_present_mark_required",
    "reviewed_source28_current_home_group_requires_review",
    "reviewed_source28_all_28_cells_must_resolve",
    "reviewed_source28_correction_hygiene_or_sourceclaim_requires_review",
    "reviewed_source28_existing_canonical_slot_requires_review",
    "reviewed_source28_atomic_required",
    "reviewed_source28_unresolved_course_audit_requires_review",
    "reviewed_source28_enrollment_ledger_conflict",
}

GUARDS |= {
    "active_fixed_tenant_superadmin_required",
    "complete_source_tables_required",
    "current_dossier_metadata_changed",
    "current_dossier_scope_changed",
    "current_period_or_contact_hours_changed",
    "current_pointers_changed",
    "current_post_restore_graph_changed",
    "current_review_history_changed",
    "current_share_or_reuse_changed",
    "current_versions_changed",
    "exact_source_identity_mapping_changed",
    "fixed_cases_required",
    "fixed_loaded_cases_required",
    "fixed_source_packet_scope",
    "fixed_scope_changed",
    "fixed_state_budget_exceeded",
    "fresh_baseline_required",
    "human_draft_changed",
    "human_draft_not_empty",
    "human_draft_sections_changed",
    "official_source_workload_changed",
    "pinned_own_source_changed",
    "pinned_source_packet_changed",
    "previous_undo_requires_review",
    "protected_journal_content_changed",
    "restored_source_status_changed",
    "restore_database_conflict",
    "reviewed_apply_receipt_missing",
    "reviewed_receipt_source_scope_changed",
    "source_assignment_geometry_changed",
    "source_author_inactive_or_deleted",
    "source_conversion_or_plan_changed",
    "source_group_sector_degree_changed",
    "source_file_unavailable",
    "source_import_content_mismatch",
    "source_packet_shape",
    "source_partial_group_geometry_unreviewed",
    "source_topic_or_selfwork_scope",
    "unexpected_cohort_context",
}

# Exact fixed Source58 reader guards; exception values remain forbidden.
GUARDS |= {
    "history_numeric_source_points_required",
    "history_reference_byte_budget",
    "source58_active_scoped_superadmin_required",
    "source58_auth_metadata_budget",
    "source58_chunk_audit_count_budget",
    "source58_chunk_identity_invalid",
    "source58_chunk_incomplete_inventory",
    "source58_chunk_raw_changed",
    "source58_chunk_total_budget",
    "source58_credit_enrollment_closure_depth",
    "source58_cross_tenant_reference",
    "source58_dangling_reference",
    "source58_diagnostic_inventory_budget",
    "source58_export_byte_budget",
    "source58_fixed_courses_missing",
    "source58_fixed_enrollments_missing",
    "source58_mark_forward_reference_missing",
    "source58_query_or_time_budget",
    "source58_readonly_postgresql_required",
    "source58_readonly_tenant_context_required",
    "source58_reference_cycle",
    "source58_reverse_budget",
    "source58_reverse_depth_budget",
    "source58_row_budget",
    "source58_select_only_required",
    "source58_time_budget",
    "source58_total_row_or_byte_budget",
}

PREFIXES = {
    "four_cell_history_diagnostic",
    "syllabus_content_diagnostic",
    "syllabus_lineage_diagnostic",
    "syllabus_forensic_diagnostic",
    "reviewed_source28_diagnostic",
    "english_level_diagnostic",
    "blank_draft_syllabus_diagnostic",
}

FIELDS = ("stage", "class", "cause", "module", "function", "line", "guard")


def describe(exc, stage):
    """No str/repr(exc), locals, SQL, paths, actor names or arbitrary exception args."""

    def name(value):
        token = type(value).__name__.lower()
        return token if token in CLASSES else "exception"

    code = None
    current, seen = exc, set()
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        value = current.args[0] if len(current.args) == 1 and isinstance(current.args[0], str) else None
        if value in GUARDS:
            code = value  # Prefer the deepest known cause over an outer generic guard.
        current = current.__cause__
    fields = {
        "stage": stage if stage in STAGES else "input",
        "class": name(exc),
        "cause": name(exc.__cause__) if exc.__cause__ is not None else "exception",
        "module": "unknown",
        "function": "unknown",
        "line": 0,
        "guard": code if code in GUARDS else "unclassified",
    }
    for frame in reversed(traceback.extract_tb(exc.__traceback__)):
        if not any(
            part in frame.filename
            for part in ("/apps/workload/", "/apps/syllabus/", "/apps/legacy_import/", "/core/", "/scripts/ops/")
        ):
            continue
        module = Path(frame.filename).stem
        if re.fullmatch(r"[a-z_][a-z0-9_]{0,63}", module) and re.fullmatch(r"[a-z_][a-z0-9_]{0,63}", frame.name):
            fields.update(module=module, function=frame.name, line=frame.lineno)
            break
    return fields


def render(fields):
    if (
        set(fields) != set(FIELDS)
        or fields["stage"] not in STAGES
        or fields["class"] not in CLASSES
        or fields["cause"] not in CLASSES
        or fields["guard"] not in GUARDS
        or type(fields["line"]) is not int
        or not 0 <= fields["line"] <= 999999
        or any(not re.fullmatch(r"[a-z_][a-z0-9_]{0,63}", fields[k]) for k in ("module", "function"))
    ):
        raise ValueError("invalid_fixed_diagnostic")
    return " ".join(f"{key}={fields[key]}" for key in FIELDS)


def parse(output, *, prefix="four_cell_history_diagnostic"):
    if prefix not in PREFIXES:
        return None
    found = []
    for line in output.splitlines():
        if not line.startswith(prefix + ": "):
            continue
        pairs = re.findall(r"([a-z]+)=([a-z0-9_]+)", line)
        fields = dict(pairs)
        if len(pairs) != len(FIELDS) or len(fields) != len(FIELDS):
            continue
        try:
            fields["line"] = int(fields["line"])
            if line != prefix + ": " + render(fields):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        found.append(fields)
    if len(found) == 1:
        return found[0]
    return None
