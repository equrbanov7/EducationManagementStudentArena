"""Nəticəli midtermin fənn dəyişikliyi — təsdiq + məcburi səbəb, audit, tarixçə (sahib 2026-10-25).

Sahib: «tələbənin imtahan nəticəsi VARSA məcburi (təsdiq + səbəb), yoxdursa rahat formada olsun».
Bax ``apps/exams/services/exam_subject_change.py``.
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.urls import reverse

from apps.audit.models import AuditLog
from apps.exams.models import Exam, ExamAttempt
from apps.exams.services import exam_journal_link, exam_subject_change
from apps.exams.tests.test_exam_journal_link_2026_10_24 import _LinkSetup, _login
from core.rls import bypass_rls

_REASON = "İmtahan yaradılarkən fənn səhv seçilmişdi"


class _GuardSetup(_LinkSetup):
    def _exam_on_wrong_subject(self, *, taken=True):
        exam, options = self._exam(title="JS Loop")
        with bypass_rls():
            Exam.objects.filter(pk=exam.pk).update(subject=self.wrong_subject, author=self.center)
            exam.refresh_from_db()
            exam.allowed_units.add(self.group)
            exam_journal_link.refresh_links(exam)
        if taken:
            self._finish(exam, options, correct=2)  # 66.7% → yanlış fənnin jurnalına 20
            self.assertEqual(self._score_in(self.wrong_offering, self.wrong_enrollment).score, Decimal("20"))
        return exam

    def _post(self, exam, **extra):
        client = _login(self.center, self.org)
        with self.captureOnCommitCallbacks(execute=True):
            return client.post(
                reverse("exams:edit_exam", kwargs={"slug": exam.slug}) + "?modal=1",
                self._payload(**extra),
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

    def _decisions(self, exam):
        with bypass_rls():
            return list(
                AuditLog.objects.filter(
                    resource_type=exam_subject_change.AUDIT_RESOURCE, resource_id=str(exam.pk)
                ).order_by("created_at")
            )

    def _subject_id(self, exam):
        with bypass_rls():
            return Exam.objects.filter(pk=exam.pk).values_list("subject_id", flat=True).get()


class NoResultsSimpleFormTests(_GuardSetup):
    def test_subject_change_without_results_needs_no_reason(self):
        exam = self._exam_on_wrong_subject(taken=False)
        response = self._post(exam, subject=str(self.subject.pk))
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertEqual(self._subject_id(exam), self.subject.pk)
        self.assertEqual(self._decisions(exam), [])

    def test_trial_attempt_is_not_a_result(self):
        exam = self._exam_on_wrong_subject(taken=False)
        with bypass_rls():
            ExamAttempt.objects.create(user=self.teacher, exam=exam, status="submitted", is_trial=True)
        response = self._post(exam, subject=str(self.subject.pk))
        self.assertEqual(response.status_code, 200, response.content[:400])

    def test_edit_form_has_no_guard_block_without_results(self):
        exam = self._exam_on_wrong_subject(taken=False)
        client = _login(self.center, self.org)
        html = client.get(reverse("exams:edit_exam", kwargs={"slug": exam.slug}) + "?modal=1").content.decode()
        self.assertNotIn("data-ew-subject-guard", html)


class ResultsRequireConfirmationTests(_GuardSetup):
    def test_change_without_reason_is_rejected_and_nothing_moves(self):
        exam = self._exam_on_wrong_subject()
        response = self._post(exam, subject=str(self.subject.pk))
        self.assertEqual(response.status_code, 409)
        payload = json.loads(response.content)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["field"], exam_subject_change.REASON_FIELD)
        self.assertEqual(payload["subject_change_required"]["students"], 1)
        self.assertIn("data-server-required", payload["html"])
        self.assertIn("Yanlış fənn", payload["html"])  # köhnə fənn → yeni fənn göstərilir
        self.assertEqual(self._subject_id(exam), self.wrong_subject.pk)  # saxlanmadı
        self.assertEqual(self._score_in(self.wrong_offering, self.wrong_enrollment).score, Decimal("20"))
        self.assertIsNone(self._score_in(self.offering, self.enrollment))
        self.assertEqual(self._decisions(exam), [])

    def test_confirm_without_reason_or_short_reason_is_rejected(self):
        exam = self._exam_on_wrong_subject()
        for extra in (
            {"subject_change_confirm": "1"},
            {"subject_change_confirm": "1", "subject_change_reason": "səhv"},
            {"subject_change_reason": _REASON},  # səbəb var, təsdiq yoxdur
        ):
            response = self._post(exam, subject=str(self.subject.pk), **extra)
            self.assertEqual(response.status_code, 409, extra)
        self.assertEqual(self._subject_id(exam), self.wrong_subject.pk)

    def test_confirmed_change_moves_results_and_is_audited(self):
        exam = self._exam_on_wrong_subject()
        response = self._post(
            exam, subject=str(self.subject.pk), subject_change_confirm="1", subject_change_reason=_REASON
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertEqual(self._subject_id(exam), self.subject.pk)
        self.assertEqual(self._score_in(self.offering, self.enrollment).score, Decimal("20"))  # yeni jurnal
        self.assertIsNone(self._score_in(self.wrong_offering, self.wrong_enrollment))  # köhnədən silindi

        decisions = self._decisions(exam)
        self.assertEqual(len(decisions), 1)
        row = decisions[0]
        self.assertEqual(row.user, self.center)
        self.assertEqual(row.reason, _REASON)
        self.assertEqual(row.changes["old"]["subject_id"], str(self.wrong_subject.pk))
        self.assertEqual(row.changes["new"]["subject_id"], str(self.subject.pk))
        self.assertEqual(row.changes["students_with_results"], 1)
        with bypass_rls():
            resync = AuditLog.objects.get(
                resource_type=exam_subject_change.AUDIT_RESOURCE_RESYNC, resource_id=str(exam.pk)
            )
        self.assertEqual(resync.changes["decision"], str(row.pk))
        self.assertEqual(resync.changes["counts"].get("written"), 1)
        self.assertEqual(resync.changes["counts"].get("cleared"), 1)

        history = exam_subject_change.history(exam)
        self.assertEqual(len(history), 1)
        self.assertEqual((history[0]["moved"], history[0]["cleared"]), (1, 1))

        client = _login(self.center, self.org)
        page = client.get(reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug})).content.decode()
        self.assertIn("ted-subject-history", page)
        self.assertIn(_REASON, page)

    def test_edit_without_subject_change_needs_no_reason(self):
        exam = self._exam_on_wrong_subject()
        response = self._post(exam, subject=str(self.wrong_subject.pk), title="JS Loop (yenilənib)")
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertEqual(self._decisions(exam), [])
        self.assertEqual(self._score_in(self.wrong_offering, self.wrong_enrollment).score, Decimal("20"))

    def test_group_change_that_moves_no_score_needs_no_reason(self):
        exam = self._exam_on_wrong_subject()
        # Qrup dəyişir, yeni qrupda bu fənnin jurnalı yoxdur → bal köhnə jurnalda QALIR (heç nə köçmür/silinmir),
        # ona görə təsdiq istənmir (sahib 2026-10-27: «qrupu çıxardım, fənn dəyişikliyi soruşur»).
        response = self._post(exam, subject=str(self.wrong_subject.pk), allowed_units=[str(self.other_group.pk)])
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertEqual(self._decisions(exam), [])
        self.assertEqual(self._score_in(self.wrong_offering, self.wrong_enrollment).score, Decimal("20"))

    def test_group_removal_with_confirmation_is_saved(self):
        # Sahib 2026-10-27: qrup çıxarılır (fənn eyni) → təsdiq + səbəb verildikdə saxlanmalıdır.
        exam = self._exam_on_wrong_subject()
        response = self._post(
            exam,
            subject=str(self.wrong_subject.pk),
            allowed_units=[str(self.other_group.pk)],
            subject_change_confirm="1",
            subject_change_reason="236 QM sehven imtahan icazesi verilib",
        )
        self.assertEqual(response.status_code, 200, response.content[:600])
        with bypass_rls():
            units = set(Exam.objects.get(pk=exam.pk).allowed_units.values_list("pk", flat=True))
        self.assertEqual(units, {self.other_group.pk})

    def test_edit_form_renders_hidden_guard_with_original_subject(self):
        exam = self._exam_on_wrong_subject()
        client = _login(self.center, self.org)
        html = client.get(reverse("exams:edit_exam", kwargs={"slug": exam.slug}) + "?modal=1").content.decode()
        self.assertIn("data-ew-subject-guard", html)
        self.assertIn(f'data-original-subject="{self.wrong_subject.pk}"', html)
        self.assertNotIn("data-server-required", html)


class ConfirmationValidatorTests(_GuardSetup):
    def test_validate_confirmation(self):
        ok, err = exam_subject_change.validate_confirmation(
            {"subject_change_confirm": "1", "subject_change_reason": _REASON}
        )
        self.assertEqual((ok, err), (_REASON, ""))
        reason, err = exam_subject_change.validate_confirmation(
            {"subject_change_confirm": "on", "subject_change_reason": "  qısa "}
        )
        self.assertIsNone(reason)
        self.assertTrue(err)


class SameSubjectAddedJournalsTests(_GuardSetup):
    """Sahib 2026-10-26: «eyni bir şeydə niyə bu gəlir?» — fənn eyni, qrupa yeni (alt qrup) jurnalı əlavə olunub."""

    def _decide(self, exam, *, old_links, new_links):
        from unittest import mock

        snapshot = exam_subject_change.take_snapshot(exam)
        snapshot = exam_subject_change.Snapshot(
            subject_id=snapshot.subject_id,
            subject_label=snapshot.subject_label,
            teacher_id=snapshot.teacher_id,
            unit_ids=snapshot.unit_ids,
            link_ids=frozenset(old_links),
            category=snapshot.category,
        )
        with mock.patch.object(exam_subject_change, "_prospective_link_ids", return_value=frozenset(new_links)):
            return exam_subject_change.decide(snapshot, exam, unit_ids=[*snapshot.unit_ids, self.other_group.pk])

    def test_only_added_journals_need_no_confirmation(self):
        exam = self._exam_on_wrong_subject()
        self.assertIsNone(self._decide(exam, old_links={"a"}, new_links={"a", "b"}))

    def test_removed_journal_needs_confirmation_only_when_scores_move(self):
        from unittest import mock

        exam = self._exam_on_wrong_subject()
        with mock.patch.object(exam_subject_change, "_moved_students", return_value=3):
            decision = self._decide(exam, old_links={"a", "b"}, new_links={"a"})
        self.assertIsNotNone(decision)
        self.assertEqual(decision.students, 3)
        with mock.patch.object(exam_subject_change, "_moved_students", return_value=0):
            self.assertIsNone(self._decide(exam, old_links={"a", "b"}, new_links={"a"}))
