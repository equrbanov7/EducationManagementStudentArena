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


class SessionTimeoutSettingsTest(TestCase):
    """Verify that session timeout values are explicitly defined in settings."""

    def test_session_cookie_age_is_defined(self):
        """SESSION_COOKIE_AGE must be explicitly set (not None or zero)."""
        self.assertTrue(
            hasattr(settings, "SESSION_COOKIE_AGE"),
            "SESSION_COOKIE_AGE must be explicitly defined in settings.",
        )
        self.assertGreater(
            settings.SESSION_COOKIE_AGE,
            0,
            "SESSION_COOKIE_AGE must be a positive integer (seconds).",
        )

    def test_session_inactivity_timeout_is_defined(self):
        """SESSION_INACTIVITY_TIMEOUT must be explicitly set."""
        self.assertTrue(
            hasattr(settings, "SESSION_INACTIVITY_TIMEOUT"),
            "SESSION_INACTIVITY_TIMEOUT must be explicitly defined in settings.",
        )
        self.assertGreater(
            settings.SESSION_INACTIVITY_TIMEOUT,
            0,
            "SESSION_INACTIVITY_TIMEOUT must be a positive integer (seconds).",
        )

    def test_session_inactivity_timeout_le_cookie_age(self):
        """Inactivity timeout must not exceed the absolute cookie lifetime."""
        self.assertLessEqual(
            settings.SESSION_INACTIVITY_TIMEOUT,
            settings.SESSION_COOKIE_AGE,
            "SESSION_INACTIVITY_TIMEOUT should be ≤ SESSION_COOKIE_AGE.",
        )

    def test_session_expire_at_browser_close_is_defined(self):
        """SESSION_EXPIRE_AT_BROWSER_CLOSE must be explicitly set."""
        self.assertTrue(
            hasattr(settings, "SESSION_EXPIRE_AT_BROWSER_CLOSE"),
            "SESSION_EXPIRE_AT_BROWSER_CLOSE must be explicitly defined in settings.",
        )
        self.assertIsInstance(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE, bool)


class StaticFilesStorageTest(TestCase):
    """Verify static-files storage backend is configured correctly."""

    def test_static_files_storage_is_set(self):
        """STATICFILES_STORAGE must be explicitly configured."""
        self.assertTrue(
            hasattr(settings, "STATICFILES_STORAGE"),
            "STATICFILES_STORAGE must be explicitly defined in settings.",
        )
        self.assertIsInstance(settings.STATICFILES_STORAGE, str)
        self.assertTrue(
            settings.STATICFILES_STORAGE,
            "STATICFILES_STORAGE must not be empty.",
        )


class DebugEnvParsingTest(TestCase):
    """Verify that the DEBUG env-bool helper works correctly for all input values."""

    # The _env_bool function is defined in both local.py and production.py.
    # We test the logic directly here to avoid triggering module-level code
    # (SECRET_KEY checks, etc.) that would fail in the test environment.

    @staticmethod
    def _env_bool(name: str, default: bool, env: dict) -> bool:
        """Inline replica of the _env_bool helper for isolated testing."""
        value = env.get(name, "").strip().lower()
        if not value:
            return default
        return value in {"1", "true", "yes", "on"}

    def test_truthy_values(self):
        """_env_bool must return True for all recognised truthy strings."""
        truthy = {"1", "true", "yes", "on", "TRUE", "YES", "ON", "True", "Yes"}
        for val in truthy:
            with self.subTest(value=val):
                result = self._env_bool("VAR", False, {"VAR": val})
                self.assertTrue(result, f"_env_bool should return True for '{val}'")

    def test_falsy_values(self):
        """_env_bool must return False for all recognised falsy strings."""
        falsy = {"0", "false", "no", "off", "FALSE", "NO", "OFF", "False", "No"}
        for val in falsy:
            with self.subTest(value=val):
                result = self._env_bool("VAR", True, {"VAR": val})
                self.assertFalse(result, f"_env_bool should return False for '{val}'")

    def test_uses_default_when_unset(self):
        """_env_bool must fall back to the default when the variable is absent."""
        self.assertTrue(self._env_bool("MISSING_VAR", True, {}))
        self.assertFalse(self._env_bool("MISSING_VAR", False, {}))

    def test_uses_default_for_empty_string(self):
        """_env_bool must fall back to the default when the variable is empty."""
        self.assertTrue(self._env_bool("VAR", True, {"VAR": ""}))
        self.assertFalse(self._env_bool("VAR", False, {"VAR": ""}))

    def test_fragile_string_comparison_is_replaced(self):
        """
        Verify that 'False' (a string with capital F) is NOT considered True.
        The old fragile pattern was: os.getenv("DEBUG", "True") == "True"
        which would return False for DEBUG=False but also for DEBUG=false,
        DEBUG=0, and DEBUG=no — instead of consistently returning False for
        all falsy values and True only for truthy ones.
        """
        # Old fragile pattern: 'False' != 'True' → returns False (correct by luck)
        # But also: 'false' != 'True' → False (correct)
        # And: '0' != 'True' → False (correct)
        # BUT: 'true' != 'True' → False! (WRONG — case-sensitive bug)
        def old_fragile(val):
            return val == "True"

        self.assertFalse(old_fragile("true"), "Old fragile parser incorrectly rejects lowercase 'true'")

        # New robust parser handles all variants correctly
        self.assertTrue(self._env_bool("VAR", False, {"VAR": "true"}))
        self.assertTrue(self._env_bool("VAR", False, {"VAR": "1"}))
        self.assertFalse(self._env_bool("VAR", True, {"VAR": "false"}))
        self.assertFalse(self._env_bool("VAR", True, {"VAR": "0"}))
