"""Audit 2026-09-28 SA-09 — müəllim DƏRS DEMƏDİYİ qrupu kursa əlavə edəndə audit.

Funksiya saxlanılır (sahibin dizaynı: «digər aktiv qruplar axtarışla»), lakin
başqa qrupun siyahısını kursa çəkmək audit jurnalına düşür; öz qrupu üçün
əlavə audit sətri yaratmır.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.audit.models import AuditLog
from apps.courses.models import CourseMembership
from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar.models import CourseOffering, Curriculum, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrgUnitType

from .test_course_panel_2026_09_28 import _PanelBase

User = get_user_model()

RESOURCE = "courses.course_group_add_untaught"


class UntaughtGroupAddAuditTest(_PanelBase):
    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.period = AcademicPeriod.objects.create(
            organization=self.org,
            name="Cari",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year=f"{today.year}/{today.year + 1}",
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=90),
            is_current=True,
        )
        self.program = Program.objects.create(organization=self.org, code="CP-PRG", name="CP ixtisas")
        self.curriculum = Curriculum.objects.create(organization=self.org, program=self.program, admission_year=2024)
        self.subject = Subject.objects.create(organization=self.org, code="CP-101", name="CP fənn")
        self.own_group = OrgUnit.objects.create(
            organization=self.org, unit_type=OrgUnitType.GROUP, name="CP-OWN", slug="cp-own"
        )
        self.foreign_group = OrgUnit.objects.create(
            organization=self.org, unit_type=OrgUnitType.GROUP, name="CP-FOREIGN", slug="cp-foreign"
        )
        CourseOffering.objects.create(
            organization=self.org,
            subject=self.subject,
            period=self.period,
            group=self.own_group,
            instructor=self.teacher,
        )
        self.own_student = self._student("cp_own_st", self.own_group)
        self.foreign_student = self._student("cp_foreign_st", self.foreign_group)

    def _student(self, username, group):
        user = User.objects.create_user(username, f"{username}@example.com", "pw")
        self._join(user, ProfileRole.STUDENT, "student")
        StudentAcademicRecord.objects.create(
            organization=self.org,
            student=user,
            program=self.program,
            curriculum=self.curriculum,
            group=group,
            admission_year=2024,
        )
        return user

    def _add(self, *groups):
        return self.client.post(
            reverse("courses:add_members_bulk", kwargs={"course_id": self.course.id}),
            {"group_ids": [str(group.pk) for group in groups]},
        )

    def test_untaught_group_add_is_audited(self):
        response = self._add(self.own_group, self.foreign_group)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["added_count"], 2)
        self.assertTrue(CourseMembership.objects.filter(course=self.course, user=self.foreign_student).exists())
        rows = AuditLog.objects.filter(resource_type=RESOURCE, resource_id=str(self.course.pk))
        self.assertEqual(rows.count(), 1)
        row = rows.get()
        self.assertEqual(row.user_id, self.teacher.pk)
        self.assertEqual(row.new_values["group_id"], str(self.foreign_group.pk))
        self.assertEqual(row.new_values["added"], 1)

    def test_own_group_add_writes_no_extra_audit(self):
        response = self._add(self.own_group)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(AuditLog.objects.filter(resource_type=RESOURCE).exists())
