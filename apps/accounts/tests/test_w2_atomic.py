"""Dalğa 2 (2026-09-14) — audit 2026-09-13 backend F-07: çoxyazılı view-lər
``transaction.atomic`` içindədir — ikinci yazı sınanda birinci geri alınır.

* parol bərpası (`password_reset_done`): parol + OTP «istifadə olundu» birlikdə;
* təşkilata müraciət (`student_organization_request`): müraciət sətri + profil;
* icazə redaktoru (`permission_editor`): rol icazələri + audit qeydi.
"""

from __future__ import annotations

import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import EmailOTP, ProfileRole
from apps.audit.models import AuditLog
from apps.notifications.models import StudentOrganizationRequest
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()
PW = "W2AtomicPass123!"


def _org(name, slug, owner, org_type=OrganizationType.UNIVERSITY):
    return Organization.objects.create(
        name=name, slug=slug, org_type=org_type, owner=owner, status="active", is_active=True
    )


class PasswordResetDoneAtomicTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("w2pr_owner", "w2pr_owner@example.com", PW)
        self.organization = _org("W2 Reset Univ", "w2-reset-univ", self.owner)
        self.user = User.objects.create_user("w2pr_user", "w2pr_user@example.com", "Old-Pass-2026!")
        profile = self.user.profile
        profile.organization = self.organization
        profile.save(update_fields=["organization"])

    def _request_code(self):
        self.assertEqual(
            self.client.post(reverse("accounts:password_reset"), {"email": self.user.email}).status_code, 302
        )
        otp = EmailOTP.objects.filter(user=self.user, purpose=EmailOTP.Purpose.PASSWORD_RESET).latest("created_at")
        code = getattr(otp, "_plain_code", None) or re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        return otp, code

    def _done(self, code):
        return self.client.post(
            reverse("accounts:password_reset_done"),
            {
                "email": self.user.email,
                "otp_code": code,
                "new_password1": "New-Pass-2026!",
                "new_password2": "New-Pass-2026!",
            },
        )

    def test_otp_mark_failure_rolls_back_the_new_password(self):
        otp, code = self._request_code()
        with mock.patch.object(EmailOTP, "save", side_effect=RuntimeError("otp boom")):
            with self.assertRaises(RuntimeError):
                self._done(code)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Old-Pass-2026!"))
        otp.refresh_from_db()
        self.assertFalse(otp.is_used)

    def test_happy_path_writes_password_and_marks_otp(self):
        otp, code = self._request_code()
        self.assertEqual(self._done(code).status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New-Pass-2026!"))
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)


class StudentOrganizationRequestAtomicTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("w2req_owner", "w2req_owner@example.com", PW)
        self.org = _org("W2 Request Org", "w2-request-org", self.owner, OrganizationType.SCHOOL)
        self.student = User.objects.create_user("w2req_student", "w2req_student@example.com", PW)
        profile = self.student.profile
        profile.role = ProfileRole.STUDENT
        profile.organization = None
        profile.organization_type = OrganizationType.INDIVIDUAL
        profile.save(update_fields=["role", "organization", "organization_type", "updated_at"])
        self.client.force_login(self.student)

    def _submit(self):
        return self.client.post(
            reverse("accounts:student_organization_request"),
            {"action": "submit_request", "organization_id": str(self.org.id), "request_message": "Salam"},
        )

    def test_profile_save_failure_rolls_back_the_request_row(self):
        from apps.accounts.models import UserProfile

        with mock.patch.object(UserProfile, "save", side_effect=RuntimeError("profile boom")):
            with self.assertRaises(RuntimeError):
                self._submit()
        with bypass_rls():
            self.assertFalse(
                StudentOrganizationRequest.objects.filter(user=self.student, organization=self.org).exists()
            )
        self.student.profile.refresh_from_db()
        self.assertIsNone(self.student.profile.requested_organization_id)

    def test_happy_path_writes_request_and_profile(self):
        self.assertEqual(self._submit().status_code, 302)
        with bypass_rls():
            self.assertTrue(
                StudentOrganizationRequest.objects.filter(user=self.student, organization=self.org).exists()
            )
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.requested_organization_id, self.org.id)


class PermissionEditorAtomicTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("w2pe_owner", "w2pe_owner@example.com", PW)
        with bypass_rls():
            self.org = _org("W2 Editor Univ", "w2-editor-univ", self.owner)
            self.rim = User.objects.create_user("w2pe_rim", "w2pe_rim@example.com", PW)
            Membership.objects.create(
                user=self.rim, organization=self.org, role=self.org.roles.get(name="ikt_rehber"), is_primary=True
            )
            self.teacher_role = Role.objects.get(organization=self.org, name="teacher")
        self.client = Client()
        self.client.force_login(self.rim)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _add(self, permission="schedule.view"):
        return self.client.post(
            reverse("accounts:permission_editor"),
            {"role_id": str(self.teacher_role.id), "action": "add", "permission": permission},
        )

    def test_audit_failure_rolls_back_the_permission_change(self):
        with mock.patch.object(AuditLog.objects, "create", side_effect=RuntimeError("audit boom")):
            with self.assertRaises(RuntimeError):
                self._add()
        with bypass_rls():
            self.teacher_role.refresh_from_db()
        self.assertNotIn("schedule.view", self.teacher_role.permissions)

    def test_happy_path_writes_both_rows(self):
        self.assertEqual(self._add().status_code, 302)
        with bypass_rls():
            self.teacher_role.refresh_from_db()
            self.assertIn("schedule.view", self.teacher_role.permissions)
            self.assertTrue(
                AuditLog.objects.filter(resource_type="role", resource_id=str(self.teacher_role.id)).exists()
            )
