"""Paket C (2026-10-17): sual göndərişi səhifələrinin ems_ui redizaynı + sorğu büdcəsi.

* Müəllim detalı · kafedra baxışı · İmtahan Mərkəzi baxışı: ortaq başlıq (status nişanı, mərhələ zolağı,
  «növbəti addım» lenti, KPI), profil örtüyü (mərkəz baxışı əvvəl qabıqdan kənar idi), inline CSS/JS yoxdur.
* Status mətni həqiqi statusdan gəlir — ``center_review`` əvvəl «Geri qaytarılıb» görünürdü.
* Sorğu sayı sual sayından asılı deyil; redaktə olunmayan detal da lazy siyahıdır.
* «Yazılı sual bankı» səhifəsi blok başına sorğu atmır (N+1 düzəlişi).
* «Sual təsdiqi» bölməsi ems_ui cədvəli + KPI filtrləri ilə; GET parametr adları dəyişməyib.
"""

import re
from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone, translation

from apps.exams.models import Exam, ExamQuestion, QuestionBlock
from apps.exams.services.question_chair_review import chair_approve, chair_request_revision
from apps.exams.services.question_submission import accept_submission
from apps.exams.tests.test_question_submission import _Base


def _text(count):
    rows = []
    for index in range(1, count + 1):
        rows.append(f"{index}. Sual {index}: $x^{index}$ nədir?")
        rows.extend(f"{'*' if pos == 0 else ''}{label}) variant {index}{label}" for pos, label in enumerate("ABCDE"))
    return "\n".join(rows) + "\n"


def _queries(client, url):
    client.get(url)  # isinmə: şablon keşi, icazə keşləri
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200, response.status_code
    return len(ctx.captured_queries), response.content.decode()


def _body(html):
    return html.split('class="qsx', 1)[1].split("</main>", 1)[0]


class SubmissionPagesMarkupTests(_Base):
    def assertModernShell(self, html):
        self.assertIn("ems-steps", html)
        self.assertIn("ems-kpis", html)
        self.assertIn("qsx-next", html)
        self.assertIn("exams/css/question_submission_page.css", html)
        self.assertIn("profile-main", html)  # profil örtüyü (sol sidebar qalır)
        for legacy in ("question_submission_ui.css", "question_submission_chain.css", "teacher_questions_bank/_part1"):
            self.assertNotIn(legacy, html)
        body = _body(html)
        self.assertNotIn("<style", body)
        self.assertNotIn(" onclick=", body)
        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)(?![^>]*application/(ld\+)?json)", body))
        self.assertNotIn(' style="', body.replace('class="ems-bar__fill" style=', ""))

    def test_center_review_inside_shell_with_true_status(self):
        submission = self._to_center(self._submission(title="Mərkəz UI"))
        with translation.override("az"):
            _count, html = _queries(
                self._client_for(self.exam_center), reverse("exams:question_submission_review", args=[submission.id])
            )
        self.assertModernShell(html)
        self.assertIn("İmtahan Mərkəzi baxır", html)
        self.assertNotIn("Geri qaytarılıb", html)
        # Qərar formunun POST müqaviləsi + JS çəngəlləri.
        for hook in ('name="decision"', 'name="bank_id"', 'name="new_bank_name"', 'name="note"', "js-qsubr-form"):
            self.assertIn(hook, html)
        self.assertIn('id="qsubDecision"', html)

    def test_chair_review_uses_reason_dialog_with_hooks(self):
        submission = self._submission(title="Kafedra UI")
        with translation.override("az"):
            _count, html = _queries(
                self._client_for(self.chair_head),
                reverse("exams:question_submission_chair_review", args=[submission.id]),
            )
        self.assertModernShell(html)
        for hook in (
            "data-qchair",
            "data-qchair-form",
            "data-qchair-dialog",
            "data-qchair-confirm",
            "data-qchair-counter",
        ):
            self.assertIn(hook, html)
        self.assertIn('class="ems-overlay ems-overlay--dialog qchair-dialog"', html)
        self.assertIn('data-qchair-action="approve"', html)
        self.assertIn("Qərarınız gözlənilir", html)

    def test_teacher_detail_states(self):
        revision = self._submission(title="Düzəliş UI")
        chair_request_revision(revision, actor=self.chair_head, reason="3-cü sual düzəldilməlidir, cavab işarəsizdir.")
        with translation.override("az"):
            _count, html = _queries(
                self._client_for(self.teacher), reverse("exams:question_submission_detail", args=[revision.id])
            )
        self.assertModernShell(html)
        self.assertIn("qsubd-verdict--rejected", html)
        self.assertIn('href="#qsubEdit"', html)
        self.assertIn('id="qsubEdit"', html)
        self.assertIn("js-qsub-delete-form", html)
        # Profil örtüyündə workbench başlığı H2-dir (qabıq H1-i verir).
        self.assertIn('class="ems-header__title wb-head__title"', html)
        self.assertIn('id="totalErrors"', html)
        self.assertIn('data-filter-trigger="has-error"', html)

        accepted = self._to_center(self._submission(title="Qəbul UI"))
        accept_submission(accepted, reviewer=self.exam_center, new_bank_name="UI bankı")
        with translation.override("az"):
            _count, html = _queries(
                self._client_for(self.teacher), reverse("exams:question_submission_detail", args=[accepted.id])
            )
        self.assertModernShell(html)
        self.assertIn("qsubd-verdict--accepted", html)
        self.assertIn("js-qsubq", html)  # redaktə olunmayan detal lazy siyahıdır
        self.assertNotIn("js-qsub-delete-form", html)


class SubmissionPagesQueryBudgetTests(_Base):
    """Sorğu sayı sual sayından asılı deyil və sabit büdcədədir (ölçü: 2026-10-17)."""

    BUDGET = {"detail_edit": 27, "detail_view": 23, "chair": 27, "center": 23}

    def _pair(self, make, client, url_name):
        small, large = make(3), make(30)
        count_small, _ = _queries(client, reverse(url_name, args=[small.id]))
        count_large, _ = _queries(client, reverse(url_name, args=[large.id]))
        self.assertEqual(count_small, count_large, "sorğu sayı sual sayı ilə böyüyür (N+1)")
        return count_large

    def test_teacher_detail_budget(self):
        teacher = self._client_for(self.teacher)
        edit = self._pair(
            lambda n: self._submission(raw_text=_text(n), title=f"E{n}"), teacher, "exams:question_submission_detail"
        )
        self.assertLessEqual(edit, self.BUDGET["detail_edit"])

        def accepted(n):
            submission = self._to_center(self._submission(raw_text=_text(n), title=f"A{n}"))
            accept_submission(submission, reviewer=self.exam_center, new_bank_name=f"Bank {n}")
            return submission

        view = self._pair(accepted, teacher, "exams:question_submission_detail")
        self.assertLessEqual(view, self.BUDGET["detail_view"])

    def test_chair_and_center_budget(self):
        chair = self._pair(
            lambda n: self._submission(raw_text=_text(n), title=f"C{n}"),
            self._client_for(self.chair_head),
            "exams:question_submission_chair_review",
        )
        self.assertLessEqual(chair, self.BUDGET["chair"])

        def at_center(n):
            submission = self._submission(raw_text=_text(n), title=f"M{n}")
            chair_approve(submission, actor=self.chair_head, note="")
            return submission

        center = self._pair(at_center, self._client_for(self.exam_center), "exams:question_submission_review")
        self.assertLessEqual(center, self.BUDGET["center"])


class WrittenBankBuilderTests(_Base):
    def _written(self, blocks):
        exam = Exam.objects.create(
            title=f"Yazılı {blocks}",
            author=self.teacher,
            organization=self.org,
            exam_type="written",
            is_active=False,
            start_datetime=timezone.now() + timedelta(days=1),
            end_datetime=timezone.now() + timedelta(days=2),
        )
        for order in range(blocks):
            block = QuestionBlock.objects.create(exam=exam, name=f"Blok {order}", order=order + 1)
            for index in (2, 1):  # tərs sıra ilə yaradılır — çıxış `order`-ə görə olmalıdır
                ExamQuestion.objects.create(exam=exam, block=block, order=index, text=f"B{order} sual {index}")
        return exam

    def test_no_query_per_block_and_order_kept(self):
        client = self._client_for(self.teacher)
        few, _ = _queries(client, reverse("exams:create_question_bank", args=[self._written(1).slug]))
        many, html = _queries(client, reverse("exams:create_question_bank", args=[self._written(6).slug]))
        self.assertEqual(few, many)
        self.assertLess(html.index("1. B0 sual 1"), html.index("2. B0 sual 2"))
        self.assertIn("etp-head", html)
        self.assertNotIn("btn-back-main", html)


class ChairSectionTests(_Base):
    def test_section_uses_ems_table_and_kpi_filters(self):
        self._submission(title="Bölmə dəsti")
        url = f"{reverse('accounts:profile')}?section=question-chair-review"
        with translation.override("az"):
            response = self._client_for(self.chair_head).get(url)
        html = response.content.decode()
        section = html.split('data-profile-section-panel="question-chair-review"', 1)[1].split("</section>", 1)[0]
        self.assertIn("ems-table", section)
        self.assertIn('data-ems-kpi-filter="submitted_to_chair"', section)
        for name in ("qchair_q", "qchair_status", "qchair_kind", "qchair_teacher"):
            self.assertIn(f'name="{name}"', section)
        self.assertIn("Bölmə dəsti", section)
        self.assertIn("question_chair_review_section.js", section)
        self.assertNotIn("qsubs-", section)


class DetailDecisionLinkTests(_Base):
    """Qərar açarı olan mərkəz istifadəçisi gözləyən göndərişin DETALINDA «yalnız baxış» yox,
    baxış (review) səhifəsinə keçid görür; açarsız işçi yalnız-oxu mətnini görür."""

    def test_center_head_gets_review_link_on_pending_detail(self):
        submission = self._to_center(self._submission(title="Detal qərar keçidi"))
        url = reverse("exams:question_submission_detail", args=[submission.id])
        review_url = reverse("exams:question_submission_review", args=[submission.id])
        with translation.override("az"):
            html = self._client_for(self.exam_center).get(url).content.decode()
        self.assertIn(f'href="{review_url}"', html)
        self.assertIn("Qərarınız gözlənilir", html)
        self.assertNotIn("Yalnız baxış:", html)

    def test_center_staff_without_key_sees_read_only_text(self):
        from django.contrib.auth import get_user_model

        from apps.accounts.models import ProfileRole
        from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org

        staff = get_user_model().objects.create_user("qs_center_staff", "qs_center_staff@test.az", PASSWORD)
        _assign_user_to_org(staff, self.org, ProfileRole.MEMBER, "exam_center_staff")
        submission = self._to_center(self._submission(title="Detal yalnız baxış"))
        url = reverse("exams:question_submission_detail", args=[submission.id])
        review_url = reverse("exams:question_submission_review", args=[submission.id])
        with translation.override("az"):
            response = self._client_for(staff).get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Yalnız baxış:", html)
        self.assertNotIn(f'href="{review_url}"', html)


class ChairApprovedFilterTests(_Base):
    def test_approved_kpi_count_matches_click_filter(self):
        submitted = self._submission(title="Hələ kafedrada")
        approved = self._submission(title="Təsdiq, mərkəzdə")
        chair_approve(approved, actor=self.chair_head, note="")
        later = self._submission(title="Təsdiq, sonra qəbul")
        chair_approve(later, actor=self.chair_head, note="")
        accept_submission(later, reviewer=self.exam_center, new_bank_name="Filtr bankı")
        url = f"{reverse('accounts:profile')}?section=question-chair-review&qchair_status=chair_approved"
        html = self._client_for(self.chair_head).get(url).content.decode()
        section = html.split('data-profile-section-panel="question-chair-review"', 1)[1].split("</section>", 1)[0]
        self.assertIn("Təsdiq, mərkəzdə", section)
        self.assertIn("Təsdiq, sonra qəbul", section)
        self.assertNotIn(submitted.title, section)
