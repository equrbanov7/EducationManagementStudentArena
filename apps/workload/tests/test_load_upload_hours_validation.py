"""Public Excel parser rejects observed date coercion and ignores technical headers."""

import io
from datetime import date, datetime, time, timedelta

from django.test import SimpleTestCase

from openpyxl import Workbook

from apps.workload.services.load_upload_parsing import TEMPLATE_HEADERS, LoadFileError, parse_workbook


def workbook_bytes(rows):
    book = Workbook()
    sheet = book.active
    sheet.title = "Dərs yükü"
    sheet.append(TEMPLATE_HEADERS)
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def course_row(**hours):
    row = ["Həsənova Səkinə Ramiz", "235 EKO", "Cəmiyyət fəlsəfəsi", 5, 20, ""] + [None] * 6
    for column, value in hours.items():
        row[int(column)] = value
    return row


class LoadHoursValidationTests(SimpleTestCase):
    def test_observed_typed_date_in_any_hours_column_fails_with_source_line(self):
        # Actual Psixologiya H7 cell was an Excel date, not 2026 contact hours.
        for column in range(6, 12):
            with self.subTest(column=column):
                row = course_row(**{str(column): datetime(2026, 5, 5)})
                with self.assertRaises(LoadFileError) as caught:
                    parse_workbook(io.BytesIO(workbook_bytes([row])))
                self.assertEqual(caught.exception.code, "invalid_hours")
                self.assertEqual(caught.exception.line, 2)
                self.assertIn("2", caught.exception.message)

    def test_date_time_and_duration_types_are_not_interpreted_as_hour_numbers(self):
        for value in (date(2026, 5, 5), time(5, 5), timedelta(hours=5)):
            with self.subTest(value=value):
                with self.assertRaises(LoadFileError) as caught:
                    parse_workbook(io.BytesIO(workbook_bytes([course_row(**{"7": value})])))
                self.assertEqual(caught.exception.code, "invalid_hours")

    def test_date_looking_strings_and_malformed_dates_fail_closed(self):
        for value in (
            "2026-05-05 00:00:00",
            "05/05/2026",
            "05/05/26",
            "2026/5/5",
            "32.14.2026",
            "05:05",
            "5:5",
            "03:30:00",
        ):
            with self.subTest(value=value):
                with self.assertRaises(LoadFileError) as caught:
                    parse_workbook(io.BytesIO(workbook_bytes([course_row(**{"7": value})])))
                self.assertEqual((caught.exception.code, caught.exception.line), ("invalid_hours", 2))

    def test_observed_design_column_labels_produce_no_fake_teacher_or_subject(self):
        technical = [f"Column{index}" for index in range(1, 13)]
        entries, skipped = parse_workbook(io.BytesIO(workbook_bytes([technical])))
        self.assertEqual(entries, [])
        self.assertEqual(skipped, [{"line": 2, "reason": "technical_header", "subject": ""}])

    def test_skipped_technical_header_does_not_replace_carried_teacher(self):
        first = course_row(**{"6": 30})
        second = course_row(**{"9": 45})
        second[0] = ""
        technical = [f"Column{index}" for index in range(1, 13)]
        entries, skipped = parse_workbook(io.BytesIO(workbook_bytes([first, technical, second])))
        self.assertEqual(len(entries), 2)
        self.assertEqual([entry.teacher_text for entry in entries], [first[0], first[0]])
        self.assertEqual([entry.subject_text for entry in entries], [first[2], first[2]])
        self.assertEqual(skipped[0]["line"], 3)

    def test_valid_arithmetic_and_normal_year_metadata_keep_existing_meaning(self):
        row = course_row(**{"6": "30x3", "7": "2*45", "8": "9+8", "9": 30.0, "10": "15", "11": "-"})
        row[3], row[4] = "2026", 2027
        entries, skipped = parse_workbook(io.BytesIO(workbook_bytes([row])))
        self.assertEqual(skipped, [])
        self.assertEqual(entries[0].hours, {"lecture": 90, "seminar": 90, "lab": 17})
        self.assertEqual(entries[1].hours, {"lecture": 30, "seminar": 15})
        self.assertEqual((entries[0].credits, entries[0].students), ("2026", "2027"))

    def test_date_metadata_outside_hour_columns_is_not_rejected(self):
        row = course_row(**{"6": 30})
        row[3] = date(2026, 5, 5)
        entries, skipped = parse_workbook(io.BytesIO(workbook_bytes([row])))
        self.assertEqual(skipped, [])
        self.assertEqual(entries[0].hours, {"lecture": 30})
