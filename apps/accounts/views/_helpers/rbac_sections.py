"""İCAZƏ-ƏSASLI profil bölmə qapıları (rol adına baxmayan menyu görünürlüyü).

Niyə ayrı modul? ``rbac.py`` modul ölçü büdcəsinə (SOFT_CAP=600) yaxınlaşmışdı və
bu üç qapı eyni naxışı təkrarlayır: «aktorun effektiv icazələrini topla → açar
varsa bölməni ``allowed_sections``-a əlavə et». Bir yerə yığmaqla həm fayl kiçilir,
həm də yeni icazə-qapılı bölmə əlavə etmək bir sətrə düşür.

ORTAQ MÜQAVİLƏ (dəyişdirməzdən əvvəl oxu):

* Bunlar YALNIZ GÖRÜNÜRLÜKDÜR. Faktiki data qapısı hər modulun öz servis
  qatındadır (``services/rim/policy.py``, ``services/people/permissions.py``,
  ``apps/audit/views.py``) və orada FAIL-CLOSED yenidən yoxlanılır.
* Rol ADI ilə qapılmır — açar icazə redaktorundan istənilən rola verilib
  yığışdırıla bilir; kodda rol siyahısı saxlasaydıq hər yeni rol üçün deploy
  lazım olardı (sahibin «tənzimlənən olsun» tələbi).
"""

from __future__ import annotations


def _effective_permissions(user, organization) -> list:
    """Aktorun aktiv təşkilatdakı effektiv icazələri (per-request memoizasiyalı).

    ``rbac`` modulundan LOKAL import olunur: ``rbac`` bu modulu yuxarıda import
    edir, yəni modul səviyyəsində əks-import dövr yaradardı.
    """
    from .rbac import _collect_actor_permissions

    permissions, _grantable = _collect_actor_permissions(user, organization)
    return list(permissions)


def apply_permission_section_gates(
    user,
    organization,
    allowed_sections: set,
    *,
    is_superadmin: bool,
    is_owner: bool,
) -> dict:
    """İcazə-qapılı bölmələri ``allowed_sections``-a əlavə edir və bayraqları qaytarır.

    Qaytarılan bayraqlar ``_role_capabilities`` cavabına düşür (şablonlar və
    testlər onlara söykənir): ``can_view_audit``, ``can_use_rim_center``,
    ``can_view_people_teachers``, ``can_view_people_students``, ``can_view_syllabus``,
    ``can_edit_syllabus``, ``can_review_syllabus``.
    """
    from apps.accounts.services.people.permissions import PERM_VIEW_STUDENTS, PERM_VIEW_TEACHERS
    from apps.accounts.services.rim.policy import RIM_PERMISSIONS
    from core.permissions import has_permission

    privileged = bool(is_superadmin or is_owner)

    # Təşkilat konteksti yoxdursa icazə həll oluna bilmir — yalnız superadmin/sahib.
    permissions: list = []
    if organization is not None and not privileged:
        permissions = _effective_permissions(user, organization)

    # Audit jurnalı: `audit.view` (rektor/prorektor "*", imtahan mərkəzi, HR).
    can_view_audit = privileged or has_permission(permissions, "audit.view")

    # «RİM mərkəzi»: `user.*` açarlarından HƏR HANSI BİRİ bölməni açır; konkret
    # düymələr (parol/blok/silmə/redaktə) öz icazəsi ilə AYRICA qapılıdır. Yəni
    # yalnız `user.search` daşıyan operator bölməni görür, dağıdıcı düyməsi olmur.
    # Bölmə superadmin-only DEYİL: köhnə sistemdən idxal olunmuş 8000+ hesabın
    # parol bərpası cutover-da gündəlik əməliyyatdır.
    can_use_rim_center = privileged or any(has_permission(permissions, perm) for perm in RIM_PERMISSIONS)

    # «Müəllimlər» / «Tələbələr» kataloqu — iki AYRI açar: «yalnız tələbələri
    # görən» tyutor kimi rollar qurula bilsin.
    can_view_people_teachers = privileged or has_permission(permissions, PERM_VIEW_TEACHERS)
    can_view_people_students = privileged or has_permission(permissions, PERM_VIEW_STUDENTS)

    # «Sillabuslar» + «Sillabus redaktoru» — iki AYRI açar: `syllabus.view` yalnız
    # oxu (kafedra müdiri, dekan), `syllabus.edit` isə redaktə (müəllim). Redaktor
    # AYRICA tam səhifə DEYİL — profil shell-inin içində açılır (sol sidebar qalır),
    # ona görə eyni qapıdan keçir. Konkret sillabusun görünməsi/redaktəsi
    # `apps/syllabus/services/scoping.py`-da fail-closed yenidən yoxlanılır.
    can_edit_syllabus = privileged or has_permission(permissions, "syllabus.edit")
    can_view_syllabus = can_edit_syllabus or has_permission(permissions, "syllabus.view")

    # «Sillabus təsdiqi» AYRICA açardır: `syllabus.review`. Müəllim (`edit`) bu
    # bölməni GÖRMÜR — qərar səthi ilə redaktə səthi bir-birinə açılmır. Menyu
    # görünürlüyü icazə açarına baxır, KONKRET sillabusun görünməsi isə
    # `apps/syllabus/services/coverage.py`-da struktur əhatəsi ilə fail-closed
    # yenidən süzülür (əhatəsiz istifadəçi boş vəziyyət görür).
    can_review_syllabus = privileged or has_permission(permissions, "syllabus.review")

    for enabled, section in (
        (can_view_audit, "audit-log"),
        (can_use_rim_center, "rim-center"),
        (can_view_people_teachers, "people-teachers"),
        (can_view_people_students, "people-students"),
        (can_view_syllabus, "syllabus-list"),
        (can_view_syllabus, "syllabus-editor"),
        (can_review_syllabus, "syllabus-review"),
    ):
        if enabled:
            allowed_sections.add(section)

    return {
        "can_view_audit": can_view_audit,
        "can_use_rim_center": can_use_rim_center,
        "can_view_people_teachers": can_view_people_teachers,
        "can_view_people_students": can_view_people_students,
        "can_view_syllabus": can_view_syllabus,
        "can_edit_syllabus": can_edit_syllabus,
        "can_review_syllabus": can_review_syllabus,
    }


__all__ = ["apply_permission_section_gates"]
