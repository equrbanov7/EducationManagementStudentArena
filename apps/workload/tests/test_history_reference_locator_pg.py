"""Real PG old/new locator equivalence, one-scan evidence and large JSON query plans."""

import json
import re
import uuid

from django.apps import apps
from django.db import connection
from django.db.models import BooleanField, Q
from django.db.models.expressions import RawSQL
from django.test import TestCase

from apps.workload.services.scoped_snapshot import source58_evidence_spec as fixed
from apps.workload.services.scoped_snapshot.four_cell_history import mark_ids
from apps.workload.services.scoped_snapshot.history_reference_locator import reference_locator
from apps.workload.services.scoped_snapshot.recovery_audit_scope import audit_locator
from apps.workload.services.scoped_snapshot.source58_evidence_history import collect_history
from apps.workload.tests.test_source58_evidence import Source58Fixture


class HistoryReferenceLocatorTests(Source58Fixture, TestCase):
    def setUp(self):
        self.make_fixture()
        self.Audit = apps.get_model("audit.AuditLog")

    def audit(self, **body):
        return self.Audit.objects.create(
            organization=self.org,
            user=self.actor,
            action="update",
            resource_type="test.history",
            resource_id="other",
            **body,
        )

    def old_locator(self, refs=(), points=()):
        ids = {c[k] for c in fixed.CASES.values() for k in ("offering_id", "lesson_id", "enrollment_id")}
        ids |= set(mark_ids(_cases=fixed.CASES).values())
        query = Q(resource_id__in=ids | set(refs))
        table = connection.ops.quote_name(self.Audit._meta.db_table)
        for field in ("changes", "old_values", "new_values"):
            for pk in ids:
                query |= Q(**{field + "__icontains": pk})
            if refs:
                pattern = "(" + "|".join(re.escape(pk) for pk in refs) + ")"
                query |= Q(
                    RawSQL(f"COALESCE({table}.{field}::text ~ %s,FALSE)", [pattern], output_field=BooleanField())
                )
            if points:
                pattern = "(^|[^0-9])(" + "|".join(map(str, points)) + ")([^0-9]|$)"
                query |= Q(
                    RawSQL(f"COALESCE({table}.{field}::text ~ %s,FALSE)", [pattern], output_field=BooleanField())
                )
        return query

    def selected(self, query):
        return set(self.Audit.objects.filter(organization=self.org).filter(query).values_list("pk", flat=True))

    def test_canonical_uuid_case_embedded_fields_and_literal_escaping_match_old_exactly(self):
        graph_id = str(uuid.uuid4())
        refs = {graph_id, "reference:%_[MiXeD]"}
        expected = set()
        for field in ("changes", "old_values", "new_values"):
            for text in (
                self.source_lesson,
                self.source_lesson.upper(),
                "f" + self.source_lesson + "tail",
                graph_id,
                "prefixreference:%_[MiXeD]suffix",
            ):
                expected.add(self.audit(**{field: {"note": text}}).pk)
            self.audit(**{field: {"note": graph_id.upper()}})
            self.audit(**{field: {"note": "reference:AX[MiXeD]"}})
        actual = self.selected(audit_locator(fixed.CASES, referenced_ids=refs))
        self.assertEqual(actual, self.selected(self.old_locator(refs)))
        self.assertEqual(actual, expected)

    def test_numeric_boundaries_null_fields_and_no_cross_field_concatenation(self):
        point = next(iter(fixed.CASES))
        yes = self.audit(new_values={"note": f"x{point}y"})
        self.audit(new_values={"note": f"1{point}0"})
        self.audit(old_values={"note": self.source_lesson[:18]}, new_values={"note": self.source_lesson[18:]})
        self.audit()
        selected = self.selected(audit_locator(fixed.CASES, source_points=fixed.CASES))
        self.assertEqual(selected, self.selected(self.old_locator(points=fixed.CASES)))
        self.assertEqual(selected, {yes.pk})

    def test_empty_and_non_uuid_literal_reference_keeps_original_null_semantics(self):
        yes = self.audit(new_values={})
        no = self.audit()
        query = reference_locator(self.Audit._meta.db_table, insensitive_ids=(), literal_ids={""})
        self.assertIn(yes.pk, self.selected(query))
        self.assertNotIn(no.pk, self.selected(query))

    def test_complete_source58_discovery_runs_expensive_locator_once_and_preserves_unknown(self):
        found = self.audit(new_values={"enrollment_id": str(self.enrollment.pk)})
        unlocated = self.Audit.objects.create(
            organization=self.org,
            user=self.actor,
            action="delete",
            resource_type="registrar.LessonMark",
            resource_id="unknown",
        )
        scans = []

        def capture(execute, sql, params, many, context):
            if "WITH body AS MATERIALIZED" in sql:
                scans.append(sql)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(capture):
            result = collect_history(referenced_ids={str(uuid.uuid4()) for _ in range(4000)})
        self.assertEqual(len(scans), 1)
        self.assertEqual(scans[0].count("regexp_matches("), 1)
        self.assertIn(str(found.pk), {r["id"] for r in result["source58_history_audits"]})
        self.assertEqual(result["source58_history_coverage"][0]["unlocatable_delete_audits"], 1)
        self.assertTrue(self.Audit.objects.filter(pk=unlocated.pk).exists())

    def test_large_payload_four_thousand_references_has_constant_regex_and_real_explain(self):
        refs = {str(uuid.uuid4()) for _ in range(4000)}
        selected = sorted(refs)[-1]
        row = self.audit(new_values={"private_padding": "X" * (4 * 1024 * 1024), "tail": selected})
        query = self.Audit.objects.filter(organization=self.org).filter(audit_locator(fixed.CASES, referenced_ids=refs))
        sql, params = query.values_list("pk", flat=True).query.sql_with_params()
        self.assertEqual(sql.count("regexp_matches("), 1)
        self.assertNotIn('UPPER("audit_auditlog"."new_values"', sql)
        self.assertIn(row.pk, set(query.values_list("pk", flat=True)))
        plan = json.loads(query.values("pk").explain(analyze=True, buffers=True, format="json"))[0]
        self.assertGreaterEqual(plan["Plan"]["Actual Rows"], 1)
        self.assertGreater(plan["Execution Time"], 0)
