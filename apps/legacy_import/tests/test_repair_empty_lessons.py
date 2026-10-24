"""``legacy_repair_empty_lessons`` — jurnalın MƏZMUNSUZ keçmiş sütunları.

Defolt silinir YALNIZ: köçürülmüş (``created_by`` boş), keçmiş, xanasız, mövzusuz, düzəlişsiz,
kilidsiz jurnaldakı dərs. Açıq bayraqla: yalnız balsız «qb» xanalı sütun (``--include-absent-only``,
xanalar da silinir, qayıb saatı yenidən hesablanır), müəllimin keçmiş sütunu
(``--include-teacher-lessons``), kilidli jurnal (``--include-locked``). «iə»/«ü/q»/bal/mövzu/düzəliş
olan sütun, bu günün dərsi və müəllimin bu gün yaratdığı dərs HƏMİŞƏ toxunulmazdır. Dry-run heç nə
silmir; apply audit yazır və idempotentdir.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.legacy_import.services.repair_empty_lessons import AUDIT_RESOURCE, TEACHER_GRACE_DAYS
from apps.organizations.models import OrgUnit, OrgUnitType
from apps.registrar.gradebook import recompute_absence_hours_many
from apps.registrar.models import (
    AssessmentScheme,
    AttendanceStatus,
    CorrectionField,
    CorrectionReason,
    CourseOffering,
    Enrollment,
    JournalCorrection,
    Lesson,
    LessonKind,
    LessonMark,
)
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org

User = get_user_model()
COMMAND = "legacy_repair_empty_lessons"
ABSENT_ONLY = "--include-absent-only"
TEACHER = "--include-teacher-lessons"
LOCKED = "--include-locked"


class LegacyRepairEmptyLessonsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_superuser("rel_actor", "rel_actor@example.test", "test-only")
        cls.org = make_org("rel-univ", owner=cls.actor)
        cls.teacher = User.objects.create_user("rel_teacher", "rel_teacher@example.test", "pw")
        activate_member(cls.org, cls.teacher, "teacher", permissions=["course.view", "grade.input"])
        students = []
        for index in range(4):
            student = User.objects.create_user(f"rel_student{index}", f"rel_student{index}@example.test", "pw")
            activate_member(cls.org, student, "student", permissions=["course.view"], level=10)
            students.append(student)
        stack = make_academic_stack(cls.org, code="REL101")
        cls.offering = make_offering(cls.org, stack, cls.teacher)
        cls.locked_offering = make_offering(cls.org, make_academic_stack(cls.org, code="REL202"), cls.teacher)
        scheme, _ = AssessmentScheme.objects.get_or_create(organization=cls.org, offering=cls.locked_offering)
        AssessmentScheme.objects.filter(pk=scheme.pk).update(is_published=True, approval_status="approved")

        def enroll(student, offering=None, **extra):
            return Enrollment.objects.create(
                organization=cls.org, offering=offering or cls.offering, student=student, **extra
            )

        cls.first = enroll(students[0])
        cls.second = enroll(students[1])
        cls.locked_enrollment = enroll(students[2], cls.locked_offering)
        # Alt qrup birləşməsi: köhnə (mənbə) jurnalın sələf qeydiyyatı → bu jurnalın qonaq sətri.
        source_group = OrgUnit.objects.create(
            organization=cls.org, name="REL101-alt", slug="rel-univ-rel101-alt", unit_type=OrgUnitType.GROUP
        )
        cls.source_offering = CourseOffering.objects.create(
            organization=cls.org,
            subject=stack["subject"],
            period=stack["period"],
            group=source_group,
            instructor=cls.teacher,
        )
        cls.guest = enroll(students[3], source_group=source_group)
        cls.predecessor = enroll(
            students[3], cls.source_offering, status=Enrollment.Status.DROPPED, superseded_by=cls.guest
        )
        cls.past = timezone.localdate() - dt.timedelta(days=30)

        def lesson(day, *, offering=None, teacher_made=False, created_days_ago=20, **extra):
            row = Lesson.objects.create(
                organization=cls.org,
                offering=offering or cls.offering,
                date=cls.past + dt.timedelta(days=day),
                kind=LessonKind.LECTURE,
                hours=2,
                created_by=cls.teacher if teacher_made else None,
                **extra,
            )
            if teacher_made:
                created_at = timezone.now() - dt.timedelta(days=created_days_ago)
                Lesson.objects.filter(pk=row.pk).update(created_at=created_at)
            return row

        def mark(lesson_row, enrollment, status=AttendanceStatus.ABSENT, score=None):
            LessonMark.objects.create(
                organization=cls.org, lesson=lesson_row, enrollment=enrollment, status=status, score=score
            )

        # Defolt silinən: köçürülmüş, keçmiş, xanasız, mövzusuz.
        cls.empty_imported = lesson(0)
        cls.empty_synthesised = lesson(1)
        Lesson.objects.filter(pk=cls.empty_synthesised.pk).update(is_legacy_synthesised=True)
        cls.empty_whitespace_topic = lesson(2, topic="   ")
        # Yalnız «qb» (--include-absent-only).
        cls.absent_only = lesson(3)
        mark(cls.absent_only, cls.first)
        mark(cls.absent_only, cls.second)
        cls.source_absent_only = lesson(4, offering=cls.source_offering)
        mark(cls.source_absent_only, cls.predecessor)
        # Müəllimin (--include-teacher-lessons; «qb»-li olan İKİ bayraqla).
        cls.teacher_empty = lesson(5, teacher_made=True)
        # 10 gün əvvəl tarixli + 10 gün əvvəl yaradılıb — buferdən (TEACHER_GRACE_DAYS=3) kənar.
        cls.teacher_absent_only = lesson(20, teacher_made=True, created_days_ago=10)
        mark(cls.teacher_absent_only, cls.first)
        # Bufer: 2 gün əvvəl TARİXLİ (çoxdan yaradılıb) və 2 gün əvvəl YARADILAN (köhnə tarixli) — toxunulmaz.
        cls.teacher_absent_recent = lesson(28, teacher_made=True, created_days_ago=10)
        mark(cls.teacher_absent_recent, cls.second)
        cls.teacher_created_recently = lesson(15, teacher_made=True, created_days_ago=2)
        # Kilidli jurnal (--include-locked).
        cls.locked_empty = lesson(7, offering=cls.locked_offering)
        cls.locked_absent_only = lesson(8, offering=cls.locked_offering)
        mark(cls.locked_absent_only, cls.locked_enrollment)
        # HEÇ VAXT silinməz.
        cls.with_topic = lesson(9, topic="Köhnə sistemdə yazılmış mövzu")
        cls.with_present = lesson(10)
        mark(cls.with_present, cls.first)
        mark(cls.with_present, cls.second, AttendanceStatus.PRESENT)
        cls.with_score = lesson(11)
        mark(cls.with_score, cls.first)
        mark(cls.with_score, cls.second, score=Decimal("3"))
        cls.with_excused = lesson(12)
        mark(cls.with_excused, cls.first, AttendanceStatus.EXCUSED)
        cls.with_correction_trace = lesson(13)
        JournalCorrection.objects.create(
            organization=cls.org,
            lesson_mark=None,  # düzəlişin yaratdığı xana geri alınıb — iz qalır
            lesson_mark_ref=uuid.uuid4(),
            lesson_ref=cls.with_correction_trace.pk,
            enrollment_ref=cls.first.pk,
            field=CorrectionField.ATTENDANCE,
            new_status=AttendanceStatus.PRESENT,
            created_mark=True,
            reason=CorrectionReason.TECHNICAL,
            note="Düzəliş izi",
            document="journal_corrections/rel.pdf",
            corrected_by=cls.actor,
            corrected_by_name=cls.actor.username,
        )
        # Müəllim bu gün keçmiş tarixə açıb, hələ doldurur.
        cls.teacher_recent = Lesson.objects.create(
            organization=cls.org, offering=cls.offering, date=cls.past, kind=LessonKind.LECTURE, created_by=cls.teacher
        )
        cls.today_imported = Lesson.objects.create(
            organization=cls.org, offering=cls.offering, date=timezone.localdate(), kind=LessonKind.LECTURE, hours=2
        )
        mark(cls.today_imported, cls.first)
        cls.today_teacher = Lesson.objects.create(
            organization=cls.org,
            offering=cls.offering,
            date=timezone.localdate(),
            kind=LessonKind.LECTURE,
            hours=2,
            created_by=cls.teacher,
        )
        mark(cls.today_teacher, cls.second)
        recompute_absence_hours_many([cls.first, cls.second, cls.locked_enrollment, cls.predecessor, cls.guest])

    def _call(self, *args):
        out = StringIO()
        call_command(COMMAND, "--organization", self.org.slug, "--actor", self.actor.username, *args, stdout=out)
        return out.getvalue()

    def _apply(self, *args):
        return self._call("--apply", "--i-know-this-is-production", *args)

    def _exists(self, lesson):
        return Lesson.objects.filter(pk=lesson.pk).exists()

    def _hours(self, enrollment):
        return Enrollment.objects.get(pk=enrollment.pk).absence_hours

    def _always_kept(self):
        return [
            self.with_topic,
            self.with_present,
            self.with_score,
            self.with_excused,
            self.with_correction_trace,
            self.teacher_recent,
            self.teacher_absent_recent,
            self.teacher_created_recently,
            self.today_imported,
            self.today_teacher,
        ]

    def _assert_kept(self, lessons):
        for lesson in lessons:
            self.assertTrue(self._exists(lesson), lesson.date)

    def _assert_deleted(self, lessons):
        for lesson in lessons:
            self.assertFalse(self._exists(lesson), lesson.date)

    def _default_targets(self):
        return [self.empty_imported, self.empty_synthesised, self.empty_whitespace_topic]

    def test_fixture_absence_hours(self):
        # 2 saatlıq dərslər: first = absent_only + teacher_absent_only + with_present + with_score + today.
        self.assertEqual(self._hours(self.first), 10)
        # absent_only + with_score («qb» balla) + teacher_absent_recent + today_teacher.
        self.assertEqual(self._hours(self.second), 8)
        self.assertEqual(self._hours(self.guest), 2)  # sələfin mənbə jurnalındakı «qb»-si köçür

    def test_dry_run_is_the_default_and_deletes_nothing(self):
        lessons, marks = Lesson.objects.count(), LessonMark.objects.count()
        output = self._call(ABSENT_ONLY, TEACHER, LOCKED)
        self.assertEqual((Lesson.objects.count(), LessonMark.objects.count()), (lessons, marks))
        self.assertIn("DRY-RUN", output)
        # 3 tam boş + 2 «qb» + 2 müəllimin + 2 kilidli.
        self.assertRegex(output, r"SİLİNƏCƏK namizəd\s*: 9\b")
        self.assertRegex(output, r"silinəcək «qb» xanası / qayıb saatı\s*: 5 / 10\b")
        self.assertRegex(output, r"FAKTİKİ silinən\s*: 0\b")
        self.assertFalse(AuditLog.objects.filter(resource_type=AUDIT_RESOURCE).exists())

    def test_dry_run_without_flags_reports_every_category(self):
        output = self._call()
        self.assertRegex(output, r"SİLİNƏCƏK namizəd\s*: 3\b")
        self.assertRegex(output, r"köçürülmüş, tam boş \(xanasız\) keçmiş dərs\s*: 4\b")  # kilidli daxil
        self.assertRegex(output, r"yalnız «qb» xanalı keçmiş dərs\s*: 3 \(saxlanır; --include-absent-only\)")
        self.assertRegex(output, r"müəllimin tam boş keçmiş dərsi\s*: 1 \(saxlanır; --include-teacher-lessons\)")
        self.assertRegex(output, r"kilidli jurnalda\s*: 1 \(saxlanır")
        self.assertRegex(output, r"müəllim dərsi buferi \(gün\)\s*: 3 \(")
        self.assertRegex(output, r"müəllimin buferdəki dərsi\s*: 3\b")
        # Xülasə açarlarında «:» yoxdur — prod-data-ops loq süzgəci (`  açar : dəyər`) hamısını saxlayır.
        summary = output.split("===", 2)[2]
        rows = [line for line in summary.splitlines() if line.startswith("  ") and " : " in line]
        self.assertTrue(rows)
        self.assertTrue(all(":" not in line.split(" : ", 1)[0] for line in rows), rows)

    def test_apply_deletes_only_empty_imported_lessons_and_is_idempotent(self):
        output = self._apply()
        self.assertRegex(output, r"FAKTİKİ silinən\s*: 3\b")
        self._assert_deleted(self._default_targets())
        self._assert_kept(
            [*self._always_kept(), self.absent_only, self.teacher_empty, self.teacher_absent_only, self.locked_empty]
        )
        self.assertEqual(self._hours(self.first), 10)

        audit = AuditLog.objects.get(resource_type=AUDIT_RESOURCE)
        self.assertEqual(audit.resource_id, str(self.offering.pk))
        self.assertEqual(audit.old_values["count"], 3)
        self.assertEqual(
            {row["id"] for row in audit.old_values["lessons"]}, {str(lesson.pk) for lesson in self._default_targets()}
        )
        self.assertEqual({row["category"] for row in audit.old_values["lessons"]}, {"empty"})

        again = self._apply()
        self.assertRegex(again, r"FAKTİKİ silinən\s*: 0\b")
        self.assertEqual(AuditLog.objects.filter(resource_type=AUDIT_RESOURCE).count(), 1)

    def test_absent_only_columns_are_deleted_with_their_marks_and_absence_hours_follow(self):
        output = self._apply(ABSENT_ONLY)
        self.assertRegex(output, r"FAKTİKİ silinən\s*: 5\b")
        self.assertRegex(output, r"tam boş / yalnız «qb» / müəllimin\s*: 3 / 2 / 0\b")
        self.assertRegex(output, r"silinən «qb» xanası / qayıb saatı\s*: 3 / 6\b")
        self._assert_deleted([*self._default_targets(), self.absent_only, self.source_absent_only])
        self._assert_kept([*self._always_kept(), self.teacher_empty, self.teacher_absent_only, self.locked_absent_only])
        self.assertFalse(LessonMark.objects.filter(lesson_id__in=[self.absent_only.pk, self.source_absent_only.pk]))
        # Real xanalı sütunların xanaları toxunulmazdır.
        self.assertEqual(LessonMark.objects.filter(lesson__in=[self.with_present, self.with_score]).count(), 4)
        self.assertEqual(self._hours(self.first), 8)
        self.assertEqual(self._hours(self.second), 6)
        self.assertEqual(self._hours(self.predecessor), 0)
        self.assertEqual(self._hours(self.guest), 0)  # sələfin xanası silindi → köçən saat da

        audit = AuditLog.objects.get(resource_type=AUDIT_RESOURCE, resource_id=str(self.offering.pk))
        absent_row = next(row for row in audit.old_values["lessons"] if row["id"] == str(self.absent_only.pk))
        self.assertEqual(absent_row["category"], "absent_only")
        self.assertEqual(
            sorted((mark["student_id"], mark["status"]) for mark in absent_row["marks"]),
            sorted((enrollment.student_id, "absent") for enrollment in (self.first, self.second)),
        )
        self.assertEqual(audit.old_values["marks"], 2)

        self.assertRegex(self._apply(ABSENT_ONLY), r"FAKTİKİ silinən\s*: 0\b")

    def test_teacher_lessons_need_their_own_flag(self):
        self._apply(ABSENT_ONLY)
        self._assert_kept([self.teacher_empty, self.teacher_absent_only])

        self._apply(TEACHER)
        self._assert_deleted([self.teacher_empty])
        self._assert_kept([self.teacher_absent_only, *self._always_kept()])  # «qb»-li üçün İKİ bayraq

        output = self._apply(TEACHER, ABSENT_ONLY)
        self.assertRegex(output, r"tam boş / yalnız «qb» / müəllimin\s*: 0 / 0 / 1\b")
        self._assert_deleted([self.teacher_absent_only])
        self._assert_kept(self._always_kept())
        self.assertEqual(self._hours(self.first), 6)
        audit = AuditLog.objects.filter(resource_type=AUDIT_RESOURCE).order_by("-created_at").first()
        row = audit.old_values["lessons"][0]
        self.assertEqual((row["category"], row["created_by_id"]), ("teacher", self.teacher.pk))

    def test_teacher_grace_buffer_protects_recently_dated_or_created_lessons(self):
        self.assertEqual(TEACHER_GRACE_DAYS, 3)
        output = self._apply(TEACHER, ABSENT_ONLY)
        self.assertRegex(output, r"müəllimin buferdəki dərsi\s*: 3\b")
        # 10 gün əvvəl tarixli + yaradılan «qb»-li dərs silinir; 2 gün əvvəl tarixli / yaradılan qalır.
        self._assert_deleted([self.teacher_empty, self.teacher_absent_only])
        self._assert_kept([self.teacher_absent_recent, self.teacher_created_recently, self.teacher_recent])
        self.assertEqual(LessonMark.objects.filter(lesson=self.teacher_absent_recent).count(), 1)
        self.assertEqual(self._hours(self.second), 6)  # yalnız absent_only-nin 2 saatı düşdü

    def test_locked_journals_need_an_explicit_flag(self):
        self._apply(ABSENT_ONLY)
        self._assert_kept([self.locked_empty, self.locked_absent_only])

        self._apply(LOCKED, "--batch-size", "1")
        self._assert_deleted([self.locked_empty])
        self._assert_kept([self.locked_absent_only])

        self._apply(LOCKED, ABSENT_ONLY)
        self._assert_deleted([self.locked_absent_only])
        self.assertEqual(self._hours(self.locked_enrollment), 0)
        self._assert_kept(self._always_kept())

    def test_full_owner_run_keeps_every_column_with_real_content(self):
        output = self._apply(LOCKED, ABSENT_ONLY, TEACHER)
        self.assertRegex(output, r"FAKTİKİ silinən\s*: 9\b")
        self.assertRegex(output, r"tam boş / yalnız «qb» / müəllimin\s*: 4 / 3 / 2\b")
        self._assert_kept(self._always_kept())
        self.assertEqual(LessonMark.objects.filter(lesson=self.today_imported).count(), 1)
        self.assertEqual(self._hours(self.first), 6)  # with_present + with_score + today
        self.assertEqual(self._hours(self.second), 6)  # with_score («qb» balla) + buferdəki müəllim dərsi + today
        self.assertRegex(self._apply(LOCKED, ABSENT_ONLY, TEACHER), r"FAKTİKİ silinən\s*: 0\b")

    def test_limit_caps_the_number_of_deleted_lessons(self):
        self._apply("--limit", "2", "--batch-size", "1")
        self.assertEqual([self._exists(lesson) for lesson in self._default_targets()].count(False), 2)

    def test_before_cannot_reach_today_or_the_future(self):
        tomorrow = (timezone.localdate() + dt.timedelta(days=1)).isoformat()
        with self.assertRaises(CommandError):
            self._call("--before", tomorrow)
        self.assertRegex(
            self._call("--before", self.past.isoformat(), ABSENT_ONLY, TEACHER, LOCKED), r"SİLİNƏCƏK namizəd\s*: 0\b"
        )
