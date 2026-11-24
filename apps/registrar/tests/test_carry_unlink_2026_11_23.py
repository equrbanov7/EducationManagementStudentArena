"""MR-000675: ``unlink_qiyabi_carry_20261123`` — qiyabi qrupun əyani jurnaldan gələn q/b köçürməsi ayrılır."""

from __future__ import annotations

import datetime
import pathlib
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.registrar import carry_unlink_2026_11_23 as fixer
from apps.registrar import guest_merge
from apps.registrar.models import Enrollment, Lesson, LessonMark
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "carry_unlink: "


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
        self.assertTrue(fixer.TARGET_GROUP.startswith("c4fd6c8c-"))
        self.assertTrue(fixer.SOURCE_GROUP.startswith("c7757f1c-"))
        self.assertEqual((fixer.TARGET_NAME, fixer.SOURCE_NAME), ("2536 MRK", "536 MRK"))

    def test_workflow_runs_the_command_and_keeps_its_summary(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - unlink_qiyabi_carry_20261123\n", text)
        self.assertIn("            unlink_qiyabi_carry_20261123)\n", text)
        self.assertIn('[ "$COMMAND" = "unlink_qiyabi_carry_20261123" ]', text)
        self.assertIn("|carry_unlink|", text)
        self.assertIn("^cunlink-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$", text)


class CarryUnlinkTest(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.admin = get_user_model().objects.create_superuser("cunl_admin", "cunl_admin@qku.edu.az", "pw")
            cls.group1.name = "2536 MRK"
            cls.group1.save(update_fields=["name"])
            cls.group2.name = "536  MRK"
            cls.group2.save(update_fields=["name"])
            cls.source = Enrollment.objects.get(student=cls.guest, offering=cls.other_offering)
            cls.target = Enrollment.objects.create(organization=cls.org, student=cls.guest, offering=cls.offering)
            cls.source.status = Enrollment.Status.DROPPED
            cls.source.superseded_by = cls.target
            cls.source.save(update_fields=["status", "superseded_by"])
            for index, enrollment in enumerate((cls.source, cls.source, cls.target)):
                lesson = Lesson.objects.create(
                    organization=cls.org,
                    offering=enrollment.offering,
                    kind="seminar",
                    date=datetime.date(2025, 9, 1) + datetime.timedelta(days=index),
                    hours=2,
                )
                LessonMark.objects.create(organization=cls.org, lesson=lesson, enrollment=enrollment, status="absent")

    def setUp(self):
        for name, value in (("TARGET_GROUP", str(self.group1.pk)), ("SOURCE_GROUP", str(self.group2.pk))):
            patcher = mock.patch.object(fixer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        scope = bypass_rls()
        scope.__enter__()
        self.addCleanup(scope.__exit__, None, None, None)

    def call(self, *extra):
        out = StringIO()
        call_command(
            "unlink_qiyabi_carry_20261123", "--org", self.org.slug, "--actor", self.admin.username, *extra, stdout=out
        )
        return _parse(out.getvalue())

    def state(self):
        self.source.refresh_from_db()
        self.target.refresh_from_db()
        return self.source.superseded_by_id, guest_merge.carried_absence_hours(self.target), self.target.absence_hours

    def test_dry_run_counts_and_writes_nothing(self):
        counts, batch = self.call()
        self.assertEqual(counts["carry_unlinked"], "1")
        self.assertEqual(batch, "")
        self.assertEqual(self.state()[:2], (self.target.pk, 4))

    def test_apply_unlinks_recomputes_and_undo_relinks(self):
        counts, batch = self.call("--apply")
        self.assertEqual(counts["carry_unlinked"], "1")
        self.assertRegex(batch, r"^cunlink-\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertEqual(self.state(), (None, 0, 2))
        self.assertEqual(LessonMark.objects.filter(enrollment=self.source).count(), 2)
        again, _ = self.call("--apply")
        self.assertEqual(again["nothing_to_unlink"], "1")
        undone, _ = self.call("--apply", "--undo", f"--batch={batch}")
        self.assertEqual(undone["undo_relinked"], "1")
        self.assertEqual(self.state(), (self.target.pk, 4, 6))

    def test_group_name_mismatch_refuses(self):
        with mock.patch.object(fixer, "SOURCE_NAME", "936 MRK"):
            counts, _ = self.call("--apply")
        self.assertEqual(counts["groups_mismatch"], "1")
        self.assertEqual(self.state()[:2], (self.target.pk, 4))

    def test_undo_requires_valid_batch(self):
        with self.assertRaises(CommandError):
            self.call("--undo")
        with self.assertRaises(CommandError):
            self.call("--undo", "--batch=bad")
