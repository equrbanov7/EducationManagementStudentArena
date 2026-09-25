"""Kabinet axtarışları — az/ing hərflərinə və ayırıcılara dözümlü (sahib 2026-09-26).

Sahib: «qruplar və bütün search yerlərində az dili hərfləri ilə yazmağı nəzərə al,
en dilə olan nəticə gəlsin; qrup nömrəsi «234 K ing»dir, «234king» və s.
kombinasiyada da işləsin». Yoxlanılır: «Qruplar» (müəllim qrupları) bölməsi,
imtahan şansı tələbə axtarışı, view-as təşkilat axtarışı, rol təyinatı
(təşkilatsız istifadəçilər), sual bankı, imtahan zalları.
"""

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.views.profile._sections.exam_chance import build_exam_chance_section
from apps.accounts.views.profile._sections.exam_rooms import build_exam_rooms_section
from apps.accounts.views.profile._sections.groups import build_groups_context
from apps.accounts.views.profile._sections.question_bank import _apply_filters
from apps.accounts.views.profile._sections.role_assignment import _unassigned_queryset
from apps.exams.models import ExamRoom, QuestionBank, StudentGroup
from apps.exams.tests.test_w5_unit_leftovers import _RegistryFixture
from apps.organizations.models import Organization
from core.constants import OrganizationType
from core.search_text import tolerant_match

from .test_view_as import PASSWORD, ViewAsTestBase

User = get_user_model()

GROUP_QUERIES = ("234k", "234king", "234 K ing", "234K ING", "234-k-ing", "234k ing", "234 kİng")


class GroupsSectionTolerantSearchTest(ViewAsTestBase):
    def setUp(self):
        super().setUp()
        self.aliyev = User.objects.create_user(
            "s1.aliyev", "s1a@example.com", PASSWORD, first_name="Şahzad", last_name="Əliyev"
        )
        self.other = User.objects.create_user(
            "s1.other", "s1o@example.com", PASSWORD, first_name="Nigar", last_name="Quliyeva"
        )
        self.group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="234 K ing")
        self.group.students.add(self.aliyev, self.other)
        self.decoy = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="235 biz")
        self.decoy.students.add(self.other)

    def _context(self, **params):
        request = RequestFactory().get("/", params)
        request.user = self.admin
        return build_groups_context(
            request,
            profile=self.admin.profile,
            capabilities={"is_superadmin": False, "can_manage_org": True},
            active_organization=self.org,
            teacher_groups_search_query=params.get("group_q", ""),
            group_students_search_query=params.get("student_q", ""),
        )

    def test_group_name_found_by_compact_variants(self):
        for query in GROUP_QUERIES:
            with self.subTest(query=query):
                names = [group.name for group in self._context(group_q=query)["teacher_groups"]]
                self.assertEqual(names, ["234 K ing"])

    def test_group_found_by_student_name_without_az_letters(self):
        for query in ("Aliyev", "Eliyev", "Sahzad", "Shahzad", "shahzad aliyev"):
            with self.subTest(query=query):
                names = [group.name for group in self._context(group_q=query)["teacher_groups"]]
                self.assertEqual(names, ["234 K ing"])

    def test_blank_query_keeps_all_groups(self):
        context = self._context(group_q="")
        self.assertEqual(context["teacher_groups_filtered_count"], 2)

    def test_group_students_search_tolerates_az_letters(self):
        for query in ("Sahzad", "Shahzad", "ALIYEV", "Şahzad Əliyev"):
            with self.subTest(query=query):
                context = self._context(group=str(self.group.pk), student_q=query)
                usernames = [user.username for user in context["selected_group_students_page"].object_list]
                self.assertEqual(usernames, ["s1.aliyev"])


class ExamChanceTolerantSearchTest(_RegistryFixture):
    def _section(self, **params):
        request = RequestFactory().get("/", params)
        request.user = self.center
        section = {}
        build_exam_chance_section(
            request,
            section,
            active_organization=self.org,
            allowed_sections={"exam-chance"},
            active_section="exam-chance",
        )
        return section

    def test_registry_group_name_compact_variants(self):
        for query in ("634ing", "634 İNG", "634-ing", "634"):
            with self.subTest(query=query):
                results = self._section(chance_student_q=query)["student_results"]
                self.assertEqual({user.username for user in results}, {"w5l_student", "w5l_student2"})

    def test_student_name_and_cohort_tolerant(self):
        self.assertEqual(
            [user.username for user in self._section(chance_student_q="Mervi")["student_results"]], ["w5l_student"]
        )
        self.assertEqual(
            [user.username for user in self._section(chance_student_q="kohorta")["student_results"]],
            ["w5l_outsider"],
        )
        # Tokenlər VƏ: ad + qrup eyni tələbədə olmalıdır.
        self.assertEqual(
            [user.username for user in self._section(chance_student_q="Aysel 634ing")["student_results"]],
            ["w5l_student2"],
        )
        self.assertEqual(self._section(chance_student_q="Aysel 701biz")["student_results"], [])


class ViewAsOrgSearchTolerantTest(ViewAsTestBase):
    def test_org_search_folds_letters_and_compacts_slug(self):
        Organization.objects.create(
            name="Şəki Dövlət Universiteti",
            slug="seki-du",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.client.force_login(self.superadmin)
        for query in ("Seki", "seki dovlet", "SHEKI", "sekidu"):
            with self.subTest(query=query):
                response = self.client.get(reverse("accounts:view_as_search"), {"type": "orgs", "q": query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["name"] for row in response.json()["results"]], ["Şəki Dövlət Universiteti"])


class RoleAssignmentUnassignedSearchTest(ViewAsTestBase):
    def test_unassigned_users_found_without_az_letters(self):
        User.objects.create_user("s1.loose", "loose@example.com", PASSWORD, first_name="Şahzad", last_name="Əliyev")
        request = RequestFactory().get("/")
        request.user = self.superadmin
        for query in ("Shahzad", "Sahzad Aliyev", "eliyev"):
            with self.subTest(query=query):
                usernames = list(
                    _unassigned_queryset(request, self.org, is_superadmin=True, search=query).values_list(
                        "user__username", flat=True
                    )
                )
                self.assertEqual(usernames, ["s1.loose"])


class QuestionBankAndRoomsSearchTest(ViewAsTestBase):
    def test_question_bank_subject_without_az_letters(self):
        QuestionBank.objects.create(
            name="Final bankı", subject="Verilənlər bazası", organization=self.org, created_by=self.admin
        )
        QuestionBank.objects.create(name="Riyaziyyat", organization=self.org, created_by=self.admin)
        params = {"search": "Verilenler", "kind": "", "lang": "", "format": ""}
        names = list(
            _apply_filters(QuestionBank.objects.filter(organization=self.org), params).values_list("name", flat=True)
        )
        self.assertEqual(names, ["Final bankı"])

    def test_exam_rooms_code_compact(self):
        ExamRoom.objects.create(
            organization=self.org, name="Zal 2-14", code="A-214", capacity=20, created_by=self.admin
        )
        ExamRoom.objects.create(organization=self.org, name="Zal B", code="ZB", capacity=20, created_by=self.admin)
        for query in ("a214", "zal214", "Zal 2 14"):
            with self.subTest(query=query):
                request = RequestFactory().get("/", {"xr_q": query})
                request.user = self.admin
                section = {}
                build_exam_rooms_section(
                    request,
                    section,
                    is_superadmin=False,
                    active_organization=self.org,
                    allowed_sections={"superadmin-exam-rooms"},
                    active_section="superadmin-exam-rooms",
                )
                self.assertEqual([room.name for room in section["rooms"]], ["Zal 2-14"])


class InMemoryListSearchTest(ViewAsTestBase):
    def test_tolerant_match_used_by_dashboard_lists(self):
        self.assertTrue(tolerant_match("Verilenler", "Verilənlər bazası", "Final"))
        self.assertTrue(tolerant_match("", "anything"))
        self.assertFalse(tolerant_match("Verilenler final", "Verilənlər bazası"))
