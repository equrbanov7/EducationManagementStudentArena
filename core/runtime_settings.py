"""«Sistem tənzimləmələri» — işləmə vaxtı dəyişən limitlər (sahib 2026-10-03).

Sahib: «yalnız RİM rəhbərində olsun, settings kimi yer — hər şeyin limitlərini bir dəfəlik oradan artırıb
azaltmaq: AI modeli, OTP etibarlılıq dəqiqəsi, müəllimin jurnalı yazma dəqiqəsi, q/b dəyişmə müddəti…».

QAYDA: ``get(key)`` əvvəl bazadakı dəyişikliyə (``accounts.RuntimeSetting``), yoxdursa mühitin / kodun
DEFOLTUNA baxır — sətir olmayanda davranış əvvəlki kimidir. Yararsız saxlanmış dəyər heç vaxt tətbiq olunmur
(defolta düşür). Keş: proses daxili ``LOCAL_TTL`` saniyə + paylaşılan Redis açarı; yazıda hər ikisi silinir,
digər replikalar ən gec ``LOCAL_TTL`` saniyəyə yeni dəyəri görür. Testlərdə ``RUNTIME_SETTINGS_ENABLED=False``
(bazaya sorğu yoxdur — sorğu büdcəsi testləri pozulmur); xüsusiyyət testləri onu açır.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from django.conf import settings
from django.utils.translation import pgettext_lazy

logger = logging.getLogger(__name__)

_CTX = "core.runtime_settings"
CACHE_KEY = "emsarena:core:runtime_settings:v1"
CACHE_TTL = 300
LOCAL_TTL = 10

_local: dict = {"data": None, "expires": 0.0}


def _setting(name: str, fallback):
    return lambda: getattr(settings, name, fallback)


@dataclass(frozen=True)
class Spec:
    key: str
    group: str
    kind: str  # "int" | "rate" | "choice"
    default: Callable[[], Any]
    label: Any
    help: Any = ""
    unit: Any = ""
    min: int = 0
    max: int = 0
    choices: Callable[[], list] | None = field(default=None, compare=False)


def _ai_model_choices() -> list:
    return [
        ("", pgettext_lazy(_CTX, "Avtomatik (cari tənzimləmə)")),
        ("gemini-3.8-flash", "gemini-3.8-flash"),
        ("gemini-3.5-flash-lite", "gemini-3.5-flash-lite"),
        ("gemini-flash-latest", "gemini-flash-latest"),
        ("gemini-pro-latest", "gemini-pro-latest"),
    ]


GROUPS = (
    ("login", pgettext_lazy(_CTX, "Giriş və parol cəhdləri")),
    ("otp", pgettext_lazy(_CTX, "E-poçt kodu (OTP)")),
    ("session", pgettext_lazy(_CTX, "Sessiya")),
    ("journal", pgettext_lazy(_CTX, "Elektron jurnal")),
    ("ai", pgettext_lazy(_CTX, "Süni intellekt")),
    ("exam", pgettext_lazy(_CTX, "Final imtahan girişi")),
)

_RATE_HELP = pgettext_lazy(_CTX, "Pəncərə ərzində icazə verilən say; keçəndə istifadəçi gözləməli olur.")

SPECS: dict[str, Spec] = {
    spec.key: spec
    for spec in (
        Spec(
            "login.device_rate", "login", "rate", _setting("LOGIN_RATE_LIMIT", "5/10m"),
            pgettext_lazy(_CTX, "Bir cihazdan səhv parol cəhdi"), _RATE_HELP, min=3, max=100,
        ),
        Spec(
            "login.account_rate", "login", "rate", _setting("LOGIN_ACCOUNT_RATE_LIMIT", "20/1h"),
            pgettext_lazy(_CTX, "Bir hesaba səhv parol cəhdi (bütün cihazlardan)"), _RATE_HELP, min=5, max=200,
        ),
        Spec(
            "login.ip_rate", "login", "rate",
            lambda: getattr(settings, "LOGIN_IP_RATE_LIMIT", getattr(settings, "LOGIN_RATE_LIMIT", "5/10m")),
            pgettext_lazy(_CTX, "Bir İP ünvanından giriş cəhdi"),
            pgettext_lazy(_CTX, "Universitet Wi-Fi-ında yüzlərlə tələbə EYNİ İP-dən çıxır — çox aşağı saxlamayın."),
            min=20, max=5000,
        ),
        Spec(
            "otp.expiry_minutes", "otp", "int", lambda: max(1, int(getattr(settings, "AUTH_OTP_EXPIRY_SECONDS", 300)) // 60),
            pgettext_lazy(_CTX, "Kodun etibarlılıq müddəti"),
            pgettext_lazy(_CTX, "E-poçta gələn 6 rəqəmli kod bu qədər dəqiqə işləyir."),
            pgettext_lazy(_CTX, "dəqiqə"), min=2, max=60,
        ),
        Spec(
            "otp.max_sends_per_hour", "otp", "int", _setting("AUTH_OTP_MAX_SENDS_PER_HOUR", 5),
            pgettext_lazy(_CTX, "Bir e-poçta saatda göndərilən kod sayı"), "", pgettext_lazy(_CTX, "kod"), min=3, max=50,
        ),
        Spec(
            "otp.resend_cooldown_seconds", "otp", "int", _setting("AUTH_OTP_RESEND_COOLDOWN_SECONDS", 60),
            pgettext_lazy(_CTX, "Kodu yenidən göndərmə fasiləsi"), "", pgettext_lazy(_CTX, "saniyə"), min=30, max=600,
        ),
        Spec(
            "otp.max_attempts", "otp", "int", _setting("AUTH_OTP_MAX_ATTEMPTS", 5),
            pgettext_lazy(_CTX, "Bir kod üçün səhv yazma cəhdi"), "", pgettext_lazy(_CTX, "cəhd"), min=3, max=20,
        ),
        Spec(
            "otp.resend_rate", "otp", "rate", _setting("OTP_RESEND_RATE_LIMIT", "3/10m"),
            pgettext_lazy(_CTX, "Kodu yenidən istəmə (ilk giriş / qeydiyyat)"), _RATE_HELP, min=2, max=50,
        ),
        Spec(
            "otp.verify_rate", "otp", "rate", _setting("OTP_VERIFY_RATE_LIMIT", "5/10m"),
            pgettext_lazy(_CTX, "Kodu yoxlama cəhdi (qeydiyyat)"), _RATE_HELP, min=3, max=100,
        ),
        Spec(
            "otp.send_ip_rate", "otp", "rate", _setting("OTP_SEND_IP_RATE_LIMIT", "40/10m"),
            pgettext_lazy(_CTX, "Bir İP-dən parol bərpa kodu göndərmə"), _RATE_HELP, min=10, max=5000,
        ),
        Spec(
            "otp.verify_ip_rate", "otp", "rate", _setting("OTP_VERIFY_IP_RATE_LIMIT", "100/10m"),
            pgettext_lazy(_CTX, "Bir İP-dən parol bərpa kodunu yoxlama"), _RATE_HELP, min=20, max=5000,
        ),
        Spec(
            "session.idle_hours", "session", "int",
            lambda: max(1, int(getattr(settings, "SESSION_INACTIVITY_TIMEOUT", 8 * 3600)) // 3600),
            pgettext_lazy(_CTX, "Hərəkətsizlikdən sonra avtomatik çıxış"),
            pgettext_lazy(_CTX, "İstifadəçi bu qədər saat heç nə etməsə, sistemdən çıxarılır (sessiya ən çox 24 saat yaşayır)."),
            pgettext_lazy(_CTX, "saat"), min=1, max=24,
        ),
        Spec(
            "journal.lesson_edit_hours", "journal", "int", lambda: 2,
            pgettext_lazy(_CTX, "Dərs sətrini (tarix, mövzu, saat) düzəltmə / silmə müddəti"),
            pgettext_lazy(_CTX, "Müəllim dərsi yaratdıqdan sonra bu qədər saat ərzində dəyişə bilər."),
            pgettext_lazy(_CTX, "saat"), min=1, max=72,
        ),
        Spec(
            "journal.mark_edit_hours", "journal", "int", lambda: 2,
            pgettext_lazy(_CTX, "q/b, i/e və balı dəyişmə müddəti"),
            pgettext_lazy(_CTX, "Yazılmış qeyd bu qədər saatdan sonra donur (sonra yalnız rəsmi düzəliş yolu)."),
            pgettext_lazy(_CTX, "saat"), min=1, max=72,
        ),
        Spec(
            "ai.model", "ai", "choice", lambda: "",
            pgettext_lazy(_CTX, "AI modeli (köməkçi, xülasə, yoxlama)"),
            pgettext_lazy(_CTX, "«Avtomatik» — mövcud server tənzimləməsi; seçilən model hamısında birinci yoxlanılır."),
            choices=_ai_model_choices,
        ),
        Spec(
            "ai.assistant_rate", "ai", "rate", _setting("AI_ASSISTANT_RATE_LIMIT", "25/1h"),
            pgettext_lazy(_CTX, "AI köməkçiyə bir istifadəçinin sual sayı"), _RATE_HELP, min=1, max=1000,
        ),
        Spec(
            "exam.pin_max_failures", "exam", "int", _setting("FINAL_EXAM_PIN_MAX_FAILURES", 5),
            pgettext_lazy(_CTX, "Final imtahan PIN-ini səhv yazma cəhdi"), "", pgettext_lazy(_CTX, "cəhd"), min=3, max=20,
        ),
        Spec(
            "exam.pin_lock_minutes", "exam", "int", _setting("FINAL_EXAM_PIN_LOCK_MINUTES", 10),
            pgettext_lazy(_CTX, "PIN səhvlərindən sonra kilid müddəti"), "", pgettext_lazy(_CTX, "dəqiqə"), min=1, max=120,
        ),
    )
}  # fmt: skip


def enabled() -> bool:
    return bool(getattr(settings, "RUNTIME_SETTINGS_ENABLED", True))


def _load_overrides() -> dict:
    from django.apps import apps
    from django.db import DatabaseError, transaction

    try:
        model = apps.get_model("accounts", "RuntimeSetting")
        # Savepoint: cədvəl hələ yoxdursa (miqrasiyadan əvvəl) xarici tranzaksiya pozulmasın.
        with transaction.atomic():
            return dict(model.objects.values_list("key", "value"))
    except (LookupError, DatabaseError):
        logger.warning("runtime settings unavailable; using defaults", exc_info=True)
        return {}


def overrides() -> dict:
    """Bazadakı bütün dəyişikliklər (keşli). Xəta olarsa boş — defoltlar işləyir."""
    now = time.monotonic()
    if _local["data"] is not None and _local["expires"] > now:
        return _local["data"]
    from django.core.cache import cache

    data = None
    try:
        data = cache.get(CACHE_KEY)
    except Exception:  # noqa: BLE001 — Redis əlçatmazdırsa bazaya düş
        data = None
    if not isinstance(data, dict):
        data = _load_overrides()
        try:
            cache.set(CACHE_KEY, data, CACHE_TTL)
        except Exception:  # noqa: BLE001
            pass
    _local.update(data=data, expires=now + LOCAL_TTL)
    return data


def invalidate() -> None:
    from django.core.cache import cache

    _local.update(data=None, expires=0.0)
    try:
        cache.delete(CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass


def _rate_parts(raw) -> tuple[int, int] | None:
    from core.rate_limit import parse_rate

    try:
        parsed = parse_rate(str(raw or ""))
    except ValueError:
        return None
    if parsed is None or parsed.window_seconds < 60:
        return None
    return parsed.limit, parsed.window_seconds // 60


def coerce(spec: Spec, raw):
    """Saxlanmış / göndərilmiş dəyəri tipə və hədlərə uyğunlaşdırır; yararsızdırsa ``None``."""
    if spec.kind == "int":
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if spec.min <= value <= spec.max else None
    if spec.kind == "rate":
        parts = _rate_parts(raw)
        if parts is None or not (spec.min <= parts[0] <= spec.max) or not (1 <= parts[1] <= 24 * 60):
            return None
        return f"{parts[0]}/{parts[1]}m"
    if spec.kind == "choice":
        value = str(raw or "")
        return value if value in {code for code, _label in (spec.choices() if spec.choices else [])} else None
    return None


def override(key: str):
    """Yalnız RİM rəhbərinin saxladığı (yararlı) dəyər, yoxdursa ``None`` — çağıran öz əvvəlki qaydasını işlədir."""
    if not enabled():
        return None
    stored = overrides().get(key)
    return None if stored is None else coerce(SPECS[key], stored)


def get(key: str):
    spec = SPECS[key]
    if enabled():
        stored = overrides().get(key)
        if stored is not None:
            value = coerce(spec, stored)
            if value is not None:
                return value
    return spec.default()


def get_int(key: str) -> int:
    return int(get(key))


__all__ = [
    "CACHE_KEY",
    "GROUPS",
    "SPECS",
    "Spec",
    "coerce",
    "enabled",
    "get",
    "get_int",
    "invalidate",
    "override",
    "overrides",
]
