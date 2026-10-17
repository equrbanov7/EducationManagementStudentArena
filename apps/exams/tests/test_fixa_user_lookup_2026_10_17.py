"""SEC-2 Low #2 (2026-10-17) — `GET /exams/lookups/users/` istifadəçi kataloqunu sadalamır.

Əvvəl istənilən müəllim `?q=a` (və ya boş sorğu) ilə bütün tələbələrin adını və ardıcıl id-sini səhifə-səhifə
(50-lik) çəkə bilirdi. İndi: sorğu ≥ 2 simvol olmalıdır (JS `EMSSearchInput` onsuz da belədir); qısa sorğuda
yalnız SEÇİLMİŞ qrupların üzvləri qayıdır (istisna etmək üçün); səhifə həddi 20; təşkilatdan kənar tələbə yoxdur.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import StudentGroup
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.exams.views.teacher.exams.lookups import USER_SEARCH_MAX_OFFSET, USER_SEARCH_MIN_QUERY, USER_SEARCH_PAGE_MAX
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


def _login(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


class UserLookupScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("fxl_owner", "fxl_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="FXL Uni", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active", is_active=True
        )
        cls.other_owner = User.objects.create_user("fxl_owner2", "fxl_owner2@test.az", PASSWORD)
        cls.other_org = Organization.objects.create(
            name="FXL Other",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.other_owner,
            status="active",
            is_active=True,
        )
        cls.teacher = User.objects.create_user("fxl_teacher", "fxl_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.member = User.objects.create_user("fxl_member", "fxl_member@test.az", PASSWORD, first_name="Mələk")
        _assign_user_to_org(cls.member, cls.org, ProfileRole.STUDENT, "student")
        cls.students = []
        for index in range(USER_SEARCH_PAGE_MAX + 5):
            student = User.objects.create_user(f"fxl_s{index:02d}", f"fxl_s{index:02d}@test.az", PASSWORD)
            _assign_user_to_org(student, cls.org, ProfileRole.STUDENT, "student")
            cls.students.append(student)
        cls.outsider = User.objects.create_user("fxl_outsider", "fxl_outsider@test.az", PASSWORD)
        _assign_user_to_org(cls.outsider, cls.other_org, ProfileRole.STUDENT, "student")
        cls.group = StudentGroup.objects.create(teacher=cls.teacher, organization=cls.org, name="FXL G")
        cls.group.students.add(cls.member)

    def search(self, **params):
        response = _login(self.teacher, self.org).get(reverse("exams:user_search"), params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_empty_or_one_char_query_returns_no_directory(self):
        for query in ("", "f", " a "):
            with self.subTest(query=query):
                payload = self.search(q=query, limit=50)
                self.assertEqual(payload["results"], [])
                self.assertFalse(payload["has_more"])

    def test_short_query_with_selected_group_returns_members_only(self):
        payload = self.search(groups=str(self.group.pk), limit=50)
        self.assertEqual([row["id"] for row in payload["results"]], [str(self.member.pk)])
        self.assertTrue(payload["results"][0]["group_member"])

    def test_two_char_query_searches_org_students_only(self):
        payload = self.search(q="fxl_outsider")
        self.assertEqual(payload["results"], [])
        payload = self.search(q="fxl_s0", limit=50)
        ids = {row["id"] for row in payload["results"]}
        self.assertIn(str(self.students[0].pk), ids)
        self.assertNotIn(str(self.teacher.pk), ids)

    def test_page_size_is_capped(self):
        payload = self.search(q="fxl", limit=50)
        self.assertEqual(len(payload["results"]), USER_SEARCH_PAGE_MAX)
        self.assertTrue(payload["has_more"])

    def test_offset_is_capped(self):
        """Baxış 2026-10-17: eyni sorğu ilə kataloqu səhifə-səhifə çəkmək olmasın."""
        payload = self.search(q="fxl", offset=USER_SEARCH_MAX_OFFSET, limit=10)
        self.assertEqual(payload["results"], [])
        self.assertFalse(payload["has_more"])
        with mock.patch("apps.exams.views.teacher.exams.lookups.USER_SEARCH_MAX_OFFSET", 22):
            payload = self.search(q="fxl", offset=20, limit=10)
        self.assertEqual(len(payload["results"]), 2)
        self.assertFalse(payload["has_more"])

    def test_response_reports_min_query_for_js_hint(self):
        self.assertEqual(self.search(q="")["min_query"], USER_SEARCH_MIN_QUERY)
        self.assertEqual(self.search(q="fxl")["min_query"], USER_SEARCH_MIN_QUERY)

    def test_student_is_forbidden(self):
        response = _login(self.member, self.org).get(reverse("exams:user_search"), {"q": "fxl"})
        self.assertEqual(response.status_code, 403)
