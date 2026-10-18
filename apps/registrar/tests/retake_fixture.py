"""25% / alt qrup testləri üçün ortaq qurğu (sahib 2026-10-18).

Struktur: fakültə A (kafedra → qruplar G1, G2) + fakültə B (qrup GX). Keçmiş dövr (2025/2026 Payız) — tələbə
fənni kəsib; cari dövr (2025/2026 Yaz) — G2-nin eyni fənn üzrə jurnalı (alt qrup hədəfi).
Rollar açarla birbaşa yaradılır (``organizations`` rol şablonlarına toxunmadan): mühasib (org-geniş
``retake.payment_verify``), dekan A (fakültə A ``retake.manage``), dekan B (fakültə B ``retake.manage``),
koordinator (``student.records_view``, fakültə A).
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar import finals, services
from apps.registrar.models import CourseOffering, Curriculum, CurriculumSubject, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def pdf(name="qebz.pdf", content=PDF_BYTES):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


class RetakeBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rt_owner", "rt_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="RT Univ",
                slug="rt-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə A", slug="rt-fa", unit_type=OrgUnitType.FACULTY
            )
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra", slug="rt-k", unit_type=OrgUnitType.CHAIR, parent=cls.faculty
            )
            cls.group1 = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="rt-g1", unit_type=OrgUnitType.GROUP, parent=cls.chair
            )
            cls.group2 = OrgUnit.objects.create(
                organization=cls.org, name="G2", slug="rt-g2", unit_type=OrgUnitType.GROUP, parent=cls.chair
            )
            cls.faculty_b = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə B", slug="rt-fb", unit_type=OrgUnitType.FACULTY
            )
            cls.group_b = OrgUnit.objects.create(
                organization=cls.org, name="GX", slug="rt-gx", unit_type=OrgUnitType.GROUP, parent=cls.faculty_b
            )
            cls.past = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2025/2026 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date="2025-09-15",
                end_date="2026-01-31",
                is_current=False,
            )
            cls.current = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2025/2026 Yaz",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date="2026-02-15",
                end_date="2026-06-30",
                is_current=True,
            )
            cls.program = Program.objects.create(
                organization=cls.org, code="INF", name="İnformatika", absence_limit_percent=25
            )
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2025)
            cls.subject = Subject.objects.create(organization=cls.org, code="INF101", name="Proqramlaşdırma")
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
            )
            cls.teacher = User.objects.create_user("rt_teacher", "rt_teacher@qku.edu.az", "pw")
            cls._member(cls.teacher, cls.org.roles.get(name="teacher"))
            cls.accountant = cls._staff("rt_acc", ["retake.payment_verify"], RoleScopeType.ORGANIZATION)
            cls.dean = cls._staff("rt_dean", ["retake.manage"], RoleScopeType.UNIT, cls.faculty)
            cls.dean_b = cls._staff("rt_dean_b", ["retake.manage"], RoleScopeType.UNIT, cls.faculty_b)
            cls.coordinator = cls._staff("rt_coord", ["student.records_view"], RoleScopeType.UNIT, cls.faculty)
            cls.student = cls._student("rt_student", cls.group1)
            cls.other = cls._student("rt_other", cls.group1)
            cls.far = cls._student("rt_far", cls.group_b)
            cls.enrollment = cls.student.enrollments.get(offering__subject=cls.subject)
            cls.offering = cls.enrollment.offering
            cls.offering.lesson_hours = 60
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["lesson_hours", "instructor"])
            # 2026-10-19: müraciət yalnız İmtahan mərkəzinin açdığı pəncərədə qəbul olunur.
            from django.utils import timezone

            from apps.registrar.models import RetakeWindow

            cls.window = RetakeWindow.objects.create(
                organization=cls.org, period=cls.current, opens_at=timezone.now() - datetime.timedelta(days=1)
            )
            cls.target = CourseOffering.objects.create(
                organization=cls.org, subject=cls.subject, period=cls.current, group=cls.group2
            )

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
            level=70,
            scope_type=scope_type,
            permissions=permissions,
        )
        cls._member(user, role, unit)
        return user

    @classmethod
    def _student(cls, username, group):
        from apps.accounts.models import ProfileRole

        student = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        profile = student.profile
        profile.organization = cls.org
        profile.organization_type = cls.org.org_type
        profile.role = ProfileRole.STUDENT
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
        cls._member(student, cls.org.roles.get(name="student"))
        record = StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=student,
            program=cls.program,
            curriculum=cls.curriculum,
            group=group,
            admission_year=2025,
        )
        services.enroll_mandatory_subjects(record=record, period=cls.past, semester_number=1)
        return student

    # ── köməkçilər ──────────────────────────────────────────────────────────
    def fail_exam(self, enrollment=None, score=10):
        """İmtahandan kəsilmə (giriş 0 + imtahan < minimum) → 25% uyğundur."""
        with bypass_rls():
            finals.set_exam_score(enrollment=enrollment or self.enrollment, score=score, by_user=self.teacher)

    def bar_by_absence(self, enrollment=None):
        with bypass_rls():
            target = enrollment or self.enrollment
            target.absence_hours = 20  # 60 saatın 25%-i = 15 saat
            target.save(update_fields=["absence_hours"])
            finals.evaluate_resit(enrollment=target, by_user=self.teacher)

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def today(self):
        return datetime.date.today()
