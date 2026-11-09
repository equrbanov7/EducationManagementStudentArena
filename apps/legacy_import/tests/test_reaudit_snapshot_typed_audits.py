"""Native typed merge lineage is exported without widening cells class authority."""

import datetime as dt
from collections import Counter
from unittest.mock import patch

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase

from apps.legacy_import.services.reaudit_snapshot import queries
from apps.registrar.models import CourseOffering, Subject
from apps.registrar.reaudit_cells.class_history import fingerprint, from_snapshot, from_tables
from apps.registrar.reaudit_cells.creation_proof import seal
from apps.registrar.reaudit_cells.manifest import normalize
from apps.registrar.reaudit_cells.snapshot import capture
from apps.registrar.tests import test_reaudit_cells_20261109 as fixtures
from apps.registrar.tests.test_lab_groups_2026_11_06 import _LabWorld
from apps.registrar.twin_merge_empty import EmptyTwinMerge
from apps.registrar.twin_merge_restore import restore_empty_merge
from apps.registrar.twin_merge_scored import ScoredTwinMerge
from core.audit import log_action
from core.constants import AuditAction


class TypedAuditSnapshotTest(_LabWorld, TestCase):
    setUp = fixtures.CellsRepairTest.setUp
    map = fixtures.CellsRepairTest.map
    set_sources = fixtures.CellsRepairTest.set_sources

    def exported(self, label="audit.AuditLog"):
        self.assertEqual(connection.vendor, "postgresql")
        with patch.object(queries, "ORG", str(self.org.pk)), patch.object(queries, "PERIOD", str(self.period.pk)):
            spec = queries.SCHEMAS[label]
            return normalize(list(queries.scoped_query(label, spec).order_by("pk").values(*spec["fields"])))

    def log(self, *, obj=None, **fields):
        return log_action(
            organization=self.org,
            user=self.owner,
            action=AuditAction.UPDATE,
            obj=obj or self.offering,
            **fields,
        )

    def make_offering(self, code):
        subject = Subject.objects.create(organization=self.org, code=code, name=code)
        return CourseOffering.objects.create(
            organization=self.org,
            subject=subject,
            period=self.period,
            group=self.group,
            instructor=self.teacher,
        )

    def test_native_merge_companion_restore_typed_receipts_are_exported(self):
        target, empty = self.make_offering("TARGET"), self.make_offering("EMPTY")
        exam = apps.get_model("exams", "Exam").objects.create(
            organization=self.org, author=self.teacher, subject=self.offering.subject, title="Synthetic"
        )
        exam.journal_offerings.add(self.offering)
        counts = Counter()
        ScoredTwinMerge(organization=self.org, actor=self.owner, counts=counts).run(
            [{"source": str(self.offering.pk), "target": str(target.pk), "target_marks": "keep"}]
        )
        self.assertEqual(counts["pairs_merged_scored"], 1)
        EmptyTwinMerge(organization=self.org, actor=self.owner, counts=counts).merge(empty, target, {})
        self.assertTrue(
            restore_empty_merge(
                organization=self.org, actor=self.owner, counts=counts, twin_id=empty.pk, keep_id=target.pk
            )
        )
        audit = apps.get_model("audit", "AuditLog")
        native = audit.objects.filter(
            organization=self.org,
            content_type__app_label="registrar",
            content_type__model="courseoffering",
        )
        expected = set(map(str, native.values_list("pk", flat=True)))
        self.assertGreaterEqual(len(expected), 7)
        self.assertTrue(native.filter(changes__kind="twin_merge_scored").exists())
        self.assertTrue(native.filter(changes__kind="twin_merge_empty_restore").exists())
        self.assertTrue(native.filter(new_values__source=str(self.offering.pk)).exists())
        exported = {row["id"]: row for row in self.exported()}
        self.assertTrue(expected.issubset(exported))
        self.assertTrue(all(exported[pk]["resource_type"] == "" for pk in expected))
        self.assertTrue(all(exported[pk]["content_type__app_label"] == "registrar" for pk in expected))
        self.assertTrue(all(exported[pk]["content_type__model"] == "courseoffering" for pk in expected))

    def test_tenant_app_and_cutoff_remain_bounded(self):
        audit = apps.get_model("audit", "AuditLog")
        kept = self.log()
        unrelated = self.log(obj=self.owner)
        foreign = apps.get_model("organizations", "Organization").objects.create(
            name="Foreign", slug="typed-audit-foreign", owner=self.owner
        )
        outside = audit.objects.create(
            organization=foreign,
            action=AuditAction.UPDATE,
            content_type=ContentType.objects.get_for_model(CourseOffering),
            object_id=str(self.offering.pk),
        )
        boundary = dt.datetime(2026, 9, 1, tzinfo=dt.timezone(dt.timedelta(hours=4)))
        with patch("django.utils.timezone.now", return_value=boundary - dt.timedelta(microseconds=1)):
            old = self.log()
        with patch("django.utils.timezone.now", return_value=boundary):
            edge = self.log()
        prefix = self.log(obj=self.owner, resource_type="registrar.synthetic")
        ids = {row["id"] for row in self.exported()}
        self.assertTrue({str(kept.pk), str(edge.pk), str(prefix.pk)}.issubset(ids))
        self.assertFalse({str(unrelated.pk), str(outside.pk), str(old.pk)} & ids)

    def test_class_history_keeps_exact_native_prefix_date_and_seal_fields(self):
        self.source["class_authority_sha256"] = "a" * 64
        payload = {"offering_id": str(self.offering.pk), "date": self.source["slot"]["date"]}
        typed = self.log(changes=payload)
        kept = self.log(resource_type="registrar.lesson", changes=payload)
        creation = self.log(resource_type="registrar.subgroup_journal_merge", changes={"manifest": {}})
        boundary = dt.datetime(2026, 9, 1, tzinfo=dt.timezone(dt.timedelta(hours=4)))
        with patch("django.utils.timezone.now", return_value=boundary - dt.timedelta(microseconds=1)):
            old = self.log(resource_type="registrar.lesson", changes=payload)
        native = capture(organization=self.org, actor=self.owner, plan=self.plan)
        tables = {
            label: self.exported(label)
            for label in (
                "registrar.Lesson",
                "registrar.LessonCorrection",
                "registrar.CorrectionReversal",
                "audit.AuditLog",
            )
        }
        exported = {row["id"]: row for row in tables["audit.AuditLog"]}
        self.assertIn(str(typed.pk), exported)
        self.assertNotIn(str(old.pk), exported)
        self.assertIn(str(kept.pk), {row["id"] for row in native["class_history_audits"]})
        self.assertNotIn(str(typed.pk), {row["id"] for row in native["class_history_audits"]})
        # Even a caller with a wider historical table cannot change native class authority.
        audit = apps.get_model("audit", "AuditLog")
        tables["audit.AuditLog"].append(normalize(audit.objects.filter(pk=old.pk).values().get()))
        self.assertEqual(
            fingerprint(from_tables(tables), course=native["offerings"][0], slot=self.source["slot"]),
            fingerprint(from_snapshot(native), course=native["offerings"][0], slot=self.source["slot"]),
        )
        original = normalize(audit.objects.filter(pk=creation.pk).values().get())
        self.assertEqual(seal(original), seal(exported[str(creation.pk)]))
