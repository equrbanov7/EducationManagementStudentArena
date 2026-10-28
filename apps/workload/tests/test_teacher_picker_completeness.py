"""MR-000048: lokal axtarışlı bölgü modalında kafedranın ilk 50-dən sonrakı müəllimi itmir."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import Membership
from apps.workload.services import teacher_pool
from core.constants import RoleScopeType
from core.rls import bypass_rls

from .factories import TEACHER_PERMS, activate_member, make_org, make_structure

User = get_user_model()


class TeacherPickerCompletenessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("picker-full")
            cls.stack = make_structure(cls.org, code="PICK")
            cls.head = User.objects.create_user("picker-head", password="pw")
            activate_member(
                cls.org,
                cls.head,
                "chair_head",
                permissions=["workload.view", "workload.manage", "workload.distribute"],
                scope_type=RoleScopeType.UNIT,
                scope_unit=cls.stack["chair"],
                level=70,
            )
            cls.target = User.objects.create_user(
                "chichek.mustafayeva", first_name="Çiçək", last_name="Mustafayeva", password="pw"
            )
            cls.role = activate_member(
                cls.org, cls.target, "teacher", permissions=TEACHER_PERMS, scope_unit=cls.stack["chair"]
            )
            users = User.objects.bulk_create(
                [User(username=f"picker-{index}", first_name=f"A{index:03}") for index in range(60)]
            )
            Membership.objects.bulk_create(
                [
                    Membership(
                        organization=cls.org,
                        user=user,
                        role=cls.role,
                        scope_unit=cls.stack["chair"],
                        is_active=True,
                    )
                    for user in users
                ]
            )
            cls.other_org = make_org("picker-other")
            cls.other_stack = make_structure(cls.other_org, code="OTHER")
            cls.other = User.objects.create_user("picker-foreign", password="pw")
            activate_member(
                cls.other_org,
                cls.other,
                "teacher",
                permissions=TEACHER_PERMS,
                scope_unit=cls.other_stack["chair"],
            )

    def _client(self):
        client = Client()
        client.force_login(self.head)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_modal_api_contains_late_own_teacher_for_local_search(self):
        response = self._client().get(
            reverse("workload:teachers"), {"chair": str(self.stack["chair"].pk), "outside": "1"}
        )
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.json()["results"]}
        self.assertEqual(len(ids), 61)
        self.assertIn(str(self.target.pk), ids)
        self.assertNotIn(str(self.other.pk), ids)

    def test_explicit_page_limit_and_search_still_work(self):
        limited = teacher_pool(self.org, self.stack["chair"], limit=50)
        self.assertEqual(len(limited), 50)
        self.assertNotIn(str(self.target.pk), {row["id"] for row in limited})
        found = teacher_pool(self.org, self.stack["chair"], search="Cicek Mustafayeva", limit=50)
        self.assertEqual([row["id"] for row in found], [str(self.target.pk)])

    def test_api_still_denies_chair_outside_actor_scope(self):
        response = self._client().get(
            reverse("workload:teachers"), {"chair": str(self.other_stack["chair"].pk), "outside": "1"}
        )
        self.assertEqual(response.status_code, 403)
