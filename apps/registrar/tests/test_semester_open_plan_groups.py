"""«Semestr açılışı» + qrupa toplu qeydiyyat — plan → qruplar qaydaları (2026-09-25).

Yoxlanılır: semestr ``N`` yalnız kursu ``ceil(N/2)`` olan qruplara düşür
(``settings.course_year``, yoxdursa ``admission_year``); seçmə fənlər açılmır;
yeni açılışa qrupun aktiv tələbələri dərhal yazılır, aktiv siyahısı olan açılışa
toxunulmur; ``enroll_group_students`` tarixçəni (``dropped``), başqa jurnaldakı
aktiv qeydiyyatı və üzvlüksüz tələbəni qoruyur; «Kafedraya göndər» bildirişi
kafedra başına birdir və «Yük bölgüsü»nə aparır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.notifications.models import InAppNotification
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import semester_actions, semester_open, services
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
YEAR = "2026/2027"


class _PlanGroupsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("pg_owner", "pg_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="PG Univ",
                slug="pg-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="PG fakültə", slug="pg-fak", unit_type=OrgUnitType.FACULTY
            )
            cls.chair = cls._unit("PG kafedra", "pg-kaf", OrgUnitType.CHAIR, cls.faculty)
            cls.other_chair = cls._unit("PG digər kafedra", "pg-kaf2", OrgUnitType.CHAIR, cls.faculty)
            cls.specialty = cls._unit("PG ixtisas", "pg-ixt", OrgUnitType.SPECIALTY, cls.faculty)
            cls.first = cls._unit("PG-261", "pg-261", OrgUnitType.GROUP, cls.specialty, {"course_year": 1})
            cls.second = cls._unit("PG-251", "pg-251", OrgUnitType.GROUP, cls.specialty, {"admission_year": 2025})
            cls.old = cls._unit("PG-171", "pg-171", OrgUnitType.GROUP, cls.specialty, {"admission_year": 2017})
            cls.bare = cls._unit("PG-X", "pg-x", OrgUnitType.GROUP, cls.specialty)
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year=YEAR,
                start_date="2026-09-15",
                end_date="2027-01-31",
                is_current=True,
            )
            cls.program = Program.objects.create(
                organization=cls.org, code="PG-P", name="PG proqramı", specialty_unit=cls.specialty
            )
            cls.plan = Curriculum.objects.create(
                organization=cls.org, program=cls.program, admission_year=2025, status="approved"
            )
            cls.mandatory = cls._subject("PG-M1", "Məcburi fənn", cls.chair)
            cls.elective = cls._subject("PG-E1", "Seçmə fənn", cls.chair)
            cls.third = cls._subject("PG-M3", "Üçüncü semestr fənni", cls.chair)
            cls._plan_row(cls.mandatory, 1)
            cls._plan_row(cls.elective, 1, is_elective=True, elective_group="Blok A")
            cls._plan_row(cls.third, 3)
            cls.actor = User.objects.create_user("pg_office", "pg_office@qku.edu.az", "pw", is_superuser=True)
            cls.freshman = cls._student("pg_s1", cls.first)
            cls.sophomore = cls._student("pg_s2", cls.second)

    @classmethod
    def _unit(cls, name, slug, unit_type, parent, settings=None):
        return OrgUnit.objects.create(
            organization=cls.org, name=name, slug=slug, unit_type=unit_type, parent=parent, settings=settings or {}
        )

    @classmethod
    def _subject(cls, code, name, chair):
        return Subject.objects.create(organization=cls.org, code=code, name=name, ects=5, chair_unit=chair)

    @classmethod
    def _plan_row(cls, subject, semester, **extra):
        return CurriculumSubject.objects.create(
            organization=cls.org,
            curriculum=cls.plan,
            subject=subject,
            semester_number=semester,
            lecture_hours=30,
            seminar_hours=15,
            **extra,
        )

    @classmethod
    def _student(cls, username, group):
        student = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            user=student, organization=cls.org, role=cls.org.roles.get(name="student"), is_active=True
        )
        StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=student,
            program=cls.program,
            curriculum=cls.plan,
            group=group,
            admission_year=2025,
        )
        return student

    def generate(self, semester):
        with bypass_rls():
            return semester_open.generate_offerings(
                organization=self.org,
                period=self.period,
                programs=[self.program],
                semester_number=semester,
                actor=self.actor,
            )


class GroupCourseYearTest(_PlanGroupsBase):
    def test_explicit_course_then_admission_year(self):
        self.assertEqual(services.group_course_year(self.first, YEAR), 1)
        self.assertEqual(services.group_course_year(self.second, YEAR), 2)
        self.assertEqual(services.group_course_year(self.second, "2027/2028"), 3)
        self.assertEqual(services.group_course_year(self.old, YEAR), 0)  # 10-cu «kurs» — sərhəddən kənar
        self.assertEqual(services.group_course_year(self.bare, YEAR), 0)
        self.assertEqual(services.group_course_year(OrgUnit(settings={"course_year": "2"}), YEAR), 2)

    def test_semester_maps_to_the_matching_course(self):
        with bypass_rls():
            first = semester_open.groups_for_semester(self.org, self.program, semester_number=1, academic_year=YEAR)
            third = semester_open.groups_for_semester(self.org, self.program, semester_number=4, academic_year=YEAR)
        self.assertEqual(first, [self.first])
        self.assertEqual(third, [self.second])


class GenerateOfferingsTest(_PlanGroupsBase):
    def test_first_semester_reaches_first_year_only_and_skips_electives(self):
        result = self.generate(1)
        with bypass_rls():
            offerings = list(CourseOffering.objects.filter(organization=self.org).values_list("subject_id", "group_id"))
            self.assertEqual(offerings, [(self.mandatory.pk, self.first.pk)])
            self.assertTrue(Enrollment.objects.filter(student=self.freshman, offering__subject=self.mandatory).exists())
        self.assertEqual((result["created"], result["skipped_electives"], result["enrolled"]), (1, 1, 1))

    def test_third_semester_reaches_the_second_year_group(self):
        result = self.generate(3)
        with bypass_rls():
            offering = CourseOffering.objects.get(organization=self.org, subject=self.third)
            self.assertEqual(offering.group_id, self.second.pk)
            self.assertEqual(offering.lesson_hours, 45)
            self.assertTrue(Enrollment.objects.filter(student=self.sophomore, offering=offering).exists())
        self.assertEqual(result["enrolled"], 1)

    def test_populated_offering_keeps_its_roster(self):
        with bypass_rls():
            offering = CourseOffering.objects.create(
                organization=self.org, subject=self.mandatory, period=self.period, group=self.first
            )
            guest = self._student("pg_guest", self.second)
            Enrollment.objects.create(organization=self.org, student=guest, offering=offering)
        result = self.generate(1)
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(offering=offering, student=self.freshman).exists())
        self.assertEqual((result["existing"], result["enrolled"]), (1, 0))

    def test_no_group_in_that_course_is_reported(self):
        result = self.generate(7)  # 4-cü kurs — heç bir qrup
        self.assertEqual((result["created"], result["skipped_no_group"]), (0, 1))


class EnrollGroupStudentsTest(_PlanGroupsBase):
    def test_history_other_journals_and_non_members_are_respected(self):
        with bypass_rls():
            offering = CourseOffering.objects.create(
                organization=self.org, subject=self.mandatory, period=self.period, group=self.first
            )
            other = CourseOffering.objects.create(
                organization=self.org, subject=self.mandatory, period=self.period, group=self.bare
            )
            dropped = self._student("pg_dropped", self.first)
            Enrollment.objects.create(organization=self.org, student=dropped, offering=offering, status="dropped")
            merged = self._student("pg_merged", self.first)
            Enrollment.objects.create(organization=self.org, student=merged, offering=other)
            outsider = self._student("pg_outsider", self.first)
            Membership.objects.filter(organization=self.org, user=outsider).update(is_active=False)
            report = services.enroll_group_students(offerings=[offering])
            self.assertEqual(Enrollment.objects.get(offering=offering, student=dropped).status, "dropped")
            self.assertFalse(Enrollment.objects.filter(offering=offering, student=merged).exists())
            self.assertFalse(Enrollment.objects.filter(offering=offering, student=outsider).exists())
            self.assertTrue(Enrollment.objects.filter(offering=offering, student=self.freshman).exists())
            again = services.enroll_group_students(offerings=[offering])
        self.assertEqual(
            {key: report[key] for key in ("created", "existing", "conflict", "not_member")},
            {"created": 1, "existing": 1, "conflict": 1, "not_member": 1},
        )
        self.assertEqual((again["created"], again["existing"]), (0, 2))


class SendToChairsTest(_PlanGroupsBase):
    def test_one_notification_per_chair_with_offerings_linking_to_distribution(self):
        head = User.objects.create_user("pg_head", "pg_head@qku.edu.az", "pw")
        other_head = User.objects.create_user("pg_head2", "pg_head2@qku.edu.az", "pw")
        with bypass_rls():
            OrgUnit.objects.filter(pk=self.chair.pk).update(head=head)
            OrgUnit.objects.filter(pk=self.other_chair.pk).update(head=other_head)
            CourseOffering.objects.create(
                organization=self.org, subject=self.mandatory, period=self.period, group=self.first
            )
            sent = semester_actions._notify_chairs(self.org, self.period, actor=self.actor)
            notes = list(InAppNotification.objects.filter(recipient__in=[head, other_head]))
        self.assertEqual(sent, 1)
        self.assertEqual([note.recipient_id for note in notes], [head.pk])
        self.assertIn("workload-distribution", notes[0].link)  # xidmət keçidi təşkilat keçidinə bükür
        self.assertEqual(notes[0].metadata.get("chair_id"), str(self.chair.pk))
