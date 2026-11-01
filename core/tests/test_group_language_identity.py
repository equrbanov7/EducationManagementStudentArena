"""Group names supply counterevidence only; no language is inferred or repaired."""

import copy
from types import SimpleNamespace

from core.group_language_identity import evidence, group_language_issues


def group(pk, name, settings):
    return SimpleNamespace(pk=pk, name=name, settings=settings)


def test_explicit_english_tag_cannot_hide_behind_az_settings():
    for name in ("234 İT ing", "235İTing", "233KEing", "235 İT ENG"):
        result = evidence(name, {"sector": "az"})
        assert result["structured"] == "az"
        assert result["explicit_name_tag"] == "en"
        assert "structured_language_name_conflict" in result["reasons"]


def test_missing_structured_language_not_supplied_by_name():
    rows = [group(1, "235 İT-1 az", {"sector": "az"}), group(2, "235 İT-2 az", {})]
    before = copy.deepcopy(rows)
    assert ("2", "structured_language_missing") in group_language_issues(rows, require_structured=True)
    assert rows == before
    rows[0].settings = {}
    assert len(group_language_issues(rows, require_structured=True)) == 2


def test_same_structured_aliases_and_explicit_labels_agree():
    rows = [
        group(1, "235 İT-1 az", {"sector": "az", "language_sector": "AZ"}),
        group(2, "235 İT-2 az", {"language_sector": "azərbaycan dili"}),
    ]
    assert not group_language_issues(rows, require_structured=True)


def test_internal_language_keys_and_cross_group_labels_cannot_disagree():
    assert evidence("235 İT-1", {"sector": "az", "language_sector": "en"})["reasons"]
    assert group_language_issues([group(1, "235 İT az", {}), group(2, "235 İT ing", {})])
    assert evidence("235 İT", {"sector": 0})["reasons"]


def test_arbitrary_subject_words_not_language_suffix_matching():
    assert evidence("235 Marketing", {})["explicit_name_tag"] == ""
    assert evidence("235 beginning", {})["explicit_name_tag"] == ""
    assert evidence("235 İT ingilis müəllimi", {})["explicit_name_tag"] == ""


def test_unknown_metadata_does_not_enable_new_zero_plan_fallback():
    rows = [group(1, "235 IT-1", {"sector": "unknown"}), group(2, "235 IT-2", {"sector": "unknown"})]
    assert ("1", "structured_language_unknown") in group_language_issues(rows, require_structured=True)
