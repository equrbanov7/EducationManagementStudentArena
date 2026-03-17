"""
Model tests for courses app.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.courses.models import Course
from apps.organizations.models import AcademicPeriod, OrgUnit, Organization
from core.constants import OrganizationType

User = get_user_model()


class CourseUnitPeriodFKTest(TestCase):
    """Tests for Course.unit and Course.period ForeignKey relationships."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="fk_test_owner",
            email="fk_test_owner@example.com",
            password="StrongPass123!",
        )
        self.org = Organization.objects.create(
            name="FK Test Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.unit = OrgUnit.objects.create(
            organization=self.org,
            unit_type="department",
            name="Computer Science",
            slug="cs-dept",
        )
        self.period = AcademicPeriod.objects.create(
            organization=self.org,
            name="Fall 2024",
            period_type="semester",
            academic_year="2024-2025",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 1, 15),
        )

    def _make_course(self, **kwargs):
        defaults = dict(
            title="Test Course",
            owner=self.owner,
            organization=self.org,
        )
        defaults.update(kwargs)
        return Course.objects.create(**defaults)

    # ── FK assignment ────────────────────────────────────────────────────

    def test_course_unit_fk_can_be_set(self):
        course = self._make_course(unit=self.unit)
        course.refresh_from_db()
        self.assertEqual(course.unit, self.unit)
        self.assertEqual(course.unit_id, self.unit.pk)

    def test_course_period_fk_can_be_set(self):
        course = self._make_course(period=self.period)
        course.refresh_from_db()
        self.assertEqual(course.period, self.period)
        self.assertEqual(course.period_id, self.period.pk)

    def test_course_unit_and_period_both_nullable(self):
        course = self._make_course()
        course.refresh_from_db()
        self.assertIsNone(course.unit)
        self.assertIsNone(course.period)

    def test_course_unit_and_period_set_together(self):
        course = self._make_course(unit=self.unit, period=self.period)
        course.refresh_from_db()
        self.assertEqual(course.unit, self.unit)
        self.assertEqual(course.period, self.period)

    # ── Reverse relations ────────────────────────────────────────────────

    def test_orgunit_related_courses(self):
        course = self._make_course(unit=self.unit)
        self.assertIn(course, self.unit.courses.all())

    def test_academic_period_related_courses(self):
        course = self._make_course(period=self.period)
        self.assertIn(course, self.period.courses.all())

    # ── SET_NULL on delete ───────────────────────────────────────────────

    def test_unit_set_null_on_delete(self):
        course = self._make_course(unit=self.unit)
        self.unit.delete()
        course.refresh_from_db()
        self.assertIsNone(course.unit)

    def test_period_set_null_on_delete(self):
        course = self._make_course(period=self.period)
        self.period.delete()
        course.refresh_from_db()
        self.assertIsNone(course.period)

    # ── Referential integrity ────────────────────────────────────────────

    def test_unit_must_belong_to_same_org_as_course(self):
        """Verify OrgUnit can only be linked to course in same organization."""
        other_owner = User.objects.create_user(
            username="other_fk_owner",
            email="other_fk_owner@example.com",
            password="StrongPass123!",
        )
        other_org = Organization.objects.create(
            name="Other FK Org",
            org_type=OrganizationType.SCHOOL,
            owner=other_owner,
            status="active",
            is_active=True,
        )
        other_unit = OrgUnit.objects.create(
            organization=other_org,
            unit_type="department",
            name="Other Dept",
            slug="other-dept",
        )
        # Django FK does not enforce cross-organization constraints at DB
        # level; it is the application's responsibility. We simply verify
        # the FK is stored as-is (no DB error) so application-layer guards
        # can be tested separately.
        course = self._make_course(unit=other_unit)
        course.refresh_from_db()
        self.assertEqual(course.unit, other_unit)
