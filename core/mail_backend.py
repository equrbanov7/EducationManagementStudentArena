"""Hesab üzrə marşrutlanan SMTP backend-i (sahib 2026-10-01: «Brevo olmasın», universitet poçtu).

Universitetin poçtu Microsoft 365-dədir (MX: wcu-edu-az.mail.protection.outlook.com). İki poçt qutusu var:

* ``verification@`` — doğrulama kodları və qalan bütün sistem məktubları (default hesab:
  ``EMAIL_HOST_USER`` / ``EMAIL_HOST_PASSWORD``);
* ``recovery@`` — parol bərpası (``EMAIL_RECOVERY_HOST_USER`` / ``EMAIL_RECOVERY_HOST_PASSWORD``).

M365 məktubu yalnız giriş edən poçt qutusunun ünvanından (From) qəbul edir — başqa ünvan
«SendAsDenied» ilə rədd olunur. Ona görə hər məktub From ünvanına görə hesaba bağlanır:
From = recovery qutusu → recovery hesabı; qalan hər şey → default hesab, From isə default
qutunun ünvanına bərabərləşdirilir (görünən ad saxlanılır, yoxdursa sayt adı qoyulur).

Yalnız ``EMAIL_BACKEND=core.mail_backend.AccountRoutingEmailBackend`` olanda işləyir; env verilməyibsə
Django-nun adi SMTP backend-i olduğu kimi qalır.
"""

from __future__ import annotations

import logging
import smtplib
import time
from email.utils import formataddr, parseaddr

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend

logger = logging.getLogger(__name__)

#: 2026-10-02: M365 bir qutuya ≤3 eyni-anlı bağlantı və ~30 məktub/dəq verir; artığını MÜVƏQQƏTİ 4xx ilə
#: rədd edir («421/432 4.3.2 concurrent connections», throttling). Sinxron OTP göndərişində istifadəçi xəta
#: görməsin deyə qısa fasilə ilə təkrar; son cəhd digər qutudan (verification@ ↔ recovery@).
RETRY_DELAYS_SECONDS = (0.6, 1.8)


def _is_transient(exc) -> bool:
    """Müvəqqəti SMTP xətası: 4xx cavab kodu və ya bağlantının kəsilməsi / timeout."""
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [code for code, _msg in (exc.recipients or {}).values()]
        return bool(codes) and all(400 <= int(code) < 500 for code in codes)
    if isinstance(exc, smtplib.SMTPResponseException):
        return 400 <= int(exc.smtp_code) < 500
    return isinstance(exc, (smtplib.SMTPServerDisconnected, ConnectionError, TimeoutError))


def _address(value: str | None) -> str:
    return (parseaddr(value or "")[1] or "").strip().lower()


def default_sender_address() -> str:
    return _address(getattr(settings, "DEFAULT_FROM_EMAIL", "")) or _address(getattr(settings, "EMAIL_HOST_USER", ""))


def recovery_sender_address() -> str:
    user = _address(getattr(settings, "EMAIL_RECOVERY_HOST_USER", ""))
    password = getattr(settings, "EMAIL_RECOVERY_HOST_PASSWORD", "") or ""
    return user if user and password else ""


def _display_name(value: str | None) -> str:
    name = (parseaddr(value or "")[0] or "").strip()
    return name or (getattr(settings, "EMAIL_FROM_NAME", "") or getattr(settings, "SITE_BRAND_NAME", "") or "").strip()


class AccountRoutingEmailBackend(BaseEmailBackend):
    """Hər məktubu From ünvanına uyğun SMTP hesabı ilə göndərir (M365 SendAs qaydası)."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        # get_connection(timeout=...) kimi açar sözlər hər alt bağlantıya ötürülür;
        # username/password isə hesabdan gəlir (çağıranın verdiyi dəyər nəzərə alınmır).
        kwargs.pop("username", None)
        kwargs.pop("password", None)
        self._smtp_kwargs = kwargs

    def _accounts(self) -> dict[str, tuple[str, str]]:
        accounts = {
            "default": (
                getattr(settings, "EMAIL_HOST_USER", "") or "",
                getattr(settings, "EMAIL_HOST_PASSWORD", "") or "",
            )
        }
        if recovery_sender_address():
            accounts["recovery"] = (settings.EMAIL_RECOVERY_HOST_USER, settings.EMAIL_RECOVERY_HOST_PASSWORD)
        return accounts

    def _route(self, message) -> str:
        sender = _address(message.from_email)
        recovery = recovery_sender_address()
        if recovery and sender == recovery:
            return "recovery"
        default_address = default_sender_address()
        if default_address and sender != default_address:
            message.from_email = formataddr((_display_name(message.from_email), default_address))
        elif default_address and not parseaddr(message.from_email or "")[0]:
            message.from_email = formataddr((_display_name(message.from_email), default_address))
        return "default"

    def _backend(self, credentials):
        username, password = credentials
        return SMTPEmailBackend(
            username=username or None,
            password=password or None,
            fail_silently=False,
            **self._smtp_kwargs,
        )

    def _send_one(self, backend, key, message, accounts):
        """Bir məktub; müvəqqəti (4xx/bağlantı) xətada fasilə ilə təkrar, son cəhd digər qutudan.

        Qaytarır: ``(göndərilən_say, istifadə_olunan_backend)`` — xəta olubsa təzə backend qaytarılır ki,
        qrupun qalan məktubları qırılmış bağlantıya yazılmasın.
        """
        other = "recovery" if key == "default" else "default"
        plan = [key] * (len(RETRY_DELAYS_SECONDS) + 1)
        if other in accounts and other != key:
            plan[-1] = other
        last_exc = None
        for attempt, account_key in enumerate(plan):
            if attempt:
                time.sleep(RETRY_DELAYS_SECONDS[attempt - 1])
                if account_key != key:
                    address = _address(accounts[account_key][0])
                    message.from_email = formataddr((_display_name(message.from_email), address))
                backend.close()
                backend = self._backend(accounts[account_key])
            try:
                return (backend.send_messages([message]) or 0), backend
            except Exception as exc:  # noqa: BLE001 — təsnif olunur, keçici deyilsə yuxarı ötürülür
                if not _is_transient(exc):
                    raise
                last_exc = exc
                logger.warning(
                    "SMTP keçici xəta (%s), cəhd %s/%s, hesab=%s: %s",
                    type(exc).__name__,
                    attempt + 1,
                    len(plan),
                    account_key,
                    str(exc)[:200],
                )
        raise last_exc

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        accounts = self._accounts()
        groups: dict[str, list] = {}
        for message in email_messages:
            groups.setdefault(self._route(message), []).append(message)
        sent = 0
        for key, messages in groups.items():
            backend = self._backend(accounts.get(key, accounts["default"]))
            try:
                for message in messages:
                    try:
                        count, backend = self._send_one(backend, key, message, accounts)
                        sent += count
                    except Exception:
                        if not self.fail_silently:
                            raise
                        logger.exception("SMTP göndərişi alınmadı (fail_silently)")
            finally:
                backend.close()
        return sent


__all__ = ["AccountRoutingEmailBackend", "default_sender_address", "recovery_sender_address"]
