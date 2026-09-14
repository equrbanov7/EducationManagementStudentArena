"""Tələbə kabinetinin sorğu büdcəsi: əlavə fənlər N+1 yaratmamalıdır."""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, services
from apps.registrar.models import (
    AttendanceStatus,
    Curriculum,
    CurriculumSubject,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


def _build_tenant(*, slug: str, subject_count: int):
    owner = User.objects.create_user(f"{slug}_owner", f"{slug}_owner@qku.edu.az", "pw")
    with bypass_rls():
        org = Organization.objects.create(
            name=f"{slug} Univ",
            slug=slug,
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        group = OrgUnit.objects.create(organization=org, name="234 KE", slug=f"{slug}-g1", unit_type=OrgUnitType.GROUP)
        period = AcademicPeriod.objects.create(
            organization=org,
            name="2024/2025 Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2024/2025",
            start_date="2024-09-01",
            end_date="2025-01-31",
            is_current=True,
        )
        program = Program.objects.create(organization=org, code="KE", name="Kompüter elmləri", absence_limit_percent=25)
        curriculum = Curriculum.objects.create(organization=org, program=program, admission_year=2024)
        teacher = User.objects.create_user(f"{slug}_teacher", f"{slug}_teacher@qku.edu.az", "pw")
        teacher.first_name, teacher.last_name = "Nigar", "Həsənli"
        teacher.save(update_fields=["first_name", "last_name"])
        Membership.objects.create(
            user=teacher, organization=org, role=org.roles.get(name="teacher"), is_primary=True, is_active=True
        )
        student = User.objects.create_user(f"{slug}_student", f"{slug}_student@qku.edu.az", "pw")
        student.first_name, student.last_name = "Aysel", "Məmmədova"
        student.save(update_fields=["first_name", "last_name"])
        Membership.objects.create(
            user=student, organization=org, role=org.roles.get(name="student"), is_primary=True, is_active=True
        )
        record = StudentAcademicRecord.objects.create(
            organization=org, student=student, program=program, curriculum=curriculum, group=group, admission_year=2024
        )
        for i in range(subject_count):
            subject = Subject.objects.create(organization=org, code=f"KE10{i}", name=f"Fənn {i}", ects=5)
            CurriculumSubject.objects.create(
                organization=org, curriculum=curriculum, subject=subject, semester_number=1
            )
        services.enroll_mandatory_subjects(record=record, period=period, semester_number=1)
        enrollments = list(student.enrollments.select_related("offering").order_by("id"))
        for enrollment in enrollments:
            offering = enrollment.offering
            offering.lesson_hours = 60
            offering.instructor = teacher
            offering.save(update_fields=["lesson_hours", "instructor"])
            for day in (1, 2, 3):
                lesson = gradebook.create_lesson(
                    allow_past=True, offering=offering, date=datetime.date(2024, 10, day), kind=LessonKind.SEMINAR
                )
                LessonMark.objects.create(
                    organization=org,
                    lesson=lesson,
                    enrollment=enrollment,
                    status=AttendanceStatus.PRESENT if day != 3 else AttendanceStatus.ABSENT,
                    score=Decimal(7) if day != 3 else None,
                )
            services.recompute_absence_hours(enrollment) if hasattr(services, "recompute_absence_hours") else None
    return {
        "org": org,
        "student": student,
        "teacher": teacher,
        "record": record,
        "period": period,
        "enrollments": enrollments,
    }


def _client_for(org, user):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


@override_settings(UNIVERSITY_MODE=True)
class MeasureTest(TestCase):
    def _measure(self, tenant, section, extra=""):
        client = _client_for(tenant["org"], tenant["student"])
        url = reverse("accounts:profile") + f"?section={section}{extra}"
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        return len(ctx.captured_queries), resp

    def test_measure(self):
        import os

        t1 = _build_tenant(slug="m1", subject_count=1)
        t3 = _build_tenant(slug="m3", subject_count=4)
        out_dir = os.environ.get("EMS_DUMP_DIR")
        for section in ("my-subjects", "my-journal", "pending-answers"):
            q1, _ = self._measure(t1, section)
            q3, resp = self._measure(t3, section)
            self.assertEqual(q3, q1, f"{section}: fənn sayı sorğu sayını artırdı")
            print(f"\n[{section}] 1 subject = {q1} queries · 4 subjects = {q3} queries")
            if out_dir:
                html = resp.content.decode()
                start = html.index(f'data-profile-section-panel="{section}"')
                begin = html.rindex("<section", 0, start)
                nxt = html.find('<section class="profile-section-panel', start)
                panel = html[begin : nxt if nxt != -1 else len(html)]
                with open(os.path.join(out_dir, f"{section}.html"), "w", encoding="utf-8") as fh:
                    fh.write(panel)
        q1, _ = self._measure(t1, "my-journal", f"&subject={t1['enrollments'][0].id}")
        q3, _ = self._measure(t3, "my-journal", f"&subject={t3['enrollments'][0].id}")
        self.assertEqual(q3, q1, "jurnal detalında N+1")
        print(f"\n[my-journal detail] 1 subject = {q1} queries · 4 subjects = {q3} queries")
