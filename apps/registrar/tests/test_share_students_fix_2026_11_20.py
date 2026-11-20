"""MR-000607: ``fix_journal_share_students_20261120`` — seminarçının payına çatışmayan oxuyan tələbələr."""

from __future__ import annotations

import pathlib
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase

from apps.organizations.models import Membership
from apps.registrar import share_students_fix_2026_11_20 as fixer
from apps.registrar.models import Enrollment, JournalShare, JournalShareSource
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "share_students: "


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
        self.assertRegex(fixer.OFFERING_ID, r"^b9fc8208-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        self.assertEqual(fixer.TEACHER_ID, 8313)
        self.assertEqual(len(set(fixer.ENROLLMENT_PREFIXES)), 3)
        for prefix in fixer.ENROLLMENT_PREFIXES:
            self.assertRegex(prefix, r"^[0-9a-f]{8}$")

    def test_workflow_runs_the_command_and_keeps_its_summary(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - fix_journal_share_students_20261120\n", text)
        self.assertIn("            fix_journal_share_students_20261120)\n", text)
        self.assertIn('[ "$COMMAND" = "fix_journal_share_students_20261120" ]', text)
        self.assertIn("|share_students|", text)
        self.assertIn("^shstud-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$", text)


class ShareStudentsFixTest(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.admin = get_user_model().objects.create_superuser("shstud_admin", "shstud_admin@qku.edu.az", "pw")
            cls.seminarist = get_user_model().objects.create_user("shstud_sem", "shstud_sem@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.seminarist,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.history.name = "Bitki ekologiyası"
            cls.history.save(update_fields=["name"])
            cls.host_row = Enrollment.objects.get(offering=cls.offering, student=cls.host)
            cls.late = [
                Enrollment.objects.create(organization=cls.org, offering=cls.offering, student=student)
                for student in (cls.guest, cls.far_student)
            ]
            cls.share = JournalShare.objects.create(
                organization=cls.org,
                offering=cls.offering,
                teacher=cls.seminarist,
                kinds=["seminar"],
                source=JournalShareSource.MANUAL,
            )
            cls.share.enrollments.set([cls.host_row])

    def setUp(self):
        prefixes = tuple(str(row.pk)[:8] for row in self.late)
        for name, value in (
            ("OFFERING_ID", str(self.offering.pk)),
            ("TEACHER_ID", self.seminarist.pk),
            ("ENROLLMENT_PREFIXES", prefixes),
        ):
            patcher = mock.patch.object(fixer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, *extra):
        out = StringIO()
        call_command(
            "fix_journal_share_students_20261120",
            "--org",
            self.org.slug,
            "--actor",
            self.admin.username,
            *extra,
            stdout=out,
        )
        return _parse(out.getvalue())

    def rows(self):
        return set(self.share.enrollments.values_list("pk", flat=True))

    def test_dry_run_counts_and_writes_nothing(self):
        counts, batch = self.call()
        self.assertEqual(counts["students_added"], "2")
        self.assertEqual(counts["share_source_manual"], "1")
        self.assertEqual(counts["other_missing"], "0")
        self.assertEqual(batch, "")
        self.assertEqual(self.rows(), {self.host_row.pk})

    def test_apply_adds_exactly_the_listed_rows_then_undo_restores(self):
        counts, batch = self.call("--apply")
        self.assertEqual(counts["students_added"], "2")
        self.assertRegex(batch, r"^shstud-\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertEqual(self.rows(), {self.host_row.pk, *(row.pk for row in self.late)})
        again, _ = self.call("--apply")
        self.assertEqual(again["already_in_share"], "2")
        self.assertEqual(again["nothing_to_add"], "1")
        undone, _ = self.call("--apply", "--undo", f"--batch={batch}")
        self.assertEqual(undone["undo_students_removed"], "2")
        self.assertEqual(self.rows(), {self.host_row.pk})

    def test_unknown_or_dropped_enrollment_blocks_everything(self):
        Enrollment.objects.filter(pk=self.late[1].pk).update(status=Enrollment.Status.DROPPED)
        counts, _ = self.call("--apply")
        self.assertEqual(counts["enrollment_not_found"], "1")
        self.assertEqual(counts["blocked"], "1")
        self.assertEqual(self.rows(), {self.host_row.pk})

    def test_wrong_subject_or_missing_share_is_refused(self):
        with mock.patch.object(fixer, "SUBJECT_MARK", "başqa fənn"):
            counts, _ = self.call("--apply")
        self.assertEqual(counts["offering_invalid"], "1")
        self.share.is_active = False
        self.share.save(update_fields=["is_active"])
        counts, _ = self.call("--apply")
        self.assertEqual(counts["share_missing"], "1")
        self.assertEqual(self.rows(), {self.host_row.pk})

    def test_undo_requires_valid_batch(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self.call("--undo")
        with self.assertRaises(CommandError):
            self.call("--undo", "--batch=bad")
