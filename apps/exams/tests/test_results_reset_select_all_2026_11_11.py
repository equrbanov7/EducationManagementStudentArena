"""«Nəticəni sil (cəhdi sıfırla)» — «Səhifədəkilərin hamısını seç» + «Bütün N nəticəni seç» (sahib 2026-11-11).

«Bütün N nəticəni seç» səhifələmədən asılı deyil: forma ID siyahısı yox, ``select_scope=all_matching`` +
nəticələr səhifəsinin süzgəc sorğusu + təsdiq modalında göstərilən sayı göndərir. Cəhdləri server özü
müəyyən edir (bu imtahan + bu süzgəc) — klientin göndərdiyi ID-lər əhatəni genişləndirə bilməz. Səbəb
əvvəlki kimi məcburidir və hər cəhd üçün audit sətri yazılır; rol qapısı dəyişməyib.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.exams.domain.unit_scope_filters import unit_filter_value
from apps.exams.models import ExamAttempt
from apps.exams.services import attempt_reset, exam_attempt_purge
from apps.exams.tests.exam_pages_scale_fixture import ExamPagesScaleFixture
from apps.organizations.models import Membership
from core.rls import bypass_rls

User = get_user_model()
REASON = "Qrup səhvən köhnə variantla imtahan verib — nəticələr sıfırlanır"


class _ResetAllFixture(ExamPagesScaleFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.center_head = User.objects.create_user("rsa_center_head", "rsa_center_head@test.az", "pw")
        Membership.objects.create(
            user=cls.center_head,
            organization=cls.org,
            role=cls.org.roles.get(name="exam_center_head"),
            is_primary=True,
            is_active=True,
        )

    def _exam_with_attempts(self, title, *, groups=2, students_each=13):
        exam, questions, users, attempts = self._build(
            questions=4,
            groups=groups,
            students_each=students_each,
            answers_each=2,
            title=title,
            exam_type_extended="midterm",
        )
        return exam, users, attempts

    def _results_url(self, exam, **params):
        url = reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug})
        if params:
            from urllib.parse import urlencode

            url = f"{url}?{urlencode(params)}"
        return url

    def _reset(self, exam, data, *, user=None):
        with self.captureOnCommitCallbacks(execute=True):
            return self._client(user or self.center_head).post(
                reverse("exams:reset_exam_attempts", kwargs={"slug": exam.slug}), data
            )

    def _remaining(self, exam):
        with bypass_rls():
            return set(ExamAttempt.objects.filter(exam=exam).values_list("pk", flat=True))

    def _reset_audit_rows(self):
        with bypass_rls():
            return list(
                AuditLog.objects.filter(
                    resource_type=exam_attempt_purge.AUDIT_RESOURCE_TYPE, changes__verb=attempt_reset.RESET_VERB
                )
            )


class ResetSelectAllUiTests(_ResetAllFixture):
    def test_head_sees_header_checkbox_and_all_matching_button_with_count(self):
        exam, users, attempts = self._exam_with_attempts("ResetUi")
        response = self._client(self.center_head).get(self._results_url(exam))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("data-reset-page-all", html)
        self.assertIn("Səhifədəkilərin hamısını seç", html)
        self.assertIn("data-reset-all-matching", html)
        self.assertIn(f'data-total="{len(attempts)}"', html)
        self.assertIn(f"Bütün {len(attempts)} nəticəni seç", html)
        self.assertIn("data-reset-all-note", html)

    def test_all_matching_button_carries_the_current_filter(self):
        exam, users, attempts = self._exam_with_attempts("ResetUiFilter", groups=2, students_each=14)
        response = self._client(self.center_head).get(self._results_url(exam, status="submitted", per_page="12"))
        html = response.content.decode()
        self.assertIn('data-filter-query="status=submitted"', html)

    def test_single_page_has_no_all_matching_button_and_teacher_has_nothing(self):
        exam, users, attempts = self._exam_with_attempts("ResetUiSmall", groups=1, students_each=3)
        html = self._client(self.center_head).get(self._results_url(exam)).content.decode()
        self.assertIn("data-reset-page-all", html)
        self.assertNotIn("data-reset-all-matching", html)
        teacher_html = self._client(self.teacher).get(self._results_url(exam)).content.decode()
        self.assertNotIn("data-reset-page-all", teacher_html)
        self.assertNotIn("data-reset-all-matching", teacher_html)


class ResetAllMatchingScopeTests(_ResetAllFixture):
    def test_all_matching_resets_every_page_and_ignores_client_ids(self):
        exam, users, attempts = self._exam_with_attempts("ResetAll")
        other, _, other_attempts = self._exam_with_attempts("ResetAllOther", groups=1, students_each=2)
        self.assertGreater(len(attempts), 12)  # birdən çox səhifə

        response = self._reset(
            exam,
            {
                "select_scope": "all_matching",
                "filter_query": "",
                "expected_count": str(len(attempts)),
                "reason": REASON,
                # Klient başqa imtahanın cəhdini də «seçib» — server buna baxmır.
                "attempt_ids": [str(other_attempts[0].pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._remaining(exam), set())
        self.assertEqual(self._remaining(other), {attempt.pk for attempt in other_attempts})
        rows = self._reset_audit_rows()
        self.assertEqual(len(rows), len(attempts))
        self.assertEqual({row.resource_id for row in rows}, {str(attempt.pk) for attempt in attempts})
        for row in rows:
            self.assertEqual(row.user_id, self.center_head.pk)
            self.assertEqual(row.reason, REASON)

    def test_all_matching_respects_the_group_filter(self):
        exam, users, attempts = self._exam_with_attempts("ResetGroup", groups=2, students_each=13)
        with bypass_rls():
            first_unit = exam.allowed_units.order_by("slug").first()
        first_group_users = {user.pk for user in users[:13]}
        expected_left = {attempt.pk for attempt in attempts if attempt.user_id not in first_group_users}

        response = self._reset(
            exam,
            {
                "select_scope": "all_matching",
                "filter_query": f"group={unit_filter_value(first_unit.pk)}",
                "expected_count": "13",
                "reason": REASON,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._remaining(exam), expected_left)
        self.assertEqual(len(self._reset_audit_rows()), 13)

    def test_count_mismatch_refuses_and_deletes_nothing(self):
        exam, users, attempts = self._exam_with_attempts("ResetStale")
        response = self._reset(
            exam, {"select_scope": "all_matching", "filter_query": "", "expected_count": "5", "reason": REASON}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self._remaining(exam)), len(attempts))
        self.assertEqual(self._reset_audit_rows(), [])
        texts = " ".join(str(message) for message in get_messages(response.wsgi_request))
        self.assertIn("Siyahı dəyişib", texts)

    def test_reason_is_still_mandatory(self):
        exam, users, attempts = self._exam_with_attempts("ResetNoReason")
        response = self._reset(
            exam,
            {"select_scope": "all_matching", "filter_query": "", "expected_count": str(len(attempts)), "reason": " "},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self._remaining(exam)), len(attempts))
        self.assertEqual(self._reset_audit_rows(), [])

    def test_teacher_author_and_student_are_denied(self):
        exam, users, attempts = self._exam_with_attempts("ResetDenied", groups=1, students_each=3)
        for user in (self.teacher, self.student):
            with self.subTest(user=user.username):
                response = self._reset(
                    exam,
                    {"select_scope": "all_matching", "filter_query": "", "expected_count": "3", "reason": REASON},
                    user=user,
                )
                self.assertIn(response.status_code, (302, 403, 404))
                self.assertEqual(len(self._remaining(exam)), 3)
        self.assertEqual(self._reset_audit_rows(), [])

    def test_ticked_ids_are_still_scoped_to_the_exam(self):
        exam, users, attempts = self._exam_with_attempts("ResetIds", groups=1, students_each=3)
        other, _, other_attempts = self._exam_with_attempts("ResetIdsOther", groups=1, students_each=2)
        response = self._reset(
            exam, {"attempt_ids": [str(attempts[0].pk), str(other_attempts[0].pk)], "reason": REASON}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._remaining(exam), {attempt.pk for attempt in attempts[1:]})
        self.assertEqual(len(self._remaining(other)), 2)
