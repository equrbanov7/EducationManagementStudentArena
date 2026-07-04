"""Tests for UNIVERSITY_MODE (cabinet-only portal) + brand white-labelling."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

User = get_user_model()


@override_settings(UNIVERSITY_MODE=True)
class UniversityModeTest(TestCase):
    """In UNIVERSITY_MODE the public marketing home is deactivated (login → cabinet)."""

    def setUp(self):
        self.client = Client()

    def test_home_redirects_anonymous_to_login(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("accounts:login"))

    def test_home_redirects_authenticated_to_cabinet(self):
        user = User.objects.create_user("uni_student", "uni_student@qku.edu.az", "StrongPass123!")
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("accounts:profile"))

    def test_login_page_hides_marketing_nav(self):
        response = self.client.get(reverse("accounts:login"))
        html = response.content.decode("utf-8", "ignore")
        # The marketing nav (about/contact links) must not appear in cabinet mode.
        self.assertNotIn("/about/", html)
        self.assertNotIn("/contact/", html)


@override_settings(UNIVERSITY_MODE=False)
class MarketingModeTest(TestCase):
    """With UNIVERSITY_MODE off the public home renders normally (marketing site)."""

    def test_home_renders_marketing_home(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)


@override_settings(SITE_BRAND_NAME="Qərbi Kaspi Universiteti")
class BrandNameTest(TestCase):
    """The configured brand name replaces the old EMSArena wordmark in titles."""

    def test_login_title_uses_brand(self):
        response = self.client.get(reverse("accounts:login"))
        html = response.content.decode("utf-8", "ignore")
        self.assertIn("Qərbi Kaspi Universiteti", html)
        self.assertNotIn("<title>EMSArena", html)
