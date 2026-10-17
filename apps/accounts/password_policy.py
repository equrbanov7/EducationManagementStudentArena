"""Sadə parol siyasəti (sahib 2026-10-15).

Sahib: «Parolu təyin etməni yüngülləşdir, 8 simvol olsun, amma çox da zorlamasın … müəllimlər uzun böyük
kodları yadda saxlaya bilməyəcək — sadə kod qoymağa icazə olsun.»

QAYDA (yeganə mənbə — ``AUTH_PASSWORD_VALIDATORS`` bu validatorları göstərir, bütün axınlar —
ilk giriş, profil «Şifrəni dəyiş», OTP ilə bərpa, RİM / admin «parolu sıfırla», Django admin — ``validate_password``
vasitəsilə məhz bunları işlədir):

* ən azı ``password.min_length`` simvol («Sistem tənzimləmələri», defolt 8);
* tərkib tələbi YOXDUR — böyük hərf, rəqəm, simvol məcburi deyil; tam rəqəmli kod («19850412») və ad/soyada
  oxşar parol qəbul olunur;
* yalnız QISA qadağa siyahısı (``TRIVIAL_PASSWORDS``), tək simvolun təkrarı («aaaaaaaa» — «11111111» siyahıda
  olduğu kimi, QA-1 F12) + istifadəçinin öz istifadəçi adı rədd edilir;
* YALNIZ rəhbər hesablarda (``PrivilegedPasswordValidator``, SEC-1 F5): tam rəqəm / tarix parolu olmaz.

Təxmin hücumuna qarşı əsas müdafiə giriş limitləridir (cihaz / hesab / İP vedrələri və blok geri sayımı —
``apps/accounts/views/auth/_shared.py``, ``login.*_rate`` tənzimləmələri), mürəkkəb parol tələbi deyil.
Brauzer tərəfi (``accounts/js/profile/change_password_strength.js``) eyni qaydanı data-atributlardan oxuyur.
"""

from __future__ import annotations

import re

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
    if len(lowered) > 1 and len(set(lowered)) == 1:  # «aaaaaaaa», «zzzzzzzz» — qısa siyahı hamısını saymır
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


# ── Rəhbər hesablar (SEC-1 F5, 2026-10-17) ──────────────────────────────────────────────────────────────
#: Tam səlahiyyətli rollar — ad ilə; bundan əlavə ``*`` açarı daşıyan istənilən rol (admin səviyyəsi) və
#: istənilən təşkilatın SAHİBİ. Tələbə və müəllim sadə qaydada qalır (sahib 2026-10-15).
PRIVILEGED_ROLE_NAMES = frozenset({"ikt_rehber", "rector", "board_chair"})
#: Yalnız rəqəm və tarix ayırıcıları («19850412», «12.04.1985», «1985-04-12», «12 04 85»).
_NUMERIC_OR_DATE = re.compile(r"^[\d\s./\-]+$")


def is_privileged_account(user) -> bool:
    """Superadmin / Django admin, təşkilat (fərdi deyil) sahibi, RİM rəhbəri, rektor, QŞ sədri və ya ``*`` açarlı rol.

    Review 2026-10-17: sorğular ``bypass_rls()`` altındadır — anonim OTP «parolu unutdum» bərpasında RLS
    konteksti boşdur (üzvlük görünmür) və başqa təşkilatdakı üzvlük də gizlənirdi; rəhbər qaydadan qaçırdı.
    Hər iki sorğu ``user_id`` / ``owner_id`` ilə açıq süzülür (``network_zone`` ilə eyni naxış)."""
    if user is None or not getattr(user, "pk", None):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    if str(getattr(getattr(user, "profile", None), "role", "") or "") == "superadmin":
        return True
    from django.db.models import Q

    from apps.organizations.models import Membership, Organization
    from core.constants import OrganizationType
    from core.rls import bypass_rls

    with bypass_rls():
        # Şəxsi «Workspace» (köhnə fərdi qeydiyyat, ``individual``) sahibi adi istifadəçidir — sayılmır.
        if Organization.objects.filter(owner_id=user.pk).exclude(org_type=OrganizationType.INDIVIDUAL).exists():
            return True
        return (
            Membership.objects.filter(user_id=user.pk, is_active=True, role__is_active=True)
            .filter(Q(role__name__in=PRIVILEGED_ROLE_NAMES) | Q(role__permissions__contains=["*"]))
            .exists()
        )


def is_numeric_or_date(password: str) -> bool:
    return bool(_NUMERIC_OR_DATE.fullmatch((password or "").strip()))


class PrivilegedPasswordValidator:
    """Rəhbər hesabda yalnız rəqəmdən / tarixdən ibarət parol olmaz; qalan hamı üçün heç nə dəyişmir."""

    def validate(self, password, user=None):
        if is_numeric_or_date(password) and is_privileged_account(user):
            raise ValidationError(
                pgettext(
                    _CTX,
                    "Rəhbər hesabı üçün yalnız rəqəmdən və ya tarixdən ibarət parol olmaz — ən azı bir hərf əlavə edin.",
                ),
                code="password_numeric_privileged",
            )

    def get_help_text(self):
        return pgettext(_CTX, "Rəhbər hesablarda parol yalnız rəqəmdən və ya tarixdən ibarət ola bilməz.")


__all__ = [
    "DEFAULT_MIN_LENGTH",
    "MinimumLengthValidator",
    "PRIVILEGED_ROLE_NAMES",
    "PrivilegedPasswordValidator",
    "is_numeric_or_date",
    "is_privileged_account",
    "TRIVIAL_PASSWORDS",
    "TrivialPasswordValidator",
    "help_text",
    "is_trivial",
    "min_length",
]
