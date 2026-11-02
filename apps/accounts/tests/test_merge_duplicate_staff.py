"""``merge_duplicate_staff`` (sahib 2026-11-03): eyni müəllimin dublikat işçi hesabı → əsas hesab.

Hal (prod): jurnal ``handover`` ilə əsas hesaba keçib (yalnız ``CourseOffering.instructor``), dərslərin müəllifi və
sillabusun sahibi isə bloklu dublikatdır — kabinetdə «Adınıza keçirilmiş: 0 dərs». Testlər sayın HANSI sahədən
oxunduğunu sübut edir: ``teacher_journal_list.attach`` → ``Lesson.instructor`` (köçürmədən əvvəl 0, sonra düzgün say).
"""

from __future__ import annotations

import datetime
import io
import re

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import Membership
from apps.registrar.models import CourseOffering, Enrollment, JournalShare, Lesson, LessonMark
from apps.registrar.page_contexts import journal_list_context
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.workload.constants import TaskStatus
from apps.workload.models import TeacherAssignment
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task
from core.rls import bypass_rls

User = get_user_model()
LINE_RE = re.compile(r"^staff_merge(_left)?: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
REASON = "Eyni müəllimin dublikat işçi hesabı — sahibin tapşırığı (test)"


def _named(user, first, last, patronymic):
    User.objects.filter(pk=user.pk).update(first_name=first, last_name=last)
    profile = user.profile
    profile.patronymic = patronymic
    profile.save(update_fields=["patronymic"])


class MergeDuplicateStaffTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("staff-merge")
            cls.admin = User.objects.create_superuser("stf_admin", "stf_admin@x.test", "pw")
            cls.stack = make_structure(cls.org, code="SM")
            cls.task = make_task(cls.org, cls.stack["chair"], status=TaskStatus.AMENDED)
            cls.row = make_row(cls.task, cls.stack, lecture_total=30, seminar_total=60)
            cls.target = User.objects.create_user("jale.qeniyeva")
            cls.source = User.objects.create_user("jalelifelong.qeniyevalifelong")
            cls.other = User.objects.create_user("stf-other")
            for user in (cls.target, cls.source, cls.other):
                activate_member(cls.org, user, "teacher", permissions=TEACHER_PERMS)
            _named(cls.target, "Jalə", "Qəniyeva", "Əli")
            _named(cls.source, "JALƏ", "QƏNİYEVA", "Əli")  # köhnə sistem yazılışı — eyni şəxs
            # «Əcnəbilər» jurnalı artıq təhvil verilib: sahib əsas hesabdır, yük təyinatı da onundur.
            cls.offering = CourseOffering.objects.create(
                organization=cls.org,
                subject=cls.stack["subject"],
                group=cls.stack["group"],
                period=cls.stack["period"],
                instructor=cls.target,
            )
            TeacherAssignment.objects.create(
                organization=cls.org, row=cls.row, teacher=cls.target, activity="seminar", hours=30
            )
            # Dublikatın qalan yük sətirləri: biri boşdur (köçür), biri hədəflə eynidir (toqquşma — qalır).
            cls.lecture_assignment = TeacherAssignment.objects.create(
                organization=cls.org, row=cls.row, teacher=cls.source, activity="lecture", hours=30
            )
            cls.clash_assignment = TeacherAssignment.objects.create(
                organization=cls.org, row=cls.row, teacher=cls.source, activity="seminar", hours=30
            )
            today = timezone.localdate()
            cls.lessons = [
                Lesson.objects.create(
                    organization=cls.org,
                    offering=cls.offering,
                    date=today - datetime.timedelta(days=7 * index + 1),
                    kind="seminar",
                    hours=2,
                    instructor=cls.source,
                    created_by=cls.source,
                )
                for index in range(3)
            ]
            student = User.objects.create_user("stf-student")
            activate_member(cls.org, student, "student", permissions=[])
            enrollment = Enrollment.objects.create(organization=cls.org, offering=cls.offering, student=student)
            cls.mark = LessonMark.objects.create(
                organization=cls.org,
                lesson=cls.lessons[0],
                enrollment=enrollment,
                status="present",
                score=7,
                entered_by=cls.source,
            )
            cls.syllabus = Syllabus.objects.create(
                organization=cls.org,
                subject=cls.stack["subject"],
                period=cls.stack["period"],
                offering=cls.offering,
                chair_unit=cls.stack["chair"],
                author=cls.source,
            )
            cls.version = SyllabusVersion.objects.create(
                organization=cls.org,
                syllabus=cls.syllabus,
                major=1,
                minor=0,
                created_by=cls.source,
                submitted_by=cls.source,
            )
            SyllabusSection.objects.create(
                organization=cls.org, version=cls.version, section_id="desc", data={}, updated_by=cls.source
            )
            # Semestrsiz «baza sillabus»: hədəfdə eyni fənn üzrə biri artıq var → unikallıq toqquşması, qalır.
            cls.base_clash = Syllabus.objects.create(
                organization=cls.org, subject=cls.stack["subject"], chair_unit=cls.stack["chair"], author=cls.source
            )
            Syllabus.objects.create(
                organization=cls.org, subject=cls.stack["subject"], chair_unit=cls.stack["chair"], author=cls.target
            )
            shared_stack = make_structure(cls.org, code="SM2")
            shared = CourseOffering.objects.create(
                organization=cls.org,
                subject=shared_stack["subject"],
                group=shared_stack["group"],
                period=shared_stack["period"],
                instructor=cls.other,
            )
            cls.share = JournalShare.objects.create(
                organization=cls.org, offering=shared, teacher=cls.source, kinds=["seminar"], source="legacy"
            )
            # Dublikat bloklu (əvvəlki birləşdirmə onu söndürüb), heç vaxt daxil olmayıb.
            User.objects.filter(pk=cls.source.pk).update(is_active=False, last_login=None)
            Membership.objects.filter(user=cls.source).update(is_active=False)

    def _run(self, *args, source=None, target=None):
        out = io.StringIO()
        call_command(
            "merge_duplicate_staff",
            "--org",
            self.org.slug,
            "--actor",
            self.admin.username,
            "--source-user",
            str(source or self.source.pk),
            "--target-user",
            str(target or self.target.pk),
            "--reason",
            REASON,
            *args,
            stdout=out,
        )
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, LINE_RE)  # stdout-a YALNIZ saylar — şəxs adı yox
            prefix, _sep, rest = line.partition(": ")
            for pair in rest.split(" "):
                key, value = pair.split("=")
                counts[f"left:{key}" if prefix.endswith("_left") else key] = value
        return counts

    def _own_row(self):
        request = RequestFactory().get("/jurnal/", {"year": ""})
        request.user = self.target
        request.organization = self.org
        rows = [o for o in journal_list_context(self.target, request)["offerings"] if o.pk == self.offering.pk]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_held_count_reads_lesson_instructor_and_merge_fixes_it(self):
        with bypass_rls():
            before = self._own_row()
            # Jurnal əsas hesabındır, amma «Adınıza keçirilmiş» Lesson.instructor-dan oxunur → 0.
            self.assertTrue(before.journal_is_current_load)
            self.assertEqual((before.journal_own_lessons, before.journal_own_hours), (0, 0))

            dry = self._run()
            self.assertEqual(dry["mode"], "dry_run")
            self.assertEqual(dry["registrar_lesson_instructor_moved"], "3")
            self.assertEqual(Lesson.objects.filter(instructor=self.source).count(), 3)  # dry-run yazmır
            self.assertFalse(AuditLog.objects.filter(resource_type="accounts.staff_merge").exists())

            counts = self._run("--apply")
            after = self._own_row()
            self.assertEqual((after.journal_own_lessons, after.journal_own_hours), (3, 6))

        self.assertEqual(counts["mode"], "apply")
        self.assertTrue(counts["batch"].startswith("stfmerge-"))
        expected = {
            "registrar_lesson_instructor_moved": "3",
            "registrar_lesson_created_by_moved": "3",
            "registrar_courseoffering_instructor_moved": "0",  # artıq təhvil verilib
            "registrar_journalshare_teacher_moved": "1",
            "workload_teacherassignment_teacher_moved": "1",
            "workload_teacherassignment_teacher_conflict": "1",
            "syllabus_syllabus_author_moved": "1",
            "syllabus_syllabus_author_conflict": "1",
            "syllabus_syllabusversion_created_by_moved": "1",
            "syllabus_syllabusversion_submitted_by_moved": "1",
            "syllabus_syllabussection_updated_by_moved": "1",
            "source_blocked_now": "0",
            "source_blocked": "1",
        }
        self.assertEqual({key: counts[key] for key in expected}, expected)
        with bypass_rls():
            self.syllabus.refresh_from_db()
            self.version.refresh_from_db()
            self.assertEqual(self.syllabus.author_id, self.target.pk)
            self.assertEqual((self.version.created_by_id, self.version.submitted_by_id), (self.target.pk,) * 2)
            self.assertEqual(JournalShare.objects.get(pk=self.share.pk).teacher_id, self.target.pk)
            self.assertEqual(TeacherAssignment.objects.get(pk=self.lecture_assignment.pk).teacher_id, self.target.pk)
            self.assertEqual(TeacherAssignment.objects.get(pk=self.clash_assignment.pk).teacher_id, self.source.pk)
            self.assertEqual(Syllabus.objects.get(pk=self.base_clash.pk).author_id, self.source.pk)
            # Bal/davamiyyət dəyərinə və onun daxil edəninə toxunulmur.
            mark = LessonMark.objects.get(pk=self.mark.pk)
            self.assertEqual((mark.score, mark.status, mark.entered_by_id), (7, "present", self.source.pk))
            self.assertFalse(User.objects.get(pk=self.source.pk).is_active)
            audit = AuditLog.objects.filter(resource_type="accounts.staff_merge", resource_id=counts["batch"])
            lesson_rows = audit.get(resource_repr="registrar.Lesson.instructor").changes
            self.assertEqual(sorted(lesson_rows["ids"]), sorted(str(lesson.pk) for lesson in self.lessons))
            self.assertEqual((lesson_rows["from_user_id"], lesson_rows["to_user_id"]), (self.source.pk, self.target.pk))
            self.assertTrue(AuditLog.objects.filter(resource_type="accounts.staff_merge_batch").exists())
        # Qalan istinadlar gizli deyil: bal xanasının daxil edəni və toqquşan sətirlər saylarla.
        self.assertEqual(counts["left:registrar_lessonmark_entered_by"], "1")
        self.assertEqual(counts["left:workload_teacherassignment_teacher"], "1")

        again = self._run("--apply")
        self.assertEqual(again["moved"], "0")
        self.assertNotIn("batch", again)

    def test_name_mismatch_needs_explicit_force(self):
        with bypass_rls():
            _named(self.source, "Jalə Lifelong", "Qəniyeva Lifelong", "Əli")
        with self.assertRaisesMessage(CommandError, "name_mismatch"):
            self._run()
        forced = self._run("--force-name-mismatch")
        self.assertEqual(forced["registrar_lesson_instructor_moved"], "3")

    def test_active_logged_in_source_is_refused(self):
        with bypass_rls():
            User.objects.filter(pk=self.source.pk).update(is_active=True, last_login=timezone.now())
        with self.assertRaisesMessage(CommandError, "source_active_with_login"):
            self._run()

    def test_active_never_logged_in_source_ends_blocked(self):
        with bypass_rls():
            User.objects.filter(pk=self.source.pk).update(is_active=True, last_login=None)
            counts = self._run("--apply")
            self.assertEqual((counts["source_blocked_now"], counts["source_blocked"]), ("1", "1"))
            self.assertFalse(User.objects.get(pk=self.source.pk).is_active)

    def test_other_gates(self):
        with self.assertRaisesMessage(CommandError, "same_user"):
            self._run(source=self.target.pk, target=self.target.pk)
        with self.assertRaisesMessage(CommandError, "target_not_active"):
            self._run(source=self.target.pk, target=self.source.pk)
        with self.assertRaisesMessage(CommandError, "reason_required"):
            call_command(
                "merge_duplicate_staff",
                "--org",
                self.org.slug,
                "--actor",
                self.admin.username,
                "--source-user",
                str(self.source.pk),
                "--target-user",
                str(self.target.pk),
                stdout=io.StringIO(),
            )
        with self.assertRaisesMessage(CommandError, "actor_must_be_active_superuser"):
            call_command(
                "merge_duplicate_staff",
                "--org",
                self.org.slug,
                "--actor",
                self.target.username,
                "--source-user",
                "1",
                "--target-user",
                "2",
                stdout=io.StringIO(),
            )
