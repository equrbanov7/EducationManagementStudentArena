"""ƏHATƏ-ƏSASLI profil bölmə qapıları — rol auditi 2026-10-13 B (B2 / B5 / B16).

Niyə ayrı modul? ``rbac_sections`` saf «açar varmı» yoxlamasıdır; buradakı üç qapı isə açardan
ƏLAVƏ ya struktur əhatəsinə (``get_permission_scope``), ya da faktiki dataya baxır. Onları bir yerə
yığmaq həm ``rbac_sections``-ı kiçik saxlayır, həm də sorğu büdcəsini bir baxışda görünən edir
(``test_rbac_permission_cache``): HƏR qapı əvvəl yaddaşdakı icazə siyahısına baxır və DB-yə yalnız
açar varsa gedir — açarsız aktor üçün sıfır əlavə sorğu.

Bunlar YALNIZ GÖRÜNÜRLÜKDÜR; data qapısı hər bölmənin öz endpoint-indədir və eyni açar + əhatə ilə
fail-closed yenidən yoxlanılır (menyu ilə data bir-birindən geniş olmamalıdır).
"""

from __future__ import annotations

#: «Akademik qeydlər» (ÜOMG / transkript) — kataloq: ``organizations.permissions_role_audit``.
RECORDS_PERMISSION = "student.records_view"

#: Əhatəli YALNIZ-OXU jurnal girişi (``registrar.journal_access.VIEW_PERMISSION``).
JOURNAL_VIEW_PERMISSION = "journal.view"


def _university_mode() -> bool:
    from django.conf import settings

    return bool(getattr(settings, "UNIVERSITY_MODE", True))


def _has_scope(user, organization, permission) -> bool:
    from apps.organizations.public import get_permission_scope

    return get_permission_scope(user, organization, permission).has_structure_access


def scope_gated_sections(user, organization, permissions, *, privileged: bool) -> set:
    """Açar + struktur əhatəsi ilə açılan bölmələr (yeni dəst qaytarır).

    * ``academic-records`` — B2 (2026-10-13): əvvəl rol ADI ilə (superadmin / org admin / dekan /
      kafedra müdiri / imtahan mərkəzi) açılırdı və redaktorda açar almaq heç nəyi bağlamırdı. İndi
      YALNIZ ``student.records_view`` əhatəsi: ORGANIZATION rolu → bütün təşkilat, UNIT rolu →
      ``scope_unit`` alt-ağacı, əhatəsiz → bölmə yoxdur (endpoint də ``has_access: False`` verir —
      ``views/academic_records._scope`` eyni açarı oxuyur). Superadmin / təşkilat sahibi
      ``get_permission_scope``-da org-wide-dır.
    * ``my-journal`` — B5: sidebar qapısı (``rbac_university_sections``) rol bayraqlarına baxırdı və
      ``journal.view`` daşıyan qeyri-müəllim (Tədris şöbəsi) jurnal linkini görmürdü, halbuki
      ``/jurnal/`` siyahısı və detal səhifəsi bu açarı onsuz da əhatə ilə tanıyır
      (``journal_scope.journal_view_q`` / ``journal_access.can_observe_journal``). Link YENİ TABDA
      yalnız-oxu jurnal iş sahəsini açır; söndürülmüş «Elektron jurnal» modulunu qaytarmır.
    """
    sections: set = set()
    if organization is None:
        return sections
    from core.permissions import has_permission

    # Rejim bayrağına baxılmır: açar özü qapıdır (köhnə imtahan mərkəzi qolu da rejimdən asılı deyildi).
    if (privileged or has_permission(permissions, RECORDS_PERMISSION)) and _has_scope(
        user, organization, RECORDS_PERMISSION
    ):
        sections.add("academic-records")

    # Jurnal linki — `rbac_university_sections`-dəki «my-journal» qolu kimi YALNIZ universitet rejimində.
    if (
        _university_mode()
        and has_permission(permissions, JOURNAL_VIEW_PERMISSION)
        and _has_scope(user, organization, JOURNAL_VIEW_PERMISSION)
    ):
        from apps.organizations.public import disabled_sections

        if "my-journal" not in disabled_sections(organization):
            sections.add("my-journal")
    return sections


#: «Fakültələr» bölməsinin əhatə açarı (struktur ağacı ilə eyni).
STRUCTURE_PERMISSION = "unit.view"
#: Bu tiplərin alt-ağacında fakültə OLMUR — kafedra/ixtisas/qrup/şöbə əhatəli aktor bölməni görmür.
BELOW_FACULTY_UNIT_TYPES = frozenset({"chair", "department", "specialty", "group", "lab", "center", "section"})


def faculties_section_visible(user, organization, *, privileged: bool) -> bool:
    """«Fakültələr» (`org-faculties`) — yalnız əhatəsində FAKÜLTƏ ola bilən aktora (2026-10-14).

    Sahib (kafedra müdiri kimi baxış): «kafedra müdiri səhifəsində buna ehtiyac yoxdur» — bölmə bütün
    KPI-ləri sıfır və «Hələ fakültə yaradılmayıb» göstərirdi. Qayda: org-wide `unit.view` (Tədris
    şöbəsi, RİM, prorektor, rektor) və fakültə əhatəli (dekan, dekan müavini) → görünür; əhatəsi
    YALNIZ kafedra/ixtisas/qrup/şöbə olan aktor (kafedra müdiri, koordinator, tyutor) → gizli.
    Sorğu büdcəsi: tiplər memoizasiya olunmuş üzvlük sətirlərindən; naməlum yuxarı tip (rektorluq,
    prorektorluq) olduqda YALNIZ onda alt-ağacda fakültə üçün tək ``EXISTS``.
    """
    if privileged:
        return True
    if organization is None:
        return False
    from apps.organizations.public import get_permission_scope, permission_scope_unit_types

    scope = get_permission_scope(user, organization, STRUCTURE_PERMISSION)
    if scope.is_org_wide:
        return True
    if not scope.is_unit_scoped:
        return False
    types = permission_scope_unit_types(user, organization, STRUCTURE_PERMISSION)
    if "faculty" in types:
        return True
    if types <= BELOW_FACULTY_UNIT_TYPES:
        return False
    from apps.organizations.models import OrgUnit

    return (
        OrgUnit.objects.filter(organization=organization, unit_type="faculty", is_active=True)
        .filter(scope.unit_subtree_q())
        .exists()
    )


def teaches_workload(user, organization) -> bool:
    """Aktorun bu təşkilatda MÜƏLLİM kimi yük bölgüsü sətri varmı (tək ``EXISTS``).

    B16 (2026-10-13): «Dərs yüküm» əvvəl ``workload.view`` ilə açılırdı — o açar Tədris şöbəsində,
    RİM əməkdaşında, qəyyumda da var (yükə NƏZARƏT üçün), ona görə onlar boş səhifə görürdü. İndi
    bölmə ``workload.object`` (müəllim şablonu) ilə, açar yoxdursa isə FAKTİKİ bölgü sətri ilə açılır —
    dərs deyən dekan / kafedra müdiri / prorektor bölməni itirmir. Sorğu YALNIZ açar yoxlaması
    uğursuz olanda gedir (kabinet qabığı sorğu büdcəlidir).
    """
    if organization is None or not getattr(user, "is_authenticated", False):
        return False
    from apps.workload.models import TeacherAssignment

    return TeacherAssignment.objects.filter(organization=organization, teacher=user).exists()


__all__ = [
    "BELOW_FACULTY_UNIT_TYPES",
    "JOURNAL_VIEW_PERMISSION",
    "RECORDS_PERMISSION",
    "STRUCTURE_PERMISSION",
    "faculties_section_visible",
    "scope_gated_sections",
    "teaches_workload",
]
