"""İstifadəçinin ÖZ istifadəçi adını dəyişməsi (sahib 2026-10-20: «hər kəs öz username-ni dəyişə bilər»).

Qayda (tələbə və əməkdaş üçün eyni):

* Ad kanonik formaya salınır (``canonical_identity``: NFKC + trim + kiçik hərf) — giriş axtarışı və bazadakı
  unikal ifadə indeksi ilə EYNİ forma, ona görə ``Elvin.Q`` / ``elvin.q`` toqquşması əvvəlcədən tutulur.
* 3–30 simvol; yalnız latın hərfləri ``a–z``, rəqəmlər, nöqtə, alt xətt, defis; hərflə başlayır, hərf və ya
  rəqəmlə bitir; iki ayırıcı yan-yana gələ bilməz (``ad..soyad``, ``ad._soyad``). ``@`` olmadığı üçün yeni ad heç
  vaxt kiminsə e-poçtu ilə toqquşmur (giriş «ad VƏ YA e-poçt» qəbul edir — bax ``backends.single_login_candidate``).
* Rezerv adlar (``admin``, ``root``, ``rim`` …) və xüsusi mənalı prefikslər (``qa.`` — test hesabı sayılır və
  məcburi profil qapısından azaddır; ``stress_`` / ``monitor_demo_`` — seed təmizləmə komandaları silir) qadağandır.
* Mövcud parol (``check_password``) məcburidir; cəhdlər istifadəçi başına məhdudlaşdırılır (parol brute-force-u
  bu formadan keçməsin). Uğurlu dəyişiklikdən sonra «Sistem tənzimləmələri» → ``profile.username_change_cooldown_days``
  gün gözləmək lazımdır; ``profile.username_change_enabled`` söndürüləndə hissə gizlənir və server rədd edir.

Uğurda: ``auth_user.username`` kilidlənmiş sətirdə yenilənir, ``username_changed_at`` yazılır, audit sətri
(köhnə → yeni) qalır, istifadəçiyə in-app bildiriş + e-poçt (COMMIT-dən sonra, best-effort) gedir. Sessiya
QALIR (Django sessiya hash-i parola bağlıdır, ada yox). Köhnə ad dərhal işləməz olur.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import formats, timezone
from django.utils.translation import pgettext

from core import runtime_settings
from core.rate_limit import record_rate_limit_hit

from ..identity import canonical_identity, canonical_identity_queryset

logger = logging.getLogger(__name__)

CTX = "accounts.username_change"
MIN_LENGTH = 3
MAX_LENGTH = 30
RATE_SCOPE = "username_change"
#: Cəhd limiti (istifadəçi başına) — mühitdən ``USERNAME_CHANGE_RATE_LIMIT`` ilə dəyişə bilər.
DEFAULT_RATE = "10/1h"
KEY_ENABLED = "profile.username_change_enabled"
KEY_COOLDOWN = "profile.username_change_cooldown_days"

_PATTERN = re.compile(r"^[a-z][a-z0-9._-]*[a-z0-9]$")
_DOUBLE_SEPARATOR = re.compile(r"[._-]{2}")
_SEPARATORS = "._-"

#: Rəsmi / sistem rolu kimi görünən adlar — həm özləri, həm də ``<ad>.``, ``<ad>_``, ``<ad>-``, ``<ad><rəqəm>``.
RESERVED_USERNAMES = frozenset(
    {
        "abuse", "admin", "administrator", "alerts", "anonymous", "api", "celery", "dekan", "django", "ems",
        "emsarena", "help", "helpdesk", "hostmaster", "hr", "info", "kadr", "mail", "moderator", "muhasib",
        "noreply", "no-reply", "none", "null", "operator", "ops", "owner", "postmaster", "qku", "rector",
        "recovery", "registrar", "rektor", "rim", "root", "security", "staff", "superadmin", "superuser",
        "support", "sys", "sysadmin", "system", "test", "undefined", "user", "verification", "wcu", "webmaster",
        "www",
    }
)  # fmt: skip
#: Kodda XÜSUSİ mənası olan prefikslər (bax modul sənədi).
RESERVED_PREFIXES = ("qa.", "myedu.", "numune.", "stress_", "monitor_demo_")


class UsernameChangeError(Exception):
    """İstifadəçiyə göstərilən, PII-siz səbəb (``code`` — testlər / audit üçün sabit)."""

    def __init__(self, code: str, message: str):
        super().__init__(code, message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class UsernameChangeResult:
    old_username: str
    new_username: str


# ── «Sistem tənzimləmələri» oxu nöqtəsi ────────────────────────────────────────────────────────────


def change_enabled() -> bool:
    return runtime_settings.get_bool(KEY_ENABLED)


def cooldown_days() -> int:
    return max(0, runtime_settings.get_int(KEY_COOLDOWN))


# ── Yoxlamalar ───────────────────────────────────────────────────────────────────────────────────────


def normalize_username(raw) -> str:
    return canonical_identity(raw)


def _is_reserved(value: str) -> bool:
    if value.startswith(RESERVED_PREFIXES):
        return True
    for name in RESERVED_USERNAMES:
        if value == name:
            return True
        if value.startswith(name):
            rest = value[len(name) :]
            if rest[0] in _SEPARATORS or rest.isdigit():
                return True
    return False


def validate_username(value: str) -> None:
    """Format və rezerv yoxlaması (baza sorğusu YOXDUR). Xəta → :class:`UsernameChangeError`."""
    if not value:
        raise UsernameChangeError("required", pgettext(CTX, "Yeni istifadəçi adını yazın."))
    if not (MIN_LENGTH <= len(value) <= MAX_LENGTH):
        raise UsernameChangeError(
            "length",
            pgettext(CTX, "İstifadəçi adı %(min)s–%(max)s simvol olmalıdır.") % {"min": MIN_LENGTH, "max": MAX_LENGTH},
        )
    if not _PATTERN.match(value) or _DOUBLE_SEPARATOR.search(value):
        raise UsernameChangeError(
            "pattern",
            pgettext(
                CTX,
                "İstifadəçi adında yalnız latın hərfləri (a–z), rəqəmlər, nöqtə, alt xətt və defis ola bilər; ad "
                "hərflə başlamalı, hərf və ya rəqəmlə bitməlidir, iki ayırıcı yan-yana gələ bilməz.",
            ),
        )
    if _is_reserved(value):
        raise UsernameChangeError("reserved", pgettext(CTX, "Bu istifadəçi adı sistem üçün ayrılıb, başqasını seçin."))


def next_change_at(profile):
    """Növbəti dəyişikliyin mümkün olduğu an; indi mümkündürsə ``None``."""
    changed_at = getattr(profile, "username_changed_at", None)
    days = cooldown_days()
    if changed_at is None or days <= 0:
        return None
    allowed_at = changed_at + timedelta(days=days)
    return allowed_at if allowed_at > timezone.now() else None


def _format_moment(value) -> str:
    return formats.date_format(timezone.localtime(value), "d.m.Y H:i")


def _cooldown_error(allowed_at) -> UsernameChangeError:
    return UsernameChangeError(
        "cooldown",
        pgettext(CTX, "İstifadəçi adını yenidən %(date)s tarixindən sonra dəyişə bilərsiniz.")
        % {"date": _format_moment(allowed_at)},
    )


def _hit_rate_limit(user) -> None:
    rate = getattr(settings, "USERNAME_CHANGE_RATE_LIMIT", DEFAULT_RATE)
    limited, retry_after = record_rate_limit_hit(RATE_SCOPE, rate, user.pk)
    if limited:
        minutes = max(1, -(-int(retry_after or 60) // 60))
        raise UsernameChangeError(
            "rate_limited",
            pgettext(CTX, "Çox sayda cəhd edildi. %(minutes)s dəqiqə sonra yenidən yoxlayın.") % {"minutes": minutes},
        )


def _taken(value: str, *, exclude_pk) -> bool:
    users = get_user_model()._default_manager.exclude(pk=exclude_pk)
    return canonical_identity_queryset(users, "username", value, alias="_new_username_key").exists()


def _taken_error() -> UsernameChangeError:
    return UsernameChangeError("taken", pgettext(CTX, "Bu istifadəçi adı artıq istifadə olunur."))


# ── Kart vəziyyəti (şablon) ─────────────────────────────────────────────────────────────────────────


def card_state(user) -> dict:
    """«Profil redaktə» kartı üçün: açıqdırmı, gözləmə varsa nə vaxta qədər."""
    if not getattr(user, "is_authenticated", False) or not change_enabled():
        return {"enabled": False}
    profile = getattr(user, "profile", None)
    allowed_at = next_change_at(profile) if profile is not None else None
    return {
        "enabled": True,
        "current": user.username,
        "min_length": MIN_LENGTH,
        "max_length": MAX_LENGTH,
        "cooldown_days": cooldown_days(),
        "locked_until": _format_moment(allowed_at) if allowed_at else "",
    }


# ── Dəyişiklik ───────────────────────────────────────────────────────────────────────────────────────


def change_own_username(*, user, new_username, password, request=None) -> UsernameChangeResult:
    """İstifadəçinin öz adını dəyişir. Xəta → :class:`UsernameChangeError` (heç nə yazılmır)."""
    from apps.accounts.models import UserProfile

    if not change_enabled():
        raise UsernameChangeError("disabled", pgettext(CTX, "İstifadəçi adını dəyişmək hazırda mümkün deyil."))
    _hit_rate_limit(user)

    profile = UserProfile.objects.filter(user_id=user.pk).first()
    allowed_at = next_change_at(profile)
    if allowed_at is not None:
        raise _cooldown_error(allowed_at)

    value = normalize_username(new_username)
    validate_username(value)
    if value == canonical_identity(user.username):
        raise UsernameChangeError("same", pgettext(CTX, "Yeni istifadəçi adı cari addan fərqli olmalıdır."))
    if not password or not user.check_password(password):
        raise UsernameChangeError("wrong_password", pgettext(CTX, "Cari parol yanlışdır."))

    User = get_user_model()
    with transaction.atomic():
        locked = User._default_manager.select_for_update().get(pk=user.pk)
        locked_profile = UserProfile.objects.select_for_update().filter(user_id=user.pk).first()
        allowed_at = next_change_at(locked_profile)
        if allowed_at is not None:  # paralel ikinci sorğu
            raise _cooldown_error(allowed_at)
        if _taken(value, exclude_pk=user.pk):
            raise _taken_error()
        old_username = locked.username
        locked.username = value
        try:
            with transaction.atomic():
                locked.save(update_fields=["username"])
        except IntegrityError:  # unikal ifadə indeksi / ad↔e-poçt trigger-i (yarış)
            raise _taken_error() from None
        if locked_profile is not None:
            locked_profile.username_changed_at = timezone.now()
            locked_profile.save(update_fields=["username_changed_at", "updated_at"])
        _audit(locked, locked_profile, old_username=old_username, request=request)
        from .username_change_notify import notify_username_changed

        notify_username_changed(locked, locked_profile, old_username=old_username)

    user.username = value
    return UsernameChangeResult(old_username=old_username, new_username=value)


def _audit(user, profile, *, old_username: str, request) -> None:
    from core.audit import log_action
    from core.constants import AuditAction

    log_action(
        action=AuditAction.UPDATE,
        user=user,
        organization=getattr(profile, "organization", None),
        old_values={"username": old_username},
        new_values={"username": user.username},
        reason="Username changed by user",
        request=request,
        resource_type="Username",
        resource_id=str(user.pk),
        resource_repr=user.username,
    )


def success_message(result: UsernameChangeResult) -> str:
    return pgettext(
        CTX,
        "İstifadəçi adınız «%(new)s» olaraq dəyişdirildi. Bundan sonra sistemə bu adla (və ya e-poçtunuzla) daxil "
        "olun — köhnə ad artıq işləmir.",
    ) % {"new": result.new_username}


__all__ = [
    "MAX_LENGTH",
    "MIN_LENGTH",
    "RESERVED_PREFIXES",
    "RESERVED_USERNAMES",
    "UsernameChangeError",
    "UsernameChangeResult",
    "card_state",
    "change_enabled",
    "change_own_username",
    "cooldown_days",
    "next_change_at",
    "normalize_username",
    "success_message",
    "validate_username",
]
