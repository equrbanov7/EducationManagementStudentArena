"""An exact lecture/seminar split preserves history and narrows writing by activity."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.workload.models import TeacherAssignment
from apps.workload.services import reviewed_split_kind_load as repair
from apps.workload.services.sbio235_state import RepairError
from core.rls import reset_rls_context

from .test_reviewed_language_level_load import LanguageLevelLoadTests


@override_settings(RLS_TRANSACTION_SCOPED=True)
class SplitKindLoadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        LanguageLevelLoadTests.setUpTestData.__func__(cls)

    def setUp(self):
        LanguageLevelLoadTests.setUp(self)
        self.patcher.stop()
        self.share.delete()
        self.row.lecture_plan = self.row.lecture_total = 30
        self.row.seminar_plan = self.row.seminar_total = 30
        self.row.total_hours = 60
        self.row.save()
        self.assignment.activity = "lecture"
        self.assignment.hours = 30
        self.assignment.save()
        self.seminar = TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=self.previous, activity="seminar", hours=30
        )
        self.offering.lesson_hours = 60
        self.offering.save(update_fields=["lesson_hours"])
        self.patcher = patch.multiple(
            repair,
            ROW=str(self.row.pk),
            JOURNAL=str(self.offering.pk),
            GROUP=str(self.ga.pk),
            SUBJECT=str(self.sa.pk),
            PERIOD=str(self.period.pk),
            TASK=str(self.ta.pk),
            CHAIR=str(self.finance.pk),
            OWNER=self.previous.pk,
            TEACHER=self.teacher.pk,
        )
        self.patcher.start()
        self.manifest = {
            "format": repair.FORMAT,
            "organization_id": repair.ORG,
            "source_sha256": repair.SOURCE_SHA,
            "sources": repair.SOURCES,
        }

    def tearDown(self):
        self.patcher.stop()
        reset_rls_context()

    def execute(self, **kw):
        return repair.run(
            manifest=self.manifest, manifest_sha="e" * 64, lines=[1900], organization=self.org, user=self.admin, **kw
        )

    def test_split_preserves_owner_academic_and_assignment_identity(self):
        before = repair._state(self.row, self.offering)
        dry = self.execute()
        self.assertEqual(before, repair._state(self.row, self.offering))
        self.execute(apply=True, expected_baseline=dry["baseline"])
        self.seminar.refresh_from_db()
        self.assertEqual(self.seminar.teacher_id, self.teacher.pk)
        self.assertEqual(self.row.assignments.count(), 2)
        self.assertEqual(
            {(s.teacher_id, tuple(s.kinds)) for s in self.offering.shares.all()},
            {(self.previous.pk, ("lecture",)), (self.teacher.pk, ("seminar",))},
        )
        repair._protected(before, repair._state(self.row, self.offering))
        self.assertEqual(self.execute()["already_done"], 1)

    def test_undo_restores_old_assignment_and_only_generated_shares(self):
        before = repair._state(self.row, self.offering)
        dry = self.execute()
        applied = self.execute(apply=True, expected_baseline=dry["baseline"])
        preview = self.execute(undo=applied["batch"])
        self.execute(undo=applied["batch"], apply=True, expected_baseline=preview["baseline"])
        self.seminar.refresh_from_db()
        self.assertEqual(self.seminar.teacher_id, self.previous.pk)
        self.assertFalse(self.offering.shares.exists())
        repair._protected(before, repair._state(self.row, self.offering))

    def test_existing_manual_share_is_not_overwritten(self):
        self.offering.shares.create(organization=self.org, teacher=self.teacher, kinds=["seminar"], source="manual")
        with self.assertRaisesMessage(RepairError, "split_kind_existing_share_needs_review"):
            self.execute()
