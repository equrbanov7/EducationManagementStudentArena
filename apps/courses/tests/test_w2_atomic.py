"""Dalğa 2 (2026-09-14) — audit 2026-09-13 backend F-07: `AddMemberView` /
`AddMembersBulkView` toplu üzvlük yazısı ``transaction.atomic`` içindədir —
ikinci tələbədə bildiriş sınanda birinci üzvlük də geri alınır."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.exams.models import StudentGroup
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()
PW = "W2AtomicPass123!"


def _assign(user, organization, profile_role, role_name):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={"role": organization.roles.get(name=role_name), "is_primary": True, "is_active": True},
    )


class _Base(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("w2cm_teacher", "w2cm_teacher@example.com", PW)
        self.org = Organization.objects.create(
            name="W2 Members Org",
            slug="w2-members-org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign(self.teacher, self.org, ProfileRole.TEACHER, "teacher")
        self.students = []
        for index in range(2):
            student = User.objects.create_user(f"w2cm_student{index}", f"w2cm_student{index}@example.com", PW)
            _assign(student, self.org, ProfileRole.STUDENT, "student")
            self.students.append(student)
        self.course = Course.objects.create(
            owner=self.teacher, title="W2 Course", status="published", organization=self.org
        )
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def memberships(self):
        return CourseMembership.objects.filter(course=self.course, role="student")


class AddMemberAtomicTest(_Base):
    def _post(self):
        return self.client.post(
            reverse("courses:add_member", kwargs={"course_id": self.course.id}),
            {"user_ids": [str(s.pk) for s in self.students], "group_name": "A"},
        )

    def test_notification_failure_on_second_student_rolls_back_the_first(self):
        calls = {"n": 0}

        def _boom(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("notify boom")

        with mock.patch("apps.notifications.public.notify_course_membership_assigned", side_effect=_boom):
            with self.assertRaises(RuntimeError):
                self._post()
        self.assertEqual(self.memberships().count(), 0)

    def test_happy_path_adds_every_student(self):
        response = self._post()
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.assertEqual(self.memberships().count(), 2)


class AddMembersBulkAtomicTest(_Base):
    def setUp(self):
        super().setUp()
        self.group = StudentGroup.objects.create(name="W2-G", teacher=self.teacher, organization=self.org)
        self.group.students.set(self.students)

    def _post(self):
        return self.client.post(
            reverse("courses:add_members_bulk", kwargs={"course_id": self.course.id}),
            {"group_ids": [str(self.group.pk)]},
        )

    def test_notification_failure_rolls_back_the_whole_group(self):
        calls = {"n": 0}

        def _boom(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("notify boom")

        with mock.patch("apps.notifications.public.notify_course_membership_assigned", side_effect=_boom):
            response = self._post()
        # View geniş `except Exception` ilə 500 JSON qaytarır — amma yarım qrup qalmır.
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.memberships().count(), 0)

    def test_happy_path_adds_every_group_student(self):
        response = self._post()
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.assertEqual(self.memberships().count(), 2)
