"""Sadə parol siyasəti (sahib 2026-10-15).

Sahib: «Parolu təyin etməni yüngülləşdir, 8 simvol olsun, amma çox da zorlamasın … müəllimlər uzun böyük
kodları yadda saxlaya bilməyəcək — sadə kod qoymağa icazə olsun.»

QAYDA (yeganə mənbə — ``AUTH_PASSWORD_VALIDATORS`` bu iki validatoru göstərir, bütün axınlar —
ilk giriş, profil «Şifrəni dəyiş», OTP ilə bərpa, RİM / admin «parolu sıfırla», Django admin — ``validate_password``
vasitəsilə məhz bunları işlədir):

* ən azı ``password.min_length`` simvol («Sistem tənzimləmələri», defolt 8);
* tərkib tələbi YOXDUR — böyük hərf, rəqəm, simvol məcburi deyil; tam rəqəmli kod («19850412») və ad/soyada
  oxşar parol qəbul olunur;
* yalnız QISA qadağa siyahısı (``TRIVIAL_PASSWORDS``) + istifadəçinin öz istifadəçi adı rədd edilir.

Təxmin hücumuna qarşı əsas müdafiə giriş limitləridir (cihaz / hesab / İP vedrələri və blok geri sayımı —
``apps/accounts/views/auth/_shared.py``, ``login.*_rate`` tənzimləmələri), mürəkkəb parol tələbi deyil.
Brauzer tərəfi (``accounts/js/profile/change_password_strength.js``) eyni qaydanı data-atributlardan oxuyur.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

_CTX = "accounts.password_policy"
DEFAULT_MIN_LENGTH = 8

#: Ən çox təxmin edilən parollar — kiçik hərflə müqayisə olunur. Siyahı QƏSDƏN qısadır: Django-nun 20 000
#: sətirlik ``CommonPasswordValidator``-u şəxsi, amma sadə kodları da rədd edirdi.
TRIVIAL_PASSWORDS = frozenset(
    {
        "12345678",
        "123456789",
        "1234567890",
        "11111111",
        "00000000",
        "87654321",
        "password",
        "qwerty12",
        "qwertyui",
        "parol123",
        "abcd1234",
        "12341234",
        "11223344",
    }
)


def min_length() -> int:
    """Cari minimum uzunluq — «Sistem tənzimləmələri» (``password.min_length``), oxunmasa defolt."""
    from core import runtime_settings

    try:
        return runtime_settings.get_int("password.min_length")
    except Exception:  # noqa: BLE001 — tənzimləmə oxunmasa parol təyini dayanmamalıdır
        return DEFAULT_MIN_LENGTH


def is_trivial(password: str, user=None) -> bool:
    lowered = (password or "").strip().lower()
    if lowered in TRIVIAL_PASSWORDS:
        return True
    username = (getattr(user, "username", "") or "").strip().lower()
    return bool(username) and lowered == username


def help_text() -> str:
    return pgettext(_CTX, "Ən azı %(min_length)d simvol. Yadda saxlaya biləcəyiniz sadə parol da olar.") % {
        "min_length": min_length()
    }


class MinimumLengthValidator:
    """Yalnız uzunluq — hədd «Sistem tənzimləmələri»ndən oxunur."""

    def validate(self, password, user=None):
        limit = min_length()
        if len(password or "") < limit:
            raise ValidationError(
                pgettext(_CTX, "Parol ən azı %(min_length)d simvol olmalıdır."),
                code="password_too_short",
                params={"min_length": limit},
            )

    def get_help_text(self):
        return help_text()


class TrivialPasswordValidator:
    """Qısa qadağa siyahısı + istifadəçi adının özü."""

    def validate(self, password, user=None):
        if is_trivial(password, user):
            raise ValidationError(
                pgettext(_CTX, "Bu parol çox asan təxmin olunur. Başqa birini seçin."),
                code="password_too_common",
            )

    def get_help_text(self):
        return pgettext(_CTX, "«12345678», «password» kimi çox yayılmış parollar və istifadəçi adınız olmaz.")


__all__ = [
    "DEFAULT_MIN_LENGTH",
    "MinimumLengthValidator",
    "TRIVIAL_PASSWORDS",
    "TrivialPasswordValidator",
    "help_text",
    "is_trivial",
    "min_length",
]
