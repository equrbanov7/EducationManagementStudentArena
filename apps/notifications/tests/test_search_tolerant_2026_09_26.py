"""Bildiriş axtarışı dözümlüdür (sahib 2026-09-26): «Sahzad» → «Şahzad», tokenlər VƏ ilə."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.notifications.models import InAppNotification
from apps.notifications.services import get_user_notifications

User = get_user_model()


class NotificationSearchTolerantTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("notif_tol", "notif_tol@example.com", "TestPass123!")
        self.hit = InAppNotification.objects.create(
            recipient=self.user, title="Verilənlər bazası", message="Şahzad Əliyev qiyməti dəyişdi"
        )
        self.miss = InAppNotification.objects.create(recipient=self.user, title="Kimya", message="Yeni tapşırıq")

    def _found(self, query):
        return set(get_user_notifications(user=self.user, search_query=query).values_list("pk", flat=True))

    def test_english_keyboard_finds_azerbaijani_text(self):
        for query in ("Sahzad", "shahzad aliyev", "verilenler", "VERİLƏNLƏR bazasi"):
            with self.subTest(query=query):
                self.assertEqual(self._found(query), {self.hit.pk})

    def test_blank_query_returns_everything(self):
        self.assertEqual(self._found("   "), {self.hit.pk, self.miss.pk})
