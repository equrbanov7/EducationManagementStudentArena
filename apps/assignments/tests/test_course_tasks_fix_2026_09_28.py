"""Kurs tapşırıqları düzəlişi (2026-09-28) — sərbəst işlər.

* redaktə GET `group_excluded_student_ids` qaytarır (qismən seçim genişlənmir);
* redaktə tarixi yerli vaxtla qaytarılır (toxunulmamış saxlama tarixi sürüşdürmür);
* `students[]` yalnız kursun tələbə üzvlərini qəbul edir;
* `search_groups` 10 qrupla məhdudlaşmır;
* tələbə dashboard-u qaralama/arxiv tapşırığı göstərmir, başlamamışa «göndər» vermir;
* bölmədə sahib olmayan müəllimə ölü düymələr göstərilmir.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.assignments.course_dashboard import build_course_dashboard_context
from apps.assignments.models import Assignment
from apps.assignments.tests.test_views import _assign_user_to_org, _login_with_org
from apps.courses.models import Course, CourseMembership
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()
_PASSWORD = "StrongPass123!"


class AssignmentCourseTasksFixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ctf_a_owner", "ctf_a_owner@example.com", _PASSWORD)
        cls.organization = Organization.objects.create(
            name="CTF A Org", org_type=OrganizationType.SCHOOL, owner=cls.owner, status="active", is_active=True
        )
        _assign_user_to_org(cls.owner, cls.organization, ProfileRole.TEACHER)
        cls.course = Course.objects.create(owner=cls.owner, title="CTF A Course", status="published")
        cls.s1, cls.s2, cls.s3 = (
            User.objects.create_user(f"ctf_a_s{i}", f"ctf_a_s{i}@example.com", _PASSWORD, first_name=f"S{i}")
            for i in (1, 2, 3)
        )
        for student in (cls.s1, cls.s2, cls.s3):
            _assign_user_to_org(student, cls.organization, ProfileRole.STUDENT)
            CourseMembership.objects.create(course=cls.course, user=student, role="student", group_name="G1")
        # Kursda olmayan tələbə və kursun müəllim üzvü — `students[]`-də qəbul olunmamalıdır.
        cls.outsider = User.objects.create_user("ctf_a_out", "ctf_a_out@example.com", _PASSWORD)
        _assign_user_to_org(cls.outsider, cls.organization, ProfileRole.STUDENT)
        cls.co_teacher = User.objects.create_user("ctf_a_t2", "ctf_a_t2@example.com", _PASSWORD)
        _assign_user_to_org(cls.co_teacher, cls.organization, ProfileRole.TEACHER)
        CourseMembership.objects.create(course=cls.course, user=cls.co_teacher, role="teacher")

    def setUp(self):
        self.client = Client()
        _login_with_org(self.client, self.owner, self.organization)
        now = timezone.now().replace(second=0, microsecond=0)
        self.assignment = Assignment.objects.create(
            course=self.course,
            title="CTF Assignment",
            start_date=now - timedelta(days=1),
            due_date=now + timedelta(days=3),
            status="active",
            max_score=50,
        )
        self.assignment.assigned_students.set([self.s1])

    def _edit_payload(self, data, **overrides):
        payload = {
            "title": data["title"],
            "description": data["description"],
            "start_date": data["start_date"],
            "deadline": data["deadline"],
            "max_attempts": data["max_attempts"],
            "status": data["status"],
            "group_names[]": data["group_names"],
            "students[]": [str(sid) for sid in data["student_ids"]],
        }
        payload.update(overrides)
        return payload

    def test_edit_get_marks_unassigned_group_members_as_excluded(self):
        response = self.client.get(reverse("assignments:edit_assignment", args=[self.assignment.id]))
        data = response.json()["data"]
        self.assertEqual(data["group_names"], ["G1"])
        self.assertEqual(data["student_ids"], [self.s1.id])
        self.assertEqual(sorted(data["group_excluded_student_ids"]), sorted([self.s2.id, self.s3.id]))

    def test_untouched_edit_round_trip_keeps_targets_dates_and_score(self):
        url = reverse("assignments:edit_assignment", args=[self.assignment.id])
        data = self.client.get(url).json()["data"]
        # Tarix yerli vaxtla (Asia/Baku) gəlir — UTC strftime deyil.
        self.assertEqual(data["start_date"], timezone.localtime(self.assignment.start_date).strftime("%Y-%m-%dT%H:%M"))
        before_start, before_due = self.assignment.start_date, self.assignment.due_date

        response = self.client.post(url, self._edit_payload(data))
        self.assertTrue(response.json()["success"], response.content[:300])

        self.assignment.refresh_from_db()
        self.assertEqual(list(self.assignment.assigned_students.values_list("id", flat=True)), [self.s1.id])
        self.assertEqual(self.assignment.start_date, before_start)
        self.assertEqual(self.assignment.due_date, before_due)
        self.assertEqual(self.assignment.max_score, 50)  # modalda sahə yoxdur — 100-ə sıfırlanmır

    def test_create_and_edit_accept_only_course_students(self):
        response = self.client.post(
            reverse("assignments:create_assignment", args=[self.course.id]),
            {
                "title": "Foreign ids",
                "start_date": "2026-10-01T10:00",
                "deadline": "2026-10-05T10:00",
                "status": "active",
                "students[]": [str(self.s2.id), str(self.outsider.id), str(self.co_teacher.id), "abc"],
            },
        )
        self.assertTrue(response.json()["success"], response.content[:300])
        created = Assignment.objects.get(id=response.json()["assignment_id"])
        self.assertEqual(list(created.assigned_students.values_list("id", flat=True)), [self.s2.id])

        url = reverse("assignments:edit_assignment", args=[self.assignment.id])
        data = self.client.get(url).json()["data"]
        self.client.post(url, self._edit_payload(data, **{"students[]": [str(self.s3.id), str(self.outsider.id)]}))
        self.assertEqual(list(self.assignment.assigned_students.values_list("id", flat=True)), [self.s3.id])

    def test_invalid_status_is_not_stored(self):
        url = reverse("assignments:edit_assignment", args=[self.assignment.id])
        data = self.client.get(url).json()["data"]
        self.client.post(url, self._edit_payload(data, status="hacked"))
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, "active")

    def test_search_groups_returns_all_course_groups(self):
        for index in range(12):
            user = User.objects.create_user(f"ctf_a_g{index}", f"ctf_a_g{index}@example.com", _PASSWORD)
            CourseMembership.objects.create(course=self.course, user=user, role="student", group_name=f"Q{index:02d}")
        response = self.client.get(reverse("assignments:search_groups"), {"course_id": self.course.id})
        names = [row["text"] for row in response.json()["results"]]
        self.assertEqual(len(names), 13)
        self.assertEqual(names, sorted(names))

    def test_remove_student_message_is_not_hardcoded_azerbaijani(self):
        response = self.client.post(
            reverse("assignments:remove_student_from_assignment", args=[self.assignment.id]),
            {"student_id": str(self.s1.id)},
        )
        body = response.json()
        self.assertTrue(body["success"])
        self.assertNotIn("tapşırıqdan çıxarıldı", body["message"])
        self.assertIn(self.s1.get_full_name() or self.s1.username, body["message"])


class AssignmentStudentVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ctf_v_owner", "ctf_v_owner@example.com", _PASSWORD)
        cls.organization = Organization.objects.create(
            name="CTF V Org", org_type=OrganizationType.SCHOOL, owner=cls.owner, status="active", is_active=True
        )
        _assign_user_to_org(cls.owner, cls.organization, ProfileRole.TEACHER)
        cls.student = User.objects.create_user("ctf_v_s", "ctf_v_s@example.com", _PASSWORD)
        _assign_user_to_org(cls.student, cls.organization, ProfileRole.STUDENT)
        cls.course = Course.objects.create(owner=cls.owner, title="CTF V Course", status="published")
        cls.membership = CourseMembership.objects.create(course=cls.course, user=cls.student, role="student")
        now = timezone.now()
        cls.by_status = {}
        for status in ("draft", "active", "inactive", "archived"):
            assignment = Assignment.objects.create(
                course=cls.course,
                title=f"CTF {status}",
                start_date=now - timedelta(days=1),
                due_date=now + timedelta(days=2),
                status=status,
            )
            assignment.assigned_students.add(cls.student)
            cls.by_status[status] = assignment
        cls.future = Assignment.objects.create(
            course=cls.course,
            title="CTF future",
            start_date=now + timedelta(days=1),
            due_date=now + timedelta(days=5),
            status="active",
        )
        cls.future.assigned_students.add(cls.student)

    def _student_context(self):
        return build_course_dashboard_context(
            course=self.course, user=self.student, membership=self.membership, can_manage=False, is_student=True
        )

    def test_student_dashboard_hides_draft_inactive_and_archived(self):
        titles = {item["assignment"].title for item in self._student_context()["assignments_with_user_data"]}
        self.assertEqual(titles, {"CTF active", "CTF future"})

    def test_not_started_assignment_cannot_be_submitted_from_dashboard(self):
        items = {item["assignment"].id: item for item in self._student_context()["assignments_with_user_data"]}
        self.assertTrue(items[self.by_status["active"].id]["can_submit"])
        self.assertFalse(items[self.future.id]["can_submit"])
        self.assertFalse(items[self.future.id]["has_started"])

    def test_student_cannot_open_draft_or_archived_detail(self):
        client = Client()
        _login_with_org(client, self.student, self.organization)
        for status in ("draft", "archived"):
            with self.subTest(status=status):
                response = client.get(reverse("assignments:assignment_detail", args=[self.by_status[status].id]))
                self.assertEqual(response.status_code, 302)
        response = client.get(reverse("assignments:assignment_detail", args=[self.by_status["active"].id]))
        self.assertEqual(response.status_code, 200)


class AssignmentSectionOwnerControlsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ctf_s_owner", "ctf_s_owner@example.com", _PASSWORD)
        cls.teacher = User.objects.create_user("ctf_s_teacher", "ctf_s_teacher@example.com", _PASSWORD)
        organization = Organization.objects.create(
            name="CTF S Org", org_type=OrganizationType.SCHOOL, owner=cls.owner, status="active", is_active=True
        )
        _assign_user_to_org(cls.owner, organization, ProfileRole.TEACHER)
        cls.course = Course.objects.create(owner=cls.owner, title="CTF S Course", status="published")
        cls.assignment = Assignment.objects.create(
            course=cls.course,
            title="CTF Section",
            start_date=timezone.now(),
            due_date=timezone.now() + timedelta(days=1),
            status="active",
        )

    def _render(self, user, *, is_owner):
        request = RequestFactory().get("/courses/1/")
        request.user = user
        return render_to_string(
            "assignments/assignment_section.html",
            {
                "request": request,
                "is_owner": is_owner,
                "is_teacher": True,
                "is_student": False,
                "assignments": [self.assignment],
                "assignments_with_user_data": [],
            },
        )

    def test_non_owner_teacher_sees_no_dead_buttons(self):
        html = self._render(self.teacher, is_owner=False)
        self.assertIn("CTF Section", html)
        self.assertNotIn("js-edit-assignment", html)
        self.assertNotIn("js-delete-assignment", html)
        self.assertNotIn(reverse("assignments:review_assignment_submissions", args=[self.assignment.id]), html)
        self.assertNotIn('data-bs-target="#addAssignmentModal"', html)

    def test_owner_sees_management_buttons(self):
        html = self._render(self.owner, is_owner=True)
        self.assertIn("js-edit-assignment", html)
        self.assertIn("js-delete-assignment", html)
        self.assertIn('data-bs-target="#addAssignmentModal"', html)
