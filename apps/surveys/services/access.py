"""Kim nəyi görür — nəticə əhatəsi və idarə hüququ (FAIL-CLOSED).

* ``survey.results.view`` əhatəsi ``organizations.scoping.get_permission_scope``-dan
  gəlir: UNIT rolu (kafedra müdiri) → ``scope_unit`` alt-ağacı; ORGANIZATION rolu
  (tədris şöbəsi, keyfiyyət, prorektor; rektor/RİM ``*`` ilə) → bütün təşkilat;
  açarsız/əhatəsiz → heç nə. Superadmin → bütün təşkilat.
* Müəllim bölməsi cavabı ``teacher_department`` (müəllimin kafedrası) üzrə,
  ümumi bölmə cavabı isə tələbənin ``group``-u üzrə əhatəyə düşür.
* ``survey.manage`` yalnız ORG-WIDE əhatə ilə keçərlidir (kampaniya təşkilat
  səviyyəsindədir).
"""

from __future__ import annotations

from django.db.models import Q

from apps.organizations.public import EMPTY_SCOPE, ORG_WIDE_SCOPE, get_permission_scope
from core.permissions import is_superadmin_user

from ..constants import PERM_MANAGE, PERM_RESULTS_VIEW, Section


def results_scope(user, organization, request=None):
    """``UnitScope`` — nəticələrə baxış əhatəsi (``has_structure_access`` yalan → heç nə)."""
    if organization is None or user is None or not getattr(user, "is_authenticated", False):
        return EMPTY_SCOPE
    if is_superadmin_user(user):
        return ORG_WIDE_SCOPE
    return get_permission_scope(user, organization, PERM_RESULTS_VIEW, request=request)


def can_view_results(user, organization, request=None) -> bool:
    return results_scope(user, organization, request=request).has_structure_access


def can_manage_campaigns(user, organization, request=None) -> bool:
    if organization is None or user is None or not getattr(user, "is_authenticated", False):
        return False
    if is_superadmin_user(user):
        return True
    return get_permission_scope(user, organization, PERM_MANAGE, request=request).is_org_wide


def response_scope_q(scope) -> Q:
    """``SurveyResponse`` üçün əhatə filtri (org-wide → boş ``Q()``; əhatəsiz → heç nə)."""
    if scope.is_org_wide:
        return Q()
    if not scope.is_unit_scoped:
        return Q(pk__in=[])
    teacher_q = Q(scope=Section.TEACHER) & scope.unit_subtree_q(
        path_field="teacher_department__path", id_field="teacher_department_id"
    )
    general_q = Q(scope=Section.GENERAL) & scope.unit_subtree_q(path_field="group__path", id_field="group_id")
    return teacher_q | general_q


def receipt_scope_q(scope) -> Q:
    """``SurveyReceipt`` (müəllim bölməsi) üçün əhatə filtri — iştirak faizi üçün."""
    if scope.is_org_wide:
        return Q()
    if not scope.is_unit_scoped:
        return Q(pk__in=[])
    return scope.unit_subtree_q(path_field="teacher_department__path", id_field="teacher_department_id")


def unit_in_scope(scope, unit_id, unit_path) -> bool:
    """Python tərəfli yoxlama (gözlənilən say hesabı üçün)."""
    if scope.is_org_wide:
        return True
    if not scope.is_unit_scoped or not unit_id:
        return False
    if unit_id in scope.unit_ids or str(unit_id) in {str(pk) for pk in scope.unit_ids}:
        return True
    path = unit_path or ""
    return any(path.startswith(f"{prefix}/") for prefix in scope.unit_paths)
