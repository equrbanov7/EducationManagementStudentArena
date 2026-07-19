"""seed_stress_exam_journal — stress org-una imtahan + elektron jurnal datası.

``seed_stress_test`` ilə yaradılmış stress təşkilatına (default slug
``stress-test-university``) yük testi üçün:
  * 1 aktiv MCQ test imtahanı (N sual) — bütün stress qruplarına təyin olunur,
    kod yoxdur, cəhd limiti yoxdur, həmişə açıq → k6 exam-flow (start→autosave→
    submit) üçün;
  * registrar elektron jurnal datası — Program/Curriculum/Subject/CourseOffering
    + hər tələbəyə StudentAcademicRecord + Enrollment + M dərs + qeydlər → k6
    my-journal read üçün.

İdempotentdir. İmtahan slug-ı stdout-a yazılır (k6 K6_TEST_EXAM_SLUG üçün).

    python manage.py seed_stress_exam_journal --questions 20 --lessons 15
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption, QuestionBlock, StudentGroup
from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from core.constants import AcademicPeriodType, OrgUnitType
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

User = get_user_model()


class Command(BaseCommand):
    help = "Seed a stress exam + electronic-journal data into the stress-test organization."

    def add_arguments(self, parser):
        parser.add_argument("--org-slug", default="stress-test-university")
        parser.add_argument("--prefix", default="stress")
        parser.add_argument("--questions", type=int, default=20)
        parser.add_argument("--lessons", type=int, default=15)
        parser.add_argument("--exam-title", default="Stress Test İmtahanı")

    @transaction.atomic
    @rls_worker_atomic()
    @bypass_rls()
    def handle(self, *args, **opts):
        org = Organization.objects.filter(slug=opts["org_slug"]).first()
        if org is None:
            self.stderr.write(f"Stress org '{opts['org_slug']}' not found — run seed_stress_test first.")
            return
        prefix = opts["prefix"]
        teacher = User.objects.filter(username=f"{prefix}_teacher").first()
        students = list(User.objects.filter(username__startswith=f"{prefix}_student_").order_by("username"))
        groups = list(StudentGroup.objects.filter(organization=org))
        if not teacher or not students or not groups:
            self.stderr.write("Missing teacher/students/groups — run seed_stress_test first.")
            return

        exam = self._seed_exam(org, teacher, groups, students, opts)
        self._seed_journal(org, teacher, students, opts)

        line = "─" * 60
        self.stdout.write(self.style.SUCCESS(line))
        self.stdout.write(self.style.SUCCESS("STRESS EXAM + JOURNAL HAZIRDIR"))
        self.stdout.write(f"  İmtahan slug : {exam.slug}")
        self.stdout.write(f"  Suallar      : {exam.questions.count()}")
        self.stdout.write(f"  Tələbə       : {len(students)}")
        self.stdout.write(self.style.SUCCESS(f"K6_TEST_EXAM_SLUG={exam.slug}"))
        self.stdout.write(self.style.SUCCESS(line))

    # ── Exam ─────────────────────────────────────────────────────────────────
    def _seed_exam(self, org, teacher, groups, students, opts):
        title = opts["exam_title"]
        exam, _ = Exam.objects.get_or_create(
            organization=org,
            author=teacher,
            title=title,
            defaults={
                "description": "Yük testi üçün MCQ imtahanı (stress).",
                "exam_type": "test",
                "is_active": True,
                "is_public": False,
                "max_attempts_per_user": 0,  # limitsiz
                "default_question_points": 1,
                "slug": slugify(f"stress-{title}") or "stress-exam",
            },
        )
        changed = []
        if not exam.is_active:
            exam.is_active, _ = True, changed.append("is_active")
        if exam.max_attempts_per_user != 0:
            exam.max_attempts_per_user = 0
            changed.append("max_attempts_per_user")
        if exam.start_datetime is not None:
            exam.start_datetime = None
            changed.append("start_datetime")
        if exam.end_datetime is not None:
            exam.end_datetime = None
            changed.append("end_datetime")
        if changed:
            exam.save(update_fields=changed)
        for group in groups:
            exam.allowed_groups.add(group)

        block, _ = QuestionBlock.objects.get_or_create(exam=exam, order=1, defaults={"name": "Stress"})
        have = exam.questions.count()
        for i in range(have, opts["questions"]):
            q = ExamQuestion.objects.create(
                exam=exam,
                block=block,
                order=i + 1,
                text=f"Stress sual {i + 1}: düzgün variantı seçin.",
                answer_mode="single",
                points=1,
                difficulty="easy",
            )
            for label, is_correct in [("A", True), ("B", False), ("C", False), ("D", False)]:
                ExamQuestionOption.objects.create(
                    question=q, label=label, text=f"Variant {label}", is_correct=is_correct
                )
        return exam

    # ── Registrar journal ────────────────────────────────────────────────────
    def _seed_journal(self, org, teacher, students, opts):
        from apps.registrar import services
        from apps.registrar.models import (
            AttendanceStatus,
            Curriculum,
            CurriculumSubject,
            Lesson,
            LessonKind,
            LessonMark,
            Program,
            StudentAcademicRecord,
            Subject,
        )

        period = AcademicPeriod.objects.filter(
            organization=org, is_current=True
        ).first() or AcademicPeriod.objects.create(
            organization=org,
            name="Stress semestr",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2024/2025",
            start_date="2024-09-01",
            end_date="2025-01-31",
            is_current=True,
        )
        unit = OrgUnit.objects.filter(organization=org, unit_type=OrgUnitType.GROUP).first() or OrgUnit.objects.create(
            organization=org, name="STRESS-QRUP", slug="stress-reg-group", unit_type=OrgUnitType.GROUP
        )
        program, _ = Program.objects.get_or_create(
            organization=org, code="STR", defaults={"name": "Stress Proqramı", "absence_limit_percent": 25}
        )
        curriculum, _ = Curriculum.objects.get_or_create(organization=org, program=program, admission_year=2024)
        subject, _ = Subject.objects.get_or_create(organization=org, code="STR101", defaults={"name": "Stress Fənni"})
        CurriculumSubject.objects.get_or_create(
            organization=org, curriculum=curriculum, subject=subject, semester_number=1
        )

        offering = None
        for student in students:
            record, _ = StudentAcademicRecord.objects.get_or_create(
                organization=org,
                student=student,
                defaults={
                    "program": program,
                    "curriculum": curriculum,
                    "group": unit,
                    "admission_year": 2024,
                },
            )
            services.enroll_mandatory_subjects(record=record, period=period, semester_number=1)
            if offering is None:
                enr = student.enrollments.filter(offering__subject=subject).first()
                if enr:
                    offering = enr.offering
                    offering.instructor = teacher
                    offering.lesson_hours = 60
                    offering.save(update_fields=["instructor", "lesson_hours"])

        if offering is None:
            self.stdout.write("  (jurnal: offering yaradılmadı — enrollment boşdur)")
            return

        # Dərslər + qeydlər (jurnalın dolu görünməsi üçün).
        for i in range(opts["lessons"]):
            lesson, created = Lesson.objects.get_or_create(
                organization=org,
                offering=offering,
                date=datetime.date(2024, 10, 1) + datetime.timedelta(days=i * 2),
                defaults={"kind": LessonKind.SEMINAR if i % 2 else LessonKind.LECTURE, "hours": 2},
            )
            if not created:
                continue
            marks = []
            for enr in offering.enrollments.all():
                marks.append(
                    LessonMark(
                        organization=org,
                        lesson=lesson,
                        enrollment=enr,
                        status=AttendanceStatus.PRESENT,
                        score=(5 if lesson.kind == LessonKind.SEMINAR else None),
                    )
                )
            LessonMark.objects.bulk_create(marks, batch_size=500, ignore_conflicts=True)
