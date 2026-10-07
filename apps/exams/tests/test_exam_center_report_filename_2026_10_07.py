"""Təhlükəsizlik auditi 2026-10-07 — imtahan mərkəzi hesabatının fayl adı xam URL parametrindən qurulmur.

``_export_xlsx`` damğanı ``date_from``-dan (yalnız ``-`` silinərək) qururdu:
``date_from=date_to='x";filename="evil.html'`` ``Content-Disposition``-a
ikinci ``filename`` yeridirdi. İndi tarix yoxlanır, damğa yalnız rəqəmdir.
Filtr/iş kitabı/audit qatı mock-lanır — burada yalnız başlığın qurulması yoxlanır.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.exams.views.exam_center import reports

FILENAME_RE = re.compile(r'^attachment; filename="imtahan_hesabati_\d{8}(_\d{4})?\.xlsx"$')


class ExamCenterReportFilenameTest(SimpleTestCase):
    def _export(self, **params):
        request = RequestFactory().get("/exams/center/reports/", {"export": "xlsx", **params})
        request.user = SimpleNamespace(get_full_name=lambda: "Mərkəz", username="center")
        workbook = mock.Mock()
        with (
            mock.patch.object(reports, "filter_tickets", return_value=[]),
            mock.patch.object(reports, "log_action"),
            mock.patch.object(reports, "_filter_summary", return_value=[]),
            mock.patch.object(reports, "build_final_report_workbook", return_value=workbook),
        ):
            response = reports._export_xlsx(request, organization=SimpleNamespace(pk=1))
        workbook.save.assert_called_once_with(response)
        return response["Content-Disposition"]

    def test_quotes_in_date_cannot_alter_filename(self):
        evil = 'x";filename="evil.html'
        header = self._export(date_from=evil, date_to=evil)
        self.assertRegex(header, FILENAME_RE)
        self.assertNotIn("evil", header)
        self.assertEqual(header.count("filename"), 1)

    def test_same_valid_day_is_used_as_stamp(self):
        header = self._export(date_from="2026-10-07", date_to="2026-10-07")
        self.assertEqual(header, 'attachment; filename="imtahan_hesabati_20261007.xlsx"')

    def test_range_or_invalid_dates_use_current_time(self):
        for params in (
            {"date_from": "2026-10-01", "date_to": "2026-10-07"},
            {"date_from": "2026-13-45", "date_to": "2026-13-45"},
            {},
        ):
            with self.subTest(params=params):
                header = self._export(**params)
                self.assertRegex(header, r'^attachment; filename="imtahan_hesabati_\d{8}_\d{4}\.xlsx"$')
