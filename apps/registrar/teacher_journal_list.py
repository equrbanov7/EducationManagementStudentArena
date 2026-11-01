"""Current workload vs own recorded history, inside canonical journal access only."""

from collections import defaultdict
from types import SimpleNamespace

from django.apps import apps as django_apps
from django.db.models import BooleanField, Case, Count, Exists, OuterRef, Q, Sum, Value, When
from django.utils import timezone

from core.group_identity import canonical_aliases

from .current_handover_journals import kind_filters as handover_kind_filters
from .journal_assignment_sources import teacher_journal_assignments
from .journal_master_history import attach as attach_master_history
from .journal_master_history import historical_marks, identity_q
from .journal_own_history import recorded_lessons
from .models import Enrollment, JournalShare, Lesson, SlotKind
from .practical_label import kind_choices

KINDS = ("lecture", "seminar", "lab")
GROUP_FIELDS = ("id", "name", "organization_id", "parent_id", "is_active", "settings", "unit_type")


def _workload_filters(queryset, user, organization):
    assignments = teacher_journal_assignments(organization=organization, teacher_id=user.pk)
    rows = queryset.exclude(group_id=None).order_by().values(*(f"group__{f}" for f in GROUP_FIELDS)).distinct()
    groups = [
        SimpleNamespace(pk=row["group__id"], **{f: row[f"group__{f}"] for f in GROUP_FIELDS if f != "id"})
        for row in rows
    ]
    aliases = canonical_aliases(groups)
    families = defaultdict(set)
    for group in groups:
        families[aliases.get(group.pk, group).pk].add(group.pk)
    filters = {kind: Q(pk__in=[]) for kind in KINDS}
    for (subject_id, period_id, group_id), kinds in assignments.items():
        if subject_id is None and period_id is None:
            match = Q(pk=group_id)
        else:
            family = families.get(group_id)
            if not family:
                continue
            match = Q(subject_id=subject_id, period_id=period_id, group_id__in=family)
        for kind in kinds:
            filters[kind] |= match
    return filters


def own_visible_queryset(queryset, user, organization):
    """Personal list authority and projection shared by the journal page and dashboard."""
    from .handover import observer_offering_ids
    from .journal_own_history import eligible, offering_ids
    from .journal_shares import own_or_shared_q

    if not eligible(user, organization):
        return project(queryset.none(), user, organization)
    observed = observer_offering_ids(user, organization)
    authorized = queryset.filter(
        own_or_shared_q(user) | Q(pk__in=observed) | Q(pk__in=offering_ids(user, organization))
    )
    return project(authorized, user, organization, observed=observed)


def _recorded_exam_attempts(user):
    """Exact linked, non-trial academic activity; drafts alone supply no history."""
    return (
        django_apps.get_model("exams", "ExamAttempt")
        .objects.filter(
            exam__organization_id=OuterRef("organization_id"),
            exam__journal_offerings=OuterRef("pk"),
            is_trial=False,
            status__in=("in_progress", "submitted", "expired"),
        )
        .filter(Q(exam__author=user) | Q(exam__journal_teacher=user))
    )


def project(queryset, user, organization, *, observed=()):
    """Do not add a single offering to the already-authorized own/share/observer set."""
    if queryset.query.is_empty():
        flags = {
            "journal_is_current_load",
            "journal_has_records",
            "journal_is_owned_past_history",
            "journal_is_master_history",
            "journal_has_assessment_history",
        }
        flags.update(f"journal_{prefix}_{kind}" for prefix in ("current", "recorded") for kind in KINDS)
        flags.update(f"journal_master_{kind}" for kind in KINDS)
        return queryset.annotate(**{name: Value(False) for name in flags})
    filters = _workload_filters(queryset, user, organization)
    recorded = recorded_lessons(user).filter(organization_id=OuterRef("organization_id"), offering_id=OuterRef("pk"))
    annotations = {
        "journal_has_records": Exists(recorded),
        "journal_has_assessment_history": Exists(_recorded_exam_attempts(user)),
    }
    master = identity_q(user, organization)
    master_marks = historical_marks()
    annotations["journal_is_master_history"] = Case(
        When(master, then=Exists(master_marks)), default=Value(False), output_field=BooleanField()
    )
    registered = Enrollment.objects.filter(organization_id=OuterRef("organization_id"), offering_id=OuterRef("pk"))
    # Existing ownership is canonical read authority. A populated past journal
    # remains discoverable, without attributing anonymous legacy lessons/hours.
    annotations["journal_is_owned_past_history"] = Case(
        When(
            instructor=user,
            period__is_current=False,
            period__end_date__lt=timezone.localdate(),
            then=Exists(registered),
        ),
        default=Value(False),
        output_field=BooleanField(),
    )
    current = Q(pk__in=[])
    handed_over = handover_kind_filters(user, organization)
    for kind, condition in filters.items():
        shares = JournalShare.objects.filter(teacher=user, is_active=True).filter(
            Q(kinds=[]) | Q(kinds__contains=[kind])
        )
        condition &= Q(instructor=user) | Q(pk__in=shares.values("offering_id"))
        condition |= handed_over[kind]
        annotations[f"journal_current_{kind}"] = Case(
            When(condition, then=Value(True)), default=Value(False), output_field=BooleanField()
        )
        annotations[f"journal_recorded_{kind}"] = Exists(recorded.filter(kind=kind))
        annotations[f"journal_master_{kind}"] = Case(
            When(master, then=Exists(master_marks.filter(lesson__kind=kind))),
            default=Value(False),
            output_field=BooleanField(),
        )
        current |= condition
    annotations["journal_is_current_load"] = Case(
        When(current, then=Value(True)), default=Value(False), output_field=BooleanField()
    )
    return queryset.annotate(**annotations).filter(
        Q(journal_is_current_load=True)
        | Q(journal_has_records=True)
        | Q(journal_has_assessment_history=True)
        | Q(journal_is_owned_past_history=True)
        | Q(journal_is_master_history=True)
        | Q(pk__in=observed)
    )


def select_view(queryset, request):
    history = request is not None and request.GET.get("teaching") == "history"
    if request is not None and not request.GET.get("teaching") and request.GET.get("year"):
        history = queryset.filter(
            period__academic_year=request.GET["year"], journal_is_owned_past_history=True
        ).exists()
    return queryset.filter(journal_is_current_load=not history), "history" if history else "current"


def filter_kind(queryset, kind):
    return queryset.filter(
        Q(journal_is_current_load=True, **{f"journal_current_{kind}": True})
        | (
            Q(journal_is_current_load=False)
            & (Q(**{f"journal_recorded_{kind}": True}) | Q(**{f"journal_master_{kind}": True}))
        )
    )


def attach(user, offerings, *, selected_kind=""):
    """Distinct real lesson IDs, never marks×students or workload/patok multiplication.

    Teaching hours require explicit Lesson.instructor. created_by/entered_by also
    retain history but are described separately, never as paid/taught hours.
    """
    if not offerings:
        return
    ids = [offering.pk for offering in offerings]
    contributions = {
        (row["offering_id"], row["kind"]): row["count"]
        for row in recorded_lessons(user)
        .filter(offering_id__in=ids)
        .values("offering_id", "kind")
        .annotate(count=Count("pk"))
    }
    taught = {
        (row["offering_id"], row["kind"]): row
        for row in Lesson.objects.filter(offering_id__in=ids, instructor=user, date__lte=timezone.localdate())
        .values("offering_id", "kind")
        .annotate(count=Count("pk"), hours=Sum("hours"))
    }
    labels = dict(SlotKind.choices)
    for offering in offerings:
        current = offering.journal_is_current_load
        prefix = "journal_current_" if current else "journal_recorded_"
        kinds = [
            kind
            for kind in KINDS
            if getattr(offering, f"{prefix}{kind}", False)
            or (not current and getattr(offering, f"journal_master_{kind}", False))
        ]
        offering.slot_kinds = kinds
        shown = [kind for kind in kinds if kind == selected_kind] if selected_kind else kinds
        offering_labels = dict(kind_choices(offering, labels))
        offering.kind_label = " · ".join(str(offering_labels[kind]) for kind in shown)
        entry_kind = getattr(offering, "journal_entry_kind", "") or selected_kind
        count_kinds = [entry_kind] if entry_kind in KINDS else KINDS
        offering.journal_own_lessons = sum(taught.get((offering.pk, kind), {}).get("count", 0) for kind in count_kinds)
        offering.journal_own_hours = sum(taught.get((offering.pk, kind), {}).get("hours", 0) for kind in count_kinds)
        offering.journal_contributed_lessons = sum(contributions.get((offering.pk, kind), 0) for kind in count_kinds)
        offering.journal_own_history_link = not current and bool(offering.journal_contributed_lessons)
        attach_master_history(offering, kind=selected_kind)
