"""Audit 2026-09-28 SV-1 — fakültə/kafedra görünüşünün valideyndən çıxılması kiçik kafedranı açmır.

Ssenari (audit PoC ``test_org_minus_department_reveals_hidden_department``): rektor, k = 3;
kafedra A — 6 cavab (hamısı 5), kafedra B — 2 cavab (hamısı 1). Əvvəl universitet
ortası 4,0 və A ortası 5,0 görünürdü → «8·4,0 − 6·5,0» B-nin hər iki cavabını açırdı.
"""

from __future__ import annotations

import itertools
import json
import re
import uuid

from django.test import SimpleTestCase, TestCase

from apps.organizations.models import OrgUnit
from apps.organizations.public import ORG_WIDE_SCOPE
from apps.surveys.services import filters as flt
from apps.surveys.services.analytics import department_benchmarks
from apps.surveys.services.analytics_extra import question_benchmarks, results_summary, safe_breakdown
from apps.surveys.services.analytics_units import settle_units
from core.constants import OrgUnitType
from core.rls import bypass_rls

from .factories import build_world, client_for, close_all, member, open_campaign
from .results_world import add_responses, close_campaign

SECTION = "/accounts/profile/?section=evaluation-results"


def _island(html, island_id):
    match = re.search(r'<script id="%s" type="application/json">(.*?)</script>' % re.escape(island_id), html, re.S)
    return json.loads(match.group(1)) if match else None


def _atoms_ok(rows, published, k):
    """Görünən vahid görünüşlərinin (valideyn + dərc olunanlar) bölgüsünün hər atomu 0 və ya ≥ k."""
    atoms: dict = {}
    for department, faculty, count in rows:
        signature = (department in published.departments, faculty in published.faculties)
        key = (department if signature[0] else None, faculty if signature[1] else None)
        atoms[key] = atoms.get(key, 0) + count
    return all(value == 0 or value >= k for value in atoms.values())


class SettleUnitsTest(SimpleTestCase):
    def test_parent_minus_single_visible_department_is_blocked(self):
        published = settle_units([("A", "F", 6), ("B", "F", 2)], 3)
        self.assertNotIn("A", published.departments)  # F − A = B (2) olardı
        self.assertNotIn("B", published.departments)
        self.assertIn("F", published.faculties)

    def test_parent_minus_published_siblings_is_blocked(self):
        published = settle_units([("A", "F", 5), ("C", "F", 5), ("B", "F", 2)], 3)
        self.assertEqual(len(published.departments), 1)  # F − A − C = B olardı; ən kiçik biri çıxır
        self.assertNotIn("B", published.departments)

    def test_org_minus_published_faculties_is_blocked(self):
        # F = A (5), G = C (5), H = B (2 < k): «universitet − F − G» = H olardı.
        published = settle_units([("A", "F", 5), ("C", "G", 5), ("B", "H", 2)], 3)
        visible_faculties = published.faculties & {"F", "G"}
        self.assertEqual(len(visible_faculties), 1)
        self.assertEqual(len(published.departments & {"A", "C"}), 1)

    def test_healthy_structure_keeps_everything(self):
        published = settle_units([("A", "F", 5), ("B", "F", 4), ("C", "G", 6)], 3)
        self.assertEqual(published.departments, {"A", "B", "C"})
        self.assertEqual(published.faculties, {"F", "G"})

    def test_department_spanning_faculties_is_never_published(self):
        published = settle_units([("A", "F", 5), ("A", "G", 5), ("C", "G", 5)], 3)
        self.assertNotIn("A", published.departments)

    def test_every_atom_is_empty_or_at_least_k(self):
        departments = [("A", "F"), ("B", "F"), ("C", "G"), ("D", "G"), ("E", None), (None, "F"), (None, None)]
        for counts in itertools.product((0, 1, 2, 3, 5), repeat=len(departments)):
            rows = [(dept, fac, n) for (dept, fac), n in zip(departments, counts) if n]
            if sum(n for _d, _f, n in rows) < 3:
                continue  # valideynin özü n < k ilə gizlidir — heç bir görünüş yoxdur
            published = settle_units(rows, 3)
            self.assertTrue(_atoms_ok(rows, published, 3), (rows, published))


class DepartmentDifferencingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        w = cls.w = build_world("svu1", students=2)
        close_all(w)
        cls.campaign = open_campaign(w, grace_until=None)
        add_responses(
            w,
            cls.campaign,
            teacher=w["teacher_a"],
            department=w["chair_a"],
            faculty=w["faculty"],
            subject=w["math"],
            group=w["group"],
            count=6,
            score=5,
            overall=9,
        )
        add_responses(
            w,
            cls.campaign,
            teacher=w["teacher_b"],
            department=w["chair_b"],
            faculty=w["faculty"],
            subject=w["phys"],
            group=w["group"],
            count=2,
            score=1,
            overall=2,
        )
        close_campaign(cls.campaign)
        with bypass_rls():
            cls.rector = member(w["org"], "svu1_rector", "rector")

    def _overview(self, query=""):
        html = client_for(self.w["org"], self.rector).get(SECTION + query).content.decode()
        return _island(html, "svr-overview-data") or {}

    def test_org_minus_department_no_longer_reveals_hidden_department(self):
        whole = self._overview()
        dept_a = self._overview(f"&er_department={self.w['chair_a'].pk}")
        dept_b = self._overview(f"&er_department={self.w['chair_b'].pk}")
        self.assertIn("likert", whole)  # universitet (8 cavab) görünür
        self.assertNotIn("likert", dept_a)  # A görünsəydi: universitet − A = B (2 cavab)
        self.assertNotIn("likert", dept_b)

    def test_summary_and_benchmarks_hide_department(self):
        with bypass_rls():
            filters = flt.ResultFilters(campaign_ids=(self.campaign.pk,), department_id=self.w["chair_a"].pk)
            summary = results_summary(self.w["org"], ORG_WIDE_SCOPE, filters, with_participation=False)
            bench = question_benchmarks(
                self.w["org"], ORG_WIDE_SCOPE, [self.campaign.pk], department_id=self.w["chair_a"].pk
            )
            dept_bench = department_benchmarks(self.w["org"], [self.campaign.pk], 3)
        self.assertTrue(summary["suppressed"])
        self.assertIsNone(summary["avg_overall"])
        self.assertEqual(bench["department"], {})  # müəllim kartındakı «kafedra» müqayisə nöqtəsi
        self.assertTrue(bench["org"])
        self.assertIsNone(dept_bench[self.w["chair_a"].pk]["avg_overall"])  # «Fərq: kafedra» sütunu
        self.assertIsNotNone(dept_bench["__org__"]["avg_overall"])

    def test_department_breakdown_rows_are_hidden(self):
        with bypass_rls():
            filters = flt.ResultFilters(campaign_ids=(self.campaign.pk,))
            data = safe_breakdown(self.w["org"], ORG_WIDE_SCOPE, filters, by="department", total_n=8)
        self.assertTrue(all(row["suppressed"] for row in data["rows"]))
        self.assertTrue(all(row["avg_overall"] is None and row["n"] is None for row in data["rows"]))

    def test_faculty_view_equal_to_parent_stays_visible(self):
        faculty = self._overview(f"&er_faculty={self.w['faculty'].pk}")
        self.assertIn("likert", faculty)  # F = universitet (fərq 0) — heç nə açmır


class SiblingDifferencingTest(TestCase):
    """A (5), C (5), B (2) — hər biri valideyndən ≥ k fərqlənir, amma «F − A − C» = B."""

    @classmethod
    def setUpTestData(cls):
        w = cls.w = build_world("svu2", students=2)
        with bypass_rls():
            cls.chair_c = OrgUnit.objects.create(
                organization=w["org"],
                name="Kafedra C",
                slug="svu2-kc",
                unit_type=OrgUnitType.CHAIR,
                parent=w["faculty"],
            )
            cls.teacher_x = member(w["org"], "svu2_tx", "teacher", unit=cls.chair_c)
        close_all(w)
        cls.campaign = open_campaign(w, grace_until=None)
        for teacher, chair, count, score in (
            (w["teacher_a"], w["chair_a"], 5, 5),
            (cls.teacher_x, cls.chair_c, 5, 4),
            (w["teacher_b"], w["chair_b"], 2, 1),
        ):
            add_responses(
                w,
                cls.campaign,
                teacher=teacher,
                department=chair,
                faculty=w["faculty"],
                subject=w["math"],
                group=w["group"],
                count=count,
                score=score,
                overall=score * 2,
            )
        close_campaign(cls.campaign)

    def test_not_all_siblings_of_a_hidden_department_are_visible(self):
        visible = []
        with bypass_rls():
            for chair in (self.w["chair_a"], self.chair_c, self.w["chair_b"]):
                filters = flt.ResultFilters(campaign_ids=(self.campaign.pk,), department_id=chair.pk)
                summary = results_summary(self.w["org"], ORG_WIDE_SCOPE, filters, with_participation=False)
                if not summary["suppressed"]:
                    visible.append(chair.pk)
        self.assertNotIn(self.w["chair_b"].pk, visible)
        self.assertLessEqual(len(visible), 1)  # A və C birlikdə görünsəydi: universitet − A − C = B

    def test_trend_point_follows_the_same_rule(self):
        from apps.surveys.services.analytics_detail import trend

        with bypass_rls():
            points = {
                chair.pk: trend(self.w["org"], ORG_WIDE_SCOPE, department_id=chair.pk)[-1]
                for chair in (self.w["chair_a"], self.chair_c)
            }
        self.assertLessEqual(sum(1 for point in points.values() if not point["suppressed"]), 1)


class UnknownUnitTest(SimpleTestCase):
    def test_unknown_unit_filter_is_not_allowed(self):
        published = settle_units([("A", "F", 6)], 3)
        self.assertTrue(published.allows(flt.ResultFilters(department_id="A")))
        self.assertFalse(published.allows(flt.ResultFilters(department_id=uuid.uuid4())))
        self.assertTrue(published.allows(flt.ResultFilters()))
