"""``create_quiz_test_accounts_20261120`` (sahib 2026-11-20): quiz üçün 30 müvəqqəti test tələbə hesabı.

Dry-run heç nə yazmır; apply 30 hesab + ``TestQrup`` (30 ``enrolled`` qeyd) yaradır, parol ``12345678``, ilk-giriş /
e-poçt / profil tamamlama qapısı yoxdur, tələbə portalından girib «TestQrup»-a təyin olunmuş quizi görür və başlaya
bilir; təkrar apply dublikat yaratmır və bloku açır; başqasının ``testuserN`` hesabı varsa heç nə yazılmır; ``--undo``
yalnız bu əmrin yaratdıqlarını silir.
"""

from __future__ import annotations

import io
from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts import profile_completion
from apps.accounts import quiz_test_accounts as spec
from apps.accounts.models import UserProfile
from apps.accounts.services.username_change import UsernameChangeError, validate_username
from apps.exams.models import Exam, ExamAttempt
from apps.organizations.models import Membership, Organization, OrgUnit
from apps.registrar.models import Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
CMD = "create_quiz_test_accounts_20261120"


def run(*args) -> str:
    out = io.StringIO()
    with bypass_rls():
        call_command(CMD, "--org", "qtest-univ", "--actor", "qtest_admin", *args, stdout=out)
    return out.getvalue()


class QuizTestAccountsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("qtest_admin", "qtest_admin@example.test", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="QTest Univ",
                slug="qtest-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.admin,
                status="active",
                is_active=True,
            )
            cls.other = User.objects.create_user("qtest.real", "qtest.real@example.test", "pw")
            Membership.objects.create(
                user=cls.other, organization=cls.org, role=cls.org.roles.get(name="student"), is_active=True
            )

    def _group(self):
        with bypass_rls():
            return OrgUnit.objects.filter(
                organization=self.org, unit_type=OrgUnitType.GROUP, name=spec.GROUP_NAME
            ).first()

    def _users(self):
        with bypass_rls():
            return list(User.objects.filter(username__in=spec.USERNAMES).order_by("pk"))

    def _quiz(self, group):
        with bypass_rls():
            exam = Exam.objects.create(
                title="Quiz",
                author=self.admin,
                organization=self.org,
                exam_type="test",
                exam_type_extended="quiz",
                is_active=True,
                is_public=False,
                start_datetime=timezone.now() - timedelta(hours=1),
                end_datetime=timezone.now() + timedelta(days=1),
            )
            exam.allowed_units.add(group)
        return exam

    def test_dry_run_writes_nothing(self):
        out = run()
        self.assertIn("quiz_test: mode=dry_run", out)
        self.assertIn("accounts=30", out)
        self.assertIn("users_created=30", out)
        self.assertNotIn(spec.PASSWORD, out)
        self.assertEqual(self._users(), [])
        self.assertIsNone(self._group())
        with bypass_rls():
            self.assertFalse(Program.objects.filter(code=spec.PROGRAM_CODE).exists())

    def test_apply_creates_ready_accounts_in_test_group(self):
        out = run("--apply")
        self.assertIn("quiz_test: mode=apply", out)
        self.assertIn("group_students=30", out)
        self.assertRegex(out, r"quiz_test: batch=quiztest-\d{8}-\d{6}-[0-9a-f]{4}")
        self.assertNotIn(spec.PASSWORD, out)
        users = self._users()
        self.assertEqual([u.username for u in sorted(users, key=lambda u: int(u.username[8:]))], list(spec.USERNAMES))
        group = self._group()
        self.assertIsNotNone(group)
        with bypass_rls():
            self.assertEqual(
                StudentAcademicRecord.objects.filter(group=group, status="enrolled", is_active=True).count(), 30
            )
            student_role = self.org.roles.get(name="student")
            for user in users:
                self.assertTrue(user.check_password(spec.PASSWORD))
                self.assertTrue(user.is_active)
                self.assertEqual((user.first_name, user.last_name), ("Test", spec.last_name_for(user.username)))
                profile = UserProfile.objects.get(user=user)
                self.assertFalse(profile.password_change_required)
                self.assertTrue(profile.email_verified)
                self.assertEqual(profile.access_state, "active")
                self.assertIn(profile.fin, (None, ""))
                self.assertTrue(
                    Membership.objects.filter(
                        user=user, organization=self.org, role=student_role, is_active=True
                    ).exists()
                )
                user.profile = profile
                self.assertTrue(profile_completion.is_exempt_user(user))
        self.assertEqual(authenticate(username="testuser7", password=spec.PASSWORD).username, "testuser7")

    @override_settings(PROFILE_COMPLETION_ENABLED=True)
    def test_student_logs_in_and_can_take_quiz(self):
        run("--apply")
        client = Client()
        response = client.post(reverse("accounts:student_login"), {"username": "testuser12", "password": spec.PASSWORD})
        self.assertEqual(response.status_code, 302, getattr(response, "context_data", None))
        # Nə ilk-giriş (parol + OTP), nə də məcburi profil məlumatları (FİN / telefon / e-poçt) qapısı yoxdur.
        for params in ({}, {"section": "assigned-exams"}):
            response = client.get(reverse("accounts:profile"), params)
            self.assertEqual(response.status_code, 200, response.get("Location", ""))
        user = User.objects.get(username="testuser12")
        exam = self._quiz(self._group())
        with bypass_rls():
            self.assertTrue(exam.can_user_see(user))
            ok, reason = exam.can_user_start(user)
            self.assertTrue(ok, reason)
            self.assertFalse(exam.can_user_see(self.other))

    def test_reapply_is_idempotent_and_unblocks(self):
        run("--apply")
        with bypass_rls():
            user = User.objects.get(username="testuser3")
            user.set_password("changed-pw-1")
            user.is_active = False
            user.save()
            UserProfile.objects.filter(user=user).update(password_change_required=True, email_verified=False)
        out = run("--apply")
        self.assertNotIn("users_created=", out)
        self.assertIn("users_existing=30", out)
        self.assertIn("passwords_reset=1", out)
        self.assertIn("users_unblocked=1", out)
        self.assertIn("first_login_cleared=1", out)
        self.assertEqual(len(self._users()), 30)
        with bypass_rls():
            self.assertEqual(OrgUnit.objects.filter(organization=self.org, name=spec.GROUP_NAME).count(), 1)
            self.assertEqual(StudentAcademicRecord.objects.filter(group=self._group()).count(), 30)
            user.refresh_from_db()
            self.assertTrue(user.is_active)
            self.assertTrue(user.check_password(spec.PASSWORD))
            self.assertFalse(UserProfile.objects.get(user=user).password_change_required)

    def test_foreign_testuser_account_blocks_apply(self):
        with bypass_rls():
            User.objects.create_user("testuser5", "real.person@example.test", "pw")
        with self.assertRaisesMessage(CommandError, "username_taken_by_other_account"):
            run("--apply")
        self.assertIsNone(self._group())
        self.assertEqual([u.username for u in self._users()], ["testuser5"])

    def test_undo_removes_everything_created_and_nothing_else(self):
        run("--apply")
        group = self._group()
        exam = self._quiz(group)
        with bypass_rls():
            ExamAttempt.objects.create(exam=exam, user=User.objects.get(username="testuser1"))
        preview = run("--undo")
        self.assertIn("quiz_test: mode=undo_dry_run", preview)
        self.assertEqual(len(self._users()), 30)
        out = run("--undo", "--apply")
        self.assertIn("quiz_test: mode=undo_apply", out)
        self.assertIn("users_deleted=30", out)
        self.assertIn("group_deleted=1", out)
        self.assertIn("program_deleted=1", out)
        self.assertEqual(self._users(), [])
        self.assertIsNone(self._group())
        with bypass_rls():
            self.assertFalse(Program.objects.filter(code=spec.PROGRAM_CODE).exists())
            self.assertTrue(User.objects.filter(pk=self.other.pk, is_active=True).exists())
            self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())
            self.assertTrue(Membership.objects.filter(user=self.other, is_active=True).exists())
            self.assertTrue(Exam.objects.filter(pk=exam.pk).exists())

    def test_undo_refuses_account_not_created_by_command(self):
        with bypass_rls():
            lookalike = User.objects.create_user("testuser9", spec.email_for("testuser9"), "pw")
        out = run("--undo", "--apply")
        self.assertIn("skipped_not_created_by_command=1", out)
        self.assertIn("users_deleted=0", out)
        with bypass_rls():
            self.assertTrue(User.objects.filter(pk=lookalike.pk).exists())

    def test_testuser_names_are_reserved_for_self_service_rename(self):
        for value in ("testuser", "testuser5", "testuser31"):
            with self.assertRaises(UsernameChangeError):
                validate_username(value)
