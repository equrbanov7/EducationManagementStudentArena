"""«Semestr açılışı» və «Tədris planı» səthlərinin OXU əhatəsi (QA-2 F-01 / F-02, 2026-10-17).

Əvvəl hər iki səth yalnız AÇARI (``semester.view`` / ``plan.view``) yoxlayırdı: dekan, kafedra müdiri,
koordinator və tyutor bütün universitetin açılışlarını, müəllim adlarını, kafedra siyahısını və bütün
ixtisasların plan sətirlərini görürdü. Yazı tərəfi isə artıq əhatəli idi (açılış — yalnız org-wide;
plan — ``program_in_scope``). İndi oxu da açarı DAŞIYAN üzvlüyün əhatəsi ilə süzülür:

* **Semestr açılışı** — ``semester.view`` əhatəsi (dar, ``get_permission_scope``): kafedra müdiri yalnız öz
  kafedrasının fənlərini (``subject.chair_unit``), dekan fakültəsinin kafedralarının fənlərini və fakültəsinin
  qruplarına açılan fənləri görür. Org-wide açar (RİM, Tədris şöbəsi, prorektor) hamısını görür.
* **Tədris planı** — ``plan.view`` əhatəsi FAKÜLTƏYƏ genişlənir (``faculty_read_scope``, 2026-10-14 oxu qaydası:
  «İxtisaslar — ancaq öz fakültəmizə aid olanı»; ixtisaslar kafedranın deyil, fakültənin altındadır). Yazı
  yenə dar ``plan.edit`` əhatəsindədir.

MODUL SƏRHƏDİ: ``apps.organizations`` statik import EDİLMİR — funksiya daxilində ``public`` fasadından.
"""

from __future__ import annotations

from django.db.models import Q

SEMESTER_VIEW = "semester.view"
PLAN_VIEW = "plan.view"


def semester_read_scope(request, organization):
    from apps.organizations.public import get_permission_scope

    return get_permission_scope(getattr(request, "user", None), organization, SEMESTER_VIEW, request=request)


def plan_read_scope(request, organization):
    from apps.organizations.public import faculty_read_scope

    return faculty_read_scope(getattr(request, "user", None), organization, PLAN_VIEW, request=request)


def offering_scope_q(scope) -> Q:
    """``CourseOffering`` üçün: fənnin kafedrası VƏ YA açılışın qrupu əhatədədir (org-wide → filtrsiz)."""
    if scope.is_org_wide:
        return Q()
    return scope.unit_subtree_q(path_field="subject__chair_unit__path", id_field="subject__chair_unit_id") | (
        scope.unit_subtree_q(path_field="group__path", id_field="group_id")
    )


def unit_scope_q(scope) -> Q:
    """``OrgUnit`` üçün alt-ağac filtri (kafedra seçicisi)."""
    return scope.unit_subtree_q()


def program_scope_q(scope, prefix: str = "") -> Q:
    """``Program`` (və ya ``prefix="program__"`` ilə ``Curriculum``) — ixtisas bölməsi əhatədədir."""
    if scope.is_org_wide:
        return Q()
    return scope.unit_subtree_q(path_field=f"{prefix}specialty_unit__path", id_field=f"{prefix}specialty_unit_id")


__all__ = [
    "PLAN_VIEW",
    "SEMESTER_VIEW",
    "offering_scope_q",
    "plan_read_scope",
    "program_scope_q",
    "semester_read_scope",
    "unit_scope_q",
]
