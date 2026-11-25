"""Tələbə yaratmanın ƏHATƏ qapısı — tələbənin QRUPU aktorun ``user.import`` əhatəsində olmalıdır (sahib 2026-11-25).

Əvvəl ``user.import`` yalnız ORGANIZATION rollarında idi (Tələbə xidmətləri, RİM rəhbəri) və açar əhatəyə baxmırdı.
«Əcnəbi tələbələrlə iş şöbəsi» UNIT rolu da tələbə əlavə edir — amma YALNIZ öz əcnəbi qruplarına. Qayda müəllim
formundakı ``rim.create_units.teacher_units`` qaydasının tələbə qarşılığıdır:

* əhatə org-wide (Tələbə xidmətləri, RİM rəhbəri, superadmin, sahib) → dəyişiklik yoxdur;
* UNIT əhatəsi → qrup həmin alt-ağacda olmalıdır; qrupsuz sətir (ATİS «qrup təyin edilməyib») da RƏDD olunur;
* əhatə yoxdur → heç bir qrup.

Üç səth eyni qaydadan keçir: tək-tək forma (``rim.create``), onun qrup seçicisi (``rim.create_options``) və toplu
fayl (``views.student_intake`` — ön baxış və tətbiq eyni planları alır).
"""

from __future__ import annotations

from django.utils.translation import pgettext

PERM_IMPORT = "user.import"
_CTX = "student_intake"


def import_scope(user, organization):
    from apps.organizations.public import get_permission_scope

    return get_permission_scope(user, organization, PERM_IMPORT)


def scope_groups(queryset, user, organization):
    """Qrup queryset-ini aktorun ``user.import`` əhatəsi ilə daraldır (fail-closed)."""
    scope = import_scope(user, organization)
    if scope.is_org_wide and not scope.excluded_unit_ids:
        return queryset
    if not scope.has_structure_access:
        return queryset.none()
    return queryset.filter(scope.unit_subtree_q())


def group_allowed(user, organization, group) -> bool:
    if group is None or organization is None:
        return False
    from apps.organizations.models import OrgUnit

    base = OrgUnit.objects.filter(organization=organization, pk=group.pk)
    return scope_groups(base, user, organization).exists()


def enforce_group_scope(plans, *, user, organization) -> None:
    """Yaradılacaq (``status == "create"``) sətirlərdən əhatədən kənar qrupa yazılanları XƏTA edir (yerində)."""
    scope = import_scope(user, organization)
    if scope.is_org_wide and not scope.excluded_unit_ids:
        return
    candidates = [plan for plan in plans if plan.status == "create"]
    if not candidates:
        return
    from apps.organizations.models import OrgUnit

    group_ids = {plan.targets["group"].pk for plan in candidates if plan.targets.get("group") is not None}
    allowed = set()
    if group_ids:
        base = OrgUnit.objects.filter(organization=organization, pk__in=list(group_ids))
        allowed = set(scope_groups(base, user, organization).values_list("pk", flat=True))
    for plan in candidates:
        group = plan.targets.get("group")
        if group is None or group.pk not in allowed:
            plan.fail(
                "group_outside_scope",
                pgettext(_CTX, "Bu qrupa tələbə əlavə etmək icazəniz yoxdur — yalnız öz qruplarınızı seçin."),
            )


__all__ = ["PERM_IMPORT", "enforce_group_scope", "group_allowed", "import_scope", "scope_groups"]
