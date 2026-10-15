"""
Tests for the contact app: form validation (anti-spam), message creation
(IP/user-agent capture) and the reply delivery status flow.

Outbound email runs in a daemon thread in production; tests replace the
thread with a synchronous runner so delivery status assertions are not racy.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from .forms import ContactForm
from .models import ContactMessage
from .services import _extract_client_ip, _send_internal_notification, create_contact_message, send_reply_to_contact

User = get_user_model()


def _valid_form_data(**overrides):
    data = {
        "name": "Elvin Qurbanov",
        "email": "student@example.com",
        "phone": "+994 50 123 45 67",
        "subject": "general",
        "message": "Salam, platforma haqqında ətraflı məlumat almaq istəyirəm.",
        "website": "",
    }
    data.update(overrides)
    return data


class _SyncThread:
    """threading.Thread əvəzedicisi — target-i start()-da sinxron icra edir."""

    def __init__(self, *, target, name=None, daemon=None):
        self._target = target

    def start(self):
        self._target()


# ---------------------------------------------------------------------------
# ContactForm
# ---------------------------------------------------------------------------
class ContactFormTest(TestCase):
    def test_valid_data_passes(self):
        form = ContactForm(data=_valid_form_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_name_too_short_rejected(self):
        form = ContactForm(data=_valid_form_data(name="A"))
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_name_with_url_rejected(self):
        form = ContactForm(data=_valid_form_data(name="www.spam.example"))
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_invalid_phone_rejected(self):
        form = ContactForm(data=_valid_form_data(phone="not-a-phone!"))
        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_empty_phone_allowed(self):
        form = ContactForm(data=_valid_form_data(phone=""))
        self.assertTrue(form.is_valid(), form.errors)

    def test_message_too_short_rejected(self):
        form = ContactForm(data=_valid_form_data(message="qısa"))
        self.assertFalse(form.is_valid())
        self.assertIn("message", form.errors)

    def test_message_with_too_many_urls_rejected(self):
        spam = "Bax: http://a.example http://b.example http://c.example http://d.example"
        form = ContactForm(data=_valid_form_data(message=spam))
        self.assertFalse(form.is_valid())
        self.assertIn("message", form.errors)

    def test_honeypot_filled_rejected(self):
        form = ContactForm(data=_valid_form_data(website="http://bot.example"))
        self.assertFalse(form.is_valid())
        self.assertIn("website", form.errors)

    def test_invalid_subject_rejected(self):
        form = ContactForm(data=_valid_form_data(subject="nonexistent"))
        self.assertFalse(form.is_valid())
        self.assertIn("subject", form.errors)


# ---------------------------------------------------------------------------
# create_contact_message + client IP çıxarılması
# ---------------------------------------------------------------------------
class CreateContactMessageTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_persists_message_with_ip_and_user_agent(self):
        request = self.factory.post("/contact/", HTTP_USER_AGENT="TestAgent/1.0")
        with patch("apps.contact.services.dispatch_contact_notification") as notify:
            message = create_contact_message(
                form_cleaned_data=_valid_form_data(),
                request=request,
            )
        self.assertIsNotNone(message.pk)
        self.assertEqual(message.name, "Elvin Qurbanov")
        self.assertEqual(message.subject, "general")
        self.assertEqual(message.ip_address, "127.0.0.1")
        self.assertEqual(message.user_agent, "TestAgent/1.0")
        notify.assert_called_once_with(message)

    def test_extract_client_ip_uses_the_trusted_proxy_member(self):
        """2026-09-02 audit, P2-6: SOL üzv müştəri tərəfindən saxtalaşdırıla bilər.

        Əvvəl bu test məhz sol üzvü («ilk XFF girişi») gözləyirdi, yəni
        saxtalaşdırıla bilən davranışı kilidləmişdi.  Edge nginx başlığı
        overwrite edir → doğru üzv SONUNCU-dur.
        """
        request = self.factory.get(
            "/contact/",
            HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1",
            REMOTE_ADDR="10.0.0.1",
        )
        self.assertEqual(_extract_client_ip(request), "10.0.0.1")

    def test_extract_client_ip_falls_back_to_remote_addr(self):
        request = self.factory.get("/contact/", REMOTE_ADDR="198.51.100.5")
        self.assertEqual(_extract_client_ip(request), "198.51.100.5")


# ---------------------------------------------------------------------------
# send_reply_to_contact — çatdırılma statusu axını
# ---------------------------------------------------------------------------
class SendReplyToContactTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="contact_admin",
            email="admin@example.com",
            password="StrongPass123!",
        )
        self.message = ContactMessage.objects.create(
            name="Tələbə",
            email="student@example.com",
            subject="general",
            message="Salam, sualım var.",
        )

    @override_settings(DEFAULT_FROM_EMAIL="verification@uni.example", SITE_BRAND_NAME="Test Universiteti")
    def test_reply_is_sent_from_the_default_mailbox(self):
        """2026-10-16: info@/support@ yoxdur — cavab sistemin real (default) qutusundan gedir."""
        with (
            patch("apps.contact.services.threading.Thread", _SyncThread),
            patch("apps.contact.services._send_email_with_fallback", return_value=(True, "")) as send,
        ):
            send_reply_to_contact(message=self.message, reply_body="Salam, cavabınız budur.", sent_by=self.admin)
        kwargs = send.call_args.kwargs
        self.assertEqual(kwargs["from_email"], "verification@uni.example")
        self.assertEqual(kwargs["from_name"], "Test Universiteti")
        self.assertEqual(kwargs["reply_to"], ["verification@uni.example"])
        self.assertEqual(kwargs["to"], ["student@example.com"])
        self.assertNotIn("emsarena", kwargs["html_body"] + kwargs["text_body"])
        self.message.refresh_from_db()
        self.assertEqual(self.message.reply_from, ContactMessage.REPLY_FROM_DEFAULT)

    @override_settings(DEFAULT_FROM_EMAIL="Portal <verification@uni.example>")
    def test_reply_sender_strips_the_display_name(self):
        with (
            patch("apps.contact.services.threading.Thread", _SyncThread),
            patch("apps.contact.services._send_email_with_fallback", return_value=(True, "")) as send,
        ):
            send_reply_to_contact(message=self.message, reply_body="Salam, cavabınız budur.", sent_by=self.admin)
        self.assertEqual(send.call_args.kwargs["from_email"], "verification@uni.example")

    def test_successful_delivery_marks_sent_and_handled(self):
        with (
            patch("apps.contact.services.threading.Thread", _SyncThread),
            patch("apps.contact.services._send_reply_email", return_value=(True, "")),
        ):
            send_reply_to_contact(
                message=self.message,
                reply_body="Salam, cavabınız budur.",
                sent_by=self.admin,
            )
        self.message.refresh_from_db()
        self.assertEqual(self.message.reply_delivery_status, ContactMessage.REPLY_DELIVERY_SENT)
        self.assertTrue(self.message.is_handled)
        self.assertIsNotNone(self.message.reply_sent_at)
        self.assertEqual(self.message.reply_body, "Salam, cavabınız budur.")
        self.assertEqual(self.message.reply_sent_by, self.admin)

    def test_failed_delivery_marks_failed_with_reason(self):
        with (
            patch("apps.contact.services.threading.Thread", _SyncThread),
            patch("apps.contact.services._send_reply_email", return_value=(False, "smtp down")),
        ):
            send_reply_to_contact(
                message=self.message,
                reply_body="Cavab mətnini yazırıq.",
                sent_by=self.admin,
            )
        self.message.refresh_from_db()
        self.assertEqual(self.message.reply_delivery_status, ContactMessage.REPLY_DELIVERY_FAILED)
        self.assertEqual(self.message.reply_delivery_error, "smtp down")
        self.assertFalse(self.message.is_handled)


# ---------------------------------------------------------------------------
# İşçi bildirişi — alıcılar (2026-10-16: sabit info@ qutusu yoxdur)
# ---------------------------------------------------------------------------
@override_settings(DEFAULT_FROM_EMAIL="verification@uni.example")
class ContactNotificationRecipientsTest(TestCase):
    def setUp(self):
        self.message = ContactMessage.objects.create(
            name="Qonaq", email="guest@example.com", subject="general", message="Salam, sualım var."
        )

    def _send(self):
        with patch("apps.contact.services._send_email_with_fallback", return_value=(True, "")) as send:
            ok = _send_internal_notification(self.message)
        return ok, send

    @override_settings(CONTACT_NOTIFY_EMAIL="")
    def test_empty_notify_email_falls_back_to_active_superusers(self):
        User.objects.create_superuser(username="root1", email="root1@example.com", password="StrongPass123!")
        User.objects.create_superuser(username="root2", email="root2@example.com", password="StrongPass123!")
        User.objects.create_superuser(username="root3", email="", password="StrongPass123!")
        gone = User.objects.create_superuser(username="root4", email="gone@example.com", password="StrongPass123!")
        gone.is_active = False
        gone.save(update_fields=["is_active"])
        User.objects.create_user(username="plain", email="plain@example.com", password="StrongPass123!")

        ok, send = self._send()

        self.assertTrue(ok)
        kwargs = send.call_args.kwargs
        self.assertEqual(kwargs["to"], ["root1@example.com", "root2@example.com"])
        self.assertEqual(kwargs["from_email"], "verification@uni.example")
        self.assertEqual(kwargs["reply_to"], ["guest@example.com"])
        self.assertNotIn("emsarena", kwargs["html_body"] + kwargs["text_body"])
        self.assertIn("Cavab sistemin rəsmi poçt qutusundan gedəcək.", kwargs["text_body"])

    @override_settings(CONTACT_NOTIFY_EMAIL="desk@uni.example, chief@uni.example")
    def test_configured_notify_email_wins(self):
        User.objects.create_superuser(username="root1", email="root1@example.com", password="StrongPass123!")
        ok, send = self._send()
        self.assertTrue(ok)
        self.assertEqual(send.call_args.kwargs["to"], ["desk@uni.example", "chief@uni.example"])

    @override_settings(CONTACT_NOTIFY_EMAIL="")
    def test_no_recipient_skips_with_warning(self):
        with self.assertLogs("core.mailing", level="WARNING"):
            ok, send = self._send()
        self.assertFalse(ok)
        send.assert_not_called()


# ---------------------------------------------------------------------------
# Görünən ünvanlar — boşdursa sətir/blok gizlənir (2026-10-16)
# ---------------------------------------------------------------------------
class ContactAddressVisibilityTest(TestCase):
    @override_settings(CONTACT_PUBLIC_EMAIL="", CONTACT_SUPPORT_EMAIL="")
    def test_contact_page_and_footer_hide_empty_addresses(self):
        response = self.client.get("/contact/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn("mailto:", html)
        self.assertNotIn("info – ümumi, support – texniki dəstək", html)
        self.assertNotIn("emsarena.com", html)
        self.assertNotIn("fa-life-ring", html)

    @override_settings(CONTACT_PUBLIC_EMAIL="desk@uni.example", CONTACT_SUPPORT_EMAIL="help@uni.example")
    def test_configured_addresses_are_shown(self):
        html = self.client.get("/contact/").content.decode()
        self.assertIn("mailto:desk@uni.example", html)
        self.assertIn("mailto:help@uni.example", html)
