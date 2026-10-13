"""``retire_qa_accounts`` — prod reyestrindən QA test hesablarını çıxarma (sahib 2026-10-14).

Kilidlənən müqavilə: ``--org`` məcburi; quru qaçış heç nə yazmır; ``--apply`` YALNIZ ``^qa\\.`` + (``@qa.local``
VƏ YA siyahı) hesabları deaktiv edir (real e-poçtlu «qa…» istifadəçiyə toxunmur), silmir, hər hesaba audit sətri
yazır; ``--undo`` eyni paketi bərpa edir.
"""

from __future__ import annotations

from io import StringIO

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()


def _run(*args):
    out = StringIO()
    call_command("retire_qa_accounts", *args, stdout=out)
    return out.getvalue()


class RetireQaAccountsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("rq_owner", "rq_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="RQ Univ",
                slug="rq-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            cls.other_org = Organization.objects.create(
                name="RQ Other",
                slug="rq-other",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            cls.role, _created = Role.objects.update_or_create(
                organization=cls.org,
                name="dean",
                defaults={
                    "display_name": "Dean",
                    "level": 30,
                    "scope_type": RoleScopeType.ORGANIZATION,
                    "permissions": [],
                    "is_active": True,
                },
            )
            cls.other_role, _created = Role.objects.update_or_create(
                organization=cls.other_org,
                name="dean",
                defaults={
                    "display_name": "Dean",
                    "level": 30,
                    "scope_type": RoleScopeType.ORGANIZATION,
                    "permissions": [],
                    "is_active": True,
                },
            )
            cls.qa_dean = cls._member("qa.dean", "qa.dean@qa.local")
            cls.qa_teacher = cls._member("qa.teacher", "someone@example.com")  # siyahıdadır
            cls.real_dean = cls._member("real.dean", "dean@qku.edu.az")
            cls.qa_lookalike = cls._member("qa.real.person", "person@qku.edu.az")  # ad uyğun, e-poçt real
            cls.qa_mail_only = cls._member("qaone", "x@qa.local")  # e-poçt uyğun, ad ^qa\. deyil
            cls.shared = cls._member("qa.sec.member", "shared@qa.local")
            Membership.objects.create(user=cls.shared, organization=cls.other_org, role=cls.other_role, is_active=True)

    @classmethod
    def _member(cls, username, email):
        user = User.objects.create_user(username, email, "pw")
        Membership.objects.create(user=user, organization=cls.org, role=cls.role, is_active=True)
        return user

    def _snapshot(self):
        with bypass_rls():
            return (
                sorted(User.objects.values_list("username", "is_active")),
                sorted(Membership.objects.values_list("user__username", "organization__slug", "is_active")),
                django_apps.get_model("audit", "AuditLog").objects.count(),
            )

    def _active(self, user):
        with bypass_rls():
            return Membership.objects.filter(user=user, organization=self.org, is_active=True).exists()

    def test_org_is_required(self):
        with self.assertRaises(CommandError):
            call_command("retire_qa_accounts", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("retire_qa_accounts", "--org", "nope", stdout=StringIO())

    def test_dry_run_changes_nothing_and_lists_only_qa(self):
        before = self._snapshot()
        out = _run("--org", self.org.slug)
        self.assertEqual(self._snapshot(), before)
        self.assertIn("DRY-RUN", out)
        for name in ("qa.dean", "qa.teacher", "qa.sec.member"):
            self.assertIn(name, out)
        for name in ("real.dean", "qa.real.person", "qaone"):
            self.assertNotIn(name, out)

    def test_apply_deactivates_only_qa_accounts_and_writes_audit(self):
        out = _run("--org", self.org.slug, "--apply")
        self.assertIn("paket=qa-retire-", out)
        for user in (self.qa_dean, self.qa_teacher):
            user.refresh_from_db()
            self.assertFalse(user.is_active)
            self.assertFalse(self._active(user))
        for user in (self.real_dean, self.qa_lookalike, self.qa_mail_only):
            user.refresh_from_db()
            self.assertTrue(user.is_active)
            self.assertTrue(self._active(user))
        # Başqa təşkilatda aktiv üzvlüyü olan hesab: bu təşkilatdan çıxır, istifadəçi aktiv qalır.
        self.shared.refresh_from_db()
        self.assertTrue(self.shared.is_active)
        self.assertFalse(self._active(self.shared))
        # Silinmir.
        self.assertTrue(User.objects.filter(username="qa.dean").exists())
        with bypass_rls():
            self.assertTrue(Membership.objects.filter(user=self.qa_dean, organization=self.org).exists())
            logs = django_apps.get_model("audit", "AuditLog").objects.filter(
                reason__startswith="QA test hesabı prod-dan"
            )
            self.assertEqual(logs.count(), 3)
            self.assertIn("sahib 2026-10-14", logs.first().reason)
        # İkinci qaçış: artıq çıxarılıb.
        self.assertIn("Çıxarılacaq QA hesabı yoxdur", _run("--org", self.org.slug, "--apply"))

    def test_undo_restores_the_batch(self):
        _run("--org", self.org.slug, "--apply")
        out = _run("--org", self.org.slug, "--undo")
        self.assertIn("GERİ QAYTARILDI: 3", out)
        for user in (self.qa_dean, self.qa_teacher, self.shared):
            user.refresh_from_db()
            self.assertTrue(user.is_active)
            self.assertTrue(self._active(user))
        with bypass_rls():
            restored = django_apps.get_model("audit", "AuditLog").objects.filter(
                reason__startswith="QA test hesabı bərpa"
            )
            self.assertEqual(restored.count(), 3)
        # Eyni paket ikinci dəfə geri qaytarılmır.
        with self.assertRaises(CommandError):
            _run("--org", self.org.slug, "--undo")
