"""OTP yoxlama/göndəriş xətalarının istifadəçi mətnləri — bütün OTP axınları üçün TƏK mənbə.

Sahib 2026-10-21: «OTP kodunun vaxtı keçib» deyirdi, halbuki kod səhv və ya yenisi ilə əvəzlənmiş
idi (ikiqat klik → iki kod). Hər səbəb (``OTPVerificationResult.reason``) öz dəqiq mətnini alır;
ilk giriş, parol bərpası (kod və link axınları) və profildə «parolu unutdum» eyni mətnləri göstərir.
"""

from __future__ import annotations

import math

from django.utils import timezone
from django.utils.formats import time_format
from django.utils.translation import pgettext

_CTX = "accounts.otp"


def _until_clock(expires_at) -> str:
    """Bitmə anı istifadəçinin saat qurşağında (Asia/Baku) «14:35» kimi."""
    return time_format(timezone.localtime(expires_at), "H:i")


def otp_validity_hint(expires_at) -> str:
    """«Kod hələ 4 dəqiqə etibarlıdır (14:35-ə qədər).» — ``expires_at`` yoxdursa boş sətir."""
    if not expires_at:
        return ""
    seconds = (expires_at - timezone.now()).total_seconds()
    if seconds <= 0:
        return ""
    minutes = max(1, math.ceil(seconds / 60))
    return pgettext(_CTX, "Kod hələ %(minutes)s dəq. etibarlıdır (%(time)s-ə qədər).") % {
        "minutes": minutes,
        "time": _until_clock(expires_at),
    }


def otp_failure_message(result) -> str:
    """``OTPVerificationResult`` → tərcümə olunmuş, səbəbə uyğun mətn."""
    reason = getattr(result, "reason", "") or ""
    if reason == "invalid":
        left = getattr(result, "remaining_attempts", None)
        message = pgettext(_CTX, "Kod səhvdir. Məktubdakı 6 rəqəmli kodu yoxlayıb yenidən daxil edin.")
        if left:
            message = "%s %s" % (
                message,
                pgettext(_CTX, "Qalan cəhd: %(left)s.") % {"left": left},
            )
        hint = otp_validity_hint(getattr(result, "expires_at", None))
        return f"{message} {hint}".strip()
    if reason == "superseded":
        return pgettext(
            _CTX,
            "Bu kod artıq etibarsızdır — ondan sonra yeni kod göndərilib. Ən son məktubdakı kodu daxil edin.",
        )
    if reason == "expired":
        return pgettext(_CTX, "Kodun vaxtı keçib. Yeni kod istəyin.")
    if reason == "already_used":
        return pgettext(_CTX, "Bu kod artıq istifadə olunub. Lazımdırsa yeni kod istəyin.")
    if reason == "max_attempts":
        return pgettext(_CTX, "Çox sayda səhv cəhd edildi — kod bağlandı. Yeni kod istəyin.")
    if reason == "missing":
        return pgettext(_CTX, "Aktiv təsdiq kodu yoxdur. Yeni kod istəyin.")
    if reason == "invalid_format":
        return pgettext(_CTX, "Kod 6 rəqəmdən ibarət olmalıdır.")
    return pgettext(_CTX, "Kodu yoxlamaq mümkün olmadı. Yenidən cəhd edin.")


def otp_already_sent_message(resend_available_in: int) -> str:
    """İkiqat klik / təkrar göndəriş: yeni kod YOXDUR, əvvəlki məktubdakı kod qüvvədədir."""
    seconds = max(0, int(resend_available_in or 0))
    message = pgettext(
        _CTX,
        "Təsdiq kodu artıq göndərilib — e-poçtunuzu (həm də «Spam» qovluğunu) yoxlayın.",
    )
    if seconds:
        message = "%s %s" % (
            message,
            pgettext(_CTX, "Yeni kodu %(seconds)s san. sonra istəyə bilərsiniz.") % {"seconds": seconds},
        )
    return message


def otp_hourly_limit_message(retry_after: int) -> str:
    minutes = max(1, math.ceil(int(retry_after or 0) / 60))
    return pgettext(_CTX, "Bu e-poçt üçün saatlıq kod limiti dolub. %(minutes)s dəq. sonra yenidən cəhd edin.") % {
        "minutes": minutes
    }


__all__ = [
    "otp_already_sent_message",
    "otp_failure_message",
    "otp_hourly_limit_message",
    "otp_validity_hint",
]
