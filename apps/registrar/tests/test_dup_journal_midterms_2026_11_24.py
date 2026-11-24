"""MR-000714: ``copy_dup_journal_midterms_20261124`` — təkrar jurnaldakı Midterm balı əsl jurnala (yalnız boş yerə)."""

from __future__ import annotations

import pathlib
from collections import Counter
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase

from apps.registrar import dup_journal_midterms_2026_11_24 as fixer
from apps.registrar.models import AssessmentComponent, ComponentScore, Enrollment
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class SpecTest(SimpleTestCase):
    def test_pairs_and_workflow(self):
        self.assertEqual(len(fixer.PAIRS), 3)
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - copy_dup_journal_midterms_20261124\n", text)
        self.assertIn("|dupmid|", text)


class DupJournalMidtermsTest(_GuestRosterBase):
    """Mənbə = G1-in «Riyaziyyat» jurnalı (təkrar rolunda), hədəf = G1-in «Tarix» jurnalı."""

    def setUp(self):
        scope = bypass_rls()
        scope.__enter__()
        self.addCleanup(scope.__exit__, None, None, None)
        self.admin = get_user_model().objects.create_superuser("dupmid_admin", "dupmid@qku.edu.az", "pw")
        self.source = self.host.enrollments.get(offering__subject=self.math).offering
        component = AssessmentComponent.objects.create(
            organization=self.org, offering=self.source, name="Midterm", kind="kollokvium", max_score=30
        )
        src_enrollment = Enrollment.objects.get(offering=self.source, student=self.host)
        ComponentScore.objects.create(organization=self.org, component=component, enrollment=src_enrollment, score=27)
        self.pairs = ((str(self.source.pk), str(self.offering.pk)),)

    def run_fix(self):
        counts = Counter()
        batch = fixer.run(organization=self.org, actor=self.admin, counts=counts, batch="", pairs=self.pairs)
        return counts, batch

    def target_scores(self):
        return list(
            ComponentScore.objects.filter(
                enrollment__offering=self.offering, enrollment__student=self.host
            ).values_list("score", flat=True)
        )

    def test_copies_once_and_undo_removes(self):
        counts, batch = self.run_fix()
        self.assertEqual(counts["scores_copied"], 1)
        self.assertEqual(self.target_scores(), [Decimal(27)])
        again, _ = self.run_fix()
        self.assertEqual(again["target_filled"], 1)
        self.assertEqual(again["scores_copied"], 0)
        undone = Counter()
        fixer.undo(organization=self.org, actor=self.admin, counts=undone, batch=batch)
        self.assertEqual(undone["undo_scores_removed"], 1)
        self.assertEqual(self.target_scores(), [])

    def test_pair_from_another_group_is_refused(self):
        counts = Counter()
        fixer.run(
            organization=self.org,
            actor=self.admin,
            counts=counts,
            batch="",
            pairs=((str(self.other_offering.pk), str(self.offering.pk)),),
        )
        self.assertEqual(counts["pair_invalid"], 1)
