"""Bölmə autosave gövdəsinin forma yoxlaması — QA 2026-09-05 SYLLABUS-02/03 reqressiya qapısı.

Əvvəl ``week.rows`` içində ``1`` / ``null`` / ``{"topic": {"a": 1}}`` yazılır və redaktor
paneli ``AttributeError`` ilə 500 verirdi; 3 MB mətn də qəbul olunurdu.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.syllabus.constants import MAX_LIST_ITEMS, MAX_TEXT_CHARS, MAX_WEEK_ROWS
from apps.syllabus.services.section_shape import SectionShapeError, normalize_section_data


class WeekRowsShapeTest(SimpleTestCase):
    def test_null_row_becomes_empty_and_strings_are_kept(self):
        data = normalize_section_data("week", {"rows": [None, {"topic": " Giriş ", "outcome": None, "lecture": "2"}]})
        self.assertEqual(data["rows"][0], {})
        self.assertEqual(data["rows"][1]["topic"], " Giriş ")
        self.assertEqual(data["rows"][1]["outcome"], "")
        self.assertEqual(data["rows"][1]["lecture"], 2)

    def test_scalar_row_is_rejected(self):
        with self.assertRaises(SectionShapeError) as ctx:
            normalize_section_data("week", {"rows": [1]})
        self.assertEqual(ctx.exception.code, "section.invalid_shape")
        self.assertEqual(ctx.exception.field, "rows[0]")

    def test_nested_object_in_topic_is_rejected(self):
        with self.assertRaises(SectionShapeError) as ctx:
            normalize_section_data("week", {"rows": [{"topic": {"a": 1}}]})
        self.assertEqual(ctx.exception.field, "rows[0].topic")

    def test_rows_must_be_a_list(self):
        with self.assertRaises(SectionShapeError):
            normalize_section_data("week", {"rows": {"0": {"topic": "x"}}})

    def test_too_many_rows_rejected(self):
        with self.assertRaises(SectionShapeError) as ctx:
            normalize_section_data("week", {"rows": [{"topic": "x"}] * (MAX_WEEK_ROWS + 1)})
        self.assertEqual(ctx.exception.code, "section.too_long")

    def test_non_numeric_hours_rejected(self):
        with self.assertRaises(SectionShapeError):
            normalize_section_data("week", {"rows": [{"lecture": "iki"}]})


class TextAndListShapeTest(SimpleTestCase):
    def test_description_over_limit_rejected(self):
        with self.assertRaises(SectionShapeError) as ctx:
            normalize_section_data("desc", {"description": "B" * (MAX_TEXT_CHARS + 1)})
        self.assertEqual(ctx.exception.code, "section.too_long")
        self.assertEqual(ctx.exception.params["max"], MAX_TEXT_CHARS)

    def test_outcomes_string_is_wrapped_and_objects_rejected(self):
        self.assertEqual(normalize_section_data("out", {"outcomes": "tək"})["outcomes"], ["tək"])
        with self.assertRaises(SectionShapeError):
            normalize_section_data("out", {"outcomes": [{"x": 1}]})
        with self.assertRaises(SectionShapeError):
            normalize_section_data("out", {"outcomes": ["a"] * (MAX_LIST_ITEMS + 1)})

    def test_generic_section_keeps_valid_json_and_rejects_deep_nesting(self):
        ok = normalize_section_data("info", {"welcome": "salam", "flags": {"a": [1, 2]}, "n": 3, "b": True})
        self.assertEqual(ok["flags"], {"a": [1, 2]})
        with self.assertRaises(SectionShapeError):
            normalize_section_data("info", {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": 1}}}}}}}}})

    def test_non_dict_payload_rejected(self):
        with self.assertRaises(SectionShapeError):
            normalize_section_data("desc", ["x"])
