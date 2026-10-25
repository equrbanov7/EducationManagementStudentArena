"""Delta köçürməsinin saf funksiyaları — DB-siz."""

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.legacy_import.services.delta.extract import build_bundle, parse_id_list
from apps.legacy_import.services.delta.lessons import mark_value, winning_cells
from apps.legacy_import.services.delta.people import _narrow, student_gender
from apps.legacy_import.services.delta.resolve import (
    group_key,
    group_key_variants,
    lesson_date,
    period_year,
    person_key,
    subject_key,
)
from apps.legacy_import.services.delta.syllabi import document_for


class KeyTests(SimpleTestCase):
    def test_group_keys_fold_case_dotless_i_and_separators(self):
        self.assertEqual(group_key("236 İT"), group_key("236 IT"))
        self.assertEqual(group_key("236İT ing"), group_key("236 İT ING"))
        self.assertEqual(group_key("3/336F1"), group_key("3/336 F1"))
        self.assertIn(group_key("236 BİO"), group_key_variants("236 BİO az"))
        self.assertNotEqual(group_key("536 TB1"), group_key("536 TB"))

    def test_subject_key_unescapes_entities(self):
        self.assertEqual(subject_key("Optimallaşdırma &uuml;sulları"), subject_key("Optimallaşdırma üsulları"))
        self.assertEqual(subject_key("Xarici dil  3"), subject_key("Xarici dil 3"))

    def test_person_key_and_period_year(self):
        self.assertEqual(person_key("Məmmədova"), person_key("Memmedova"))
        self.assertEqual(period_year("2026/2027 Payız"), "2026/2027")
        self.assertEqual(period_year("Yay"), "")

    def test_lesson_date_uses_semester_window(self):
        period = SimpleNamespace(start_date=dt.date(2026, 9, 15), end_date=dt.date(2027, 1, 31))
        self.assertEqual(lesson_date(period, 10, 6), dt.date(2026, 10, 6))
        self.assertEqual(lesson_date(period, 1, 12), dt.date(2027, 1, 12))
        self.assertIsNone(lesson_date(period, 6, 1))
        self.assertIsNone(lesson_date(period, 2, 30))

    def test_parse_id_list_is_fail_soft(self):
        self.assertEqual(parse_id_list('["1", 2, " 3 "]'), [1, 2, 3])
        self.assertEqual(parse_id_list("not json"), [])
        self.assertEqual(parse_id_list('{"a": 1}'), [])


class CellTests(SimpleTestCase):
    def test_mark_values(self):
        self.assertEqual(mark_value("ie"), ("present", None, "present"))
        self.assertEqual(mark_value("qb"), ("absent", None, "absent"))
        self.assertEqual(mark_value("10"), ("present", Decimal(10), "score"))
        self.assertEqual(mark_value("55")[2], "score_out_of_range")
        self.assertEqual(mark_value("")[2], "blank")
        self.assertEqual(mark_value("l")[2], "unknown_token")

    def test_winning_cell_prefers_counter_then_update_then_id(self):
        base = {"journal_uniqid": "u", "month_id": "10", "day_number": "06", "student_id": 1, "time": "09:00"}
        rows = [
            {**base, "id": 1, "point": "5", "update_counter": 2, "updated_at": None},
            {**base, "id": 2, "point": "7", "update_counter": 1, "updated_at": "2026-10-10"},
            {**base, "id": 3, "point": "9", "update_counter": 2, "updated_at": "2026-10-01"},
        ]
        self.assertEqual([row["id"] for row in winning_cells(rows)], [3])


class PeopleRuleTests(SimpleTestCase):
    def test_contradicting_patronymic_blocks_group_only_match(self):
        group = SimpleNamespace(pk="g")
        row = {"father_name": "Orxan", "birthday": ""}
        candidates = [(10, person_key("Elşən"), None), (11, "", None)]
        self.assertEqual(_narrow(candidates, row, group, {10: "g", 11: "g"}), [11])
        same_birth = {"father_name": "Orxan", "birthday": "2007-05-04"}
        self.assertEqual(_narrow([(12, person_key("Başqa"), dt.date(2007, 5, 4))], same_birth, None, {}), [12])

    def test_many_patronymic_matches_prefer_single_one_in_legacy_group(self):
        group = SimpleNamespace(pk="g")
        row = {"father_name": "Emin", "birthday": ""}
        candidates = [(20, person_key("EMİN QIZI"), None), (21, person_key("Emin"), None)]
        self.assertEqual(_narrow(candidates, row, group, {20: "g", 21: "other"}), [20])
        self.assertEqual(sorted(_narrow(candidates, row, None, {})), [20, 21])

    def test_gender_from_code_or_text(self):
        self.assertEqual(student_gender({"sex": 1, "gender": None}), "male")
        self.assertEqual(student_gender({"sex": 0, "gender": "Qadın"}), "female")
        self.assertEqual(student_gender({"sex": 0, "gender": ""}), "unspecified")


class SyllabusDocumentTests(SimpleTestCase):
    def test_document_unescapes_and_keeps_week_order(self):
        from apps.legacy_import.services.rehearsal_syllabus_targets import build_section_data

        row = {
            "id": 5,
            "uniqid": "s5",
            "lesson_id": 1,
            "teacher_id": 2,
            "ders_saati": 30,
            "language": "az",
            "active": 1,
            "week": [
                {
                    "id": 2,
                    "uniqid": "s5",
                    "movzu": "Giri&ccedil;",
                    "muh_saat": "2",
                    "sem_saat": "",
                    "praktiki_saat": "",
                    "lab_saat": "",
                    "qeyd": "",
                },
                {
                    "id": 3,
                    "uniqid": "s5",
                    "movzu": "",
                    "muh_saat": "0.5",
                    "sem_saat": "2",
                    "praktiki_saat": "",
                    "lab_saat": "",
                    "qeyd": "",
                },
            ],
            "sections": {"sillabus_derslikler": [[1, "Kitab 1\r\nKitab 2"]]},
        }
        data, _codes = build_section_data(document_for(row))
        weeks = data["week"]["rows"]
        self.assertEqual(weeks[0]["topic"], "Giriç")
        self.assertEqual(len(weeks), 2)


class BuildBundleTests(SimpleTestCase):
    def test_orchestration_collects_referenced_rows(self):
        calls = []

        class FakeExtractor:
            src = "`src`"

            def resolve_full_semesters(self):
                return [14]

            def journals(self):
                return [
                    {
                        "id": 1,
                        "uniqid": "u1",
                        "students_id": '["7"]',
                        "groups_id": '["3"]',
                        "teacher_id": 9,
                        "lesson_id": 4,
                        "sillabus_id": 0,
                    }
                ]

            def lesson_dates(self, ids):
                return []

            def lesson_topics(self, ids):
                calls.append(("lesson_topics", set(ids)))
                return []

            def points(self, uniqids):
                return [{"student_id": 8, "journal_uniqid": "old"}]

            def students(self, referenced):
                calls.append(("students", set(referenced)))
                return [{"id": 7, "group_id": 3, "speciality_id": 1}]

            def syllabi(self, ids):
                return []

            def expelled_students(self, exclude):
                calls.append(("expelled_students", set(exclude)))
                return []

            def _new_or_changed(self, table, columns):
                return set(), set()

            def _by_ids(self, table, columns, ids):
                calls.append((table, set(ids)))
                return []

            def _rows(self, sql, params=()):
                return []

            def excuse_windows(self, ids, since):
                return []

        bundle = build_bundle(FakeExtractor(), snapshot={}, since="2026-08-01")
        self.assertEqual(bundle["snapshot"]["full_semesters"], [14])
        self.assertIn(("students", {7, 8}), calls)
        self.assertIn(("workers", {9}), calls)
        self.assertIn(("groups", {3}), calls)
        self.assertIn(("expelled_students", {7}), calls)


class WorkloadChairTests(SimpleTestCase):
    def test_inactive_chair_is_never_chosen(self):
        from apps.legacy_import.services.delta.workload import _chair_for, _scaled

        inactive = SimpleNamespace(unit_type="chair", is_active=False)
        active = SimpleNamespace(unit_type="chair", is_active=True)
        offering = SimpleNamespace(subject=SimpleNamespace(chair_unit_id=1, chair_unit=inactive), instructor_id=7)
        self.assertIsNone(_chair_for(offering, {7: inactive}))
        self.assertIs(_chair_for(offering, {7: active}), active)
        self.assertEqual(_scaled({"lecture": 2, "seminar": 2}, 45), {"lecture": 23, "seminar": 22})


class FatherNameTests(SimpleTestCase):
    def test_suffix_and_short_names_match_and_other_names_do_not(self):
        from apps.legacy_import.services.delta.people import same_father
        from apps.legacy_import.services.delta.resolve import person_key as key

        self.assertTrue(same_father(key("ŞAİQ"), key("ŞAİQ QIZI")))
        self.assertTrue(same_father(key("Əli"), key("ƏLİ QIZI")))
        self.assertTrue(same_father(key("HƏBİB"), key("Həbib oğlu")))
        self.assertFalse(same_father(key("Mahir"), key("Müşviq")))
        self.assertFalse(same_father(key("Azər"), key("Emin")))
        self.assertFalse(same_father("", key("Emin")))

    def test_pick_lesson_prefers_exact_time_then_single_lesson(self):
        from apps.legacy_import.services.delta.topics import pick_lesson

        nine, ten = dt.time(9, 0), dt.time(10, 30)
        self.assertEqual(pick_lesson([(1, nine, ""), (2, ten, "")], ten)[0], 2)
        self.assertEqual(pick_lesson([(1, nine, "")], ten)[0], 1)
        self.assertIsNone(pick_lesson([(1, nine, ""), (2, dt.time(13, 0), "")], ten))
        self.assertIsNone(pick_lesson([], ten))
