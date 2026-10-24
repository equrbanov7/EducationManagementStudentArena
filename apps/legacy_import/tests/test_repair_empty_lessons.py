"""``legacy_repair_empty_lessons`` — köçürmədən qalan TAM BOŞ jurnal sütunları.

Silinir YALNIZ: köçürülmüş (``created_by`` boş), keçmiş, xanasız, mövzusuz, düzəlişsiz,
kilidsiz jurnaldakı dərs. Müəllimin boş dərsi, bu günün dərsi, mövzulu / xanalı /
düzəlişli dərs və (defolt) kilidli jurnal TOXUNULMAZDIR. Dry-run heç nə silmir; apply
audit yazır və idempotentdir.
"""

from __future__ import annotations

import datetime as dt
import uuid
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.legacy_import.services.repair_empty_lessons import AUDIT_RESOURCE
from apps.registrar.models import (
    AssessmentScheme,
    AttendanceStatus,
    CorrectionField,
    CorrectionReason,
    Enrollment,
    JournalCorrection,
    Lesson,
    LessonKind,
    LessonMark,
)
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org

User = get_user_model()
COMMAND = "legacy_repair_empty_lessons"


class LegacyRepairEmptyLessonsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_superuser("rel_actor", "rel_actor@example.test", "test-only")
        cls.org = make_org("rel-univ", owner=cls.actor)
        cls.teacher = User.objects.create_user("rel_teacher", "rel_teacher@example.test", "pw")
        cls.student = User.objects.create_user("rel_student", "rel_student@example.test", "pw")
        activate_member(cls.org, cls.teacher, "teacher", permissions=["course.view", "grade.input"])
        activate_member(cls.org, cls.student, "student", permissions=["course.view"], level=10)
        cls.offering = make_offering(cls.org, make_academic_stack(cls.org, code="REL101"), cls.teacher)
        cls.locked_offering = make_offering(cls.org, make_academic_stack(cls.org, code="REL202"), cls.teacher)
        scheme, _ = AssessmentScheme.objects.get_or_create(organization=cls.org, offering=cls.locked_offering)
        AssessmentScheme.objects.filter(pk=scheme.pk).update(is_published=True, approval_status="approved")
        cls.enrollment = Enrollment.objects.create(organization=cls.org, offering=cls.offering, student=cls.student)
        cls.past = timezone.localdate() - dt.timedelta(days=30)

        def lesson(day, *, offering=None, **extra):
            return Lesson.objects.create(
                organization=cls.org,
                offering=offering or cls.offering,
                date=cls.past + dt.timedelta(days=day),
                kind=LessonKind.LECTURE,
                hours=2,
                **extra,
            )

        # Silinməli: köçürülmüş, keçmiş, xanasız, mövzusuz.
        cls.empty_imported = lesson(0)
        cls.empty_synthesised = lesson(1)
        Lesson.objects.filter(pk=cls.empty_synthesised.pk).update(is_legacy_synthesised=True)
        cls.empty_whitespace_topic = lesson(2, topic="   ")
        # Saxlanmalı.
        cls.with_topic = lesson(3, topic="Köhnə sistemdə yazılmış mövzu")
        cls.with_mark = lesson(4)
        LessonMark.objects.create(
            organization=cls.org, lesson=cls.with_mark, enrollment=cls.enrollment, status=AttendanceStatus.ABSENT
        )
        cls.teacher_empty = lesson(5, created_by=cls.teacher)  # müəllim açıb, hələ işarələməyib
        cls.with_correction_trace = lesson(6)
        JournalCorrection.objects.create(
            organization=cls.org,
            lesson_mark=None,  # düzəlişin yaratdığı xana geri alınıb — iz qalır
            lesson_mark_ref=uuid.uuid4(),
            lesson_ref=cls.with_correction_trace.pk,
            enrollment_ref=cls.enrollment.pk,
            field=CorrectionField.ATTENDANCE,
            new_status=AttendanceStatus.PRESENT,
            created_mark=True,
            reason=CorrectionReason.TECHNICAL,
            note="Düzəliş izi",
            document="journal_corrections/rel.pdf",
            corrected_by=cls.actor,
            corrected_by_name=cls.actor.username,
        )
        cls.today_imported = Lesson.objects.create(
            organization=cls.org, offering=cls.offering, date=timezone.localdate(), kind=LessonKind.LECTURE
        )
        cls.locked_empty = lesson(7, offering=cls.locked_offering)

    def _call(self, *args):
        out = StringIO()
        call_command(COMMAND, "--organization", self.org.slug, "--actor", self.actor.username, *args, stdout=out)
        return out.getvalue()

    def _apply(self, *args):
        return self._call("--apply", "--i-know-this-is-production", *args)

    def _exists(self, lesson):
        return Lesson.objects.filter(pk=lesson.pk).exists()

    def _kept(self):
        return [
            self.with_topic,
            self.with_mark,
            self.teacher_empty,
            self.with_correction_trace,
            self.today_imported,
        ]

    def test_dry_run_is_the_default_and_deletes_nothing(self):
        before = Lesson.objects.count()
        output = self._call()
        self.assertEqual(Lesson.objects.count(), before)
        self.assertIn("DRY-RUN", output)
        self.assertRegex(output, r"SİLİNƏCƏK namizəd\s*: 3\b")
        self.assertRegex(output, r"FAKTİKİ silinən\s*: 0\b")
        self.assertFalse(AuditLog.objects.filter(resource_type=AUDIT_RESOURCE).exists())

    def test_apply_deletes_only_empty_imported_lessons_and_is_idempotent(self):
        output = self._apply()
        self.assertRegex(output, r"FAKTİKİ silinən\s*: 3\b")
        for lesson in (self.empty_imported, self.empty_synthesised, self.empty_whitespace_topic):
            self.assertFalse(self._exists(lesson), lesson.date)
        for lesson in [*self._kept(), self.locked_empty]:
            self.assertTrue(self._exists(lesson), lesson.date)
        self.assertEqual(LessonMark.objects.filter(lesson=self.with_mark).count(), 1)

        audit = AuditLog.objects.get(resource_type=AUDIT_RESOURCE)
        self.assertEqual(audit.resource_id, str(self.offering.pk))
        self.assertEqual(audit.old_values["count"], 3)
        self.assertEqual(
            {row["id"] for row in audit.old_values["lessons"]},
            {str(self.empty_imported.pk), str(self.empty_synthesised.pk), str(self.empty_whitespace_topic.pk)},
        )

        again = self._apply()
        self.assertRegex(again, r"FAKTİKİ silinən\s*: 0\b")
        self.assertEqual(AuditLog.objects.filter(resource_type=AUDIT_RESOURCE).count(), 1)

    def test_locked_journals_need_an_explicit_flag(self):
        self.assertRegex(self._call(), r"kilidli jurnalda\s*: 1 \(saxlanır")
        self._apply("--include-locked", "--batch-size", "1")
        self.assertFalse(self._exists(self.locked_empty))
        for lesson in self._kept():
            self.assertTrue(self._exists(lesson), lesson.date)

    def test_limit_caps_the_number_of_deleted_lessons(self):
        self._apply("--limit", "2", "--batch-size", "1")
        targets = (self.empty_imported, self.empty_synthesised, self.empty_whitespace_topic)
        self.assertEqual([self._exists(lesson) for lesson in targets].count(False), 2)

    def test_before_cannot_reach_today_or_the_future(self):
        tomorrow = (timezone.localdate() + dt.timedelta(days=1)).isoformat()
        with self.assertRaises(CommandError):
            self._call("--before", tomorrow)
        self.assertRegex(self._call("--before", self.past.isoformat()), r"SİLİNƏCƏK namizəd\s*: 0\b")
