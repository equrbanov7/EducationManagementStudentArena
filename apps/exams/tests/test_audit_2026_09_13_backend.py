"""Backend auditi 2026-09-13 — exams tapıntıları.

* F-03: ``grant_extra_attempt`` / ``grant_extra_attempt_group`` audit-siz idi →
  hər grant ``AuditLog``-a yazılır; (giriş auditi F-10) tələbə imtahanın
  təşkilatının AKTİV üzvü olmalıdır — kənar ``User.id`` 404.
* F-07: ``process_question_bank`` dublikat blok adında döngünün ortasında
  qayıdırdı və əvvəlki bloklar yazılmış qalırdı → indi bütün POST bir
  tranzaksiyadadır, xəta hər şeyi geri alır.
* F-08: ``journal_sync`` faiz/bal tavanı istisnalarını səssiz udurdu → log +
  ``ems_journal_sync_skips_total`` sayğacı (fail-soft davranış qalır).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.audit.models import AuditLog
from apps.exams.models import Exam, QuestionBlock, StudentExamAttemptGrant, StudentGroup
from apps.exams.services import journal_sync
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


def _login(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


class AttemptGrantAuditAndScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("ag_teacher", "ag_teacher@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="AG University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.student = User.objects.create_user("ag_student", "ag_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")
        # Başqa tenantın AKTİV tələbəsi — əvvəl grant yazıla bilirdi.
        cls.other_owner = User.objects.create_user("ag_other_owner", "ag_other_owner@test.az", PASSWORD)
        cls.other_org = Organization.objects.create(
            name="AG Other",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.other_owner,
            status="active",
            is_active=True,
        )
        cls.outsider = User.objects.create_user("ag_outsider", "ag_outsider@test.az", PASSWORD)
        _assign_user_to_org(cls.outsider, cls.other_org, ProfileRole.STUDENT, "student")
        cls.exam = Exam.objects.create(
            author=cls.teacher,
            title="AG Exam",
            organization=cls.org,
            exam_type="test",
            is_active=True,
            max_attempts_per_user=1,
        )

    def _grant_logs(self):
        return AuditLog.objects.filter(resource_type="StudentExamAttemptGrant")

    def test_individual_grant_is_audited(self):
        client = _login(self.teacher, self.org)
        response = client.post(
            reverse("exams:grant_extra_attempt", args=[self.exam.slug]),
            {"student_id": str(self.student.id), "extra_attempts": "2"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        grant = StudentExamAttemptGrant.objects.get(exam=self.exam, student=self.student)
        self.assertEqual(grant.extra_attempts, 2)
        log = self._grant_logs().get()
        self.assertEqual(log.action, "create")
        self.assertEqual(log.user_id, self.teacher.id)
        self.assertEqual(log.organization_id, self.org.id)
        self.assertEqual(log.resource_id, str(grant.pk))
        self.assertEqual(log.old_values, {"extra_attempts": 0})
        self.assertEqual(log.new_values, {"extra_attempts": 2})
        self.assertEqual(log.changes["action"], "exam_attempt_grant")
        self.assertEqual(log.changes["student_id"], str(self.student.pk))

        # Təkrar grant → mövcud sətir artır, ikinci qeyd köhnə→yeni dəyərlə.
        client.post(
            reverse("exams:grant_extra_attempt", args=[self.exam.slug]),
            {"student_id": str(self.student.id), "extra_attempts": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        second = self._grant_logs().order_by("-created_at", "-id").first()
        self.assertEqual(second.action, "update")
        self.assertEqual(second.old_values, {"extra_attempts": 2})
        self.assertEqual(second.new_values, {"extra_attempts": 3})
        self.assertEqual(self._grant_logs().count(), 2)

    def test_student_outside_exam_organization_is_404_without_grant(self):
        client = _login(self.teacher, self.org)
        response = client.post(
            reverse("exams:grant_extra_attempt", args=[self.exam.slug]),
            {"student_id": str(self.outsider.id)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "student_not_found")
        self.assertFalse(StudentExamAttemptGrant.objects.filter(exam=self.exam).exists())
        self.assertFalse(self._grant_logs().exists())

    def test_inactive_membership_in_exam_organization_is_404(self):
        from apps.organizations.models import Membership

        Membership.objects.filter(user=self.student, organization=self.org).update(is_active=False)
        client = _login(self.teacher, self.org)
        response = client.post(
            reverse("exams:grant_extra_attempt", args=[self.exam.slug]),
            {"student_id": str(self.student.id)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(StudentExamAttemptGrant.objects.filter(exam=self.exam).exists())

    def test_group_grant_writes_one_audit_row_per_student(self):
        second = User.objects.create_user("ag_student2", "ag_student2@test.az", PASSWORD)
        _assign_user_to_org(second, self.org, ProfileRole.STUDENT, "student")
        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="AG-G")
        group.students.add(self.student, second)
        client = _login(self.teacher, self.org)
        response = client.post(
            reverse("exams:grant_extra_attempt_group", args=[self.exam.slug]),
            {"group_id": str(group.id)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["granted_count"], 2)
        self.assertEqual(self._grant_logs().count(), 2)
        self.assertEqual(
            {log.changes["student_id"] for log in self._grant_logs()}, {str(self.student.pk), str(second.pk)}
        )


class QuestionBankPostAtomicTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("qb_atomic_teacher", "qb_atomic@test.az", PASSWORD)
        self.org = Organization.objects.create(
            name="QB Atomic Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER, "teacher")
        self.exam = Exam.objects.create(
            author=self.teacher, title="QB Atomic Exam", organization=self.org, exam_type="written", is_active=True
        )
        self.old_block = QuestionBlock.objects.create(exam=self.exam, name="Köhnə blok", order=1)
        self.client = _login(self.teacher, self.org)

    def test_duplicate_block_name_rolls_back_everything(self):
        response = self.client.post(
            reverse("exams:process_question_bank", args=[self.exam.slug]),
            {
                "deleted_block_ids": str(self.old_block.id),
                "random_question_count": "3",
                "block_name_1": "Blok A",
                "block_content_1": "1. Birinci sual",
                "block_db_id_1": "",
                "block_name_2": "blok a",  # dublikat (case-insensitive) → xəta döngünün ORTASINDA
                "block_content_2": "1. İkinci sual",
                "block_db_id_2": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("exams:create_question_bank", args=[self.exam.slug]), response.url)
        # Heç nə yazılmayıb: silinən blok yerindədir, «Blok A» yaranmayıb, sual sayı dəyişməyib.
        self.assertTrue(QuestionBlock.objects.filter(pk=self.old_block.pk).exists())
        self.assertFalse(QuestionBlock.objects.filter(exam=self.exam, name__iexact="Blok A").exists())
        self.exam.refresh_from_db()
        self.assertNotEqual(self.exam.random_question_count, 3)

    def test_valid_post_still_saves(self):
        response = self.client.post(
            reverse("exams:process_question_bank", args=[self.exam.slug]),
            {
                "deleted_block_ids": str(self.old_block.id),
                "random_question_count": "3",
                "block_name_1": "Blok A",
                "block_content_1": "1. Birinci sual",
                "block_db_id_1": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(QuestionBlock.objects.filter(pk=self.old_block.pk).exists())
        block = QuestionBlock.objects.get(exam=self.exam, name="Blok A")
        self.assertEqual(block.questions.count(), 1)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.random_question_count, 3)


class _BrokenScore:
    """``score_percent`` oxunanda partlayan cəhd atributu."""

    def __get__(self, instance, owner):
        raise RuntimeError("boom")


class _BrokenTestAttempt:
    id = 777
    user_id = 1
    is_trial = False
    supervision_status = "active"
    teacher_score = None
    score_percent = _BrokenScore()

    def __init__(self, exam):
        self.exam = exam


class _BrokenAnswers:
    def select_related(self, *args):
        raise RuntimeError("answers boom")


class _BrokenQuestions:
    def all(self):
        raise RuntimeError("questions boom")


class JournalSyncFailureVisibilityTest(SimpleTestCase):
    def _counter_value(self, reason):
        return journal_sync.journal_sync_skips_total.labels(reason=reason)._value.get()

    def test_test_percent_failure_is_logged_and_counted(self):
        exam = SimpleNamespace(
            exam_type="test",
            exam_type_extended="final",  # H-1: yalnız final kateqoriyası jurnala yazılır
            subject_id=1,
            organization=SimpleNamespace(pk=1),
            questions=None,
        )
        attempt = _BrokenTestAttempt(exam)
        before = self._counter_value(journal_sync.SKIP_PERCENT_UNAVAILABLE)
        with self.assertLogs("apps.exams.services.journal_sync", level=logging.WARNING) as captured:
            self.assertIsNone(journal_sync.sync_attempt_to_journal(attempt))
        self.assertEqual(self._counter_value(journal_sync.SKIP_PERCENT_UNAVAILABLE), before + 1)
        joined = "\n".join(captured.output)
        self.assertIn("test percent failed for attempt 777", joined)
        self.assertIn("skipped (percent_unavailable)", joined)

    def test_written_attempt_with_broken_max_score_is_logged_and_counted(self):
        exam = SimpleNamespace(
            exam_type="written",
            exam_type_extended="final",
            subject_id=1,
            organization=SimpleNamespace(pk=1),
            questions=_BrokenQuestions(),
        )
        attempt = SimpleNamespace(
            id=778,
            user_id=1,
            exam=exam,
            is_trial=False,
            supervision_status="active",
            teacher_score=5,
            answers=_BrokenAnswers(),
            graded_by=None,
        )
        before = self._counter_value(journal_sync.SKIP_PERCENT_UNAVAILABLE)
        with self.assertLogs("apps.exams.services.journal_sync", level=logging.WARNING) as captured:
            self.assertIsNone(journal_sync.sync_attempt_to_journal(attempt))
        self.assertEqual(self._counter_value(journal_sync.SKIP_PERCENT_UNAVAILABLE), before + 1)
        joined = "\n".join(captured.output)
        self.assertIn("answers could not be read for attempt 778", joined)
        self.assertIn("max score could not be computed for attempt 778", joined)
        self.assertIn("has no max score", joined)

    def test_ungraded_written_attempt_is_a_silent_wait_not_a_failure(self):
        exam = SimpleNamespace(
            exam_type="written",
            exam_type_extended="final",
            subject_id=1,
            organization=SimpleNamespace(pk=1),
            questions=None,
        )
        attempt = SimpleNamespace(
            id=779, user_id=1, exam=exam, is_trial=False, supervision_status="active", teacher_score=None
        )
        before = self._counter_value(journal_sync.SKIP_PERCENT_UNAVAILABLE)
        with self.assertNoLogs("apps.exams.services.journal_sync", level=logging.WARNING):
            self.assertIsNone(journal_sync.sync_attempt_to_journal(attempt))
        self.assertEqual(self._counter_value(journal_sync.SKIP_PERCENT_UNAVAILABLE), before)
