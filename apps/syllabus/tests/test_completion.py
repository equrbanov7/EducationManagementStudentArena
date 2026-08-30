"""Tamamlanma qaydası — DB-siz vahid testlər.

Əsas iddia: faiz DOLDURULMUŞ INPUT SAYINA görə DEYİL, biznes qaydasına görədir.
"""

from __future__ import annotations

import copy

from apps.syllabus import completion
from apps.syllabus.constants import RULE_SECTIONS, SectionKey
from apps.syllabus.tests.factories import PLAN_HOURS, complete_section_data


def test_complete_data_is_100_percent():
    report = completion.evaluate(complete_section_data(), PLAN_HOURS)
    assert report.percent == 100, report.as_dict()["issues"]
    assert report.is_complete
    assert set(report.sections) == set(RULE_SECTIONS)


def test_empty_data_is_zero_except_policy_locked_assess():
    report = completion.evaluate({}, PLAN_HOURS)
    # `assess` çəkiləri siyasətlə kilidlidir → həmişə ödənilmiş sayılır.
    assert report.sections[SectionKey.ASSESS.value] is True
    assert report.percent == round(1 / len(RULE_SECTIONS) * 100)


def test_partially_filled_section_does_not_count_as_partially_complete():
    """«8 sahədən 5-i doldurulub» faizi YOXDUR — qayda ya ödənilir, ya yox."""
    data = complete_section_data()
    data[SectionKey.LIT.value]["primary"] = ["Yalnız bir mənbə göstərilib 2020"]
    report = completion.evaluate(data, PLAN_HOURS)
    assert report.sections[SectionKey.LIT.value] is False
    assert report.percent == round(7 / 8 * 100)
    codes = {issue.code for issue in report.issues}
    assert "lit.primary_too_few" in codes


def test_week_hours_must_match_the_study_plan():
    data = complete_section_data()
    data[SectionKey.WEEK.value]["rows"][0]["lecture"] += 1
    report = completion.evaluate(data, PLAN_HOURS)
    assert report.sections[SectionKey.WEEK.value] is False
    mismatch = [issue for issue in report.issues if issue.code == "week.hours_mismatch"]
    assert mismatch and mismatch[0].params["kind"] == "lecture"


def test_orphan_learning_outcome_blocks_the_outcomes_section():
    data = complete_section_data()
    data[SectionKey.OUT.value]["outcomes"].append("Dördüncü nəticə heç bir həftədə yoxdur")
    report = completion.evaluate(data, PLAN_HOURS)
    assert report.sections[SectionKey.OUT.value] is False
    assert any(issue.code == "out.orphan_outcomes" for issue in report.issues)


def test_ghost_week_row_hours_without_topic_is_rejected():
    data = complete_section_data()
    data[SectionKey.WEEK.value]["rows"][-1]["lecture"] = 2
    report = completion.evaluate(data, PLAN_HOURS)
    assert report.sections[SectionKey.WEEK.value] is False
    assert any(issue.code == "week.hours_without_topic" for issue in report.issues)


def test_disallowed_selfwork_option_is_not_complete():
    data = complete_section_data()
    data[SectionKey.SELF.value] = {"option": "3x5", "topics": [{"title": "Uzun mövzu adı"}] * 3}
    report = completion.evaluate(data, PLAN_HOURS)
    assert report.sections[SectionKey.SELF.value] is False
    assert any(issue.code == "self.option_not_allowed" for issue in report.issues)


def test_selfwork_topic_count_must_match_the_option():
    data = complete_section_data()
    data[SectionKey.SELF.value]["topics"] = [{"title": "Yalnız bir mövzu var"}]
    report = completion.evaluate(data, PLAN_HOURS)
    assert report.sections[SectionKey.SELF.value] is False
    issue = next(i for i in report.issues if i.code == "self.topic_count_mismatch")
    assert issue.params == {"need": 2, "have": 1}


def test_short_description_is_reported_with_measurements():
    data = complete_section_data()
    data[SectionKey.DESC.value]["description"] = "qısa"
    report = completion.evaluate(data, PLAN_HOURS)
    issue = next(i for i in report.issues if i.code == "desc.description_too_short")
    assert issue.params["min"] == 120
    assert issue.params["have"] == len("qısa")


def test_report_is_json_serializable():
    import json

    report = completion.evaluate(complete_section_data(), PLAN_HOURS)
    assert json.loads(json.dumps(report.as_dict()))["percent"] == 100


def test_evaluation_does_not_mutate_input():
    data = complete_section_data()
    snapshot = copy.deepcopy(data)
    completion.evaluate(data, PLAN_HOURS)
    assert data == snapshot
