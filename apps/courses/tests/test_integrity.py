"""
Integrity tests for destructive actions and cascade behavior.

Tests cascade (ON DELETE CASCADE) and SET_NULL (ON DELETE SET_NULL) behavior
for courses, organizations, memberships, and audit logs to ensure data-loss
risks are detectable and audit data is preserved as expected.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase
from django.utils import timezone

from apps.assignments.models import Assignment
from apps.audit.models import AuditLog
from apps.courses.models import Course
from apps.exams.models import Exam
from apps.labs.models import Lab
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.signals import create_default_roles
from core.constants import AuditAction, OrganizationType, RoleScopeType

User = get_user_model()


def _make_lab(course, owner, title="Lab"):
    """Create a minimal valid Lab."""
    now = timezone.now()
    return Lab.objects.create(
        title=title,
        course=course,
        created_by=owner,
        start_datetime=now,
        end_datetime=now + timedelta(days=7),
    )


def _make_assignment(course, owner, title="Assignment"):
    """Create a minimal valid Assignment."""
    return Assignment.objects.create(
        title=title,
        course=course,
        created_by=owner,
        start_date=timezone.now(),
    )


class CourseDeletionCascadeTest(TestCase):
    """
    Verify cascade behavior when a Course is deleted.

    - Labs linked to the course → deleted (CASCADE)
    - Assignments linked to the course → deleted (CASCADE)
    - Exams linked to the course → kept, course FK set to NULL (SET_NULL)
    """

    def setUp(self):
        post_save.disconnect(create_default_roles, sender=Organization)
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="pass"
        )
        self.org = Organization.objects.create(
            name="Test Org",
            slug="test-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
        )
        self.course = Course.objects.create(
            title="Test Course",
            owner=self.owner,
            organization=self.org,
        )

    def tearDown(self):
        post_save.connect(create_default_roles, sender=Organization)

    def test_labs_deleted_when_course_deleted(self):
        """Deleting a course cascades to its labs."""
        lab = _make_lab(self.course, self.owner, "Lab 1")
        lab_pk = lab.pk
        self.course.delete()
        self.assertFalse(Lab.objects.filter(pk=lab_pk).exists())

    def test_multiple_labs_deleted_when_course_deleted(self):
        """All labs belonging to a deleted course are removed."""
        lab1 = _make_lab(self.course, self.owner, "Lab A")
        lab2 = _make_lab(self.course, self.owner, "Lab B")
        self.course.delete()
        self.assertFalse(Lab.objects.filter(pk__in=[lab1.pk, lab2.pk]).exists())

    def test_assignments_deleted_when_course_deleted(self):
        """Deleting a course cascades to its assignments."""
        assignment = _make_assignment(self.course, self.owner, "HW 1")
        assignment_pk = assignment.pk
        self.course.delete()
        self.assertFalse(Assignment.objects.filter(pk=assignment_pk).exists())

    def test_multiple_assignments_deleted_when_course_deleted(self):
        """All assignments belonging to a deleted course are removed."""
        a1 = _make_assignment(self.course, self.owner, "HW 1")
        a2 = _make_assignment(self.course, self.owner, "HW 2")
        self.course.delete()
        self.assertFalse(Assignment.objects.filter(pk__in=[a1.pk, a2.pk]).exists())

    def test_exams_preserved_with_null_course_when_course_deleted(self):
        """Deleting a course sets course=None on linked exams (SET_NULL)."""
        exam = Exam.objects.create(
            title="Midterm",
            author=self.owner,
            organization=self.org,
            course=self.course,
        )
        exam_pk = exam.pk
        self.course.delete()
        exam.refresh_from_db()
        self.assertIsNone(exam.course)
        self.assertTrue(Exam.objects.filter(pk=exam_pk).exists())

    def test_labs_of_other_courses_not_affected(self):
        """Deleting one course does not remove labs from other courses."""
        other_course = Course.objects.create(
            title="Other Course",
            owner=self.owner,
            organization=self.org,
        )
        other_lab = _make_lab(other_course, self.owner, "Other Lab")
        self.course.delete()
        self.assertTrue(Lab.objects.filter(pk=other_lab.pk).exists())


class OrganizationDeletionCascadeTest(TestCase):
    """
    Verify cascade behavior when an Organization is deleted or deactivated.

    - Memberships → deleted (CASCADE)
    - Organization deactivation → memberships still exist (flag-only change)
    """

    def setUp(self):
        post_save.disconnect(create_default_roles, sender=Organization)
        self.owner = User.objects.create_user(
            username="owner2", email="owner2@test.com", password="pass"
        )
        self.member = User.objects.create_user(
            username="member", email="member@test.com", password="pass"
        )
        self.org = Organization.objects.create(
            name="University",
            slug="university",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
        )
        self.role = Role.objects.create(
            organization=self.org,
            name="student",
            display_name="Student",
            level=10,
            scope_type=RoleScopeType.COURSE,
            permissions=[],
        )
        self.membership = Membership.objects.create(
            user=self.member,
            organization=self.org,
            role=self.role,
            is_primary=True,
        )

    def tearDown(self):
        post_save.connect(create_default_roles, sender=Organization)

    def test_memberships_deleted_when_organization_deleted(self):
        """Deleting an organization cascades to all its memberships."""
        membership_pk = self.membership.pk
        self.org.delete()
        self.assertFalse(Membership.objects.filter(pk=membership_pk).exists())

    def test_multiple_memberships_deleted_when_organization_deleted(self):
        """All memberships for a deleted organization are removed."""
        extra_user = User.objects.create_user(
            username="extra", email="extra@test.com", password="pass"
        )
        extra_membership = Membership.objects.create(
            user=extra_user,
            organization=self.org,
            role=self.role,
        )
        all_pks = [self.membership.pk, extra_membership.pk]
        self.org.delete()
        self.assertFalse(Membership.objects.filter(pk__in=all_pks).exists())

    def test_organization_deactivation_preserves_memberships(self):
        """Deactivating an organization does not delete its memberships."""
        self.org.is_active = False
        self.org.save()
        self.assertTrue(Membership.objects.filter(pk=self.membership.pk).exists())

    def test_membership_deactivation_preserves_record(self):
        """Deactivating a membership keeps it in the database."""
        self.membership.is_active = False
        self.membership.save()
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.is_active)
        self.assertTrue(Membership.objects.filter(pk=self.membership.pk).exists())

    def test_memberships_of_other_organizations_not_affected(self):
        """Deleting one organization does not remove memberships from others."""
        other_org = Organization.objects.create(
            name="Other Org",
            slug="other-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
        )
        other_role = Role.objects.create(
            organization=other_org,
            name="student",
            display_name="Student",
            level=10,
            scope_type=RoleScopeType.COURSE,
            permissions=[],
        )
        other_membership = Membership.objects.create(
            user=self.member,
            organization=other_org,
            role=other_role,
        )
        self.org.delete()
        self.assertTrue(Membership.objects.filter(pk=other_membership.pk).exists())


class AuditLogPreservationOnUserDeleteTest(TestCase):
    """
    Verify that audit logs are preserved when a User is deleted.

    AuditLog.user uses on_delete=SET_NULL, so deleting a user should
    keep the audit log record with user=None (not delete it).
    """

    def setUp(self):
        post_save.disconnect(create_default_roles, sender=Organization)
        self.owner = User.objects.create_user(
            username="org_owner", email="org_owner@test.com", password="pass"
        )
        self.user = User.objects.create_user(
            username="audited", email="audited@test.com", password="pass"
        )
        self.org = Organization.objects.create(
            name="Audit Org",
            slug="audit-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
        )

    def tearDown(self):
        post_save.connect(create_default_roles, sender=Organization)

    def test_audit_log_preserved_when_user_deleted(self):
        """Deleting a user sets audit_log.user=None; the log record survives."""
        log = AuditLog.objects.create(
            action=AuditAction.CREATE,
            user=self.user,
            organization=self.org,
            resource_type="Course",
            resource_id="1",
            resource_repr="Test Course",
        )
        log_pk = log.pk
        self.user.delete()
        log.refresh_from_db()
        self.assertIsNone(log.user)
        self.assertTrue(AuditLog.objects.filter(pk=log_pk).exists())

    def test_multiple_audit_logs_preserved_when_user_deleted(self):
        """All audit logs for a deleted user are preserved with user=None."""
        log1 = AuditLog.objects.create(
            action=AuditAction.CREATE,
            user=self.user,
            organization=self.org,
            resource_type="Exam",
            resource_id="10",
            resource_repr="Exam 1",
        )
        log2 = AuditLog.objects.create(
            action=AuditAction.UPDATE,
            user=self.user,
            organization=self.org,
            resource_type="Exam",
            resource_id="10",
            resource_repr="Exam 1 edited",
        )
        self.user.delete()
        self.assertTrue(AuditLog.objects.filter(pk=log1.pk, user__isnull=True).exists())
        self.assertTrue(AuditLog.objects.filter(pk=log2.pk, user__isnull=True).exists())

    def test_audit_log_organization_set_null_when_org_deleted(self):
        """Deleting an org sets audit_log.organization=None; the log survives."""
        log = AuditLog.objects.create(
            action=AuditAction.DELETE,
            user=self.user,
            organization=self.org,
            resource_type="Course",
            resource_id="99",
            resource_repr="Deleted Course",
        )
        log_pk = log.pk
        self.org.delete()
        log.refresh_from_db()
        self.assertIsNone(log.organization)
        self.assertTrue(AuditLog.objects.filter(pk=log_pk).exists())
