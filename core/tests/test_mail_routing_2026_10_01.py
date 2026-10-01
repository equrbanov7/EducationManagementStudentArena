"""Sahib 2026-10-01: Brevo əvəzinə universitet poçtu (M365) — hesab üzrə marşrutlama.

* parol bərpası recovery@ qutusundan, qalan hər şey verification@ (default) qutusundan;
* M365 yalnız giriş edən qutunun ünvanını From kimi qəbul edir → yad From default ünvana çevrilir;
* recovery hesabı konfiqurasiya olunmayıbsa əvvəlki davranış (DEFAULT_FROM_EMAIL).
"""

from unittest.mock import MagicMock, patch

from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from core.mail_backend import AccountRoutingEmailBackend
from core.mailing import sender_for

M365 = dict(
    EMAIL_HOST_USER="verification@wcu.edu.az",
    EMAIL_HOST_PASSWORD="test-default-pw",
    DEFAULT_FROM_EMAIL="verification@wcu.edu.az",
    EMAIL_RECOVERY_HOST_USER="recovery@wcu.edu.az",
    EMAIL_RECOVERY_HOST_PASSWORD="test-recovery-pw",
    EMAIL_FROM_NAME="Qərbi Kaspi Universiteti",
)


class SenderForTests(SimpleTestCase):
    @override_settings(**M365)
    def test_password_reset_uses_recovery_mailbox(self):
        self.assertEqual(sender_for("password_reset"), "recovery@wcu.edu.az")
        self.assertEqual(sender_for("login"), "verification@wcu.edu.az")
        self.assertEqual(sender_for(None), "verification@wcu.edu.az")

    @override_settings(
        DEFAULT_FROM_EMAIL="no-reply@emsarena.com", EMAIL_RECOVERY_HOST_USER="", EMAIL_RECOVERY_HOST_PASSWORD=""
    )
    def test_without_recovery_account_previous_behaviour(self):
        self.assertEqual(sender_for("password_reset"), "no-reply@emsarena.com")

    @override_settings(**{**M365, "EMAIL_RECOVERY_HOST_PASSWORD": ""})
    def test_recovery_user_without_password_is_ignored(self):
        self.assertEqual(sender_for("password_reset"), "verification@wcu.edu.az")


@override_settings(**M365)
class RoutingBackendTests(SimpleTestCase):
    def _send(self, *messages):
        created = []

        def factory(**kwargs):
            backend = MagicMock()
            backend.send_messages.side_effect = lambda msgs: len(msgs)
            created.append((kwargs, backend))
            return backend

        with patch("core.mail_backend.SMTPEmailBackend", side_effect=factory):
            sent = AccountRoutingEmailBackend(timeout=8).send_messages(list(messages))
        return sent, created

    def test_groups_by_account_and_logs_in_with_matching_credentials(self):
        reset = EmailMessage("r", "b", "recovery@wcu.edu.az", ["a@x.az"])
        otp = EmailMessage("o", "b", "verification@wcu.edu.az", ["b@x.az"])
        sent, created = self._send(reset, otp)
        self.assertEqual(sent, 2)
        creds = {(kw["username"], kw["password"]) for kw, _ in created}
        self.assertEqual(
            creds, {("recovery@wcu.edu.az", "test-recovery-pw"), ("verification@wcu.edu.az", "test-default-pw")}
        )
        self.assertTrue(all(kw["timeout"] == 8 for kw, _ in created))
        self.assertEqual(reset.from_email, "recovery@wcu.edu.az")

    def test_foreign_from_is_rewritten_to_default_mailbox_keeping_name(self):
        legacy = EmailMessage("s", "b", "Portal <no-reply@emsarena.com>", ["c@x.az"])
        bare = EmailMessage("s", "b", "verification@wcu.edu.az", ["d@x.az"])
        _sent, created = self._send(legacy, bare)
        self.assertEqual(len(created), 1)
        self.assertIn("<verification@wcu.edu.az>", legacy.from_email)
        self.assertTrue(legacy.from_email.startswith("Portal"))
        self.assertIn("<verification@wcu.edu.az>", bare.from_email)  # sayt adı əlavə olunur

    def test_empty_batch(self):
        self.assertEqual(AccountRoutingEmailBackend().send_messages([]), 0)
