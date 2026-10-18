"""«Alt qrupa yerləşdirmə» testlərinin ortaq qurğusu (registrar + accounts testləri işlədir).

Bir fakültə · bir kafedra · İKİ qrup (G1 — hədəf, G2 — tələbənin öz qrupu) + kənar fakültə (GX).
Cari semestrdə hər qrupun Tarix + Riyaziyyat jurnalı var (məcburi plan); Fizika YALNIZ G1-də açılıb —
tələbə (G2) onu alt qrupdan götürür. Aktorlar açarla qurulur (rol adı ilə yox):

* ``dean`` — UNIT rolu, ``retake.manage``, əhatə: fakültə;
* ``far_dean`` — eyni açar, əhatə: kənar fakültə;
* ``plain`` — açarsız əməkdaş (``unit.view``);
* ``org_admin`` — ORGANIZATION rolu, ``retake.manage``.
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar import services
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    Program,
    ScheduleSlot,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def pdf(name="teqdimat.pdf"):
    return SimpleUploadedFile(name, PDF_BYTES, content_type="application/pdf")


class SubgroupFixture:
    """``setUpTestData``-dan çağırılan qurucu (mixin — TestCase sinfinə qoşulur)."""

    PREFIX = "sg"

    @classmethod
    def build_world(cls):
        p = cls.PREFIX
        cls.owner = User.objects.create_user(f"{p}_owner", f"{p}_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name=f"{p} Univ",
                slug=f"{p}-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            unit = OrgUnit.objects.create
            cls.faculty = unit(organization=cls.org, name="Fakültə", slug=f"{p}-f", unit_type=OrgUnitType.FACULTY)
            cls.chair = unit(
                organization=cls.org, name="Kafedra", slug=f"{p}-k", unit_type=OrgUnitType.CHAIR, parent=cls.faculty
            )
            cls.group1 = unit(
                organization=cls.org, name="G1", slug=f"{p}-g1", unit_type=OrgUnitType.GROUP, parent=cls.chair
            )
            cls.group2 = unit(
                organization=cls.org, name="G2", slug=f"{p}-g2", unit_type=OrgUnitType.GROUP, parent=cls.chair
            )
            cls.far_faculty = unit(
                organization=cls.org, name="Uzaq fakültə", slug=f"{p}-ff", unit_type=OrgUnitType.FACULTY
            )
            cls.far_group = unit(
                organization=cls.org, name="GX", slug=f"{p}-gx", unit_type=OrgUnitType.GROUP, parent=cls.far_faculty
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date="2025-09-01",
                end_date="2026-01-31",
                is_current=True,
            )
            cls.past_period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Yaz",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2025-02-01",
                end_date="2025-06-30",
                is_current=False,
            )
            cls.key_role = Role.objects.create(
                organization=cls.org,
                name=f"{p}_retake_unit",
                display_name="Dekanlıq (test)",
                level=70,
                scope_type=RoleScopeType.UNIT,
                permissions=["retake.manage", "unit.view"],
            )
            cls.org_role = Role.objects.create(
                organization=cls.org,
                name=f"{p}_retake_org",
                display_name="Tədris şöbəsi (test)",
                level=80,
                scope_type=RoleScopeType.ORGANIZATION,
                permissions=["retake.manage", "unit.view"],
            )
            cls.plain_role = Role.objects.create(
                organization=cls.org,
                name=f"{p}_plain",
                display_name="Əməkdaş (test)",
                level=40,
                scope_type=RoleScopeType.UNIT,
                permissions=["unit.view"],
            )
            cls.teacher = cls._member(f"{p}_teacher", cls.org.roles.get(name="teacher"))
            cls.dean = cls._member(f"{p}_dean", cls.key_role, cls.faculty)
            cls.far_dean = cls._member(f"{p}_far", cls.key_role, cls.far_faculty)
            cls.plain = cls._member(f"{p}_plain", cls.plain_role, cls.faculty)
            cls.org_admin = cls._member(f"{p}_orgadm", cls.org_role)

            cls.program = Program.objects.create(organization=cls.org, code=f"{p.upper()}P", name="Tarix")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2025)
            cls.history = Subject.objects.create(organization=cls.org, code=f"{p.upper()}TAR", name="Tarix", ects=5)
            cls.math = Subject.objects.create(organization=cls.org, code=f"{p.upper()}RIY", name="Riyaziyyat", ects=5)
            cls.physics = Subject.objects.create(organization=cls.org, code=f"{p.upper()}FIZ", name="Fizika", ects=6)
            for subject in (cls.history, cls.math):
                CurriculumSubject.objects.create(
                    organization=cls.org, curriculum=cls.curriculum, subject=subject, semester_number=1
                )
            cls.host = cls._student(f"{p}_host", cls.group1)
            cls.student = cls._student(f"{p}_stud", cls.group2)
            cls.far_student = cls._student(f"{p}_farst", cls.far_group)
            cls.record = StudentAcademicRecord.objects.get(student=cls.student)
            cls.physics_g1 = CourseOffering.objects.create(
                organization=cls.org, subject=cls.physics, period=cls.period, group=cls.group1, instructor=cls.teacher
            )
            Enrollment.objects.create(organization=cls.org, student=cls.host, offering=cls.physics_g1)
            cls.history_g1 = cls.host.enrollments.get(offering__subject=cls.history).offering
            cls.own_history = cls.student.enrollments.get(offering__subject=cls.history).offering
            cls.own_math = cls.student.enrollments.get(offering__subject=cls.math).offering

    @classmethod
    def _member(cls, username, role, unit=None):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw", first_name=username.title())
        Membership.objects.create(
            user=user, organization=cls.org, role=role, scope_unit=unit, is_primary=True, is_active=True
        )
        return user

    @classmethod
    def _student(cls, username, group):
        student = cls._member(username, cls.org.roles.get(name="student"))
        record = StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=student,
            program=cls.program,
            curriculum=cls.curriculum,
            group=group,
            admission_year=2025,
        )
        services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
        return student

    # ── köməkçilər ──────────────────────────────────────────────────────────

    def slot(self, offering, weekday=1, start=(9, 0), end=(10, 20), week_type="all"):
        with bypass_rls():
            return ScheduleSlot.objects.create(
                organization=self.org,
                offering=offering,
                weekday=weekday,
                start_time=datetime.time(*start),
                end_time=datetime.time(*end),
                week_type=week_type,
            )

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client
