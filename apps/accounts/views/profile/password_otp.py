"""Şifrə dəyişmə üçün email OTP sorğusu (profil kabineti).

İstifadəçi mövcud şifrəsini unudubsa, «Şifrəni dəyiş» bölməsindən öz təsdiqli
emailinə birdəfəlik kod istəyir. Kod mövcud PASSWORD_RESET OTP infrastrukturu
ilə göndərilir (saatlıq limit + resend cooldown ``issue_email_otp``-dədir),
yoxlama isə profil POST axınındakı ``OTPPasswordResetConfirmForm``-da gedir.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.accounts.models import EmailOTP
from core.utils import get_auth_otp_expiry_seconds, get_auth_otp_resend_cooldown_seconds

from ...services import OTPRateLimitError, OTPResendCooldownError, send_otp_email

logger = logging.getLogger(__name__)


def mask_email(email):
    """«ab***@domen» — OTP UI-də ünvanı tam göstərmədən istiqamətləndirmək üçün."""
    email = str(email or "")
    if "@" not in email:
        return email
    local, _, domain = email.partition("@")
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}***@{domain}"


@login_required
@require_POST
def change_password_otp_request(request):
    """Daxil olmuş istifadəçinin öz emailinə şifrə-dəyişmə OTP kodu göndərir."""
    email = (request.user.email or "").strip()
    if not email:
        return JsonResponse(
            {
                "success": False,
                "error": pgettext(
                    "accounts.password_otp",
                    "Hesabınızda email ünvanı yoxdur. Əvvəlcə profilə email əlavə edin.",
                ),
            },
            status=400,
        )

    try:
        send_otp_email(
            email,
            user=request.user,
            purpose=EmailOTP.Purpose.PASSWORD_RESET,
            request=request,
            enforce_cooldown=True,
        )
    except OTPResendCooldownError as exc:
        return JsonResponse(
            {
                "success": False,
                "error": pgettext("accounts.password_otp", "Yeni kod üçün bir az gözləyin."),
                "retry_after": exc.retry_after,
            },
            status=429,
        )
    except OTPRateLimitError as exc:
        return JsonResponse(
            {
                "success": False,
                "error": pgettext(
                    "accounts.password_otp", "Bu email üçün saatlıq kod limiti dolub. Daha sonra yenidən cəhd edin."
                ),
                "retry_after": exc.retry_after,
            },
            status=429,
        )
    except Exception:
        logger.exception("Password-change OTP delivery failed for user %s", request.user.pk)
        return JsonResponse(
            {
                "success": False,
                "error": pgettext("accounts.password_otp", "Kod göndərilə bilmədi. Bir az sonra yenidən cəhd edin."),
            },
            status=502,
        )

    return JsonResponse(
        {
            "success": True,
            "detail": pgettext("accounts.password_otp", "Kod %(email)s ünvanına göndərildi.")
            % {"email": mask_email(email)},
            "expires_in": get_auth_otp_expiry_seconds(),
            "resend_available_in": get_auth_otp_resend_cooldown_seconds(),
        },
        status=202,
    )
