"""Həftəlik cədvəlin PLAN SAATINDAN özü tənzimlənməsi (sahib 2026-09-21).

Qayda: bir dərs = 2 saat; saat seçimi «—»/1/2; sətir sayı ``ceil(saat / 2)``
(15/15 → 8); planda saatı olmayan növün sütunu görünmür; təzə qaralamada
bölgü 2-2-…-qalıq düzülür; müəllim «+» ilə sətir artıra bilər.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase

import pytest

from apps.syllabus import services
from apps.syllabus.completion import evaluate
from apps.syllabus.constants import MIN_FILLED_WEEKS, WEEK_ROWS, SectionKey
from apps.syllabus.tests.editor_dom import render_editor_dom
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org
from apps.syllabus.week_plan import (
    default_distribution,
    expected_week_rows,
    hour_choices,
    seed_missing_hours,
    visible_hour_kinds,
)

User = get_user_model()
PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]


class WeekPlanRulesTest(SimpleTestCase):
    def test_rows_follow_the_largest_kind_at_two_hours_per_lesson(self):
        self.assertEqual(expected_week_rows({"lecture": 15, "seminar": 15}), 8)
        self.assertEqual(expected_week_rows({"lecture": 30, "seminar": 15}), 15)
        self.assertEqual(expected_week_rows({"lecture": 30, "seminar": 16, "lab": 14}), 15)
        self.assertEqual(expected_week_rows({}), 0)
        self.assertEqual(expected_week_rows(None), 0)

    def test_hour_choices_stop_at_two(self):
        self.assertEqual(hour_choices(), (0, 1, 2))

    def test_default_distribution_is_two_two_remainder(self):
        self.assertEqual(default_distribution(15), [2] * 7 + [1])
        self.assertEqual(default_distribution(30), [2] * 15)
        self.assertEqual(default_distribution(0), [])

    def test_a_kind_without_plan_hours_is_hidden_unless_a_row_uses_it(self):
        self.assertEqual(visible_hour_kinds({"lecture": 15, "seminar": 15}), ("lecture", "seminar"))
        rows = [{"lecture": 2, "seminar": 0, "lab": 2}]
        self.assertEqual(visible_hour_kinds({"lecture": 15, "seminar": 15}, rows), ("lecture", "seminar", "lab"))
        self.assertEqual(visible_hour_kinds({}), ("lecture", "seminar", "lab"))

    def test_seeding_fills_only_kinds_whose_total_is_zero(self):
        rows = [{"topic": "A", "lecture": 0, "seminar": 3, "lab": 0, "outcome": "", "practical": 2}]
        seeded, changed = seed_missing_hours(rows, {"lecture": 5, "seminar": 15})
        self.assertTrue(changed)
        self.assertEqual([row["lecture"] for row in seeded], [2, 2, 1])
        # Müəllimin yazdığı seminar bölgüsünə toxunulmur, digər açarlar qalır.
        self.assertEqual(seeded[0]["seminar"], 3)
        self.assertEqual(seeded[0]["practical"], 2)
        self.assertEqual(seeded[0]["topic"], "A")
        _again, changed_again = seed_missing_hours(seeded, {"lecture": 5, "seminar": 15})
        self.assertFalse(changed_again)

    def test_completion_minimum_follows_the_plan(self):
        rows = [
            {"topic": f"Mövzu {i + 1}", "outcome": "TN1", "lecture": 2 if i < 7 else 1, "seminar": 0, "lab": 0}
            for i in range(8)
        ]
        data = {
            "desc": {"description": "x" * 130, "goal": "y" * 70},
            "out": {"outcomes": ["Nəticə bir mətn", "Nəticə iki mətn", "Nəticə üç mətn"]},
            "week": {"rows": rows},
        }
        codes = [issue.code for issue in evaluate(data, {"lecture": 15}).issues if issue.section == "week"]
        self.assertNotIn("week.too_few_topics", codes)
        # Plan yoxdursa köhnə sabit minimum (14) qalır.
        codes = [issue.code for issue in evaluate(data, {}).issues if issue.section == "week"]
        self.assertIn("week.too_few_topics", codes)
        self.assertLess(len(rows), MIN_FILLED_WEEKS)


@pytest.fixture
def world():
    org = make_org("weekplan-org")
    teacher = User.objects.create_user("weekplan_teacher", "weekplan@x.test", "pw")
    stack = make_academic_stack(org, code="WP101")
    activate_member(org, teacher, "teacher", permissions=PERMS)
    offering = make_offering(org, stack, teacher)
    return {"org": org, "teacher": teacher, "stack": stack, "offering": offering}


def _fresh_draft(world, plan_hours):
    actor = services.resolve_actor(world["teacher"], world["org"])
    syllabus, version = services.create_draft(
        organization=world["org"],
        subject=world["stack"]["subject"],
        period=world["stack"]["period"],
        program=world["stack"]["program"],
        chair_unit=world["stack"]["chair"],
        author=world["teacher"],
        actor=actor,
        plan_hours=plan_hours,
    )
    return actor, version


@pytest.mark.django_db
def test_a_fresh_draft_renders_plan_rows_with_seeded_hours_and_no_lab_column(world):
    _actor, version = _fresh_draft(world, {"lecture": 15, "seminar": 15})
    root, se = render_editor_dom(
        user=world["teacher"], organization=world["org"], version=version, step=SectionKey.WEEK.value
    )
    # 15/15 → 8 sətir (7×2 + 1), lab sütunu/çipi yoxdur.
    assert len(se["week_rows"]) == 8
    assert se["limits"]["weeks"] == 8
    assert [row["lecture"] for row in se["week_rows"]] == [2] * 7 + [1]
    assert [row["seminar"] for row in se["week_rows"]] == [2] * 7 + [1]
    assert se["hours"]["kinds"] == ("lecture", "seminar")
    assert [chip["kind"] for chip in se["hours"]["rows"]] == ["lecture", "seminar"]
    assert se["hours"]["ok"]
    assert not root.xpath("//*[@data-syl-week-row]//select[@data-week='lab']")
    # Seçim siyahısı 2-də dayanır.
    values = {opt.get("value") for opt in root.xpath("//*[@data-syl-week-row]//select[@data-week='lecture']/option")}
    assert values == {"0", "1", "2"}
    # «+» düyməsi və şablon sətri var; şablon sətri toplayıcı üçün görünməzdir.
    assert root.xpath("//button[@data-syl-week-add]")
    assert root.xpath("//template[@data-syl-week-template]//tr[@data-syl-week-row-template]")
    assert len(root.xpath("//tr[@data-syl-week-row]")) == 8
    # Bölgü BAZAYA yazılıb (çip, çatışmazlıq siyahısı və DOM eyni şeyi deyir).
    stored = services.section_data_map(version)[SectionKey.WEEK.value]["rows"]
    assert sum(row["lecture"] for row in stored) == 15


@pytest.mark.django_db
def test_without_a_plan_the_table_keeps_sixteen_rows_and_three_columns(world):
    _actor, version = _fresh_draft(world, {})
    root, se = render_editor_dom(
        user=world["teacher"], organization=world["org"], version=version, step=SectionKey.WEEK.value
    )
    assert len(se["week_rows"]) == WEEK_ROWS
    assert se["hours"]["kinds"] == ("lecture", "seminar", "lab")
    assert root.xpath("//*[@data-syl-week-row]//select[@data-week='lab']")


@pytest.mark.django_db
def test_a_migrated_lab_value_keeps_the_lab_column_visible(world):
    actor, version = _fresh_draft(world, {"lecture": 15, "seminar": 15})
    rows = [{"topic": "Köhnə", "lecture": 2, "seminar": 2, "lab": 4, "outcome": ""}]
    services.save_section(version=version, section_id=SectionKey.WEEK.value, data={"rows": rows}, actor=actor)
    root, se = render_editor_dom(
        user=world["teacher"], organization=world["org"], version=version, step=SectionKey.WEEK.value
    )
    assert se["hours"]["kinds"] == ("lecture", "seminar", "lab")
    # 4 saat siyahıda olmasa da seçili qalır (autosave 0 yazmasın).
    assert root.xpath("//tr[@data-syl-week-row='1']//select[@data-week='lab']/option[@value='4'][@selected]")
