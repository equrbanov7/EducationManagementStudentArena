"""Sahib 2026-11-07: alt qrupa keçid ana qrupun jurnalındakı heç nəyi gizlətməməlidir.

* tələbə öz qrupunun qeydiyyatlı alt qrupuna keçəndə ana qrupun DƏRSLİ jurnalındakı sətri aktiv qalır (qeydləri ilə);
  dərssiz ana jurnal əvvəlki kimi alt qrupun jurnalına keçir;
* ``restore_subgroup_parent_enrollments``: köhnə qaydanın tarixçəyə atdığı sətir bərpa olunur (qeydləri olduğu kimi),
  qeydsiz varis tarixçəyə keçir, qeydli varis də aktiv qalır; defolt dry-run, idempotent, stdout-da yalnız saylar.
"""

import io
from unittest import mock

from django.core.management import call_command
from django.utils import timezone

from apps.organizations.models import OrgUnit
from apps.registrar import transfer
from apps.registrar.models import Enrollment, Lesson, LessonMark
from apps.registrar.tests.test_audit_2026_09_28_b2_lifecycle import _LifecycleBase
from apps.registrar.tests.test_lab_groups_2026_11_06 import WORKFLOW
from core.rls import bypass_rls


class _SubgroupBase(_LifecycleBase):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            OrgUnit.objects.filter(pk=self.group2.pk).update(settings={"parent_group": str(self.group1.pk)})
            self.group2.refresh_from_db()
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])

    def _lesson_with_mark(self, enrollment):
        with bypass_rls():
            lesson = Lesson.objects.create(
                organization=self.org, offering=enrollment.offering, date=timezone.localdate(), kind="lecture"
            )
            LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=enrollment, status="present")
        return lesson

    def _transfer(self):
        with bypass_rls():
            return transfer.transfer_student_group(
                record=self.record, new_group=self.group2, period=self.period, by_user=self.owner
            )

    def _get(self, enrollment):
        with bypass_rls():
            return Enrollment.objects.get(pk=enrollment.pk)


class SubgroupTransferKeepsParentJournalTest(_SubgroupBase):
    def test_parent_journal_with_lessons_keeps_the_student(self):
        self._lesson_with_mark(self.current)
        self._transfer()
        row = self._get(self.current)
        self.assertEqual((row.status, row.superseded_by_id), (Enrollment.Status.ENROLLED, None))
        with bypass_rls():
            self.assertTrue(LessonMark.objects.filter(enrollment=row).exists())
            self.assertFalse(
                Enrollment.objects.filter(
                    student=self.student, offering__group=self.group2, status=Enrollment.Status.ENROLLED
                ).exists()
            )

    def test_parent_journal_without_lessons_moves_as_before(self):
        self._transfer()
        row = self._get(self.current)
        self.assertEqual(row.status, Enrollment.Status.DROPPED)
        self.assertEqual(row.superseded_by.offering.group_id, self.group2.pk)

    def test_plain_transfer_to_another_group_still_moves(self):
        with bypass_rls():
            OrgUnit.objects.filter(pk=self.group2.pk).update(settings={})
            self.group2.refresh_from_db()
        self._lesson_with_mark(self.current)
        self._transfer()
        self.assertEqual(self._get(self.current).status, Enrollment.Status.DROPPED)


class RestoreSubgroupParentEnrollmentsTest(_SubgroupBase):
    def _old_rule_transfer(self):
        with mock.patch("apps.registrar.subgroup_parent_restore_2026_11_07.parent_journal_in_use", return_value=False):
            self._transfer()
        return self._get(self.current).superseded_by

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "restore_subgroup_parent_enrollments",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            *extra,
            stdout=out,
        )
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, r"^lab_groups: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("lab_groups: ") :].split())
        return counts

    def test_dry_run_apply_idempotent(self):
        self._lesson_with_mark(self.current)
        successor = self._old_rule_transfer()
        self.assertEqual(self._call(), {"candidates": "1", "restored": "1", "successor_retired": "1"})
        self.assertEqual(self._get(self.current).status, Enrollment.Status.DROPPED)
        self._call("--apply")
        row, succ = self._get(self.current), self._get(successor)
        self.assertEqual((row.status, row.superseded_by_id), (Enrollment.Status.ENROLLED, None))
        self.assertEqual((succ.status, succ.superseded_by_id), (Enrollment.Status.DROPPED, row.pk))
        with bypass_rls():
            self.assertTrue(LessonMark.objects.filter(enrollment=row).exists())
        self.assertEqual(self._call("--apply"), {"candidates": "0"})

    def test_successor_with_records_stays_active(self):
        self._lesson_with_mark(self.current)
        successor = self._old_rule_transfer()
        self._lesson_with_mark(successor)
        self.assertEqual(self._call("--apply"), {"candidates": "1", "restored": "1", "both_kept": "1"})
        self.assertEqual(self._get(self.current).status, Enrollment.Status.ENROLLED)
        self.assertEqual(self._get(successor).status, Enrollment.Status.ENROLLED)

    def test_parent_journal_without_lessons_is_not_restored(self):
        self._old_rule_transfer()
        self.assertEqual(self._call("--apply"), {"candidates": "0"})
        self.assertEqual(self._get(self.current).status, Enrollment.Status.DROPPED)

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - restore_subgroup_parent_enrollments\n", text)
        self.assertIn('[ "$COMMAND" = "restore_subgroup_parent_enrollments" ]', text)
