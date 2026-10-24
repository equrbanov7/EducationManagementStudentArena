"""«Sillabus təsdiqi tələb olunur» — «Sistem tənzimləmələri» açarı (sahib 2026-10-25).

Sahib: «sillabus approve hissəsini hələlik söndür, avtomatik qəbul olsun, sistem settings-ə əlavə et,
özüm tənzimləyə bilim».

DEFOLT = SÖNÜLÜ (kafedra təsdiqi tələb olunmur): müəllim sillabusu təsdiqə göndərəndə versiya dərhal
``APPROVED`` olur (``approval_source = auto``, ``approved_by`` boş). Yandırılanda köhnə kafedra təsdiqi
axını tam qüvvəyə minir. Oxu nöqtəsi YALNIZ :func:`approval_required` — ``apps.syllabus.services.workflow``
və ``syllabus_auto_approve_pending`` əmri onu çağırır, açarı birbaşa oxumur.

Testlərdə defolt ``config.settings.test``-də ``SYLLABUS_APPROVAL_REQUIRED = True`` ilə KAFEDRA AXININA
qaytarılıb (mövcud iş axını testləri dəyişməsin); avtomatik yolu ``override_settings`` yoxlayır.

``Spec`` sinfi IMPORT EDİLMİR (dövri import olmasın) — ``runtime_settings`` onu :func:`register`-ə ötürür.
"""

from __future__ import annotations

from django.conf import settings
from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

GROUP = ("syllabus", pgettext_lazy(_CTX, "Sillabus"))

KEY_APPROVAL_REQUIRED = "syllabus.approval_required"


def _default_approval_required() -> bool:
    return bool(getattr(settings, "SYLLABUS_APPROVAL_REQUIRED", False))


def build_specs(spec_cls) -> tuple:
    return (
        spec_cls(
            KEY_APPROVAL_REQUIRED, GROUP[0], "bool", _default_approval_required,
            pgettext_lazy(_CTX, "Sillabus təsdiqi tələb olunur (kafedra müdiri)"),
            pgettext_lazy(
                _CTX,
                "Söndürülübsə (defolt) müəllim sillabusu təsdiqə göndərən kimi o avtomatik təsdiqlənir: kafedra "
                "müdirinin təsdiq növbəsində gözləyən sillabus olmur, tarixçədə «avtomatik təsdiq (sistem "
                "tənzimləməsi)» görünür. Yandırılanda əvvəlki qayda qayıdır: sillabus kafedra müdirinin təsdiqini "
                "gözləyir. Açarı dəyişmək artıq göndərilmiş sillabusların statusunu dəyişmir — söndürülü vəziyyətdə "
                "gözləyənləri toplu təsdiqləmək üçün «syllabus_auto_approve_pending» əməliyyatı var.",
            ),
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """``runtime_settings``-ə qrup və açarı əlavə edir; yeni ``GROUPS``-u qaytarır (idempotent)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    if any(code == GROUP[0] for code, _label in groups):
        return groups
    return groups + (GROUP,)


def approval_required() -> bool:
    """Sillabus kafedra təsdiqi tələb olunurmu (defolt: xeyr — avtomatik təsdiq)."""
    try:
        from core import runtime_settings

        return bool(runtime_settings.get(KEY_APPROVAL_REQUIRED))
    except Exception:  # noqa: BLE001 — tənzimləmə oxunmasa defolt (göndərmə sınmasın)
        return _default_approval_required()


__all__ = ["GROUP", "KEY_APPROVAL_REQUIRED", "approval_required", "build_specs", "register"]
