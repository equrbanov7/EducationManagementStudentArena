"""2026-10-13 (gecə) — imtahan mərkəzinin qərar modalı: müqayisə, tarixçə, sorğu büdcəsi, IDOR.

* tələbənin cavabı ↔ açar ÇATDIRILMA snapshot-undan göstərilir (müəllif sonradan sualı/variantı
  redaktə etsə də mərkəz tələbənin gördüyünü görür); dondurulmuş seçim canlı seçimdən üstündür;
* aktiv açar düzəlişi kartı və tarixçə (göndərilmə → qərar → bal) modalda görünür;
* sorğu sayı item sayından asılı deyil (N+1 yoxdur);
* tələbə qərar modalını aça bilmir, başqasının apellyasiyası «yoxdur» kimi cavablanır;
  dekan/koordinator (oxu scope-u) yalnız-oxu detal görür.
"""

from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.appeals.services import accept_appeal_item
from apps.appeals.tests.test_key_correction_2026_10_13 import _AJAX, _KeyFixSetup
from apps.exams.models import ExamAnswer, ExamQuestion, ExamQuestionOption


class ReviewComparisonTests(_KeyFixSetup):
    def _review(self, user=None):
        return self._client(user or self.head).get(
            reverse("appeals:review_appeal", args=[self.item.appeal_id]) + "?fragment=1", **_AJAX
        )

    def test_comparison_uses_delivered_snapshot_not_live_question(self):
        # İmtahandan SONRA müəllif variantı redaktə edib və açarı dəyişib.
        self.q1_a.text = "REDAKTƏ OLUNMUŞ"
        self.q1_a.is_correct = False
        self.q1_a.save(update_fields=["text", "is_correct"])
        self.q1_b.is_correct = True
        self.q1_b.save(update_fields=["is_correct"])
        response = self._review()
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "REDAKTƏ OLUNMUŞ")
        item = response.context["items"][0]
        options = {opt.id: opt for opt in item.delivered.options}
        self.assertTrue(options[self.q1_a.id].is_correct)  # imtahan anındakı açar
        self.assertTrue(options[self.q1_b.id].is_selected)  # dondurulmuş seçim
        self.assertEqual(item.selected_option_ids, {self.q1_b.id})
        self.assertTrue(item.can_correct_key)
        self.assertContains(response, "data-key-fix-form")

    def test_active_key_correction_and_timeline_are_shown(self):
        self._apply()
        with self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(self.item, reviewer=self.head, response_text="Haqlıdır.")
        response = self._review()
        self.assertContains(response, "data-key-fix-card")
        self.assertContains(response, "Düzəldilmiş açar")
        item = response.context["items"][0]
        self.assertFalse(item.can_correct_key)
        texts = [event["text"] for event in response.context["review_timeline"]]
        self.assertTrue(any("göndərildi" in text for text in texts), texts)
        self.assertTrue(any("cavab açarı düzəldildi" in text for text in texts), texts)

    def test_read_only_reviewer_sees_no_key_fix_form(self):
        response = self._review(self.staff)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-key-fix-form")
        self.assertNotContains(response, "data-key-fix-revoke-url")

    def test_query_count_does_not_grow_with_items(self):
        client = self._client(self.head)
        url = reverse("appeals:review_appeal", args=[self.item.appeal_id]) + "?fragment=1"
        client.get(url, **_AJAX)  # isinmə (sessiya/keş)
        with CaptureQueriesContext(connection) as one_item:
            client.get(url, **_AJAX)
        # Eyni apellyasiyaya 4 sual da əlavə et (hər birinə cavab + snapshot).
        appeal = self.item.appeal
        for order in range(3, 7):
            question = ExamQuestion.objects.create(exam=self.exam, order=order, text=f"Q{order}", points=1)
            option = ExamQuestionOption.objects.create(question=question, label="A", text="a", is_correct=True)
            answer = ExamAnswer.objects.create(
                attempt=self.attempt,
                question=question,
                question_snapshot=self._snapshot(question, [option]),
                selected_option_ids_snapshot=[option.id],
            )
            appeal.items.create(question=question, answer=answer, appeal_type="other", comment="x" * 30)
        with CaptureQueriesContext(connection) as five_items:
            client.get(url, **_AJAX)
        # Effektiv bal hesabı cavab sayı ilə dəyişmir; item-lər üzrə sabit sorğu sayı (N+1 yoxdur).
        import collections
        import re

        def shapes(ctx):
            return collections.Counter(
                re.sub(r"\d+", "N", re.sub(r"IN \([^)]*\)", "IN (..)", q["sql"]))[:200] for q in ctx.captured_queries
            )

        diff = shapes(five_items) - shapes(one_item)
        self.assertLessEqual(len(five_items) - len(one_item), 2, list(diff.items()))


class ReviewAccessTests(_KeyFixSetup):
    def test_student_cannot_open_review_modal(self):
        response = self._client(self.student).get(
            reverse("appeals:review_appeal", args=[self.item.appeal_id]) + "?fragment=1", **_AJAX
        )
        self.assertEqual(response.status_code, 403)

    def test_other_student_gets_same_answer_as_missing_appeal(self):
        client = self._client(self.peer)
        foreign = client.get(reverse("appeals:appeal_detail", args=[self.item.appeal_id]) + "?fragment=1", **_AJAX)
        missing = client.get(reverse("appeals:appeal_detail", args=[999999]) + "?fragment=1", **_AJAX)
        self.assertEqual(foreign.status_code, missing.status_code)
        self.assertEqual(foreign.get("Location"), missing.get("Location"))

    def test_dean_covering_group_gets_read_only_detail(self):
        response = self._client(self.dean).get(
            reverse("appeals:appeal_detail", args=[self.item.appeal_id]) + "?fragment=1", **_AJAX
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "decision_")
        other = self._client(self.other_dean).get(
            reverse("appeals:appeal_detail", args=[self.item.appeal_id]) + "?fragment=1", **_AJAX
        )
        self.assertEqual(other.status_code, 302)
