"""Dərs yükü giriş qapıları — QA 2026-09-05 WORKLOAD-SCHEDULE-01/02 reqressiya qapısı."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.workload.services.people import parse_uuid, resolve_chair
from apps.workload.services.scoping import WorkloadDenied
from apps.workload.services.tasks import normalize_academic_year


class AcademicYearGuardTest(SimpleTestCase):
    def test_valid_forms_normalise(self):
        self.assertEqual(normalize_academic_year("2026/2027"), "2026/2027")
        self.assertEqual(normalize_academic_year("2026-2027"), "2026/2027")

    def test_garbage_and_out_of_range_years_are_rejected(self):
        # `format_year` ilk 4 rəqəmli ili götürüb Y/Y+1 qurur ("2026/2029" → "2026/2027" — qəsdli);
        # burada yalnız il TAPILMAYAN və ya diapazondan kənar dəyərlər rədd edilir.
        for raw in ("abc", "", "1800/1801", "iki min", "9999"):
            self.assertEqual(normalize_academic_year(raw), "", raw)


class ChairIdGuardTest(SimpleTestCase):
    def test_non_uuid_chair_is_denied_not_500(self):
        self.assertIsNone(parse_uuid("x"))
        self.assertIsNone(parse_uuid(""))
        with self.assertRaises(WorkloadDenied):
            resolve_chair(None, "x")
