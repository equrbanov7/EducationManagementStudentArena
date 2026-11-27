from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.db import connections
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

import phonenumbers
import yaml

from .channels import whatsapp_channel
from .models import ContactMessage
from .tests import _valid_form_data


@override_settings(CONTACT_PAGE_ENABLED=True)
class PublicContactTests(TestCase):
    def test_independent_messages_have_distinct_receipts_bound_to_sender(self):
        url = reverse("contact")
        first, second = [self.client.get(url).context["submission_token"] for _ in range(2)]
        self.assertNotEqual(first, second)
        with patch("apps.contact.services.dispatch_contact_notification") as notify:
            for token in (first, first, second):
                with self.captureOnCommitCallbacks(execute=True):
                    answer = self.client.post(url, _valid_form_data(submission_token=token))
                receipt_url = answer["Location"]
                self.assertEqual(parse_qs(urlsplit(receipt_url).query)["receipt"], [token])
            self.assertEqual(notify.call_count, 2)
        self.assertEqual(ContactMessage.objects.count(), 2)
        self.assertTrue(self.client.get(receipt_url).context["submitted"])
        self.assertFalse(Client().get(receipt_url).context["submitted"])
        self.assertFalse(Client().get(url + "?sent=1").context["submitted"])

    def test_invalid_form_keeps_its_key_and_older_pages_can_retry_without_retyping(self):
        url = reverse("contact")
        token = self.client.get(url).context["submission_token"]
        response = self.client.post(url, _valid_form_data(submission_token=token, message="x"))
        self.assertEqual(response.context["submission_token"], token)
        self.assertFalse(ContactMessage.objects.exists())
        response = self.client.post(url, _valid_form_data())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.context["form"]["email"].value(), _valid_form_data()["email"])
        self.assertTrue(response.context["submission_token"])

    def test_whatsapp_is_only_shown_for_a_valid_configured_number(self):
        example = phonenumbers.example_number("GB")
        e164 = phonenumbers.format_number(example, phonenumbers.PhoneNumberFormat.E164)
        for number in ("", "not a number", "+994000000000"):
            with self.subTest(number=number), override_settings(CONTACT_WHATSAPP_NUMBER=number):
                self.assertNotContains(self.client.get(reverse("contact")), "wa.me/")
        with override_settings(CONTACT_WHATSAPP_NUMBER=e164):
            self.assertContains(self.client.get(reverse("contact")), f"https://wa.me/{e164[1:]}", count=2)
            request = RequestFactory().get(reverse("contact"))
            request.organization = SimpleNamespace(settings={"contact": {"whatsapp_number": ""}})
            self.assertIsNone(whatsapp_channel(request))
            request.organization.settings["contact"]["whatsapp_number"] = e164
            self.assertEqual(whatsapp_channel(request)["url"], f"https://wa.me/{e164[1:]}")


@override_settings(CONTACT_PAGE_ENABLED=True)
class ConcurrentContactTest(TransactionTestCase):
    def test_two_posts_for_one_form_create_one_message_and_notify_once(self):
        url = reverse("contact")
        token = self.client.get(url).context["submission_token"]
        gate = Barrier(2, timeout=5)

        def post():
            try:
                client = Client()
                client.cookies = self.client.cookies.copy()
                gate.wait()
                return client.post(
                    url,
                    _valid_form_data(submission_token=token, email="concurrent@example.invalid"),
                    REMOTE_ADDR="192.0.2.70",
                ).status_code
            finally:
                connections.close_all()

        with patch("apps.contact.services.dispatch_contact_notification") as notify, ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(post) for _ in range(2)]
            self.assertEqual([job.result(timeout=10) for job in futures], [302, 302])
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertEqual(notify.call_count, 1)


class PublicContactConfigurationTests(SimpleTestCase):
    def test_public_number_is_optional_in_deployment_and_example_environments(self):
        root = Path(settings.BASE_DIR)
        compose = yaml.safe_load((root / "docker-compose.prod.yml").read_text())
        self.assertEqual(
            compose["services"]["app"]["environment"]["CONTACT_WHATSAPP_NUMBER"], "${CONTACT_WHATSAPP_NUMBER:-}"
        )
        for filename in (".env.example", ".env.production.example"):
            self.assertIn("CONTACT_WHATSAPP_NUMBER=", (root / filename).read_text().splitlines())
