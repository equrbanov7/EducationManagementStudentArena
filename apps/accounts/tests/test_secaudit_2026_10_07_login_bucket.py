"""Təhlükəsizlik auditi 2026-10-07, AUTH-02 — login limit açarı giriş axtarışı ilə eyni kanonik formadadır.

Açar əvvəl yalnız trim + lower idi, giriş isə NFKC ilə axtarılır: eyni hesabın Unicode-ekvivalent
yazılışları ayrı vedrələrə düşür və hesab səviyyəli limit (SA-03) zəifləyirdi.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import Membership, Organization
from core import rate_limit as rate_limit_module
from core.rls import bypass_rls

User = get_user_model()
PW = "AuditPass123!"
LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "secaudit1007"}}


def _reset_rate_limits():
    from django.core.cache import cache

    cache.clear()
    rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()


def _fullwidth_first_letter(value: str) -> str:
    """İlk ASCII hərfi «fullwidth» uyğun simvolla əvəz edir — NFKC onu geri ASCII-yə çevirir."""
    first = value[0]
    return chr(ord(first) - 0x21 + 0xFF01) + value[1:]


# ── AUTH-02 ─────────────────────────────────────────────────────────────────


@override_settings(
    CACHES=LOCMEM_CACHE,
    LOGIN_RATE_LIMIT="5/10m",
    LOGIN_IP_RATE_LIMIT="60/10m",
    LOGIN_ACCOUNT_RATE_LIMIT="20/1h",
    LOGIN_ACCOUNT_DISTINCT_IP_ALERT=0,
)
class CanonicalLoginBucketTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.owner = User.objects.create_user("a2_owner", "a2_owner@audit.az", PW)
            cls.org = Organization.objects.create(
                name="A2 Univ",
                slug="a2-univ",
                org_type="university",
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.victim = User.objects.create_user("victim.user", "victim.user@audit.az", PW)
            Membership.objects.create(
                user=cls.victim,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )

    def setUp(self):
        _reset_rate_limits()

    def _login(self, username, password, ip):
        return Client().post(
            reverse("accounts:staff_login"), {"username": username, "password": password}, REMOTE_ADDR=ip
        )

    def test_control_equivalent_spelling_reaches_the_same_account(self):
        response = self._login(_fullwidth_first_letter("victim.user"), PW, "10.5.0.1")
        self.assertEqual(response.status_code, 302)

    def test_equivalent_spelling_shares_the_account_bucket(self):
        for i in range(20):
            self._login("victim.user", f"wrong{i}", f"10.4.0.{i + 1}")
        self.assertEqual(self._login("victim.user", PW, "10.4.1.1").status_code, 429)

        variant = _fullwidth_first_letter("victim.user")
        self.assertEqual(self._login(variant, PW, "10.4.1.2").status_code, 429)

    def test_password_reset_clears_the_canonical_bucket(self):
        from apps.accounts.views.auth._shared import _clear_login_rate_limits_after_password_reset

        variant = _fullwidth_first_letter("victim.user")
        for i in range(20):
            self._login(variant, f"wrong{i}", f"10.3.0.{i + 1}")
        self.assertEqual(self._login("victim.user", PW, "10.3.1.1").status_code, 429)

        request = Client().get("/").wsgi_request
        _clear_login_rate_limits_after_password_reset(request, self.victim)
        self.assertEqual(self._login("victim.user", PW, "10.3.1.2").status_code, 302)
