"""Source-reviewed narrow workload grants; no owner, role or academic writes."""

import json
import re
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction
from core.tenancy import request_has_active_organization_context

from .integrity import is_authorized_instructor
from .journal_shares import _MEMO_ATTR, active_shares, forget, journal_scope
from .models import Enrollment, JournalShare, JournalShareSource, Lesson, LessonKind


def _scope_signature(user, offering):
    forget(offering)
    scope = journal_scope(user, offering)
    return (scope.kinds, scope.enrollment_ids, scope.full, scope.can_manage_scores, scope.is_owner)


def reviewed_share_preserves_owner(*, offering, teacher_id, kinds, enrollment_ids):
    """Pure read-only projection: a new narrow share must not narrow its owner."""
    owner = get_user_model().objects.only("id", "is_active", "is_superuser").get(pk=offering.instructor_id)
    owner.set_active_organization_context(offering.organization)
    before = _scope_signature(owner, offering)
    shares = active_shares(offering)
    projected = SimpleNamespace(
        teacher_id=teacher_id, kinds=list(kinds), enrollment_id_set=frozenset(map(str, enrollment_ids))
    )
    try:
        setattr(offering, _MEMO_ATTR, shares + [projected])
        scope = journal_scope(owner, offering)
        after = (scope.kinds, scope.enrollment_ids, scope.full, scope.can_manage_scores, scope.is_owner)
        return before == after
    finally:
        forget(offering)


def _actor(actor, organization, *, lock=False):
    if not getattr(actor, "is_active", False) or not getattr(actor, "is_superuser", False):
        raise ValidationError("active_superadmin_required")
    live = get_user_model().objects.filter(pk=actor.pk, is_active=True, is_superuser=True)
    if lock:
        live = live.select_for_update()
    if live.values("id").first() is None:
        raise ValidationError("active_superadmin_required")
    selected = actor.get_active_organization()
    if (
        selected is None
        or selected.pk != organization.pk
        or not request_has_active_organization_context(
            SimpleNamespace(user=actor, organization=organization), allow_superadmin=True
        )
    ):
        raise ValidationError("actor_tenant_context_required")


@transaction.atomic
def create_reviewed_workload_share(*, offering, teacher, enrollment_ids, kinds, actor, source_sha256, batch):
    """Create one exact non-owner grant; existing grants are never widened.

    Caller must validate immutable official source and a fresh full-graph baseline.
    Explicit roster and kinds remain explicit even when covering the current grid.
    """
    _actor(actor, offering.organization)
    original_offering = offering
    offering = (
        type(offering)
        .objects.select_for_update(of=("self",))
        .select_related("organization", "period")
        .get(pk=offering.pk, organization_id=offering.organization_id)
    )
    _actor(actor, offering.organization, lock=True)
    kinds = sorted(set(kinds))
    ids = {str(pk) for pk in enrollment_ids}
    if not kinds or not set(kinds) <= set(LessonKind.values) or not ids:
        raise ValidationError("explicit_kind_and_roster_required")
    if not re.fullmatch(r"[a-f0-9]{64}", source_sha256) or not re.fullmatch(r"kindshare-[a-f0-9]{12}", batch):
        raise ValidationError("reviewed_source_and_batch_required")
    if teacher.pk == offering.instructor_id or not offering.is_active or offering.period.locked_at is not None:
        raise ValidationError("nonowner_active_open_offering_required")
    if not is_authorized_instructor(organization=offering.organization, instructor=teacher):
        raise ValidationError("active_authorized_teacher_required")
    from .handover import closed_offering_ids
    from .models import TeachingHandover

    if (
        offering.pk in closed_offering_ids([offering.pk])
        or TeachingHandover.objects.filter(offering=offering, reverted_at__isnull=True).exists()
    ):
        raise ValidationError("closed_or_handed_over_offering")
    valid = set(
        map(
            str,
            Enrollment.objects.filter(
                organization=offering.organization,
                offering=offering,
                pk__in=ids,
                status=Enrollment.Status.ENROLLED,
                superseded_by__isnull=True,
            ).values_list("pk", flat=True),
        )
    )
    if valid != ids:
        raise ValidationError("reviewed_roster_changed")
    if Lesson.objects.filter(offering=offering, instructor=teacher).exclude(kind__in=kinds).exists():
        raise ValidationError("unreviewed_owned_lesson_kind_requires_review")
    if JournalShare.objects.select_for_update().filter(offering=offering, teacher=teacher, is_active=True).exists():
        raise ValidationError("existing_teacher_share_requires_review")
    owner = get_user_model().objects.only("id", "is_active", "is_superuser").get(pk=offering.instructor_id)
    owner.set_active_organization_context(offering.organization)
    before = _scope_signature(owner, offering)
    share = JournalShare.objects.create(
        organization=offering.organization,
        offering=offering,
        teacher=teacher,
        kinds=kinds,
        source=JournalShareSource.WORKLOAD,
        batch=batch,
        created_by=actor,
    )
    share.enrollments.set(ids)
    if _scope_signature(owner, offering) != before:
        raise ValidationError("existing_owner_access_would_change")
    forget(offering)
    scope = journal_scope(teacher, offering)
    if scope.kinds != frozenset(kinds) or scope.enrollment_ids != frozenset(ids):
        raise ValidationError("reviewed_scope_broadened")
    log_action(
        AuditAction.CREATE,
        user=actor,
        organization=offering.organization,
        obj=share,
        reason="workload.reviewed_kind_share",
        new_values={"source_sha256": source_sha256, "kinds": kinds, "enrollment_count": len(ids), "batch": batch},
    )
    forget(original_offering)
    return share


@transaction.atomic
def undo_reviewed_workload_share(*, share_id, offering, actor, batch, expected_state):
    """Remove only the repair-created unchanged grant; audit history remains."""
    _actor(actor, offering.organization)
    original_offering = offering
    offering = (
        type(offering)
        .objects.select_for_update(of=("self",))
        .select_related("organization", "period")
        .get(pk=offering.pk, organization_id=offering.organization_id)
    )
    _actor(actor, offering.organization, lock=True)
    share = JournalShare.objects.select_for_update().get(
        pk=share_id, organization=offering.organization, offering=offering
    )
    through = JournalShare.enrollments.through
    actual = json.loads(
        json.dumps(
            {
                "share": JournalShare.objects.filter(pk=share.pk).values().get(),
                "students": list(through.objects.filter(journalshare_id=share.pk).order_by("pk").values()),
            },
            default=str,
        )
    )
    if actual != expected_state or share.source != JournalShareSource.WORKLOAD or share.batch != batch:
        raise ValidationError("undo_created_share_changed")
    # Refuse future descendants instead of cascading new history/configuration.
    through = JournalShare.enrollments.through
    for rel in share._meta.get_fields(include_hidden=True):
        if rel.auto_created and not rel.concrete and rel.related_model and rel.related_model is not through:
            raise ValidationError("undo_unknown_share_relation")
    owner = get_user_model().objects.only("id", "is_active", "is_superuser").get(pk=offering.instructor_id)
    owner.set_active_organization_context(offering.organization)
    owner_before = _scope_signature(owner, offering)
    log_action(
        AuditAction.DELETE,
        user=actor,
        organization=offering.organization,
        obj=share,
        reason="workload.reviewed_kind_share_undone",
        old_values=actual,
    )
    share.delete()
    if _scope_signature(owner, offering) != owner_before:
        raise ValidationError("undo_existing_owner_access_changed")
    forget(offering)
    forget(original_offering)
