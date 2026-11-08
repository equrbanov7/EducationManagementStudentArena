"""Sahib 2026-11-07: alt qrupa keçid ana qrupun jurnalındakı heç nəyi gizlətməməlidir.

* köçürmə xidməti DƏYİŞMİR (köhnə bərpa alətləri ona bağlıdır);
* ``restore_subgroup_parent_enrollments``: köhnə qaydanın tarixçəyə atdığı sətir bərpa olunur (qeydləri olduğu kimi),
  qeydsiz varis tarixçəyə keçir, qeydli varis də aktiv qalır; defolt dry-run, idempotent, stdout-da yalnız saylar.
"""

import io
from unittest import mock

from django.core.management import call_command
from django.utils import timezone

from apps.organizations.models import OrgUnit
from apps.registrar import subgroup_parent_restore_2026_11_07 as restore
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


class RestoreSubgroupParentEnrollmentsTest(_SubgroupBase):
    def setUp(self):
        super().setUp()
        patch = mock.patch.object(restore, "PARENT_GROUPS", (str(self.group1.pk),))
        patch.start()
        self.addCleanup(patch.stop)
        patch_since = mock.patch.object(restore, "SINCE", timezone.localdate())
        patch_since.start()
        self.addCleanup(patch_since.stop)

    def _old_rule_transfer(self):
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

    def test_other_parent_groups_are_out_of_scope(self):
        self._lesson_with_mark(self.current)
        self._old_rule_transfer()
        with mock.patch.object(restore, "PARENT_GROUPS", ("00000000-0000-0000-0000-000000000000",)):
            self.assertEqual(self._call("--apply"), {"candidates": "0"})
        self.assertEqual(self._get(self.current).status, Enrollment.Status.DROPPED)

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - restore_subgroup_parent_enrollments\n", text)
        self.assertIn('[ "$COMMAND" = "restore_subgroup_parent_enrollments" ]', text)
