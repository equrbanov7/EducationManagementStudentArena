"""Vahid müasir e-poçt şablonu (sahib 2026-10-15: «Mailə gələn template-in dizaynını yaxşılaşdır»).

Hər məktub `templates/emails/base_email.html` / `base_email.txt`-dən törəyir: başlıq zolağı,
kart, bulletproof düymə, OTP qutusu, gizli önbaxış (preheader), altlıq və mətn variantı.
Bu testlər hər şablonu real kontekstlə render edir və açar dəyişənlərin (kod, link) yerində
olduğunu, mətn variantında HTML/CSS qalmadığını və məktubun TƏK dildə qaldığını yoxlayır.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from unittest import mock

from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings
from django.utils import timezone, translation

from apps.notifications.templatetags.email_layout import email_absolute_url, email_chrome
from core.mailing import plain_text_body

CODE = "482913"
RESET_URL = "https://ems.qku.edu.az/accounts/password-reset/MQ/abc-123/"
CREATED = timezone.make_aware(dt.datetime(2026, 10, 15, 9, 30))


def _user():
    return SimpleNamespace(username="elvin.qurbanov", get_username=lambda: "elvin.qurbanov", email="e@qku.edu.az")


def _otp_context(purpose="login"):
    return {
        "brand": "Qərbi Kaspi Universiteti",
        "user": _user(),
        "recipient_name": "Elvin Qurbanov",
        "email": "e@qku.edu.az",
        "headline": "Giriş təsdiqi",
        "otp_intro_action": "girişinizi təsdiqləmək",
        "cta_label": "Girişi təsdiqlə",
        "code": CODE,
        "verification_link": "",
        "otp_expiry_minutes": 5,
        "expires_at": None,
        "purpose": purpose,
    }


def _contact_message():
    return SimpleNamespace(
        pk=7,
        name="Aysel Məmmədova",
        email="aysel@example.com",
        phone="+994 50 000 00 00",
        message="Salam,\nqəbul haqqında sual.",
        created_at=CREATED,
        get_subject_display=lambda: "Qəbul",
    )


def _trial_request():
    return SimpleNamespace(
        pk=3,
        full_name="Murad Əliyev",
        email="murad@example.com",
        subject_name="Riyaziyyat",
        original_filename="suallar.pdf",
        note="Fayl 30 sualdır.",
        created_at=CREATED,
    )


#: (şablon, kontekst, HTML/mətndə mütləq olmalı açar dəyərlər)
CASES = {
    "accounts/emails/login_otp_email": (_otp_context, (CODE, "Elvin Qurbanov")),
    "accounts/emails/verification_email": (lambda: _otp_context("password_reset"), (CODE,)),
    "accounts/password_reset_email": (
        lambda: {
            "brand": "Qərbi Kaspi Universiteti",
            "email": "e@qku.edu.az",
            "user": _user(),
            "reset_url": RESET_URL,
            "otp_code": CODE,
            "otp_expiry_minutes": 5,
        },
        (CODE, RESET_URL),
    ),
    "admin/emails/admin_otp_email": (
        lambda: {"brand": "Qərbi Kaspi Universiteti", "user": _user(), "code": CODE, "otp_expiry_minutes": 5},
        (CODE, "elvin.qurbanov"),
    ),
    "blog/emails/new_post_notification": (
        lambda: {
            "brand": "Qərbi Kaspi Universiteti",
            "post": SimpleNamespace(
                title="Yeni semestr", excerpt="Dərslər başlayır.", get_absolute_url=lambda: "/blog/yeni-semestr/"
            ),
        },
        ("Yeni semestr", "http://testserver/blog/yeni-semestr/"),
    ),
    "contact/email/contact_notification": (
        lambda: {
            "message": _contact_message(),
            "subject_display": "Qəbul",
            "brand": "Qərbi Kaspi Universiteti",
            "site_name": "Qərbi Kaspi Universiteti",
            "reply_url": "https://ems.qku.edu.az/admin/contact/7/reply/",
            "detail_url": "https://ems.qku.edu.az/admin/contact/7/",
        },
        ("Aysel Məmmədova", "aysel@example.com", "https://ems.qku.edu.az/admin/contact/7/reply/"),
    ),
    "contact/email/contact_reply": (
        lambda: {
            "message": _contact_message(),
            "reply_body": "Sənədləri sabah gətirin.",
            "from_email": "info@qku.edu.az",
            "brand": "Qərbi Kaspi Universiteti",
        },
        ("Sənədləri sabah gətirin.", "info@qku.edu.az"),
    ),
    "trial_exams/email/trial_notification": (
        lambda: {
            "request_obj": _trial_request(),
            "brand": "Qərbi Kaspi Universiteti",
            "reply_url": "https://ems.qku.edu.az/admin/trial/3/reply/",
            "detail_url": "https://ems.qku.edu.az/profile/trial/3/",
            "profile_detail_url": "https://ems.qku.edu.az/profile/trial/3/",
            "admin_detail_url": "https://ems.qku.edu.az/admin/trial/3/",
            "file_download_url": "https://ems.qku.edu.az/media/trial/suallar.pdf",
        },
        ("Murad Əliyev", "https://ems.qku.edu.az/profile/trial/3/", "https://ems.qku.edu.az/media/trial/suallar.pdf"),
    ),
    "trial_exams/email/trial_reply": (
        lambda: {
            "request_obj": _trial_request(),
            "reply_body": "Suallar əlavə olundu.",
            "from_email": "info@qku.edu.az",
            "brand": "Qərbi Kaspi Universiteti",
        },
        ("Riyaziyyat", "Suallar əlavə olundu."),
    ),
}


@override_settings(SITE_URL="http://testserver", CONTACT_SUPPORT_EMAIL="support@qku.edu.az")
class EmailTemplatesRenderTest(SimpleTestCase):
    def test_every_html_mail_uses_the_shared_layout_and_keeps_its_variables(self):
        for name, (make_context, needles) in CASES.items():
            with self.subTest(template=name), translation.override("az"):
                html = render_to_string(f"{name}.html", make_context())
                self.assertIn('class="em-preheader"', html)
                self.assertIn("Qərbi Kaspi Universiteti", html)
                self.assertIn("Elektron Universitet", html)
                self.assertNotIn("EMS Arena", html)
                self.assertIn("max-width:600px", html)
                self.assertIn(f"&copy; {timezone.now().year}", html)
                self.assertIn("mailto:support@qku.edu.az", html)
                for needle in needles:
                    self.assertIn(needle, html)

    def test_every_mail_has_a_plain_text_part_without_markup(self):
        for name, (make_context, needles) in CASES.items():
            with self.subTest(template=name), translation.override("az"):
                context = make_context()
                text = plain_text_body(f"{name}.html", context)
                self.assertEqual(text, render_to_string(f"{name}.txt", context).strip() + "\n")
                self.assertNotIn("<", text.replace("<strong>", ""))
                self.assertNotIn("{", text)
                self.assertNotIn("&amp;", text)
                self.assertIn("Elektron Universitet", text)
                self.assertNotIn("EMS Arena", text)
                for needle in needles:
                    self.assertIn(needle, text)

    def test_otp_code_is_in_a_large_monospace_copy_box_with_expiry(self):
        html = render_to_string("accounts/emails/login_otp_email.html", _otp_context())
        box = html[html.index('class="em-code"') :]
        box = box[: box.index("</div>")]
        self.assertIn("monospace", box)
        self.assertIn("letter-spacing:8px", box)
        self.assertIn("user-select:all", box)
        self.assertIn(CODE, box)
        self.assertIn("5 dəqiqə", html)
        self.assertIn("avtomatik göndərilib, cavab yazmayın", html)

    def test_reset_mail_has_a_bulletproof_button_with_link_fallback(self):
        html = render_to_string(
            "accounts/password_reset_email.html",
            {"brand": "Q", "user": _user(), "reset_url": RESET_URL, "otp_code": CODE, "otp_expiry_minutes": 5},
        )
        self.assertIn('class="em-btn"', html)
        self.assertEqual(html.count(f'href="{RESET_URL}"'), 2)
        self.assertIn("Düymə işləmirsə", html)

    def test_staff_notifications_do_not_say_do_not_reply(self):
        # Komanda bildirişində Reply-To müraciətçidir — «cavab yazmayın» yanlış olardı.
        make_context, _needles = CASES["contact/email/contact_notification"]
        html = render_to_string("contact/email/contact_notification.html", make_context())
        self.assertNotIn("cavab yazmayın", html)
        self.assertIn("Avtomatik göndərilmiş bildiriş", html)

    def test_english_otp_mail_is_fully_english(self):
        with translation.override("en"):
            html = render_to_string("accounts/emails/login_otp_email.html", _otp_context())
            text = render_to_string("accounts/emails/login_otp_email.txt", _otp_context())
        for body in (html, text):
            self.assertIn("please do not reply", body)
            for marker in ("cavab yazmayın", "Etibarlılıq", "Kodunuz", "Sualınız"):
                self.assertNotIn(marker, body)
        self.assertIn("Valid for 5 minutes", html)
        self.assertIn("e-University", html)
        self.assertIn("e-University", text)


class EmailChromeTest(SimpleTestCase):
    @override_settings(SITE_URL="https://ems.qku.edu.az/", CONTACT_SUPPORT_EMAIL="support@qku.edu.az")
    def test_public_https_site_gets_an_absolute_logo(self):
        chrome = email_chrome()
        self.assertEqual(chrome["site_url"], "https://ems.qku.edu.az")
        self.assertTrue(chrome["logo_url"].startswith("https://ems.qku.edu.az/"))
        # Universitetin rəsmi emblemi (köhnə məhsul işarəsi yox — sahib 2026-10-15).
        self.assertTrue(chrome["logo_url"].endswith("brand/favicon-192x192.png"))
        self.assertEqual(chrome["support_email"], "support@qku.edu.az")

    def test_private_or_plain_http_site_has_no_logo(self):
        for site_url in ("http://ems.qku.edu.az", "https://127.0.0.1", "https://10.0.0.5:8443", "https://localhost"):
            with self.subTest(site_url=site_url), override_settings(SITE_URL=site_url):
                self.assertEqual(email_chrome()["logo_url"], "")

    @override_settings(CONTACT_SUPPORT_EMAIL="")
    def test_missing_support_address_hides_the_line(self):
        self.assertEqual(email_chrome()["support_email"], "")
        html = render_to_string("admin/emails/admin_otp_email.html", {"user": _user(), "code": CODE})
        self.assertNotIn("Sualınız varsa", html)

    @override_settings(SITE_URL="https://ems.qku.edu.az")
    def test_absolute_url_filter(self):
        self.assertEqual(email_absolute_url("/blog/x/"), "https://ems.qku.edu.az/blog/x/")
        self.assertEqual(email_absolute_url("https://a.b/c"), "https://a.b/c")
        self.assertEqual(email_absolute_url(""), "")


class PlainTextFallbackTest(SimpleTestCase):
    def test_fallback_without_txt_drops_head_style_and_preheader(self):
        html = (
            "<html><head><title>T</title><style>.a{color:red}</style></head><body>"
            '<div class="em-preheader">gizli</div><p>Görünən mətn</p></body></html>'
        )
        text = plain_text_body("nonexistent/template_without_txt.html", {}, html)
        self.assertEqual(text, "Görünən mətn\n")


class SendersAttachBothPartsTest(SimpleTestCase):
    """Göndərənlər mətn hissəsini `.txt` şablondan götürür (əvvəl `strip_tags(html)` idi)."""

    def test_contact_notification_text_part_comes_from_the_txt_template(self):
        from apps.contact import services

        with mock.patch.object(services, "_send_email_with_fallback", return_value=(True, "")) as send:
            services._send_internal_notification(_contact_message())
        kwargs = send.call_args.kwargs
        self.assertIn("Aysel Məmmədova", kwargs["text_body"])
        self.assertNotIn("<td", kwargs["text_body"])
        self.assertNotIn("em-preheader", kwargs["text_body"])
        self.assertIn('class="em-preheader"', kwargs["html_body"])

    def test_trial_reply_text_part_comes_from_the_txt_template(self):
        from apps.trial_exams import services

        with mock.patch.object(services, "send_email_with_fallback", return_value=(True, "")) as send:
            services._send_reply_email(_trial_request(), "Suallar əlavə olundu.", "info")
        kwargs = send.call_args.kwargs
        self.assertIn("Suallar əlavə olundu.", kwargs["text_body"])
        self.assertNotIn("<", kwargs["text_body"])
