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

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from celery import shared_task

logger = logging.getLogger(__name__)


def _otp_subject_for_purpose(purpose: str) -> str:
    return {
        "signup": "EMSArena email təsdiqi",
        "login": "EMSArena giriş OTP kodu",
        "password_reset": "EMSArena şifrə sıfırlama OTP kodu",
        "admin_login": "EMSArena admin giriş OTP kodu",
    }.get(purpose, "EMSArena OTP kodu")


def _otp_headline_for_purpose(purpose: str) -> str:
    return {
        "signup": "Email təsdiqi",
        "login": "Giriş təsdiqi",
        "password_reset": "Şifrə sıfırlama təsdiqi",
        "admin_login": "Admin giriş təsdiqi",
    }.get(purpose, "OTP təsdiqi")


def _otp_intro_for_purpose(purpose: str) -> str:
    return {
        "signup": "hesabınızı aktivləşdirmək",
        "login": "girişinizi təsdiqləmək",
        "password_reset": "şifrəni sıfırlama əməliyyatını təsdiqləmək",
        "admin_login": "admin girişinizi təsdiqləmək",
    }.get(purpose, "əməliyyatı təsdiqləmək")


def _otp_cta_for_purpose(purpose: str) -> str:
    return {
        "signup": "Emaili təsdiqlə",
        "login": "Girişi təsdiqlə",
        "password_reset": "Şifrəni sıfırla",
        "admin_login": "Admin girişi təsdiqlə",
    }.get(purpose, "OTP-ni təsdiqlə")


def _otp_template_prefix_for_purpose(purpose: str) -> str:
    if purpose == "login":
        return "accounts/emails/login_otp_email"
    return "accounts/emails/verification_email"


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="core.email_tasks.send_account_otp_email",
)
def send_account_otp_email(
    self,
    *,
    user_pk: int | None = None,
    recipient_email: str,
    recipient_name: str = "",
    purpose: str = "signup",
    code: str,
    expires_at: str | None = None,
    verification_link: str = "",
    otp_expiry_minutes: int = 5,
) -> None:
    """
    Send a purpose-specific OTP email asynchronously.
    """
    user = None
    resolved_name = recipient_name
    if user_pk:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            user = User.objects.get(pk=user_pk)
        except User.DoesNotExist:
            logger.warning("send_account_otp_email: user %s not found, continuing without user object", user_pk)
        else:
            resolved_name = resolved_name or user.get_full_name().strip() or user.username

    context = {
        "user": user,
        "recipient_name": resolved_name or recipient_email,
        "email": recipient_email,
        "headline": _otp_headline_for_purpose(purpose),
        "otp_intro_action": _otp_intro_for_purpose(purpose),
        "cta_label": _otp_cta_for_purpose(purpose),
        "purpose": purpose,
        "code": code,
        "verification_link": verification_link,
        "otp_expiry_minutes": otp_expiry_minutes,
        "expires_at": expires_at,
    }
    template_prefix = _otp_template_prefix_for_purpose(purpose)
    text_body = render_to_string(f"{template_prefix}.txt", context)
    html_body = render_to_string(f"{template_prefix}.html", context)

    try:
        message = EmailMultiAlternatives(
            subject=_otp_subject_for_purpose(purpose),
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient_email],
        )
        message.attach_alternative(html_body, "text/html")
        message.send()
        logger.info("Purpose-specific OTP email sent to %s for purpose %s", recipient_email, purpose)
    except Exception as exc:
        logger.exception("Failed to send purpose-specific OTP email to %s: %s", recipient_email, exc)
        raise


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
    otp_expiry_minutes: int = 5,
) -> None:
    """Backward-compatible Celery task for signup verification OTP emails."""

    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_pk)
    except User.DoesNotExist:
        logger.warning("send_verification_otp_email: user %s not found, skipping", user_pk)
        return

    send_account_otp_email.run(
        user_pk=user_pk,
        recipient_email=user.email,
        recipient_name=user.get_full_name().strip() or user.username,
        purpose="signup",
        code=code,
        expires_at=expires_at,
        verification_link=verification_link,
        otp_expiry_minutes=otp_expiry_minutes,
    )


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
    html_message = render_to_string("accounts/emails/new_post_notification.html", context)
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
