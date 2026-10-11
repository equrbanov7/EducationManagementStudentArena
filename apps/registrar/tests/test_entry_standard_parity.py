"""Köhnə kodun sabit nəticələri və yeni standartın bütün oxu yollarında pariteti.

Sahib 2026-10-10 («Yeni qayda var»): sərbəst iş ləğv (defolt), midterm 30, seminar + lab olan fəndə aktivlik
5 + 5.  ``EntryStandardParityTest`` yeni qaydanı, ``EntryStandardOldRuleParityTest`` isə RİM-də köhnə qaydaya
qayıdışı (sərbəst iş açıq, birgə orta) EYNİ fiksturada kilidləyir — keçmiş (kollokvium) dövrlərin rəqəmləri
hər iki halda baseline ilə bayt-bayt eynidir."""

from __future__ import annotations

import json
from pathlib import Path

from django.db import connection
from django.test import TestCase, override_settings

from apps.registrar.tests.entry_standard_fixture import EntryStandardFixture
from apps.registrar.tests.entry_standard_probe import MirrorProbe

BASELINE = json.loads(Path(__file__).with_name("entry_standard_baseline.json").read_text())
# YENİ QAYDA (M1 — 3 seminar + 1 lab: aktivlik 5 + 5; sərbəst iş sayılmır; midterm ≤ 30):
# M1/s0: 9.33 + (round2(8.33/2)=4.17 + 9/2=4.50) + 17 = 35.00 → 35.
# M1/s1: buraxılmır → 0 + (0 + 10/2) + 20 = 25 (lab balı var, seminar balı yox → seminar payı 0).
# M1/s2: 10 + 7.5/2 + 0 = 13.75 → 14 (lab balı hələ yoxdur → lab payı 0).
# M1/s3: idmançı, 7.33 + 6.5/2 + min(18 + 3, 30) = 31.58 → 32.
# M2: dərs yoxdur; sərbəst iş sayılmır → s0: 10 + 20 = 30 (tavan 35 işə düşmür).
EXPECTED_NEW = {"M1": (35, 25, 14, 32), "M2": (30, 10, 22, 10)}
# KÖHNƏ QAYDA (2026-09-25; RİM-də sərbəst iş açıq + birgə orta) — keçiddən əvvəlki rəqəmlər:
# M1/s0: 9.33 + 8.50 + 17 + 9 = 43.83 → 44.
# M1/s1: qayıb həddi keçilib, təkrar imtahan davamiyyət balını artırmır.
# M1/s3: idmançı istisnası, 7.33 + 6.50 + min(18+3,20) + 2.50 = 36.33 → 36.
EXPECTED_OLD_RULE = {"M1": (44, 40, 18, 36), "M2": (35, 10, 22, 10)}
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


class _ParityChecks:
    expected: dict = {}
    #: Yeni dövrün orta yekunu (``period_analytics`` və ``academic_summary`` eyni nəticələrdən).
    new_avg_total = ""

    def test_all_mirrors_and_query_budgets(self):
        probe = MirrorProbe(self)
        numbers = json.loads(json.dumps(probe.collect()))
        for surface, rows in BASELINE["numbers"].items():
            for key, value in rows.items():
                if key.startswith(("K1/", "K2/")) or key == "old":
                    with self.subTest(legacy_surface=surface, row=key):
                        self.assertEqual(numbers[surface][key], value)
        for offering, entries in self.expected.items():
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
        self.assertEqual(numbers["period_analytics"]["new"][4], self.new_avg_total)
        if connection.vendor == "postgresql":
            for surface, count in probe.queries.items():
                with self.subTest(query_budget=surface):
                    self.assertLessEqual(count, BASELINE["queries"][surface])


class EntryStandardParityTest(_ParityChecks, EntryStandardFixture, TestCase):
    expected = EXPECTED_NEW
    new_avg_total = "55.00"  # (65 + 50 + 50) / 3


@override_settings(ACADEMIC_SELFWORK_ENABLED=True, ACADEMIC_ACTIVITY_SPLIT=False)
class EntryStandardOldRuleParityTest(_ParityChecks, EntryStandardFixture, TestCase):
    """Geri dönüş: RİM-də sərbəst iş açılıb, 5 + 5 söndürülüb → 2026-09-25 rəqəmləri (midterm 20) qayıdır."""

    expected = EXPECTED_OLD_RULE
    new_avg_total = "64.33"  # (74 + 65 + 54) / 3
