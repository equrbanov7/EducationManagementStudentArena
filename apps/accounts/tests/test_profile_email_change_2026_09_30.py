"""2026-09-30 — kabinetdə e-poçtu dəyişmək (mobil də daxil) və «təsdiqli e-poçt» bayrağı.

E-poçt dəyişəndə ``email_verified`` sıfırlanır (RİM redaktəsi ilə eyni qayda): operator parolu
sıfırlayanda yeni ünvan ilk girişdə OTP ilə təsdiqlənir. E-poçt eyni qalanda bayraq toxunulmur.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class ProfileEmailChangeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "email.change", "kohne@example.com", "StrongPass123!", first_name="Aysel", last_name="Quliyeva"
        )
        profile = self.user.profile
        profile.email_verified = True
        profile.save(update_fields=["email_verified", "updated_at"])
        self.client.force_login(self.user)

    def _post(self, email):
        return self.client.post(
            reverse("accounts:profile"),
            {"profile_form": "edit-profile", "email": email, "first_name": "Aysel", "last_name": "Quliyeva"},
        )

    def test_changed_email_is_saved_and_needs_verification_again(self):
        response = self._post("Yeni.Unvan@Gmail.com")

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "yeni.unvan@gmail.com")
        self.assertFalse(self.user.profile.email_verified)

    def test_same_email_keeps_verified_flag(self):
        self._post("KOHNE@example.com")

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "kohne@example.com")
        self.assertTrue(self.user.profile.email_verified)

    def test_email_field_is_mobile_friendly(self):
        page = self.client.get(reverse("accounts:profile") + "?section=edit-profile")

        self.assertContains(page, 'inputmode="email"')
        self.assertContains(page, 'autocapitalize="none"')
