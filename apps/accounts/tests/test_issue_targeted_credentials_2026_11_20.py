"""``issue_staff_credentials --target-users`` — dəqiq siyahı üzrə ilkin parol (sahib 2026-11-20)."""

from __future__ import annotations

import csv
import io
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.organizations.models import Membership, Organization, OrgUnit
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class IssueTargetedCredentialsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("itc_owner", "itc@itc.test", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="ITC", slug="itc-org", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
            )
            unit = OrgUnit.objects.create
            fac = unit(organization=cls.org, name="İqtisadiyyat", slug="itc-f", unit_type=OrgUnitType.FACULTY)
            group = unit(organization=cls.org, name="2536 Bİ", slug="itc-g", unit_type=OrgUnitType.GROUP, parent=fac)
            program = Program.objects.create(organization=cls.org, code="IQ", name="İqtisadiyyat")
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2025)
            student_role = cls.org.roles.get(name="student")

            def student(username, *, activated=False, active=True):
                user = User.objects.create_user(username, f"{username}@itc.test", "old-pass", last_name=username)
                Membership.objects.create(user=user, organization=cls.org, role=student_role, is_active=True)
                StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=user,
                    program=program,
                    curriculum=curriculum,
                    group=group,
                    admission_year=2025,
                    status="enrolled",
                )
                profile = user.profile
                profile.email_verified = activated
                profile.password_change_required = not activated
                profile.save(update_fields=["email_verified", "password_change_required", "updated_at"])
                if not active:
                    User.objects.filter(pk=user.pk).update(is_active=False)
                return user

            cls.pending = student("itc.pending")
            cls.by_name = student("itc.byname")
            cls.activated = student("itc.activated", activated=True)
            cls.inactive = student("itc.inactive", active=False)
            cls.untouched = student("itc.untouched")

    def _run(self, *, apply=False):
        tmp = Path(tempfile.mkdtemp())
        targets = tmp / "targets.txt"
        targets.write_text(
            f"# siyahı\n{self.pending.pk}\nITC.BYNAME\n{self.activated.pk}\n{self.inactive.pk}\n999999999\n"
            f"{self.pending.pk}\n",
            encoding="utf-8",
        )
        report, creds = tmp / "report.csv", tmp / "creds.csv"
        kwargs = {"target_users": str(targets), "report_out": str(report)}
        if apply:
            kwargs.update(
                apply=True,
                credentials_out=str(creds),
                reason="Dəqiq siyahı üzrə ilkin parol — sınaq",
                i_know_this_is_production=True,
            )
        out = io.StringIO()
        call_command("issue_staff_credentials", "--org", "itc-org", stdout=out, **kwargs)
        rows = {r["username"]: r for r in csv.DictReader(report.open(encoding="utf-8"))}
        issued = {r["username"]: r for r in csv.DictReader(creds.open(encoding="utf-8"))} if creds.exists() else {}
        return out.getvalue(), rows, issued

    def test_dry_run_reports_only_listed_accounts_without_writing(self):
        before = User.objects.get(pk=self.pending.pk).password
        out, rows, issued = self._run()
        self.assertEqual(set(rows), {"itc.pending", "itc.byname", "itc.activated", "itc.inactive"})
        self.assertEqual(rows["itc.pending"]["emel"], "yeni ilkin parol veriləcək")
        self.assertEqual(rows["itc.pending"]["qrup_vezife"], "2536 Bİ")
        self.assertIn("parol verilmir", rows["itc.activated"]["emel"])
        self.assertIn("parol verilmir", rows["itc.inactive"]["emel"])
        self.assertNotIn("ilkin_parol", next(iter(rows.values())))
        self.assertIn("requested=5 found=4 not_found=1", out)
        self.assertIn("new_targets=2 issued=0 mode=DRY-RUN", out)
        self.assertNotIn("itc.", out)
        self.assertEqual(issued, {})
        self.assertEqual(User.objects.get(pk=self.pending.pk).password, before)

    def test_apply_issues_server_passwords_only_to_pending_listed_accounts(self):
        activated_hash = User.objects.get(pk=self.activated.pk).password
        untouched_hash = User.objects.get(pk=self.untouched.pk).password
        out, rows, issued = self._run(apply=True)
        self.assertEqual(set(issued), {"itc.pending", "itc.byname"})
        for username, row in issued.items():
            user = User.objects.select_related("profile").get(username=username)
            self.assertTrue(check_password(row["ilkin_parol"], user.password))
            self.assertTrue(user.profile.password_change_required)
            self.assertFalse(user.profile.email_verified)
            self.assertEqual(rows[username]["emel"], "yeni ilkin parol verildi")
            self.assertNotIn(row["ilkin_parol"], out)
        self.assertEqual(User.objects.get(pk=self.activated.pk).password, activated_hash)
        self.assertEqual(User.objects.get(pk=self.untouched.pk).password, untouched_hash)
        self.assertIn("issued=2 mode=APPLY", out)

    def test_empty_target_file_is_refused(self):
        empty = Path(tempfile.mkdtemp()) / "empty.txt"
        empty.write_text("# yalnız şərh\n\n", encoding="utf-8")
        with self.assertRaises(CommandError):
            call_command("issue_staff_credentials", "--org", "itc-org", "--target-users", str(empty))
