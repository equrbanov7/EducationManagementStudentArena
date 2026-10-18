"""«Əmək müqavilələri» — «Sistem tənzimləmələri» açarları (sahib 2026-10-19).

Oxu nöqtəsi YALNIZ ``apps.hr_contracts.services.queries`` (``reminder_thresholds`` / ``expiring_window`` /
``email_enabled``) — çağıranlar açarları birbaşa oxumur.

NİYƏ AYRI MODUL: ``core/runtime_settings.py`` modul ölçüsü büdcəsinə (600) yaxındır. Bu modul ``Spec`` sinfini
IMPORT ETMİR (dövri import olmasın) — ``runtime_settings`` öz ``Spec``-ini, ``GROUPS`` və ``SPECS``-ini
:func:`register`-ə ötürür.

``hr.contract_reminder_days`` ``choice`` tiplidir (mövcud UI-də sərbəst mətn tipi yoxdur): tövsiyə olunan
«60,30,14,7,1» və bir neçə hazır dəst. Hər hədd müqavilə başına BİR dəfə göndərilir.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

_CTX = "core.runtime_settings"

GROUP = ("hr_contracts", pgettext_lazy(_CTX, "Əmək müqavilələri"))

REMINDER_DAYS_DEFAULT = "60,30,14,7,1"
EXPIRING_WINDOW_DEFAULT = 60


def _reminder_choices() -> list:
    return [
        ("90,60,30,14,7,1", "90 · 60 · 30 · 14 · 7 · 1"),
        ("60,30,14,7,1", "60 · 30 · 14 · 7 · 1"),
        ("60,30,7,1", "60 · 30 · 7 · 1"),
        ("30,14,7,1", "30 · 14 · 7 · 1"),
        ("30,7,1", "30 · 7 · 1"),
        ("14,7,1", "14 · 7 · 1"),
    ]


def build_specs(spec_cls) -> tuple:
    """``runtime_settings.Spec`` nümunələri (sinif çağırandan gəlir — dövri import yoxdur)."""
    return (
        spec_cls(
            "hr.contract_reminder_days", "hr_contracts", "choice", lambda: REMINDER_DAYS_DEFAULT,
            pgettext_lazy(_CTX, "Bitmə xatırlatmalarının günləri"),
            pgettext_lazy(
                _CTX,
                "Müqavilənin bitməsinə bu qədər gün qalanda işçiyə və Kadrlar şöbəsinə (HR) bildiriş gedir — hər hədd "
                "bir dəfə. Müddəti bitən müqavilə üçün əlavə olaraq bir dəfə «müddəti bitdi» bildirişi göndərilir. "
                "Yenilənmiş və ya xitam verilmiş müqavilələrə xatırlatma getmir.",
            ),
            pgettext_lazy(_CTX, "gün"), choices=_reminder_choices,
        ),
        spec_cls(
            "hr.contract_expiring_window", "hr_contracts", "int", lambda: EXPIRING_WINDOW_DEFAULT,
            pgettext_lazy(_CTX, "«Bitmək üzrədir» pəncərəsi"),
            pgettext_lazy(
                _CTX,
                "HR siyahısında müqavilə bitməsinə bu qədər gün (və ya daha az) qalanda «Bitmək üzrədir» kimi "
                "işarələnir və yuxarıdakı sayğacda göstərilir.",
            ),
            pgettext_lazy(_CTX, "gün"), min=7, max=180,
        ),
        spec_cls(
            "hr.contract_email_enabled", "hr_contracts", "bool", lambda: True,
            pgettext_lazy(_CTX, "Müqavilə bildirişləri e-poçtla da getsin"),
            pgettext_lazy(
                _CTX,
                "Yandırılıbsa bitmə xatırlatması, «müqavilə göndərildi» və «işçi təsdiqlədi» bildirişləri kabinetdən "
                "əlavə istifadəçinin e-poçtuna da gedir. Söndürüləndə yalnız kabinet bildirişi qalır.",
            ),
        ),
    )  # fmt: skip


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    """``runtime_settings``-ə qrup və açarları əlavə edir; yeni ``GROUPS``-u qaytarır (idempotent)."""
    specs.update({spec.key: spec for spec in build_specs(spec_cls)})
    if any(code == GROUP[0] for code, _label in groups):
        return groups
    return groups + (GROUP,)


__all__ = ["EXPIRING_WINDOW_DEFAULT", "GROUP", "REMINDER_DAYS_DEFAULT", "build_specs", "register"]
