"""«Akademik analitika» bölməsinin görünüşü (2026-10-11 səliqə).

Kilidlənənlər: kabinetdə ikinci başlıq yoxdur (qabıq `<h1>` verir), KPI-lar ortaq
`ems-kpi` komponentidir, cədvəllər `ems-table`-dir; yekunlaşmış nəticə yoxdursa
keçid faizi və orta GPA «—» + səbəb qeydi göstərir («0,00%» / «Hesablana bilmir» YOX).
"""

import re
from decimal import Decimal

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils import translation

from apps.registrar import analytics_display
from apps.registrar.tests.test_analytics import _AnalyticsBase

PARTIAL = "registrar/partials/_analytics_content.html"


def _totals(**overrides):
    base = {
        "students": 628,
        "enrollments": 1596,
        "graded": 0,
        "passed": 0,
        "failed": 0,
        "in_progress": 1596,
        "barred": 0,
        "pass_rate": Decimal("0.00"),
        "fail_rate": Decimal("0.00"),
        "definite": 0,
        "avg_gpa": None,
        "avg_gpa_available": False,
        "avg_total": Decimal("0.00"),
        "absence_rate": Decimal("3.20"),
    }
    base.update(overrides)
    return base


def _row(label, **overrides):
    row = _totals(students=10, enrollments=20, in_progress=20, **overrides)
    row.update({"key": label, "label": label, "sublabel": ""})
    return row


def _data(totals, rows=None):
    rows = rows or [_row("KE-101")]
    return {"has_data": True, "period": None, "totals": totals, "programs": rows, "groups": rows, "at_risk": []}


def _kpi_values(html):
    return [re.sub(r"<[^>]+>", "", v).strip() for v in re.findall(r'class="ems-kpi__value">(.*?)</div>', html, re.S)]


class AnalyticsKpiTilesTest(SimpleTestCase):
    def setUp(self):
        translation.activate("az")
        self.addCleanup(translation.deactivate)

    def test_nothing_finalized_shows_dash_with_reason(self):
        tiles = analytics_display.kpi_tiles(_data(_totals()))
        by_label = {str(t["label"]): t for t in tiles}
        self.assertEqual(len(tiles), 5)
        self.assertEqual(by_label["Keçid faizi"]["value"], "—")
        self.assertIn("yekunlaşmış", by_label["Keçid faizi"]["note"])
        self.assertEqual(by_label["Orta GPA"]["value"], "—")
        self.assertNotIn("unit", by_label["Keçid faizi"])

    def test_finalized_values_and_tones(self):
        totals = _totals(
            passed=3,
            failed=7,
            definite=10,
            pass_rate=Decimal("30.00"),
            avg_gpa=Decimal("55.10"),
            avg_gpa_available=True,
            absence_rate=Decimal("22.50"),
            barred=4,
        )
        by_label = {str(t["label"]): t for t in analytics_display.kpi_tiles(_data(totals))}
        self.assertEqual(by_label["Keçid faizi"]["value"], Decimal("30.00"))
        self.assertEqual(by_label["Keçid faizi"]["tone"], "accent-danger")
        self.assertEqual(by_label["Orta GPA"]["value"], Decimal("55.10"))
        self.assertEqual(by_label["Qayıb faizi"]["tone"], "accent-warning")
        self.assertIn("4", by_label["Qayıb faizi"]["note"])

    def test_no_data_has_no_tiles(self):
        self.assertEqual(analytics_display.kpi_tiles({"has_data": False, "totals": None}), [])


class AnalyticsPartialRenderTest(SimpleTestCase):
    def setUp(self):
        translation.activate("az")
        self.addCleanup(translation.deactivate)

    def _render(self, data, **extra):
        ctx = analytics_display.view_context([], data, embedded=True)
        ctx.update({"embedded_in_shell": True, "request": RequestFactory().get("/"), **extra})
        return render_to_string(PARTIAL, ctx)

    def test_embedded_has_no_own_title_and_uses_components(self):
        html = self._render(_data(_totals()))
        self.assertNotIn("<h1", html)
        self.assertNotRegex(html, r"<h2[^>]*>\s*(<i[^>]*></i>\s*)?Akademik analitika")
        self.assertIn('class="ems-header"', html)
        self.assertIn("ems-kpi", html)
        self.assertIn("ems-table", html)
        self.assertNotIn("analytics-card", html)
        self.assertNotIn("journal-grid", html)

    def test_nothing_finalized_renders_dash_not_zero(self):
        html = self._render(_data(_totals()))
        values = _kpi_values(html)
        self.assertEqual(values[2], "—")  # keçid faizi
        self.assertEqual(values[3], "—")  # orta GPA
        self.assertNotIn("Hesablana bilmir", html)
        self.assertNotIn("0,00%", html)
        self.assertNotIn("0.00%", html)

    def test_empty_semester_uses_empty_state(self):
        html = self._render({"has_data": False, "totals": None, "programs": [], "groups": [], "at_risk": []})
        self.assertIn("ems-state", html)
        self.assertIn("hələ qiymətləndirmə datası yoxdur", html)
        self.assertNotIn("ems-kpi", html)


@override_settings(UNIVERSITY_MODE=True)
class AnalyticsCabinetRenderTest(_AnalyticsBase):
    def test_cabinet_section_renders_components_once(self):
        from django.test import Client
        from django.urls import reverse

        client = Client()
        client.force_login(self.dean)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        resp = client.get(reverse("accounts:profile"), {"section": "analytics"})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        panel = html[html.index('data-profile-section-panel="analytics"') :]
        self.assertNotIn('class="journal-title"', panel)
        self.assertIn("ems-kpi__value", panel)
        self.assertIn('class="ems-table ems-table--sticky analytics-table', panel)
        self.assertEqual(len(resp.context["analytics_kpis"]), 5)
