"""Fərdi PIN provizionu — PBKDF2 hash-i request-dən kənarda (tutum testi 2026-10-06).

Əvvəl: qrup final/midterm imtahanına təyin olunanda hər tələbə üçün request
daxilində ``make_password`` (~0.1 s) — 300 tələbə ≈ 30 s → timeout. İndi sətir
şifrəli nüsxə ilə dərhal yaranır (PIN dərhal görünür), hash-i commit-dən sonra
``exams.hash_pending_student_pins`` task-ı yazır; worker gecikərsə ilk giriş
həmin tək sətri özü hash edir.
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamStudentPin, FinalExamTicket, StudentGroup
from apps.exams.services import student_pin_hashing
from apps.exams.services.final_center import pins
from apps.exams.services.student_pin_hashing import PIN_HASH_PENDING
from apps.exams.services.student_pins import provision_exam_student_pins, student_visible_pin, verify_student_pin
from apps.exams.tasks import hash_pending_student_pins
from apps.exams.tests.test_exam_center_policy import _assign_user_to_org
from apps.exams.tests.test_final_center_flow import _FlowBase
from apps.exams.tests.test_final_entry_hash_budget_2026_10_06 import count_pin_hashes
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()

N_STUDENTS = 6


def _hash_task_callbacks(callbacks, exam):
    marker = ("exams.hash_pending_student_pins", exam.pk)
    return [cb for cb in callbacks if getattr(cb, "ems_marker", None) == marker]


def _commit(callbacks, exam):
    """TestCase tranzaksiyası commit olunmur — commit-dən sonrakı hash callback-ini əl ilə işlət."""
    for callback in _hash_task_callbacks(callbacks, exam):
        callback()  # eager Celery → task elə burada işləyir


class _OrgFixture:
    @staticmethod
    def make_org(prefix):
        owner = User.objects.create_user(f"{prefix}_owner", f"{prefix}_owner@test.az", "x")
        org = Organization.objects.create(
            name=f"{prefix} University",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        teacher = User.objects.create_user(f"{prefix}_teacher", f"{prefix}_teacher@test.az", "x")
        _assign_user_to_org(teacher, org, ProfileRole.TEACHER, "teacher")
        students = []
        for idx in range(N_STUDENTS):
            student = User.objects.create_user(f"{prefix}_s{idx}", f"{prefix}_s{idx}@test.az", "x")
            _assign_user_to_org(student, org, ProfileRole.STUDENT, "student")
            students.append(student)
        return org, teacher, students

    @staticmethod
    def make_final(org, teacher, category="final"):
        return Exam.objects.create(
            author=teacher,
            title=f"{org.name} {category}",
            organization=org,
            exam_type_extended=category,
            is_active=True,
            is_public=False,
        )


class AsyncProvisioningTests(_OrgFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.students = cls.make_org("aph")
        cls.group = StudentGroup.objects.create(teacher=cls.teacher, organization=cls.org, name="APH-1")
        cls.group.students.add(*cls.students[:-1])

    def setUp(self):
        pins._verified_pins.clear()
        self.exam = self.make_final(self.org, self.teacher)

    def _assign_in_request(self):
        """Müəllim sorğusu: qrup + fərdi tələbə + formun açıq provizion çağırışı (commit-dən əvvəl)."""
        with self.captureOnCommitCallbacks(execute=False) as callbacks, count_pin_hashes() as counter:
            self.exam.allowed_groups.add(self.group)
            self.exam.allowed_users.add(self.students[-1])
            provision_exam_student_pins(self.exam)
        return callbacks, counter

    def test_group_assignment_does_not_hash_in_request(self):
        callbacks, counter = self._assign_in_request()
        self.assertEqual(counter.full_hashes, 0)
        rows = list(ExamStudentPin.objects.filter(exam=self.exam))
        self.assertEqual(len(rows), N_STUDENTS)
        self.assertTrue(all(row.pin_hash == PIN_HASH_PENDING and row.pin_cipher for row in rows))
        # PIN kabinetdə DƏRHAL görünür (şifrəli nüsxədən) — «hazırlanır» pəncərəsi yoxdur.
        visible = {student_visible_pin(self.exam, s) for s in self.students}
        self.assertEqual(len(visible), N_STUDENTS)
        self.assertTrue(all(value and value.isdigit() for value in visible))
        # 3 provizion çağırışı → bir tranzaksiyada BİR hash task-ı.
        self.assertEqual(len(_hash_task_callbacks(callbacks, self.exam)), 1)

    def test_task_hashes_all_pending_and_rerun_is_idempotent(self):
        callbacks, _counter = self._assign_in_request()
        visible = {s.pk: student_visible_pin(self.exam, s) for s in self.students}
        with count_pin_hashes() as counter:
            _commit(callbacks, self.exam)
        self.assertEqual(counter.full_hashes, N_STUDENTS)
        for row in ExamStudentPin.objects.filter(exam=self.exam):
            self.assertNotEqual(row.pin_hash, PIN_HASH_PENDING)
            self.assertTrue(check_password(visible[row.student_id], row.pin_hash))
        # PIN dəyişmir (tələbənin artıq gördüyü PIN etibarlıdır).
        self.assertEqual({s.pk: student_visible_pin(self.exam, s) for s in self.students}, visible)

        with count_pin_hashes() as counter:
            self.assertEqual(hash_pending_student_pins(self.exam.pk, self.org.pk), 0)
        self.assertEqual(counter.full_hashes, 0)

    def test_reprovision_without_new_students_schedules_nothing(self):
        callbacks, _counter = self._assign_in_request()
        _commit(callbacks, self.exam)
        with self.captureOnCommitCallbacks(execute=False) as callbacks, count_pin_hashes() as counter:
            self.assertEqual(provision_exam_student_pins(self.exam), 0)
        self.assertEqual(counter.full_hashes, 0)
        self.assertEqual(_hash_task_callbacks(callbacks, self.exam), [])

    def test_broker_down_keeps_rows_pending_without_request_hashing(self):
        callbacks, _counter = self._assign_in_request()
        with (
            mock.patch.object(hash_pending_student_pins, "delay", side_effect=ConnectionError("broker down")),
            count_pin_hashes() as counter,
        ):
            _commit(callbacks, self.exam)
        self.assertEqual(counter.full_hashes, 0)
        self.assertEqual(ExamStudentPin.objects.filter(exam=self.exam, pin_hash=PIN_HASH_PENDING).count(), N_STUDENTS)
        # Növbəti provizion (məs. imtahan yenidən saxlanır) gözləyənləri yenidən növbəyə qoyur.
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            provision_exam_student_pins(self.exam)
        self.assertEqual(len(_hash_task_callbacks(callbacks, self.exam)), 1)

    def test_revoked_pin_is_regenerated_as_pending(self):
        callbacks, _counter = self._assign_in_request()
        _commit(callbacks, self.exam)
        student = self.students[0]
        old_pin = student_visible_pin(self.exam, student)
        ExamStudentPin.objects.filter(exam=self.exam, student=student).update(revoked_at=timezone.now(), pin_cipher="")
        with count_pin_hashes() as counter, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(provision_exam_student_pins(self.exam), 1)
            self.assertEqual(counter.full_hashes, 0)  # request daxilində hash yox
        # Bərpa: yeni PIN görünür və task (eager, commit-dən sonra) yalnız onu hash edir.
        self.assertEqual(counter.full_hashes, 1)
        row = ExamStudentPin.objects.get(exam=self.exam, student=student)
        self.assertIsNone(row.revoked_at)
        new_pin = student_visible_pin(self.exam, student)
        self.assertTrue(new_pin)
        self.assertTrue(check_password(new_pin, row.pin_hash))
        if old_pin != new_pin:
            self.assertFalse(check_password(old_pin, row.pin_hash))

    def test_unreadable_pending_cipher_gets_fresh_pin(self):
        self._assign_in_request()
        student = self.students[0]
        ExamStudentPin.objects.filter(exam=self.exam, student=student).update(pin_cipher="not-a-token")
        self.assertEqual(hash_pending_student_pins(self.exam.pk, self.org.pk), N_STUDENTS)
        row = ExamStudentPin.objects.get(exam=self.exam, student=student)
        new_pin = student_visible_pin(self.exam, student)
        self.assertTrue(new_pin)
        self.assertTrue(check_password(new_pin, row.pin_hash))

    def test_midterm_cabinet_verify_seals_pending_pin_with_one_hash(self):
        midterm = self.make_final(self.org, self.teacher, category="midterm")
        with self.captureOnCommitCallbacks(execute=False):
            midterm.allowed_users.add(self.students[0])
        raw = student_visible_pin(midterm, self.students[0])
        with count_pin_hashes() as counter:
            self.assertTrue(verify_student_pin(midterm, self.students[0], raw))
            self.assertTrue(verify_student_pin(midterm, self.students[0], raw))  # təkrar — memo
            self.assertFalse(verify_student_pin(midterm, self.students[0], "00000000"))
        self.assertEqual(counter.full_hashes, 2)
        row = ExamStudentPin.objects.get(exam=midterm, student=self.students[0])
        self.assertTrue(check_password(raw, row.pin_hash))

    def test_pending_verify_race_with_worker_uses_stored_hash(self):
        with self.captureOnCommitCallbacks(execute=False):
            self.exam.allowed_users.add(self.students[0])
        row = ExamStudentPin.objects.get(exam=self.exam, student=self.students[0])
        raw = student_visible_pin(self.exam, self.students[0])
        # Worker sətri request-in oxumasından SONRA hash edib.
        hash_pending_student_pins(self.exam.pk, self.org.pk)
        stored = ExamStudentPin.objects.get(pk=row.pk).pin_hash
        self.assertTrue(student_pin_hashing.verify_pending_student_pin(row, raw))
        self.assertEqual(ExamStudentPin.objects.get(pk=row.pk).pin_hash, stored)  # üstünə yazılmadı
        self.assertFalse(student_pin_hashing.verify_pending_student_pin(row, "00000000"))


class AsyncHashingTenantIsolationTests(_OrgFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org_a, cls.teacher_a, cls.students_a = cls.make_org("tia")
        cls.org_b, cls.teacher_b, cls.students_b = cls.make_org("tib")

    def _gucs(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_setting('app.current_org_id', true), current_setting('app.bypass_rls', true)"
            )
            return cursor.fetchone()

    def test_task_only_sees_its_own_organization(self):
        if connection.vendor != "postgresql":
            self.skipTest("RLS yalnız PostgreSQL-də")
        exam_a = self.make_final(self.org_a, self.teacher_a)
        exam_b = self.make_final(self.org_b, self.teacher_b)
        with self.captureOnCommitCallbacks(execute=False):
            exam_a.allowed_users.add(*self.students_a)
            exam_b.allowed_users.add(*self.students_b)

        # Məhdud tətbiq rolu (bypass yox) — RLS siyasətləri real işləyir.
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', false)")
            cursor.execute("SELECT set_config('app.current_org_id', '', false)")
            cursor.execute("SET LOCAL ROLE rls_app_role")
        before = self._gucs()

        # Yanlış təşkilat konteksti: A imtahanının sətirləri görünmür → heç nə yazılmır.
        with count_pin_hashes() as counter:
            self.assertEqual(hash_pending_student_pins(exam_a.pk, self.org_b.pk), 0)
        self.assertEqual(counter.full_hashes, 0)
        self.assertEqual(self._gucs(), before)  # eager task çağıranın RLS kontekstini bərpa edir

        self.assertEqual(hash_pending_student_pins(exam_a.pk, self.org_a.pk), N_STUDENTS)
        self.assertEqual(self._gucs(), before)

        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
        self.assertFalse(ExamStudentPin.objects.filter(exam=exam_a, pin_hash=PIN_HASH_PENDING).exists())
        # B təşkilatının sətirlərinə toxunulmayıb.
        self.assertEqual(ExamStudentPin.objects.filter(exam=exam_b, pin_hash=PIN_HASH_PENDING).count(), N_STUDENTS)


class PendingPinFinalEntryTests(_FlowBase):
    RAW_PIN = "31415926"

    def setUp(self):
        super().setUp()
        pins._verified_pins.clear()
        FinalExamTicket.objects.all().delete()
        Exam.objects.filter(pk=self.exam.pk).update(start_datetime=timezone.now() - timedelta(minutes=1))
        # Worker hələ işləməyib: sətir yalnız şifrəli nüsxə ilə.
        self.row = ExamStudentPin.objects.create(
            exam=self.exam,
            student=self.student,
            pin_hash=PIN_HASH_PENDING,
            pin_cipher=pins._fernet().encrypt(self.RAW_PIN.encode()).decode(),
        )

    def _post(self, pin):
        return Client().post(reverse("exams:final_exam_entry"), {"username": self.student.username, "pin": pin})

    def test_entry_with_pending_pin_succeeds_with_one_hash_and_seals_row(self):
        with count_pin_hashes() as counter:
            response = self._post(self.RAW_PIN)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(response.wsgi_request.session["_auth_user_id"]), self.student.pk)
        self.assertEqual(counter.full_hashes, 1)
        self.row.refresh_from_db()
        self.assertTrue(check_password(self.RAW_PIN, self.row.pin_hash))

    def test_wrong_pin_on_pending_row_one_hash_row_stays_pending(self):
        with count_pin_hashes() as counter:
            response = self._post("00000000")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", response.wsgi_request.session)
        self.assertEqual(counter.full_hashes, 1)
        self.row.refresh_from_db()
        self.assertEqual(self.row.pin_hash, PIN_HASH_PENDING)
