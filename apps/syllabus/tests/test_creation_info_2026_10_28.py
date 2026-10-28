"""Yeni sillabusun müəllifi avtomatik dolur, məsləhət saatı təsdiqi saxlamır."""

from django.test import override_settings

import pytest

from apps.syllabus import services
from apps.syllabus.constants import SyllabusStatus
from apps.syllabus.models import ApprovalSource
from apps.syllabus.tests.factories import PLAN_HOURS
from apps.syllabus.tests.test_workflow import _fill
from apps.syllabus.tests.test_workflow import draft as _draft_fixture
from apps.syllabus.tests.test_workflow import world as _world_fixture

draft = _draft_fixture
world = _world_fixture
pytestmark = pytest.mark.django_db


def test_creation_prefills_actual_author_name(world):
    teacher = world["teacher"]
    teacher.first_name, teacher.last_name = "Sevinc", "Rəcəbova"
    teacher.save(update_fields=["first_name", "last_name"])
    actor = services.resolve_actor(teacher, world["org"])
    _, version = services.create_draft(
        organization=world["org"],
        subject=world["stack"]["subject"],
        period=world["stack"]["period"],
        actor=actor,
        offering=world["offering"],
        program=world["stack"]["program"],
        chair_unit=world["stack"]["chair"],
        plan_hours=PLAN_HOURS,
    )
    info = version.sections.get(section_id="info")
    assert info.data["teacher"] == "Sevinc Rəcəbova"
    assert info.data["office_hours"] == ""


@pytest.mark.parametrize("hours", ["", "x"])
@override_settings(SYLLABUS_APPROVAL_REQUIRED=False)
def test_optional_consultation_does_not_block_immediate_approval(draft, hours):
    _, version, actor = draft
    _fill(version, actor)
    _, report = services.save_section(version=version, section_id="info", data={"office_hours": hours}, actor=actor)
    assert report.percent == 100
    assert not any(issue.code == "info.office_hours_missing" for issue in report.issues)
    approved = services.submit(version=version, actor=actor)
    assert approved.status == SyllabusStatus.APPROVED
    assert approved.approval_source == ApprovalSource.AUTO
