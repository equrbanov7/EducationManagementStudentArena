"""«Jurnal təmizliyi» testlərinin ORTAQ fiksturu (sahib 2026-10-10).

Tarixlər bu günə görə qurulur (cari / gələcək / keçmiş dövr), ona görə testlər təqvimdən asılı deyil.
Tələbələr ``Enrollment.objects.create`` ilə birbaşa yazılır: xaric / arxiv tələbəyə ``services`` artıq
YENİ sətir yaratmır (önləmə qapısı) — tarixi vəziyyəti məhz belə qurmaq lazımdır.
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook
from apps.registrar.models import (
    AcademicStatus,
    AssessmentScheme,
    AttendanceStatus,
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    EnrollmentKind,
    Lesson,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

REASON = "Rektorun xaric əmrləri əsasında jurnallar təmizlənir (test qeydi)."


class HygieneBase(TestCase):
    """Bir universitet, fakültə → 2 qrup, 3 dövr, 3 fənn; köməkçilər tələbə/sətir/bal yaradır."""

    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.year_start = cls.today.year if cls.today.month >= 9 else cls.today.year - 1
        cls.owner = User.objects.create_user("jh_owner", "jh_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JH Univ",
                slug="jh-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="JH Fakültə", slug="jh-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="JH-101", slug="jh-g1", unit_type=OrgUnitType.GROUP, parent=cls.faculty
            )
            cls.group2 = OrgUnit.objects.create(
                organization=cls.org, name="JH-102", slug="jh-g2", unit_type=OrgUnitType.GROUP, parent=cls.faculty
            )
            cls.past = cls._period("Keçmiş", -400, -200)
            cls.current = cls._period("Cari", -30, 90, is_current=True)
            cls.future = cls._period("Gələcək", 120, 240)
            cls.program = Program.objects.create(organization=cls.org, code="JHCS", name="Kompüter elmləri")
            cls.curriculum = Curriculum.objects.create(
                organization=cls.org, program=cls.program, admission_year=cls.year_start - 1
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="JH-1", name="Alqoritmlər")
            cls.subject_b = Subject.objects.create(organization=cls.org, code="JH-2", name="Verilənlər bazası")
            cls.subject_c = Subject.objects.create(organization=cls.org, code="JH-3", name="Şəbəkələr")
            for subject in (cls.subject, cls.subject_b):
                CurriculumSubject.objects.create(
                    organization=cls.org, curriculum=cls.curriculum, subject=subject, semester_number=1
                )
            cls.offering = cls._offering(cls.subject, cls.current)
            cls.teacher = User.objects.create_user("jh_teacher", "jh_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )

    # ── köməkçilər ──────────────────────────────────────────────────────────

    @classmethod
    def _period(cls, name, start, end, *, is_current=False):
        return AcademicPeriod.objects.create(
            organization=cls.org,
            name=name,
            period_type=AcademicPeriodType.SEMESTER,
            academic_year=f"{cls.year_start}/{cls.year_start + 1}",
            start_date=cls.today + dt.timedelta(days=start),
            end_date=cls.today + dt.timedelta(days=end),
            is_current=is_current,
        )

    @classmethod
    def _offering(cls, subject, period, group=None, **extra):
        return CourseOffering.objects.create(
            organization=cls.org, subject=subject, period=period, group=group or cls.group, **extra
        )

    @classmethod
    def make_student(
        cls,
        username,
        *,
        status=AcademicStatus.ENROLLED,
        is_active=True,
        admission_year=None,
        archived=False,
        group=None,
        with_record=True,
    ):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw", first_name="Ad", last_name=username)
        Membership.objects.create(
            user=user, organization=cls.org, role=cls.org.roles.get(name="student"), is_primary=True, is_active=True
        )
        if archived:
            UserProfile.objects.filter(user=user).update(access_state=UserProfile.AccessState.ARCHIVED)
        if with_record:
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=user,
                program=cls.program,
                curriculum=cls.curriculum,
                group=group or cls.group,
                admission_year=admission_year or cls.year_start - 1,
                status=status,
                is_active=is_active,
            )
        return user

    @classmethod
    def enroll(cls, student, offering=None, **extra):
        return Enrollment.objects.create(
            organization=cls.org, student=student, offering=offering or cls.offering, **extra
        )

    @classmethod
    def lesson(cls, offering=None, *, days=-7):
        return Lesson.objects.create(
            organization=cls.org,
            offering=offering or cls.offering,
            date=cls.today + dt.timedelta(days=days),
            kind=LessonKind.SEMINAR,
            hours=2,
        )

    @classmethod
    def mark(cls, enrollment, lesson=None):
        lesson = lesson or cls.lesson(enrollment.offering)
        return LessonMark.objects.create(
            organization=cls.org, lesson=lesson, enrollment=enrollment, status=AttendanceStatus.PRESENT
        )

    @staticmethod
    def close_journal(offering):
        scheme = gradebook.ensure_assessment_scheme(offering=offering)
        AssessmentScheme.objects.filter(pk=scheme.pk).update(is_published=True, approval_status="approved")

    @staticmethod
    def status_of(enrollment):
        return Enrollment.objects.get(pk=enrollment.pk).status


__all__ = ["REASON", "EnrollmentKind", "HygieneBase", "User"]
