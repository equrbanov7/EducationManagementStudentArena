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
    # Mərhələ 2 (ekran 05/06/07) — tədris planı, qrup reyestri, semestr açılışı.
    ("curriculum-editor", "curriculum_editor_section", "curriculum_sections", "build_curriculum_section"),
    ("groups-registry", "groups_registry_section", "curriculum_sections", "build_groups_section"),
    ("semester-opening", "semester_opening_section", "curriculum_sections", "build_semester_section"),
    # Mərhələ 3 (ekran 08/09) — Tələbə Xidmətləri Mərkəzi. Eyni cədvəldə
    # saxlanılır ki, «aktiv bölmə deyilsə sorğu işləmir» qaydası TƏK yerdə
    # qalsın (modul adı tarixi səbəbdən `_teaching_office`-dur).
    ("student-admission", "student_admission_section", "student_admission", "build_student_admission_section"),
    ("student-registry", "student_registry_section", "student_registry", "build_student_registry_section"),
    # Mərhələ 4 (ekran 12/13/15/17) — dərs yükü zənciri.
    ("workload-center", "workload_center_section", "workload_center", "build_workload_center_section"),
    ("workload-visa", "workload_visa_section", "workload_chain", "build_workload_visa_section"),
    ("workload-approval", "workload_approval_section", "workload_chain", "build_workload_approval_section"),
    ("workload-overview", "workload_overview_section", "workload_chain", "build_workload_overview_section"),
    # Mərhələ 6 (ekran 21) — «Keçilmiş dərslər» (müəllim + nəzarətçi).
    ("lessons-log", "lessons_log_section", "lessons_log", "build_lessons_log_section"),
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
