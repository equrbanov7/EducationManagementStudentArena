"""Sahib 2026-11-19 — «RİM təqdimatı ilə düzəliş» testdən gələn midterm balını dəyişə bilmirdi.

Ekran (`exam_score_entry.js`) testdən gələn balın S-xanalarını (`data-q-locked`) heç bir rejimdə açmırdı; indi
RİM rejimində açılır. Bu, serverdə iki şeyi tələb edir (burada yoxlanır):

* dəyişdirilmiş test balı RİM təqdimatı (səbəb + qeyd + sənəd) ilə yazılır — ``correction`` sətri, jurnal xanası;
* toxunulmamış test sətirləri də S1 = bal kimi POST olunur — bölgüsü heç yazılmamış balda bu DƏYİŞİKLİK deyil,
  boş düzəliş sətri yaranmır (``exam_score_questions.split_unchanged``).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.registrar import exam_score_entry as service
from apps.registrar import exam_score_questions as questions
from apps.registrar import exam_score_sheets as sheets
from apps.registrar import interim_components
from apps.registrar.models import (
    ComponentScore,
    CorrectionReason,
    ExamAssessment,
    ExamScoreEntry,
    ExamScoreEntryKind,
)
from apps.registrar.tests.test_exam_score_assessment_2026_10_25 import _MEDIA, MidtermPeriodFixture, _pdf
from core.rls import bypass_rls


class SplitUnchangedTest(SimpleTestCase):
    def test_single_column_on_unsplit_score_is_not_a_change(self):
        self.assertTrue(questions.split_unchanged(None, [19]))
        self.assertTrue(questions.split_unchanged(None, None))
        self.assertTrue(questions.split_unchanged([9, 10], ["9", "10"]))
        # Çox sütunlu bölgü və fərqli bölgü yenə dəyişiklikdir (köhnə qayda).
        self.assertFalse(questions.split_unchanged(None, [9, 10]))
        self.assertFalse(questions.split_unchanged([9, 10], [10, 9]))
        self.assertFalse(questions.split_unchanged([19], None))


@override_settings(UNIVERSITY_MODE=True, MEDIA_ROOT=_MEDIA)
class RimCorrectionOfTestScoreTest(MidtermPeriodFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.build_fixture("esrt")
            cls.component = interim_components.ensure_kollokviums(cls.offering)[0]
            for index, enrollment in enumerate(cls.enrollments, start=1):
                ComponentScore.objects.create(
                    organization=cls.org,
                    component=cls.component,
                    enrollment=enrollment,
                    score=Decimal("19"),
                    exam_source={"attempt_id": index, "exam_id": 1, "percent": "63.3"},
                )

    def _save(self, user, values, **submission):
        sheet = sheets.create_sheet(
            offering=self.offering,
            by_user=user,
            assessment=ExamAssessment.MIDTERM,
            question_maxes=[30],
            checked_on=timezone.localdate(),
        )
        rows = [
            {"enrollment_id": str(enrollment.pk), "question_scores": [value], "kind": "correction", **submission}
            for enrollment, value in zip(self.enrollments, values)
        ]
        later = timezone.now() + timedelta(days=2)
        with mock.patch("django.utils.timezone.now", return_value=later):
            return service.save_roster_scores(offering=self.offering, rows=rows, by_user=user, sheet=sheet)

    def _cells(self):
        return [
            ComponentScore.objects.get(component=self.component, enrollment=enrollment).score
            for enrollment in self.enrollments
        ]

    def test_rim_changes_test_score_and_untouched_rows_write_nothing(self):
        submission = {"reason": CorrectionReason.TECHNICAL, "note": "RİM təqdimatı № 7", "evidence": _pdf()}
        with bypass_rls():
            result = self._save(self.rim, ["25", "19"], **submission)
            self.assertEqual(result["written"], 1, result)
            self.assertFalse(result["errors"], result)
            self.assertEqual(self._cells(), [Decimal("25"), Decimal("19")])
            entry = ExamScoreEntry.objects.get()
            self.assertEqual(entry.kind, ExamScoreEntryKind.CORRECTION)
            self.assertEqual((entry.old_score, entry.new_score), (Decimal("19"), Decimal("25")))
            self.assertEqual(entry.enrollment, self.enrollments[0])

    def test_correction_of_test_score_still_needs_rim_and_full_submission(self):
        with bypass_rls():
            denied = self._save(self.center, ["25", "19"], reason=CorrectionReason.TECHNICAL, note="x", evidence=_pdf())
            self.assertEqual(denied["written"], 0)
            no_doc = self._save(self.rim, ["25", "19"], reason=CorrectionReason.TECHNICAL, note="x")
            self.assertEqual(no_doc["written"], 0)
            self.assertEqual(self._cells(), [Decimal("19"), Decimal("19")])
            self.assertFalse(ExamScoreEntry.objects.exists())
