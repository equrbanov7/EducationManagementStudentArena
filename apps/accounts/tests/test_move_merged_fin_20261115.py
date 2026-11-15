"""``move_merged_fin_20261115`` (sahib 2026-11-15): birləşmiş dublikatın FİN-i əsas hesaba keçir, geri qaytarılır."""

from __future__ import annotations

import io
import re

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AuditLog
from apps.organizations.models import Organization
from core.rls import bypass_rls

User = get_user_model()
LINE_RE = re.compile(r"^fin_move: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
CMD = "move_merged_fin_20261115"


class MoveMergedFinTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.admin = User.objects.create_superuser("fm_admin", "fm_admin@qku.edu.az", "pw")
            cls.org = Organization.objects.create(name="FM Org", slug="fm-org", owner=cls.admin)
            cls.source = User.objects.create_user("fm_src", is_active=False)
            cls.target = User.objects.create_user("fm_tgt")
            cls.other = User.objects.create_user("fm_other")
            for user, fin in ((cls.source, "AB12CDE"), (cls.target, None), (cls.other, "ZZ99ZZZ")):
                profile, _ = UserProfile.objects.get_or_create(user=user)
                UserProfile.objects.filter(pk=profile.pk).update(fin=fin)

    def run_cmd(self, *args):
        out = io.StringIO()
        call_command(CMD, "--org", "fm-org", "--actor", "fm_admin", *args, stdout=out)
        lines = out.getvalue().strip().splitlines()
        for line in lines:
            self.assertRegex(line, LINE_RE)
        return lines

    def fin(self, user):
        with bypass_rls():
            return UserProfile.objects.get(user=user).fin

    def test_dry_run_writes_nothing(self):
        lines = self.run_cmd("--pairs", f"{self.source.pk}:{self.target.pk}")
        self.assertIn("moved=1", lines[0])
        self.assertEqual((self.fin(self.source), self.fin(self.target)), ("AB12CDE", None))

    def test_apply_moves_and_undo_restores(self):
        lines = self.run_cmd("--pairs", f"{self.source.pk}:{self.target.pk}", "--apply")
        self.assertEqual((self.fin(self.source), self.fin(self.target)), (None, "AB12CDE"))
        batch = lines[-1].split("batch=")[1]
        with bypass_rls():
            entry = AuditLog.objects.get(resource_id=batch)
        self.assertNotIn("AB12CDE", str(entry.new_values))
        self.run_cmd("--undo", batch, "--apply")
        self.assertEqual((self.fin(self.source), self.fin(self.target)), ("AB12CDE", None))

    def test_guards_skip_without_writing(self):
        lines = self.run_cmd(
            "--pairs", f"{self.target.pk}:{self.source.pk},{self.source.pk}:{self.other.pk}", "--apply"
        )
        self.assertIn("skipped_source_active=1", lines[0])
        self.assertIn("skipped_target_has_fin=1", lines[0])
        self.assertIn("moved=0", lines[0])
        self.assertEqual((self.fin(self.source), self.fin(self.other)), ("AB12CDE", "ZZ99ZZZ"))

    def test_bad_pairs_rejected(self):
        with self.assertRaisesMessage(CommandError, "bad_pairs"):
            self.run_cmd("--pairs", "9507-7742")
