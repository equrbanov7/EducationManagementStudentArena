"""PostgreSQL backstop and publish/delete race tests for active exams."""

import threading
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase

import pytest

from apps.exams.models import Exam, ExamQuestion
from apps.exams.services.lifecycle import publish_exam
from apps.exams.services.question_invariants import delete_exam_questions
from apps.organizations.models import Organization
from core.constants import OrganizationType

pytestmark = pytest.mark.postgres

User = get_user_model()


def _fixture(suffix=""):
    teacher = User.objects.create_user(f"qinv-pg-teacher{suffix}", password="pw")
    org = Organization.objects.create(
        name=f"Question invariant PG org {suffix}",
        org_type=OrganizationType.SCHOOL,
        owner=teacher,
        status="active",
        is_active=True,
    )
    exam = Exam.objects.create(
        title=f"Question invariant PG exam {suffix}",
        author=teacher,
        organization=org,
        is_active=False,
    )
    question = ExamQuestion.objects.create(exam=exam, order=1, text="Q1", points=1)
    Exam.objects.filter(pk=exam.pk).update(is_active=True)
    exam.refresh_from_db()
    return teacher, org, exam, question


@skipUnless(connection.vendor == "postgresql", "Database trigger is PostgreSQL-specific.")
class ActiveExamQuestionDatabaseInvariantTests(TestCase):
    def setUp(self):
        self.teacher, self.org, self.exam, self.question = _fixture()

    def test_direct_delete_of_last_active_question_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExamQuestion.objects.filter(pk=self.question.pk).delete()

        self.assertTrue(ExamQuestion.objects.filter(pk=self.question.pk, is_active=True).exists())

    def test_direct_deactivation_of_last_active_question_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExamQuestion.objects.filter(pk=self.question.pk).update(is_active=False)

        self.assertTrue(ExamQuestion.objects.filter(pk=self.question.pk, is_active=True).exists())

    def test_direct_move_of_last_active_question_is_rejected(self):
        other = Exam.objects.create(
            title="Other draft exam",
            author=self.teacher,
            organization=self.org,
            is_active=False,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            ExamQuestion.objects.filter(pk=self.question.pk).update(exam=other)

        self.question.refresh_from_db()
        self.assertEqual(self.question.exam_id, self.exam.pk)

    def test_direct_publish_of_empty_exam_is_rejected(self):
        empty = Exam.objects.create(
            title="Empty draft",
            author=self.teacher,
            organization=self.org,
            is_active=False,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Exam.objects.filter(pk=empty.pk).update(is_active=True)
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS exams_exam_publish_requires_question IMMEDIATE")

        empty.refresh_from_db()
        self.assertFalse(empty.is_active)

    def test_direct_insert_of_active_empty_exam_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Exam.objects.create(
                title="Inserted active empty exam",
                author=self.teacher,
                organization=self.org,
                is_active=True,
            )
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS exams_exam_publish_requires_question IMMEDIATE")


@skipUnless(connection.vendor == "postgresql", "True publish/delete race needs PostgreSQL.")
class ActiveExamQuestionRaceTests(TransactionTestCase):
    def test_publish_and_last_question_delete_never_leave_active_empty_exam(self):
        teacher = User.objects.create_user("qinv-race-teacher", password="pw")
        org = Organization.objects.create(
            name="Question invariant race org",
            org_type=OrganizationType.SCHOOL,
            owner=teacher,
            status="active",
            is_active=True,
        )
        exam = Exam.objects.create(
            title="Question invariant race exam",
            author=teacher,
            organization=org,
            is_active=False,
        )
        question = ExamQuestion.objects.create(exam=exam, order=1, text="Q1", points=1)
        barrier = threading.Barrier(2)
        unexpected_errors = []

        def publisher():
            try:
                barrier.wait(timeout=10)
                publish_exam(Exam.objects.get(pk=exam.pk), by_user=User.objects.get(pk=teacher.pk))
            except Exception as exc:  # noqa: BLE001 - collected for invariant assertion
                unexpected_errors.append(exc)
            finally:
                close_old_connections()

        def deleter():
            try:
                barrier.wait(timeout=10)
                delete_exam_questions(Exam.objects.get(pk=exam.pk), [question.pk])
            except (ValidationError, IntegrityError):
                # Expected losing side when publish wins the lock race.
                pass
            except Exception as exc:  # noqa: BLE001 - collected for invariant assertion
                unexpected_errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=publisher), threading.Thread(target=deleter)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertFalse(any(thread.is_alive() for thread in threads), "Publish/delete race deadlocked.")
        self.assertFalse(unexpected_errors, f"Unexpected race errors: {unexpected_errors}")
        exam.refresh_from_db()
        active_questions = ExamQuestion.objects.filter(exam=exam, is_active=True).count()
        self.assertFalse(exam.is_active and active_questions == 0)
