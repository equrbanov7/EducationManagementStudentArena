"""Təhlükəsizlik auditi 2026-10-07, AUTH-01 — şəbəkə zonası qapısı view-as altında ƏSL istifadəçini yoxlayır.

``ViewAsMiddleware`` ``request.user``-i hədəflə əvəz edir; qapı ``request.user``-ə baxdığı üçün
daxildə başladılmış view-as sessiyası (superadmin və ya inzibati aktor) kənar zonadan işləyirdi.
"""

from django.test import override_settings
from django.urls import reverse

from .test_network_zone import ZONE
from .test_view_as import ViewAsTestBase

EXT = "85.132.1.1"
INT = "10.0.2.50"


# ── AUTH-01 ─────────────────────────────────────────────────────────────────


class SuperadminViewAsZoneTest(ViewAsTestBase):
    @override_settings(**ZONE)
    def test_superadmin_view_as_session_is_ended_outside(self):
        self.client.force_login(self.superadmin)
        start = self.client.post(
            reverse("accounts:view_as_start"),
            {"user_id": self.teacher.pk, "org": self.org.pk},
            REMOTE_ADDR=INT,
        )
        self.assertEqual(start.status_code, 302)
        self.assertIn("view_as_state", self.client.session)

        response = self.client.get(reverse("accounts:profile"), REMOTE_ADDR=EXT)

        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "errors/network_zone.html")
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(**ZONE)
    def test_control_superadmin_view_as_keeps_working_inside(self):
        self.client.force_login(self.superadmin)
        self.client.post(
            reverse("accounts:view_as_start"),
            {"user_id": self.teacher.pk, "org": self.org.pk},
            REMOTE_ADDR=INT,
        )
        response = self.client.get(reverse("accounts:profile"), REMOTE_ADDR=INT)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["user"].pk, self.teacher.pk)

    @override_settings(**ZONE, NETWORK_ZONE_STAFF_INTERNAL_ONLY=True)
    def test_staff_rule_classifies_the_real_actor_not_the_view_as_target(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        start = self.client.post(reverse("accounts:view_as_start"), {"user_id": self.student.pk}, REMOTE_ADDR=INT)
        self.assertEqual(start.status_code, 302)
        self.assertIn("view_as_state", self.client.session)

        response = self.client.get(reverse("accounts:profile"), REMOTE_ADDR=EXT)

        self.assertEqual(response.status_code, 403)
