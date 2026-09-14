"""Kurs üzvləri səhifəsi + `available_students` endpoint-i — audit 2026-09-10 P1-4.

Nə səhv idi (ölçülmüş, düzəlişdən ƏVVƏL):
- `CourseMembersView` tenant-ın BÜTÜN tələbə istifadəçilərini (`all_users`,
  real bazada auth_user = 8 443 sətir) səhifələməsiz kontekstə verirdi və modal
  hər biri üçün checkbox sətri render edirdi — 40 namizədin 40-ı HTML-də idi.
- `course.memberships.all()` `select_related("user")`-siz idi → üzvlük başına
  bir `SELECT auth_user` (1 üzv + 1 namizəd = 33 sorğu, 8 üzv + 40 namizəd = 40).

Bu testlər düzəlişi qoruyur: səhifənin sorğu sayı üzv/namizəd sayından asılı
deyil, namizədlər HTML-ə düşmür, modal JSON endpoint-i isə eyni əhatə ilə
(eyni təşkilat, yalnız tələbə, üzv olmayan) axtarışlı və 50 tavanlı səhifələyir.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.courses.views.teacher.membership import (
    AVAILABLE_STUDENTS_DEFAULT_LIMIT,
    AVAILABLE_STUDENTS_MAX_LIMIT,
)
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def _assign_user_to_org(user, organization, profile_role):
    role_name = {ProfileRole.TEACHER: "teacher", ProfileRole.STUDENT: "student"}.get(profile_role, "member")
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


class _MembersFixtureMixin:
    """Sahib müəllim + təşkilat + kurs; tələbə fabrikası."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="p14_owner", email="p14_owner@example.com", password="StrongPass123!"
        )
        self.org = Organization.objects.create(
            name="P14 Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.owner, self.org, ProfileRole.TEACHER)
        self.course = Course.objects.create(
            owner=self.owner, title="P14 Course", status="published", organization=self.org
        )
        self._login(self.owner)

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _student(self, index, *, organization=None, member=False, first_name=None, last_name=None):
        user = User.objects.create_user(
            username=f"p14_st_{index:03d}",
            email=f"p14_st_{index}@example.com",
            password="StrongPass123!",
            first_name=first_name if first_name is not None else f"Ad{index}",
            last_name=last_name if last_name is not None else f"Soyad{index}",
        )
        _assign_user_to_org(user, organization or self.org, ProfileRole.STUDENT)
        if member:
            CourseMembership.objects.create(course=self.course, user=user, role="student", group_name=f"G{index % 2}")
        return user


class MembersPageQueryBudgetTest(_MembersFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("courses:course_members", kwargs={"course_id": self.course.id})

    def test_query_count_independent_of_member_and_candidate_count(self):
        members = [self._student(0, member=True)]
        candidates = [self._student(100)]

        self.client.get(self.url)  # isti tur — sessiya/auth keşi sabitləşsin
        with CaptureQueriesContext(connection) as small:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        members += [self._student(i, member=True) for i in range(1, 8)]
        candidates += [self._student(i) for i in range(101, 140)]
        with CaptureQueriesContext(connection) as large:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            len(small.captured_queries),
            len(large.captured_queries),
            "Üzvlər səhifəsinin sorğu sayı üzv/namizəd sayı ilə artmamalıdır (P1-4 N+1 / 8k siyahı)",
        )

        html = response.content.decode("utf-8")
        # Render olunan məlumat dəyişməyib: hər üzvün adı və username-i səhifədədir.
        for user in members:
            self.assertIn(user.get_full_name(), html)
            self.assertIn(f"@{user.username}", html)
        # Namizədlər artıq HTML-ə düşmür — modal onları JSON endpoint-indən çəkir.
        for user in candidates:
            self.assertNotIn(f'id="user_{user.id}"', html)
            self.assertNotIn(user.username, html)
        available_url = reverse("courses:available_students", kwargs={"course_id": self.course.id})
        self.assertIn(f'data-available-url="{available_url}"', html)
        self.assertIn('courses/js/_member_form_modal.js?v=20260912-1" defer', html)
        self.assertIn('id="student_selected_chips"', html)

    def test_members_page_has_no_per_member_user_select(self):
        for i in range(6):
            self._student(i, member=True)
        self.client.get(self.url)
        with CaptureQueriesContext(connection) as captured:
            self.client.get(self.url)
        user_selects = [q["sql"] for q in captured.captured_queries if q["sql"].startswith('SELECT "auth_user"."id"')]
        # Yalnız auth (request.user) üçün — üzvlük başına ayrıca SELECT olmamalıdır.
        self.assertLessEqual(len(user_selects), 1, user_selects)


class AvailableStudentsEndpointTest(_MembersFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("courses:available_students", kwargs={"course_id": self.course.id})

    def _get(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_response_shape(self):
        self._student(1, first_name="Aysel", last_name="Məmmədova")
        payload = self._get()
        self.assertEqual(set(payload.keys()), {"success", "users", "q", "page", "limit", "has_more"}, payload.keys())
        self.assertIs(payload["success"], True)
        self.assertEqual(payload["q"], "")
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["limit"], AVAILABLE_STUDENTS_DEFAULT_LIMIT)
        self.assertIs(payload["has_more"], False)
        self.assertEqual(
            payload["users"],
            [
                {
                    "id": User.objects.get(username="p14_st_001").id,
                    "username": "p14_st_001",
                    "full_name": "Aysel Məmmədova",
                }
            ],
        )

    def test_scope_same_org_students_not_members_only(self):
        visible = self._student(1)
        self._student(2, member=True)  # artıq üzvdür
        other_org = Organization.objects.create(
            name="P14 Other Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self._student(3, organization=other_org)  # başqa tenant
        teacher = User.objects.create_user(
            username="p14_teacher_x", email="p14_teacher_x@example.com", password="StrongPass123!"
        )
        _assign_user_to_org(teacher, self.org, ProfileRole.TEACHER)  # tələbə deyil

        payload = self._get()
        self.assertEqual([u["id"] for u in payload["users"]], [visible.id])

    def test_q_filters_username_first_and_last_name_multi_term(self):
        aysel = self._student(1, first_name="Aysel", last_name="Məmmədova")
        rauf = self._student(2, first_name="Rauf", last_name="Əliyev")
        self._student(3, first_name="Nigar", last_name="Həsənli")

        self.assertEqual([u["id"] for u in self._get(q="st_002")["users"]], [rauf.id])
        self.assertEqual([u["id"] for u in self._get(q="aysel")["users"]], [aysel.id])
        self.assertEqual([u["id"] for u in self._get(q="Əliyev")["users"]], [rauf.id])
        self.assertEqual([u["id"] for u in self._get(q="Aysel Məmmədova")["users"]], [aysel.id])
        self.assertEqual(self._get(q="Aysel Əliyev")["users"], [])
        self.assertEqual(self._get(q="yoxdur")["users"], [])
        self.assertEqual(self._get(q="  aysel  ")["q"], "aysel")

    def test_limit_is_capped_and_pagination_works(self):
        total = AVAILABLE_STUDENTS_MAX_LIMIT + 5
        for i in range(total):
            self._student(i)

        first = self._get(limit=500)
        self.assertEqual(first["limit"], AVAILABLE_STUDENTS_MAX_LIMIT)
        self.assertEqual(len(first["users"]), AVAILABLE_STUDENTS_MAX_LIMIT)
        self.assertIs(first["has_more"], True)
        self.assertEqual(first["page"], 1)

        second = self._get(limit=500, page=2)
        self.assertEqual(second["page"], 2)
        self.assertEqual(len(second["users"]), 5)
        self.assertIs(second["has_more"], False)

        # Səhifələr kəsişmir və birlikdə hamısını əhatə edir (username sırası).
        seen = [u["username"] for u in first["users"]] + [u["username"] for u in second["users"]]
        self.assertEqual(seen, sorted(seen))
        self.assertEqual(len(set(seen)), total)

        default = self._get()
        self.assertEqual(len(default["users"]), AVAILABLE_STUDENTS_DEFAULT_LIMIT)
        self.assertIs(default["has_more"], True)

    def test_invalid_params_fall_back_to_defaults(self):
        self._student(1)
        payload = self._get(limit="abc", page="-3")
        self.assertEqual(payload["limit"], AVAILABLE_STUDENTS_DEFAULT_LIMIT)
        self.assertEqual(payload["page"], 1)
        self.assertEqual(len(payload["users"]), 1)
        self.assertEqual(self._get(limit="0")["limit"], 1)

    def test_query_count_independent_of_result_count(self):
        self._student(1)
        self.client.get(self.url)
        with CaptureQueriesContext(connection) as small:
            self._get()
        for i in range(2, 30):
            self._student(i)
        with CaptureQueriesContext(connection) as large:
            self._get()
        self.assertEqual(len(small.captured_queries), len(large.captured_queries))

    def test_non_owner_gets_json_403_and_anonymous_redirects(self):
        other_teacher = User.objects.create_user(
            username="p14_other_teacher", email="p14_other_teacher@example.com", password="StrongPass123!"
        )
        _assign_user_to_org(other_teacher, self.org, ProfileRole.TEACHER)
        self._login(other_teacher)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertIs(response.json()["success"], False)

        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_add_member_contract_unchanged_hidden_user_ids(self):
        """Modal gizli `user_ids` input-ları göndərir — AddMemberView eyni sahələri oxuyur."""
        first = self._student(1)
        second = self._student(2)
        response = self.client.post(
            reverse("courses:add_member", kwargs={"course_id": self.course.id}),
            {"user_ids": [str(first.id), str(second.id)], "group_name": "842A1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["success"], True)
        self.assertEqual(
            set(
                CourseMembership.objects.filter(course=self.course, group_name="842A1").values_list(
                    "user_id", flat=True
                )
            ),
            {first.id, second.id},
        )
        # Əlavə olunanlar artıq namizəd siyahısında görünmür.
        self.assertEqual(self._get()["users"], [])
