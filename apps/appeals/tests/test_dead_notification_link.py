"""Silinmiş müraciətə işarə edən köhnə bildiriş keçidi 404 verməməlidir.

İstifadəçi şikayəti (2026-07-29): profil → Bildirişlər → "Keçidə get" → 404.
Səbəb: bildiriş `/appeals/<id>/` yolunu dondurur, müraciət sonradan silinir və
`get_object_or_404` boş 404 səhifəsi qaytarırdı.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

# Bazada mövcud olmayan ID (heç bir müraciət yaradılmır).
MISSING_APPEAL_ID = 987654


class DeadAppealLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("dead-link-user", "dead-link@example.com", "pass12345")

    def setUp(self):
        self.client.force_login(self.user)

    def test_student_detail_link_redirects_instead_of_404(self):
        response = self.client.get(reverse("appeals:appeal_detail", args=[MISSING_APPEAL_ID]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("section=my-appeals", response["Location"])

    def test_review_link_redirects_instead_of_404(self):
        response = self.client.get(reverse("appeals:review_appeal", args=[MISSING_APPEAL_ID]))

        self.assertEqual(response.status_code, 302)
        self.assertIn("section=manage-appeals", response["Location"])

    def test_user_sees_an_explanation_message(self):
        response = self.client.get(reverse("appeals:appeal_detail", args=[MISSING_APPEAL_ID]), follow=True)

        texts = [str(m) for m in response.context["messages"]]
        self.assertTrue(texts, msg="istifadəçiyə heç bir izah verilmir")
        self.assertIn("mövcud deyil", " ".join(texts))
