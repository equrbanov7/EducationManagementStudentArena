"""«Fənləri birləşdir» testlərinin ortaq qurğusu (2026-10-19).

Struktur: fakültə → kafedra → qruplar G1/G2; dövr «2026/2027 Payız». Hədəf fənn ``T`` (QA-SM-T),
mənbə ``S`` (QA-SM-S, eyni ad «Vo İP sistemləri» variantı). ``build_full_source()`` mənbəyə
``Subject``-ə baxan HƏR əlaqə növündən bir sətir bağlayır (inventardakı bütün cədvəllər).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    ExamChanceGrant,
    ExternalCreditRecognition,
    GroupElectiveChoice,
    Program,
    RetakeApplication,
    Subject,
)
from apps.registrar.models.curriculum_meta import PlanStatus
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()
REASON = "Tədris şöbəsinin təklifi: eyni fənnin iki kataloq kartı"


class SubjectMergeBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sm_owner", "sm_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SM Univ",
                slug="sm-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="sm-f", unit_type=OrgUnitType.FACULTY
            )
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra", slug="sm-k", unit_type=OrgUnitType.CHAIR, parent=cls.faculty
            )
            cls.group1 = OrgUnit.objects.create(
                organization=cls.org, name="234 K", slug="sm-g1", unit_type=OrgUnitType.GROUP, parent=cls.chair
            )
            cls.group2 = OrgUnit.objects.create(
                organization=cls.org, name="235 K", slug="sm-g2", unit_type=OrgUnitType.GROUP, parent=cls.chair
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=date(2026, 9, 15),
                end_date=date(2027, 1, 25),
            )
            cls.program = Program.objects.create(organization=cls.org, code="SM-P", name="Telekommunikasiya")
            cls.target = Subject.objects.create(
                organization=cls.org, code="QA-SM-T", name="VoIP sistemləri", ects=5, chair_unit=cls.chair
            )
            cls.source = Subject.objects.create(
                organization=cls.org, code="QA-SM-S", name="Vo İP sistemləri", ects=5, chair_unit=cls.chair
            )
            cls.teacher = User.objects.create_user("sm_teacher", "sm_teacher@qku.edu.az", "pw")
            cls._member(cls.teacher, cls.org.roles.get(name="teacher"))
            cls.student = cls._student("sm_student")
            cls.other_student = cls._student("sm_student2")
            cls.office = cls._staff("sm_office", ["catalog.view", "catalog.manage"], RoleScopeType.ORGANIZATION)
            cls.dean = cls._staff("sm_dean", ["catalog.view", "catalog.manage"], RoleScopeType.UNIT, cls.faculty)
            cls.viewer = cls._staff("sm_viewer", ["catalog.view"], RoleScopeType.ORGANIZATION)

    # ── köməkçilər ──────────────────────────────────────────────────────────

    @classmethod
    def _member(cls, user, role, unit=None):
        Membership.objects.create(
            user=user, organization=cls.org, role=role, scope_unit=unit, is_primary=True, is_active=True
        )

    @classmethod
    def _staff(cls, username, permissions, scope_type, unit=None):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        role = Role.objects.create(
            organization=cls.org,
            name=f"t_{username}",
            display_name=username,
            level=80,
            scope_type=scope_type,
            permissions=permissions,
        )
        cls._member(user, role, unit)
        return user

    @classmethod
    def _student(cls, username):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw", first_name=username, last_name="QA")
        cls._member(user, cls.org.roles.get(name="student"))
        return user

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def offering(self, subject, group, period=None):
        with bypass_rls():
            return CourseOffering.objects.create(
                organization=self.org, subject=subject, period=period or self.period, group=group
            )

    def enroll(self, offering, student=None, *, grade=None):
        with bypass_rls():
            enrollment = Enrollment.objects.create(
                organization=self.org, student=student or self.student, offering=offering
            )
            if grade is not None:
                django_apps.get_model("registrar", "FinalGrade").objects.create(
                    organization=self.org, enrollment=enrollment, exam_score=Decimal(grade)
                )
        return enrollment

    def plan(self, status=PlanStatus.DRAFT, *, year=2026, version=1, name="Plan"):
        with bypass_rls():
            return Curriculum.objects.create(
                organization=self.org,
                program=self.program,
                admission_year=year,
                name=name,
                status=status,
                version=version,
            )

    def plan_row(self, plan, subject, semester=1, **extra):
        with bypass_rls():
            return CurriculumSubject.objects.create(
                organization=self.org, curriculum=plan, subject=subject, semester_number=semester, credits=5, **extra
            )

    def syllabus(self, subject, *, period=None, author=None, offering=None):
        Syllabus = django_apps.get_model("syllabus", "Syllabus")
        with bypass_rls():
            return Syllabus.objects.create(
                organization=self.org, subject=subject, period=period, author=author, offering=offering
            )

    def folder(self, subject, *, period=None):
        SubjectFolder = django_apps.get_model("subject_folder", "SubjectFolder")
        with bypass_rls():
            return SubjectFolder.objects.create(
                organization=self.org, subject=subject, owner=self.teacher, period=period, title="Qovluq"
            )

    def retake(self, subject, enrollment, *, student=None, status="submitted"):
        with bypass_rls():
            return RetakeApplication.objects.create(
                organization=self.org,
                student=student or self.student,
                enrollment=enrollment,
                subject=subject,
                period=self.period,
                kind="retake_25",
                status=status,
            )

    def task_row(self, subject, groups, task=None):
        TeachingTask = django_apps.get_model("workload", "TeachingTask")
        TeachingTaskRow = django_apps.get_model("workload", "TeachingTaskRow")
        with bypass_rls():
            task = task or TeachingTask.objects.create(
                organization=self.org, academic_year="2026/2027", chair=self.chair
            )
            row = TeachingTaskRow.objects.create(organization=self.org, task=task, subject=subject, subject_text="")
            row.groups.set(groups)
        return task, row

    def build_full_source(self):
        """Mənbəyə hər FK növündən bir sətir (+ konfliktsiz). Qaytarır: ``{açar: obyekt}``."""
        StudentGroup = django_apps.get_model("exams", "StudentGroup")
        Exam = django_apps.get_model("exams", "Exam")
        QuestionBank = django_apps.get_model("exams", "QuestionBank")
        QuestionSubmission = django_apps.get_model("exams", "QuestionSubmission")
        SurveyTemplate = django_apps.get_model("surveys", "SurveyTemplate")
        SurveyCampaign = django_apps.get_model("surveys", "SurveyCampaign")
        SurveyResponse = django_apps.get_model("surveys", "SurveyResponse")
        TeacherAvailability = django_apps.get_model("timetable", "TeacherAvailability")
        built = {}
        built["offering"] = self.offering(self.source, self.group1)
        built["target_offering"] = self.offering(self.target, self.group2)
        built["enrollment"] = self.enroll(built["offering"], grade="40")
        approved = self.plan(PlanStatus.APPROVED, name="Təsdiqli plan")
        built["approved_plan"] = approved
        built["plan_row"] = self.plan_row(approved, self.source, semester=3)
        with bypass_rls():
            built["elective"] = GroupElectiveChoice.objects.create(
                organization=self.org,
                group=self.group1,
                period=self.period,
                elective_group="SB1",
                chosen_subject=self.source,
            )
            built["retake"] = RetakeApplication.objects.create(
                organization=self.org,
                student=self.student,
                enrollment=built["enrollment"],
                subject=self.source,
                period=self.period,
                kind="retake_25",
            )
            built["chance"] = ExamChanceGrant.objects.create(
                organization=self.org, student=self.student, subject=self.source, exam_id=1, reason="other"
            )
            built["recognition"] = ExternalCreditRecognition.objects.create(
                organization=self.org,
                student=self.student,
                subject=self.source,
                period=self.period,
                enrollment=built["enrollment"],
                program="exchange",
                institution="QA University",
                country="QA",
                foreign_subject="QA Subject",
                foreign_credit=Decimal("5"),
                foreign_grade="A",
                study_period="2025/2026",
                recognized_score=90,
                document=SimpleUploadedFile("qa.pdf", b"%PDF-1.4 qa", content_type="application/pdf"),
            )
            built["syllabus"] = self.syllabus(self.source, period=self.period, author=self.teacher)
            built["offering_syllabus"] = self.syllabus(self.source, offering=built["offering"], author=self.teacher)
            built["task"], built["task_row"] = self.task_row(self.source, [self.group1])
            built["group_move"] = StudentGroup.objects.create(organization=self.org, teacher=self.teacher, name="SG-1")
            built["group_move"].subjects.add(self.source)
            built["group_both"] = StudentGroup.objects.create(organization=self.org, teacher=self.teacher, name="SG-2")
            built["group_both"].subjects.add(self.source, self.target)
            built["exam"] = Exam.objects.create(
                author=self.teacher, title="Final", organization=self.org, subject=self.source
            )
            built["bank"] = QuestionBank.objects.create(
                name="Bank", created_by=self.teacher, organization=self.org, subject_ref=self.source
            )
            built["submission"] = QuestionSubmission.objects.create(
                organization=self.org, teacher=self.teacher, title="Suallar", raw_text="1. ?", subject_ref=self.source
            )
            template = SurveyTemplate.objects.create(organization=self.org, name="Sorğu")
            campaign = SurveyCampaign.objects.create(organization=self.org, period=self.period, template=template)
            built["survey"] = SurveyResponse.objects.create(
                organization=self.org,
                campaign=campaign,
                scope="teacher",
                teacher=self.teacher,
                offering=built["offering"],
                subject=self.source,
            )
            built["folder"] = self.folder(self.source, period=self.period)
            built["availability"] = TeacherAvailability.objects.create(
                organization=self.org,
                teacher=self.teacher,
                period=self.period,
                note="",
                subject_priorities={str(self.source.pk): 4, str(self.target.pk): 2},
            )
        return built
