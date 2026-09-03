"""Marşrutlaşdırma — «Digər» ailəyə görə ayrılır, əcdad düzgün tapılır."""

from __future__ import annotations

import pytest

from apps.applications.constants import SenderFamily
from apps.applications.services.routing import (
    allowed_kinds_for,
    route_for,
    sender_family_for,
    sender_scope_unit_for,
)
from apps.applications.tests.factories import add_member, kind_of, make_user, make_world

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    return make_world("routing")


def test_family_comes_from_the_active_membership(world):
    org = world["organization"]
    assert sender_family_for(world["student"], org) == SenderFamily.STUDENT.value
    assert sender_family_for(world["teacher"], org) == SenderFamily.TEACHER.value
    assert sender_family_for(world["dean"], org) == SenderFamily.STAFF.value


def test_user_without_an_active_membership_has_no_family(world):
    stranger = make_user("no-membership")
    assert sender_family_for(stranger, world["organization"]) is None


def test_student_other_goes_to_the_coordinator_of_their_specialty(world):
    unit, scope, family, sender_unit = route_for(
        kind_of(world, "diger"), world["student"], organization=world["organization"]
    )
    assert unit.code == "koordinator"
    assert scope == world["tree"]["specialty"]
    assert family == SenderFamily.STUDENT.value
    assert sender_unit == world["tree"]["group"]


def test_teacher_other_goes_to_the_chair(world):
    unit, scope, family, _sender = route_for(
        kind_of(world, "diger"), world["teacher"], organization=world["organization"]
    )
    assert unit.code == "kafedra"
    assert scope == world["tree"]["chair"]
    assert family == SenderFamily.TEACHER.value


def test_staff_other_goes_to_rim_with_no_scope(world):
    unit, scope, family, _sender = route_for(kind_of(world, "diger"), world["dean"], organization=world["organization"])
    assert unit.code == "rim"
    assert scope is None
    assert family == SenderFamily.STAFF.value


def test_student_complaint_resolves_to_the_faculty_dean(world):
    unit, scope, _family, _sender = route_for(
        kind_of(world, "sikayet"), world["student"], organization=world["organization"]
    )
    assert unit.code == "dekan"
    assert scope == world["tree"]["faculty"]


def test_central_units_never_carry_a_scope_unit(world):
    for code in ("transkript", "texniki", "odenis"):
        unit, scope, _family, _sender = route_for(
            kind_of(world, code), world["student"], organization=world["organization"]
        )
        assert scope is None, code
        assert unit.resolve_by == "organization"


def test_missing_ancestor_falls_back_to_an_unscoped_route(world):
    """Struktur qurulmamış tələbə üçün müraciət İTMİR, sadəcə əhatəsiz gedir."""
    org = world["organization"]
    orphan = make_user("orphan-student")
    add_member(org, orphan, "student", permissions=["application.create"], level=10)
    unit, scope, family, sender_unit = route_for(kind_of(world, "diger"), orphan, organization=org)
    assert unit.code == "koordinator"
    assert scope is None and sender_unit is None
    assert family == SenderFamily.STUDENT.value


def test_allowed_kinds_are_filtered_per_family(world):
    org = world["organization"]
    student_codes = {kind.code for kind in allowed_kinds_for(org, SenderFamily.STUDENT.value)}
    teacher_codes = {kind.code for kind in allowed_kinds_for(org, SenderFamily.TEACHER.value)}
    staff_codes = {kind.code for kind in allowed_kinds_for(org, SenderFamily.STAFF.value)}

    assert "transkript" in student_codes and "transkript" not in teacher_codes
    assert "teqdimat" in teacher_codes and "teqdimat" not in student_codes
    assert "hr" in staff_codes and "hr" not in student_codes
    assert "diger" in student_codes and "diger" in teacher_codes and "diger" in staff_codes


def test_student_scope_unit_prefers_the_academic_record(world):
    """Qeydiyyat sətri (SAR) varsa qrup ONDAN gəlir, üzvlükdən yox."""
    from apps.registrar.models import Curriculum, Program, StudentAcademicRecord

    org = world["organization"]
    other_group = world["other_tree"]["group"]
    program = Program.objects.create(organization=org, code="P-ROUTE", name="Proqram")
    curriculum = Curriculum.objects.create(organization=org, program=program, admission_year=2025)
    StudentAcademicRecord.objects.create(
        organization=org,
        student=world["student"],
        program=program,
        curriculum=curriculum,
        group=other_group,
        admission_year=2025,
    )
    assert sender_scope_unit_for(world["student"], org, SenderFamily.STUDENT.value) == other_group

    unit, scope, _family, _sender = route_for(kind_of(world, "diger"), world["student"], organization=org)
    assert unit.code == "koordinator"
    assert scope == world["other_tree"]["specialty"]
