"""Sahib 2026-11-28: tələbə kabinetində «Aktivlik» yox — fənnin növünə görə «Seminar» / «Laboratoriya»."""

from decimal import Decimal

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils import translation

from apps.registrar import activity_kinds as ak
from apps.registrar import entry_standard


def _totals(seminar=(), lab=()):
    totals = ak.LessonTotals()
    for score in seminar:
        totals.add(ak.SEMINAR, Decimal(score))
    for score in lab:
        totals.add(ak.LAB, Decimal(score))
    return totals


def _parts(detail, **extra):
    return entry_standard.EntryParts(
        attendance=Decimal("10"),
        activity=detail.value,
        midterm=Decimal("0"),
        selfwork=Decimal("0"),
        total=Decimal("10"),
        selfwork_active=False,
        activity_detail=detail,
        **extra,
    )


class ActivityKindLabelTests(SimpleTestCase):
    def test_seminar_only_marks(self):
        detail = ak.activity(_totals(seminar=[8]), lambda: ak.SEMINAR_BIT, split_enabled=True)
        self.assertEqual(detail.kind_label, ak.SEMINAR)

    def test_lab_only_subject(self):
        detail = ak.activity(_totals(lab=[6]), ak.LAB_BIT, split_enabled=True)
        self.assertEqual(detail.kind_label, ak.LAB)

    def test_both_kinds_split(self):
        detail = ak.activity(_totals(seminar=[8]), ak.BOTH, split_enabled=True)
        self.assertTrue(detail.split)
        self.assertEqual(detail.kind_label, "both")

    def test_no_marks_lazy_bits_are_resolved_once_for_the_label(self):
        calls = []
        detail = ak.activity(_totals(), lambda: calls.append(1) or ak.LAB_BIT, split_enabled=True)
        self.assertEqual(calls, [])  # sorğu yoxdur — tənbəl maska çağırılmır
        self.assertEqual(detail.kind_label, ak.LAB)
        self.assertEqual(detail.kind_label, ak.LAB)
        self.assertEqual(calls, [1])

    def test_no_marks_known_bits_used(self):
        detail = ak.activity(_totals(), ak.LAB_BIT, split_enabled=True)
        self.assertEqual(detail.kind_label, ak.LAB)


class ActivityLabelTemplateTests(SimpleTestCase):
    def _render(self, template, parts):
        with translation.override("az"):
            return render_to_string(template, {"parts": parts})

    def test_entry_parts_uses_kind_name(self):
        html = self._render("registrar/partials/_entry_parts.html", _parts(ak.ActivityDetail(Decimal("6"), kinds=2)))
        self.assertIn("Laboratoriya: <strong>6", html)
        self.assertNotIn("Aktivlik", html)

    def test_breakdown_uses_kind_name(self):
        html = self._render("partials/ems_ui/_entry_breakdown.html", _parts(ak.ActivityDetail(Decimal("7"), kinds=1)))
        self.assertIn(">Seminar</span>", html)
        self.assertNotIn("Aktivlik", html)

    def test_unknown_kind_falls_back_to_both_names(self):
        html = self._render("partials/ems_ui/_entry_breakdown.html", _parts(ak.ActivityDetail(Decimal("0"))))
        self.assertIn(">Seminar / Laboratoriya</span>", html)

    def test_practical_subject(self):
        parts = _parts(ak.ActivityDetail(Decimal("5"), kinds=1), practical=True)
        html = self._render("registrar/partials/_entry_parts.html", parts)
        self.assertIn("Praktiki məşğələ: <strong>5", html)

    def test_reconciliation_notice_is_red(self):
        with translation.override("az"):
            html = render_to_string("partials/_result_reconciliation_notice.html", {})
        self.assertIn("ems-banner--danger", html)
