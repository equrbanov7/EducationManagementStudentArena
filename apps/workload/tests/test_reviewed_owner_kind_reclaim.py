"""Official Enzimologiya source retires an incorrect automatic seminar allocation."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.workload.services import reviewed_split_kind_load as repair
from apps.workload.services.sbio235_state import RepairError
from core.rls import reset_rls_context

from .test_reviewed_split_kind_load import SplitKindLoadTests


@override_settings(RLS_TRANSACTION_SCOPED=True)
class OwnerKindReclaimTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        SplitKindLoadTests.setUpTestData.__func__(cls)

    def setUp(self):
        SplitKindLoadTests.setUp(self)
        self.seminar.teacher = self.teacher
        self.seminar.save()
        for teacher, kinds in ((self.previous, ["lecture"]), (self.teacher, ["seminar"])):
            self.offering.shares.create(organization=self.org, teacher=teacher, kinds=kinds, source="workload")
        self.specpatch = patch.dict(
            repair.RECLAIM_SPEC,
            {
                "ROW": str(self.row.pk),
                "JOURNAL": str(self.offering.pk),
                "GROUP": str(self.ga.pk),
                "SUBJECT": str(self.sa.pk),
                "PERIOD": str(self.period.pk),
                "TASK": str(self.ta.pk),
                "CHAIR": str(self.finance.pk),
                "OWNER": self.previous.pk,
                "TEACHER": self.teacher.pk,
            },
        )
        self.specpatch.start()
        self.manifest = {
            "format": repair.RECLAIM_FORMAT,
            "organization_id": repair.ORG,
            "source_sha256": repair.SOURCE_SHA,
            "sources": repair.RECLAIM_SPEC["SOURCES"],
        }

    def tearDown(self):
        self.specpatch.stop()
        self.patcher.stop()
        reset_rls_context()

    def execute(self, **kw):
        return repair.run(
            manifest=self.manifest, manifest_sha="f" * 64, lines=[2000], organization=self.org, user=self.admin, **kw
        )

    def test_reclaim_keeps_journal_marks_and_retires_only_automatic_access(self):
        before = repair._state(self.row, self.offering)
        dry = self.execute()
        self.assertEqual(before, repair._state(self.row, self.offering))
        self.execute(apply=True, expected_baseline=dry["baseline"])
        self.seminar.refresh_from_db()
        self.assertEqual(self.seminar.teacher_id, self.previous.pk)
        self.assertFalse(self.offering.shares.filter(is_active=True).exists())
        self.assertEqual(self.offering.shares.count(), 2)
        repair._protected(before, repair._state(self.row, self.offering))
        self.assertEqual(self.execute()["already_done"], 1)

    def test_undo_restores_exact_shares_and_assignment_id(self):
        before = repair._state(self.row, self.offering)
        dry = self.execute()
        result = self.execute(apply=True, expected_baseline=dry["baseline"])
        preview = self.execute(undo=result["batch"])
        self.execute(undo=result["batch"], apply=True, expected_baseline=preview["baseline"])
        self.seminar.refresh_from_db()
        self.assertEqual(self.seminar.teacher_id, self.teacher.pk)
        self.assertEqual(before["shares"], repair._state(self.row, self.offering)["shares"])
        repair._protected(before, repair._state(self.row, self.offering))

    def test_limited_or_manual_share_never_reclaimed(self):
        share = self.offering.shares.get(teacher=self.teacher)
        share.enrollments.add(self.offering.enrollments.first())
        with self.assertRaisesMessage(RepairError, "reclaim_existing_share_needs_review"):
            self.execute()
