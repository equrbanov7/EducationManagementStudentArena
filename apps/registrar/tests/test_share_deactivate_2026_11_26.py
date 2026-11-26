"""Dizayn 26.11: ``deactivate_journal_share_20261126`` — 635 Q jurnalında Fatimə İsmayılovanın artıq payı passiv."""

from __future__ import annotations

import pathlib
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase

from apps.organizations.models import Membership
from apps.registrar import share_deactivate_2026_11_26 as fixer
from apps.registrar.models import JournalShare, JournalShareSource, Lesson
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "share_deactivate: "


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
    def test_fixed_ids_and_workflow(self):
        self.assertEqual((fixer.OFFERING_ID[:8], fixer.TEACHER_ID), ("b1ef8891", 8390))
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - deactivate_journal_share_20261126\n", text)
        self.assertIn("            deactivate_journal_share_20261126)\n", text)
        self.assertIn('[ "$COMMAND" = "deactivate_journal_share_20261126" ]', text)
        self.assertIn("|share_deactivate|", text)
        self.assertIn("^shdeac-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$", text)


class ShareDeactivateTest(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            User = get_user_model()
            cls.admin = User.objects.create_superuser("shdeac_admin", "shdeac_admin@qku.edu.az", "pw")
            cls.extra = User.objects.create_user("shdeac_t", "shdeac_t@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.extra,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.history.name = "Kompüter layihələndirilməsi"
            cls.history.save(update_fields=["name"])
            cls.share = JournalShare.objects.create(
                organization=cls.org, offering=cls.offering, teacher=cls.extra, source=JournalShareSource.MANUAL
            )

    def setUp(self):
        for name, value in (("OFFERING_ID", str(self.offering.pk)), ("TEACHER_ID", self.extra.pk)):
            patcher = mock.patch.object(fixer, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, *extra):
        out = StringIO()
        call_command(
            "deactivate_journal_share_20261126",
            "--org",
            self.org.slug,
            "--actor",
            self.admin.username,
            *extra,
            stdout=out,
        )
        return _parse(out.getvalue())

    def active(self):
        with bypass_rls():
            return JournalShare.objects.get(pk=self.share.pk).is_active

    def test_dry_run_then_apply_then_undo(self):
        counts, batch = self.call()
        self.assertEqual((counts["shares_deactivated"], batch, self.active()), ("1", "", True))
        counts, batch = self.call("--apply")
        self.assertEqual(counts["shares_deactivated"], "1")
        self.assertFalse(self.active())
        again, _ = self.call("--apply")
        self.assertEqual(again["nothing_to_deactivate"], "1")
        undone, _ = self.call("--apply", "--undo", f"--batch={batch}")
        self.assertEqual(undone["undo_shares_reactivated"], "1")
        self.assertTrue(self.active())

    def test_refused_when_the_teacher_wrote_in_this_journal(self):
        with bypass_rls():
            Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=self.offering.period.start_date,
                instructor=self.extra,
            )
        counts, _ = self.call("--apply")
        self.assertEqual(counts["teacher_has_records_blocked"], "1")
        self.assertTrue(self.active())
