"""Conservative inference defaults; legacy heuristics require an explicit opt-in."""

from django.core.management.base import CommandError


def inference_teacher(own, owner, legacy, *, safe_mode):
    # A retained foreign journal can have a new owner; authorless history is not
    # teaching attribution. Synthesised source lessons need separate reviewed proof.
    return own if safe_mode and not legacy else None if safe_mode else own or owner


def configure_options(options):
    legacy = options["legacy_heuristics"]
    for key, historical in (("snap_minutes", 25), ("recent_days", 14)):
        if options[key] is None:
            options[key] = historical if legacy else 0
    if not legacy and (options["snap_minutes"] or options["recent_days"] or options["min_occurrences"] < 2):
        raise CommandError("timetable_infer_review_required_for_heuristics: --legacy-heuristics")
    return not legacy


def validate_rules(rules):
    if rules.safe_mode and (rules.snap_minutes or rules.recent_days or rules.min_occurrences < 2):
        raise ValueError("unsafe_inference_requires_legacy_mode")


def secure_units(units):
    for unit in units:
        if len({fact.end for fact in unit.facts}) > 1:
            unit.status, unit.reason = "ambiguous", "actual_end_conflict"
        if unit.room_source != "lessons":
            unit.room, unit.room_source = "", ""
        unit.room_alternatives = [(room, source) for room, source in unit.room_alternatives if source == "lessons"]


def positive_allocations(organization, period):
    from django.apps import apps

    assignment = apps.get_model("workload.TeacherAssignment")
    # Exact kind/group only. Free-form subgroup notes are not permission to infer
    # whole-row teaching; drafts and retained transfer history do not confer slots.
    query = assignment.objects.filter(
        organization=organization,
        row__organization=organization,
        row__period=period,
        row__task__organization=organization,
        row__task__academic_year=period.academic_year,
        row__subject__organization=organization,
        row__groups__organization=organization,
        row__task__status__in=("approved", "distributing", "distributed", "amended"),
        row__row_kind="teaching",
        hours__gt=0,
        teacher_id__isnull=False,
        activity__in=("lecture", "seminar", "lab"),
        groups_note="",
        note="",
    )
    return set(query.values_list("row__subject_id", "row__groups__id", "teacher_id", "activity"))
