"""A corrected course/period must not retain another course's syllabus."""

from django.apps import apps

import pytest

from apps.registrar.semester_readiness import approved_syllabus_offering_ids
from apps.syllabus import services
from apps.syllabus.models import Syllabus
from apps.syllabus.services import sharing
from apps.syllabus.services.week_rows import approved_week_rows_for_offerings
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.reuse_fixtures import actor, approved_syllabus, build_world

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    value = build_world("syllabus-scope-integrity")
    value["source"], value["version"] = approved_syllabus(value, "o1")
    return value


def _change(world, instance, field):
    if field == "subject":
        model = apps.get_model("registrar", "Subject")
        replacement = model.objects.create(organization=world["org"], code="DIFFERENT", name="Başqa fənn")
    else:
        model = apps.get_model("organizations", "AcademicPeriod")
        replacement = model.objects.create(
            organization=world["org"],
            name="Yaz",
            academic_year="2025/2026",
            period_type="semester",
            start_date="2026-02-01",
            end_date="2026-07-01",
        )
    type(instance).objects.filter(pk=instance.pk).update(**{field: replacement})
    instance.refresh_from_db()


def _assert_missing(world, offering):
    assert services.syllabus_for_offering_obj(offering) is None
    assert offering.pk not in services.student_syllabus_map(world["org"], [offering])
    assert offering.pk not in approved_week_rows_for_offerings([offering])
    rows = [{"id": offering.pk, "subject_id": offering.subject_id, "instructor_id": offering.instructor_id}]
    assert offering.pk not in approved_syllabus_offering_ids(world["org"], offering.period, rows)


@pytest.mark.parametrize("field", ["subject", "period"])
def test_own_syllabus_stops_following_a_changed_course_or_period(world, field):
    offering = world["offerings"]["o1"]
    _change(world, offering, field)
    _assert_missing(world, offering)


@pytest.mark.parametrize("field", ["subject", "period"])
def test_shared_syllabus_stops_following_a_changed_target(world, field):
    offering = world["offerings"]["o2"]
    sharing.share(source=world["source"], offering=offering, actor=actor(world))
    _change(world, offering, field)
    assert sharing.shared_syllabus_ids([offering.pk]) == {}
    _assert_missing(world, offering)


@pytest.mark.parametrize("field", ["subject", "period"])
def test_shared_syllabus_stops_using_a_changed_source_offering(world, field):
    offering = world["offerings"]["o2"]
    sharing.share(source=world["source"], offering=offering, actor=actor(world))
    _change(world, world["offerings"]["o1"], field)
    assert sharing.shared_syllabus_ids([offering.pk]) == {}
    _assert_missing(world, offering)


def test_wrong_subject_dossier_does_not_mask_a_valid_base_syllabus(world):
    offering = world["offerings"]["o1"]
    _change(world, world["source"], "subject")
    base = Syllabus.objects.create(
        organization=world["org"],
        subject=world["subject"],
        author=world["teacher"],
        chair_unit=world["chair"],
    )
    assert services.syllabus_for_offering_obj(offering) == base


def test_legacy_bound_syllabus_without_period_remains_visible(world):
    offering = world["offerings"]["o1"]
    Syllabus.objects.filter(pk=world["source"].pk).update(period=None)
    assert services.syllabus_for_offering_obj(offering).pk == world["source"].pk
    assert services.student_syllabus_map(world["org"], [offering])[offering.pk] == world["source"].pk
    assert offering.pk in approved_week_rows_for_offerings([offering])


@pytest.mark.parametrize("field", ["subject", "period"])
def test_stale_editor_cannot_create_dossier_after_course_reassignment(world, field):
    offering = world["offerings"]["o2"]
    stale = type(offering).objects.get(pk=offering.pk)
    _change(world, offering, field)
    with pytest.raises(TransitionDenied, match="reuse.not_sibling"):
        services.create_draft(
            organization=world["org"],
            subject=world["subject"],
            period=world["period"],
            offering=stale,
            actor=actor(world),
            chair_unit=world["chair"],
        )
    assert not Syllabus.objects.filter(offering=offering).exists()
