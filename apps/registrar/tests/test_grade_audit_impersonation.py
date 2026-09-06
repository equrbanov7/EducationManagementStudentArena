"""«Başqasının adından» yazılan bal dəyişikliyində ƏSL aktorun izi (sahib qərarı).

2026-09-06: «RİM başqasının yerinə yaza bilər, amma RİM izi düşsün ki, bunu RİM
edib». Jurnalın öz bal auditi (`grade_audit.log_grade_changes`) `core.audit`-dən
KEÇMİR — sətri birbaşa yazır, ona görə möhür orada da ayrıca qoyulmalıdır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Organization
from apps.registrar import grade_audit
from apps.registrar.models import Subject
from core.audit import IMPERSONATION_KEY
from core.constants import AcademicPeriodType, OrganizationType
from core.rls import bypass_rls

User = get_user_model()


class GradeAuditImpersonationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ga_owner", "ga_owner@qku.edu.az", "pw")
        cls.teacher = User.objects.create_user("ga_teacher", "ga_teacher@qku.edu.az", "pw")
        cls.rim = User.objects.create_user("ga_rim", "ga_rim@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="GA Univ",
                slug="ga-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
        cls.period = AcademicPeriod.objects.create(
            organization=cls.org,
            name="Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2025/2026",
            start_date="2025-09-01",
            end_date="2026-01-15",
            is_current=True,
        )
        cls.subject = Subject.objects.create(organization=cls.org, code="GA101", name="Test")
        from apps.registrar import services

        cls.offering = services.get_or_create_offering(
            organization=cls.org, subject=cls.subject, period=cls.period, group=None
        )

    def _changes(self):
        return [{"student": "Tələbə", "item": "01.09 · Mühazirə", "old": "", "new": "8"}]

    def test_a_plain_save_carries_no_impersonation_stamp(self):
        grade_audit.log_grade_changes(
            offering=self.offering, by_user=self.teacher, kind="mark", changes=self._changes()
        )
        row = AuditLog.objects.filter(resource_type="registrar.grade.mark").latest("id")
        self.assertEqual(row.user_id, self.teacher.id)
        self.assertNotIn(IMPERSONATION_KEY, str(row.changes))

    def test_a_save_under_view_as_names_the_real_actor(self):
        request = RequestFactory().post("/jurnal/")
        request.user = self.teacher
        request.real_user = self.rim
        request.is_view_as = True
        request.view_as_mode = "limited"

        grade_audit.log_grade_changes(
            offering=self.offering,
            by_user=self.teacher,
            kind="mark",
            changes=self._changes(),
            request=request,
        )
        row = AuditLog.objects.filter(resource_type="registrar.grade.mark").latest("id")
        stamps = [entry for entry in row.changes if isinstance(entry, dict) and IMPERSONATION_KEY in entry]
        self.assertEqual(len(stamps), 1, row.changes)
        self.assertEqual(stamps[0][IMPERSONATION_KEY]["username"], "ga_rim")
        self.assertEqual(stamps[0][IMPERSONATION_KEY]["mode"], "limited")
        # Dəyişikliyin özü qorunur — möhür ONA ƏLAVƏDİR, əvəz DEYİL.
        self.assertEqual(len(row.changes), 2)
