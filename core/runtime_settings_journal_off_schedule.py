"""«Cədvəldən kənar» işarəsi — «Sistem tənzimləmələri» açarı (sahib 2026-11-14, MR-356).

Sahib: «cədvəldən kənar yazısını yığışdır, kimə düşübsə də sil. və onu söndürmək olsun — settings-də söndürüb
yandırmaq»; «dərs cədvəlindəki tarixə görə problem olmasın, heç nəyə məcbur etməsin».

``journal.off_schedule_flag`` — bayraq, DEFOLT SÖNÜLÜ (``settings.JOURNAL_OFF_SCHEDULE_FLAG``), mövcud «journal»
qrupunda. Oxu nöqtəsi YALNIZ :func:`core.academic_rules.off_schedule_flag_enabled`.

``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

GROUP_CODE = "journal"
KEY_OFF_SCHEDULE_FLAG = "journal.off_schedule_flag"


def _default() -> bool:
    return bool(getattr(settings, "JOURNAL_OFF_SCHEDULE_FLAG", False))


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_OFF_SCHEDULE_FLAG, GROUP_CODE, "bool", _default,
            pgettext_lazy(_CTX, "«Cədvəldən kənar» işarəsi"),
            pgettext_lazy(
                _CTX,
                "Yandırılıbsa tarixi və saatı dərs cədvəlinə uyğun gəlməyən yeni dərs üçün səbəb soruşulur və dərs "
                "«cədvəldən kənar» kimi işarələnir. Söndürülüdə müəllim istənilən tarix və saatda dərs aça bilər — "
                "səbəb soruşulmur, heç nə işarələnmir və «cədvəldən kənar» yazısı heç yerdə göstərilmir.",
            ),
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """Açarı ``SPECS``-ə əlavə edir; ``GROUPS`` DƏYİŞMİR (açar mövcud «journal» qrupundadır)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    return groups


__all__ = ["GROUP_CODE", "KEY_OFF_SCHEDULE_FLAG", "build_specs", "register"]
