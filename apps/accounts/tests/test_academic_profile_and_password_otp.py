"""«Akademik fəaliyyət» qeydləri (academic_items_api) və şifrə-dəyişmə OTP
axını (change_password_otp_request + change-password-otp POST) testləri.

2026-08-15 profil redizaynı: bax _edit_profile.html / _change_password.html.
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import AcademicProfileItem, EmailOTP
from apps.accounts.services import issue_email_otp
from core.roles import ProfileRole

User = get_user_model()


def _make_user(username, role):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass123",
    )
    profile = user.profile
    profile.role = role
    profile.save(update_fields=["role", "updated_at"])
    return user


class AcademicItemsApiTest(TestCase):
    def setUp(self):
        self.teacher = _make_user("akademik_teacher", ProfileRole.TEACHER)
        self.student = _make_user("akademik_student", ProfileRole.STUDENT)
        self.url = reverse("accounts:academic_items_api")

    def _post(self, user, **data):
        self.client.force_login(user)
        return self.client.post(self.url, data=data)

    def test_requires_login(self):
        response = self.client.post(self.url, data={"action": "create"})
        self.assertEqual(response.status_code, 302)

    def test_teacher_creates_subject_item(self):
        response = self._post(
            self.teacher,
            action="create",
            kind="subject",
            title="Verilənlər bazası sistemləri",
            detail="Kompüter elmləri kafedrası",
            year="2026",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn("Verilənlər bazası sistemləri", payload["html"])
        item = self.teacher.academic_items.get()
        self.assertEqual(item.kind, AcademicProfileItem.Kind.SUBJECT)
        self.assertEqual(item.year, 2026)

    def test_student_cannot_create_subject_item(self):
        response = self._post(self.student, action="create", kind="subject", title="Fizika")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(self.student.academic_items.count(), 0)

    def test_student_creates_certificate(self):
        response = self._post(
            self.student,
            action="create",
            kind="certificate",
            title="IELTS 7.5",
            link="https://example.com/cert",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(self.student.academic_items.get().kind, AcademicProfileItem.Kind.CERTIFICATE)

    def test_invalid_link_scheme_rejected(self):
        response = self._post(
            self.teacher,
            action="create",
            kind="publication",
            title="Məqalə",
            link="javascript:alert(1)",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.teacher.academic_items.count(), 0)

    def test_invalid_year_rejected(self):
        response = self._post(self.teacher, action="create", kind="publication", title="Məqalə", year="1800")
        self.assertEqual(response.status_code, 400)

    def test_update_only_own_items(self):
        item = AcademicProfileItem.objects.create(
            user=self.teacher, kind=AcademicProfileItem.Kind.PUBLICATION, title="Orijinal"
        )
        response = self._post(
            self.student,
            action="update",
            item_id=str(item.pk),
            kind="publication",
            title="Oğurlanmış",
        )
        self.assertEqual(response.status_code, 404)
        item.refresh_from_db()
        self.assertEqual(item.title, "Orijinal")

    def test_owner_updates_and_deletes(self):
        item = AcademicProfileItem.objects.create(
            user=self.teacher, kind=AcademicProfileItem.Kind.CONFERENCE, title="Köhnə ad"
        )
        response = self._post(
            self.teacher,
            action="update",
            item_id=str(item.pk),
            kind="conference",
            title="Yeni ad",
            year="2025",
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.title, "Yeni ad")
        self.assertEqual(item.year, 2025)

        response = self._post(self.teacher, action="delete", item_id=str(item.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.teacher.academic_items.count(), 0)


class ChangePasswordOtpTest(TestCase):
    def setUp(self):
        self.user = _make_user("otp_teacher", ProfileRole.TEACHER)
        self.request_url = reverse("accounts:change_password_otp_request")
        self.profile_url = reverse("accounts:profile")

    def test_request_requires_login(self):
        response = self.client.post(self.request_url)
        self.assertEqual(response.status_code, 302)

    def test_request_sends_email_and_cooldown_applies(self):
        self.client.force_login(self.user)
        response = self.client.post(self.request_url)
        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn("***", payload["detail"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user.email, mail.outbox[0].to)

        # Dərhal ikinci sorğu resend cooldown-a düşməlidir.
        response = self.client.post(self.request_url)
        self.assertEqual(response.status_code, 429)
        self.assertFalse(response.json()["success"])

    def test_change_password_with_valid_otp(self):
        code, _expires_at, _record = issue_email_otp(
            self.user, email=self.user.email, purpose=EmailOTP.Purpose.PASSWORD_RESET
        )
        self.client.force_login(self.user)
        response = self.client.post(
            f"{self.profile_url}?section=change-password",
            data={
                "profile_form": "change-password-otp",
                "section": "change-password",
                "otp_code": code,
                "new_password1": "YeniSifre#2026",
                "new_password2": "YeniSifre#2026",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("section=change-password", response.url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("YeniSifre#2026"))
        # Sessiya update_session_auth_hash ilə qorunur — istifadəçi çıxarılmır.
        response = self.client.get(f"{self.profile_url}?section=profile-info")
        self.assertEqual(response.status_code, 200)
        # OTP birdəfəlikdir — təkrar istifadə mümkün deyil.
        self.assertFalse(
            EmailOTP.objects.filter(user=self.user, purpose=EmailOTP.Purpose.PASSWORD_RESET, is_used=False).exists()
        )

    def test_change_password_with_wrong_otp_fails(self):
        issue_email_otp(self.user, email=self.user.email, purpose=EmailOTP.Purpose.PASSWORD_RESET)
        self.client.force_login(self.user)
        response = self.client.post(
            f"{self.profile_url}?section=change-password",
            data={
                "profile_form": "change-password-otp",
                "section": "change-password",
                "otp_code": "000000",
                "new_password1": "YeniSifre#2026",
                "new_password2": "YeniSifre#2026",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("testpass123"))


class PublicProfileVisibilityTest(TestCase):
    """Açıq profil: telefon görünürlüyü, önizləmə rejimi, akademik qeydlər."""

    def setUp(self):
        self.teacher = _make_user("pub_teacher", ProfileRole.TEACHER)
        profile = self.teacher.profile
        profile.phone = "+994 50 111 22 33"
        profile.phone_secondary = "+994 55 444 55 66"
        profile.academic_title = "professor"
        profile.save(update_fields=["phone", "phone_secondary", "academic_title", "updated_at"])
        AcademicProfileItem.objects.create(
            user=self.teacher, kind=AcademicProfileItem.Kind.PUBLICATION, title="Konsensus alqoritmləri"
        )
        self.url = reverse("accounts:public_profile", args=[self.teacher.username])

    def test_anonymous_viewer_sees_no_phone_but_sees_academic_items(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "+994 50 111 22 33")
        self.assertNotContains(response, "+994 55 444 55 66")
        self.assertContains(response, "Konsensus alqoritmləri")

    def test_student_viewer_sees_no_phone(self):
        student = _make_user("pub_student_viewer", ProfileRole.STUDENT)
        self.client.force_login(student)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "+994 50 111 22 33")

    def test_same_org_teacher_sees_phones_cross_org_teacher_does_not(self):
        """Telefon gating tenant-scoped-dur: yalnız profil sahibi ilə EYNİ
        təşkilatda müəllim+ aktiv üzvlüyü olan baxan görür."""
        from apps.organizations.models import Organization

        from .test_profile_views import _assign_user_to_org

        org_a = Organization.objects.create(
            name="Gating Org A", org_type="university", owner=self.teacher, status="active", is_active=True
        )
        org_b = Organization.objects.create(
            name="Gating Org B", org_type="university", owner=self.teacher, status="active", is_active=True
        )
        _assign_user_to_org(self.teacher, org_a, ProfileRole.TEACHER)

        same_org_teacher = _make_user("pub_sameorg_teacher", ProfileRole.TEACHER)
        _assign_user_to_org(same_org_teacher, org_a, ProfileRole.TEACHER)
        cross_org_teacher = _make_user("pub_crossorg_teacher", ProfileRole.TEACHER)
        _assign_user_to_org(cross_org_teacher, org_b, ProfileRole.TEACHER)
        same_org_student = _make_user("pub_sameorg_student", ProfileRole.STUDENT)
        _assign_user_to_org(same_org_student, org_a, ProfileRole.STUDENT)

        self.client.force_login(same_org_teacher)
        response = self.client.get(self.url)
        self.assertContains(response, "+994 50 111 22 33")

        self.client.force_login(cross_org_teacher)
        response = self.client.get(self.url)
        self.assertNotContains(response, "+994 50 111 22 33")

        self.client.force_login(same_org_student)
        response = self.client.get(self.url)
        self.assertNotContains(response, "+994 50 111 22 33")

    def test_superadmin_viewer_sees_both_phones(self):
        admin = User.objects.create_superuser(
            username="pub_admin_viewer", email="pub_admin_viewer@example.com", password="testpass123"
        )
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+994 50 111 22 33")
        self.assertContains(response, "+994 55 444 55 66")

    def test_self_view_redirects_but_preview_renders(self):
        self.client.force_login(self.teacher)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

        response = self.client.get(f"{self.url}?preview=1")
        self.assertEqual(response.status_code, 200)
        # Önizləmə banneri + sahibin öz nömrələri görünür.
        self.assertContains(response, "Önizləmə rejimi")
        self.assertContains(response, "+994 50 111 22 33")


class EditProfileSecondPhoneTest(TestCase):
    def test_phone_secondary_saved_from_edit_profile(self):
        user = _make_user("phone2_user", ProfileRole.TEACHER)
        self.client.force_login(user)
        response = self.client.post(
            reverse("accounts:profile") + "?section=edit-profile",
            data={
                "profile_form": "edit-profile",
                "section": "edit-profile",
                "first_name": "Tel",
                "last_name": "Iki",
                "email": "phone2_user@example.com",
                "phone": "+994 50 000 00 01",
                "phone_secondary": "+994 55 000 00 02",
                "bio": "",
                "location": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.phone_secondary, "+994 55 000 00 02")


class AuditTrailTest(TestCase):
    """Qeyd CRUD-u və şifrə dəyişmə audit jurnalına yazılır."""

    def test_academic_item_create_writes_audit_log(self):
        from apps.audit.models import AuditLog

        teacher = _make_user("audit_teacher", ProfileRole.TEACHER)
        self.client.force_login(teacher)
        response = self.client.post(
            reverse("accounts:academic_items_api"),
            data={"action": "create", "kind": "publication", "title": "Audit məqaləsi"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuditLog.objects.filter(user=teacher, resource_type="AcademicProfileItem", action="create").exists()
        )

    def test_otp_password_change_writes_audit_log(self):
        from apps.audit.models import AuditLog

        user = _make_user("audit_otp_user", ProfileRole.TEACHER)
        code, _expires, _rec = issue_email_otp(user, email=user.email, purpose=EmailOTP.Purpose.PASSWORD_RESET)
        self.client.force_login(user)
        response = self.client.post(
            reverse("accounts:profile") + "?section=change-password",
            data={
                "profile_form": "change-password-otp",
                "section": "change-password",
                "otp_code": code,
                "new_password1": "AuditSifre#2026",
                "new_password2": "AuditSifre#2026",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(AuditLog.objects.filter(user=user, resource_type="UserPassword", action="update").exists())
