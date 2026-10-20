"""Apellyasiya «imtahan sonunda» rejimi — «Sistem tənzimləmələri» açarı (sahib 2026-10-20).

Sahib: «Apellyasiyanı imtahan bitən kimi verirsə düzgün cavabları da görür; sonradan (evdən) verirsə
YALNIZ sualları görür». Açar MÖVCUD «exam» qrupuna düşür (yeni qrup yaradılmır). Oxu nöqtəsi
:func:`appeal_onsite_minutes` — ``apps.appeals.services.onsite`` və nəticə səhifəsinin izahı onu çağırır,
açarı birbaşa oxumur.

``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

#: Açarın düşdüyü MÖVCUD qrup (``runtime_settings.GROUPS``-da artıq var).
GROUP_CODE = "exam"
KEY_ONSITE_MINUTES = "exam.appeal_onsite_minutes"
ONSITE_MINUTES_DEFAULT = 15
ONSITE_MINUTES_MIN = 0
ONSITE_MINUTES_MAX = 120


def _default_onsite_minutes() -> int:
    return int(getattr(settings, "APPEAL_ONSITE_MINUTES", ONSITE_MINUTES_DEFAULT))


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_ONSITE_MINUTES, GROUP_CODE, "int", _default_onsite_minutes,
            pgettext_lazy(_CTX, "İmtahan sonunda apellyasiya müddəti"),
            pgettext_lazy(
                _CTX,
                "Final/midterm bitdikdən sonra neçə dəqiqə ərzində, universitet şəbəkəsindən və imtahanı verdiyi "
                "sessiyadan verilən apellyasiyada tələbə sualla yanaşı variantları, öz cavabını və düzgün cavabı "
                "görür. Bundan sonra (məsələn, evdən) verilən apellyasiyada yalnız suallar göstərilir. "
                "0 — bu rejim söndürülür (həmişə yalnız suallar).",
            ),
            pgettext_lazy(_CTX, "dəqiqə"), min=ONSITE_MINUTES_MIN, max=ONSITE_MINUTES_MAX,
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """Açarı ``SPECS``-ə əlavə edir; ``GROUPS`` DƏYİŞMİR (açar mövcud «exam» qrupundadır)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    return groups


def appeal_onsite_minutes() -> int:
    """«İmtahan sonunda» apellyasiya müddəti (dəqiqə, 0..120). Oxunmasa / yararsızdırsa defolt."""
    try:
        from core import runtime_settings

        value = int(runtime_settings.get_int(KEY_ONSITE_MINUTES))
    except Exception:  # noqa: BLE001 — tənzimləmə oxunmasa da apellyasiya işləməlidir
        try:
            value = _default_onsite_minutes()
        except (TypeError, ValueError):
            value = ONSITE_MINUTES_DEFAULT
    return max(ONSITE_MINUTES_MIN, min(ONSITE_MINUTES_MAX, value))


__all__ = [
    "GROUP_CODE",
    "KEY_ONSITE_MINUTES",
    "ONSITE_MINUTES_DEFAULT",
    "appeal_onsite_minutes",
    "build_specs",
    "register",
]
