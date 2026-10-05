"""Təhlükəsizlik auditi 2026-10-05 — kurs resursu başqa kursun mövzusuna bağlana bilməz.

``CourseResourceForm.topic`` default queryset-i BÜTÜN ``CourseTopic``-lər idi.
Kurs A-nın sahibi ``topic=<B kursunun mövzu id-si>`` göndərəndə resurs B kursunun
mövzu akkordeonunda (``topic.resources``) görünürdü — başqa (hətta başqa
tenant-ın) kursuna link/fayl yeridilməsi.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseResource, CourseTopic

from .test_tenant_isolation import _assign_user_to_org, _create_org, _create_role, _login_with_org

User = get_user_model()


class ResourceTopicOwnershipTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher_a = User.objects.create_user("sec_rt_a", "sec_rt_a@orga.com", "StrongPass123!")
        self.teacher_b = User.objects.create_user("sec_rt_b", "sec_rt_b@orgb.com", "StrongPass123!")
        self.org_a = _create_org("SecRT Org A", "sec-rt-org-a", self.teacher_a)
        self.org_b = _create_org("SecRT Org B", "sec-rt-org-b", self.teacher_b)
        _assign_user_to_org(
            self.teacher_a,
            self.org_a,
            ProfileRole.TEACHER,
            _create_role(self.org_a, "teacher", level=60, permissions=["course.*"]),
        )
        _assign_user_to_org(
            self.teacher_b,
            self.org_b,
            ProfileRole.TEACHER,
            _create_role(self.org_b, "teacher", level=60, permissions=["course.*"]),
        )
        self.course_a = Course.objects.create(
            owner=self.teacher_a, title="A", status="published", organization=self.org_a
        )
        self.course_b = Course.objects.create(
            owner=self.teacher_b, title="B", status="published", organization=self.org_b
        )
        self.topic_a = CourseTopic.objects.create(course=self.course_a, title="A1", order=1)
        self.topic_b = CourseTopic.objects.create(course=self.course_b, title="B1", order=1)
        _login_with_org(self.client, self.teacher_a, self.org_a)

    def _post(self, topic):
        return self.client.post(
            reverse("courses:add_resource", kwargs={"course_id": self.course_a.id}),
            {"title": "Link", "resource_type": "link", "url": "https://example.com/x", "topic": topic.id},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_foreign_course_topic_is_rejected(self):
        self._post(self.topic_b)
        self.assertFalse(CourseResource.objects.filter(topic=self.topic_b).exists())

    def test_own_course_topic_is_accepted(self):
        response = self._post(self.topic_a)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CourseResource.objects.filter(course=self.course_a, topic=self.topic_a).exists())
