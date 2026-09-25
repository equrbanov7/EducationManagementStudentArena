"""Köhnə kodun sabit nəticələri və yeni standartın bütün oxu yollarında pariteti."""

from __future__ import annotations

import json
from pathlib import Path

from django.db import connection
from django.test import TestCase

from apps.registrar.tests.entry_standard_fixture import EntryStandardFixture
from apps.registrar.tests.entry_standard_probe import MirrorProbe

BASELINE = json.loads(Path(__file__).with_name("entry_standard_baseline.json").read_text())
# M1/s0: 9.33 + 8.50 + 17 + 9 = 43.83 → 44.
# M1/s1: qayıb həddi keçilib, təkrar imtahan davamiyyət balını artırmır.
# M1/s3: idmançı istisnası, 7.33 + 6.50 + min(18+3,20) + 2.50 = 36.33 → 36.
EXPECTED_NEW = {"M1": (44, 40, 18, 36), "M2": (35, 10, 22, 10)}
ENTRY_SURFACES = (
    "entry_single",
    "entry_batch",
    "final_breakdown",
    "journal_grid",
    "dashboard",
    "schedule_stats",
    "student_journal_detail",
    "student_journal_summary",
    "student_subjects_journal",
)
FINAL_SURFACES = ("final_single", "final_batch", "offering_results", "student_subjects_final", "transcript")


class EntryStandardParityTest(EntryStandardFixture, TestCase):
    def test_all_mirrors_and_query_budgets(self):
        probe = MirrorProbe(self)
        numbers = json.loads(json.dumps(probe.collect()))
        for surface, rows in BASELINE["numbers"].items():
            for key, value in rows.items():
                if key.startswith(("K1/", "K2/")) or key == "old":
                    with self.subTest(legacy_surface=surface, row=key):
                        self.assertEqual(numbers[surface][key], value)
        for offering, entries in EXPECTED_NEW.items():
            for index, entry in enumerate(entries):
                key = f"{offering}/esd_s{index}"
                for surface in ENTRY_SURFACES:
                    with self.subTest(surface=surface, row=key):
                        self.assertEqual(numbers[surface][key], str(entry))
                result = numbers["final_single"][key]
                self.assertEqual(result[0], str(entry))
                for surface in FINAL_SURFACES:
                    self.assertEqual(numbers[surface][key], result, (surface, key))
                self.assertEqual(numbers["analytics_eval"][key], result[1:])
                self.assertEqual(numbers["analytics_eval_for"][key], result[1:3])
                self.assertEqual(numbers["exam_result_summary"][key], result[:2])
        # İki sürətli aqreqatorun ÜOMG-si eyni nəticələrdən çıxmalıdır.
        self.assertEqual(numbers["period_analytics"]["new"][4], "64.33")  # (74+65+54)/3
        if connection.vendor == "postgresql":
            for surface, count in probe.queries.items():
                with self.subTest(query_budget=surface):
                    self.assertLessEqual(count, BASELINE["queries"][surface])
