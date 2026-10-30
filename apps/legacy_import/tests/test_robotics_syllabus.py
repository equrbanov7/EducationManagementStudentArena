"""Fresh yükə bağlı own-source recovery; saat, müəllif və mövcud məzmun qorunur."""

import datetime as dt
import hashlib
import io
import json
import tempfile

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.legacy_import.services import robotics_syllabus as recovery
from apps.legacy_import.services.syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from apps.syllabus.models import Syllabus
from apps.syllabus.public import section_data_map
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from core.rls import bypass_rls


def plan():
    spec = recovery.SPEC
    source = dict(
        id=spec.source_syllabus,
        teacher_id=spec.source_author,
        lesson_id=spec.source_lesson,
        uniqid=spec.uniqid,
        ders_saati=60,
        language="en",
        active=1,
        week=[
            dict(
                id=128240 + i,
                uniqid=spec.uniqid,
                movzu=f"Robot topic {i}",
                muh_saat="2",
                sem_saat="2",
                praktiki_saat="0",
                lab_saat="0",
                qeyd="Original source note",
            )
            for i in range(15)
        ],
        sections={table: [[1, f"Original {table}"]] for table in SYLLABUS_SECTION_CONTRACTS},
    )
    source["sections"]["sillabus_serbest_is"] = [[i, f"Original self-work {i}"] for i in range(4)]
    source["sections"].pop("sillabus_imtahan_suallari")  # Actual7715 has no exam-question rows.
    return dict(
        format=spec.format,
        source=source,
        source_journal=dict(
            id=spec.journal,
            teacher_id=spec.source_author,
            lesson_id=spec.journal_lesson,
            sillabus_id=spec.source_syllabus,
        ),
    )


class RoboticsSyllabusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        spec = recovery.SPEC
        User = get_user_model()
        cls.actor = User.objects.create_superuser("robot_restore", "restore@example.test", "test")
        with bypass_rls():
            cls.org = Organization.objects.create(
                pk=spec.organization,
                name="QKU",
                slug="qku",
                org_type="university",
                owner=cls.actor,
                status="active",
                is_active=True,
            )
            cls.author = User.objects.create_user(pk=spec.author, username="own.robotics")
            UserProfile.objects.filter(user=cls.author).update(organization=cls.org)
            Membership.objects.create(user=cls.author, organization=cls.org, role=cls.org.roles.get(name="teacher"))
            period = AcademicPeriod.objects.create(
                pk=spec.period,
                organization=cls.org,
                academic_year="2026/2027",
                name="Payız",
                period_type="semester",
                start_date=dt.date(2026, 9, 1),
                end_date=dt.date(2027, 1, 31),
                is_current=True,
            )
            subject = Subject.objects.create(organization=cls.org, code=spec.subject_code, name="Sənaye robotları")
            group = OrgUnit.objects.create(
                pk=recovery.GROUP,
                organization=cls.org,
                name="233 CM ing",
                slug="robot-group",
                unit_type="group",
            )
            chair = OrgUnit.objects.create(organization=cls.org, name="Mexanika", slug="robot-chair", unit_type="chair")
            task = TeachingTask.objects.create(
                organization=cls.org, academic_year="2026/2027", chair=chair, status="distributed"
            )
            cls.row = TeachingTaskRow.objects.create(
                pk=recovery.ROW,
                organization=cls.org,
                task=task,
                subject=subject,
                period=period,
                season="fall",
                lecture_plan=30,
                lecture_total=30,
                seminar_plan=30,
                seminar_total=30,
                union_count=1,
                subgroup_count=1,
                total_hours=60,
            )
            cls.row.groups.add(group)
            for activity in ("lecture", "seminar"):
                TeacherAssignment.objects.create(
                    organization=cls.org, row=cls.row, teacher=cls.author, activity=activity, hours=30
                )
            cls.offering = CourseOffering.objects.create(
                pk=spec.offering,
                organization=cls.org,
                subject=subject,
                period=period,
                group=group,
                instructor=cls.author,
                lesson_hours=60,
            )
            student = User.objects.create_user(username="robot.student")
            enrollment = Enrollment.objects.create(organization=cls.org, offering=cls.offering, student=student)
            lesson = Lesson.objects.create(
                organization=cls.org,
                offering=cls.offering,
                date=dt.date(2026, 10, 20),
                kind="seminar",
                hours=2,
                topic="Teacher original",
                instructor=cls.author,
                created_by=cls.author,
            )
            cls.mark = LessonMark.objects.create(
                organization=cls.org, lesson=lesson, enrollment=enrollment, score=9, entered_by=cls.author
            )

    def run_command(self, *, data=None, apply=True, undo="", case="robotics"):
        out = io.StringIO()
        raw = json.dumps(data or plan()).encode()
        with tempfile.NamedTemporaryFile(suffix=".json") as stream:
            stream.write(raw)
            stream.flush()
            args = dict(org="qku", actor=self.actor.username, apply=apply, stdout=out, case=case)
            args.update({"undo": undo} if undo else {"file": stream.name, "sha256": hashlib.sha256(raw).hexdigest()})
            call_command("recover_workload_syllabi", **args)
        return out.getvalue()

    def test_dry_apply_repeat_undo_preserve_existing_journal(self):
        before = list(LessonMark.objects.filter(pk=self.mark.pk).values())
        self.assertIn("topics_restored=15", self.run_command(apply=False))
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())
        output = self.run_command()
        syllabus = Syllabus.objects.get(offering=self.offering)
        version = syllabus.current_version
        self.assertEqual(syllabus.author_id, recovery.AUTHOR)
        self.assertEqual(version.status, "approved")
        self.assertEqual(version.approval_source, "migration")
        self.assertIsNone(version.approved_by_id)
        sections = section_data_map(version)
        self.assertEqual(len(sections["week"]["rows"]), 15)
        self.assertEqual(len(sections["self"]["topics"]), 4)
        self.assertEqual(sum(row["lecture"] for row in sections["week"]["rows"]), 30)
        self.assertEqual(sum(row["seminar"] for row in sections["week"]["rows"]), 30)
        self.assertIn("already_present=1", self.run_command())
        self.assertEqual(before, list(LessonMark.objects.filter(pk=self.mark.pk).values()))
        self.run_command(undo=output.split("batch=")[1].strip())
        syllabus.refresh_from_db()
        self.assertFalse(syllabus.is_active)
        self.assertEqual(before, list(LessonMark.objects.filter(pk=self.mark.pk).values()))

    def test_different_case_or_source_language_cannot_restore_here(self):
        with self.assertRaisesMessage(Exception, "journal_source_scope"):
            self.run_command(case="bilal")
        data = plan()
        data["source"]["language"] = "az"
        with self.assertRaisesMessage(Exception, "source_language_scope"):
            self.run_command(data=data)
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())

    def test_fresh_load_assignment_or_unit_change_blocks_restore(self):
        TeacherAssignment.objects.filter(row=self.row, activity="seminar").update(hours=15)
        with self.assertRaisesMessage(Exception, "live_workload_scope"):
            self.run_command()
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())

    def test_source_contact_hours_cannot_be_relabelled(self):
        data = plan()
        data["source"]["week"][0]["sem_saat"] = "0"
        with self.assertRaisesMessage(Exception, "source_hour_scope"):
            self.run_command(data=data)
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())

    def test_only_verified_empty_exam_table_may_be_absent(self):
        data = plan()
        data["source"]["sections"].pop("sillabus_tesviri_ve_meqsedi")
        with self.assertRaisesMessage(Exception, "section_source_scope"):
            self.run_command(data=data)
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())
