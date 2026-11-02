"""Current released teaching is an affiliation for directory reading only."""

from django.apps import apps
from django.db.models import Q

from .permissions import PERM_VIEW_TEACHERS
from .scoping import structure_filter_q


def teaching_user_ids(actor, *, request=None, filters=None):
    """Do not grant membership, editing rights or access to unrelated courses."""
    scope = actor.scope_for(PERM_VIEW_TEACHERS, request=request)
    model = apps.get_model("workload", "TeacherAssignment")
    rows = model.objects.filter(
        organization=actor.organization,
        row__organization=actor.organization,
        row__task__organization=actor.organization,
        row__task__chair__organization=actor.organization,
        row__period__organization=actor.organization,
        row__period__is_current=True,
        row__period__is_active=True,
        hours__gt=0,
    ).filter(
        Q(row__task__status__in=("approved", "distributed", "amended"))
        | Q(row__task__status="distributing", row__task__submitted_at__isnull=False)
    )
    if not scope.has_structure_access:
        return rows.none().values("teacher_id")
    if not scope.is_org_wide:
        rows = rows.filter(scope.unit_subtree_q(path_field="row__task__chair__path", id_field="row__task__chair_id"))
    if filters is not None:
        rows = rows.filter(
            structure_filter_q(
                actor.organization, filters, path_field="row__task__chair__path", id_field="row__task__chair_id"
            )
        )
    return rows.order_by().values("teacher_id")
