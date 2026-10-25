"""Parol bərpası linkinin token-i — ömrü OTP kodu ilə EYNİDİR (2026-10-25).

Kök səbəb: bərpa məktubu «Link və OTP kodu N dəqiqə etibarlıdır» deyir; N «Sistem tənzimləmələri»ndəki
``otp.expiry_minutes``-dir (prod: 60). Django-nun ``default_token_generator``-u isə linki
``settings.PASSWORD_RESET_TIMEOUT``-a görə yoxlayır — o, mühitdən gəlir (prod ``.env``: 300 san). Nəticə:
məktubdakı «Şifrəni yenilə» düyməsi 5 dəqiqədən sonra «Link etibarsızdır» göstərirdi, halbuki məktub və kod
hələ 60 dəqiqə keçərli idi. İstifadəçi yeni kod istəyir, yenə linkə basır — dövr (prodda bir hesab 8 kod).

Bu generator imzanı Django ilə EYNİ qurur (eyni ``key_salt``, eyni heş dəyəri — artıq göndərilmiş linklər
keçərli qalır), yalnız vaxt həddini OTP-nin işləmə vaxtındakı ömründən (``get_auth_otp_expiry_seconds``) götürür.
Link onsuz da OTP kodu olmadan parolu dəyişmir (``OTPPasswordResetConfirmForm``) — ömürlərin bərabərliyi
təhlükəsizlik sərhədini dəyişmir.
"""

from __future__ import annotations

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import constant_time_compare
from django.utils.http import base36_to_int

from core.utils import get_auth_otp_expiry_seconds


def reset_link_lifetime_seconds() -> int:
    """Bərpa linkinin ömrü — məktubda yazılan OTP müddəti ilə eyni (işləmə vaxtında oxunur)."""
    return get_auth_otp_expiry_seconds()


class OTPWindowPasswordResetTokenGenerator(PasswordResetTokenGenerator):
    """``PasswordResetTokenGenerator`` — vaxt həddi ``PASSWORD_RESET_TIMEOUT`` yox, OTP ömrüdür."""

    def check_token(self, user, token):
        if not (user and token):
            return False
        try:
            ts_b36, _hash = str(token).split("-")
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False
        for secret in [self.secret, *self.secret_fallbacks]:
            if constant_time_compare(self._make_token_with_timestamp(user, ts, secret), token):
                break
        else:
            return False
        return (self._num_seconds(self._now()) - ts) <= reset_link_lifetime_seconds()


password_reset_token_generator = OTPWindowPasswordResetTokenGenerator()

__all__ = ["OTPWindowPasswordResetTokenGenerator", "password_reset_token_generator", "reset_link_lifetime_seconds"]
