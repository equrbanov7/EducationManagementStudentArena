"""Midterm imtahan mərkəzi axını — «Sistem tənzimləmələri» açarı (sahib 2026-10-20).

Sahib: «Midterm də Final imtahanı kimidir — orada da URL /midterm olsun. Final imtahanındakı proses, məsuliyyət
və ciddilik nədirsə eynisi». Açar yandırılıbsa (defolt) midterm yalnız imtahan zalında ``/exams/midterm/``
ünvanından (istifadəçi adı + PIN → qaydalar → gözləmə otağı → nəzarətçi startı) verilir; söndürüləndə HƏR ŞEY
əvvəlki kimidir — midterm kabinetdəki «Təyin olunmuş imtahanlar» bölməsindən fərdi PIN ilə başlayır. Midterm
dövrü ortasında keçid üçün təhlükəsiz «geri qaytarma» düyməsidir.

Açar MÖVCUD «exam» qrupuna düşür (yeni qrup yaradılmır). Oxu nöqtəsi :func:`midterm_via_center` —
``apps.exams.services.center_exams`` onu çağırır, açarı birbaşa oxumur.

``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

#: Açarın düşdüyü MÖVCUD qrup (``runtime_settings.GROUPS``-da artıq var).
GROUP_CODE = "exam"
KEY_MIDTERM_VIA_CENTER = "exam.midterm_via_center"


def _default_midterm_via_center() -> bool:
    # İstehsal defoltu ``config/settings/components/exam.py``-dadır (True). Test ayarları onu import etmir —
    # kod defoltu False (köhnə kabinet axını), ``EXAM_FINAL_INTERNAL_ONLY`` ilə eyni konvensiya.
    return bool(getattr(settings, "EXAM_MIDTERM_VIA_CENTER", False))


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_MIDTERM_VIA_CENTER, GROUP_CODE, "bool", _default_midterm_via_center,
            pgettext_lazy(_CTX, "Midterm imtahan mərkəzi vasitəsilə (/exams/midterm/)"),
            pgettext_lazy(
                _CTX,
                "Yandırılıbsa midterm final kimi yalnız imtahan zalında /exams/midterm/ ünvanından verilir: istifadəçi "
                "adı + PIN, imtahan qaydaları, gözləmə otağı, nəzarətçinin startı, cihaz bağlantısı və 5 dəqiqəlik "
                "nəticə baxışı. Kabinetdən midterm başlamaq olmur. Söndürüləndə midterm əvvəlki kimi kabinetdən fərdi "
                "PIN ilə başlayır. Artıq başlamış midterm cəhdləri hər iki halda normal bitir.",
            ),
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """Açarı ``SPECS``-ə əlavə edir; ``GROUPS`` DƏYİŞMİR (açar mövcud «exam» qrupundadır)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    return groups


def midterm_via_center() -> bool:
    """Midterm imtahan mərkəzi axını ilə verilirmi. Tənzimləmə oxunmasa — defolt (``EXAM_MIDTERM_VIA_CENTER``)."""
    try:
        from core import runtime_settings

        return runtime_settings.get_bool(KEY_MIDTERM_VIA_CENTER)
    except Exception:  # noqa: BLE001 — tənzimləmə oxunmasa da imtahan girişi işləməlidir
        return _default_midterm_via_center()


__all__ = [
    "GROUP_CODE",
    "KEY_MIDTERM_VIA_CENTER",
    "build_specs",
    "midterm_via_center",
    "register",
]
