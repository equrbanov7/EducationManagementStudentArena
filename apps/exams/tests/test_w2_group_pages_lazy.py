"""W2 2026-09-14 — perf auditi 2026-09-13 F-10: qrup tam səhifələri lazy namizədlərlə.

`/exams/groups/` (`exams:teacher_group_list`) və `exams:create_student_group`
formanı `defer_choices`-siz qururdu → təşkilatın BÜTÜN tələbə/müəllim
`<option>`-ları hər GET-də render olunurdu (klonda 2 008 ms / 2,5 MB). İndi:

* GET → forma boş widget-lə, şablonda `data-candidates-url` =
  `exams:teacher_group_candidates`; HTML ölçüsü və sorğu sayı tələbə sayından
  asılı DEYİL (2 → 150 tələbə).
* Namizəd endpoint-i əvvəlki kimi eyni widget HTML-ini qaytarır (məzmun dəyişmir).
* Bound (POST xətası) re-render-də variantlar özü render olunur, seçim qorunur,
  `data-candidates-url` boşdur (JS mövcud `<option>`-larla işləyir).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import StudentGroup
from apps.exams.tests.test_views import _assign_user_to_org, _login_with_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()
PASSWORD = "StrongPass123!"


class GroupPagesLazyCandidatesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("w2p_owner", "w2p_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="W2P University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(cls.owner, cls.org, ProfileRole.ORG_OWNER)
        cls.teacher = User.objects.create_user("w2p_teacher", "w2p_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER)
        cls.base_students = [cls._make_student(index) for index in range(2)]
        group = StudentGroup.objects.create(teacher=cls.teacher, organization=cls.org, name="W2P Group")
        group.teachers.add(cls.teacher)
        group.students.add(cls.base_students[0])
        cls.group = group

    def setUp(self):
        # Hər test öz siyahısını genişləndirir (sinif siyahısı dəyişməz qalır).
        self.students = list(self.base_students)

    @classmethod
    def _make_student(cls, index: int):
        student = User.objects.create_user(f"w2p_student_{index:03d}", f"w2p_s{index}@test.az", PASSWORD)
        _assign_user_to_org(student, cls.org, ProfileRole.STUDENT)
        return student

    def _client(self):
        client = Client()
        _login_with_org(client, self.owner, self.org)
        return client

    def _measure(self, client, url):
        client.get(url)  # isinmə (sessiya/permission keşi)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries), len(response.content), response

    def _add_students(self, count: int):
        for index in range(len(self.students), len(self.students) + count):
            self.students.append(self._make_student(index))

    def _assert_page_independent_of_student_count(self, url_name: str):
        client = self._client()
        url = reverse(url_name)
        candidates_url = reverse("exams:teacher_group_candidates")

        small_queries, small_size, small_response = self._measure(client, url)
        self.assertContains(small_response, f'data-candidates-url="{candidates_url}"')
        self.assertNotContains(small_response, "w2p_student_001")  # variant render olunmur

        self._add_students(148)  # 2 → 150 tələbə
        large_queries, large_size, large_response = self._measure(client, url)
        self.assertNotContains(large_response, "w2p_student_149")
        self.assertEqual(small_queries, large_queries, "sorğu sayı tələbə sayından asılıdır")
        # HTML ölçüsü sabitdir (148 tələbəlik `<option>` yoxdur); kiçik fərq — yalnız
        # `student_count` sayğacının rəqəm uzunluğu (`2` → `150`).
        self.assertLess(abs(large_size - small_size), 64, f"HTML ölçüsü dəyişdi: {small_size} → {large_size}")
        return large_response

    def test_group_list_page_html_and_queries_independent_of_student_count(self):
        response = self._assert_page_independent_of_student_count("exams:teacher_group_list")
        # Səhifənin funksional hissəsi qalır: qrup kartı, redaktə/silmə marşrutları.
        self.assertContains(response, "W2P Group")
        self.assertContains(response, reverse("exams:teacher_update_group", args=[0]))
        self.assertContains(response, reverse("exams:teacher_delete_group", args=[self.group.id]))
        self.assertContains(response, reverse("exams:create_student_group"))
        self.assertContains(response, "exams/js/teacher_group_list.js?v=20260914-1")

    def test_create_page_html_and_queries_independent_of_student_count(self):
        response = self._assert_page_independent_of_student_count("exams:create_student_group")
        self.assertContains(response, reverse("exams:teacher_create_group"))
        self.assertContains(response, 'id="createGroupForm"')
        self.assertContains(response, "data-csg-checklist")
        # Sayğaclar COUNT sorğusundan gəlir — 150 tələbə göstərilir.
        self.assertContains(response, "<strong>150</strong>")
        self.assertContains(response, "exams/js/create_student_group.js?v=20260914-1")

    def test_candidates_endpoint_still_returns_every_student_option(self):
        """Lazy endpoint məzmunu dəyişmir: bütün tələbə/müəllim `<option>`-ları oradadır."""
        self._add_students(3)
        client = self._client()
        response = client.get(reverse("exams:teacher_group_candidates"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for student in self.students:
            self.assertIn(f'value="{student.id}"', payload["students"])
            self.assertIn(student.username, payload["students"])
        self.assertIn(f'value="{self.teacher.id}"', payload["primary_teacher"])
        self.assertIn(f'value="{self.teacher.id}"', payload["assigned_teachers"])
        # Qrup üzvlüyü metadatası (`data-user-group-labels`) da qorunur.
        self.assertIn("W2P Group", payload["students"])

    def test_invalid_create_post_rerenders_options_with_selection(self):
        """Bound formada variantlar özü render olunur (seçim qorunur), lazy URL boşdur."""
        client = self._client()
        response = client.post(
            reverse("exams:teacher_create_group"),
            {
                "name": "",  # məcburi sahə boş → 400 re-render
                "students": [str(self.students[1].id)],
                "primary_teacher": str(self.teacher.id),
                "assigned_teachers": [str(self.teacher.id)],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'data-candidates-url=""', status_code=400)
        self.assertContains(response, f'<option value="{self.students[1].id}" selected', status_code=400)
        self.assertContains(response, "w2p_student_000", status_code=400)

    def test_teacher_without_multi_assign_gets_self_only_primary_option_lazily(self):
        """Adi müəllim: səhifə yenə lazy; endpoint yalnız özünü (seçilmiş) qaytarır."""
        client = Client()
        _login_with_org(client, self.teacher, self.org)
        # Müəllimin `group.manage` açarı default olmadığı üçün yaratma səhifəsi 403-dür —
        # siyahı səhifəsi (group.view / müəllim rolu) açılır və lazy URL daşıyır.
        response = client.get(reverse("exams:teacher_group_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-candidates-url="{reverse("exams:teacher_group_candidates")}"')
        self.assertNotContains(response, "w2p_student_001")
