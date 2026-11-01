"""Selected-teacher joint journals: canonical per-member observation, never impersonation."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from . import journal_access, journal_shares


def _teacher(teacher_id):
    try:
        pk = int(teacher_id)
    except (ValueError, TypeError):
        return None
    return get_user_model().objects.filter(pk=pk, is_active=True).first() if pk > 0 else None


def allowed(joints, actor, *, request=None):
    if not actor.is_authenticated or not actor.is_active:
        return []
    from . import corrections, guest_roster

    corrector = bool(request is not None and request.user.pk == actor.pk and corrections.can_correct_journal(request))
    request_org = getattr(getattr(request, "organization", None), "pk", None)
    result = []
    for joint in joints:
        for offering in joint.offerings:
            if not (
                journal_access.can_edit_journal(actor, offering)
                or journal_access.can_observe_journal(actor, offering)
                or (corrector and request_org == offering.organization_id)
                or guest_roster.can_manage_offering_roster(actor, offering)
            ):
                break
            scope = journal_shares.journal_scope(actor, offering)
            if scope.enrollment_ids is not None or not scope.allows_kind(joint.kind):
                break
        else:
            result.append(joint)
    return result


def project(queryset, *, organization, actor, teacher_id, selected_kind, request=None):
    teacher = _teacher(teacher_id)
    if teacher is None:
        return queryset
    from .joint_journal_list import project as project_entries

    return project_entries(
        queryset,
        organization=organization,
        user=teacher,
        selected_kind=selected_kind,
        observer=actor,
        observer_request=request,
    )


def detail(request, *, organization, source_row_id, kind, teacher_id):
    # Even an actor who can edit a physical journal gets no POST route through
    # this observation link. Their existing canonical correction route stays separate.
    if request.method != "GET":
        raise PermissionDenied
    teacher = _teacher(teacher_id)
    if teacher is None:
        raise PermissionDenied
    from .joint_journal import selections

    found = [
        joint
        for joint in allowed(selections(organization=organization, user=teacher), request.user, request=request)
        if str(joint.source_row_id) == str(source_row_id) and joint.kind == kind
    ]
    if len(found) != 1:
        raise PermissionDenied
    from .joint_journal_views import _render_detail

    return _render_detail(request, found[0], record_user=teacher, read_only=True)
