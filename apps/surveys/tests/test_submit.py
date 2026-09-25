"""Tələbə axını — forma, server yoxlaması, ikiqat göndəriş, irəliləyiş, anonim yazı."""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from apps.surveys.constants import CampaignStatus, Section
from apps.surveys.models import SurveyAnswer, SurveyCampaign, SurveyReceipt, SurveyResponse
from apps.surveys.services.templates import template_questions
from core.rls import bypass_rls

from .factories import build_world, client_for, close_all, likert_payload, member, open_campaign


class SubmitFlowTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svsub", students=2)
        close_all(cls.w)
        cls.campaign = open_campaign(cls.w)
        with bypass_rls():
            cls.teacher_questions = template_questions(cls.campaign.template, section=Section.TEACHER)
            cls.general_questions = template_questions(cls.campaign.template, section=Section.GENERAL)
            cls.rector = member(cls.w["org"], "svsub_rector", "rector")

    def setUp(self):
        self.student = self.w["students"][0]
        self.client = client_for(self.w["org"], self.student)

    def _url(self, offering, teacher):
        return reverse("surveys:teacher", args=[self.campaign.pk, offering.pk, teacher.pk])

    def test_home_lists_targets_with_progress_and_privacy_notice(self):
        response = self.client.get(reverse("surveys:home"))
        self.assertEqual(response.status_code, 200)
        block = response.context["blocks"][0]
        self.assertEqual((block["done"], block["total"]), (0, 4))
        self.assertContains(response, "Riyaziyyat")
        self.assertContains(response, 'class="svy-privacy"')
        self.assertContains(response, reverse("surveys:defer"))  # möhlət müddəti daxilində

    def test_form_renders_accessible_controls(self):
        response = self.client.get(self._url(self.w["off_math"], self.w["teacher_a"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="radio" name="q_clarity" value="5"')
        self.assertContains(response, 'name="q_overall" value="10"')
        self.assertContains(response, 'data-svy-counter="q_strengths-count"')
        self.assertNotContains(response, 'style="')
        self.assertNotContains(response, "<script>")

    def test_missing_required_answer_is_rejected_and_nothing_is_written(self):
        data = likert_payload(self.teacher_questions)
        data.pop("q_clarity")
        response = self.client.post(self._url(self.w["off_math"], self.w["teacher_a"]), data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("clarity", response.context["errors"])
        self.assertFalse(SurveyReceipt.objects.exists())
        self.assertFalse(SurveyResponse.objects.exists())

    def test_out_of_range_and_too_long_text_are_rejected(self):
        data = likert_payload(self.teacher_questions)
        data["q_clarity"] = "7"
        data["q_improve"] = "x" * 1501
        response = self.client.post(self._url(self.w["off_math"], self.w["teacher_a"]), data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.context["errors"]), {"clarity", "improve"})

    def test_valid_submit_writes_anonymous_response_and_moves_on(self):
        data = likert_payload(self.teacher_questions, score=5, overall=9, text="Çox aydın izah edir.")
        response = self.client.post(self._url(self.w["off_math"], self.w["teacher_a"]), data)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/sorgu/{self.campaign.pk}/", response["Location"])
        receipt = SurveyReceipt.objects.get()
        self.assertEqual((receipt.student_id, receipt.teacher_id), (self.student.pk, self.w["teacher_a"].pk))
        self.assertEqual(receipt.teacher_department_id, self.w["chair_a"].pk)
        answer_row = SurveyResponse.objects.get()
        self.assertEqual(answer_row.teacher_id, self.w["teacher_a"].pk)
        self.assertEqual(answer_row.subject_id, self.w["math"].pk)
        self.assertEqual(answer_row.group_id, self.w["group"].pk)
        self.assertEqual(answer_row.teacher_department_id, self.w["chair_a"].pk)
        self.assertEqual(answer_row.faculty_id, self.w["faculty"].pk)
        self.assertEqual(answer_row.course_year, 2)
        self.assertEqual(SurveyAnswer.objects.filter(response=answer_row).count(), 17)  # 15 bal + 2 mətn
        self.assertEqual(SurveyAnswer.objects.get(response=answer_row, question__code="overall").score, 9)

    def test_double_submit_creates_no_second_response(self):
        url = self._url(self.w["off_math"], self.w["teacher_a"])
        data = likert_payload(self.teacher_questions)
        self.client.post(url, data)
        second = self.client.post(url, data)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(second["Location"], reverse("surveys:home"))
        self.assertEqual(SurveyReceipt.objects.count(), 1)
        self.assertEqual(SurveyResponse.objects.count(), 1)

    def test_foreign_target_is_refused(self):
        other = member(self.w["org"], "svsub_other_teacher", "teacher")
        response = self.client.post(self._url(self.w["off_math"], other), likert_payload(self.teacher_questions))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SurveyResponse.objects.exists())

    def test_full_flow_ends_on_thanks_and_unlocks_cabinet(self):
        pairs = (
            (self.w["off_math"], self.w["teacher_a"]),
            (self.w["off_math"], self.w["teacher_c"]),
            (self.w["off_phys"], self.w["teacher_b"]),
        )
        self.assertEqual(self.client.get("/accounts/profile/").status_code, 302)
        for offering, teacher in pairs:
            self.client.post(self._url(offering, teacher), likert_payload(self.teacher_questions))
        final = self.client.post(
            reverse("surveys:general", args=[self.campaign.pk]), likert_payload(self.general_questions, text="Wi-Fi")
        )
        self.assertEqual(final["Location"], reverse("surveys:thanks"))
        self.assertEqual(SurveyReceipt.objects.filter(student=self.student).count(), 4)
        general = SurveyResponse.objects.get(scope=Section.GENERAL)
        self.assertIsNone(general.teacher_id)
        self.assertEqual(general.group_id, None)  # tələbənin akademik qeydi yoxdur → snapshot boş
        self.assertEqual(self.client.get("/accounts/profile/").status_code, 200)

    def test_closed_campaign_refuses_submission(self):
        SurveyCampaign.objects.filter(pk=self.campaign.pk).update(status=CampaignStatus.CLOSED)
        response = self.client.post(
            self._url(self.w["off_math"], self.w["teacher_a"]), likert_payload(self.teacher_questions)
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SurveyResponse.objects.exists())

    def test_view_as_cannot_submit_on_behalf_of_student(self):
        client = client_for(self.w["org"], self.rector)
        client.post(reverse("accounts:view_as_start"), {"user_id": self.student.pk})
        response = client.post(
            self._url(self.w["off_math"], self.w["teacher_a"]), likert_payload(self.teacher_questions)
        )
        self.assertIn(response.status_code, (302, 403))
        self.assertFalse(SurveyResponse.objects.exists())
        self.assertFalse(SurveyReceipt.objects.exists())

    def test_staff_cannot_open_student_pages(self):
        client = client_for(self.w["org"], self.w["teacher_a"])
        self.assertEqual(client.get(reverse("surveys:home")).status_code, 403)
