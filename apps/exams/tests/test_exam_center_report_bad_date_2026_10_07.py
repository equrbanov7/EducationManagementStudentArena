"""İmtahan mərkəzi hesabatı: yararsız tarix parametri 500 vermir, filtr sadəcə tətbiq olunmur (2026-10-07)."""

from django.test import SimpleTestCase

from apps.exams.services.final_center import reports


class ReportDateParamTests(SimpleTestCase):
    def test_valid_iso_date_is_parsed(self):
        self.assertEqual(str(reports._report_date({"date_from": "2026-10-07"}, "date_from")), "2026-10-07")

    def test_invalid_dates_are_ignored(self):
        for raw in ("2026-13-40", "abc", "2026-02-30", "", "x\";filename=evil"):
            self.assertIsNone(reports._report_date({"date_from": raw}, "date_from"), raw)
