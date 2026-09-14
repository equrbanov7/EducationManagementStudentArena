"""W5 `w5left` (2026-09-14), tapşırıq 3: tələbənin qrupu dəyişəndə imtahan PIN-ləri.

W4 hesabatı «qalanlar» 4: `StudentAcademicRecord.group` köçürməsi final/midterm
PIN-lərini yeniləmirdi — imtahan yenidən saxlananadək yeni qrupun tələbəsi
PIN-siz qalırdı. İndi `registrar.transfer` `student_group_changed` siqnalı
göndərir (registrar → exams statik importu dövr yaradardı), `exams`
(`services/unit_pin_sync.py`) `on_commit`-də yeni qrupun aktiv final/midterm
imtahanlarını idempotent sinxronlaşdırır; yeni qeyd / status dəyişikliyi
`post_save` ilə eyni yolu işlədir.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.exams.models import Exam, ExamStudentPin
from apps.exams.services.unit_pin_sync import sync_student_pins_for_unit
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import movements, transfer
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class GroupTransferPinSyncTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("w5p_owner", "w5p_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="W5P Univ",
                slug="w5p-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group1 = OrgUnit.objects.create(
                organization=self.org, name="G1", slug="w5p-g1", unit_type=OrgUnitType.GROUP
            )
            self.group2 = OrgUnit.objects.create(
                organization=self.org, name="G2", slug="w5p-g2", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            self.program = Program.objects.create(organization=self.org, code="CS", name="Kompüter elmləri")
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2024
            )
            self.student = User.objects.create_user("w5p_student", "w5p_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=self.student,
                organization=self.org,
                role=self.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            self.record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=self.program,
                curriculum=self.curriculum,
                group=self.group1,
                admission_year=2024,
            )
        self.final = self._exam("W5P Final", "final")
        self.final.allowed_units.add(self.group2)  # m2m_changed → G2-nin cari tələbələrinə PIN (hazırda heç kim)
        self.quiz = self._exam("W5P Quiz", "quiz")
        self.quiz.allowed_units.add(self.group2)

    def _student(self, username):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        with bypass_rls():
            Membership.objects.create(
                user=user,
                organization=self.org,
                role=self.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
        return user

    def _exam(self, title, category):
        return Exam.objects.create(
            title=title,
            author=self.owner,
            organization=self.org,
            exam_type="test",
            exam_type_extended=category,
            is_active=True,
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(days=2),
        )

    def _pin_exists(self, exam):
        return ExamStudentPin.objects.filter(exam=exam, student=self.student).exists()

    def test_transfer_into_group_with_active_final_provisions_pin(self):
        self.assertFalse(self._pin_exists(self.final))
        with self.captureOnCommitCallbacks(execute=True) as callbacks, bypass_rls():
            transfer.transfer_student_group(
                record=self.record, new_group=self.group2, period=self.period, by_user=self.owner
            )
        self.assertTrue(callbacks, "on_commit callback qeydiyyata alınmalı idi")
        self.assertTrue(self._pin_exists(self.final))
        # Quiz PIN tələb etmir — heç nə yazılmır.
        self.assertFalse(self._pin_exists(self.quiz))
        self.assertFalse(ExamStudentPin.objects.filter(exam=self.quiz).exists())

    def test_transfer_via_movement_service_provisions_pin(self):
        with self.captureOnCommitCallbacks(execute=True), bypass_rls():
            movements.create_movement(
                record=self.record,
                kind="group_transfer",
                order_number="Ə-1",
                order_date=timezone.localdate(),
                reason="Test köçürmə — W5 PIN sinxronu yoxlaması",
                actor=self.owner,
                period=self.period,
                new_group=self.group2,
            )
        self.assertTrue(self._pin_exists(self.final))

    def test_pin_is_not_written_when_enclosing_transaction_rolls_back(self):
        # Siqnal atomik blokun içində gedir; PIN yazısı `on_commit`-dədir → xarici
        # tranzaksiya geri çevriləndə callback atılır, PIN yaranmır.
        with self.captureOnCommitCallbacks(execute=True) as callbacks, bypass_rls():
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    transfer.transfer_student_group(
                        record=self.record, new_group=self.group2, period=self.period, by_user=self.owner
                    )
                    raise RuntimeError("simulyasiya: köçürmədən sonra xəta")
        self.assertEqual(len(callbacks), 0)
        self.assertFalse(self._pin_exists(self.final))
        self.record.refresh_from_db()
        self.assertEqual(self.record.group_id, self.group1.id)

    def test_new_record_in_group_provisions_pin(self):
        newcomer = self._student("w5p_new")
        with self.captureOnCommitCallbacks(execute=True), bypass_rls():
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=newcomer,
                program=self.program,
                curriculum=self.curriculum,
                group=self.group2,
                admission_year=2024,
            )
        self.assertTrue(ExamStudentPin.objects.filter(exam=self.final, student=newcomer).exists())

    def test_expulsion_removes_pin_and_unrelated_update_is_ignored(self):
        with self.captureOnCommitCallbacks(execute=True), bypass_rls():
            transfer.transfer_student_group(
                record=self.record, new_group=self.group2, period=self.period, by_user=self.owner
            )
        self.assertTrue(self._pin_exists(self.final))
        self.record.refresh_from_db()

        # Üzvlüyə aid olmayan sahə → sinxron çağırılmır (on_commit qeydiyyatı yoxdur).
        with self.captureOnCommitCallbacks(execute=True) as callbacks, bypass_rls():
            self.record.education_form = self.record.education_form
            self.record.save(update_fields=["education_form", "updated_at"])
        self.assertEqual(len(callbacks), 0)

        with self.captureOnCommitCallbacks(execute=True), bypass_rls():
            self.record.status = "expelled"
            self.record.is_active = False
            self.record.save(update_fields=["status", "is_active", "updated_at"])
        self.assertFalse(self._pin_exists(self.final))

    def test_sync_is_idempotent_and_query_count_is_bounded(self):
        with self.captureOnCommitCallbacks(execute=True), bypass_rls():
            transfer.transfer_student_group(
                record=self.record, new_group=self.group2, period=self.period, by_user=self.owner
            )
        pin = ExamStudentPin.objects.get(exam=self.final, student=self.student)
        self.assertEqual(sync_student_pins_for_unit(self.group2.pk), 1)
        # İdempotent: mövcud PIN dəyişmir.
        self.assertEqual(ExamStudentPin.objects.get(exam=self.final, student=self.student).pin_hash, pin.pin_hash)

        # 1 yeni PIN yaradan sinxron ↔ 4 yeni PIN yaradan sinxron: eyni sayda sorğu
        # (bulk_create; sətir başına sorğu yoxdur).
        ExamStudentPin.objects.filter(exam=self.final).delete()
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(sync_student_pins_for_unit(self.group2.pk), 1)
        first = len(ctx.captured_queries)
        self.assertEqual(ExamStudentPin.objects.filter(exam=self.final).count(), 1)

        for index in range(3):
            user = self._student(f"w5p_more{index}")
            with bypass_rls():
                StudentAcademicRecord.objects.create(
                    organization=self.org,
                    student=user,
                    program=self.program,
                    curriculum=self.curriculum,
                    group=self.group2,
                    admission_year=2024,
                )
        ExamStudentPin.objects.filter(exam=self.final).delete()
        with CaptureQueriesContext(connection) as ctx:
            sync_student_pins_for_unit(self.group2.pk)
        self.assertEqual(len(ctx.captured_queries), first)
        self.assertEqual(ExamStudentPin.objects.filter(exam=self.final).count(), 4)
