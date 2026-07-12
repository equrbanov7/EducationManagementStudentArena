"""Təhlükəsizlik hadisələri: siqnallar, dedup, brute-force nümunəsi."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.monitoring.models import SecurityEvent
from apps.monitoring.security import BRUTE_FORCE_THRESHOLD, record_security_event

User = get_user_model()


LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=LOCMEM_CACHE)
class SecurityEventTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_failed_login_creates_event(self):
        Client().post(reverse("accounts:staff_login"), {"username": "yoxdur_bele_user", "password": "yanlis"})
        self.assertTrue(
            SecurityEvent.objects.filter(event_type="login_failed", username_hint="yoxdur_bele_user").exists()
        )

    def test_dedup_increments_count_instead_of_new_rows(self):
        record_security_event(event_type="login_failed", username_hint="tekrar", ip_address="10.0.0.9")
        record_security_event(event_type="login_failed", username_hint="tekrar", ip_address="10.0.0.9")
        record_security_event(event_type="login_failed", username_hint="tekrar", ip_address="10.0.0.9")
        events = SecurityEvent.objects.filter(event_type="login_failed", username_hint="tekrar")
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.get().count, 3)

    def test_superadmin_target_flagged_high(self):
        User.objects.create_superuser("super_hedef", "super_hedef@test.az", "Pass123!x")
        Client().post(reverse("accounts:staff_login"), {"username": "super_hedef", "password": "yanlis"})
        self.assertTrue(
            SecurityEvent.objects.filter(
                event_type="superadmin_login_failed", username_hint="super_hedef", severity="high"
            ).exists()
        )

    def test_brute_force_pattern_detected(self):
        client = Client()
        for i in range(BRUTE_FORCE_THRESHOLD + 1):
            client.post(
                reverse("accounts:staff_login"),
                {"username": f"bf_user_{i}", "password": "yanlis"},
                REMOTE_ADDR="10.9.9.9",
            )
        self.assertTrue(SecurityEvent.objects.filter(event_type="login_brute_force", ip_address="10.9.9.9").exists())

    def test_no_sensitive_data_in_event(self):
        Client().post(reverse("accounts:staff_login"), {"username": "hersey_temiz", "password": "SUPERGIZLI!"})
        event = SecurityEvent.objects.filter(username_hint="hersey_temiz").get()
        blob = str(event.request_info) + event.message
        self.assertNotIn("SUPERGIZLI", blob)
