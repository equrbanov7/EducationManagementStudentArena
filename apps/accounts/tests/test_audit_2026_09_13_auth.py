"""Access auditi (2026-09-13) — autentifikasiya tapıntılarının reqressiya testləri.

F-01  superadmin login qaçış yolu dar vedrəyə bağlıdır, uğursuz cəhdlər sayılır
F-02  `send/resend/verify-otp` JSON API `password_reset` / `signup` (qeydiyyat
      sönülü) məqsədlərində hesab mövcudluğunu sızdırmır
F-08  ilk-giriş axını başqa hesabın e-poçtuna OTP göndərmir; unikal-indeks
      yarışı 500 vermir
F-09  OTP JSON endpoint-ləri və parol-bərpa formaları üçün İP qapısı
F-11  yeganə təşkilatı dayandırılmış istifadəçi login-dən sonra sərt çıxış alır

Zondlar auditorun `scratchpad/audit/access/probes/test_followup_probes.py`
faylındakı A3 / A4 / A2-ip-spray / A7 / A11 ssenarilərinə modelləşdirilib.
"""

import json
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import EmailOTP, UserProfile
from apps.accounts.views.auth.constants import (
    LOGIN_LIMIT_SCOPE_DEVICE,
    LOGIN_LIMIT_SCOPE_SUPERADMIN_ESCAPE,
)
from apps.organizations.models import Membership, Organization
from core import rate_limit as rate_limit_module
from core.rate_limit import is_rate_limited
from core.rls import bypass_rls

User = get_user_model()
PW = "AuditPass123!"
OTP_RE = re.compile(r"\b(\d{6})\b")
LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "fixauth"}}


def _last_otp():
    match = OTP_RE.search(mail.outbox[-1].body)
    return match.group(1) if match else None


def _reset_rate_limit_caches():
    from django.core.cache import cache

    cache.clear()
    rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()


class _AuthBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.owner = User.objects.create_user("fx_owner", "fx_owner@audit.az", PW)
            cls.org = Organization.objects.create(
                name="Fix Univ",
                slug="fix-univ",
                org_type="university",
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.teacher = User.objects.create_user("fx_teacher", "fx_teacher@audit.az", PW)
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.superadmin = User.objects.create_superuser("fx_root", "fx_root@audit.az", PW)

    def setUp(self):
        _reset_rate_limit_caches()
        mail.outbox.clear()

    def _login(self, client, username, password, ip):
        return client.post(
            reverse("accounts:staff_login"),
            {"username": username, "password": password},
            REMOTE_ADDR=ip,
        )

    def _json(self, client, url_name, ip, **payload):
        return client.post(
            reverse(url_name),
            json.dumps(payload),
            content_type="application/json",
            REMOTE_ADDR=ip,
        )


@override_settings(
    CACHES=LOCMEM_CACHE,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    LOGIN_RATE_LIMIT="5/10m",
    LOGIN_IP_RATE_LIMIT="60/10m",
    LOGIN_SUPERADMIN_ESCAPE_RATE_LIMIT="3/1h",
)
class SuperadminEscapeBucketTest(_AuthBase):
    """F-01 — qaçış yolu 3/1h (İP + istifadəçi adı) vedrəsi ilə məhdudlaşır."""

    def test_escape_exhausted_after_three_guesses_blocks_even_correct_password(self):
        client = Client()
        ip = "10.13.1.1"
        for _ in range(5):
            self.assertEqual(self._login(client, "fx_root", "wrong", ip).status_code, 200)

        # Limit doldu: növbəti 3 səhv cəhd qaçış vedrəsini xərcləyir (hər biri 429).
        for _ in range(3):
            response = self._login(client, "fx_root", "wrong-again", ip)
            self.assertEqual(response.status_code, 429)
            self.assertNotIn("_auth_user_id", client.session)

        escape_key = (f"ip:{ip}", "fx_root")
        self.assertTrue(is_rate_limited(LOGIN_LIMIT_SCOPE_SUPERADMIN_ESCAPE, "3/1h", *escape_key)[0])

        # Auditor zondu `A3-superadmin-correct-under-limit` əvvəl 302 + sessiya idi.
        with mock.patch("apps.accounts.views.auth._shared.authenticate") as authenticate_mock:
            response = self._login(client, "fx_root", PW, ip)
            authenticate_mock.assert_not_called()
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", client.session)

    def test_failed_attempts_under_limit_are_counted_in_normal_limiter(self):
        client = Client()
        ip = "10.13.1.2"
        for _ in range(5):
            self._login(client, "fx_root", "wrong", ip)
        count_key, _expires = rate_limit_module._cache_keys(LOGIN_LIMIT_SCOPE_DEVICE, (f"ip:{ip}",))
        before = int(rate_limit_module._rate_limit_cache().get(count_key) or 0)

        self._login(client, "fx_root", "wrong", ip)

        after = int(rate_limit_module._rate_limit_cache().get(count_key) or 0)
        self.assertEqual(after, before + 1, "limit altındakı uğursuz cəhd normal vedrədə sayılmalıdır")

    def test_superadmin_correct_password_within_escape_budget_still_enters(self):
        """Qaçış yolunun özü saxlanılır: büdcə daxilində düzgün parol girir və limiti təmizləyir."""
        client = Client()
        ip = "10.13.1.3"
        for _ in range(5):
            self._login(client, "fx_root", "wrong", ip)
        self.assertEqual(self._login(client, "fx_root", "wrong", ip).status_code, 429)

        response = self._login(client, "fx_root", PW, ip)

        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", client.session)

    def test_non_superadmin_correct_password_under_limit_stays_blocked(self):
        client = Client()
        ip = "10.13.1.4"
        for _ in range(5):
            self._login(client, "fx_teacher", "wrong", ip)

        response = self._login(client, "fx_teacher", PW, ip)

        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", client.session)


@override_settings(
    CACHES=LOCMEM_CACHE,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    OTP_SEND_IP_RATE_LIMIT="40/10m",
    OTP_VERIFY_IP_RATE_LIMIT="100/10m",
)
class OtpApiEnumerationTest(_AuthBase):
    """F-02 — `password_reset` və (qeydiyyat sönülü) `signup` cavabları neytraldır."""

    EXISTING = "fx_teacher@audit.az"
    UNKNOWN = "nobody_zz@audit.az"

    def _send(self, purpose, email, ip, url_name="accounts:send_otp_api"):
        return self._json(Client(), url_name, ip, email=email, purpose=purpose)

    def test_password_reset_purpose_is_neutral_on_send_and_resend(self):
        for url_name in ("accounts:send_otp_api", "accounts:resend_otp_api"):
            existing = self._send("password_reset", self.EXISTING, "10.13.2.1", url_name)
            unknown = self._send("password_reset", self.UNKNOWN, "10.13.2.2", url_name)
            self.assertEqual(existing.status_code, 202, url_name)
            self.assertEqual(unknown.status_code, 202, url_name)
            self.assertEqual(existing.json(), unknown.json(), url_name)
            self.assertNotIn("expires_in", existing.json(), url_name)

    def test_password_reset_purpose_sends_password_reset_otp_to_real_account(self):
        self._send("password_reset", self.EXISTING, "10.13.2.3")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.EXISTING])
        with bypass_rls():
            self.assertTrue(
                EmailOTP.objects.filter(email=self.EXISTING, purpose=EmailOTP.Purpose.PASSWORD_RESET).exists()
            )
            # Əvvəl səhvən SIGNUP OTP-si göndərilirdi.
            self.assertFalse(EmailOTP.objects.filter(email=self.EXISTING, purpose=EmailOTP.Purpose.SIGNUP).exists())

    def test_password_reset_cooldown_is_not_leaked(self):
        first = self._send("password_reset", self.EXISTING, "10.13.2.4")
        second = self._send("password_reset", self.EXISTING, "10.13.2.5")

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(PUBLIC_SIGNUP_ENABLED=False)
    def test_signup_purpose_is_neutral_when_public_signup_disabled(self):
        existing = self._send("signup", self.EXISTING, "10.13.2.6")
        unknown = self._send("signup", self.UNKNOWN, "10.13.2.7")

        self.assertEqual(existing.status_code, 202)
        self.assertEqual(unknown.status_code, 202)
        self.assertEqual(existing.json(), unknown.json())
        self.assertEqual(len(mail.outbox), 0)

        verify_existing = self._json(
            Client(), "accounts:verify_otp_api", "10.13.2.8", email=self.EXISTING, purpose="signup", otp="000000"
        )
        verify_unknown = self._json(
            Client(), "accounts:verify_otp_api", "10.13.2.9", email=self.UNKNOWN, purpose="signup", otp="000000"
        )
        self.assertEqual(verify_existing.status_code, 400)
        self.assertEqual(verify_unknown.status_code, 400)
        self.assertEqual(verify_existing.json()["detail"], verify_unknown.json()["detail"])

    @override_settings(PUBLIC_SIGNUP_ENABLED=True)
    def test_signup_purpose_keeps_ui_feedback_when_public_signup_enabled(self):
        self.assertEqual(self._send("signup", self.EXISTING, "10.13.2.10").status_code, 409)
        self.assertEqual(self._send("signup", self.UNKNOWN, "10.13.2.11").status_code, 404)

    def test_login_purpose_still_sends_and_stays_neutral_for_unknown(self):
        existing = self._send("login", self.EXISTING, "10.13.2.12")
        unknown = self._send("login", self.UNKNOWN, "10.13.2.13")

        self.assertEqual(existing.status_code, 202)
        self.assertEqual(unknown.status_code, 202)
        self.assertEqual(len(mail.outbox), 1)


@override_settings(
    CACHES=LOCMEM_CACHE,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    OTP_SEND_IP_RATE_LIMIT="4/10m",
    OTP_VERIFY_IP_RATE_LIMIT="3/10m",
)
class OtpIpRateLimitTest(_AuthBase):
    """F-09 — bir İP-dən fərqli e-poçtlara «spray» İP vedrəsi ilə dayanır."""

    def test_send_otp_ip_spray_is_limited(self):
        ip = "10.13.3.1"
        statuses = [
            self._json(
                Client(), "accounts:send_otp_api", ip, email=f"victim{i}@example.org", purpose="login"
            ).status_code
            for i in range(6)
        ]

        # Auditor zondu `A2-send-otp-ip-spray`: 12 e-poçt → hamısı 202 idi.
        self.assertEqual(statuses, [202, 202, 202, 202, 429, 429])
        response = self._json(Client(), "accounts:send_otp_api", ip, email="victim99@example.org", purpose="login")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)

    def test_send_and_resend_share_the_ip_bucket_but_other_ip_is_unaffected(self):
        ip = "10.13.3.2"
        for i in range(2):
            self._json(Client(), "accounts:send_otp_api", ip, email=f"a{i}@example.org", purpose="login")
        for i in range(2):
            self._json(Client(), "accounts:resend_otp_api", ip, email=f"b{i}@example.org", purpose="login")

        blocked = self._json(Client(), "accounts:resend_otp_api", ip, email="c@example.org", purpose="login")
        other_ip = self._json(Client(), "accounts:send_otp_api", "10.13.3.3", email="c@example.org", purpose="login")

        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(other_ip.status_code, 202)

    def test_verify_otp_ip_limit(self):
        ip = "10.13.3.4"
        statuses = [
            self._json(
                Client(), "accounts:verify_otp_api", ip, email=f"v{i}@example.org", purpose="login", otp="000000"
            ).status_code
            for i in range(4)
        ]

        self.assertEqual(statuses, [400, 400, 400, 429])

    def test_password_reset_form_ip_limit(self):
        ip = "10.13.3.5"
        statuses = [
            Client()
            .post(reverse("accounts:password_reset"), {"email": f"p{i}@example.org"}, REMOTE_ADDR=ip)
            .status_code
            for i in range(5)
        ]

        self.assertEqual(statuses, [302, 302, 302, 302, 429])

    def test_password_reset_done_form_ip_limit(self):
        ip = "10.13.3.6"
        client = Client()
        client.post(reverse("accounts:password_reset"), {"email": "fx_teacher@audit.az"}, REMOTE_ADDR=ip)
        payload = {"otp_code": "000000", "new_password1": "ResetStrongPass123!", "new_password2": "ResetStrongPass123!"}
        statuses = [
            client.post(reverse("accounts:password_reset_done"), payload, REMOTE_ADDR=ip).status_code for i in range(4)
        ]

        self.assertEqual(statuses, [200, 200, 200, 429])


@override_settings(
    CACHES=LOCMEM_CACHE,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class FirstLoginForeignEmailTest(_AuthBase):
    """F-08 — ilk-giriş axını başqa hesabın e-poçtuna kod göndərmir; yarış 500 vermir."""

    NEW_PW = "Qq11223344!!"

    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.first = User.objects.create_user("fx_first", "fx_first@audit.az", PW)
            Membership.objects.create(
                user=self.first,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            UserProfile.objects.filter(user=self.first).update(password_change_required=True)
        self.client = Client()
        self.client.force_login(self.first)
        self.url = reverse("accounts:set_initial_password")

    def test_send_otp_to_another_users_email_is_refused(self):
        # Auditor zondu `A11-send-otp-foreign-email`: mails=1, to=fx_teacher.
        response = self.client.post(
            self.url, {"action": "send_otp", "email": "FX_Teacher@audit.az"}, REMOTE_ADDR="10.13.4.1"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotIn("first_login_otp_sent_email", self.client.session)
        follow = self.client.get(self.url, REMOTE_ADDR="10.13.4.1")
        self.assertContains(follow, "Bu email ünvanı istifadə oluna bilməz")

    def test_own_or_free_email_still_receives_code_and_flow_completes(self):
        self.client.post(self.url, {"action": "send_otp", "email": "fx_first_new@audit.az"}, REMOTE_ADDR="10.13.4.2")
        self.assertEqual(len(mail.outbox), 1)
        code = _last_otp()

        response = self.client.post(
            self.url,
            {"action": "set_password", "code": code, "password1": self.NEW_PW, "password2": self.NEW_PW},
            REMOTE_ADDR="10.13.4.2",
        )

        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            self.first.refresh_from_db()
        self.assertEqual(self.first.email, "fx_first_new@audit.az")
        self.assertTrue(self.first.check_password(self.NEW_PW))
        self.assertFalse(self.first.profile.password_change_required)

    def test_email_claimed_between_send_and_set_password_gives_message_not_500(self):
        email = "fx_race@audit.az"
        self.client.post(self.url, {"action": "send_otp", "email": email}, REMOTE_ADDR="10.13.4.3")
        code = _last_otp()
        with bypass_rls():
            User.objects.create_user("fx_racer", email, PW)  # yarış: e-poçt artıq başqa hesaba verildi

        response = self.client.post(
            self.url,
            {"action": "set_password", "code": code, "password1": self.NEW_PW, "password2": self.NEW_PW},
            REMOTE_ADDR="10.13.4.3",
        )

        # Əvvəl: `accounts_auth_email_canon_uniq` UniqueViolation → 500 (run2.log:106).
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            self.first.refresh_from_db()
        self.assertEqual(self.first.email, "fx_first@audit.az")
        self.assertTrue(self.first.check_password(PW), "yarışda parol da dəyişməməlidir")
        self.assertTrue(self.first.profile.password_change_required)
        follow = self.client.get(self.url, REMOTE_ADDR="10.13.4.3")
        self.assertContains(follow, "Bu email ünvanı istifadə oluna bilməz")

    def test_integrity_error_path_is_exercised(self):
        """Yarış qorunması DB-dən asılı olmadan da işləyir (IntegrityError inyeksiyası)."""
        self.client.post(self.url, {"action": "send_otp", "email": "fx_inject@audit.az"}, REMOTE_ADDR="10.13.4.4")
        code = _last_otp()

        with mock.patch.object(User, "save", side_effect=IntegrityError("accounts_auth_email_canon_uniq")):
            response = self.client.post(
                self.url,
                {"action": "set_password", "code": code, "password1": self.NEW_PW, "password2": self.NEW_PW},
                REMOTE_ADDR="10.13.4.4",
            )

        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            self.first.refresh_from_db()
        self.assertEqual(self.first.email, "fx_first@audit.az")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SuspendedOnlyOrganizationLoginTest(TestCase):
    """F-11 — yeganə təşkilatı dayandırılmış istifadəçi org-suz sessiyada qalmır."""

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.owner = User.objects.create_user("fx_s_owner", "fx_s_owner@audit.az", PW)
            cls.org = Organization.objects.create(
                name="Susp Univ",
                slug="susp-univ",
                org_type="university",
                owner=cls.owner,
                status="suspended",
                is_active=True,
            )
            cls.teacher = User.objects.create_user("fx_s_teacher", "fx_s_teacher@audit.az", PW)
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )

    def _set_status(self, status):
        with bypass_rls():
            Organization.objects.filter(pk=self.org.pk).update(status=status)

    def test_login_then_first_request_hard_logs_out(self):
        client = Client()
        login = client.post(
            reverse("accounts:staff_login"),
            {"username": "fx_s_teacher", "password": PW},
            REMOTE_ADDR="10.13.5.1",
        )
        self.assertEqual(login.status_code, 302)

        # Auditor zondu `A7-suspended-login-follow`: 200, auth=True idi.
        response = client.get(reverse("accounts:profile"), REMOTE_ADDR="10.13.5.1")

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])
        self.assertNotIn("_auth_user_id", client.session)

    def test_forced_session_without_org_selection_is_logged_out(self):
        client = Client()
        client.force_login(self.teacher)

        response = client.get(reverse("accounts:profile"), REMOTE_ADDR="10.13.5.2")

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", client.session)

    def test_pending_only_org_sets_flag_but_keeps_session(self):
        self._set_status("pending")
        try:
            client = Client()
            client.force_login(self.teacher)

            response = client.get(reverse("accounts:profile"), REMOTE_ADDR="10.13.5.3")

            self.assertEqual(response.status_code, 200)
            self.assertIn("_auth_user_id", client.session)
            self.assertTrue(response.wsgi_request.org_pending_approval)
            self.assertIsNone(response.wsgi_request.organization)
            self.assertContains(response, "Təşkilat təsdiqi gözlənilir")
        finally:
            self._set_status("suspended")

    def test_active_org_user_and_superadmin_are_unaffected(self):
        self._set_status("active")
        try:
            client = Client()
            client.force_login(self.teacher)
            response = client.get(reverse("accounts:profile"), REMOTE_ADDR="10.13.5.4")
            self.assertEqual(response.status_code, 200)
            self.assertIn("_auth_user_id", client.session)
            self.assertFalse(response.wsgi_request.org_pending_approval)
        finally:
            self._set_status("suspended")

        with bypass_rls():
            root = User.objects.create_superuser("fx_s_root", "fx_s_root@audit.az", PW)
        client = Client()
        client.force_login(root)
        response = client.get(reverse("accounts:profile"), REMOTE_ADDR="10.13.5.5")
        self.assertIn(response.status_code, (200, 302))
        self.assertIn("_auth_user_id", client.session)
        self.assertIsNone(response.wsgi_request.blocked_organization)
