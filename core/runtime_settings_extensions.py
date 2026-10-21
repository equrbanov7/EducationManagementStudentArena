"""``core/runtime_settings.py``-in ayrı modullardakı açar qrupları (o fayl 600-sətir tavanındadır).

Hər modulun ``register(groups, specs, spec_cls)`` funksiyası var; yeni qrup üçün yalnız :data:`_MODULES`-a ad
əlavə olunur — ``runtime_settings.py``-ə sətir əlavə etmək lazım deyil.
"""

from __future__ import annotations

import importlib

_MODULES = (
    "core.runtime_settings_hr_contracts",  # «Əmək müqavilələri» (2026-10-19)
    "core.runtime_settings_site",  # «Açıq səhifələr» (2026-10-20)
    "core.runtime_settings_username",  # «profile» qrupuna istifadəçi adı açarları (2026-10-20)
    "core.runtime_settings_appeals",  # «exam» qrupuna «imtahan sonunda» apellyasiya açarı (2026-10-20)
    "core.runtime_settings_midterm",  # «exam» qrupuna «midterm imtahan mərkəzi vasitəsilə» açarı (2026-10-20)
    "core.runtime_settings_exam_center",  # «exam» qrupuna zal kompüteri yoxlaması + sual sayı açarları (2026-10-21)
    "core.runtime_settings_monitoring",  # «Monitorinq» — in-app söndürmə, yükdə avto-pauza, keş intervalı (2026-10-21)
)


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    for name in _MODULES:
        groups = importlib.import_module(name).register(groups, specs, spec_cls)
    return groups


__all__ = ["register"]
