"""OTP ikiqat göndərişi və dəqiq xəta mətnləri (sahib 2026-10-21).

Şikayət: «OTP kodu üçün mail təsdiqlə olanda … müəllim 2 dəfə OTP kodu göndərməyə vuranda problem olur …
deyir ki OTP kodunun vaxtı keçib». Kök səbəb: hər göndəriş əvvəlki kodu ``is_used=True`` edirdi — ikinci
klik birinci məktubdakı kodu öldürür, onu daxil edən istifadəçi «Kod yanlış və ya vaxtı keçib» görürdü.

Qayda indi:
* cooldown daxilində təkrar göndəriş YENİ KOD/MƏKTUB vermir (idempotent), paralel sorğular advisory
  kilidlə ardıcıllaşır;
* cooldown-dan sonra yeni kod gedir, amma son ``OTP_ACCEPTED_RECENT_CODES`` kod öz müddətinə qədər keçərlidir;
* «səhvdir» / «vaxtı keçib» / «əvəzlənib» / «istifadə olunub» / «çox cəhd» ayrı-ayrı deyilir.
"""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

import pytest

from apps.accounts.forms import OTPPasswordResetConfirmForm
from apps.accounts.models import EmailOTP
from apps.accounts.services import (
    OTPRateLimitError,
    issue_email_otp,
    request_email_otp,
    verify_email_otp,
)
from apps.accounts.services.auth import OTP_ACCEPTED_RECENT_CODES
from apps.accounts.services.otp_messages import otp_failure_message
from core import rate_limit as rate_limit_module

User = get_user_model()

PURPOSE = EmailOTP.Purpose.PASSWORD_RESET
NEW_PASSWORD = "MyOwnPassword456!"
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


def _code(message) -> str:
    match = re.search(r"\b(\d{6})\b", message.body)
    assert match, message.body
    return match.group(1)


def _age_all_codes(email, seconds=61):
    """Cooldown keçmiş kimi: bütün kodların yaranma vaxtını geri çək (müddətə toxunmadan)."""
    for otp in EmailOTP.objects.filter(email=email):
        EmailOTP.objects.filter(pk=otp.pk).update(created_at=otp.created_at - timedelta(seconds=seconds))


@override_settings(EMAIL_BACKEND=LOCMEM)
class RequestEmailOtpServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("otp_twice", "otp.twice@example.com", "Temp-Pass-123!")
        self.email = self.user.email

    def _send(self):
        return request_email_otp(self.email, user=self.user, purpose=PURPOSE)

    def test_two_rapid_requests_issue_one_code_and_one_mail(self):
        first = self._send()
        second = self._send()

        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertGreater(second.resend_available_in, 0)
        self.assertEqual(second.expires_at, first.expires_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(EmailOTP.objects.filter(email=self.email, purpose=PURPOSE).count(), 1)
        self.assertTrue(
            verify_email_otp(email=self.email, code=_code(mail.outbox[0]), user=self.user, purpose=PURPOSE).success
        )

    def test_resend_after_cooldown_keeps_previous_code_valid(self):
        self._send()
        _age_all_codes(self.email)
        resent = self._send()

        self.assertFalse(resent.reused)
        self.assertEqual(len(mail.outbox), 2)
        old_code, new_code = _code(mail.outbox[0]), _code(mail.outbox[1])
        live = EmailOTP.pending_queryset(user=self.user, email=self.email, purpose=PURPOSE)
        self.assertEqual(live.count(), 2)

        result = verify_email_otp(email=self.email, code=old_code, user=self.user, purpose=PURPOSE)
        self.assertTrue(result.success)
        # Uğurlu yoxlama qalan kodları bağlayır — ikinci məktubdakı kod artıq «istifadə olunmuş» sayılmır, əvəzlənib.
        if new_code != old_code:
            again = verify_email_otp(email=self.email, code=new_code, user=self.user, purpose=PURPOSE)
            self.assertFalse(again.success)
            self.assertNotEqual(again.reason, "expired")

    def test_newest_code_from_the_second_mail_also_verifies(self):
        self._send()
        _age_all_codes(self.email)
        self._send()
        result = verify_email_otp(email=self.email, code=_code(mail.outbox[1]), user=self.user, purpose=PURPOSE)
        self.assertTrue(result.success)

    def test_code_beyond_the_accepted_window_is_superseded_not_expired(self):
        for _ in range(OTP_ACCEPTED_RECENT_CODES + 1):
            self._send()
            _age_all_codes(self.email)
        oldest = _code(mail.outbox[0])
        newer = {_code(message) for message in mail.outbox[1:]}
        if oldest in newer:  # 1/10^6 təsadüf — ssenari mənasızdır
            self.skipTest("random collision")

        result = verify_email_otp(email=self.email, code=oldest, user=self.user, purpose=PURPOSE)

        self.assertFalse(result.success)
        self.assertEqual(result.reason, "superseded")
        text = otp_failure_message(result)
        self.assertIn("etibarsızdır", text)
        self.assertNotIn("vaxtı keçib", text)
        # Əsl (köhnə) kod təxmin deyil — səhv cəhd sayılmır.
        latest = EmailOTP.pending_queryset(user=self.user, email=self.email, purpose=PURPOSE).first()
        self.assertEqual(latest.attempts_count, 0)

    def test_wrong_code_is_reported_as_wrong_with_remaining_attempts(self):
        self._send()
        code = _code(mail.outbox[0])
        wrong = "000000" if code != "000000" else "111111"

        result = verify_email_otp(email=self.email, code=wrong, user=self.user, purpose=PURPOSE)

        self.assertEqual(result.reason, "invalid")
        self.assertEqual(result.remaining_attempts, 4)
        text = otp_failure_message(result)
        self.assertIn("Kod səhvdir", text)
        self.assertNotIn("vaxtı keçib", text)
        self.assertIn("etibarlıdır", text)  # qalan müddət ipucu

    def test_expired_code_is_reported_as_expired(self):
        self._send()
        EmailOTP.objects.filter(email=self.email).update(expires_at=timezone.now() - timedelta(seconds=1))

        result = verify_email_otp(email=self.email, code=_code(mail.outbox[0]), user=self.user, purpose=PURPOSE)

        self.assertEqual(result.reason, "expired")
        self.assertIn("vaxtı keçib", otp_failure_message(result))
        # Təkrar cəhd də (kod artıq bağlanıb) «vaxtı keçib» qalır, «yanlış» deyil.
        again = verify_email_otp(email=self.email, code=_code(mail.outbox[0]), user=self.user, purpose=PURPOSE)
        self.assertEqual(again.reason, "expired")

    def test_reused_code_is_reported_as_already_used(self):
        self._send()
        code = _code(mail.outbox[0])
        self.assertTrue(verify_email_otp(email=self.email, code=code, user=self.user, purpose=PURPOSE).success)

        result = verify_email_otp(email=self.email, code=code, user=self.user, purpose=PURPOSE)

        self.assertEqual(result.reason, "already_used")

    @override_settings(AUTH_OTP_MAX_ATTEMPTS=3)
    def test_max_attempts_closes_every_accepted_code(self):
        self._send()
        _age_all_codes(self.email)
        self._send()
        codes = {_code(message) for message in mail.outbox}
        wrong = next(candidate for candidate in ("000000", "111111", "222222", "333333") if candidate not in codes)

        reasons = [
            verify_email_otp(email=self.email, code=wrong, user=self.user, purpose=PURPOSE).reason for _ in range(3)
        ]

        self.assertEqual(reasons, ["invalid", "invalid", "max_attempts"])
        self.assertFalse(EmailOTP.pending_queryset(user=self.user, email=self.email, purpose=PURPOSE).exists())
        late = verify_email_otp(email=self.email, code=_code(mail.outbox[0]), user=self.user, purpose=PURPOSE)
        self.assertFalse(late.success)
        self.assertEqual(late.reason, "max_attempts")

    @override_settings(AUTH_OTP_MAX_SENDS_PER_HOUR=2)
    def test_hourly_limit_is_still_enforced(self):
        self._send()
        _age_all_codes(self.email)
        self._send()
        _age_all_codes(self.email)
        with self.assertRaises(OTPRateLimitError):
            self._send()
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(AUTH_OTP_EXPIRY_SECONDS=600)
    def test_expiry_setting_is_used_consistently_for_issue_mail_and_verify(self):
        result = self._send()
        otp = EmailOTP.objects.get(email=self.email)
        self.assertEqual(round((otp.expires_at - otp.created_at).total_seconds()), 600)
        self.assertEqual(result.expires_at, otp.expires_at)
        self.assertIn("10", mail.outbox[0].body)

        code = _code(mail.outbox[0])
        later = timezone.now() + timedelta(minutes=9)
        with mock.patch("django.utils.timezone.now", return_value=later):
            self.assertTrue(verify_email_otp(email=self.email, code=code, user=self.user, purpose=PURPOSE).success)

    def test_issue_without_reuse_still_keeps_only_the_accepted_window(self):
        for _ in range(OTP_ACCEPTED_RECENT_CODES + 2):
            issue_email_otp(self.user, purpose=PURPOSE)
        live = EmailOTP.pending_queryset(user=self.user, email=self.email, purpose=PURPOSE)
        self.assertEqual(live.count(), OTP_ACCEPTED_RECENT_CODES)

    def test_failed_delivery_leaves_no_phantom_code_and_allows_immediate_retry(self):
        with mock.patch("apps.accounts.services.auth._send_otp_message", side_effect=RuntimeError("smtp down")):
            with self.assertRaises(RuntimeError):
                self._send()
        self.assertFalse(EmailOTP.objects.filter(email=self.email).exists())
        self.assertFalse(self._send().reused)
        self.assertEqual(len(mail.outbox), 1)


@override_settings(EMAIL_BACKEND=LOCMEM)
class FirstLoginDoubleSendTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("first_twice", "first.twice@example.com", "Temp-Pass-123!")
        profile = self.user.profile
        profile.password_change_required = True
        profile.email_verified = False
        profile.save(update_fields=["password_change_required", "email_verified", "updated_at"])
        self.url = reverse("accounts:set_initial_password")
        self.email = "teacher.own@gmail.com"
        self.client.force_login(self.user)
        # Testlərdə keş DummyCache-dir; limiter proses-qlobal LocMem ehtiyatına düşür — testlər arası sızmasın.
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        self.addCleanup(rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear)

    def _send(self, **extra):
        return self.client.post(self.url, {"action": "send_otp", "email": self.email}, **extra)

    def _set_password(self, code):
        return self.client.post(
            self.url,
            {"action": "set_password", "code": code, "password1": NEW_PASSWORD, "password2": NEW_PASSWORD},
            follow=True,
        )

    def test_double_click_sends_one_mail_and_step_two_shows_validity(self):
        first = self._send()
        second = self._send(follow=True)

        self.assertEqual(first.status_code, 302)  # PRG: GET yeniləməsi kodu təkrar göndərmir
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(second, "artıq göndərilib")
        self.assertTrue(second.context["otp_sent"])
        otp = EmailOTP.objects.get(email=self.email)
        clock = timezone.localtime(otp.expires_at).strftime("%H:%M")
        self.assertContains(second, f"{clock}-ə qədər")
        self.assertContains(second, "data-otp-remaining-seconds")
        self.assertRegex(second.content.decode(), r'data-otp-resend-wait="[1-9]\d*"')
        self.assertContains(second, "accounts/js/otp_send_guard.js")

        # Yeniləmə (GET) yeni kod göndərmir.
        self.client.get(self.url)
        self.assertEqual(len(mail.outbox), 1)

        response = self._set_password(_code(mail.outbox[0]))
        self.assertEqual(response.redirect_chain[-1][0], reverse("accounts:profile"))

    def test_step_one_form_is_guarded_against_double_submit(self):
        response = self.client.get(self.url)
        self.assertContains(response, "data-otp-submit-once")
        self.assertContains(response, "data-busy-label")

    def test_resend_after_cooldown_first_mail_code_still_works(self):
        self._send()
        _age_all_codes(self.email)
        self._send()
        self.assertEqual(len(mail.outbox), 2)

        response = self._set_password(_code(mail.outbox[0]))

        self.assertEqual(response.redirect_chain[-1][0], reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, self.email)
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_wrong_code_says_wrong_not_expired(self):
        self._send()
        code = _code(mail.outbox[0])
        response = self._set_password("000000" if code != "000000" else "111111")
        self.assertContains(response, "Kod səhvdir")
        self.assertNotContains(response, "vaxtı keçib. Yenidən")
        self.assertNotContains(response, "Kod yanlış və ya vaxtı keçib")

    def test_expired_code_says_expired_and_offers_resend(self):
        self._send()
        EmailOTP.objects.filter(email=self.email).update(expires_at=timezone.now() - timedelta(seconds=5))
        response = self._set_password(_code(mail.outbox[0]))
        self.assertContains(response, "Kodun vaxtı keçib")
        self.assertContains(response, "Kodu yenidən göndər")
        self.assertContains(response, 'data-otp-resend-wait="0"')

    @override_settings(OTP_RESEND_RATE_LIMIT="2/10m")
    def test_rate_limit_counts_real_sends_only(self):
        self._send()
        self._send()  # ikiqat klik — limitə sayılmır
        _age_all_codes(self.email)
        self._send()
        _age_all_codes(self.email)
        response = self._send(follow=True)
        self.assertEqual(len(mail.outbox), 2)
        self.assertContains(response, "Çox sayda cəhd")

    @override_settings(AUTH_OTP_MAX_SENDS_PER_HOUR=1)
    def test_hourly_limit_message_is_specific(self):
        self._send()
        _age_all_codes(self.email)
        response = self._send(follow=True)
        self.assertContains(response, "saatlıq kod limiti")
        self.assertEqual(len(mail.outbox), 1)


@override_settings(EMAIL_BACKEND=LOCMEM)
class PasswordRecoveryDoubleSendTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("recover_twice", "recover.twice@example.com", "Old-Pass-123!")
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        self.addCleanup(rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear)

    def test_double_post_on_reset_form_sends_one_mail_and_first_code_works(self):
        url = reverse("accounts:password_reset")
        self.assertEqual(self.client.post(url, {"email": self.user.email}).status_code, 302)
        self.assertEqual(self.client.post(url, {"email": self.user.email}).status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

        done = self.client.get(reverse("accounts:password_reset_done"))
        self.assertContains(done, "data-otp-remaining-seconds")
        self.assertContains(done, "accounts/js/otp_send_guard.js")

        response = self.client.post(
            reverse("accounts:password_reset_done"),
            {"otp_code": _code(mail.outbox[0]), "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_reset_form_wrong_and_expired_codes_get_distinct_messages(self):
        self.client.post(reverse("accounts:password_reset"), {"email": self.user.email})
        code = _code(mail.outbox[0])
        done_url = reverse("accounts:password_reset_done")
        payload = {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}

        wrong = self.client.post(done_url, {"otp_code": "000000" if code != "000000" else "111111", **payload})
        self.assertContains(wrong, "Kod səhvdir")

        EmailOTP.objects.filter(email=self.user.email).update(expires_at=timezone.now() - timedelta(seconds=1))
        expired = self.client.post(done_url, {"otp_code": code, **payload})
        self.assertContains(expired, "Kodun vaxtı keçib")
        self.assertContains(expired, reverse("accounts:password_reset"))

    def test_rejected_new_password_does_not_burn_the_code(self):
        self.client.post(reverse("accounts:password_reset"), {"email": self.user.email})
        code = _code(mail.outbox[0])
        done_url = reverse("accounts:password_reset_done")

        bad = self.client.post(done_url, {"otp_code": code, "new_password1": "x", "new_password2": "x"})
        self.assertEqual(bad.status_code, 200)
        good = self.client.post(
            done_url, {"otp_code": code, "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
        )
        self.assertEqual(good.status_code, 302)


@override_settings(EMAIL_BACKEND=LOCMEM)
class ProfilePasswordOtpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("profile_twice", "profile.twice@example.com", "Old-Pass-123!")
        self.url = reverse("accounts:change_password_otp_request")
        self.client.force_login(self.user)

    def test_rapid_second_request_sends_no_second_mail(self):
        self.assertEqual(self.client.post(self.url).status_code, 202)
        second = self.client.post(self.url)
        self.assertEqual(second.status_code, 429)
        self.assertGreater(second.json()["retry_after"], 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_after_cooldown_keeps_first_code_valid_in_profile_form(self):
        self.client.post(self.url)
        _age_all_codes(self.user.email)
        self.assertEqual(self.client.post(self.url).status_code, 202)
        self.assertEqual(len(mail.outbox), 2)

        form = OTPPasswordResetConfirmForm(
            self.user,
            {"otp_code": _code(mail.outbox[0]), "new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD},
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertFalse(EmailOTP.pending_queryset(user=self.user, email=self.user.email, purpose=PURPOSE).exists())

    def test_profile_form_wrong_code_message(self):
        self.client.post(self.url)
        code = _code(mail.outbox[0])
        form = OTPPasswordResetConfirmForm(
            self.user,
            {
                "otp_code": "000000" if code != "000000" else "111111",
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Kod səhvdir", " ".join(form.errors["otp_code"]))


@pytest.mark.postgres
@override_settings(EMAIL_BACKEND=LOCMEM)
class ParallelSendRaceTests(TransactionTestCase):
    """İki PARALEL sorğu (ikiqat klik iki ayrı işçidə) — advisory kilid bir kod/məktub qoyur."""

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Advisory locks require PostgreSQL")
        self.user = User.objects.create_user("race_twice", "race.twice@example.com", "Temp-Pass-123!")

    def _send(self, barrier):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            return request_email_otp(self.user.email, user=self.user, purpose=PURPOSE)
        finally:
            connection.close()

    def test_parallel_requests_issue_a_single_code(self):
        from apps.accounts.services import auth as auth_module

        original = auth_module._count_recent_sends

        def slow_count(**kwargs):
            # Yarış pəncərəsini genişləndir: kilid olmasa hər iki sorğu burada «kod yoxdur» görüb yaradardı.
            time.sleep(0.3)
            return original(**kwargs)

        barrier = threading.Barrier(2)
        with mock.patch.object(auth_module, "_count_recent_sends", side_effect=slow_count):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = [future.result(timeout=15) for future in [pool.submit(self._send, barrier) for _ in range(2)]]

        self.assertEqual(sorted(result.reused for result in results), [False, True])
        self.assertEqual(EmailOTP.objects.filter(email=self.user.email, purpose=PURPOSE).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
