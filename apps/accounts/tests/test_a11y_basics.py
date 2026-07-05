"""U18 — baza a11y elementləri: skip-link + main landmark + lang atributu."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class A11yBasicsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("a11y_user", "a11y@qku.edu.az", "pw")

    def _page(self):
        client = Client()
        client.force_login(self.user)
        return client.get(reverse("accounts:profile")).content.decode()

    def test_skip_link_is_first_focusable(self):
        page = self._page()
        self.assertIn('class="skip-link"', page)
        self.assertIn('href="#main-content"', page)
        # Skip-link body-nin əvvəlində olmalıdır (naviqasiyadan ƏVVƏL).
        self.assertLess(page.index('class="skip-link"'), page.index("<nav"))

    def test_main_landmark_has_target_id(self):
        self.assertIn('<main id="main-content">', self._page())

    def test_html_lang_reflects_active_language(self):
        client = Client()
        client.force_login(self.user)
        page = client.get(reverse("accounts:profile"), HTTP_ACCEPT_LANGUAGE="ru").content.decode()
        self.assertIn('<html lang="ru">', page)
