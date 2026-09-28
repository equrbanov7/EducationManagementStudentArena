"""Kurs tapşırıqları düzəlişi (2026-09-28) — laboratoriya işləri.

* qismən qrup seçimi fərdi tələbə kimi saxlanılır (bütün qrupa açılmır);
* redaktə GET `group_excluded_student_ids` qaytarır, toxunulmamış saxlama girişi dəyişmir;
* `student_ids[]` yalnız kursun tələbə üzvlərini qəbul edir;
* yaratma modalının «Status» seçimi nəzərə alınır; etibarsız status yazılmır;
* dashboard görünürlüyü `Lab.can_student_access` ilə eynidir (filtr yoxdur = bütün kurs,
  qrup müqayisəsi registrdən asılı deyil);
* qaralama lab tələbəyə birbaşa linklə açılmır;
* bölmədə yaradan olmayan müəllimə redaktə/bloklar düyməsi göstərilmir.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.labs.course_dashboard import build_course_dashboard_context
from apps.labs.models import Lab
from apps.labs.tests.test_views import _assign_user_to_org, _login_with_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()
_PASSWORD = "StrongPass123!"


class _LabFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ctf_l_owner", "ctf_l_owner@example.com", _PASSWORD)
        cls.organization = Organization.objects.create(
            name="CTF L Org", org_type=OrganizationType.SCHOOL, owner=cls.owner, status="active", is_active=True
        )
        _assign_user_to_org(cls.owner, cls.organization, ProfileRole.TEACHER)
        cls.course = Course.objects.create(owner=cls.owner, title="CTF L Course", status="published")
        cls.a1, cls.a2, cls.a3, cls.b1 = (
            User.objects.create_user(f"ctf_l_{name}", f"ctf_l_{name}@example.com", _PASSWORD)
            for name in ("a1", "a2", "a3", "b1")
        )
        cls.memberships = {}
        for student, group in ((cls.a1, "Group A"), (cls.a2, "Group A"), (cls.a3, "Group A"), (cls.b1, "Group B")):
            _assign_user_to_org(student, cls.organization, ProfileRole.STUDENT)
            cls.memberships[student.id] = CourseMembership.objects.create(
                course=cls.course, user=student, role="student", group_name=group
            )
        cls.outsider = User.objects.create_user("ctf_l_out", "ctf_l_out@example.com", _PASSWORD)
        _assign_user_to_org(cls.outsider, cls.organization, ProfileRole.STUDENT)

    def setUp(self):
        self.client = Client()
        _login_with_org(self.client, self.owner, self.organization)

    def _lab(self, **overrides):
        now = timezone.now().replace(second=0, microsecond=0)
        fields = {
            "course": self.course,
            "title": "CTF Lab",
            "start_datetime": now - timedelta(hours=1),
            "end_datetime": now + timedelta(days=2),
            "max_score": 100,
            "max_attempts": 1,
            "status": "published",
            "created_by": self.owner,
        }
        fields.update(overrides)
        return Lab.objects.create(**fields)

    def _create(self, **extra):
        payload = {
            "title": "Created Lab",
            "start_datetime": "2026-10-01T10:00",
            "end_datetime": "2026-10-05T10:00",
            "max_score": "100",
            "max_attempts": "1",
        }
        payload.update(extra)
        response = self.client.post(reverse("labs:create_lab", args=[self.course.id]), payload)
        self.assertTrue(response.json()["success"], response.content[:300])
        return Lab.objects.get(id=response.json()["lab_id"])


class LabTargetsTests(_LabFixture):
    def test_partial_group_selection_stays_partial(self):
        lab = self._create(**{"group_names[]": ["Group A"], "student_ids[]": [str(self.a1.id)]})
        self.assertEqual(lab.allowed_groups, "")
        self.assertEqual(list(lab.allowed_students.values_list("id", flat=True)), [self.a1.id])
        self.assertTrue(lab.can_student_access(self.a1))
        self.assertFalse(lab.can_student_access(self.a2))

    def test_fully_selected_group_is_kept_as_group(self):
        ids = [str(self.a1.id), str(self.a2.id), str(self.a3.id), str(self.b1.id)]
        lab = self._create(**{"group_names[]": ["Group A", "Group B"], "student_ids[]": ids[:3]})
        # Group B işarələnib, amma tələbəsi seçilməyib → tələbə seçimi olduğu üçün düşür.
        self.assertEqual(lab.allowed_groups, "Group A")
        self.assertFalse(lab.allowed_students.exists())
        self.assertFalse(lab.can_student_access(self.b1))

    def test_groups_only_and_foreign_ids(self):
        lab = self._create(**{"group_names[]": ["group b", "Nope"], "student_ids[]": [str(self.outsider.id)]})
        self.assertEqual(lab.allowed_groups, "Group B")
        self.assertFalse(lab.allowed_students.exists())

    def test_create_honours_status_select(self):
        self.assertEqual(self._create().status, "draft")
        self.assertEqual(self._create(status="published").status, "published")
        self.assertEqual(self._create(status="archived").status, "draft")

    def test_edit_get_and_untouched_round_trip(self):
        lab = self._lab(allowed_groups="Group B")
        lab.allowed_students.set([self.a1])
        url = reverse("labs:edit_lab", args=[lab.id])
        data = self.client.get(url).json()["data"]
        self.assertEqual(data["group_names"], ["Group A", "Group B"])
        self.assertEqual(data["student_ids"], [self.a1.id])
        self.assertEqual(sorted(data["group_excluded_student_ids"]), sorted([self.a2.id, self.a3.id]))
        self.assertEqual(data["start_datetime"], timezone.localtime(lab.start_datetime).strftime("%Y-%m-%dT%H:%M"))

        # Modalın toxunulmamış göndərişi: qruplar + (excluded xaric) avtomatik seçilən tələbələr.
        response = self.client.post(
            url,
            {
                "title": data["title"],
                "start_datetime": data["start_datetime"],
                "end_datetime": data["end_datetime"],
                "max_score": data["max_score"],
                "max_attempts": data["max_attempts"],
                "status": "bogus",
                "max_file_size_mb": data["max_file_size_mb"],
                "allowed_extensions": data["allowed_extensions"],
                "group_names[]": data["group_names"],
                "student_ids[]": [str(self.a1.id), str(self.b1.id)],
            },
        )
        self.assertTrue(response.json()["success"], response.content[:300])
        before_start = lab.start_datetime
        lab.refresh_from_db()
        self.assertEqual(lab.status, "published")  # etibarsız status yazılmır
        self.assertEqual(lab.start_datetime, before_start)
        self.assertEqual(lab.allowed_groups, "Group B")
        self.assertEqual(list(lab.allowed_students.values_list("id", flat=True)), [self.a1.id])
        self.assertFalse(lab.can_student_access(self.a2))


class LabVisibilityTests(_LabFixture):
    def _visible_titles(self, student):
        context = build_course_dashboard_context(
            course=self.course,
            user=student,
            membership=self.memberships[student.id],
            can_manage=False,
            is_student=True,
        )
        return {item["lab"].title for item in context["labs_with_user_data"]}

    def test_dashboard_agrees_with_can_student_access(self):
        labs = [
            self._lab(title="Whole course"),
            self._lab(title="Group a lowercase", allowed_groups="group a"),
            self._lab(title="Group B only", allowed_groups="Group B"),
            self._lab(title="Draft whole course", status="draft"),
        ]
        for student in (self.a1, self.b1):
            visible = self._visible_titles(student)
            for lab in labs:
                with self.subTest(student=student.username, lab=lab.title):
                    expected = lab.status == "published" and lab.can_student_access(student)
                    self.assertEqual(lab.title in visible, expected)
        self.assertIn("Whole course", self._visible_titles(self.a1))
        self.assertIn("Group a lowercase", self._visible_titles(self.a1))

    def test_student_cannot_open_draft_lab_detail(self):
        draft = self._lab(title="Draft", status="draft")
        client = Client()
        _login_with_org(client, self.a1, self.organization)
        response = client.get(reverse("labs:lab_detail", args=[draft.id]))
        self.assertEqual(response.status_code, 403)


class LabSectionControlsTests(_LabFixture):
    def test_non_creator_sees_answers_but_no_management_buttons(self):
        lab = self._lab(title="Section Lab")
        co_teacher = User.objects.create_user("ctf_l_t2", "ctf_l_t2@example.com", _PASSWORD)
        request = RequestFactory().get("/courses/1/")
        base = {"is_teacher": True, "is_student": False, "labs": [lab], "labs_with_user_data": []}

        request.user = co_teacher
        html = render_to_string("labs/lab_section.html", {**base, "request": request, "is_owner": False})
        self.assertIn(reverse("labs:lab_submissions", args=[lab.id]), html)
        self.assertNotIn(reverse("labs:manage_blocks", args=[lab.id]), html)
        self.assertNotIn("js-edit-lab", html)
        self.assertNotIn('data-bs-target="#addLabModal"', html)
        self.assertNotIn("lab_section.js", html)

        request.user = self.owner
        html = render_to_string("labs/lab_section.html", {**base, "request": request, "is_owner": True})
        self.assertIn(reverse("labs:manage_blocks", args=[lab.id]), html)
        self.assertIn("js-edit-lab", html)
        self.assertIn("js-delete-lab", html)
