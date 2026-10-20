"""``core/runtime_settings.py``-in ayrı modullardakı açar qrupları (o fayl 600-sətir tavanındadır).

Hər modulun ``register(groups, specs, spec_cls)`` funksiyası var; yeni qrup üçün yalnız :data:`_MODULES`-a ad
əlavə olunur — ``runtime_settings.py``-ə sətir əlavə etmək lazım deyil.
"""

from __future__ import annotations

import importlib

_MODULES = (
    "core.runtime_settings_hr_contracts",  # «Əmək müqavilələri» (2026-10-19)
    "core.runtime_settings_site",  # «Açıq səhifələr» (2026-10-20)
)


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    for name in _MODULES:
        groups = importlib.import_module(name).register(groups, specs, spec_cls)
    return groups


__all__ = ["register"]
