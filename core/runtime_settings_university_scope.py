"""«Universitet əhatəli kafedra» — «Sistem tənzimləmələri» açarı (sahib 2026-11-22, RİM rəhbəri).

Sahib: «Xarici dil kafedrasında tyutorlar və dekanlıq işçiləri qrup yaradanda və ya alt qrupa tələbə əlavə edəndə
bütün universitetdən qrupları götürürlər — onların qrup-tələbə görünüşünü universitet üzrə dəyişin».

``academic.university_wide_chairs`` — bayraq, DEFOLT YANILI (``settings.ACADEMIC_UNIVERSITY_WIDE_CHAIRS``), mövcud
«academic» qrupunda. Söndürüləndə əvvəlki qayda: namizəd tələbələr aktorun öz əhatəsindəndir. Hansı kafedraların
universitet əhatəli olduğu və oxu nöqtəsi: :mod:`apps.organizations.university_wide_scope`.

``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

GROUP_CODE = "academic"
KEY_UNIVERSITY_WIDE_CHAIRS = "academic.university_wide_chairs"


def _default() -> bool:
    return bool(getattr(settings, "ACADEMIC_UNIVERSITY_WIDE_CHAIRS", True))


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_UNIVERSITY_WIDE_CHAIRS, GROUP_CODE, "bool", _default,
            pgettext_lazy(_CTX, "Xarici dillər kafedrası: tələbələr bütün universitetdən"),
            pgettext_lazy(
                _CTX,
                "Yandırılıbsa Xarici dillər kafedrasının qrupunda və ya səviyyə qrupunda tyutor və dekanlıq işçiləri "
                "tələbə əlavə edəndə bütün universitetin qruplarını və tələbələrini görür. Kim qrup yarada və tələbə "
                "əlavə edə bilər — dəyişmir. Söndürüləndə əvvəlki qayda: yalnız öz məktəbinin (fakültəsinin) "
                "tələbələri.",
            ),
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """Açarı ``SPECS``-ə əlavə edir; ``GROUPS`` DƏYİŞMİR (açar mövcud «academic» qrupundadır)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    return groups


__all__ = ["GROUP_CODE", "KEY_UNIVERSITY_WIDE_CHAIRS", "build_specs", "register"]
