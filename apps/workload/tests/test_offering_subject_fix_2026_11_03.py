"""Səhv fənnə bağlı jurnalın fənni YERİNDƏ düzəlir (2026-11-03).

Jurnal + yük sətri «X-2» fənnindədir, həqiqətdə «X-1» olmalıdır; jurnalda dərslər/xanalar var. Veb yolu (sətrin
fənnini dəyişmək) yeni BOŞ jurnal yaradır — ``fix_offering_subject`` isə mövcud jurnalı saxlayır: fənn yerində
dəyişir, səhv sillabus ayrılır, düzgün sillabus paylaşma ilə bağlanır, sətrin fənni dəyişir və sinxron yeni
jurnal YARATMIR.
"""

import datetime
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from apps.syllabus.models import Syllabus, SyllabusShare
from apps.syllabus.public import import_migrated_version, syllabus_for_offering_obj
from apps.workload.constants import AmendmentReason, TaskStatus
from apps.workload.models import TeacherAssignment
from apps.workload.services import offering_subject_fix as service
from apps.workload.services.offering_sync import sync_task_offerings
from apps.workload.services.row_edit import save_row_amended
from apps.workload.services.scoping import resolve_actor
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task
from core.constants import OrgUnitType

User = get_user_model()


class OfferingSubjectFixTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("osfix_admin", "osfix_admin@x.test", "pw")
        self.org = make_org("osfix", owner=self.admin)
        self.stack = make_structure(self.org, code="OSFX")
        self.period, self.group = self.stack["period"], self.stack["group"]
        self.wrong = self.stack["subject"]  # «X-2» (Yaz)
        self.wrong.name = "Riyaziyyat-2"
        self.wrong.save(update_fields=["name"])
        self.right = Subject.objects.create(organization=self.org, code="OSFX100", name="Riyaziyyat-1", ects=6)
        self.teacher = User.objects.create_user("osfix_teacher", "osfix_teacher@x.test", "pw")
        activate_member(self.org, self.teacher, "teacher", permissions=TEACHER_PERMS)
        self.student = User.objects.create_user("osfix_student", "osfix_student@x.test", "pw")
        activate_member(self.org, self.student, "student")

        self.task = make_task(self.org, self.stack["chair"], status=TaskStatus.DISTRIBUTED)
        self.row = make_row(self.task, self.stack, lecture_total=30, seminar_total=30)
        TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=self.teacher, activity="lecture", hours=30
        )
        TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=self.teacher, activity="seminar", hours=30
        )
        self.offering = CourseOffering.objects.create(
            organization=self.org,
            subject=self.wrong,
            period=self.period,
            group=self.group,
            instructor=self.teacher,
            lesson_hours=60,
        )
        enrollment = Enrollment.objects.create(organization=self.org, offering=self.offering, student=self.student)
        start = datetime.date(2026, 9, 16)
        for week in range(18):
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=start + datetime.timedelta(days=7 * week),
                kind="seminar",
                start_time=datetime.time(11, 50),
            )
            LessonMark.objects.create(
                organization=self.org, lesson=lesson, enrollment=enrollment, status="present", score=8
            )
        # Səhv sillabus — jurnalın ÖZ dosyesi, «X-2» fənni.
        import_migrated_version(
            organization=self.org,
            subject=self.wrong,
            period=self.period,
            offering=self.offering,
            author=self.teacher,
            approved_at=timezone.now(),
            section_data={"desc": {"description": "X-2"}},
        )
        self.wrong_syllabus = Syllabus.objects.get(offering=self.offering)
        # Düzgün sillabus — eyni müəllimin başqa qrupdakı «X-1» jurnalının dosyesi.
        other_group = OrgUnit.objects.create(
            organization=self.org,
            name="OSFX-237",
            slug="osfix-group-2",
            unit_type=OrgUnitType.GROUP,
            parent=self.stack["specialty"],
        )
        self.sibling = CourseOffering.objects.create(
            organization=self.org,
            subject=self.right,
            period=self.period,
            group=other_group,
            instructor=self.teacher,
            lesson_hours=60,
        )
        import_migrated_version(
            organization=self.org,
            subject=self.right,
            period=self.period,
            offering=self.sibling,
            author=self.teacher,
            approved_at=timezone.now(),
            section_data={"desc": {"description": "X-1"}},
        )
        self.right_syllabus = Syllabus.objects.get(offering=self.sibling)

    def call(self, **kwargs):
        values = {
            "offering_id": str(self.offering.pk),
            "subject_id": str(self.right.pk),
            "detach_syllabus_id": str(self.wrong_syllabus.pk),
            "attach_syllabus_id": str(self.right_syllabus.pk),
            "row_id": str(self.row.pk),
        }
        values.update(kwargs)
        return service.fix_offering_subject(organization=self.org, user=self.admin, **values)

    def group_offerings(self):
        return set(CourseOffering.objects.filter(period=self.period, group=self.group).values_list("pk", flat=True))

    def test_web_path_would_create_a_new_empty_journal(self):
        """Kontrast: sətrin fənnini adi yolla dəyişmək sinxronda YENİ boş jurnal yaradır (problemin özü)."""
        save_row_amended(
            task=self.task,
            row=self.row,
            actor=resolve_actor(self.admin, self.org),
            data={"subject_id": str(self.right.pk)},
            amend={"reason": AmendmentReason.CORRECTION, "note": "test"},
            sync_offerings=True,
        )
        fresh = CourseOffering.objects.get(subject=self.right, period=self.period, group=self.group)
        self.assertNotEqual(fresh.pk, self.offering.pk)
        self.assertFalse(Lesson.objects.filter(offering=fresh).exists())

    def test_fix_keeps_journal_moves_links_and_sync_creates_nothing(self):
        before_ids = self.group_offerings()
        protected = service.protected_hash(self.offering.pk)

        dry = self.call()
        self.assertEqual(dry["changes"], 4)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.subject_id, self.wrong.pk)  # dry-run geri qaytarıldı
        self.assertFalse(SyllabusShare.objects.filter(offering=self.offering).exists())

        result = self.call(apply=True)
        self.assertEqual(
            {k: result[k] for k in ("offering_subject_changed", "own_syllabus_detached", "share_attached")},
            {"offering_subject_changed": 1, "own_syllabus_detached": 1, "share_attached": 1},
        )
        self.assertEqual(result["row_subject_changed"], 1)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.subject_id, self.right.pk)
        self.assertEqual(self.group_offerings(), before_ids)  # yeni jurnal YOXDUR
        self.assertEqual(service.protected_hash(self.offering.pk), protected)
        self.assertEqual(Lesson.objects.filter(offering=self.offering).count(), 18)
        self.wrong_syllabus.refresh_from_db()
        self.assertIsNone(self.wrong_syllabus.offering_id)
        self.assertFalse(self.wrong_syllabus.is_active)
        self.assertEqual(SyllabusShare.objects.get(offering=self.offering).syllabus_id, self.right_syllabus.pk)
        self.assertEqual(syllabus_for_offering_obj(self.offering).pk, self.right_syllabus.pk)
        self.row.refresh_from_db()
        self.assertEqual((self.row.subject_id, self.row.subject_text), (self.right.pk, "Riyaziyyat-1"))
        receipt = AuditLog.objects.get(resource_type=service.RESOURCE, resource_id=str(self.offering.pk))
        self.assertEqual(receipt.new_values["old_subject"], str(self.wrong.pk))
        self.assertEqual(receipt.old_values["syllabus_link"]["kind"], "own")

        # Tam sənəd sinxronu (təsdiq / «Bölgünü təsdiqlə» yolu) da yeni jurnal yaratmır.
        report = sync_task_offerings(self.task, actor=resolve_actor(self.admin, self.org))
        self.assertEqual(report["created"], 0)
        self.assertEqual(self.group_offerings(), before_ids)

        again = self.call(apply=True)
        self.assertEqual(again["changes"], 0)
        self.assertEqual(
            {k: again[k] for k in ("offering_already", "detach_already", "attach_already", "row_already")},
            {"offering_already": 1, "detach_already": 1, "attach_already": 1, "row_already": 1},
        )
        self.assertEqual(AuditLog.objects.filter(resource_type=service.RESOURCE).count(), 1)

    def test_shared_wrong_syllabus_is_unshared(self):
        """Səhv sillabus başqa (X-2) jurnalın dosyesidir və bu jurnala PAYLAŞMA ilə bağlanıb — yalnız bağ silinir."""
        other = OrgUnit.objects.create(
            organization=self.org, name="OSFX-238", slug="osfix-g3", unit_type=OrgUnitType.GROUP
        )
        x2_home = CourseOffering.objects.create(
            organization=self.org, subject=self.wrong, period=self.period, group=other, instructor=self.teacher
        )
        Syllabus.objects.filter(pk=self.wrong_syllabus.pk).update(offering=x2_home)
        SyllabusShare.objects.create(organization=self.org, syllabus=self.wrong_syllabus, offering=self.offering)
        result = self.call(apply=True)
        self.assertEqual((result["share_detached"], result["share_attached"]), (1, 1))
        self.assertEqual(SyllabusShare.objects.get(offering=self.offering).syllabus_id, self.right_syllabus.pk)
        self.wrong_syllabus.refresh_from_db()
        self.assertEqual((self.wrong_syllabus.offering_id, self.wrong_syllabus.is_active), (x2_home.pk, True))

    def test_collision_with_existing_target_journal_stops_without_writes(self):
        CourseOffering.objects.create(organization=self.org, subject=self.right, period=self.period, group=self.group)
        with self.assertRaisesMessage(service.OfferingSubjectFixError, "target_offering_exists"):
            self.call(apply=True)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.subject_id, self.wrong.pk)
        self.assertTrue(Syllabus.objects.filter(pk=self.wrong_syllabus.pk, offering=self.offering).exists())

    def test_load_row_on_old_subject_must_be_moved_too(self):
        with self.assertRaisesMessage(service.OfferingSubjectFixError, "load_row_required"):
            self.call(apply=True, row_id="")

    def test_multi_group_row_is_refused(self):
        other = OrgUnit.objects.create(
            organization=self.org, name="OSFX-239", slug="osfix-g4", unit_type=OrgUnitType.GROUP
        )
        self.row.groups.add(other)
        with self.assertRaisesMessage(service.OfferingSubjectFixError, "row_has_other_groups"):
            self.call(apply=True)

    def test_command_dry_run_then_apply(self):
        def run(*extra):
            out = StringIO()
            call_command(
                "fix_offering_subject",
                "--org=osfix",
                f"--actor={self.admin.username}",
                f"--offering={self.offering.pk}",
                f"--subject={self.right.pk}",
                f"--detach-syllabus={self.wrong_syllabus.pk}",
                f"--attach-syllabus={self.right_syllabus.pk}",
                f"--row={self.row.pk}",
                *extra,
                stdout=out,
            )
            return out.getvalue()

        self.assertIn("offering_subject_fix: mode=dry_run", run())
        self.assertEqual(CourseOffering.objects.get(pk=self.offering.pk).subject_id, self.wrong.pk)
        self.assertIn("changes=4", run("--apply"))
        self.assertEqual(CourseOffering.objects.get(pk=self.offering.pk).subject_id, self.right.pk)
        self.assertIn("changes=0", run("--apply"))
        with self.assertRaisesMessage(CommandError, "subject_invalid"):
            call_command(
                "fix_offering_subject",
                "--org=osfix",
                f"--actor={self.admin.username}",
                f"--offering={self.offering.pk}",
                "--subject=not-a-uuid",
                stdout=StringIO(),
            )
