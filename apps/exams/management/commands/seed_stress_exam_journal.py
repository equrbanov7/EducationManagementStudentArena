"""seed_stress_exam_journal — stress org-una imtahan + elektron jurnal datası.

``seed_stress_test`` ilə yaradılmış stress təşkilatına (default slug
``stress-test-university``) yük testi üçün:
  * 1 aktiv MCQ test imtahanı (N sual) — bütün stress qruplarına təyin olunur,
    kod yoxdur, cəhd limiti yoxdur, həmişə açıq → k6 exam-flow (start→autosave→
    submit) üçün;
  * registrar elektron jurnal datası — Program/Curriculum/Subject/CourseOffering
    + hər tələbəyə StudentAcademicRecord + Enrollment + M dərs + qeydlər → k6
    my-journal read üçün (2024/2025, köhnə davranış, dəyişməz).

Bundan əlavə (yeni bayraqlar, defolt AÇIQdır — sadə çağırış hamısını yaradır)
sahibin jurnal + imtahan↔jurnal körpüsünü VİZUAL test edə bilməsi üçün
2025/2026 tədris ili datası:
  * ``--seed-2025-2026`` — 2025/2026 Payız semestri (``AcademicPeriod``,
    ``is_current=True`` — köhnə 2024/2025 avtomatik ``is_current=False``
    olur), həmin dövr üçün 2 əlavə fənn (STR102/STR103), dərslər + qeydlər;
  * ``--seed-corrections`` — İmtahan Mərkəzi düzəlişləri (sarı xanalar):
    ≥1 bal korreksiyası + ≥1 davamiyyət korreksiyası (qb → üzrlü), hər biri
    minimal PDF sənədlə (``apps.registrar.corrections.apply_correction``);
  * ``--seed-failures`` — ≥2 tələbə davamiyyətdən (qayıb limitini keçərək)
    kəsilir, ≥2 tələbə imtahandan (aşağı bal, ``exam_bridge`` vasitəsilə F);
  * ``--seed-past-years`` — 2 keçmiş tədris ili (2022/2023, 2023/2024), sabit
    tələbədə A-E+barred+qb+imtahan qarışığı (data: ``_stress_past_years_data.py``).

İdempotentdir — təkrar çağırış mövcud qeydləri təkrarlamır (get_or_create /
update_or_create; korreksiyalar mövcud ``JournalCorrection`` yoxlanışı ilə bir
dəfə tətbiq olunur). İmtahan slug-ı stdout-a yazılır (k6 K6_TEST_EXAM_SLUG üçün).

    python manage.py seed_stress_exam_journal --questions 20 --lessons 15
    python manage.py seed_stress_exam_journal --no-seed-corrections  # yalnız jurnal
"""

from __future__ import annotations

import argparse
import datetime

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption, QuestionBlock, StudentGroup
from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from core.constants import AcademicPeriodType, OrgUnitType
from core.management.command_safety import ProductionCommandSafetyMixin
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

User = get_user_model()

# Minimal, struktur baxımdan etibarlı bir-səhifəlik PDF — seed-i sürətli saxlamaq
# üçün balaca, ``FileUploadValidator``-dan keçmək üçün real (uzantı .pdf +
# "%PDF" imzası + heç bir bloklanan MIME/işarə).
_MIN_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n"
    b"%%EOF"
)


def _correction_document(name: str) -> SimpleUploadedFile:
    """Düzəliş üçün məcburi sənəd sahəsini (PDF) doldurmaq üçün in-memory fayl."""
    return SimpleUploadedFile(name, _MIN_PDF_BYTES, content_type="application/pdf")


class Command(ProductionCommandSafetyMixin, BaseCommand):
    safety_command_name = "seed_stress_exam_journal"
    help = "Seed a stress exam + electronic-journal data into the stress-test organization."

    def add_arguments(self, parser):
        parser.add_argument("--org-slug", default="stress-test-university")
        parser.add_argument("--prefix", default="stress")
        parser.add_argument("--questions", type=int, default=20)
        parser.add_argument("--lessons", type=int, default=15)
        parser.add_argument("--exam-title", default="Stress Test İmtahanı")
        parser.add_argument(
            "--lessons-2526",
            type=int,
            default=16,
            help="2025/2026 fənləri (STR102/STR103) üçün dərs sayı (davamiyyət-kəsilməsi ssenarisi üçün ≥8 tövsiyə olunur).",
        )
        parser.add_argument(
            "--seed-2025-2026",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="2025/2026 tədris ili jurnal datası (yeni AcademicPeriod + 2 fənn + dərslər/qeydlər).",
        )
        parser.add_argument(
            "--seed-corrections",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="İmtahan Mərkəzi düzəlişləri (sarı xanalar): bal + davamiyyət korreksiyası.",
        )
        parser.add_argument(
            "--seed-failures",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Kəsilən tələbələr: davamiyyət limitindən (barred) və imtahandan (aşağı bal → F).",
        )
        parser.add_argument(
            "--seed-past-years",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Keçmiş illər (2022/2023, 2023/2024): sabit tələbədə A-E+barred+qb+imtahan qarışığı.",
        )

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

        offerings_2526: dict = {}
        roles = self._assign_journal_roles(students)
        corrections: list = []
        failures: dict = {}

        if opts["seed_2025_2026"]:
            offerings_2526 = self._seed_journal_2025_2026(org, teacher, students, opts, roles)

        if opts["seed_corrections"] and offerings_2526 and roles:
            corrections = self._seed_corrections(org, teacher, offerings_2526, roles)

        if opts["seed_failures"] and offerings_2526 and roles:
            failures = self._seed_failures(org, teacher, offerings_2526, roles)

        offerings_past: dict = {}
        if opts["seed_past_years"]:
            from . import _stress_past_years_data as past_data

            offerings_past = past_data.seed_past_years(org=org, teacher=teacher, students=students)
            if not offerings_past:
                self.stdout.write("  (keçmiş illər: STR proqramı/kurikulumu tapılmadı — seed edilmədi)")

        line = "─" * 60
        self.stdout.write(self.style.SUCCESS(line))
        self.stdout.write(self.style.SUCCESS("STRESS EXAM + JOURNAL HAZIRDIR"))
        self.stdout.write(f"  İmtahan slug   : {exam.slug}")
        self.stdout.write(f"  Suallar        : {exam.questions.count()}")
        self.stdout.write(f"  Tələbə         : {len(students)}")
        if offerings_2526:
            self.stdout.write(f"  2025/2026 fənn : {', '.join(sorted(offerings_2526))}")
        if corrections:
            self.stdout.write(f"  Düzəlişlər (sarı xana) : {len(corrections)}")
        if failures:
            self.stdout.write(f"  Kəsilən (davamiyyət)   : {len(failures.get('attendance', []))}")
            self.stdout.write(f"  Kəsilən (imtahan)      : {len(failures.get('exam', []))}")
        if offerings_past:
            self.stdout.write(f"  Keçmiş illər fənn : {', '.join(sorted(offerings_past))}")
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

    # ── Registrar journal (2024/2025 — köhnə davranış, dəyişməz) ────────────────
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

    # ── Registrar journal (2025/2026 — yeni tədris ili) ──────────────────────
    def _seed_journal_2025_2026(self, org, teacher, students, opts, roles) -> dict:
        """2025/2026 Payız semestri: 2 əlavə fənn (STR102/STR103), dərslər + qeydlər.

        Köhnə (2024/2025) Program/Curriculum-u YENİDƏN İSTİFADƏ edir (bu fayldaki
        ``_seed_journal`` onları artıq yaratmışdır) — yalnız yeni semestr sətirləri
        (``CurriculumSubject``, semester_number=2) və yeni ``AcademicPeriod`` əlavə
        olunur. Qaytarır: ``{subject_code: CourseOffering}``.
        """
        from apps.registrar import services
        from apps.registrar.models import (
            CourseOffering,
            Curriculum,
            CurriculumSubject,
            Program,
            StudentAcademicRecord,
            Subject,
        )

        program = Program.objects.filter(organization=org, code="STR").first()
        curriculum = Curriculum.objects.filter(organization=org, program=program).first() if program else None
        unit = OrgUnit.objects.filter(organization=org, unit_type=OrgUnitType.GROUP).first()
        if program is None or curriculum is None or unit is None:
            self.stdout.write("  (2025/2026: STR proqramı/kurikulumu/qrupu tapılmadı — jurnal seed edilmədi)")
            return {}

        period, _created = AcademicPeriod.objects.get_or_create(
            organization=org,
            name="Payız semestri",
            academic_year="2025/2026",
            defaults={
                "period_type": AcademicPeriodType.SEMESTER,
                "start_date": datetime.date(2025, 9, 1),
                "end_date": datetime.date(2026, 1, 31),
                "is_current": True,
            },
        )
        if not period.is_current:
            # ``AcademicPeriod.save()`` digər dövrləri artıq ``is_current=False`` edir,
            # amma bura idempotent yenidən-icra (əvvəllər yaradılıb, sonra kim isə
            # ``is_current``-i dəyişib) halı üçün aydın şəkildə bərpa edir.
            period.is_current = True
            period.save(update_fields=["is_current"])
        # Köhnə tədris ilini açıq şəkildə deaktiv et — niyyəti sənədləşdirir,
        # hətta model-səviyyəli avtomatik keçidə etibar etsək belə.
        AcademicPeriod.objects.filter(organization=org, academic_year="2024/2025").exclude(pk=period.pk).update(
            is_current=False
        )

        subject2, _ = Subject.objects.get_or_create(
            organization=org, code="STR102", defaults={"name": "Stress Fənni II"}
        )
        subject3, _ = Subject.objects.get_or_create(
            organization=org, code="STR103", defaults={"name": "Stress Fənni III"}
        )
        CurriculumSubject.objects.get_or_create(
            organization=org, curriculum=curriculum, subject=subject2, semester_number=2
        )
        CurriculumSubject.objects.get_or_create(
            organization=org, curriculum=curriculum, subject=subject3, semester_number=2
        )

        for student in students:
            record = StudentAcademicRecord.objects.filter(organization=org, student=student).first()
            if record is None:
                continue
            services.enroll_mandatory_subjects(record=record, period=period, semester_number=2)

        offerings: dict = {}
        for subject in (subject2, subject3):
            offering = CourseOffering.objects.filter(
                organization=org, subject=subject, period=period, group=unit
            ).first()
            if offering is None:
                continue
            changed = []
            if offering.instructor_id != teacher.id:
                offering.instructor = teacher
                changed.append("instructor")
            if offering.lesson_hours != 60:
                offering.lesson_hours = 60
                changed.append("lesson_hours")
            if changed:
                offering.save(update_fields=changed)
            offerings[subject.code] = offering

        if not offerings:
            self.stdout.write("  (2025/2026: heç bir offering yaradılmadı — enrollment boşdur)")
            return {}

        exam_fail_ids = {s.id for s in roles["exam_fail"]} if roles else set()
        attendance_fail_ids = {s.id for s in roles["attendance_fail"]} if roles else set()

        for offering in offerings.values():
            self._seed_lessons_for_offering(org, offering, opts, exam_fail_ids, attendance_fail_ids)
        return offerings

    def _seed_lessons_for_offering(self, org, offering, opts, exam_fail_ids, attendance_fail_ids):
        """Dərslər + qeydlər — normal tələbələr üçün dolu, uyğun rollar üçün aşağı bal."""
        from apps.registrar.models import AttendanceStatus, Lesson, LessonKind, LessonMark

        enrollments = list(offering.enrollments.select_related("student").order_by("student__username"))
        start = datetime.date(2025, 10, 1)
        for i in range(opts["lessons_2526"]):
            lesson, created = Lesson.objects.get_or_create(
                organization=org,
                offering=offering,
                date=start + datetime.timedelta(days=i * 2),
                defaults={"kind": LessonKind.SEMINAR if i % 2 else LessonKind.LECTURE, "hours": 2},
            )
            if not created:
                continue
            marks = []
            for idx, enr in enumerate(enrollments):
                status = AttendanceStatus.PRESENT
                # Real jurnal görüntüsü üçün seyrək (deterministik) qayıb — davamiyyətdən
                # kəsilməsi planlanan tələbələr üçün ötürülür (onların qb-si aşağıda,
                # ``_seed_failures``-da, hədəfli şəkildə yazılır).
                if enr.student_id not in attendance_fail_ids and (idx + i) % 7 == 0:
                    status = AttendanceStatus.ABSENT
                score = None
                if lesson.kind == LessonKind.SEMINAR:
                    # İmtahandan kəsiləcək tələbələrin giriş balı da aşağı olsun ki,
                    # yekun bal (giriş + aşağı imtahan) 51-dən aşağı qalıb "F" göstərsin.
                    score = 2 if enr.student_id in exam_fail_ids else 5 + (idx % 5)
                marks.append(LessonMark(organization=org, lesson=lesson, enrollment=enr, status=status, score=score))
            LessonMark.objects.bulk_create(marks, batch_size=500, ignore_conflicts=True)

    # ── Rol təyinatı (korreksiya + kəsilmə demo-ları üçün sabit tələbələr) ──────
    def _assign_journal_roles(self, students) -> dict | None:
        """Vizual test üçün sabit tələbə rolları — ən azı 6 tələbə tələb olunur."""
        if len(students) < 6:
            return None
        return {
            "attendance_fail": students[0:2],
            "exam_fail": students[2:4],
            "correction_score": students[4],
            "correction_attendance": students[5],
        }

    # ── İmtahan Mərkəzi düzəlişləri (sarı xanalar) ───────────────────────────
    def _seed_corrections(self, org, teacher, offerings, roles) -> list:
        from apps.registrar.corrections import apply_correction
        from apps.registrar.models import (
            AttendanceStatus,
            CorrectionField,
            CorrectionReason,
            JournalCorrection,
            LessonKind,
            LessonMark,
        )

        offering = offerings.get("STR102")
        if offering is None:
            return []

        created: list = []

        # 1) Bal korreksiyası — bir seminar xanasının balını dəyişir (apellyasiya).
        score_student = roles["correction_score"]
        score_enr = offering.enrollments.filter(student=score_student).first()
        seminar_lesson = offering.lessons.filter(kind=LessonKind.SEMINAR).order_by("date").first()
        if score_enr and seminar_lesson:
            already = JournalCorrection.objects.filter(
                lesson_mark__lesson=seminar_lesson, lesson_mark__enrollment=score_enr, field=CorrectionField.SCORE
            ).exists()
            if already:
                created.append(("score", score_student.username))
            else:
                mark, _ = LessonMark.objects.update_or_create(
                    organization=org,
                    lesson=seminar_lesson,
                    enrollment=score_enr,
                    defaults={"status": AttendanceStatus.PRESENT, "score": 6},
                )
                try:
                    apply_correction(
                        mark=mark,
                        field=CorrectionField.SCORE,
                        new_score=9,
                        reason=CorrectionReason.APPEAL,
                        note="Apellyasiya komissiyası qərarı ilə bal düzəldildi (seed).",
                        document=_correction_document("bal-duzelisi.pdf"),
                        by_user=teacher,
                    )
                    created.append(("score", score_student.username))
                except Exception as exc:  # noqa: BLE001 — seed heç vaxt komandanı sındırmasın
                    self.stderr.write(f"  (corrections: bal korreksiyası tətbiq edilmədi: {exc})")

        # 2) Davamiyyət korreksiyası — qb → üzrlü (tibbi arayış).
        att_student = roles["correction_attendance"]
        att_enr = offering.enrollments.filter(student=att_student).first()
        lecture_lesson = offering.lessons.order_by("date").first()
        if att_enr and lecture_lesson:
            already = JournalCorrection.objects.filter(
                lesson_mark__lesson=lecture_lesson,
                lesson_mark__enrollment=att_enr,
                field=CorrectionField.ATTENDANCE,
            ).exists()
            if already:
                created.append(("attendance", att_student.username))
            else:
                mark, _ = LessonMark.objects.update_or_create(
                    organization=org,
                    lesson=lecture_lesson,
                    enrollment=att_enr,
                    defaults={"status": AttendanceStatus.ABSENT, "score": None},
                )
                try:
                    apply_correction(
                        mark=mark,
                        field=CorrectionField.ATTENDANCE,
                        new_status=AttendanceStatus.EXCUSED,
                        reason=CorrectionReason.MEDICAL,
                        note="Xəstəlik vərəqəsi əsasında üzrlü sayıldı (seed).",
                        document=_correction_document("tibbi-arayis.pdf"),
                        by_user=teacher,
                    )
                    created.append(("attendance", att_student.username))
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(f"  (corrections: davamiyyət korreksiyası tətbiq edilmədi: {exc})")

        return created

    # ── Kəsilən tələbələr (davamiyyət + imtahan) ─────────────────────────────
    def _seed_failures(self, org, teacher, offerings, roles) -> dict:
        from apps.registrar.gradebook import recompute_absence_hours
        from apps.registrar.models import AttendanceStatus, LessonMark, Program
        from apps.registrar.public import record_exam_result

        result: dict = {"attendance": [], "exam": []}
        program = Program.objects.filter(organization=org, code="STR").first()
        limit_percent = program.absence_limit_percent if program else 25

        # 1) Davamiyyətdən kəsilmə (barred): STR102-də limitin üstündə "qb" yazılır.
        offering_att = offerings.get("STR102")
        if offering_att is not None:
            lessons = list(offering_att.lessons.order_by("date"))
            allowed_hours = float(offering_att.lesson_hours or 0) * limit_percent / 100.0
            hours_acc = 0
            needed = 0
            for lesson in lessons:
                hours_acc += lesson.hours
                needed += 1
                if hours_acc > allowed_hours:
                    break
            target_lessons = lessons[:needed] if needed else lessons
            for student in roles["attendance_fail"]:
                enr = offering_att.enrollments.filter(student=student).first()
                if enr is None:
                    continue
                for lesson in target_lessons:
                    LessonMark.objects.update_or_create(
                        organization=org,
                        lesson=lesson,
                        enrollment=enr,
                        defaults={"status": AttendanceStatus.ABSENT, "score": None},
                    )
                recompute_absence_hours(enrollment=enr)
                result["attendance"].append(student.username)

        # 2) İmtahandan kəsilmə: STR103 üzrə aşağı imtahan balı (bridge → F).
        offering_exam = offerings.get("STR103")
        if offering_exam is not None:
            for student in roles["exam_fail"]:
                fg = record_exam_result(
                    student=student,
                    subject_id=offering_exam.subject_id,
                    organization=org,
                    score_percent=20,
                    by_user=teacher,
                )
                if fg is not None:
                    result["exam"].append(student.username)

            # Jurnalın dolu görünməsi üçün qalan (kəsilməyən) tələbələrə yaxşı imtahan
            # balı yazılır — bridge-in "keçən" yolu da vizual test edilə bilsin.
            fail_ids = {s.id for s in roles["attendance_fail"]} | {s.id for s in roles["exam_fail"]}
            for enr in offering_exam.enrollments.exclude(student_id__in=fail_ids).select_related("student"):
                record_exam_result(
                    student=enr.student,
                    subject_id=offering_exam.subject_id,
                    organization=org,
                    score_percent=70,
                    by_user=teacher,
                )

        return result
