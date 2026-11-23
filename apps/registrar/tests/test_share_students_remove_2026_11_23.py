"""MR-000686/687: ``remove_share_students_20261123`` — iki payda olan tələbə səhv müəllimin payından çıxır."""

from __future__ import annotations

import pathlib
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.organizations.models import Membership
from apps.registrar import share_students_remove_2026_11_23 as fixer
from apps.registrar.models import Enrollment, JournalShare, JournalShareSource
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "share_remove: "


def _parse(text: str) -> tuple[dict, str]:
    counts, batch = {}, ""
    for line in text.splitlines():
        if not line.startswith(PREFIX) or "mode=" in line:
            continue
        body = line[len(PREFIX) :]
        if body.startswith("batch="):
            batch = body.split("=", 1)[1]
            continue
        counts.update(pair.split("=", 1) for pair in body.split())
    return counts, batch


class SpecTest(SimpleTestCase):
    def test_fixed_ids(self):
        self.assertRegex(fixer.OFFERING_ID, r"^bde3ea2e-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        self.assertEqual({teacher for teacher, _ in fixer.REMOVALS}, {8361, 8373})
        for _teacher, prefix in fixer.REMOVALS:
            self.assertRegex(prefix, r"^[0-9a-f]{8}$")

    def test_workflow_runs_the_command_and_keeps_its_summary(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - remove_share_students_20261123\n", text)
        self.assertIn("            remove_share_students_20261123)\n", text)
        self.assertIn('[ "$COMMAND" = "remove_share_students_20261123" ]', text)
        self.assertIn("|share_remove|", text)
        self.assertIn("^shrem-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$", text)


class ShareStudentsRemoveTest(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            User = get_user_model()
            cls.admin = User.objects.create_superuser("shrem_admin", "shrem_admin@qku.edu.az", "pw")
            cls.teacher_a = User.objects.create_user("shrem_a", "shrem_a@qku.edu.az", "pw")
            cls.teacher_b = User.objects.create_user("shrem_b", "shrem_b@qku.edu.az", "pw")
            for teacher in (cls.teacher_a, cls.teacher_b):
                Membership.objects.create(
                    user=teacher,
                    organization=cls.org,
                    role=cls.org.roles.get(name="teacher"),
                    is_primary=True,
                    is_active=True,
                )
            cls.history.name = "İxtisasyönümlü xarici dil-2"
            cls.history.save(update_fields=["name"])
            cls.host_row = Enrollment.objects.get(offering=cls.offering, student=cls.host)
            cls.musa, cls.medine = (
                Enrollment.objects.create(organization=cls.org, offering=cls.offering, student=student)
                for student in (cls.guest, cls.far_student)
            )
            cls.share_a = JournalShare.objects.create(
                organization=cls.org, offering=cls.offering, teacher=cls.teacher_a, source=JournalShareSource.MANUAL
            )
            cls.share_b = JournalShare.objects.create(
                organization=cls.org, offering=cls.offering, teacher=cls.teacher_b, source=JournalShareSource.MANUAL
            )
            cls.share_a.enrollments.set([cls.host_row, cls.musa, cls.medine])
            cls.share_b.enrollments.set([cls.musa, cls.medine])

    def setUp(self):
        removals = (
            (self.teacher_a.pk, str(self.musa.pk)[:8]),
            (self.teacher_b.pk, str(self.medine.pk)[:8]),
        )
        for name, value in (("OFFERING_ID", str(self.offering.pk)), ("REMOVALS", removals)):
            patcher = mock.patch.object(fixer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, *extra):
        out = StringIO()
        call_command(
            "remove_share_students_20261123", "--org", self.org.slug, "--actor", self.admin.username, *extra, stdout=out
        )
        return _parse(out.getvalue())

    def rows(self, share):
        return set(share.enrollments.values_list("pk", flat=True))

    def test_dry_run_counts_and_writes_nothing(self):
        counts, batch = self.call()
        self.assertEqual(counts["students_removed"], "2")
        self.assertEqual(batch, "")
        self.assertEqual(self.rows(self.share_a), {self.host_row.pk, self.musa.pk, self.medine.pk})
        self.assertEqual(self.rows(self.share_b), {self.musa.pk, self.medine.pk})

    def test_apply_swaps_then_is_idempotent_then_undo_restores(self):
        counts, batch = self.call("--apply")
        self.assertEqual(counts["students_removed"], "2")
        self.assertRegex(batch, r"^shrem-\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertEqual(self.rows(self.share_a), {self.host_row.pk, self.medine.pk})
        self.assertEqual(self.rows(self.share_b), {self.musa.pk})
        again, _ = self.call("--apply")
        self.assertEqual(again["already_removed"], "2")
        self.assertEqual(again["nothing_to_remove"], "1")
        undone, _ = self.call("--apply", "--undo", f"--batch={batch}")
        self.assertEqual(undone["undo_students_restored"], "2")
        self.assertEqual(self.rows(self.share_a), {self.host_row.pk, self.musa.pk, self.medine.pk})
        self.assertEqual(self.rows(self.share_b), {self.musa.pk, self.medine.pk})

    def test_student_never_left_without_a_teacher(self):
        self.share_b.enrollments.remove(self.musa)
        counts, _ = self.call("--apply")
        self.assertEqual(counts["would_orphan"], "1")
        self.assertEqual(counts["blocked"], "1")
        self.assertEqual(self.rows(self.share_a), {self.host_row.pk, self.musa.pk, self.medine.pk})

    def test_wrong_subject_or_missing_share_is_refused(self):
        with mock.patch.object(fixer, "SUBJECT_MARK", "başqa fənn"):
            counts, _ = self.call("--apply")
        self.assertEqual(counts["offering_invalid"], "1")
        self.share_b.is_active = False
        self.share_b.save(update_fields=["is_active"])
        counts, _ = self.call("--apply")
        # B passiv: Musa A-dan çıxsa heç bir payda qalmaz → orphan qoruyucusu bütün planı dayandırır.
        self.assertEqual(counts["blocked"], "1")
        self.assertEqual(self.rows(self.share_a), {self.host_row.pk, self.musa.pk, self.medine.pk})

    def test_undo_requires_valid_batch(self):
        with self.assertRaises(CommandError):
            self.call("--undo")
        with self.assertRaises(CommandError):
            self.call("--undo", "--batch=bad")
