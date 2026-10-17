"""Paket E (2026-10-17) — lab səhifələrinin `ems_ui` redizaynı: sorğu büdcəsi + tapılmış xətalar.

* `manage_blocks` hər blok üçün `block.questions` (3 sorğu) oxuyurdu (N+1) — indi blok/sual sayından asılı deyil;
* yaradan olmayan müəllim bloklar/önizləmə səhifəsini açanda `redirect(..., pk=...)` NoReverseMatch (500) verirdi —
  kurs paneli marşrutunun açarı `course_id`-dir;
* qiymətləndirilməmiş cavabın qiymət səhifəsi «anonim pəncərə»də `data-review-countdown="0"` yazırdı —
  `review_countdown.js` 0-da səhifəni hər saniyə yenidən yükləyirdi (sonsuz yenilənmə);
* lab səhifələri yeni dialoq/qabıq markup-ı ilə render olunur (Bootstrap `modal fade` yoxdur).
"""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.labs.models import LabAnswer, LabAssignment, LabBlock, LabQuestion, LabSubmission
from apps.labs.tests.test_course_tasks_fix_2026_09_28 import _LabFixture
from apps.labs.tests.test_views import _assign_user_to_org, _login_with_org


class ManageBlocksQueryBudgetTests(_LabFixture):
    def _blocks(self, lab, blocks, questions):
        for order in range(1, blocks + 1):
            block = LabBlock.objects.create(lab=lab, title=f"Blok {order}", order=order)
            for number in range(1, questions + 1):
                LabQuestion.objects.create(block=block, question_number=number, question_text=f"Sual {order}-{number}")

    def test_query_count_independent_of_block_and_question_count(self):
        lab = self._lab()
        self._blocks(lab, 1, 1)
        url = reverse("labs:manage_blocks", args=[lab.id])
        self.client.get(url)  # isti tur — sessiya/auth keşi sabitləşsin
        with CaptureQueriesContext(connection) as small:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        self._blocks(lab, 6, 4)
        with CaptureQueriesContext(connection) as large:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            len(small.captured_queries),
            len(large.captured_queries),
            "manage_blocks sorğu sayı blok/sual sayı ilə artmamalıdır (prefetch_related('questions'))",
        )
        html = response.content.decode("utf-8")
        self.assertIn("Sual 6-4", html)
        self.assertEqual(response.context["total_questions"], 1 + 6 * 4)

    def test_renders_design_system_markup_without_bootstrap_modals(self):
        lab = self._lab()
        self._blocks(lab, 2, 2)
        html = self.client.get(reverse("labs:manage_blocks", args=[lab.id])).content.decode("utf-8")
        for needle in ('id="addBlockModal"', 'id="editQuestionModal"', "ems-overlay--dialog", "data-lab-block-tab"):
            self.assertIn(needle, html)
        self.assertNotIn("modal fade modal-modern", html)
        self.assertNotIn("accordion-item", html)


class LabPermissionRedirectTests(_LabFixture):
    """Yaradan olmayan müəllim — 500 yox, kurs panelinə yönləndirmə."""

    def _other_teacher(self):
        from django.contrib.auth import get_user_model

        other = get_user_model().objects.create_user("pkge_other_t", "pkge_other_t@example.com", "StrongPass123!")
        _assign_user_to_org(other, self.organization, ProfileRole.TEACHER)
        _login_with_org(self.client, other, self.organization)
        return other

    def test_manage_blocks_and_preview_redirect_non_creator(self):
        lab = self._lab()
        self._other_teacher()
        dashboard = reverse("courses:course_dashboard", kwargs={"course_id": self.course.id})
        for name in ("labs:manage_blocks", "labs:preview_randomization"):
            response = self.client.get(reverse(name, args=[lab.id]))
            self.assertRedirects(response, dashboard, fetch_redirect_response=False)

    def test_questions_per_student_redirects_non_creator(self):
        lab = self._lab()
        self._other_teacher()
        response = self.client.post(
            reverse("labs:update_questions_per_student", args=[lab.id]), {"questions_per_student": 2}
        )
        self.assertEqual(response.status_code, 302)


class GradePageCountdownTests(_LabFixture):
    def test_ungraded_submission_has_no_zero_countdown_reload_loop(self):
        lab = self._lab()
        block = LabBlock.objects.create(lab=lab, title="B", order=1)
        question = LabQuestion.objects.create(block=block, question_number=1, question_text="Q1")
        assignment = LabAssignment.objects.create(lab=lab, student=self.a1)
        assignment.assigned_questions.add(question)
        submission = LabSubmission.objects.create(assignment=assignment, submission_text="x")
        LabAnswer.objects.create(
            lab=lab, question=question, student=self.a1, submission=submission, answer="cavab", is_draft=False
        )
        html = self.client.get(reverse("labs:grade_submission_page", args=[submission.id])).content.decode("utf-8")
        # Qiymətləndirilməmiş cavabda «qalan vaxt» yoxdur — geri sayım elementi render olunmamalıdır.
        self.assertNotIn('data-review-countdown="0"', html)
        self.assertIn('id="gradeForm"', html)
        self.assertIn("ems-banner", html)


class LabCrumbsTagTests(_LabFixture):
    def test_crumbs_course_lab_and_optional_tail(self):
        from apps.labs.templatetags.lab_filters import lab_crumbs

        lab = self._lab()
        crumbs = lab_crumbs(lab, "Bloklar", "labs:manage_blocks")
        self.assertEqual([c["label"] for c in crumbs], [self.course.title, lab.title, "Bloklar"])
        self.assertEqual(crumbs[1]["url"], reverse("labs:manage_blocks", args=[lab.id]))
        self.assertEqual(crumbs[2]["url"], "")
        self.assertEqual(len(lab_crumbs(lab)), 2)


def test_effective_max_file_size_matches_server_clamp_2026_10_18():
    """Review 2026-10-18: UI ipucu serverin tətbiq etdiyi həddi göstərir (köhnə 0 / 100 MB sətirlər)."""
    from apps.labs.models import Lab

    for raw, expected in ((0, 1), (25, 25), (100, 50), (None, 50)):
        lab = Lab(max_file_size_mb=raw)
        assert lab.effective_max_file_size_mb == expected
