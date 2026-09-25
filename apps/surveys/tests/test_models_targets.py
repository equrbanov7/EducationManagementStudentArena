"""Model məhdudiyyətləri, anonimlik sxemi və hədəf hesabı."""

from __future__ import annotations

import datetime

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.registrar.models import Enrollment, Lesson
from apps.surveys.constants import Section
from apps.surveys.models import SurveyAnswer, SurveyReceipt, SurveyResponse
from apps.surveys.services.targets import pending_counts, student_targets
from apps.surveys.services.templates import ensure_default_template
from core.rls import bypass_rls

from .factories import build_world, close_all, close_journal, open_campaign


class AnonymitySchemaTest(TestCase):
    """Cavab cədvəllərində tələbəyə və ya vaxta aparan heç bir sahə YOXDUR."""

    def test_response_has_no_student_or_time_fields(self):
        names = {field.name for field in SurveyResponse._meta.get_fields()}
        for forbidden in ("student", "created_at", "updated_at", "submitted_on", "submitted_at", "receipt"):
            self.assertNotIn(forbidden, names)
        self.assertEqual(SurveyResponse._meta.pk.get_internal_type(), "UUIDField")

    def test_answer_has_no_time_fields_and_random_pk(self):
        names = {field.name for field in SurveyAnswer._meta.get_fields()}
        self.assertFalse(names & {"created_at", "updated_at", "student"})
        self.assertEqual(SurveyAnswer._meta.pk.get_internal_type(), "UUIDField")

    def test_receipt_does_not_reference_response(self):
        related = {getattr(f.related_model, "__name__", "") for f in SurveyReceipt._meta.get_fields() if f.is_relation}
        self.assertNotIn("SurveyResponse", related)
        self.assertNotIn("SurveyAnswer", related)
        self.assertEqual(SurveyReceipt._meta.pk.get_internal_type(), "UUIDField")


class ReceiptConstraintTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svm", students=1)
        close_all(cls.w)
        cls.campaign = open_campaign(cls.w)

    def _receipt(self, **extra):
        data = {
            "organization": self.w["org"],
            "campaign": self.campaign,
            "student": self.w["students"][0],
            "scope": Section.TEACHER,
            "offering": self.w["off_math"],
            "teacher": self.w["teacher_a"],
            "completed_on": "2026-09-25",
        }
        data.update(extra)
        return SurveyReceipt.objects.create(**data)

    def test_one_receipt_per_student_teacher(self):
        with bypass_rls():
            self._receipt()
            with self.assertRaises(IntegrityError), transaction.atomic():
                self._receipt()
            # «1 müəllim üzrə tələbədən 1»: eyni müəllim BAŞQA açılışda da ikinci qəbz ala bilməz.
            with self.assertRaises(IntegrityError), transaction.atomic():
                self._receipt(offering=self.w["off_phys"])
            # Eyni açılışın BAŞQA müəllimi — ayrıca hədəfdir.
            self._receipt(teacher=self.w["teacher_c"])

    def test_general_once_per_campaign(self):
        with bypass_rls():
            self._receipt(scope=Section.GENERAL, offering=None, teacher=None)
            with self.assertRaises(IntegrityError), transaction.atomic():
                self._receipt(scope=Section.GENERAL, offering=None, teacher=None)

    def test_scope_shape_is_enforced(self):
        with bypass_rls(), self.assertRaises(IntegrityError), transaction.atomic():
            self._receipt(scope=Section.GENERAL)  # ümumi bölmədə açılış olmamalıdır

    def test_answer_score_range(self):
        with bypass_rls():
            template = ensure_default_template(self.w["org"])
            question = template.questions.get(code="clarity")
            response = SurveyResponse.objects.create(
                organization=self.w["org"], campaign=self.campaign, scope=Section.TEACHER
            )
            with self.assertRaises(IntegrityError), transaction.atomic():
                SurveyAnswer.objects.create(organization=self.w["org"], response=response, question=question, score=11)


class TargetComputationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svt", students=2)
        cls.campaign = open_campaign(cls.w)

    def test_open_journals_give_no_targets(self):
        with bypass_rls():
            self.assertEqual(student_targets(self.campaign, self.w["students"][0]), [])
            self.assertEqual(pending_counts(self.campaign, self.w["students"][0]), (0, 0))

    def test_closed_journals_lesson_instructors_and_fallback(self):
        close_all(self.w)
        with bypass_rls():
            targets = student_targets(self.campaign, self.w["students"][0], with_labels=True)
        teacher_pairs = {(t.offering_id, t.teacher_id) for t in targets if not t.is_general}
        self.assertEqual(
            teacher_pairs,
            {
                (self.w["off_math"].pk, self.w["teacher_a"].pk),  # instructor=None dərsi → açılışın müəllimi
                (self.w["off_math"].pk, self.w["teacher_c"].pk),  # dərsin öz müəllimi
                (self.w["off_phys"].pk, self.w["teacher_b"].pk),  # dərs yoxdur → geri düşmə
            },
        )
        self.assertEqual(sum(1 for t in targets if t.is_general), 1)
        labelled = next(t for t in targets if t.teacher_id == self.w["teacher_c"].pk)
        self.assertEqual(labelled.subject, "Riyaziyyat")
        self.assertEqual(labelled.group, "G-101")
        self.assertTrue(labelled.teacher_name)

    def test_only_closed_offerings_count(self):
        with bypass_rls():
            close_journal(self.w["org"], self.w["off_phys"])
            targets = student_targets(self.campaign, self.w["students"][0])
        self.assertEqual({t.teacher_id for t in targets if not t.is_general}, {self.w["teacher_b"].pk})

    def test_dropped_enrollment_is_excluded(self):
        close_all(self.w)
        with bypass_rls():
            Enrollment.objects.filter(student=self.w["students"][0], offering=self.w["off_phys"]).update(
                status="dropped"
            )
            targets = student_targets(self.campaign, self.w["students"][0])
        self.assertNotIn(self.w["off_phys"].pk, {t.offering_id for t in targets})

    def test_all_lessons_by_other_teacher_drop_offering_instructor(self):
        close_all(self.w)
        with bypass_rls():
            Lesson.objects.filter(offering=self.w["off_math"], instructor__isnull=True).update(
                instructor=self.w["teacher_c"]
            )
            targets = student_targets(self.campaign, self.w["students"][0])
        math_teachers = {t.teacher_id for t in targets if t.offering_id == self.w["off_math"].pk}
        self.assertEqual(math_teachers, {self.w["teacher_c"].pk})

    def test_teacher_with_two_offerings_is_one_target(self):
        """Sahib (2026-09-25): «1 müəllim üzrə tələbədən 1» — iki fənn, bir forma, fənlər birlikdə."""
        close_all(self.w)
        student = self.w["students"][0]
        with bypass_rls():
            Lesson.objects.create(
                organization=self.w["org"],
                offering=self.w["off_phys"],
                date=datetime.date(2026, 9, 11),
                instructor=self.w["teacher_a"],
            )
            targets = student_targets(self.campaign, student, with_labels=True)
            plain = student_targets(self.campaign, student)
        teacher_a = [t for t in targets if t.teacher_id == self.w["teacher_a"].pk]
        self.assertEqual(len(teacher_a), 1)
        self.assertEqual(set(teacher_a[0].subject.split(", ")), {"Riyaziyyat", "Fizika"})
        # Etiketli və etiketsiz çağırış EYNİ «əsas» açılışı seçir (forma URL-i sabit qalır).
        primary = next(t.offering_id for t in plain if t.teacher_id == self.w["teacher_a"].pk)
        self.assertEqual(teacher_a[0].offering_id, primary)
        with bypass_rls():
            SurveyReceipt.objects.create(
                organization=self.w["org"],
                campaign=self.campaign,
                student=student,
                scope=Section.TEACHER,
                offering_id=primary,
                teacher=self.w["teacher_a"],
                completed_on="2026-09-25",
            )
            after = student_targets(self.campaign, student)
        self.assertTrue(next(t for t in after if t.teacher_id == self.w["teacher_a"].pk).done)

    def test_receipts_mark_targets_done(self):
        close_all(self.w)
        student = self.w["students"][1]
        with bypass_rls():
            SurveyReceipt.objects.create(
                organization=self.w["org"],
                campaign=self.campaign,
                student=student,
                scope=Section.TEACHER,
                offering=self.w["off_phys"],
                teacher=self.w["teacher_b"],
                completed_on="2026-09-25",
            )
            pending, total = pending_counts(self.campaign, student)
        self.assertEqual((pending, total), (3, 4))
