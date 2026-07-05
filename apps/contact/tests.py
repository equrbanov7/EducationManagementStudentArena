"""
Tests for the contact app: form validation (anti-spam), message creation
(IP/user-agent capture) and the reply delivery status flow.

Outbound email runs in a daemon thread in production; tests replace the
thread with a synchronous runner so delivery status assertions are not racy.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from .forms import ContactForm
from .models import ContactMessage
from .services import _extract_client_ip, create_contact_message, send_reply_to_contact

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

    def test_extract_client_ip_prefers_first_xff_entry(self):
        request = self.factory.get(
            "/contact/",
            HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1",
            REMOTE_ADDR="10.0.0.1",
        )
        self.assertEqual(_extract_client_ip(request), "203.0.113.7")

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

    def test_invalid_reply_from_raises(self):
        with self.assertRaises(ValueError):
            send_reply_to_contact(
                message=self.message,
                reply_body="Cavab",
                reply_from="unknown-inbox",
                sent_by=self.admin,
            )

    def test_successful_delivery_marks_sent_and_handled(self):
        with (
            patch("apps.contact.services.threading.Thread", _SyncThread),
            patch("apps.contact.services._send_reply_email", return_value=(True, "")),
        ):
            send_reply_to_contact(
                message=self.message,
                reply_body="Salam, cavabınız budur.",
                reply_from="info",
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
                reply_from="support",
                sent_by=self.admin,
            )
        self.message.refresh_from_db()
        self.assertEqual(self.message.reply_delivery_status, ContactMessage.REPLY_DELIVERY_FAILED)
        self.assertEqual(self.message.reply_delivery_error, "smtp down")
        self.assertFalse(self.message.is_handled)
