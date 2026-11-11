"""Sual bankı — toplu əməllər və cavablanmış sualın «yeni versiya» ilə dəyişdirilməsi (sahib 2026-11-11).

* «Bütün sualları deaktiv et / aktiv et» — silmədən, audit ilə;
* «Bütün N sualı seç» — ``select_scope=all_matching``: sualları server cari süzgəcdən özü müəyyən edir
  (klientin göndərdiyi ID siyahısına baxılmır, başqa imtahana keçə bilməz);
* «Seçilənləri sil» istifadə olunmuş suallarda dalana dirənmir — «deaktiv edilsin?» (``on_used=deactivate``);
* cavablanmış sualın redaktəsi köhnə sualı DƏYİŞMİR: yeni versiya yaranır, köhnəsi deaktiv olunur,
  keçmiş cəhdlərin cavabları və balı olduğu kimi qalır.
"""

from __future__ import annotations

from django.urls import reverse

from apps.audit.models import AuditLog
from apps.exams.models import ExamAnswer, ExamQuestion
from apps.exams.services import question_invariants, question_versioning
from apps.exams.services.result_calculation import calculate_test_attempt_result
from apps.exams.tests.exam_pages_scale_fixture import AJAX, ExamPagesScaleFixture
from core.rls import bypass_rls

PARTIAL = {"HTTP_X_QB_PARTIAL": "1"}


class _BankFixture(ExamPagesScaleFixture):
    def _bank_url(self, exam, **params):
        url = reverse("exams:teacher_questions_bank", kwargs={"slug": exam.slug})
        if params:
            from urllib.parse import urlencode

            url = f"{url}?{urlencode(params)}"
        return url

    def _post(self, exam, data, *, user=None, **extra):
        return self._client(user).post(self._bank_url(exam), data, **extra)

    def _active(self, exam):
        with bypass_rls():
            return set(exam.questions.filter(is_active=True).values_list("pk", flat=True))

    def _bulk_audit(self, exam):
        with bypass_rls():
            return list(
                AuditLog.objects.filter(
                    resource_type=question_invariants.AUDIT_RESOURCE, resource_id=str(exam.pk)
                ).order_by("created_at", "pk")
            )


class BulkAllTests(_BankFixture):
    def test_deactivate_all_then_activate_all_keeps_rows_and_is_audited(self):
        exam, questions, _, _ = self._build(questions=30, title="BulkAll", is_active=False)
        response = self._post(exam, {"bulk_action": "deactivate_all"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._active(exam), set())
        with bypass_rls():
            self.assertEqual(exam.questions.count(), 30)  # heç nə silinmir

        response = self._post(exam, {"bulk_action": "activate_all"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self._active(exam)), 30)

        rows = self._bulk_audit(exam)
        self.assertEqual([row.changes["verb"] for row in rows], ["deactivate", "activate"])
        for row in rows:
            self.assertEqual(row.user_id, self.teacher.pk)
            self.assertEqual(row.changes["count"], 30)
            self.assertEqual(row.changes["scope"], "all")
            self.assertEqual(row.changes["exam_slug"], exam.slug)

    def test_deactivate_all_on_published_exam_asks_before_unpublishing(self):
        exam, _, _, _ = self._build(questions=5, title="BulkAllActive")
        response = self._post(exam, {"bulk_action": "deactivate_all"}, **AJAX)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "exam_deactivation_required")
        self.assertEqual(len(self._active(exam)), 5)
        self.assertEqual(self._bulk_audit(exam), [])

        response = self._post(exam, {"bulk_action": "deactivate_all", "confirm_exam_deactivation": "1"}, **AJAX)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._active(exam), set())
        exam.refresh_from_db()
        self.assertFalse(exam.is_active)
        self.assertEqual(len(self._bulk_audit(exam)), 1)

    def test_student_and_foreign_teacher_cannot_run_bulk_actions(self):
        exam, _, _, _ = self._build(questions=4, title="BulkPerm", is_active=False)
        for user in (self.student, self.student_b):
            with self.subTest(user=user.username):
                response = self._post(exam, {"bulk_action": "deactivate_all"}, user=user)
                self.assertIn(response.status_code, (302, 403, 404))
                self.assertEqual(len(self._active(exam)), 4)
        self.assertEqual(self._bulk_audit(exam), [])

    def test_page_offers_bulk_all_and_select_all_matching(self):
        exam, _, _, _ = self._build(questions=30, title="BulkUi", is_active=False)
        html = self._client().get(self._bank_url(exam)).content.decode()
        self.assertIn('data-bulk-all="deactivate_all"', html)
        self.assertIn('data-bulk-all="activate_all"', html)
        self.assertIn('id="selectAllMatchingBtn"', html)
        self.assertIn('data-total="30"', html)
        self.assertIn("Bütün 30 sualı seç", html)
        self.assertIn('name="select_scope"', html)


class SelectAllMatchingScopeTests(_BankFixture):
    def test_all_matching_uses_the_server_side_filter_not_client_ids(self):
        exam, questions, _, _ = self._build(questions=30, title="ScopeA", is_active=False)
        other, other_questions, _, _ = self._build(questions=6, title="ScopeB", is_active=False)
        with bypass_rls():
            ExamQuestion.objects.filter(pk__in=[q.pk for q in questions[:10]]).update(language="en")

        # Süzgəc: yalnız «en» sualları. Klient başqa imtahanın və süzgəcdən kənar sualların ID-lərini göndərir.
        response = self._post(
            exam,
            {
                "bulk_action": "deactivate",
                "select_scope": "all_matching",
                "language": "en",
                "selected_question_ids": [str(other_questions[0].pk), str(questions[20].pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._active(exam), {q.pk for q in questions[10:]})
        self.assertEqual(len(self._active(other)), 6)

        row = self._bulk_audit(exam)[-1]
        self.assertEqual(row.changes["scope"], "all_matching")
        self.assertEqual(row.changes["filter"], {"language": "en"})
        self.assertEqual(row.changes["count"], 10)

    def test_all_matching_covers_every_page_of_a_search(self):
        exam, questions, _, _ = self._build(questions=40, title="ScopeSearch", is_active=False)
        marked = questions[5:20]  # 15 sual — səhifə ölçüsü 12-dir, seçim isə səhifədən asılı deyil
        with bypass_rls():
            for question in marked:
                ExamQuestion.objects.filter(pk=question.pk).update(text=f"Fotosintez haqqında sual {question.order}")
        page = self._client().get(self._bank_url(exam, q="fotosintez"))
        self.assertEqual(page.context["page_obj"].paginator.count, 15)
        self.assertEqual(len(page.context["page_obj"].object_list), 12)

        response = self._post(
            exam, {"bulk_action": "deactivate", "select_scope": "all_matching", "q": "fotosintez", "page": "1"}
        )
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            inactive = set(exam.questions.filter(is_active=False).values_list("pk", flat=True))
        self.assertEqual(inactive, {question.pk for question in marked})

    def test_without_scope_flag_only_posted_ids_of_this_exam_change(self):
        exam, questions, _, _ = self._build(questions=5, title="ScopeIds", is_active=False)
        other, other_questions, _, _ = self._build(questions=3, title="ScopeIdsOther", is_active=False)
        self._post(
            exam,
            {"bulk_action": "deactivate", "selected_question_ids": [str(questions[0].pk), str(other_questions[0].pk)]},
        )
        self.assertEqual(self._active(exam), {q.pk for q in questions[1:]})
        self.assertEqual(len(self._active(other)), 3)


class DeleteUsedQuestionsTests(_BankFixture):
    def _exam_with_answers(self, title):
        exam, questions, users, attempts = self._build(
            questions=8, groups=1, students_each=2, answers_each=3, title=title, is_active=False
        )
        return exam, questions, attempts

    def test_delete_offers_deactivation_for_used_questions_and_keeps_answers(self):
        exam, questions, attempts = self._exam_with_answers("UsedDelete")
        ids = [str(q.pk) for q in questions[:5]]  # ilk 3-ü cavablanıb, 2-si yox
        with bypass_rls():
            answers_before = ExamAnswer.objects.filter(attempt__in=attempts).count()

        response = self._post(exam, {"bulk_action": "delete", "selected_question_ids": ids}, **AJAX)
        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertEqual(payload["code"], "questions_have_answers")
        self.assertEqual((payload["used_count"], payload["unused_count"]), (3, 2))
        self.assertEqual(payload["fallback_field"], "on_used")
        self.assertIn("deaktiv", payload["confirm"]["body"])
        with bypass_rls():
            self.assertEqual(exam.questions.count(), 8)  # imtinada heç nə dəyişmir
        self.assertEqual(len(self._active(exam)), 8)

        response = self._post(
            exam, {"bulk_action": "delete", "selected_question_ids": ids, "on_used": "deactivate"}, **AJAX, **PARTIAL
        )
        self.assertEqual(response.status_code, 200)
        texts = " ".join(item["text"] for item in response.json()["messages"])
        self.assertIn("2 sual silindi", texts)
        self.assertIn("3 sual silinmədi", texts)
        with bypass_rls():
            remaining = set(exam.questions.values_list("pk", flat=True))
            self.assertEqual(remaining, {q.pk for q in questions[:3]} | {q.pk for q in questions[5:]})
            self.assertEqual(ExamAnswer.objects.filter(attempt__in=attempts).count(), answers_before)
        self.assertEqual(self._active(exam), {q.pk for q in questions[5:]})
        row = self._bulk_audit(exam)[-1]
        self.assertEqual(row.changes["verb"], "delete")
        self.assertEqual(row.changes["count"], 2)
        self.assertEqual(row.changes["kept_used_deactivated"], 3)

    def test_plain_form_delete_of_used_questions_still_refuses_with_explanation(self):
        exam, questions, _ = self._exam_with_answers("UsedDeletePlain")
        response = self._post(exam, {"bulk_action": "delete", "selected_question_ids": [str(questions[0].pk)]})
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            self.assertEqual(exam.questions.count(), 8)
        self.assertEqual(len(self._active(exam)), 8)


class QuestionVersioningTests(_BankFixture):
    def _edit_url(self, exam, question):
        return reverse("exams:edit_exam_question", kwargs={"slug": exam.slug, "question_id": question.pk}) + "?modal=1"

    def _payload(self, text):
        return {
            "modal": "1",
            "text": text,
            "answer_mode": "single",
            "language": "az",
            "option1_text": "Yeni A",
            "option2_text": "Yeni B",
            "option2_is_correct": "on",
            "option3_text": "Yeni C",
        }

    def _setup(self, title):
        exam, questions, users, attempts = self._build(
            questions=6, groups=1, students_each=2, answers_each=2, title=title
        )
        return exam, questions, attempts

    def _scores(self, attempts):
        with bypass_rls():
            return [
                (result.correct_count, result.wrong_count, str(result.score), str(result.max_score))
                for result in (calculate_test_attempt_result(attempt) for attempt in attempts)
            ]

    def test_editing_an_answered_question_creates_a_new_version_and_freezes_the_old_one(self):
        exam, questions, attempts = self._setup("Version")
        old = questions[0]
        with bypass_rls():
            old_options = list(old.options.order_by("id").values_list("id", "text", "is_correct"))
            answer_ids = set(ExamAnswer.objects.filter(question=old).values_list("pk", flat=True))
        scores_before = self._scores(attempts)
        self.assertTrue(answer_ids)

        page = self._client().get(self._edit_url(exam, old), **AJAX)
        self.assertContains(page, "data-qf-version-note")
        self.assertContains(page, "Dəyiş (yeni versiya)")
        self.assertContains(page, reverse("appeals:manage_appeals"))

        response = self._client().post(self._edit_url(exam, old), self._payload("Düzəldilmiş mətn"), **AJAX, **PARTIAL)
        self.assertEqual(response.status_code, 200, response.content[:400])
        payload = response.json()
        self.assertTrue(payload["new_version"])
        self.assertEqual(payload["replaced_id"], old.pk)
        self.assertNotEqual(payload["question_id"], old.pk)
        self.assertIn("yeni versiya", payload["message"])

        with bypass_rls():
            old.refresh_from_db()
            new = ExamQuestion.objects.get(pk=payload["question_id"])
            # Köhnə sual: mətn və variantlar OLDUĞU KİMİ, yalnız deaktiv.
            self.assertFalse(old.is_active)
            self.assertEqual(old.text, "Sual mətni nömrə 1")
            self.assertEqual(list(old.options.order_by("id").values_list("id", "text", "is_correct")), old_options)
            # Yeni versiya: aktiv, eyni sıra, köhnəyə bağlı, öz variantları ilə.
            self.assertTrue(new.is_active)
            self.assertEqual(new.replaces_id, old.pk)
            self.assertEqual((new.exam_id, new.order, new.text), (exam.pk, old.order, "Düzəldilmiş mətn"))
            self.assertEqual(
                list(new.options.order_by("label").values_list("label", "text", "is_correct")),
                [("A", "Yeni A", False), ("B", "Yeni B", True), ("C", "Yeni C", False)],
            )
            # Keçmiş cavablar köhnə suala bağlı qalır; yeni sualın cavabı yoxdur.
            self.assertEqual(set(ExamAnswer.objects.filter(question=old).values_list("pk", flat=True)), answer_ids)
            self.assertFalse(ExamAnswer.objects.filter(question=new).exists())
            audit = AuditLog.objects.get(resource_type=question_versioning.AUDIT_RESOURCE, resource_id=str(exam.pk))
        self.assertEqual(self._scores(attempts), scores_before)  # keçmiş cəhdlərin balı dəyişmir
        self.assertEqual(audit.user_id, self.teacher.pk)
        self.assertEqual(audit.changes["old_question_id"], old.pk)
        self.assertEqual(audit.changes["new_question_id"], new.pk)
        self.assertEqual(audit.changes["answers_kept"], len(answer_ids))
        exam.refresh_from_db()
        self.assertTrue(exam.is_active)  # aktiv imtahan aktiv sualsız qalmır

    def test_editing_an_unanswered_question_stays_in_place(self):
        exam, questions, _ = self._setup("VersionInPlace")
        target = questions[5]  # cavablanmayıb
        page = self._client().get(self._edit_url(exam, target), **AJAX)
        self.assertNotContains(page, "data-qf-version-note")
        response = self._client().post(self._edit_url(exam, target), self._payload("Yerində dəyişdi"), **AJAX)
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertFalse(response.json()["new_version"])
        with bypass_rls():
            target.refresh_from_db()
            self.assertEqual(target.text, "Yerində dəyişdi")
            self.assertTrue(target.is_active)
            self.assertEqual(exam.questions.count(), 6)
            self.assertFalse(AuditLog.objects.filter(resource_type=question_versioning.AUDIT_RESOURCE).exists())

    def test_invalid_versioned_edit_changes_nothing(self):
        exam, questions, _ = self._setup("VersionInvalid")
        old = questions[0]
        bad = self._payload("Yarımçıq")
        bad["option1_is_correct"] = "on"  # tək cavab rejimində iki düzgün variant — forma rədd edir
        response = self._client().post(self._edit_url(exam, old), bad, **AJAX)
        self.assertEqual(response.status_code, 400)
        self.assertIn("data-qf-version-note", response.json()["html"])
        with bypass_rls():
            old.refresh_from_db()
            self.assertTrue(old.is_active)
            self.assertEqual(old.text, "Sual mətni nömrə 1")
            self.assertEqual(exam.questions.count(), 6)

    def test_student_cannot_create_a_version(self):
        exam, questions, _ = self._setup("VersionPerm")
        response = self._client(self.student).post(self._edit_url(exam, questions[0]), self._payload("Hack"), **AJAX)
        self.assertIn(response.status_code, (302, 403, 404))
        with bypass_rls():
            self.assertEqual(exam.questions.count(), 6)
            self.assertFalse(ExamQuestion.objects.filter(text="Hack").exists())

    def test_bank_card_labels_answered_questions(self):
        exam, questions, _ = self._setup("VersionCard")
        response = self._client().get(self._bank_url(exam, sort="oldest"))
        by_id = {question.id: question for question in response.context["page_obj"].object_list}
        self.assertTrue(by_id[questions[0].pk].edit_creates_version)
        self.assertFalse(by_id[questions[5].pk].edit_creates_version)
        html = response.content.decode()
        self.assertIn("Dəyiş (yeni versiya)", html)
        self.assertIn("Cavablanıb", html)


class BankLiveFragmentTests(_BankFixture):
    def test_partial_response_is_only_the_live_regions(self):
        exam, _, _, _ = self._build(questions=30, title="Live", is_active=False)
        full = self._client().get(self._bank_url(exam))
        partial = self._client().get(self._bank_url(exam, page=2), **PARTIAL)
        self.assertEqual(partial.status_code, 200)
        html = partial.content.decode()
        self.assertNotIn("<html", html)
        self.assertNotIn("questionSearchForm", html)  # süzgəc forması (fokus) yenidən çəkilmir
        for region in ("kpis", "export", "quality", "list", "danger"):
            self.assertIn(f'data-qb-live="{region}"', html)
            self.assertIn(f'data-qb-live="{region}"', full.content.decode())
        self.assertEqual(partial.context["page_obj"].number, 2)
        self.assertLess(len(partial.content), len(full.content) * 0.7)
        self.assertIn("X-QB-Partial", partial["Vary"])

    def test_partial_mutation_returns_messages_instead_of_queueing_them(self):
        exam, questions, _, _ = self._build(questions=5, title="LiveMsg", is_active=False)
        client = self._client()
        response = client.post(
            self._bank_url(exam),
            {"bulk_action": "deactivate", "selected_question_ids": [str(questions[0].pk)], "page": "1"},
            **AJAX,
            **PARTIAL,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual([item["level"] for item in payload["messages"]], ["success"])
        # Mesaj artıq oxunub — növbəti tam səhifədə təkrar görünmür.
        follow = client.get(payload["redirect_url"])
        self.assertEqual(list(follow.context["messages"]), [])
