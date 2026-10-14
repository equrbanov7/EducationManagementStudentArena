"""2026-10-14 (sahib): «Ancaq sınaq imtahanı yaradılması olan yerlərdə select option yox,
avtomatik ancaq Sınaq yazsın».

Qayda:
* Final/midterm səlahiyyəti olmayan aktor (müəllim) üçün yeganə real kateqoriya «Sınaq»
  (quiz) olduqda sehrbaz select ÇƏKMİR — oxunan həb + gizli input; redaktə modalı da
  eyni partialdır.
* Server həmin kateqoriyanı MƏCBURİ edir: boş/çatışmayan dəyər → quiz; başqa dəyər
  (final, midterm, placement …) saxtalaşdırılıb göndərilsə forma rədd edir.
* Bir neçə real kateqoriya icazəlidirsə (imtahan mərkəzi) adi select qalır.
"""

from django import forms
from django.urls import reverse

from apps.exams.forms import ExamForm
from apps.exams.models import Exam
from apps.exams.tests.test_exam_center_policy import _Base


class TrialOnlyCategoryFormTests(_Base):
    def setUp(self):
        self.teacher.set_active_organization_context(self.org)
        self.exam_center.set_active_organization_context(self.org)

    def _data(self, **overrides):
        data = {
            "title": "Sınaq imtahanı",
            "exam_type": "test",
            "random_question_count": 10,
            "subject": self.subject.pk,
        }
        data.update(overrides)
        return data

    def test_teacher_category_is_locked_to_trial(self):
        form = ExamForm(user=self.teacher, organization=self.org)
        self.assertEqual(form.exam_category_locked["value"], "quiz")
        field = form.fields["exam_type_extended"]
        self.assertIsInstance(field.widget, forms.HiddenInput)
        self.assertEqual([value for value, _label in field.choices], ["quiz"])
        self.assertEqual(form.initial["exam_type_extended"], "quiz")

    def test_exam_center_keeps_full_select(self):
        form = ExamForm(user=self.exam_center, organization=self.org)
        self.assertIsNone(form.exam_category_locked)
        values = {value for value, _label in form.fields["exam_type_extended"].choices}
        self.assertTrue({"", "quiz", "midterm", "final"} <= values)
        self.assertNotIsInstance(form.fields["exam_type_extended"].widget, forms.HiddenInput)

    def test_teacher_empty_category_is_forced_to_trial(self):
        form = ExamForm(self._data(exam_type_extended=""), user=self.teacher, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["exam_type_extended"], "quiz")
        self.assertEqual(form.save(commit=False).exam_type_extended, "quiz")

    def test_teacher_missing_category_is_forced_to_trial(self):
        form = ExamForm(self._data(), user=self.teacher, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["exam_type_extended"], "quiz")

    def test_teacher_tampered_category_is_rejected(self):
        for tampered in ("final", "midterm", "placement", "practice"):
            with self.subTest(category=tampered):
                form = ExamForm(self._data(exam_type_extended=tampered), user=self.teacher, organization=self.org)
                self.assertFalse(form.is_valid())
                self.assertIn("exam_type_extended", form.errors)

    def test_teacher_editing_uncategorised_exam_is_forced_to_trial(self):
        legacy = Exam.objects.create(
            title="Köhnə imtahan",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            exam_type_extended=None,
        )
        unbound = ExamForm(instance=legacy, user=self.teacher, organization=self.org)
        self.assertEqual(unbound.exam_category_locked["value"], "quiz")
        bound = ExamForm(
            self._data(title="Köhnə imtahan", exam_type_extended=""),
            instance=legacy,
            user=self.teacher,
            organization=self.org,
        )
        self.assertTrue(bound.is_valid(), bound.errors)
        self.assertEqual(bound.save(commit=False).exam_type_extended, "quiz")

    def test_teacher_editing_existing_final_is_not_locked(self):
        # Legacy final (müəllif müəllimdir): iki real seçim qalır → select qalır, dəyər qorunur.
        form = ExamForm(instance=self.final_exam, user=self.teacher, organization=self.org)
        self.assertIsNone(form.exam_category_locked)


class TrialOnlyCategoryRenderTests(_Base):
    def test_teacher_create_modal_renders_trial_pill_without_select(self):
        response = self._client_for(self.teacher).get(reverse("exams:create_exam") + "?modal=1")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("ew-category-pill", html)
        self.assertIn('data-ew-display="Sınaq"', html)
        self.assertNotIn('<select name="exam_type_extended"', html)
        self.assertInHTML(
            '<input type="hidden" name="exam_type_extended" id="id_exam_type_extended" value="quiz" '
            'data-ew-display="Sınaq">',
            html,
        )

    def test_teacher_edit_modal_renders_trial_pill(self):
        url = reverse("exams:edit_exam", kwargs={"slug": self.quiz_exam.slug}) + "?modal=1"
        response = self._client_for(self.teacher).get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("ew-category-pill", html)
        self.assertNotIn('<select name="exam_type_extended"', html)

    def test_exam_center_create_modal_keeps_select(self):
        response = self._client_for(self.exam_center).get(reverse("exams:create_exam") + "?modal=1")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn("ew-category-pill", html)
        self.assertIn('<select name="exam_type_extended"', html)
