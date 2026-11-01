"""A missing source instructor or end cannot silently create a weekly timetable."""

from types import SimpleNamespace

from django.core.management.base import CommandError

import pytest

from apps.registrar.timetable_inference import Rules
from apps.registrar.timetable_inference_safety import configure_options, inference_teacher, secure_units, validate_rules


def options(**updates):
    return dict(legacy_heuristics=False, snap_minutes=None, recent_days=None, min_occurrences=2, **updates)


def test_safe_defaults_disable_snap_and_single_lesson_promotion():
    value = options()
    assert configure_options(value) is True
    assert value["snap_minutes"] == value["recent_days"] == 0
    assert Rules().snap_minutes == Rules().recent_days == 0
    validate_rules(Rules())


@pytest.mark.parametrize("values", [{"snap_minutes": 25}, {"recent_days": 14}, {"min_occurrences": 1}])
def test_unsafe_command_options_require_explicit_legacy_mode(values):
    value = options()
    value.update(values)
    with pytest.raises(CommandError):
        configure_options(value)
    with pytest.raises(ValueError):
        validate_rules(Rules(**values))


def test_historical_mode_remains_explicit_and_available():
    value = options()
    value["legacy_heuristics"] = True
    assert configure_options(value) is False
    assert (value["snap_minutes"], value["recent_days"]) == (25, 14)
    assert inference_teacher(None, 99, True, safe_mode=False) == 99


def test_source_lessons_never_default_to_current_owner():
    assert inference_teacher(None, 99, False, safe_mode=True) is None
    assert inference_teacher(None, 99, True, safe_mode=True) is None
    assert inference_teacher(14, 99, True, safe_mode=True) is None
    assert inference_teacher(14, 99, False, safe_mode=True) == 14


def test_different_real_end_times_and_foreign_room_are_held():
    unit = SimpleNamespace(
        facts=[SimpleNamespace(end="10:00"), SimpleNamespace(end="10:30")],
        status="ready",
        reason="",
        room="Elsewhere",
        room_source="teacher",
        room_alternatives=[("A1", "lessons"), ("B2", "teacher_slot")],
    )
    secure_units([unit])
    assert (unit.status, unit.reason) == ("ambiguous", "actual_end_conflict")
    assert (unit.room, unit.room_source) == ("", "")
    assert unit.room_alternatives == [("A1", "lessons")]


@pytest.mark.django_db
def test_loader_holds_unattributed_synthesised_missing_end_and_offschedule_lessons():
    import datetime as dt

    from django.contrib.auth import get_user_model

    from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
    from apps.registrar.models import CourseOffering, Lesson, Subject
    from apps.registrar.timetable_inference import load_facts
    from core.rls import bypass_rls

    teacher = get_user_model().objects.create_user("strict.timetable.teacher")
    with bypass_rls():
        org = Organization.objects.create(
            name="Strict timetable", slug="strict-timetable", owner=teacher, org_type="university", status="active"
        )
        Membership.objects.create(user=teacher, organization=org, role=org.roles.get(name="teacher"), is_active=True)
        period = AcademicPeriod.objects.create(
            organization=org,
            name="Payız",
            academic_year="2026/2027",
            start_date=dt.date(2026, 9, 15),
            end_date=dt.date(2027, 2, 1),
        )
        group = OrgUnit.objects.create(organization=org, name="TT", slug="strict-tt", unit_type="group")
        subject = Subject.objects.create(organization=org, code="TT", name="TT")
        offering = CourseOffering.objects.create(
            organization=org, subject=subject, period=period, group=group, instructor=teacher
        )
        from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow

        chair = OrgUnit.objects.create(organization=org, name="TT Chair", slug="strict-tt-chair", unit_type="chair")
        task = TeachingTask.objects.create(
            organization=org, chair=chair, academic_year="2026/2027", status="distributed"
        )
        row = TeachingTaskRow.objects.create(
            organization=org, task=task, subject=subject, period=period, lecture_total=30
        )
        row.groups.add(group)
        TeacherAssignment.objects.create(organization=org, row=row, teacher=teacher, activity="lecture", hours=30)
        for changes in (
            {},
            {"instructor": teacher, "end_time": None},
            {"instructor": teacher, "is_legacy_synthesised": True},
            {"instructor": teacher, "off_schedule_reason": "Replacement"},
            {"instructor": teacher},
            {"instructor": teacher, "kind": "seminar"},
        ):
            args = dict(
                organization=org,
                offering=offering,
                date=dt.date(2026, 10, 26),
                start_time=dt.time(11, 30),
                end_time=dt.time(13),
            )
            args.update(changes)
            Lesson.objects.create(**args)
        facts, stats = load_facts(organization=org, period=period, date_from=period.start_date, date_to=period.end_date)
    assert len(facts) == 1
    assert (facts[0].start, facts[0].end, facts[0].teacher_id) == (dt.time(11, 30), dt.time(13), teacher.pk)
    assert stats["no_teacher"] == 2 and stats["no_time"] == 1 and stats["off_schedule"] == 1
    assert stats["no_current_allocation"] == 1
