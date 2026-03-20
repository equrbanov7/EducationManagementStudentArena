from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class SecurityConfigurationTest(TestCase):
    def _parse_csp(self, response):
        directives = {}
        for chunk in response.headers["Content-Security-Policy"].split(";"):
            chunk = chunk.strip()
            if not chunk:
                continue
            name, _, value = chunk.partition(" ")
            directives[name] = value
        return directives

    def _csrf_client_with_pending_email(self):
        client = Client(enforce_csrf_checks=True)
        user = User.objects.create_user(
            username="otpsecurityuser",
            email="otpsecurity@example.com",
            password="StrongPass123!",
            is_active=False,
        )
        session = client.session
        session["pending_verify_email"] = user.email
        session.save()
        return client

    def test_whitenoise_disables_wildcard_static_cors(self):
        self.assertFalse(settings.WHITENOISE_ALLOW_ALL_ORIGINS)

        response = self.client.get("/static/css/main.css")

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.headers.get("Access-Control-Allow-Origin"), "*")

    def test_subscribe_page_uses_strict_style_src(self):
        response = self.client.get(reverse("subscribe"))

        self.assertEqual(response.status_code, 200)
        directives = self._parse_csp(response)
        self.assertIn("style-src", directives)
        self.assertNotIn("'unsafe-inline'", directives["style-src"])
        self.assertEqual(directives.get("style-src-attr"), "'unsafe-inline'")

    def test_verify_code_csrf_failures_still_include_csp(self):
        client = self._csrf_client_with_pending_email()

        response = client.post(reverse("accounts:verify_code"), {"code": "123456"})

        self.assertEqual(response.status_code, 403)
        directives = self._parse_csp(response)
        self.assertIn("style-src", directives)
        self.assertNotIn("'unsafe-inline'", directives["style-src"])

    def test_resend_code_csrf_failures_still_include_csp(self):
        client = self._csrf_client_with_pending_email()

        response = client.post(reverse("accounts:resend_code"))

        self.assertEqual(response.status_code, 403)
        directives = self._parse_csp(response)
        self.assertIn("style-src", directives)
        self.assertNotIn("'unsafe-inline'", directives["style-src"])
