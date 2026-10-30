"""The reviewed geometry restores load without rewriting existing academic data."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.workload.models import TeachingTask, TeachingTaskRow
from apps.workload.services import reviewed_batch as repair
from apps.workload.services import reviewed_source_geometry as geometry
from apps.workload.services.reviewed_batch_manifest import ORG, YEAR, select_manifest
from apps.workload.services.sbio235_state import RepairError, records
from core.rls import apply_rls_request_context, reset_rls_context

from .test_reviewed_source_geometry import entry


@override_settings(RLS_TRANSACTION_SCOPED=True)
class ReviewedSourceGeometryDatabaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser("geometry_admin", "geometry@x.test", "pw")
        cls.org = Organization.objects.create(
            pk=ORG, name="QKU", slug="qku", owner=cls.admin, org_type="university", status="active", is_active=True
        )
        faculty = OrgUnit.objects.create(organization=cls.org, name="School", slug="school", unit_type="faculty")
        cls.chair = OrgUnit.objects.create(
            organization=cls.org, name="Chair", slug="chair", unit_type="chair", parent=faculty
        )
        specialty = OrgUnit.objects.create(
            organization=cls.org, name="Specialty", slug="specialty", unit_type="specialty", parent=faculty
        )
        cls.teacher = User.objects.create_user(
            pk=geometry.TEACHER, username="geometry_teacher", first_name="Source", last_name="Teacher"
        )
        profile = cls.teacher.profile
        profile.organization, profile.patronymic, profile.role = cls.org, "Father", "teacher"
        profile.save(update_fields=["organization", "patronymic", "role"])
        Membership.objects.create(
            organization=cls.org,
            user=cls.teacher,
            role=cls.org.roles.get(name="teacher"),
            scope_unit=cls.chair,
            is_active=True,
            is_primary=True,
        )
        Membership.objects.create(
            organization=cls.org,
            user=cls.admin,
            role=cls.org.roles.get(name="teacher"),
            scope_unit=cls.chair,
            is_active=True,
            is_primary=False,
        )
        cls.task = TeachingTask.objects.create(
            pk=geometry.TASK, organization=cls.org, chair=cls.chair, academic_year=YEAR, status="distributed"
        )
        cls.period = AcademicPeriod.objects.create(
            pk=geometry.PERIOD,
            organization=cls.org,
            name="Fall",
            academic_year=YEAR,
            period_type="semester",
            start_date="2026-09-01",
            end_date="2027-01-31",
            is_current=True,
        )
        cls.subject = Subject.objects.create(
            pk=geometry.SUBJECT,
            organization=cls.org,
            code="QKU-SOURCE105",
            name="İqtisadiyyatın əsasları",
            chair_unit=cls.chair,
        )
        cls.groups, cls.offerings = [], []
        for i, (jid, gid) in enumerate(geometry.JOURNALS.items()):
            group = OrgUnit.objects.create(
                pk=gid,
                organization=cls.org,
                name=f"SourceGroup{i}",
                slug=f"group{i}",
                unit_type="group",
                parent=specialty,
            )
            offering = CourseOffering.objects.create(
                pk=jid,
                organization=cls.org,
                group=group,
                subject=cls.subject,
                period=cls.period,
                instructor=cls.teacher,
                lesson_hours=45,
            )
            cls.groups.append(group)
            cls.offerings.append(offering)
            student = User.objects.create_user(f"geometry_student{i}")
            Membership.objects.create(
                organization=cls.org,
                user=student,
                role=cls.org.roles.get(name="student"),
                scope_unit=group,
                is_active=True,
                is_primary=True,
            )
            enrollment = Enrollment.objects.create(organization=cls.org, offering=offering, student=student)
            for offset in range(5):
                Lesson.objects.create(
                    organization=cls.org,
                    offering=offering,
                    date=date(2026, 9, 21) + timedelta(days=7 * offset),
                    start_time="11:50",
                    kind="lecture",
                    hours=2,
                    instructor=None,
                )
            lesson = Lesson.objects.create(
                organization=cls.org,
                offering=offering,
                date=date(2026, 9, 16 + i),
                start_time="08:30",
                kind="seminar",
                hours=2,
                instructor=None,
            )
            LessonMark.objects.create(
                organization=cls.org, lesson=lesson, enrollment=enrollment, status="present", score=9, entered_by=None
            )
            syllabus = Syllabus.objects.create(
                organization=cls.org, subject=cls.subject, offering=offering, period=cls.period, author=cls.teacher
            )
            version = SyllabusVersion.objects.create(
                organization=cls.org,
                syllabus=syllabus,
                major=1,
                status="approved",
                approved_by=cls.admin,
                approved_at=timezone.now(),
                locked_at=timezone.now(),
                plan_hours={"lecture": 30, "seminar": 15},
            )
            SyllabusSection.objects.create(
                organization=cls.org, version=version, section_id="week", data={"rows": [{"topic": "Preserve"}]}
            )
            syllabus.current_version = syllabus.approved_version = version
            syllabus.save(update_fields=["current_version", "approved_version"])

    def setUp(self):
        apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
        value = entry()
        value["teacher_identity"] = [
            {
                "id": self.teacher.pk,
                "first_name": self.teacher.first_name,
                "last_name": self.teacher.last_name,
                "patronymic": "Father",
            }
        ]
        value["physical_source_groups"] = [
            {"id": str(g.pk), "name": g.name, "parent_id": str(g.parent_id), "children": []} for g in self.groups
        ]
        value["desired_row"]["specialty_id"] = str(self.groups[0].parent_id)
        self.plan = select_manifest(
            {
                "format": "reviewed-workload-source/2",
                "organization_id": ORG,
                "academic_year": YEAR,
                "chair_id": str(self.chair.pk),
                "source_entries": [value],
            },
            sha256="b" * 64,
            lines=[105],
        )

    def tearDown(self):
        reset_rls_context()

    def run_repair(self, **kwargs):
        return repair.run(plan=self.plan, organization=self.org, user=self.admin, **kwargs)

    def protected(self):
        return {
            label: records(model.objects.filter(organization=self.org))
            for label, model in (
                ("lessons", Lesson),
                ("marks", LessonMark),
                ("enrollments", Enrollment),
                ("syllabi", Syllabus),
                ("versions", SyllabusVersion),
                ("sections", SyllabusSection),
            )
        }

    def test_restore_keeps_raw_source_all_authors_marks_syllabi_and_journal_ids(self):
        before = self.protected()
        source = self.plan.items[0]["row_data"].copy()
        preview = self.run_repair()
        result = self.run_repair(apply=True, expected_baseline=preview["baseline"])
        self.assertEqual((result["created_rows"], result["created_journals"]), (1, 0))
        row = TeachingTaskRow.objects.get(task=self.task)
        self.assertEqual((row.lecture_plan, row.lecture_total, row.seminar_plan, row.seminar_total), (30, 30, 15, 45))
        self.assertEqual((row.union_count, row.subgroup_count), (1, 3))
        self.assertEqual({str(pk) for pk in row.groups.values_list("pk", flat=True)}, {str(g.pk) for g in self.groups})
        self.assertEqual(set(row.assignments.values_list("activity", "hours")), {("lecture", 30), ("seminar", 45)})
        self.assertEqual(self.protected(), before)
        self.assertEqual(self.plan.items[0]["row_data"], source)
        self.assertEqual(
            {str(pk) for pk in CourseOffering.objects.values_list("id", flat=True)}, {str(o.pk) for o in self.offerings}
        )
        self.assertEqual(self.run_repair()["already_done"], 1)
        current = self.run_repair()["baseline"]
        self.run_repair(apply=True, undo=result["batch"], expected_baseline=current)
        self.assertFalse(TeachingTaskRow.objects.filter(task=self.task).exists())
        self.assertEqual(self.protected(), before)

    def test_new_current_lesson_is_preserved_not_compared_to_old_clone(self):
        Lesson.objects.create(
            organization=self.org,
            offering=self.offerings[0],
            date="2026-10-28",
            kind="seminar",
            hours=2,
            instructor=self.teacher,
        )
        before = self.protected()
        preview = self.run_repair()
        self.run_repair(apply=True, expected_baseline=preview["baseline"])
        self.assertEqual(self.protected(), before)

    def test_live_owner_change_rejects_without_any_load_or_academic_write(self):
        self.offerings[0].instructor = self.admin
        self.offerings[0].save(update_fields=["instructor"])
        before = self.protected()
        with self.assertRaises(RepairError):
            self.run_repair()
        self.assertFalse(TeachingTaskRow.objects.filter(task=self.task).exists())
        self.assertEqual(self.protected(), before)

    def test_new_lesson_after_preview_rejects_stale_baseline_without_losing_it(self):
        preview = self.run_repair()
        Lesson.objects.create(
            organization=self.org,
            offering=self.offerings[0],
            date="2026-10-28",
            kind="seminar",
            hours=2,
            instructor=self.teacher,
        )
        before = self.protected()
        with self.assertRaisesMessage(RepairError, "baseline_conflict"):
            self.run_repair(apply=True, expected_baseline=preview["baseline"])
        self.assertEqual(self.protected(), before)
        self.assertFalse(TeachingTaskRow.objects.filter(task=self.task).exists())

    def test_lesson_beyond_source_unit_rejects(self):
        Lesson.objects.create(
            organization=self.org, offering=self.offerings[0], date="2026-10-28", kind="seminar", hours=16
        )
        before = self.protected()
        with self.assertRaisesMessage(RepairError, "source_plan_below_recorded_teaching_hours"):
            self.run_repair()
        self.assertEqual(self.protected(), before)
