"""Qiymət yazma yollarında yarış (race) vəziyyətləri — Codex audit §14 (2026-09-13).

Codex (2026-09-12): «Enrollment üzrə kilidləmə yalnız bal daxil etmə servisinin
yarış problemini hədəfləyir; bütün digər qiymət yazı yollarının eyni yarış
sınağından keçdiyi iddia edilmir.»  Bu fayl qalan yolları eyni sınaqdan keçirir:

* ``gradebook.save_marks`` — grid xanası (əvvəl: iki paralel yazı eyni xanaya
  → ikinci INSERT ``uniq_lesson_enrollment_mark``-a çırpılıb bütün partiyanı
  IntegrityError ilə çökdürürdü; indi açılış sətri ``FOR UPDATE`` ilə kilidlənir);
* ``finals.set_exam_score`` — yekun bal + ``evaluate_resit`` (əvvəl: iki paralel
  yazı ``uniq_resit_per_enrollment`` IntegrityError-u verə bilirdi; indi qeydiyyat
  sətri kilidlənir — ``exam_score_entry`` ilə eyni kilid obyekti);
* ``journal_extras.set_selfwork_mark`` — təhvil işarəsi (əvvəl: paralel toggle
  ``uniq_selfwork_topic_enrollment``-ə çırpılırdı);
* ``save_marks`` ↔ ``set_exam_score`` — fərqli sətirləri kilidləyən iki yol
  eyni anda: deadlock YOXDUR (kilid sırası: açılış → qeydiyyat → xana).

Yalnız PostgreSQL (sətir kilidləri); ``TransactionTestCase`` — hər thread öz
bağlantısı ilə real paralel tranzaksiya açır.
"""

from __future__ import annotations

import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

import pytest

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, gradebook, journal_extras, services
from apps.registrar.models import (
    AttendanceStatus,
    Curriculum,
    CurriculumSubject,
    FinalGrade,
    LessonKind,
    LessonMark,
    Program,
    ResitRecord,
    SelfWorkMark,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


def _run_parallel(workers):
    """Hər işçini öz DB bağlantısında, ortaq bariyerdən sonra eyni anda işə sal."""
    barrier = Barrier(len(workers))

    def wrap(fn):
        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                with bypass_rls():
                    return fn()
            finally:
                close_old_connections()

        return run

    with ThreadPoolExecutor(max_workers=len(workers)) as pool:
        futures = [pool.submit(wrap(fn)) for fn in workers]
        return [f.result(timeout=30) for f in futures]


@pytest.mark.postgres
class GradeWriteConcurrencyTest(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row locks required")
        owner = User.objects.create_user("race_owner", "race_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="Race Univ",
                slug="race-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            specialty = OrgUnit.objects.create(
                organization=self.org, name="CS", slug="race-cs", unit_type=OrgUnitType.SPECIALTY
            )
            group = OrgUnit.objects.create(
                organization=self.org, name="KE-1", slug="race-ke-1", unit_type=OrgUnitType.GROUP, parent=specialty
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            program = Program.objects.create(organization=self.org, code="CS", name="KE", absence_limit_percent=25)
            curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2024)
            subject = Subject.objects.create(organization=self.org, code="CS101", name="Proqramlaşdırma")
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=curriculum, subject=subject, semester_number=1
            )
            self.teacher = User.objects.create_user("race_teacher", "race_teacher@qku.edu.az", "pw")
            self.student = User.objects.create_user("race_student", "race_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=self.teacher,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=self.student,
                organization=self.org,
                role=self.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=program,
                curriculum=curriculum,
                group=group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=record, period=self.period, semester_number=1)
            self.offering = self.student.enrollments.get().offering
            self.offering.lesson_hours = 20
            self.offering.instructor = self.teacher
            self.offering.save(update_fields=["lesson_hours", "instructor"])
            self.enrollment = self.offering.enrollments.get()
            self.lesson = gradebook.create_lesson(
                allow_past=True,
                offering=self.offering,
                date=datetime.date(2024, 10, 2),
                kind=LessonKind.SEMINAR,
                hours=2,
                created_by=self.teacher,
            )

    def _save_cell(self, score):
        def run():
            return gradebook.save_marks(
                offering=self.offering,
                entries=[
                    {
                        "lesson_id": str(self.lesson.pk),
                        "enrollment_id": str(self.enrollment.pk),
                        "status": AttendanceStatus.PRESENT,
                        "score": score,
                    }
                ],
                by_user=self.teacher,
                enforce_day=False,
                report=True,
            )

        return run

    def test_parallel_grid_saves_on_the_same_cell_do_not_crash_and_keep_one_mark(self):
        """Əvvəl: ikinci yazı IntegrityError → 500. İndi: hər ikisi yazılır, bir sətir qalır."""
        results = _run_parallel([self._save_cell(7), self._save_cell(9)])
        self.assertEqual([r["written"] for r in results], [1, 1])
        self.assertEqual([r["rejected"] for r in results], [0, 0])
        with bypass_rls():
            marks = list(LessonMark.objects.filter(lesson=self.lesson, enrollment=self.enrollment))
            self.assertEqual(len(marks), 1)
            self.assertIn(marks[0].score, (7, 9))
            self.enrollment.refresh_from_db()
            self.assertEqual(self.enrollment.absence_hours, 0)

    def test_parallel_final_exam_scores_leave_one_final_grade_and_at_most_one_resit(self):
        """Əvvəl: `evaluate_resit`-in `first()`→`create` cütü paralel çağırışda dublikat
        `ResitRecord` (unikal məhdudiyyət → IntegrityError) verə bilirdi."""

        def write(score):
            def run():
                return finals.set_exam_score(enrollment=self.enrollment, score=score, by_user=self.teacher)

            return run

        results = _run_parallel([write(10), write(12)])
        self.assertTrue(all(r is not None for r in results))
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.filter(enrollment=self.enrollment).count(), 1)
            self.assertLessEqual(ResitRecord.objects.filter(enrollment=self.enrollment).count(), 1)
            self.assertIn(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, (10, 12))

    def test_parallel_selfwork_toggles_keep_one_mark(self):
        with bypass_rls():
            topic = journal_extras.add_selfwork_topic(offering=self.offering, title="Sərbəst iş 1")
        self.assertIsNotNone(topic)

        def toggle(done):
            def run():
                return journal_extras.set_selfwork_mark(
                    offering=self.offering,
                    topic_id=str(topic.pk),
                    enrollment_id=str(self.enrollment.pk),
                    done=done,
                    by_user=self.teacher,
                )

            return run

        results = _run_parallel([toggle(True), toggle(True)])
        self.assertEqual(results, [True, True])
        with bypass_rls():
            self.assertEqual(SelfWorkMark.objects.filter(topic=topic, enrollment=self.enrollment).count(), 1)

    def test_grid_save_and_final_score_in_parallel_do_not_deadlock(self):
        """Fərqli kilid obyektləri (açılış vs qeydiyyat) — Postgres deadlock aşkarlasa
        istisna atardı; hər iki yol tamamlanmalıdır."""

        def final():
            return finals.set_exam_score(enrollment=self.enrollment, score=40, by_user=self.teacher)

        results = _run_parallel([self._save_cell(8), final])
        self.assertEqual(results[0]["written"], 1)
        self.assertIsNotNone(results[1])
        with bypass_rls():
            self.assertEqual(LessonMark.objects.filter(lesson=self.lesson).count(), 1)
            self.assertEqual(FinalGrade.objects.filter(enrollment=self.enrollment).count(), 1)
