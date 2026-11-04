"""«Müraciətlər» — «Sistem tənzimləmələri» açarı: gündəlik müraciət limiti (sahib 2026-11-04).

Sahib: «bir gündə müraciət göndərmə limitini də artır, max 5-10 olsun». Əvvəl gündəlik hədd YOX idi — yalnız eyni
mətnli təkrarı 2 dəqiqəlik pəncərə tuturdu (``apps.applications.services.submit.DUPLICATE_WINDOW``). İndi bir
istifadəçi təşkilatın yerli təqvim günü ərzində ən çox N müraciət göndərə bilər (defolt 10); RİM rəhbəri dəyəri
buradan 1–50 aralığında dəyişir. Silinmiş müraciətlər sayılmır.

Oxu nöqtəsi YALNIZ :func:`daily_limit` (``apps.applications.services.submit`` onu çağırır).
Testlərdə defolt ``settings.APPLICATIONS_DAILY_LIMIT`` ilə dəyişir (``override_settings``).
``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

GROUP = ("applications", pgettext_lazy(_CTX, "Müraciətlər"))

KEY_DAILY_LIMIT = "applications.daily_limit"
DAILY_LIMIT_MIN = 1
DAILY_LIMIT_MAX = 50


def _default_daily_limit() -> int:
    return int(getattr(settings, "APPLICATIONS_DAILY_LIMIT", 10))


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_DAILY_LIMIT, GROUP[0], "int", _default_daily_limit,
            pgettext_lazy(_CTX, "Bir istifadəçinin gündə göndərə biləcəyi müraciət sayı"),
            pgettext_lazy(
                _CTX,
                "Bir istifadəçi bir təqvim günü (Bakı vaxtı ilə 00:00–24:00) ərzində ən çox bu qədər yeni müraciət "
                "göndərə bilər. Limit dolanda yeni müraciət rədd olunur və istifadəçiyə sabah yenidən cəhd etməsi "
                "deyilir; artıq göndərilmiş müraciətlərə cavab yazmaq və sənəd əlavə etmək bu limitə düşmür.",
            ),
            pgettext_lazy(_CTX, "müraciət"),
            min=DAILY_LIMIT_MIN,
            max=DAILY_LIMIT_MAX,
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """``runtime_settings``-ə qrup və açarı əlavə edir; yeni ``GROUPS``-u qaytarır (idempotent)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    if any(code == GROUP[0] for code, _label in groups):
        return groups
    return groups + (GROUP,)


def daily_limit() -> int:
    """Gündəlik müraciət limiti; tənzimləmə oxunmasa — defolt (heç vaxt istisna atmır)."""
    try:
        from core import runtime_settings

        return runtime_settings.get_int(KEY_DAILY_LIMIT)
    except Exception:  # noqa: BLE001 — oxunmasa defolt limit işləyir (göndəriş sınmasın)
        return _default_daily_limit()


__all__ = ["DAILY_LIMIT_MAX", "DAILY_LIMIT_MIN", "GROUP", "KEY_DAILY_LIMIT", "build_specs", "daily_limit", "register"]
