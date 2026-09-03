"""Tədris şöbəsi bölmələrinin context dispatch-i (ekran 01–04).

``_stage3`` modul ölçüsü büdcəsinə (SOFT_CAP=600) dayandığı üçün bu dörd
şərtli çağırış AYRI moduldadır. Davranış eynidir: hər bölmə YALNIZ o zaman
qurulur ki, həm ``allowed_sections``-da olsun, həm də AKTİV bölmə olsun —
əks halda profil konteksti heç bir əlavə sorğu işlətmir.
"""

from __future__ import annotations

#: (bölmə açarı, context atributu, builder modulu, builder adı)
_SECTIONS = (
    ("org-structure-tree", "structure_tree_section", "teaching_office", "build_structure_tree_section"),
    ("chair-profile", "chair_profile_section", "teaching_office", "build_chair_profile_section"),
    ("programs-registry", "programs_registry_section", "catalog_sections", "build_programs_section"),
    ("subject-catalog", "subject_catalog_section", "catalog_sections", "build_subjects_section"),
)


def dispatch_teaching_office_sections(state) -> None:
    """Aktiv Tədris şöbəsi bölməsinin context-ini qurur (yerində mutasiya)."""
    from importlib import import_module

    for section_key, attribute, module_name, builder_name in _SECTIONS:
        if section_key not in state.allowed_sections or state.active_section != section_key:
            continue
        module = import_module(f"apps.accounts.views.profile._sections.{module_name}")
        getattr(module, builder_name)(
            state.request,
            getattr(state, attribute),
            active_organization=state.active_organization,
            allowed_sections=state.allowed_sections,
            active_section=state.active_section,
        )


__all__ = ["dispatch_teaching_office_sections"]
