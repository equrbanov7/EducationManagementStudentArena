"""Real PG: fixed-byte workload receipts never become grade intent or bypass unknown audit."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.db import connection, transaction
from django.test import override_settings

from apps.audit.models import AuditLog
from apps.workload.services import recovery_audit_diagnostic as diagnostic
from apps.workload.services.scoped_snapshot import workload_audit_receipt_spec as spec
from apps.workload.services.scoped_snapshot import workload_audit_receipts as thin
from apps.workload.services.scoped_snapshot.four_cell_history import annotated
from apps.workload.tests.test_four_cell_history_pg import FourCellHistoryPostgresTests as Base
from core.rls import apply_rls_request_context


class FixedWorkloadReceiptTests(Base):
    def setUp(self):
        super().setUp()
        self.pins = patch.dict(spec.PINS, {}, clear=True)
        field_pins = patch.dict(spec.FIELD_PINS, {}, clear=True)
        field_pins.start()
        self.addCleanup(field_pins.stop)
        self.pins.start()
        self.addCleanup(self.pins.stop)

    def receipt(self, family="reviewed", *, size=1100000, mutate=None):
        selection = "b" * 64
        before = {key: [] for key in spec.BEFORE[family]}
        before["selection"] = selection
        before["rows"] = [
            {"offering_id": str(self.offering.pk), "private_snapshot_note": "PRIVATE_NO_FETCH_" + "x" * size}
        ]
        before["history"] = {
            key: [] for key in ("LoadObjection", "TaskFacultySlice", "TaskRowReview", "WorkloadAmendment")
        }
        style = "md5" if family == "reviewed" else "sha256"
        academic = {key: {"count": 0, style: "a" * (32 if style == "md5" else 64)} for key in spec.ACADEMIC}
        if family == "reviewed":
            before["academic"] = academic
            before["extensions"] = {}
            before["electives"] = {}
            values = dict(
                selection_sha=selection,
                manifest_sha256="c" * 64,
                kind="apply",
                before_baseline="d" * 64,
                after_baseline="e" * 64,
                before=before,
                details={key: [] for key in spec.DETAILS},
                protected_academic={key: v for key, v in academic.items() if key != "offering"},
            )
            batch = "source-20261030-000000-abcdef01"
        else:
            row = str(uuid4())
            values = dict(
                kind="apply",
                source_manifest_sha256="c" * 64,
                selection_sha256=selection,
                selected_rows=[row],
                before_baseline="d" * 64,
                after_baseline="e" * 64,
                before=before,
                created_assignment_ids={row: []},
                academic_before_after=academic,
            )
            batch = "owneract-20261030-000000-abcd"
        kwargs = dict(
            organization=self.org,
            user=self.actor,
            action="update",
            resource_type=spec.FAMILIES[family][0],
            resource_id=batch,
            reason=spec.FAMILIES[family][1],
            new_values=values,
        )
        if mutate:
            mutate(kwargs)
        obj = AuditLog.objects.create(**kwargs)
        sha = annotated(AuditLog.objects.filter(pk=obj.pk)).values_list("_raw_sha", flat=True).get()
        spec.PINS[str(obj.pk)] = (family, sha)
        row = thin.preview(annotated(AuditLog.objects.filter(pk=obj.pk)))[0]
        proof = row["_thin"]
        spec.FIELD_PINS[str(obj.pk)] = {
            key: proof[name]
            for key, name in (
                ("old_values_sha256", "old_values_sql_sha256"),
                ("new_values_sha256", "new_values_sql_sha256"),
                ("changes_sha256", "changes_sql_sha256"),
                ("resource_id_sha256", "resource_id_sql_sha256"),
            )
        }
        spec.FIELD_PINS[str(obj.pk)]["source_raw_bytes"] = row["_raw_bytes"]
        return obj

    def test_large_reviewed_and_owner_use_sql_only_metadata_preserve_all_bytes_both_rls(self):
        a, b = self.receipt(), self.receipt("owner")
        before = self.fingerprint()
        selected_json = []

        def inspect(execute, sql, params, many, context):
            if 'FROM "audit_auditlog"' in sql and '"new_values"' in sql:
                selected_json.append(sql)
            return execute(sql, params, many, context)

        for mode in (False, True):
            with connection.execute_wrapper(inspect):
                result = self.read(mode)
            rows = result["four_cell_history_audits"]
            projected = [row for row in rows if row.get("projection") == "verified_workload_receipt"]
            self.assertEqual({row["id"] for row in projected}, {str(a.pk), str(b.pk)})
            for row in projected:
                self.assertEqual(row["case_ids"], [])
                self.assertFalse(row["unresolved_scope_row"])
                self.assertFalse(row["contrary_clear_evidence"])
                self.assertEqual(row["json_hash_policy"], spec.JSON_SQL_POLICY)
            # Only the ordinary small grade audit is ever selected as a raw body.
            raw_selects = [sql for sql in selected_json if ', "audit_auditlog"."new_values"' in sql]
            self.assertTrue(all("NOT (" in sql for sql in raw_selects))
            self.assertNotIn("PRIVATE_NO_FETCH", json.dumps(result, default=str))
            self.assertTrue(result["four_cell_history_changes"][0]["clear_evidence"])
            self.assertEqual(result["four_cell_history_scope"][0]["verified_workload_receipts"], 2)
        self.assertEqual(before, self.fingerprint())

    def test_authenticated_october_receipt_schema_versions_preserve_all_bytes(self):
        # Actual encrypted diagnostic 41326871426: all three reviewed receipts
        # omit later provenance; the oldest also predates before.electives.
        for electives in (False, True):
            for choices in (False, True):

                def historical(kwargs, electives=electives, choices=choices):
                    value = kwargs["new_values"]
                    value["details"].pop("detached_objection_provenance")
                    if not electives:
                        value["before"].pop("electives")
                    if choices:
                        value["details"]["created_elective_choice_ids"] = []

                with self.subTest(electives=electives, choices=choices):
                    obj = self.receipt(size=128, mutate=historical)
                    self.enterContext(patch.object(spec, "WITHOUT_PROVENANCE", (*spec.WITHOUT_PROVENANCE, str(obj.pk))))
                    if not electives:
                        self.enterContext(
                            patch.object(spec, "WITHOUT_ELECTIVES", (*spec.WITHOUT_ELECTIVES, str(obj.pk)))
                        )
                    before = self.fingerprint()
                    for bypass in (False, True):
                        rows = self.read(bypass)["four_cell_history_audits"]
                        self.assertTrue(
                            any(r["id"] == str(obj.pk) and r.get("receipt_semantics_validated") for r in rows)
                        )
                    self.assertEqual(before, self.fingerprint())

    def test_historical_schema_does_not_accept_other_omissions_or_bad_optional_arrays(self):
        mutations = [
            lambda v: v["before"].pop("electives"),
            lambda v: v["details"].pop("detached_objection_provenance"),
            lambda v: v["before"].pop("extensions"),
            lambda v: v["details"].pop("created_row_ids"),
            lambda v: v["details"].update(unknown_intent=[]),
            lambda v: v["details"].update(created_elective_choice_ids=["private-not-uuid"]),
            lambda v: v["details"].update(detached_objection_provenance={}),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                obj = self.receipt(size=128, mutate=lambda k, mutate=mutate: mutate(k["new_values"]))
                row = thin.preview(annotated(AuditLog.objects.filter(pk=obj.pk)))[0]
                with self.assertRaisesRegex(ValueError, "receipt_semantics_unverified"):
                    thin.validate(row)

    def test_changed_hash_and_forged_semantics_are_never_accepted(self):
        obj = self.receipt()
        with (
            patch.dict(spec.PINS, {str(obj.pk): ("reviewed", "0" * 64)}),
            self.assertRaisesRegex(ValueError, "receipt_row_changed"),
        ):
            self.read()
        changes = [
            lambda k: k.update(action="delete"),
            lambda k: k.update(resource_type="registrar.grade.full-edit"),
            lambda k: k.update(reason="private_reason"),
            lambda k: k.update(changes=[{"new": "—"}]),
            lambda k: k["new_values"].update(kind="undo"),
            lambda k: k["new_values"].update(manifest_sha256="PRIVATE"),
            lambda k: k["new_values"].update(unknown_grade_intent=True),
            lambda k: k["new_values"]["before"].update(rows="not-array"),
            lambda k: k["new_values"]["protected_academic"].update(mark={"count": True, "md5": "a" * 32}),
            lambda k: k["new_values"]["protected_academic"].pop("mark"),
        ]
        for mutate in changes:
            with self.subTest(mutate=changes.index(mutate)):
                obj = self.receipt(mutate=mutate)
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    apply_rls_request_context(user_id=self.actor.pk, org_id=self.org.pk, bypass=False, local=True)
                    projected = thin.preview(annotated(AuditLog.objects.filter(organization=self.org, pk=obj.pk)))
                    with self.assertRaisesRegex(ValueError, "receipt_(semantics|source_baseline)"):
                        thin.validate(projected[0])

    def test_unknown_oversized_and_grade_resource_never_gain_projection(self):
        self.receipt()
        spec.PINS.clear()
        with self.assertRaisesRegex(ValueError, "byte_budget"):
            self.read()
        self.receipt(mutate=lambda k: k.update(resource_type="workload.repeated_sections_repair"))
        spec.PINS.clear()
        with self.assertRaisesRegex(ValueError, "byte_budget"):
            self.read()

    def test_new_grade_clear_after_earlier_read_is_still_collected(self):
        self.receipt()
        self.read()
        obj = AuditLog.objects.create(
            organization=self.org,
            user=self.actor,
            action="update",
            resource_type="registrar.grade.mark",
            resource_id=str(self.offering.pk),
            changes=[
                {"enrollment_id": str(self.enrollment.pk), "lesson_id": str(self.lesson.pk), "old": "q/b", "new": "—"}
            ],
        )
        result = self.read()
        self.assertTrue(
            any(row["audit_id"] == str(obj.pk) and row["clear_evidence"] for row in result["four_cell_history_changes"])
        )

    def test_semantic_preview_never_fetches_before_or_claims_grade_authority(self):
        obj = self.receipt(
            mutate=lambda k: k["new_values"]["protected_academic"].update(
                unknown_private_model={"contact": "PRIVATE_CONTACT"}
            )
        )
        result = diagnostic.metadata(self.case)
        self.assertEqual(result["row_count"], 2)
        preview = result["receipt_semantic_previews"][0]
        self.assertFalse(preview["semantic_checks_passed"])
        self.assertFalse(preview["grade_apply_authority"])
        self.assertEqual(preview["proof"]["protected_unknown_key_count"], 1)
        self.assertEqual(preview["proof"]["before_field_types"]["rows"], "array")
        self.assertEqual(preview["proof"]["details_known_keys"], list(spec.DETAILS))
        self.assertIsNone(preview["proof"]["protected_fingerprints"])
        self.assertNotIn("PRIVATE", json.dumps(result, default=str))
        path = Path(__file__).resolve().parents[3] / "scripts/ops/workload_receipt_preview_scope.py"
        definition = importlib.util.spec_from_file_location("receipt_preview_actual_pg", path)
        validator = importlib.util.module_from_spec(definition)
        definition.loader.exec_module(validator)
        with (
            patch.dict(validator.contract.PINS, spec.PINS, clear=True),
            patch.dict(validator.contract.FIELD_PINS, spec.FIELD_PINS, clear=True),
        ):
            validator.validate(json.loads(json.dumps(preview, default=str)))
        self.assertIn(str(obj.pk), {r["id"] for r in result["rows"]})

    def test_empty_result_count_zero_md5_sentinel_is_not_falsely_changed(self):
        obj = self.receipt(mutate=lambda row: row["new_values"]["protected_academic"]["mark"].update(md5=""))
        result = self.read()
        row = next(row for row in result["four_cell_history_audits"] if row["id"] == str(obj.pk))
        self.assertEqual(row["projection"], "verified_workload_receipt")
        self.assertEqual(row["case_ids"], [])
        self.assertEqual(row["json_hash_policy"], spec.JSON_SQL_POLICY)


@override_settings(RLS_TRANSACTION_SCOPED=True)
class TransactionScopedReceiptTests(FixedWorkloadReceiptTests):
    pass


del Base
