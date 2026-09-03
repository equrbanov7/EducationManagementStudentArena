"""STAGED (import-pending) hesab + audience-gated login formaları.

``test_account_archive.py`` eyni HTTP-səviyyəli yoxlamanı ARCHIVED hesab üçün
edir (``test_an_archived_account_cannot_use_the_staff_portal`` /
``..._student_portal``), amma STAGED hesab üçün ekvivalent yoxlama yox idi —
yalnız ``authenticate()``-in birbaşa çağırışı test olunurdu
(``test_identity_access.py::test_staged_account_cannot_password_or_otp_login``).
Bu fayl həmin boşluğu bağlayır: STAGED hesab, ``EmailOrUsernameBackend`` və
``is_active=False`` səbəbindən, HƏR İKİ audience-gated login formasından (tələbə
VƏ əməkdaş) düzgün parolla belə keçə bilməməlidir, forma 200 (yenidən göstərilir)
qaytarmalı və sessiya açılmamalıdır.
"""

from django.contrib.auth import authenticate, get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.identity import user_access_is_login_blocked, user_access_is_staged
from apps.accounts.models import UserProfile
from apps.accounts.services import stage_imported_account
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()

PASSWORD = "Staged-Portal-Password-123!"


class StagedAccountPortalLoginTests(TestCase):
    """STAGED (idxal, hələ aktivləşdirilməmiş) hesab heç bir portaldan keçmir."""

    def setUp(self):
        self.actor = User.objects.create_superuser(
            username="staged_portal_root",
            email="staged-portal-root@example.com",
            password="Root-Password-123!",
        )
        self.organization = Organization.objects.create(
            name="Staged Portal University",
            slug="staged-portal-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.actor,
            status="active",
            is_active=True,
        )
        self.student_role = self.organization.roles.get(name="student")
        self.teacher_role = self.organization.roles.get(name="teacher")

    def _stage(self, *, username, email, identifier, role=None):
        user = stage_imported_account(
            organization=self.organization,
            role=role or self.student_role,
            actor=self.actor,
            username=username,
            email=email,
            student_identifier=identifier,
        ).user
        # Legacy import: unusable password olsa da, HTTP-səviyyəli formanın
        # doğru parolla belə keçmədiyini sübut etmək üçün bilinən parol qoyuruq.
        user.set_password(PASSWORD)
        user.save(update_fields=["password"])
        return user

    def test_staged_account_is_the_correct_access_state(self):
        staged = self._stage(
            username="staged_portal_student_1",
            email="staged.portal.student.1@example.com",
            identifier="STG-1",
        )
        self.assertEqual(staged.profile.access_state, UserProfile.AccessState.STAGED)
        self.assertFalse(staged.is_active)
        self.assertTrue(user_access_is_staged(staged))
        self.assertTrue(user_access_is_login_blocked(staged))
        self.assertIsNone(authenticate(username=staged.username, password=PASSWORD))

    def test_a_staged_student_cannot_use_the_student_portal(self):
        staged = self._stage(
            username="staged_portal_student_2",
            email="staged.portal.student.2@example.com",
            identifier="STG-2",
        )
        client = Client()
        response = client.post(
            reverse("accounts:student_login"),
            {"username": staged.username, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200)  # forma yenidən göstərilir, login OLMUR
        self.assertNotIn("_auth_user_id", client.session)

    def test_a_staged_student_cannot_use_the_staff_portal_either(self):
        staged = self._stage(
            username="staged_portal_student_3",
            email="staged.portal.student.3@example.com",
            identifier="STG-3",
        )
        client = Client()
        response = client.post(
            reverse("accounts:staff_login"),
            {"username": staged.username, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", client.session)

    def test_a_staged_worker_cannot_use_the_staff_portal(self):
        staged = self._stage(
            username="staged_portal_teacher_1",
            email="staged.portal.teacher.1@example.com",
            identifier="STG-T1",
            role=self.teacher_role,
        )
        client = Client()
        response = client.post(
            reverse("accounts:staff_login"),
            {"username": staged.username, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", client.session)

    def test_login_by_email_is_blocked_the_same_way_as_by_username(self):
        staged = self._stage(
            username="staged_portal_student_4",
            email="staged.portal.student.4@example.com",
            identifier="STG-4",
        )
        client = Client()
        response = client.post(
            reverse("accounts:student_login"),
            {"username": staged.email, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", client.session)

    def test_unknown_username_and_staged_username_are_indistinguishable_by_status_code(self):
        """Enumeration observation: both a real STAGED user and a fictitious
        username return the same 200-with-form-error shape (no 404/differing
        latency-sensitive branch), so the login form itself does not leak
        which usernames exist."""
        staged = self._stage(
            username="staged_portal_student_5",
            email="staged.portal.student.5@example.com",
            identifier="STG-5",
        )
        client = Client()
        staged_response = client.post(
            reverse("accounts:student_login"),
            {"username": staged.username, "password": "whatever-wrong"},
        )
        unknown_response = client.post(
            reverse("accounts:student_login"),
            {"username": "no-such-user-at-all", "password": "whatever-wrong"},
        )
        self.assertEqual(staged_response.status_code, unknown_response.status_code)
