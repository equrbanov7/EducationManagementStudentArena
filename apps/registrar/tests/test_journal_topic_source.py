"""Jurnal ↔ sillabus körpüsü — mövzu siyahısı və plan saatları.

İki qayda kilidlənir:

* **README §6.5 / §8/0:** jurnalın mövzu siyahısı TƏSDİQLƏNMİŞ sillabusun
  həftəlik planından gəlir; mövzu bir dəfə yazılır, saat isə mühazirə / seminar
  / laboratoriya üzrə ayrıca saxlanılır və mövzu hansı növlərə aid olduğunu
  daşıyır.  Sillabus yoxdursa köhnə mənbə (LMS kursu) qalır.
* **README §8/11:** sillabusun auditoriya saatı bazası TƏSDİQLƏNMİŞ tədris
  planının sətrindən oxunur (``registrar.plan_hours``).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

import pytest

from apps.organizations.models import OrgUnit
from apps.registrar import journal_topics
from apps.registrar.models import Curriculum, CurriculumSubject, PlanStatus
from apps.registrar.plan_hours import plan_hours_for_offering, program_for_offering
from apps.syllabus import services
from apps.syllabus.constants import SectionKey
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)
from core.constants import OrgUnitType, RoleScopeType

User = get_user_model()

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]

pytestmark = pytest.mark.django_db


@pytest.fixture()
def bridge():
    org = make_org("syl-bridge")
    teacher = User.objects.create_user("br_teacher", "br_teacher@x.test", "pw")
    chair = User.objects.create_user("br_chair", "br_chair@x.test", "pw")
    stack = make_academic_stack(org, code="BRG101")
    activate_member(org, teacher, "teacher", permissions=TEACHER_PERMS)
    activate_member(
        org,
        chair,
        "chair_head",
        permissions=CHAIR_PERMS,
        scope_unit=stack["chair"],
        level=70,
        scope_type=RoleScopeType.UNIT,
    )
    offering = make_offering(org, stack, teacher)
    return {"org": org, "teacher": teacher, "chair": chair, "stack": stack, "offering": offering}


def _approved_syllabus(bridge):
    actor = services.resolve_actor(bridge["teacher"], bridge["org"])
    _syllabus, version = services.create_draft(
        organization=bridge["org"],
        subject=bridge["stack"]["subject"],
        period=bridge["stack"]["period"],
        actor=actor,
        offering=bridge["offering"],
        program=bridge["stack"]["program"],
        chair_unit=bridge["stack"]["chair"],
        plan_hours=dict(PLAN_HOURS),
    )
    for section_id, data in complete_section_data().items():
        if section_id in {SectionKey.PREV.value, SectionKey.SEND.value}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=actor)
    version.refresh_from_db()
    version = services.submit(version=version, actor=actor)
    chair_actor = services.resolve_actor(bridge["chair"], bridge["org"])
    return services.approve(version=version, actor=chair_actor)


# ── Mövzu mənbəyi ────────────────────────────────────────────────────────────


def test_without_a_syllabus_the_topic_list_is_empty(bridge):
    """LMS kursu da yoxdursa siyahı boşdur — şablon sərbəst mətn göstərir."""
    assert journal_topics.syllabus_topic_rows(bridge["offering"]) == []
    assert journal_topics.lesson_topic_choices(bridge["offering"]) == []


def test_a_draft_syllabus_does_not_leak_into_the_journal(bridge):
    actor = services.resolve_actor(bridge["teacher"], bridge["org"])
    _syllabus, version = services.create_draft(
        organization=bridge["org"],
        subject=bridge["stack"]["subject"],
        period=bridge["stack"]["period"],
        actor=actor,
        offering=bridge["offering"],
        chair_unit=bridge["stack"]["chair"],
        plan_hours=dict(PLAN_HOURS),
    )
    services.save_section(
        version=version,
        section_id=SectionKey.WEEK.value,
        data=complete_section_data()[SectionKey.WEEK.value],
        actor=actor,
    )
    assert journal_topics.lesson_topic_choices(bridge["offering"]) == []


def test_the_approved_weekly_plan_becomes_the_journal_topic_list(bridge):
    _approved_syllabus(bridge)

    titles = journal_topics.lesson_topic_choices(bridge["offering"])

    assert titles[:3] == ["Mövzu 1", "Mövzu 2", "Mövzu 3"]
    # 14 dolu həftə — boş sətirlər mövzu siyahısına düşmür.
    assert len(titles) == 14


def test_each_topic_carries_the_lesson_kinds_it_has_hours_for(bridge):
    _approved_syllabus(bridge)

    rows = {row["title"]: row["kinds"] for row in journal_topics.syllabus_topic_rows(bridge["offering"])}

    # Fixture hər dolu həftəyə üç növ üzrə də saat verir (30/16/14 bölgüsü).
    assert rows["Mövzu 2"] == ("lecture", "seminar", "lab")


def test_the_meta_rows_expose_the_kinds_and_the_covered_flag(bridge):
    _approved_syllabus(bridge)

    meta = journal_topics.lesson_topic_meta(bridge["offering"], [])

    first = meta[0]
    assert first["title"] == "Mövzu 1"
    assert first["covered"] is False
    assert first["kinds_attr"] == "lecture seminar lab"
    assert first["covered_kinds"] == []


def test_a_held_lesson_marks_its_topic_and_records_the_kind(bridge):
    _approved_syllabus(bridge)

    class _Lesson:
        topic = "Mövzu 1"
        date = None
        kind = "seminar"

    meta = {row["title"]: row for row in journal_topics.lesson_topic_meta(bridge["offering"], [_Lesson()])}

    assert meta["Mövzu 1"]["covered"] is True
    assert meta["Mövzu 1"]["covered_kinds"] == ["seminar"]
    assert meta["Mövzu 2"]["covered"] is False


# ── Plan saatları ────────────────────────────────────────────────────────────


def _approved_curriculum(bridge, *, hours):
    curriculum = Curriculum.objects.create(
        organization=bridge["org"],
        program=bridge["stack"]["program"],
        admission_year=2025,
        status=PlanStatus.APPROVED,
    )
    CurriculumSubject.objects.create(
        organization=bridge["org"],
        curriculum=curriculum,
        subject=bridge["stack"]["subject"],
        semester_number=1,
        credits=5,
        total_hours=150,
        **{f"{kind}_hours": value for kind, value in hours.items()},
    )
    return curriculum


def _link_group_to_program(bridge):
    speciality = OrgUnit.objects.create(
        organization=bridge["org"],
        name="İxtisas bölməsi",
        slug=f"{bridge['org'].slug}-spec",
        unit_type=OrgUnitType.SPECIALTY,
    )
    OrgUnit.objects.filter(pk=bridge["stack"]["group"].pk).update(parent=speciality)
    bridge["stack"]["group"].refresh_from_db()
    program = bridge["stack"]["program"]
    program.specialty_unit = speciality
    program.save(update_fields=["specialty_unit"])
    bridge["offering"].refresh_from_db()
    return program


def test_no_approved_plan_means_no_hour_constraint(bridge):
    """Plan yoxdursa BOŞ bölgü — uydurma saat yazılmır (fail-open by design)."""
    assert plan_hours_for_offering(bridge["offering"]) == {}


def test_a_draft_plan_is_not_a_source_of_truth(bridge):
    curriculum = _approved_curriculum(bridge, hours={"lecture": 30, "seminar": 16, "lab": 14})
    Curriculum.objects.filter(pk=curriculum.pk).update(status=PlanStatus.DRAFT)
    assert plan_hours_for_offering(bridge["offering"]) == {}


def test_the_approved_plan_row_supplies_the_per_kind_hours(bridge):
    _approved_curriculum(bridge, hours={"lecture": 30, "seminar": 16, "lab": 14})

    assert plan_hours_for_offering(bridge["offering"]) == {"lecture": 30, "seminar": 16, "lab": 14}


def test_zero_hour_kinds_are_dropped_so_they_never_constrain_the_week(bridge):
    _approved_curriculum(bridge, hours={"lecture": 30, "seminar": 0, "lab": 0})

    assert plan_hours_for_offering(bridge["offering"]) == {"lecture": 30}


def test_the_offering_program_is_resolved_through_the_group_parent(bridge):
    program = _link_group_to_program(bridge)

    assert program_for_offering(bridge["offering"]) == program
