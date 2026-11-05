"""Sahib 2026-11-04: midterm zamanı qayıbdan kəsilən tələbə imtahan verə bilsin (qayıb texniki səhv ola bilər).

Qayıb limiti qapısı (``admission_block_reason``, ``registrar_block_reason(s)``) yalnız midterm OLMAYAN
imtahanlara tətbiq olunur; finalda əvvəlki kimi buraxılmır.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from apps.exams.models import Exam
from apps.exams.services.absence_gate import absence_gate_applies
from apps.exams.services.final_center import admission_block_reason
from apps.exams.services.journal_sync import registrar_block_reason, registrar_block_reasons
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import _make_people, _make_quiz
from apps.registrar.models import Subject

ELIGIBILITY = "apps.registrar.public.exam_eligibility"
BATCH = "apps.registrar.public.exam_eligibility_batch"
BARRED = {"linked": True, "barred": True, "reason": "QAYIB-LIMITI"}


class MidtermAbsenceGateTests(TestCase):
    def setUp(self):
        self.org, self.teacher, self.student = _make_people("mtabs")
        self.subject = Subject.objects.create(organization=self.org, code="MT-ABS", name="Fənn")
        self.exam = _make_quiz(self.org, self.teacher, subject=self.subject)
        self.request = SimpleNamespace(user=self.student)

    def _set_kind(self, kind):
        Exam.objects.filter(pk=self.exam.pk).update(exam_type_extended=kind)
        self.exam.refresh_from_db()

    def test_scope(self):
        self.assertFalse(absence_gate_applies(SimpleNamespace(exam_type_extended="midterm")))
        self.assertTrue(absence_gate_applies(SimpleNamespace(exam_type_extended="final")))

    def test_midterm_is_not_gated(self):
        self._set_kind("midterm")
        with patch(ELIGIBILITY, side_effect=AssertionError("çağırılmamalıdır")):
            self.assertIsNone(admission_block_reason(self.student, self.exam))
            self.assertIsNone(registrar_block_reason(self.request, self.exam))
        with patch(BATCH, return_value={self.subject.pk: BARRED}):
            self.assertEqual(registrar_block_reasons(self.request, [self.exam]), {self.exam.pk: None})

    def test_final_is_still_gated(self):
        self._set_kind("final")
        with patch(ELIGIBILITY, return_value=BARRED):
            self.assertEqual(admission_block_reason(self.student, self.exam), "QAYIB-LIMITI")
            self.assertEqual(registrar_block_reason(self.request, self.exam), "QAYIB-LIMITI")
        with patch(BATCH, return_value={self.subject.pk: BARRED}):
            self.assertEqual(registrar_block_reasons(self.request, [self.exam]), {self.exam.pk: "QAYIB-LIMITI"})
