"""«Xarici dildə işgüzar kommunikasiya» qiymətləndirmə profili — «Sistem tənzimləmələri» açarı (sahib 2026-11-22).

Sahib (RİM rəhbəri): «Dil fənlərində 10 bal sərbəst iş, 10 bal davamiyyət, 10 bal midterm; midterm üçün xana; final
70»; əlavə: səviyyəsiz adlar da, «Praktiki məşğələ balını hesabla seminar kimi» (praktiki + sərbəst iş ≤ 10).
``academic.language_business_profile`` — bayraq, DEFOLT YANILI (``settings.ACADEMIC_LANGUAGE_BUSINESS_PROFILE``),
mövcud «academic» qrupunda. Söndürüləndə səviyyəli adlar adi səviyyə qaydası ilə (davamiyyət + praktiki məşğələ +
midterm, imtahan 70), səviyyəsiz adlar universitet standartı ilə hesablanır. Qayda: :mod:`core.language_business_rule`.

``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import pgettext_lazy

from core.language_business_rule import SETTING_KEY

_CTX = "core.runtime_settings"

GROUP_CODE = "academic"
KEY_LANGUAGE_BUSINESS_PROFILE = SETTING_KEY


def _default() -> bool:
    return bool(getattr(settings, "ACADEMIC_LANGUAGE_BUSINESS_PROFILE", True))


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_LANGUAGE_BUSINESS_PROFILE, GROUP_CODE, "bool", _default,
            pgettext_lazy(
                _CTX, "«Xarici dildə işgüzar kommunikasiya»: davamiyyət 10 + praktiki / sərbəst iş 10 + midterm 10"
            ),
            pgettext_lazy(
                _CTX,
                "Yandırılıbsa «Xarici dildə işgüzar (və akademik) kommunikasiya -1, -2, -3» fənlərində (səviyyəsiz və ya "
                "Beginner, Elementary, Pre-intermediate, Intermediate) imtahana qədər bal = davamiyyət 10 + praktiki / "
                "sərbəst iş 10 (praktiki məşğələ ortası + sərbəst iş, ən çox 10) + midterm 10, yekun imtahan 70. Sərbəst "
                "iş tabı açıqdır, müəllim midterm balını (0–10) jurnalda özü yaza bilər. Söndürüləndə səviyyəli fənlər "
                "digər səviyyə fənləri kimi (davamiyyət + praktiki məşğələ + midterm 10, imtahan 70), səviyyəsizlər "
                "universitet standartı ilə hesablanır.",
            ),
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """Açarı ``SPECS``-ə əlavə edir; ``GROUPS`` DƏYİŞMİR (açar mövcud «academic» qrupundadır)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    return groups


__all__ = ["GROUP_CODE", "KEY_LANGUAGE_BUSINESS_PROFILE", "build_specs", "register"]
