"""Neutral carry-history hint, never a teacher-hour or mark projection."""

from django.db.models import Exists, OuterRef, Q

from .enrollment_history import predecessors
from .models import CourseOffering, JournalShare, LessonMark


def available(user, offerings, *, organization, kinds=None, enrollment_ids=None):
    """Return only IDs already authorized by the existing personal journal scope.

    Exact predecessor validation is the same provider used by carry_over_map.
    This query detects persisted marks, including zero scores. It does not load
    their values, calculate any counter, or add source courses to the list.
    Queries are batched across the whole page, never one per offering/student.
    """
    if user is None or organization is None or not offerings:
        return set()
    from .teacher_journal_list import own_visible_queryset

    ids = {o.pk for o in offerings if o.organization_id == organization.pk}
    authorized = own_visible_queryset(
        CourseOffering.objects.filter(organization=organization, pk__in=ids), user, organization
    ).values("pk")
    source_marks = LessonMark.objects.filter(
        organization=organization,
        enrollment_id=OuterRef("pk"),
        lesson__organization=organization,
        lesson__offering_id=OuterRef("offering_id"),
    )
    # Conservatively honor caller-owned partial roster shares in one batched
    # query. An owner can see additional unclaimed rows elsewhere; this neutral
    # hint never expands that share to disclose another student's history.
    shares = {}
    for oid, share_kinds, eid in JournalShare.objects.filter(
        organization=organization, teacher=user, is_active=True, offering_id__in=ids
    ).values_list("offering_id", "kinds", "enrollments__id"):
        bucket = shares.setdefault(oid, {"kinds": share_kinds, "rows": set(), "all": False})
        if eid is None:
            bucket["all"] = True
        else:
            bucket["rows"].add(str(eid))
    allowed = Q(pk__in=[])
    for oid in ids:
        selected = (kinds or {}).get(oid)
        condition = Q(enrollment__superseded_by__offering_id=oid)
        if selected is not None:
            condition &= Q(lesson__kind__in=selected)
        share = shares.get(oid)
        if share:
            if share["kinds"]:
                condition &= Q(lesson__kind__in=share["kinds"])
            if not share["all"]:
                condition &= Q(enrollment__superseded_by_id__in=share["rows"])
        roster = (enrollment_ids or {}).get(oid)
        if roster is not None:
            condition &= Q(enrollment__superseded_by_id__in=roster)
        allowed |= condition
    source_marks = source_marks.filter(allowed)
    return set(
        predecessors()
        .filter(
            organization=organization,
            superseded_by__offering_id__in=authorized,
            superseded_by__status="enrolled",
        )
        .annotate(has_visible_prior_marks=Exists(source_marks))
        .filter(has_visible_prior_marks=True)
        .values_list("superseded_by__offering_id", flat=True)
        .distinct()
    )


def attach(user, offerings, *, selected_kind=""):
    candidates = [o for o in offerings if not o.journal_own_lessons and not o.journal_own_hours]
    for offering in offerings:
        offering.journal_prior_history_available = False
    if not candidates:
        return
    visible = available(
        user,
        candidates,
        organization=candidates[0].organization,
        kinds={
            o.pk: (
                [getattr(o, "journal_entry_kind", "") or selected_kind]
                if getattr(o, "journal_entry_kind", "") or selected_kind
                else getattr(o, "slot_kinds", None)
            )
            for o in candidates
        },
    )
    for offering in candidates:
        offering.journal_prior_history_available = offering.pk in visible
