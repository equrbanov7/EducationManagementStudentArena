"""2026-10-13 (gecə) — «cavabın düzəldilməsi»: fərdi qərar + açar düzəlişi (bütün tələbələr).

Yoxlanan zəmanətlər:

* açar düzəlişi YENİ açara uyğun cavab verən hər bitmiş cəhdə kredit verir, heç kimin balını
  azaltmır, rəsmi jurnal balını yeniləyir və registrar ledger-ində ``kind=appeal`` sətri qalır;
* idempotentlik: ikinci aktiv düzəliş rədd olunur; fərdi qəbul + açar krediti ikiqat sayılmır;
* geri alma balı bərpa edir, amma tarixçə (sətirlər) qalır;
* rədd olunmuş apellyasiya heç nəyi dəyişmir;
* HTTP: qərar açarı (``appeal.decide``) olmayan 403, özgə təşkilat / tələbə 404 (IDOR);
* müəllim bildirişi (final → jurnal avtomatik, midterm → əl ilə) və mərkəz bildirişi açarla.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.appeals.constants import APPEAL_TYPE_WRONG_ANSWER_KEY
from apps.appeals.models import AnswerKeyCorrection, KeyCorrectionCredit, ScoreAdjustment
from apps.appeals.services import (
    accept_appeal_item,
    apply_key_correction,
    create_appeal,
    effective_test_score,
    reject_appeal_item,
    revoke_key_correction,
)
from apps.appeals.services.history import appeal_rows_by_attempt
from apps.appeals.tests.test_audit_2026_09_28_a3 import _A3Setup
from apps.exams.models import ExamAnswer, ExamAttempt, ExamGradeEvent, ExamQuestion, ExamQuestionOption
from apps.notifications.models import InAppNotification
from apps.organizations.models import Membership, Organization
from apps.registrar.models import ExamScoreEntry, ExamScoreEntryKind, FinalGrade
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()
_AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
COMMENT = "Açar səhvdir, B variantı düzgündür — dərslik 4.2."


class _KeyFixSetup(_A3Setup):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.head = User.objects.create_user("kf_head", "kf_head@qku.edu.az", "pw")
            self.staff = User.objects.create_user("kf_staff", "kf_staff@qku.edu.az", "pw")
            for user, role_name in ((self.head, "exam_center_head"), (self.staff, "exam_center_staff")):
                Membership.objects.create(
                    user=user,
                    organization=self.org,
                    role=self.org.roles.get(name=role_name),
                    is_primary=True,
                    is_active=True,
                )
            self.peer = User.objects.create_user("kf_peer", "kf_peer@qku.edu.az", "pw")
            self.peer_ok = User.objects.create_user("kf_peer_ok", "kf_peer_ok@qku.edu.az", "pw")
            for user in (self.peer, self.peer_ok):
                Membership.objects.create(
                    user=user, organization=self.org, role=self.org.roles.get(name="student"), is_active=True
                )
        self.exam = self._exam(exam_type="test", title="KF Final")
        self.q1 = ExamQuestion.objects.create(exam=self.exam, order=1, text="Q1", points=1)
        self.q1_a = ExamQuestionOption.objects.create(question=self.q1, label="A", text="a", is_correct=True)
        self.q1_b = ExamQuestionOption.objects.create(question=self.q1, label="B", text="b", is_correct=False)
        self.q2 = ExamQuestion.objects.create(exam=self.exam, order=2, text="Q2", points=1)
        self.q2_a = ExamQuestionOption.objects.create(question=self.q2, label="A", text="a", is_correct=True)
        ExamQuestionOption.objects.create(question=self.q2, label="B", text="b", is_correct=False)
        # Tələbə (müraciət edən) və peer B seçib (köhnə açarla səhv), peer_ok A seçib (köhnə açarla düz).
        self.attempt = self._attempt(self.student, self.q1_b)
        self.peer_attempt = self._attempt(self.peer, self.q1_b)
        self.ok_attempt = self._attempt(self.peer_ok, self.q1_a)
        self.item = self._appeal_item()

    def _snapshot(self, question, options):
        return {
            "v": 2,
            "points": 1,
            "text": question.text,
            "options": [
                {"id": opt.id, "label": opt.label, "text": opt.text, "is_correct": opt.is_correct} for opt in options
            ],
        }

    def _attempt(self, user, q1_choice):
        attempt = ExamAttempt.objects.create(user=user, exam=self.exam, status="in_progress")
        for question, choice in ((self.q1, q1_choice), (self.q2, self.q2_a)):
            answer = ExamAnswer.objects.create(
                attempt=attempt,
                question=question,
                question_snapshot=self._snapshot(question, list(question.options.order_by("id"))),
                selected_option_ids_snapshot=[choice.id],
            )
            answer.selected_options.add(choice)
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")
        return attempt

    def _appeal_item(self):
        appeal = create_appeal(
            attempt=self.attempt,
            student=self.student,
            items=[{"question_id": self.q1.id, "appeal_type": APPEAL_TYPE_WRONG_ANSWER_KEY, "comment": COMMENT}],
        )
        return appeal.items.get()

    def _score(self, attempt):
        return effective_test_score(attempt)["effective_score"]

    def _final_grade(self):
        with bypass_rls():
            return FinalGrade.objects.filter(enrollment__student=self.student).first()

    def _apply(self, option_ids=None):
        with self.captureOnCommitCallbacks(execute=True):
            return apply_key_correction(
                self.item,
                reviewer=self.head,
                corrected_option_ids=option_ids or [self.q1_b.id],
                reason="B variantı düzgündür — dərslik 4.2",
            )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client


class KeyCorrectionServiceTests(_KeyFixSetup):
    def test_credits_everyone_who_chose_the_new_key_and_never_lowers(self):
        before = {a.id: self._score(a) for a in (self.attempt, self.peer_attempt, self.ok_attempt)}
        grade_before = self._final_grade().exam_score

        correction = self._apply()

        self.assertEqual((correction.affected_count, correction.credited_count), (3, 2))
        self.assertEqual(correction.previous_option_ids, [self.q1_a.id])
        self.assertEqual(self._score(self.attempt), before[self.attempt.id] + 1)
        self.assertEqual(self._score(self.peer_attempt), before[self.peer_attempt.id] + 1)
        # Köhnə açarla düz cavab verən tələbənin balı AZALMIR.
        self.assertEqual(self._score(self.ok_attempt), before[self.ok_attempt.id])
        # Tarixçə yenidən yazılmır — snapshot toxunulmaz.
        answer = ExamAnswer.objects.get(attempt=self.attempt, question=self.q1)
        self.assertTrue(next(o for o in answer.question_snapshot["options"] if o["id"] == self.q1_a.id)["is_correct"])
        # Ledger (exams) + rəsmi jurnal (registrar) + append-only apellyasiya sətri.
        self.assertEqual(ExamGradeEvent.objects.filter(question=self.q1, new_score=1, old_score=0).count(), 2)
        self.assertGreater(self._final_grade().exam_score, grade_before)
        with bypass_rls():
            entry = ExamScoreEntry.objects.filter(enrollment__student=self.student).latest("created_at")
        self.assertEqual(entry.kind, ExamScoreEntryKind.APPEAL)
        self.assertEqual(entry.old_score, grade_before)

    def test_second_active_correction_is_refused(self):
        self._apply()
        with self.assertRaises(ValidationError):
            self._apply()
        self.assertEqual(AnswerKeyCorrection.objects.count(), 1)
        self.assertEqual(KeyCorrectionCredit.objects.count(), 2)

    def test_same_key_and_foreign_option_are_refused(self):
        with self.assertRaises(ValidationError):
            self._apply([self.q1_a.id])  # köhnə açarla eyni
        with self.assertRaises(ValidationError):
            self._apply([self.q2_a.id])  # başqa sualın variantı
        self.assertFalse(AnswerKeyCorrection.objects.exists())

    def test_individual_accept_on_top_of_key_correction_is_not_double_counted(self):
        self._apply()
        score = self._score(self.attempt)
        with self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(self.item, reviewer=self.head, response_text="Haqlıdır.")
        self.assertEqual(self._score(self.attempt), score)
        # Açar düzəlişi geri alınsa fərdi qərarın krediti QALIR.
        correction = AnswerKeyCorrection.objects.get()
        with self.captureOnCommitCallbacks(execute=True):
            revoke_key_correction(correction, reviewer=self.head, reason="Səhv düzəliş idi, geri alınır")
        self.assertEqual(self._score(self.attempt), score)
        self.assertEqual(self._score(self.peer_attempt), self._score(self.ok_attempt) - 1)

    def test_revoke_restores_scores_and_keeps_history(self):
        base = self._score(self.peer_attempt)
        grade_before = self._final_grade().exam_score
        correction = self._apply()
        with self.captureOnCommitCallbacks(execute=True):
            revoke_key_correction(correction, reviewer=self.head, reason="Mənbə yoxlandı — köhnə açar düz idi")
        self.assertEqual(self._score(self.peer_attempt), base)
        self.assertEqual(self._final_grade().exam_score, grade_before)
        correction.refresh_from_db()
        self.assertIsNotNone(correction.revoked_at)
        self.assertEqual(KeyCorrectionCredit.objects.filter(reverted=True).count(), 2)
        with bypass_rls():
            kinds = list(
                ExamScoreEntry.objects.filter(enrollment__student=self.student, kind=ExamScoreEntryKind.APPEAL)
                .order_by("created_at")
                .values_list("old_score", "new_score")
            )
        self.assertEqual(len(kinds), 2)  # artım + geri alma — hər ikisi qalır
        rows = appeal_rows_by_attempt([self.attempt.id])[self.attempt.id]
        self.assertIn("key_revoked", [row["status"] for row in rows])
        with self.assertRaises(ValidationError):
            revoke_key_correction(correction, reviewer=self.head, reason="ikinci dəfə geri alma")

    def test_rejected_appeal_changes_nothing(self):
        score = self._score(self.attempt)
        grade = self._final_grade().exam_score
        with self.captureOnCommitCallbacks(execute=True):
            reject_appeal_item(self.item, reviewer=self.head, response_text="Açar düzdür.")
        self.assertEqual(self._score(self.attempt), score)
        self.assertEqual(self._final_grade().exam_score, grade)
        self.assertFalse(ScoreAdjustment.objects.exists())
        self.assertFalse(ExamGradeEvent.objects.filter(attempt=self.attempt).exists())
        with bypass_rls():
            self.assertFalse(
                ExamScoreEntry.objects.filter(enrollment__student=self.student, kind=ExamScoreEntryKind.APPEAL).exists()
            )

    def test_accept_twice_credits_once(self):
        score = self._score(self.attempt)
        for _ in range(2):
            with self.captureOnCommitCallbacks(execute=True):
                accept_appeal_item(self.item, reviewer=self.head, response_text="Haqlıdır.")
        self.assertEqual(self._score(self.attempt), score + Decimal("1"))
        self.assertEqual(ScoreAdjustment.objects.filter(appeal_item=self.item).count(), 1)


class KeyCorrectionNotificationTests(_KeyFixSetup):
    def test_students_and_teacher_are_notified(self):
        self._apply()
        self.assertTrue(InAppNotification.objects.filter(recipient=self.peer, title="Cavab açarı düzəldildi").exists())
        self.assertFalse(
            InAppNotification.objects.filter(recipient=self.peer_ok, title="Cavab açarı düzəldildi").exists()
        )
        teacher_note = InAppNotification.objects.filter(recipient=self.teacher, title="Cavab açarı düzəlişi").get()
        self.assertIn("avtomatik", teacher_note.message)

    def test_teacher_notified_when_accept_changes_score(self):
        with self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(self.item, reviewer=self.head, response_text="Haqlıdır.")
        note = InAppNotification.objects.get(recipient=self.teacher, title="Apellyasiya nəticəsində bal dəyişdi")
        self.assertIn("+1", note.message)

    def test_midterm_teacher_hint_says_update_journal_manually(self):
        self.exam.exam_type_extended = "midterm"
        self.exam.save(update_fields=["exam_type_extended"])
        with self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(self.item, reviewer=self.head, response_text="Haqlıdır.")
        note = InAppNotification.objects.get(recipient=self.teacher, title="Apellyasiya nəticəsində bal dəyişdi")
        self.assertIn("Midterm", note.message)

    def test_new_appeal_notifies_key_holders_only(self):
        # Müraciət setUp-da yaradılıb: açar sahibi (rəhbər) bildiriş alır, açarsız işçi almır.
        marker = {"metadata__appeal_id": self.item.appeal_id}
        self.assertTrue(InAppNotification.objects.filter(recipient=self.head, **marker).exists())
        self.assertFalse(InAppNotification.objects.filter(recipient=self.staff, **marker).exists())


class KeyCorrectionEndpointTests(_KeyFixSetup):
    def _post(self, user):
        return self._client(user).post(
            reverse("appeals:key_correction_apply", args=[self.item.id]),
            {"corrected_option_ids": [self.q1_b.id], "reason": "B variantı düzgündür — dərslik 4.2"},
            **_AJAX,
        )

    def test_head_applies_staff_is_forbidden(self):
        self.assertEqual(self._post(self.staff).status_code, 403)
        self.assertFalse(AnswerKeyCorrection.objects.exists())
        response = self._post(self.head)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["credited_count"], 2)

    def test_student_and_foreign_org_get_not_found(self):
        self.assertEqual(self._post(self.student).status_code, 404)
        with bypass_rls():
            other = Organization.objects.create(
                name="KF Other",
                slug="kf-other",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            outsider = User.objects.create_user("kf_out", "kf_out@qku.edu.az", "pw")
            Membership.objects.create(
                user=outsider, organization=other, role=other.roles.get(name="exam_center_head"), is_active=True
            )
        client = Client()
        client.force_login(outsider)
        session = client.session
        session["active_organization"] = other.slug
        session.save()
        response = client.post(
            reverse("appeals:key_correction_apply", args=[self.item.id]),
            {"corrected_option_ids": [self.q1_b.id], "reason": "B variantı düzgündür — dərslik 4.2"},
            **_AJAX,
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(AnswerKeyCorrection.objects.exists())

    def test_get_is_not_allowed_and_revoke_requires_key(self):
        client = self._client(self.head)
        self.assertEqual(client.get(reverse("appeals:key_correction_apply", args=[self.item.id])).status_code, 405)
        correction = self._apply()
        url = reverse("appeals:key_correction_revoke", args=[correction.id])
        self.assertEqual(self._client(self.staff).post(url, {"reason": "geri alma səbəbi"}, **_AJAX).status_code, 403)
        response = client.post(url, {"reason": "geri alma səbəbi"}, **_AJAX)
        self.assertEqual(response.status_code, 200)
        correction.refresh_from_db()
        self.assertIsNotNone(correction.revoked_at)


class KeyCorrectionFullPointsTests(_KeyFixSetup):
    """Sahib 2026-10-14: «tam bal verilsin» — açar düzəlişi sualın TAM balını verir (əvvəl sabit +1)."""

    Q1_POINTS = 3

    def _snapshot(self, question, options):
        snapshot = super()._snapshot(question, options)
        if question.pk == self.q1.pk:
            snapshot["points"] = self.Q1_POINTS
        return snapshot

    def test_key_correction_gives_the_full_question_points(self):
        before = self._score(self.attempt)
        self._apply()
        self.assertEqual(self._score(self.attempt), before + Decimal(self.Q1_POINTS))
        self.assertEqual(
            KeyCorrectionCredit.objects.get(attempt=self.peer_attempt).delta_points, Decimal(self.Q1_POINTS)
        )

    def test_individual_plus_one_is_topped_up_not_doubled(self):
        before = self._score(self.attempt)
        with self.captureOnCommitCallbacks(execute=True):
            accept_appeal_item(self.item, reviewer=self.head, response_text="Haqlıdır.")
        self.assertEqual(self._score(self.attempt), before + Decimal("1"))
        self._apply()
        # +1 (fərdi) + 2 (tamamlama) = sualın tam balı; ikiqat (+1 +3) YOX.
        self.assertEqual(self._score(self.attempt), before + Decimal(self.Q1_POINTS))
