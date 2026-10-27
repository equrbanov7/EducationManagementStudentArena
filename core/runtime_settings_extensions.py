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
    "core.runtime_settings_journal_late",  # «journal» qrupuna «Gec yazılıb» başlanğıc tarixi (2026-10-25)
    "core.runtime_settings_rim_activation",  # «login» qrupuna «aktivləşdirəndə RİM-ə bildiriş» açarı (2026-10-23)
    "core.runtime_settings_syllabus",  # «Sillabus» — kafedra təsdiqi tələb olunur/avtomatik təsdiq (2026-10-25)
    "core.runtime_settings_push",  # «Bildirişlər» — telefona push (FCM) açarı (2026-10-25)
    "core.runtime_settings_exam_scores",  # «exam» qrupuna kağız bal 15 dəq / tələbəyə 24 saat açarları (2026-10-25)
    "core.runtime_settings_session",  # «session»/«journal»: brauzer bağlananda çıxış, jurnal bağlanması (2026-10-27)
)


def register(groups: tuple, specs: dict, spec_cls) -> tuple:
    for name in _MODULES:
        groups = importlib.import_module(name).register(groups, specs, spec_cls)
    return groups


__all__ = ["register"]
