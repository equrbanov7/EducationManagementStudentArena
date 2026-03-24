"""
Tests for core.email_tasks — Celery async email delivery tasks.

These tests run tasks synchronously (CELERY_TASK_ALWAYS_EAGER=True is set in
test settings) so no broker is required.  The email backend is the console
backend in tests, so no real messages are sent.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class SendVerificationOtpEmailTaskTest(TestCase):
    """send_verification_otp_email Celery task tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="password123",
        )

    def test_task_sends_email_to_user(self):
        from django.core import mail

        from core.email_tasks import send_verification_otp_email

        send_verification_otp_email.delay(
            user_pk=self.user.pk,
            code="123456",
            expires_at=None,
            verification_link="http://testserver/accounts/verify/?token=abc",
            otp_expiry_minutes=3,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_task_skips_missing_user(self):
        from django.core import mail

        from core.email_tasks import send_verification_otp_email

        # Use a PK that does not exist
        send_verification_otp_email.delay(
            user_pk=999999,
            code="000000",
        )

        self.assertEqual(len(mail.outbox), 0)

    def test_task_email_contains_otp_code(self):
        from django.core import mail

        from core.email_tasks import send_verification_otp_email

        otp_code = "654321"
        send_verification_otp_email.delay(
            user_pk=self.user.pk,
            code=otp_code,
            otp_expiry_minutes=5,
        )

        self.assertEqual(len(mail.outbox), 1)
        # The plain-text body or HTML alternative should contain the code
        message = mail.outbox[0]
        body_contains_code = otp_code in message.body or any(
            otp_code in alt_body for alt_body, _ in getattr(message, "alternatives", [])
        )
        self.assertTrue(body_contains_code)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class SendTemplateEmailAsyncTaskTest(TestCase):
    """send_template_email_async Celery task tests."""

    def test_task_sends_template_email(self):
        from django.core import mail

        from core.email_tasks import send_template_email_async

        send_template_email_async.delay(
            subject="Test subject",
            template_name="email_templates/welcome_email.html",
            context={},
            recipient_list=["recipient@example.com"],
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("recipient@example.com", mail.outbox[0].to)
        self.assertEqual(mail.outbox[0].subject, "Test subject")

    def test_task_uses_default_from_email(self):
        from django.conf import settings
        from django.core import mail

        from core.email_tasks import send_template_email_async

        send_template_email_async.delay(
            subject="From test",
            template_name="email_templates/welcome_email.html",
            context={},
            recipient_list=["someone@example.com"],
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, settings.DEFAULT_FROM_EMAIL)

    def test_task_uses_explicit_from_email(self):
        from django.core import mail

        from core.email_tasks import send_template_email_async

        send_template_email_async.delay(
            subject="Custom from",
            template_name="email_templates/welcome_email.html",
            context={},
            recipient_list=["someone@example.com"],
            from_email="custom@example.com",
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, "custom@example.com")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class SendNewPostNotificationEmailTaskTest(TestCase):
    """send_new_post_notification_email Celery task tests."""

    def _create_post(self):
        from apps.blog.models import Post

        user = User.objects.create_user(
            username="author",
            email="author@example.com",
            password="password",
        )
        return Post.objects.create(
            title="Test Post",
            content="Test content",
            author=user,
            is_published=True,
        )

    def test_task_sends_notification_to_subscribers(self):
        from django.core import mail

        from core.email_tasks import send_new_post_notification_email

        post = self._create_post()
        subscriber_emails = ["sub1@example.com", "sub2@example.com"]

        send_new_post_notification_email.delay(
            post_pk=post.pk,
            subscriber_emails=subscriber_emails,
        )

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        # Sent as BCC to protect subscriber privacy
        self.assertEqual(sorted(message.bcc), sorted(subscriber_emails))

    def test_task_skips_when_no_subscribers(self):
        from django.core import mail

        from core.email_tasks import send_new_post_notification_email

        post = self._create_post()

        send_new_post_notification_email.delay(
            post_pk=post.pk,
            subscriber_emails=[],
        )

        self.assertEqual(len(mail.outbox), 0)

    def test_task_skips_missing_post(self):
        from django.core import mail

        from core.email_tasks import send_new_post_notification_email

        send_new_post_notification_email.delay(
            post_pk=999999,
            subscriber_emails=["sub@example.com"],
        )

        self.assertEqual(len(mail.outbox), 0)
