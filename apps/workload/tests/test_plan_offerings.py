"""Plan kafedraya çatanda fənn qruplara düşür (sahib 2026-09-25) — təsdiq → açılış + qeydiyyat.

Yoxlanılır: təsdiq anında açılışlar MÜƏLLİMSİZ yaranır; boş ``period`` tədris ili +
fəsildən törədilir; ``lesson_hours`` QRUP başınadır (şişirdilmiş ``*_total`` yox);
seçmə blok qrup açılışı vermir; yalnız aktiv tələbələr yazılır (akademik məzuniyyət,
passiv qeyd, üzvlüksüz — yox; başqa jurnalda aktiv olan və ``dropped`` tarixçəsi
toxunulmur); təkrar keçid idempotentdir; kilidli semestr və ləğv edilmiş açılış
toxunulmazdır; generator dövrü və kursu (``admission_year``) özü tapır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.notifications.models import InAppNotification
from apps.organizations.models import AcademicPeriod, Membership, OrgUnit
from apps.registrar.models import (
    AcademicStatus,
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    StudentAcademicRecord,
    Subject,
)
from apps.workload.constants import TaskStatus
from apps.workload.models import TaskFacultySlice, TeachingTaskRow
from apps.workload.services import (
    approve_slice,
    generate_rows_from_plan,
    resolve_actor,
    review_all,
    submit_task,
)
from apps.workload.services.offering_sync import sync_task_offerings
from apps.workload.services.plan_calendar import PeriodResolver
from core.constants import AcademicPeriodType, OrgUnitType, RoleScopeType

from .factories import YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

OFFICE_PERMS = ["workload.view", "workload.manage", "workload.submit", "workload.report"]
COORD_PERMS = ["workload.view", "workload.review"]
DEAN_PERMS = ["workload.view", "workload.approve", "workload.report"]
CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute"]


class PlanOfferingBase(TestCase):
    """Fakültə → kafedra → ixtisas → qrup + zəncir aktorları + qrupun tələbələri."""

    code = "P2G"

    @classmethod
    def setUpTestData(cls):
        cls.org = make_org(f"wl-{cls.code.lower()}")
        cls.stack = make_structure(cls.org, code=cls.code)
        cls.office = User.objects.create_user(f"{cls.code}.office", f"{cls.code}o@x.test", "pw")
        cls.coordinator = User.objects.create_user(f"{cls.code}.coord", f"{cls.code}c@x.test", "pw")
        cls.dean = User.objects.create_user(f"{cls.code}.dean", f"{cls.code}d@x.test", "pw")
        cls.chair_head = User.objects.create_user(f"{cls.code}.chair", f"{cls.code}h@x.test", "pw")
        activate_member(cls.org, cls.office, "teaching_office_head", permissions=OFFICE_PERMS, level=85)
        activate_member(
            cls.org,
            cls.coordinator,
            "program_coordinator",
            permissions=COORD_PERMS,
            scope_unit=cls.stack["specialty"],
            scope_type=RoleScopeType.UNIT,
            level=45,
        )
        activate_member(
            cls.org,
            cls.dean,
            "dean",
            permissions=DEAN_PERMS,
            scope_unit=cls.stack["faculty"],
            scope_type=RoleScopeType.UNIT,
            level=70,
        )
        activate_member(
            cls.org,
            cls.chair_head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=cls.stack["chair"],
            scope_type=RoleScopeType.UNIT,
            level=60,
        )
        cls.curriculum = Curriculum.objects.create(
            organization=cls.org, program=cls.stack["program"], admission_year=2025
        )
        cls.student = cls._student("active")
        cls.on_leave = cls._student("leave", status=AcademicStatus.ACADEMIC_LEAVE)
        cls.passive = cls._student("passive", is_active=False)
        cls.no_member = cls._student("nomember")
        Membership.objects.filter(organization=cls.org, user=cls.no_member).update(is_active=False)

    @classmethod
    def _student(cls, suffix, *, group=None, status=AcademicStatus.ENROLLED, is_active=True):
        user = User.objects.create_user(f"{cls.code}.st.{suffix}", f"{cls.code}{suffix}@x.test", "pw")
        activate_member(cls.org, user, "student", permissions=["course.view"], level=10)
        StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=user,
            program=cls.stack["program"],
            curriculum=cls.curriculum,
            group=group or cls.stack["group"],
            admission_year=2025,
            status=status,
            is_active=is_active,
        )
        return user

    def actor(self, user):
        return resolve_actor(user, self.org)

    def office_task(self, **row_kwargs):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        row = make_row(task, self.stack, **row_kwargs)
        return task, row

    def approve(self, task):
        submit_task(task=task, actor=self.actor(self.office))
        review_all(actor=self.actor(self.coordinator))
        result = approve_slice(slice_obj=TaskFacultySlice.objects.get(task=task), actor=self.actor(self.dean))
        task.refresh_from_db()
        return result

    def offerings(self, **extra):
        return CourseOffering.objects.filter(organization=self.org, **extra)


class ApprovalCreatesOfferingsTest(PlanOfferingBase):
    code = "P2A"

    def _inflated_row(self, task):
        """Birləşmə/yarımqrup çarpanlı sətir: qrup başına 30 + 15, cəmdə 30 + 30."""
        row = make_row(task, self.stack, lecture_total=30, seminar_total=30, with_period=False)
        TeachingTaskRow.objects.filter(pk=row.pk).update(seminar_plan=15, subgroup_count=2)
        return row

    def test_approval_creates_group_offering_with_derived_period_and_per_group_hours(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        row = self._inflated_row(task)
        result = self.approve(task)

        self.assertEqual(task.status, TaskStatus.APPROVED)
        row.refresh_from_db()
        self.assertEqual(row.period_id, self.stack["period"].pk)  # «Payız P2A» — il + fəsil
        offering = self.offerings(subject=self.stack["subject"]).get()
        self.assertEqual(offering.group_id, self.stack["group"].pk)
        self.assertEqual(offering.period_id, self.stack["period"].pk)
        self.assertIsNone(offering.instructor_id)  # müəllim hələ təyin olunmayıb
        self.assertEqual(offering.lesson_hours, 45)  # 30 + 15, şişirdilmiş 60 yox
        self.assertEqual(result["offerings"]["created"], 1)
        self.assertEqual(result["offerings"]["period_set"], 1)

    def test_only_active_enrolled_members_are_enrolled(self):
        task, _row = self.office_task()
        result = self.approve(task)
        offering = self.offerings(subject=self.stack["subject"]).get()
        students = set(Enrollment.objects.filter(offering=offering).values_list("student_id", flat=True))
        self.assertEqual(students, {self.student.pk})
        self.assertEqual(result["offerings"]["enrolled"], 1)
        self.assertEqual(result["offerings"]["enroll_not_member"], 1)
        enrollment = Enrollment.objects.get(offering=offering, student=self.student)
        self.assertEqual(enrollment.status, Enrollment.Status.ENROLLED)
        self.assertEqual(enrollment.kind, "mandatory")

    def test_chair_notification_and_audit_carry_the_counts(self):
        task, _row = self.office_task()
        self.stack["chair"].head = self.chair_head
        self.stack["chair"].save(update_fields=["head"])
        self.approve(task)
        note = InAppNotification.objects.filter(recipient=self.chair_head).latest("created_at")
        self.assertEqual(note.metadata.get("event"), "workload_task_approved")
        self.assertEqual(note.metadata.get("offerings_created"), 1)
        self.assertIn("qruplara düşdü", note.message)
        audit = AuditLog.objects.get(organization=self.org, reason="workload.task_approved")
        self.assertEqual(audit.new_values["offerings"]["created"], 1)

    def test_second_pass_is_idempotent(self):
        task, _row = self.office_task()
        self.approve(task)
        again = sync_task_offerings(task, actor=self.actor(self.dean))
        self.assertEqual((again["created"], again["updated"], again["enrolled"]), (0, 0, 0))
        self.assertEqual(self.offerings().count(), 1)
        self.assertEqual(Enrollment.objects.filter(offering__organization=self.org).count(), 1)

    def test_elective_block_subject_is_not_opened_for_the_group(self):
        elective = Subject.objects.create(organization=self.org, code="P2A-EL", name="Seçmə fənn", ects=4)
        plan = Curriculum.objects.create(
            organization=self.org, program=self.stack["program"], admission_year=2026, status="approved"
        )
        CurriculumSubject.objects.create(
            organization=self.org,
            curriculum=plan,
            subject=elective,
            semester_number=1,
            is_elective=True,
            elective_group="ATMF I",
        )
        task, _row = self.office_task()
        make_row(task, {**self.stack, "subject": elective}, lecture_total=30, seminar_total=0)
        result = self.approve(task)
        self.assertFalse(self.offerings(subject=elective).exists())
        self.assertTrue(self.offerings(subject=self.stack["subject"]).exists())
        self.assertEqual(result["offerings"]["elective_pending"], 1)

    def test_student_active_in_another_journal_and_dropped_history_are_untouched(self):
        other_group = OrgUnit.objects.create(
            organization=self.org,
            name="P2A-236 ing",
            slug="p2a-other-group",
            unit_type=OrgUnitType.GROUP,
            parent=self.stack["specialty"],
        )
        merged = self._student("merged")
        dropped = self._student("dropped")
        other = CourseOffering.objects.create(
            organization=self.org, subject=self.stack["subject"], period=self.stack["period"], group=other_group
        )
        Enrollment.objects.create(organization=self.org, student=merged, offering=other)  # alt qrup birləşməsi
        own = CourseOffering.objects.create(
            organization=self.org, subject=self.stack["subject"], period=self.stack["period"], group=self.stack["group"]
        )
        Enrollment.objects.create(organization=self.org, student=dropped, offering=own, status="dropped")
        task, _row = self.office_task()
        result = self.approve(task)
        self.assertNotIn("created", result["offerings"])  # açılış artıq var idi (sıfır sayğac yazılmır)
        self.assertFalse(Enrollment.objects.filter(offering=own, student=merged).exists())
        self.assertEqual(Enrollment.objects.get(offering=own, student=dropped).status, "dropped")
        self.assertTrue(Enrollment.objects.filter(offering=own, student=self.student, status="enrolled").exists())
        self.assertEqual(result["offerings"]["enroll_conflict"], 1)
        self.assertEqual(result["offerings"]["enroll_existing"], 1)

    def test_locked_semester_and_cancelled_offering_are_left_alone(self):
        spring = AcademicPeriod.objects.create(
            organization=self.org,
            name="Yaz",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year=YEAR,
            start_date="2027-02-01",
            end_date="2027-06-30",
        )
        AcademicPeriod.objects.filter(pk=spring.pk).update(locked_at="2027-02-02T10:00:00Z")
        cancelled_subject = Subject.objects.create(organization=self.org, code="P2A-X", name="Ləğv", ects=3)
        CourseOffering.objects.create(
            organization=self.org,
            subject=cancelled_subject,
            period=self.stack["period"],
            group=self.stack["group"],
            is_active=False,
        )
        task, spring_row = self.office_task()
        TeachingTaskRow.objects.filter(pk=spring_row.pk).update(period=spring)
        make_row(task, {**self.stack, "subject": cancelled_subject})
        result = self.approve(task)
        self.assertFalse(self.offerings(period=spring).exists())
        self.assertEqual(result["offerings"]["period_locked"], 1)
        self.assertEqual(result["offerings"]["inactive_skipped"], 1)
        self.assertFalse(Enrollment.objects.filter(offering__subject=cancelled_subject).exists())


class PeriodResolverTest(PlanOfferingBase):
    code = "P2R"

    def test_exact_name_beats_keyword_and_month(self):
        exact = AcademicPeriod.objects.create(
            organization=self.org,
            name="Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year=YEAR,
            start_date="2026-09-15",
            end_date="2027-01-31",
        )
        resolver = PeriodResolver(self.org)
        self.assertEqual(resolver.resolve(YEAR, "fall"), exact)
        self.assertIsNone(resolver.resolve(YEAR, "spring"))
        self.assertIsNone(PeriodResolver(self.org).resolve("2031/2032", "fall"))

    def test_keyword_and_month_fallbacks(self):
        spring = AcademicPeriod.objects.create(
            organization=self.org,
            name="Yaz semestri",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year=YEAR,
            start_date="2027-02-01",
            end_date="2027-06-30",
        )
        summer = AcademicPeriod.objects.create(
            organization=self.org,
            name="III dövr",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year=YEAR,
            start_date="2027-07-01",
            end_date="2027-08-20",
        )
        resolver = PeriodResolver(self.org)
        self.assertEqual(resolver.resolve(YEAR, "spring"), spring)
        self.assertEqual(resolver.resolve(YEAR, "summer"), summer)  # ad fəsil demir → başlanğıc ayı
        self.assertEqual(resolver.resolve(YEAR, "fall"), self.stack["period"])  # «Payız P2R»


class GenerationFixesPeriodAndCourseTest(PlanOfferingBase):
    code = "P2N"

    def test_generated_rows_get_period_and_admission_year_groups(self):
        OrgUnit.objects.filter(pk=self.stack["group"].pk).update(settings={"admission_year": 2026})
        OrgUnit.objects.create(
            organization=self.org,
            name="P2N-235",
            slug="p2n-old-group",
            unit_type=OrgUnitType.GROUP,
            parent=self.stack["specialty"],
            settings={"admission_year": 2025},  # 2-ci kurs — 1-ci semestr fənni ona düşmür
        )
        plan = Curriculum.objects.create(
            organization=self.org, program=self.stack["program"], admission_year=2026, status="approved"
        )
        CurriculumSubject.objects.create(
            organization=self.org,
            curriculum=plan,
            subject=self.stack["subject"],
            semester_number=1,
            credits=5,
            lecture_hours=30,
            seminar_hours=15,
        )
        stale = make_task(self.org, self.stack["chair"], created_by=self.office)
        old_subject = Subject.objects.create(organization=self.org, code="P2N-OLD", name="Köhnə sətir", ects=3)
        leftover = make_row(stale, {**self.stack, "subject": old_subject}, with_period=False)
        result = generate_rows_from_plan(task=stale, actor=self.actor(self.office))
        self.assertEqual(result["created"], 1)
        row = TeachingTaskRow.objects.get(task=stale, subject=self.stack["subject"])
        self.assertEqual(row.period_id, self.stack["period"].pk)
        self.assertEqual(list(row.groups.values_list("pk", flat=True)), [self.stack["group"].pk])
        leftover.refresh_from_db()
        self.assertEqual(leftover.period_id, self.stack["period"].pk)  # əvvəlki dövrsüz sətir də bağlandı
        self.assertEqual(result["period_set"], 1)
