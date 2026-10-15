"""Sahib 2026-10-15: «Sillabusda təlim nəticəsinin ancaq 1-ni yazmaq məcbur olsun, hər həftəyə görə olmasın.»

* ``out`` bölməsi: ən azı 1 dolu təlim nəticəsi (``MIN_OUTCOMES``) — əvvəl 3 idi və hər nəticə ən azı bir
  həftədə istifadə olunmalı idi (``out.orphan_outcomes``) — o qayda ləğv edilib.
* ``week`` bölməsi: həftə sətrinin nəticəyə bağlanması İSTƏYƏ BAĞLIDIR (``week.outcome_not_linked`` ləğv).
* 1 nəticə + nəticəsiz həftələr → 100% və göndərmə mümkündür; 0 nəticə → göndərmə bloklanır.
* ``recompute_syllabus_completion`` köhnə qaydanın keşini (faiz, bölmə bayrağı) yeni qaydaya gətirir.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command

import pytest

from apps.syllabus import completion, services
from apps.syllabus.constants import MIN_OUTCOMES, SectionKey, SyllabusStatus
from apps.syllabus.models import SyllabusSection, SyllabusVersion
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.editor_dom import render_editor_dom
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)

User = get_user_model()

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
OUT = SectionKey.OUT.value
WEEK = SectionKey.WEEK.value
SKIP = {SectionKey.PREV.value, SectionKey.SEND.value}
REMOVED_CODES = {"out.orphan_outcomes", "week.outcome_not_linked"}


def _one_outcome_no_links():
    """Tam sillabus, amma YALNIZ 1 təlim nəticəsi və heç bir həftə nəticəyə bağlanmayıb."""
    data = complete_section_data()
    data[OUT] = {"outcomes": ["Alqoritmin mürəkkəbliyini qiymətləndirir"]}
    for row in data[WEEK]["rows"]:
        row["outcome"] = ""
    return data


# ── 1. Domen qaydası (DB-siz) ───────────────────────────────────────────────
def test_only_one_outcome_is_required():
    assert MIN_OUTCOMES == 1


def test_one_outcome_and_weeks_without_outcome_are_complete():
    report = completion.evaluate(_one_outcome_no_links(), PLAN_HOURS)
    assert report.sections[OUT] is True
    assert report.sections[WEEK] is True
    assert report.percent == 100, report.as_dict()["issues"]
    assert not REMOVED_CODES & {issue.code for issue in report.issues}


def test_some_weeks_linked_and_some_not_is_still_complete():
    data = _one_outcome_no_links()
    data[WEEK]["rows"][0]["outcome"] = "TN1"
    report = completion.evaluate(data, PLAN_HOURS)
    assert report.sections[WEEK] is True and report.percent == 100


@pytest.mark.parametrize(
    "outcomes",
    [[], ["", "   "], ["qısa"]],  # boş / yalnız boşluq / MIN_OUTCOME_CHARS-dan qısa — sayılmır
    ids=["none", "blank", "too-short"],
)
def test_zero_valid_outcomes_block_the_outcomes_section(outcomes):
    data = _one_outcome_no_links()
    data[OUT] = {"outcomes": outcomes}
    report = completion.evaluate(data, PLAN_HOURS)
    assert report.sections[OUT] is False
    assert report.percent < 100
    issue = next(item for item in report.issues if item.code == "out.too_few")
    assert issue.params == {"min": 1, "have": 0}


# ── 2. Servis qatı: göndərmə ─────────────────────────────────────────────────
@pytest.fixture()
def world(db):
    org = make_org("lo-rule-org")
    teacher = User.objects.create_user("lo_rule_teacher", "lo_rule_teacher@x.test", "pw")
    activate_member(org, teacher, "teacher", permissions=TEACHER_PERMS)
    stack = make_academic_stack(org, code="LOR101")
    offering = make_offering(org, stack, teacher)
    actor = services.resolve_actor(teacher, org)
    _syllabus, version = services.create_draft(
        organization=org,
        subject=stack["subject"],
        period=stack["period"],
        actor=actor,
        offering=offering,
        program=stack["program"],
        chair_unit=stack["chair"],
        plan_hours=PLAN_HOURS,
    )
    return {"org": org, "teacher": teacher, "actor": actor, "version": version}


def _fill(world, data):
    version = world["version"]
    for section_id, payload in data.items():
        if section_id in SKIP:
            continue
        services.save_section(version=version, section_id=section_id, data=payload, actor=world["actor"])
    version.refresh_from_db()
    return version


def test_one_outcome_without_week_links_can_be_submitted(world):
    version = _fill(world, _one_outcome_no_links())
    assert version.completion_percent == 100
    assert version.sections.filter(section_id__in=[OUT, WEEK], is_complete=True).count() == 2
    submitted = services.submit(version=version, actor=world["actor"])
    assert submitted.status == SyllabusStatus.SUBMITTED


def test_zero_outcomes_block_the_submit(world):
    data = _one_outcome_no_links()
    data[OUT] = {"outcomes": []}
    version = _fill(world, data)
    assert version.completion_percent < 100
    with pytest.raises(TransitionDenied) as excinfo:
        services.submit(version=version, actor=world["actor"])
    assert excinfo.value.code == "transition.incomplete"


def test_editor_marks_the_week_outcome_optional_and_the_send_step_is_open(world):
    version = _fill(world, _one_outcome_no_links())
    root, se = render_editor_dom(user=world["teacher"], organization=world["org"], version=version)
    assert se["limits"]["outcomes"] == 1
    assert se["can_submit"] is True
    states = {step["id"]: step["state"] for step in se["nav"]}
    assert states[OUT] == "done" and states[WEEK] == "done"
    assert root.xpath("//table[contains(@class,'syl-weeks')]//th//*[contains(@class,'syl-weeks__opt')]")
    hint = " ".join(root.xpath("//*[@data-syl-panel='out']//p[contains(@class,'syl-hintbox')]//text()"))
    assert "Ən azı 1 təlim nəticəsi" in hint


# ── 3. Keş: köhnə qaydanın faizi əmrlə yenilənir ────────────────────────────
def test_recompute_command_lifts_a_draft_cached_under_the_old_rule(world):
    version = _fill(world, _one_outcome_no_links())
    # Köhnə qayda (3 nəticə + hər həftə bağlı) altında keşlənmiş vəziyyət.
    SyllabusSection.objects.filter(version=version, section_id__in=[OUT, WEEK]).update(is_complete=False)
    SyllabusVersion.objects.filter(pk=version.pk).update(completion_percent=75)

    call_command("recompute_syllabus_completion", "--apply", stdout=StringIO())

    version.refresh_from_db()
    assert version.completion_percent == 100
    assert version.sections.filter(section_id__in=[OUT, WEEK], is_complete=True).count() == 2
    again = StringIO()
    call_command("recompute_syllabus_completion", "--apply", stdout=again)
    assert "0 açıq versiya yeniləndi" in again.getvalue()
