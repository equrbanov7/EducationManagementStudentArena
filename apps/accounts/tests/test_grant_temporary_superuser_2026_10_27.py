"""``grant_temporary_superuser`` — müvəqqəti superadmin girişi və geri alma (sahib 2026-10-27)."""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.audit.models import AuditLog

User = get_user_model()


def _run(*args):
    out = StringIO()
    call_command("grant_temporary_superuser", *args, stdout=out)
    return out.getvalue()


class TemporarySuperuserTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tsu.owner", "tsu.owner@x.test", "pw")

    def test_dry_run_writes_nothing(self):
        self.assertIn("state=granted", _run("--username", "tsu.owner"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(AuditLog.objects.filter(resource_type="temporary_superuser").exists())

    def test_grant_then_revoke(self):
        self.assertIn("state=granted", _run("--username", "tsu.owner", "--days", "3", "--apply"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_superuser and self.user.is_staff)
        self.assertIn("state=already_superuser", _run("--username", "tsu.owner", "--apply"))
        self.assertIn("state=revoked", _run("--username", "tsu.owner", "--revoke", "--apply"))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_superuser or self.user.is_staff)
        self.assertEqual(AuditLog.objects.filter(resource_type="temporary_superuser").count(), 2)

    def test_revoke_never_touches_permanent_superuser(self):
        User.objects.filter(pk=self.user.pk).update(is_superuser=True, is_staff=True)
        self.assertIn("state=permanent_superuser_untouched", _run("--username", "tsu.owner", "--revoke", "--apply"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_superuser)

    def test_bounds(self):
        with self.assertRaises(CommandError):
            _run("--username", "tsu.owner", "--days", "30")
        with self.assertRaises(CommandError):
            _run("--username", "yoxdur")
