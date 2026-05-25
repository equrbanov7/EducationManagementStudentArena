from django.test import TestCase
from django.urls import reverse

from core.seo_views import GOOGLE_SITE_VERIFICATION_CONTENT, GOOGLE_SITE_VERIFICATION_FILENAME


class GoogleSiteVerificationTests(TestCase):
    def test_google_verification_file_is_served_from_root(self):
        response = self.client.get(f"/{GOOGLE_SITE_VERIFICATION_FILENAME}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(response.content.decode("utf-8"), GOOGLE_SITE_VERIFICATION_CONTENT)

    def test_google_verification_url_name_resolves(self):
        self.assertEqual(reverse("google_site_verification"), f"/{GOOGLE_SITE_VERIFICATION_FILENAME}")
