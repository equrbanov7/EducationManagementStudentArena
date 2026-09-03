"""ROL-ƏSASLI universitet bölmə qapıları (menyu görünürlüyü).

Niyə ayrı modul? ``rbac.py`` modul ölçü büdcəsinə (SOFT_CAP=600) dayanmışdı və
``_role_capabilities`` içindəki iki blok — «universitet kabineti» (U12) və
«universitet strukturu» — saf hesablamadır: yalnız rol bayraqlarından asılıdır,
DB-yə getmir, request oxumur. Buraya köçürüldü; NƏTİCƏ EYNİDİR (blok-blok
köçürmə, şərtlər dəyişməyib) — ``test_sidebar_role_matrix.py`` bunu kilidləyir.

MÜQAVİLƏ:

* Funksiya SAFDIR: mutasiya etmir, yeni ``set`` qaytarır; çağıran onu
  ``allowed_sections``-a ``|=`` ilə birləşdirir.
* Bunlar YALNIZ GÖRÜNÜRLÜKDÜR — faktiki data qapısı registrar/organizations
  servis qatındadır və orada fail-closed yenidən yoxlanılır.
* İCAZƏ açarı ilə qapılan bölmələr burada DEYİL — onlar
  ``rbac_sections.apply_permission_section_gates``-dədir.
"""

from __future__ import annotations


def university_role_sections(
    *,
    is_superadmin: bool,
    is_org_admin: bool,
    is_unit_manager: bool,
    is_hr: bool,
    is_tutor: bool,
    is_exam_center: bool,
    is_teacher: bool,
    is_student: bool,
    has_active_org_context: bool,
    can_manage_journal_roster: bool,
    can_close_journals: bool,
    can_enter_exam_scores: bool,
    can_view_unit_analytics: bool,
) -> set:
    """Rol bayraqlarından törəyən universitet bölmələri (yeni dəst qaytarır)."""
    sections: set = set()

    # Universitet kabineti (U12): registrar səhifələri profil shell-inin İÇİNDƏ
    # bölmə kimi açılır (sidebar itmir — SPA panel). Faktiki data-icazə yenə də
    # registrar servis qatındadır; bunlar görünürlük + fragment gating üçündür.
    from django.conf import settings as _u12_settings

    if getattr(_u12_settings, "UNIVERSITY_MODE", True) and (has_active_org_context or is_superadmin):
        sections.update({"my-schedule", "academic-calendar"})
        # Müəllim/admin: sidebar linki jurnal iş sahəsini YENİ TABDA (/jurnal/) açır.
        # Tələbə: bölmə profil panelində öz jurnal xülasəsini göstərir (yalnız-oxu).
        if is_teacher or is_org_admin or is_superadmin or is_student or can_manage_journal_roster:
            sections.add("my-journal")
        if can_close_journals:
            sections.add("journal-close")
        if can_enter_exam_scores:
            sections.add("exam-score-entry")
        if can_view_unit_analytics:
            sections.add("analytics")
        if is_superadmin or is_org_admin or is_unit_manager:
            sections.add("academic-records")

    # Universitet strukturu (fakültə/kafedra) idarəetmə linkləri:
    # - rektor/prorektor/org admin → bütün təşkilat
    # - dekan/kafedra müdürü → yalnız öz alt-ağacı (data scoping organizations.scoping-də)
    # - HR → üzv siyahısı (vəzifə/unit təyinatları üçün)
    if is_superadmin or is_org_admin or is_unit_manager:
        sections.update({"org-structure", "org-faculties", "org-kafedras", "org-members"})
    elif is_hr:
        # HR struktur səhifələrini görür: `member.edit` icazəsi ilə müəllimin
        # kafedra təyinatını idarə edir; unit CRUD düymələri icazə flag-ları
        # ilə gizlənir (unit.create/edit/delete HR-da yoxdur).
        sections.update({"org-faculties", "org-kafedras", "org-members"})
    elif is_tutor or is_exam_center:
        # İmtahan mərkəzi org-wide, tyutor isə yalnız öz alt-ağacı üzrə
        # üzv siyahısı görür (data scoping organizations.scoping-də tətbiq olunur).
        sections.add("org-members")

    if is_superadmin or is_org_admin:
        sections.add("org-roles")

    # Dekan/kafedra müdürü: öz alt-ağacının imtahanlarına oxu-only baxış.
    if is_unit_manager:
        sections.add("unit-exams")

    return sections


__all__ = ["university_role_sections"]
