"""Two-source catalogue bridge requires immutable apply evidence and live workload."""

from unittest.mock import patch

from django.test import TestCase

from apps.audit.models import AuditLog
from apps.legacy_import.services import reviewed_content_catalog_bridge as bridge
from apps.legacy_import.services.reviewed_content_contract import ContentError
from apps.registrar.models import CourseOffering
from apps.workload.models import TeacherAssignment
from apps.workload.tests import test_scoped_snapshot as fixtures


class CatalogBridgeTests(TestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp

    def prepare(self):
        pk = next(iter(bridge.BRIDGES))
        legacy, line, code, name = bridge.BRIDGES[pk]
        subject = self.stack["subject"]
        subject.code, subject.name, subject.ects, subject.kind = code, name, 6, "core"
        subject.chair_unit = self.stack["chair"]
        subject.save()
        self.offering = CourseOffering.objects.create(
            id=pk,
            organization=self.org,
            subject=subject,
            period=self.stack["period"],
            group=self.stack["group"],
            instructor=self.teacher,
            lesson_hours=45,
        )
        self.spec = {"legacy_subject_id": legacy, "selection_id": line, "teacher_id": self.teacher.pk}
        self.log = AuditLog.objects.create(
            organization=self.org,
            action="update",
            resource_type="workload.reviewed_source_batch",
            resource_id="fixture-batch",
            reason="workload.reviewed_source_batch",
            new_values={
                "kind": "apply",
                "manifest_sha256": bridge.MANIFEST,
                "details": {"created_subject_ids": [str(subject.pk)], "created_offering_ids": [pk]},
            },
        )
        for kind, hours in (("lecture", 30), ("seminar", 15)):
            TeacherAssignment.objects.create(
                organization=self.org, row=self.row, teacher=self.teacher, activity=kind, hours=hours
            )

    def check(self, maps=None):
        with (
            patch.object(bridge, "TASK", str(self.task.pk)),
            patch.object(bridge, "CHAIR", str(self.stack["chair"].pk)),
        ):
            return bridge.reviewed_catalog_bridge(self.offering, self.spec, maps or set())

    def test_valid_exact_receipt_and_assignment(self):
        self.prepare()
        self.assertTrue(self.check())
        self.assertEqual(AuditLog.objects.filter(pk=self.log.pk).count(), 1)

    def test_changed_receipt_hours_mapping_fail_closed(self):
        self.prepare()
        with self.assertRaisesMessage(ContentError, "reviewed_catalog_bridge_identity_changed"):
            self.check({"different-legacy-target"})
        self.row.seminar_plan = 14
        self.row.save(update_fields=["seminar_plan"])
        with self.assertRaisesMessage(ContentError, "reviewed_catalog_source_workload_changed"):
            self.check()
        with patch.object(bridge, "MANIFEST", "0" * 64):
            with self.assertRaisesMessage(ContentError, "reviewed_catalog_original_receipt_required"):
                self.check()

    def test_undone_receipt_rejected(self):
        self.prepare()
        AuditLog.objects.create(
            organization=self.org,
            action="update",
            resource_type="workload.reviewed_source_batch",
            resource_id="fixture-batch",
            new_values={"kind": "undo"},
        )
        with self.assertRaisesMessage(ContentError, "reviewed_catalog_receipt_undone"):
            self.check()
