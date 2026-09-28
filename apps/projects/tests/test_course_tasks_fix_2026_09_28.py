"""Kurs tapşırıqları düzəlişi (2026-09-28) — kurs işləri (projects).

* redaktə GET `group_excluded_student_ids` qaytarır (qismən seçim genişlənmir);
* redaktə tarixi yerli vaxtla qaytarılır (toxunulmamış saxlama tarixi sürüşdürmür);
* `students[]` yalnız kursun tələbə üzvlərini qəbul edir;
* bölmədə sahib olmayan müəllimə ölü düymələr göstərilmir.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.organizations.models import Organization
from apps.projects.models import Project
from apps.projects.tests.test_views import _assign_user_to_org, _login_with_org
from core.constants import OrganizationType

User = get_user_model()
_PASSWORD = "StrongPass123!"


class ProjectCourseTasksFixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ctf_p_owner", "ctf_p_owner@example.com", _PASSWORD)
        cls.teacher = User.objects.create_user("ctf_p_teacher", "ctf_p_teacher@example.com", _PASSWORD)
        cls.organization = Organization.objects.create(
            name="CTF P Org", org_type=OrganizationType.SCHOOL, owner=cls.owner, status="active", is_active=True
        )
        _assign_user_to_org(cls.owner, cls.organization, ProfileRole.TEACHER)
        _assign_user_to_org(cls.teacher, cls.organization, ProfileRole.TEACHER)
        cls.course = Course.objects.create(owner=cls.owner, title="CTF P Course", status="published")
        cls.s1, cls.s2, cls.s3 = (
            User.objects.create_user(f"ctf_p_s{i}", f"ctf_p_s{i}@example.com", _PASSWORD) for i in (1, 2, 3)
        )
        for student in (cls.s1, cls.s2, cls.s3):
            _assign_user_to_org(student, cls.organization, ProfileRole.STUDENT)
            CourseMembership.objects.create(course=cls.course, user=student, role="student", group_name="P1")
        cls.outsider = User.objects.create_user("ctf_p_out", "ctf_p_out@example.com", _PASSWORD)
        _assign_user_to_org(cls.outsider, cls.organization, ProfileRole.STUDENT)

    def setUp(self):
        self.client = Client()
        _login_with_org(self.client, self.owner, self.organization)
        now = timezone.now().replace(second=0, microsecond=0)
        self.project = Project.objects.create(
            course=self.course,
            title="CTF Project",
            start_date=now - timedelta(days=1),
            deadline=now + timedelta(days=3),
            status="active",
            max_score=40,
        )
        self.project.assigned_students.set([self.s1, self.s2])
        self.url = reverse("projects:edit_project", args=[self.project.id])

    def _payload(self, data, **overrides):
        payload = {
            "title": data["title"],
            "description": data["description"],
            "start_date": data["start_date"],
            "deadline": data["deadline"],
            "max_attempts": data["max_attempts"],
            "max_score": data["max_score"],
            "status": data["status"],
            "group_names[]": data["group_names"],
            "students[]": [str(sid) for sid in data["student_ids"]],
        }
        payload.update(overrides)
        return payload

    def test_edit_get_marks_unassigned_group_members_as_excluded(self):
        data = self.client.get(self.url).json()["data"]
        self.assertEqual(data["group_names"], ["P1"])
        self.assertEqual(data["group_excluded_student_ids"], [self.s3.id])

    def test_untouched_edit_round_trip_keeps_targets_and_dates(self):
        data = self.client.get(self.url).json()["data"]
        before_start, before_deadline = self.project.start_date, self.project.deadline
        response = self.client.post(self.url, self._payload(data))
        self.assertTrue(response.json()["success"], response.content[:300])
        self.project.refresh_from_db()
        self.assertEqual(sorted(self.project.assigned_students.values_list("id", flat=True)), [self.s1.id, self.s2.id])
        self.assertEqual(self.project.start_date, before_start)
        self.assertEqual(self.project.deadline, before_deadline)
        self.assertEqual(self.project.max_score, 40)

    def test_create_accepts_only_course_students(self):
        response = self.client.post(
            reverse("projects:create_project", args=[self.course.id]),
            {
                "title": "Foreign ids",
                "start_date": "2026-10-01T10:00",
                "deadline": "2026-10-05T10:00",
                "status": "active",
                "students[]": [str(self.s3.id), str(self.outsider.id), str(self.teacher.id)],
            },
        )
        self.assertTrue(response.json()["success"], response.content[:300])
        project = Project.objects.get(id=response.json()["project_id"])
        self.assertEqual(list(project.assigned_students.values_list("id", flat=True)), [self.s3.id])
        # datetime-local dəyəri layihə vaxt qurşağında saxlanılır
        self.assertEqual(timezone.localtime(project.start_date).strftime("%Y-%m-%dT%H:%M"), "2026-10-01T10:00")

    def test_section_hides_owner_controls_from_non_owner(self):
        request = RequestFactory().get("/courses/1/")
        request.user = self.teacher
        context = {
            "request": request,
            "is_teacher": True,
            "is_student": False,
            "projects": [self.project],
            "projects_with_user_data": [],
        }
        html = render_to_string("projects/project_section.html", {**context, "is_owner": False})
        self.assertIn("CTF Project", html)
        self.assertNotIn("js-edit-project", html)
        self.assertNotIn("js-delete-project", html)
        self.assertNotIn(reverse("projects:review_project_submissions", args=[self.project.id]), html)

        html = render_to_string("projects/project_section.html", {**context, "is_owner": True})
        self.assertIn("js-edit-project", html)
        self.assertIn(reverse("projects:review_project_submissions", args=[self.project.id]), html)
