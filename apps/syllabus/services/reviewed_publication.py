"""Explicit operator publication: the teacher is never impersonated."""

from copy import copy
from types import SimpleNamespace

from django.db import transaction
from django.utils import timezone

from ..content_fingerprints import content_fingerprints
from ..models import SyllabusVersion
from ..state_machine import Transition, TransitionDenied
from . import versioning, workflow
from .approval_hooks import reviewed_batch_without_carry
from .drafts import completion_report, recompute_completion, section_data_map


def reviewed_completion_report(*, version, sections, plan_hours):
    """Evaluate proposed fill-only content with the real native completion rules."""
    proposed = copy(version)
    proposed.plan_hours = dict(plan_hours)
    proposed._prefetched_objects_cache = {
        "sections": [SimpleNamespace(section_id=key, data=value) for key, value in sections.items()]
    }
    return completion_report(proposed)


@transaction.atomic
def publish_reviewed_draft(*, version, actor, expected_body_sha256, reason):
    """Publish a complete reviewed draft under the actual operator's identity.

    This is deliberately absent from UI available_actions. Ordinary author-only
    submission is unchanged. The caller owns explicit carry actions and receipt.
    """
    if not actor.is_superadmin or not actor.user.is_active or not str(reason or "").strip():
        raise TransitionDenied("reviewed_operator_required")
    locked = SyllabusVersion.objects.select_for_update(of=("self",)).get(pk=version.pk, organization=actor.organization)
    if content_fingerprints(section_data_map(locked))["canonical_body_sha256"] != expected_body_sha256:
        raise TransitionDenied("reviewed_body_changed")
    report = completion_report(locked)
    if report.percent != 100:
        raise TransitionDenied("transition.incomplete")
    # Run permissions and self-conflict checks before any persistent mutation.
    previous_completion = locked.completion_percent
    locked.completion_percent = report.percent
    workflow._guard(version=locked, actor=actor, name=Transition.REVIEWED_SUBMIT, reason=reason)
    workflow._guard_self_conflict(version=locked, actor=actor, name=Transition.REVIEWED_SUBMIT)
    locked.completion_percent = previous_completion
    locked, _ = versioning.escalate_if_structural(locked, actor=actor)
    recompute_completion(locked)
    now = timezone.now()
    with reviewed_batch_without_carry():
        submitted = workflow._apply(
            version=locked,
            actor=actor,
            name=Transition.REVIEWED_SUBMIT,
            reason=reason,
            comment="Reviewed operator submission; original teacher authorship preserved.",
            submitted_at=now,
            submitted_by=actor.user,
            locked_at=now,
            reviewer=None,
            review_started_at=None,
            decision_reason="",
        )
        return workflow.approve(version=submitted, actor=actor, comment=reason)
