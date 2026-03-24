"""
core/email_tasks.py
───────────────────
Celery tasks for asynchronous email delivery.

All outbound email should be dispatched through this module so that the
HTTP response is never blocked by SMTP network I/O.

Usage
-----
::

    from core.email_tasks import send_verification_otp_email

    # Enqueue asynchronously (non-blocking)
    send_verification_otp_email.delay(
        user_pk=user.pk,
        code=code,
        expires_at=expires_at.isoformat(),
    )
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, mail_admins
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="core.email_tasks.send_verification_otp_email",
)
def send_verification_otp_email(
    self,
    *,
    user_pk: int,
    code: str,
    expires_at: str | None = None,
    verification_link: str = "",
    otp_expiry_minutes: int = 3,
) -> None:
    """
    Send an OTP verification email to the user asynchronously.

    Parameters
    ----------
    user_pk:
        Primary key of the user to notify.
    code:
        The 6-digit OTP code.
    expires_at:
        ISO-8601 string of the OTP expiry timestamp (UTC).
    verification_link:
        Full URL for the one-click verification link.
    otp_expiry_minutes:
        Human-readable expiry period shown in the email body.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_pk)
    except User.DoesNotExist:
        logger.warning("send_verification_otp_email: user %s not found, skipping", user_pk)
        return

    context = {
        "user": user,
        "code": code,
        "verification_link": verification_link,
        "otp_expiry_minutes": otp_expiry_minutes,
        "expires_at": expires_at,
    }
    text_body = render_to_string("accounts/emails/verification_email.txt", context)
    html_body = render_to_string("accounts/emails/verification_email.html", context)

    try:
        message = EmailMultiAlternatives(
            subject="Email təsdiqi",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        message.attach_alternative(html_body, "text/html")
        message.send()
        logger.info("Verification OTP email sent to user %s", user_pk)
    except Exception as exc:
        logger.exception("Failed to send verification OTP email to user %s: %s", user_pk, exc)
        raise


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="core.email_tasks.send_template_email_async",
)
def send_template_email_async(
    self,
    *,
    subject: str,
    template_name: str,
    context: dict,
    recipient_list: list[str],
    from_email: str | None = None,
) -> None:
    """
    Send a template-based email asynchronously.

    Drop-in async equivalent of ``core.utils.send_template_email``.
    """
    html_message = render_to_string(template_name, context)
    plain_message = strip_tags(html_message)
    sender = from_email or settings.DEFAULT_FROM_EMAIL

    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=sender,
            to=recipient_list,
        )
        message.attach_alternative(html_message, "text/html")
        message.send()
        logger.info("Template email '%s' sent to %d recipient(s)", subject, len(recipient_list))
    except Exception as exc:
        logger.exception("Failed to send template email '%s': %s", subject, exc)
        raise


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    autoretry_for=(Exception,),
    name="core.email_tasks.send_new_post_notification_email",
)
def send_new_post_notification_email(
    self,
    *,
    post_pk: int,
    subscriber_emails: list[str],
) -> None:
    """
    Notify blog subscribers about a new post asynchronously.

    This replaces the synchronous ``send_new_post_notification`` signal
    handler in ``apps/blog/signals.py``.
    """
    from apps.blog.models import Post

    try:
        post = Post.objects.get(pk=post_pk)
    except Post.DoesNotExist:
        logger.warning("send_new_post_notification_email: post %s not found, skipping", post_pk)
        return

    if not subscriber_emails:
        return

    context = {"post": post}
    html_message = render_to_string("blog/email/new_post_notification.html", context)
    plain_message = strip_tags(html_message)

    try:
        message = EmailMultiAlternatives(
            subject=f"Yeni post: {post.title}",
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.DEFAULT_FROM_EMAIL],
            bcc=subscriber_emails,
        )
        message.attach_alternative(html_message, "text/html")
        message.send()
        logger.info(
            "New-post notification for post %s sent to %d subscriber(s)",
            post_pk,
            len(subscriber_emails),
        )
    except Exception as exc:
        logger.exception("Failed to send new-post notification for post %s: %s", post_pk, exc)
        raise
