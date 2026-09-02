"""
`provision_student_credentials` komandası + ilk-giriş axını ilə inteqrasiya testləri.

Ssenari: superadmin bütün tələbələrə default parol verir → tələbə default
parolla girir → middleware onu setup səhifəsinə kilidləyir → yeni email + OTP
+ yeni parol → kilid açılır.
"""

import csv
import io as _io
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

PASSWORD = "StrongPass123!"
DEFAULT_PASSWORD = "Telebe2026!"


def _assign(user, organization, profile_role, membership_role_name):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={
            "role": organization.roles.get(name=membership_role_name),
            "is_primary": True,
            "is_active": True,
        },
    )


class ProvisionCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("pv_owner", "pv_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="PV University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.student1 = User.objects.create_user("pv_student1", "s1@test.az", PASSWORD)
        _assign(cls.student1, cls.org, ProfileRole.STUDENT, "student")
        cls.student2 = User.objects.create_user("pv_student2", "s2@test.az", PASSWORD)
        _assign(cls.student2, cls.org, ProfileRole.STUDENT, "student")
        cls.teacher = User.objects.create_user("pv_teacher", "t@test.az", PASSWORD)
        _assign(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")

    def _run(self, *args):
        out = _io.StringIO()
        call_command("provision_student_credentials", *args, stdout=out)
        return out.getvalue()

    def test_sets_default_password_and_first_login_flag(self):
        output = self._run("--org", self.org.slug, "--password", DEFAULT_PASSWORD)
        self.assertIn("2 tələbəyə", output)

        for student in (self.student1, self.student2):
            student.refresh_from_db()
            self.assertTrue(student.check_password(DEFAULT_PASSWORD))
            self.assertTrue(student.profile.password_change_required)
            self.assertFalse(student.profile.email_verified)

        # Müəllimə toxunulmur.
        self.teacher.refresh_from_db()
        self.assertTrue(self.teacher.check_password(PASSWORD))
        self.assertFalse(self.teacher.profile.password_change_required)

    def test_skips_already_configured_without_force(self):
        profile = self.student1.profile
        profile.email_verified = True
        profile.password_change_required = False
        profile.save(update_fields=["email_verified", "password_change_required", "updated_at"])

        self._run("--org", self.org.slug, "--password", DEFAULT_PASSWORD)
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.check_password(PASSWORD))  # dəyişməyib
        self.student2.refresh_from_db()
        self.assertTrue(self.student2.check_password(DEFAULT_PASSWORD))

    def test_force_resets_configured_accounts(self):
        profile = self.student1.profile
        profile.email_verified = True
        profile.password_change_required = False
        profile.save(update_fields=["email_verified", "password_change_required", "updated_at"])

        self._run("--org", self.org.slug, "--password", DEFAULT_PASSWORD, "--force")
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.check_password(DEFAULT_PASSWORD))
        self.assertTrue(self.student1.profile.password_change_required)

    def test_dry_run_changes_nothing(self):
        output = self._run("--org", self.org.slug, "--password", DEFAULT_PASSWORD, "--dry-run")
        self.assertIn("DRY-RUN", output)
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.check_password(PASSWORD))
        self.assertFalse(self.student1.profile.password_change_required)

    def test_generate_writes_csv_with_unique_passwords(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = str(Path(tmp) / "creds.csv")
            self._run("--org", self.org.slug, "--generate", "--csv", csv_path)

            with open(csv_path, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))

        self.assertEqual(len(rows), 2)
        passwords = {row["password"] for row in rows}
        self.assertEqual(len(passwords), 2)  # hər tələbəyə fərqli parol
        by_username = {row["username"]: row["password"] for row in rows}
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.check_password(by_username["pv_student1"]))

    def test_generate_without_csv_rejected(self):
        with self.assertRaises(CommandError):
            call_command("provision_student_credentials", "--org", self.org.slug, "--generate")

    def test_unknown_org_rejected(self):
        with self.assertRaises(CommandError):
            call_command("provision_student_credentials", "--org", "yoxdur", "--password", "x")

    def test_group_filter_narrows_the_printable_list(self):
        """Parol siyahısı praktikada QRUP-QRUP çap olunur (kurator paylayır)."""
        from apps.organizations.models import OrgUnit
        from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
        from core.constants import OrgUnitType

        group = OrgUnit.objects.create(organization=self.org, name="PV-101", slug="pv-101", unit_type=OrgUnitType.GROUP)
        program = Program.objects.create(organization=self.org, code="PV", name="Proqram")
        curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2024)
        StudentAcademicRecord.objects.create(
            organization=self.org,
            student=self.student1,
            program=program,
            curriculum=curriculum,
            group=group,
            admission_year=2024,
        )

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = str(Path(tmp) / "pv-101.csv")
            self._run("--org", self.org.slug, "--group", "PV-101", "--generate", "--csv", csv_path)
            with open(csv_path, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))

        self.assertEqual([row["username"] for row in rows], ["pv_student1"])
        self.student2.refresh_from_db()
        self.assertTrue(self.student2.check_password(PASSWORD))  # qrupdan kənar tələbəyə toxunulmayıb

    def test_unknown_group_rejected(self):
        with self.assertRaises(CommandError):
            call_command(
                "provision_student_credentials", "--org", self.org.slug, "--group", "yoxdur", "--password", "x"
            )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ProvisionEndToEndTest(TestCase):
    """Default parolla giriş → məcburi setup → OTP → yeni parol → kilid açılır."""

    NEW_PASSWORD = "OzParolum2026!"
    NEW_EMAIL = "yeni.telebe@example.com"

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("pv2_owner", "pv2_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="PV2 University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.student = User.objects.create_user("pv2_student", "old@test.az", PASSWORD)
        _assign(cls.student, cls.org, ProfileRole.STUDENT, "student")

    def test_full_first_login_cycle_after_provisioning(self):
        call_command("provision_student_credentials", "--org", self.org.slug, "--password", DEFAULT_PASSWORD)

        client = Client()
        # 1) Default parolla giriş mümkündür.
        self.assertTrue(client.login(username="pv2_student", password=DEFAULT_PASSWORD))

        # 2) İstənilən səhifə setup səhifəsinə yönləndirilir.
        set_url = reverse("accounts:set_initial_password")
        response = client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], set_url)

        # 3) Yeni email yazır → OTP göndərilir.
        client.post(set_url, {"action": "send_otp", "email": self.NEW_EMAIL})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.NEW_EMAIL, mail.outbox[0].to)

        # 4) Kod + yeni parol → hesab təsdiqlənir, kilid açılır.
        # Kod DB-də hash-lənmiş saxlanır — mövcud test konvensiyası kimi
        # e-poçt mətnindən çıxarırıq.
        import re

        match = re.search(r"\b(\d{6})\b", mail.outbox[-1].body)
        assert match, "OTP kodu e-poçtda tapılmadı"
        client.post(
            set_url,
            {
                "action": "set_password",
                "code": match.group(1),
                "password1": self.NEW_PASSWORD,
                "password2": self.NEW_PASSWORD,
            },
        )

        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(self.NEW_PASSWORD))
        self.assertEqual(self.student.email, self.NEW_EMAIL)
        self.assertTrue(self.student.profile.email_verified)
        self.assertFalse(self.student.profile.password_change_required)

        # 5) Artıq sərbəst gəzə bilir.
        response = client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
