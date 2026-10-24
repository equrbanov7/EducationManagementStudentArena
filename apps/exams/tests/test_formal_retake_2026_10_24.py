"""Midterm / final — nəticələr səhifəsindən BİRBAŞA əlavə cəhd yoxdur, rəsmi «Yenidən imtahan cəhdi» (2026-10-24).

* ``grant_extra_attempt`` / ``grant_extra_attempt_group`` midterm və finalda imtina edir (403 / xəta mesajı) —
  köhnə forma və ya əl ilə POST rəsmi axından (əsas, əmr, sənəd, qeyd) yan keçə bilmir;
* quiz kimi digər imtahanlarda davranış dəyişmir;
* nəticələr səhifəsinin düymələri İmtahan Mərkəzi üçün ``?section=exam-chance`` səhifəsinə ön-doldurulmuş
  keçid verir (imtahan + tələbə / qrup axtarışı), qalan istifadəçilər üçün yalnız kilid qeydi.
"""

from __future__ import annotations

from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from apps.exams.models import ExamAttempt, StudentExamAttemptGrant, StudentGroup
from apps.exams.services.formal_retake import formal_retake_url, requires_formal_retake
from apps.exams.tests.test_second_chance import _Base

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class FormalRetakeEndpointTests(_Base):
    def _teacher_exam(self, category):
        return self._make_exam(category, author=self.teacher, title=f"FR {category}")

    def test_requires_formal_retake_only_for_midterm_and_final(self):
        self.assertTrue(requires_formal_retake(self._teacher_exam("midterm")))
        self.assertTrue(requires_formal_retake(self._teacher_exam("final")))
        self.assertFalse(requires_formal_retake(self._teacher_exam("quiz")))
        self.assertFalse(requires_formal_retake(self._make_exam(None, author=self.teacher, title="FR none")))

    def test_individual_grant_refused_for_midterm_and_final(self):
        client = self._client_for(self.teacher)
        for category in ("midterm", "final"):
            with self.subTest(category=category):
                exam = self._teacher_exam(category)
                url = reverse("exams:grant_extra_attempt", args=[exam.slug])
                response = client.post(url, {"student_id": str(self.student.pk)}, **AJAX)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["error"], "formal_retake_required")
                response = client.post(url, {"student_id": str(self.student.pk)})
                self.assertEqual(response.status_code, 302)
                self.assertTrue(any("Yenidən imtahan cəhdi" in str(m) for m in get_messages(response.wsgi_request)))
                self.assertFalse(StudentExamAttemptGrant.objects.filter(exam=exam).exists())

    def test_group_grant_refused_for_midterm(self):
        exam = self._teacher_exam("midterm")
        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="FR-1")
        group.students.add(self.student)
        response = self._client_for(self.teacher).post(
            reverse("exams:grant_extra_attempt_group", args=[exam.slug]), {"group_id": str(group.pk)}, **AJAX
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(StudentExamAttemptGrant.objects.filter(exam=exam).exists())

    def test_quiz_keeps_direct_grant(self):
        exam = self._teacher_exam("quiz")
        response = self._client_for(self.teacher).post(
            reverse("exams:grant_extra_attempt", args=[exam.slug]), {"student_id": str(self.student.pk)}, **AJAX
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(StudentExamAttemptGrant.objects.get(exam=exam, student=self.student).extra_attempts, 1)


class FormalRetakeResultsPageTests(_Base):
    def _results(self, user, exam):
        ExamAttempt.objects.create(
            user=self.student, exam=exam, attempt_number=1, status="submitted", finished_at=timezone.now()
        )
        response = self._client_for(user).get(reverse("exams:teacher_exam_results", args=[exam.slug]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_formal_url_prefills_exam_and_student(self):
        exam = self._make_exam("final")
        url = formal_retake_url(exam, student=self.student)
        self.assertTrue(url.startswith(reverse("accounts:profile") + "?"))
        self.assertIn("section=exam-chance", url)
        self.assertIn(f"chance_exam={exam.pk}", url)
        self.assertIn(f"chance_student={self.student.pk}", url)
        self.assertNotIn(self.student.username, url)  # anonim yoxlama pəncərəsində ad sızmır
        self.assertIn("chance_student_q=FR-9", formal_retake_url(exam, group_name="FR-9"))

    def test_midterm_results_link_to_exam_chance_for_center(self):
        exam = self._make_exam("midterm", title="FR midterm nəticə")
        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="FR-2")
        group.students.add(self.student)
        exam.allowed_groups.add(group)
        page = self._results(self.center, exam)
        self.assertNotIn(reverse("exams:grant_extra_attempt", args=[exam.slug]), page)
        self.assertNotIn(reverse("exams:grant_extra_attempt_group", args=[exam.slug]), page)
        self.assertIn(
            formal_retake_url(exam, student=self.student).replace("&", "&amp;"), page
        )  # tələbə düyməsi → rəsmi səhifə
        self.assertIn('name="chance_exam" value="%s"' % exam.pk, page)  # qrup forması (GET) imtahanı ön-doldurur
        self.assertIn('name="chance_student_q"', page)
        self.assertIn('<option value="FR-2">', page)

    def test_midterm_results_show_lock_for_teacher(self):
        exam = self._make_exam("midterm", author=self.teacher, title="FR midterm müəllim")
        page = self._results(self.teacher, exam)
        self.assertNotIn(reverse("exams:grant_extra_attempt", args=[exam.slug]), page)
        self.assertNotIn("section=exam-chance", page)
        self.assertIn("etr-formal-note", page)

    def test_quiz_results_keep_direct_form(self):
        exam = self._make_exam("quiz", author=self.teacher, title="FR quiz")
        page = self._results(self.teacher, exam)
        self.assertIn(reverse("exams:grant_extra_attempt", args=[exam.slug]), page)
        self.assertNotIn("section=exam-chance", page)
