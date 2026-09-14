"""2026-09-14 wave 2 (audit F-07, §27 «6 ixracda formula neytrallaşdırma») — accounts ixracları.

Üç CSV ixracı ``core.export_safety.safe_csv_writer``-ə keçirildi:

* ``student_registry_export`` — tələbə reyestri (ad/qrup/ixtisas mətnləri);
* ``statistics_export_csv`` — köhnə statistika xülasəsi;
* ``statistics_export_metrics_csv`` — rol-aware göstəricilər (artıq ``_safe`` ilə
  neytrallaşdırırdı; sarğı ikiqat prefiks QOYMAMALIDIR).

Hər test ``=1+1`` (və digər formula-başlanğıclı) xananın çıxışda ``'=1+1`` olduğunu,
ədəd sütunlarının isə dəyişmədiyini yoxlayır.
"""

from __future__ import annotations

import csv
import io
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import UserProfile

User = get_user_model()
PASSWORD = "StrongPass123!"


def _parse_csv(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8").lstrip("﻿")
    return list(csv.reader(io.StringIO(text)))


class StudentRegistryExportFormulaTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("w2sec_registry", "w2sec_registry@test.az", PASSWORD)
        self.client = Client()
        self.client.force_login(self.user)

    def test_formula_like_cells_are_neutralised(self):
        row = {
            "student_code": "=1+1",
            "name": '=HYPERLINK("http://evil")',
            "program_label": "+cmd",
            "group_name": "-1+1",
            "course_label": 2,
            "admission_year": 2024,
            "form_label": "@SUM(A1)",
            "funding_label": "\tödənişli",
            "status_label": "aktiv",
        }
        actor = SimpleNamespace(can_view_registry=True)
        with (
            mock.patch("apps.accounts.services.people.resolve_actor", return_value=actor),
            mock.patch("apps.accounts.services.people.registry.export_rows", return_value=[row]),
        ):
            response = self.client.get(reverse("accounts:student_registry_export"))
        self.assertEqual(response.status_code, 200)
        rows = _parse_csv(response.content)
        self.assertEqual(len(rows), 2)
        data = rows[1]
        self.assertEqual(data[0], "'=1+1")
        self.assertEqual(data[1], '\'=HYPERLINK("http://evil")')
        self.assertEqual(data[2], "'+cmd")
        self.assertEqual(data[3], "'-1+1")
        # Ədədlər dəyişmir.
        self.assertEqual(data[4], "2")
        self.assertEqual(data[5], "2024")
        self.assertEqual(data[6], "'@SUM(A1)")
        self.assertEqual(data[7], "'\tödənişli")
        self.assertEqual(data[8], "aktiv")


class StatisticsExportCsvFormulaTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("w2sec_stats", "w2sec_stats@test.az", PASSWORD)
        UserProfile.objects.get_or_create(user=self.user)
        self.client = Client()
        self.client.force_login(self.user)

    def test_summary_values_are_neutralised(self):
        stats = {"summary": {"total_users": 7, "top_course": "=1+1", "note": "+cmd"}}
        with mock.patch("core.cache.get_or_set_cached_statistics", return_value=stats):
            response = self.client.get(reverse("accounts:statistics_export_csv"))
        self.assertEqual(response.status_code, 200)
        rows = _parse_csv(response.content)
        body = {row[0]: row[1] for row in rows[1:]}
        self.assertEqual(body["Total Users"], "7")
        self.assertEqual(body["Top Course"], "'=1+1")
        self.assertEqual(body["Note"], "'+cmd")


class StatisticsExportMetricsFormulaTest(TestCase):
    """``build_metrics_csv_rows`` artıq ``'`` qoyur; ``safe_csv_writer`` ikinci dəfə qoymamalıdır."""

    def setUp(self):
        self.user = User.objects.create_superuser("w2sec_metrics", "w2sec_metrics@test.az", PASSWORD)
        UserProfile.objects.get_or_create(user=self.user)
        self.client = Client()
        self.client.force_login(self.user)

    def test_no_double_prefix_and_raw_formula_absent(self):
        presented = {
            "scope_label": "=1+1",
            "window": {"period_name": "+cmd", "date_from": "", "date_to": ""},
            "kpis": [{"label": "Tələbə", "value": 12, "unit": "", "note": None}],
            "blocks": [],
            "extra": [],
        }
        with (
            mock.patch(
                "apps.accounts.views.profile.statistics_export_metrics._compute_dashboard",
                return_value=(presented, [], []),
            ),
            mock.patch(
                "apps.accounts.views.profile.statistics_export_metrics._resolve_profile",
                return_value="superadmin",
            ),
        ):
            response = self.client.get(reverse("accounts:statistics_export_metrics_csv"))
        self.assertEqual(response.status_code, 200)
        flat = [cell for row in _parse_csv(response.content) for cell in row]
        self.assertIn("'=1+1", flat)
        self.assertIn("'+cmd", flat)
        self.assertNotIn("=1+1", flat)
        self.assertNotIn("''=1+1", flat)
        self.assertIn("12", flat)
