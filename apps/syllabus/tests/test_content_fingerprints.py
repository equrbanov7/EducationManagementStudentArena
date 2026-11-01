"""Fingerprint equality is evidence only; counts cannot substitute for authored content."""

import copy

from django.test import SimpleTestCase

from apps.syllabus.content_fingerprints import content_fingerprints, digest, leaf_counts, typed_hours


class ContentFingerprintTests(SimpleTestCase):
    def source(self):
        return {
            "info": {"teacher": "PRIVATE_PHONE_NAME", "language": "az"},
            "desc": {"description": "Real authored source α + β", "goal": ""},
            "week": {"rows": [{"topic": "Meaningful topic", "lecture": 2, "seminar": 0, "lab": 0, "outcome": "TN1"}]},
        }

    def test_same_counts_different_authored_text_have_different_hashes(self):
        first = self.source()
        second = copy.deepcopy(first)
        second["week"]["rows"][0]["topic"] = "Current meaningful replacement"
        a, b = content_fingerprints(first), content_fingerprints(second)
        self.assertEqual(a["topic_summary"]["hours_by_kind"], b["topic_summary"]["hours_by_kind"])
        self.assertEqual(a["topic_summary"]["row_count"], b["topic_summary"]["row_count"])
        self.assertNotEqual(a["canonical_body_sha256"], b["canonical_body_sha256"])
        self.assertNotIn("Meaningful topic", str(a))
        self.assertNotIn("PRIVATE_PHONE_NAME", str(a))

    def test_contact_only_difference_and_current_addition_are_preserved(self):
        first = self.source()
        second = copy.deepcopy(first)
        second["info"]["teacher"] = "Other private contact"
        a, b = content_fingerprints(first), content_fingerprints(second)
        self.assertNotEqual(a["canonical_body_sha256"], b["canonical_body_sha256"])
        self.assertEqual(a["course_body_sha256"], b["course_body_sha256"])
        second["desc"]["goal"] = "Current teacher addition, do not overwrite"
        self.assertNotEqual(a["course_body_sha256"], content_fingerprints(second)["course_body_sha256"])

    def test_boolean_hours_are_not_one_and_blank_topics_are_visible(self):
        data = self.source()
        data["week"]["rows"][0].update(topic="", lecture=True, lab="2")
        result = content_fingerprints(data)
        self.assertFalse(result["topic_summary"]["totals_complete"])
        self.assertEqual(result["topic_summary"]["hours_without_topic_count"], 1)
        self.assertEqual(result["topic_summary"]["numeric_string_count"], 1)
        self.assertIsNone(result["topics"][0]["hours"]["lecture"])
        self.assertFalse(typed_hours({"phone_unknown": "PRIVATE"})["valid"])

    def test_unknown_sections_and_keys_are_hash_only_and_empty_counts_distinct(self):
        result = content_fingerprints(
            {
                "PRIVATE_KEY_SENTINEL": {"PRIVATE_NESTED_KEY": "PRIVATE_VALUE"},
                "desc": {"description": "", "extra": [], "goal": None},
            }
        )
        self.assertEqual(result["unknown_section_count"], 1)
        self.assertNotIn("PRIVATE", str(result))
        self.assertEqual(leaf_counts({"x": "", "y": [], "z": None})["blank_string_leaves"], 1)
        self.assertNotEqual(digest({"x": ""}), digest({"x": None}))

    def test_topic_order_and_math_symbols_remain_significant(self):
        data = self.source()
        data["week"]["rows"].append({"topic": "α≠a", "lecture": 0, "seminar": 2})
        a = content_fingerprints(data)
        data["week"]["rows"].reverse()
        b = content_fingerprints(data)
        self.assertNotEqual(a["canonical_body_sha256"], b["canonical_body_sha256"])
        self.assertEqual(a["topic_summary"]["row_multiset_sha256"], b["topic_summary"]["row_multiset_sha256"])

    def test_deep_json_fails_closed_before_unbounded_recursion(self):
        value = "PRIVATE"
        for _ in range(40):
            value = [value]
        with self.assertRaisesRegex(ValueError, "shape_budget"):
            content_fingerprints({"desc": value})
