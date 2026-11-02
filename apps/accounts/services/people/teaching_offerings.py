"""Directory teaching metadata follows subject/workload chair, never a home-chair shortcut."""

from django.apps import apps
from django.db.models import Q

from apps.organizations.public import kafedra_unit_types, permission_scope_units
from apps.registrar.public import offering_chairs

from .permissions import PERM_VIEW_TEACHERS


def scoped_owned_offerings(target, actor, *, request=None):
    """Keep existing ownership/hours semantics; fix only structural read visibility.

    A chair is a sibling of the specialty/group in imported university trees.
    Filtering only group.path therefore made legitimate teachers' detail cards
    empty. The same canonical subject/workload chair map as journal filtering is
    used here. Faculty/group scopes retain their original group-tree meaning.
    This grants no membership, journal editing or access to another chair.
    """
    organization = actor.organization
    queryset = apps.get_model("registrar.CourseOffering").objects.filter(
        organization=organization, instructor=target, is_active=True
    )
    if organization is None or not actor.can_view_teachers:
        return queryset.none()
    scope = actor.scope_for(PERM_VIEW_TEACHERS, request=request)
    if not scope.has_structure_access:
        return queryset.none()
    if scope.is_org_wide:
        return queryset
    units = [
        unit
        for unit in permission_scope_units(actor.user, organization, PERM_VIEW_TEACHERS)
        if unit.pk in scope.unit_ids
    ]
    chair_types = kafedra_unit_types(organization)
    chairs = {str(unit.pk) for unit in units if unit.unit_type in chair_types}
    if not chairs:
        return queryset.filter(scope.unit_subtree_q(path_field="group__path", id_field="group_id"))
    condition = Q(pk__in=[])
    for unit in units:
        if str(unit.pk) not in chairs:
            condition |= Q(group_id=unit.pk)
            if unit.path:
                condition |= Q(group__path__startswith=unit.path + "/")
    mapping = offering_chairs.offering_chairs(queryset, organization.pk)
    allowed = [pk for pk, owners in mapping.items() if chairs.intersection(owners)]
    return queryset.filter(condition | Q(pk__in=allowed))
