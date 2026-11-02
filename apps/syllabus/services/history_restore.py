"""Fill-only exact approved own-syllabus binding during an authorized load restore."""

from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction
from core.reviewed_graph import digest, rows

from ..content_fingerprints import topic_metrics, typed_hours
from ..models import ShareSource, Syllabus, SyllabusShare
from ..state_machine import TransitionDenied
from .sharing import CODE_ALREADY, CODE_HAS_OWN, _audit, target_code


def _language(group):
    if group is None:
        return ""
    settings = group.settings or {}
    values = {
        "az": "az",
        "aze": "az",
        "azərbaycan": "az",
        "en": "en",
        "ing": "en",
        "english": "en",
        "ru": "ru",
        "rus": "ru",
    }
    return values.get(str(settings.get("language") or settings.get("sector") or "").casefold(), "")


def approved_restore_sources(offering, *, chair_id=None, hours=None, context_for=None):
    """Exact subject/period/author/language and genuine approved topics; never fuzzy titles."""
    result = []
    candidates = (
        Syllabus.objects.filter(
            organization_id=offering.organization_id,
            subject_id=offering.subject_id,
            period_id=offering.period_id,
            author_id=offering.instructor_id,
            is_active=True,
            approved_version__status="approved",
            reused_from__isnull=True,
            offering__is_active=True,
            offering__instructor_id=offering.instructor_id,
            offering__organization_id=offering.organization_id,
            offering__subject_id=offering.subject_id,
            offering__period_id=offering.period_id,
        )
        .select_related("approved_version", "offering__group")
        .prefetch_related("approved_version__sections")
        .order_by("pk")
    )
    language = _language(offering.group)
    for source in candidates:
        version = source.approved_version
        parsed = typed_hours(version.plan_hours)
        if version.syllabus_id != source.pk or not parsed["valid"] or parsed["hours"].get("practical", 0):
            continue
        plan = {kind: parsed["hours"][kind] for kind in ("lecture", "seminar", "lab")}
        if sum(plan.values()) != offering.lesson_hours or hours is not None and plan != hours:
            continue
        if source.offering_id != offering.pk:
            if not language or _language(source.offering.group) != language or context_for is None:
                continue
            target_context, source_context = context_for(offering), context_for(source.offering)
            if target_context is None or source_context != target_context:
                continue
        if chair_id is not None and str(source.chair_unit_id) != str(chair_id):
            continue
        sections = {section.section_id: section.data for section in version.sections.all()}
        _, topics = topic_metrics(sections.get("week", {}))
        if not topics["nonempty_topic_count"] or topics["hours_without_topic_count"] or not topics["totals_complete"]:
            continue
        if any(topics["hours_by_kind"][kind] != plan[kind] for kind in plan):
            continue
        result.append(source)
    return result


@transaction.atomic
def bind_approved_restore_source(*, offering, actor, chair_id, hours, selected_id="", request=None, context_for=None):
    """Authorized workload operator chooses an existing teacher-owned approved body.

    Only the existing share relation is created; no draft, version, authorship,
    approval or content is changed. Caller must bind this to its academic graph
    transaction. Returned share_id is the sole permitted graph addition.
    """
    if (
        actor.organization.pk != offering.organization_id
        or not actor.has("workload.manage")
        or not actor.has("workload.distribute")
        or not actor.covers_unit(chair_id, "workload.manage")
        or not actor.covers_unit(chair_id, "workload.distribute")
    ):
        raise TransitionDenied("transition.permission_denied")
    candidates = approved_restore_sources(offering, chair_id=chair_id, hours=hours, context_for=context_for)
    source = (
        next((s for s in candidates if str(s.pk) == str(selected_id)), None)
        if selected_id
        else (candidates[0] if len(candidates) == 1 else None)
    )
    if selected_id and source is None:
        raise TransitionDenied("reuse.not_own_source")
    if source is None:
        return {"status": "ambiguous" if len(candidates) > 1 else "missing", "share_id": None}
    # Own approved dossier or existing identical share already serves this journal.
    state = target_code(offering, syllabus_id=source.pk)
    if state == CODE_ALREADY or source.offering_id == offering.pk:
        return {"status": "already_approved", "share_id": None}
    if state == CODE_HAS_OWN:
        return {"status": "own_dossier_preserved", "share_id": None}
    if state:
        raise TransitionDenied(state)
    source = Syllabus.objects.select_for_update(of=("self",)).get(pk=source.pk)
    # Recheck under native source locks; never bind a stale preflight version.
    source.offering.__class__.objects.select_for_update().get(pk=source.offering_id)
    source.approved_version.__class__.objects.select_for_update().get(pk=source.approved_version_id)
    source = next(
        (
            s
            for s in approved_restore_sources(offering, chair_id=chair_id, hours=hours, context_for=context_for)
            if s.pk == source.pk
        ),
        None,
    )
    if source is None:
        raise TransitionDenied("reuse.source_not_approved")
    version = source.approved_version
    before = digest(
        {
            "syllabus": rows(Syllabus.objects.filter(pk=source.pk)),
            "version": rows(version.__class__.objects.filter(pk=version.pk)),
            "sections": rows(version.sections.all()),
        }
    )
    share = SyllabusShare.objects.create(
        organization_id=offering.organization_id,
        offering=offering,
        syllabus=source,
        source=ShareSource.TEACHER,
        created_by=actor.user,
    )
    _audit(share, action=AuditAction.CREATE, user=actor.user, request=request, source="authorized_history_load_restore")
    after = digest(
        {
            "syllabus": rows(Syllabus.objects.filter(pk=source.pk)),
            "version": rows(version.__class__.objects.filter(pk=version.pk)),
            "sections": rows(version.sections.all()),
        }
    )
    if before != after:
        raise TransitionDenied("version.approved_locked")
    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=actor.organization,
        resource_type="syllabus.HistoryRestoreBinding",
        resource_id=str(offering.pk),
        reason="Exact approved own syllabus reused during explicit current workload restoration.",
        new_values={"syllabus_id": str(source.pk), "share_id": str(share.pk), "source_sha256": before},
        request=request,
    )
    return {"status": "approved_bound", "share_id": str(share.pk)}
