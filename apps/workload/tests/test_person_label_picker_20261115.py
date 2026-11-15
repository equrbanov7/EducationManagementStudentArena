"""Dərs yükü müəllim seçicisi «Soyad Ad Ata adı» göstərir və ata adı ilə tapır (sahib 2026-11-15)."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import UserProfile
from core.constants import RoleScopeType
from core.rls import bypass_rls

from .factories import TEACHER_PERMS, activate_member, make_org, make_structure

User = get_user_model()


class WorkloadTeacherPickerLabelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("picker-label")
            cls.stack = make_structure(cls.org, code="PLBL")
            cls.head = User.objects.create_user("plbl-head", password="pw")
            activate_member(
                cls.org,
                cls.head,
                "chair_head",
                permissions=["workload.view", "workload.manage", "workload.distribute"],
                scope_type=RoleScopeType.UNIT,
                scope_unit=cls.stack["chair"],
                level=70,
            )
            cls.teacher = User.objects.create_user("aynur.m", first_name="Aynur", last_name="Məmmədova", password="pw")
            profile, _ = UserProfile.objects.get_or_create(user=cls.teacher)
            profile.patronymic = "Vüqar"
            profile.save(update_fields=["patronymic"])
            activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=cls.stack["chair"])
            cls.twin = User.objects.create_user("aynur.m2", first_name="Aynur", last_name="Məmmədova", password="pw")
            activate_member(cls.org, cls.twin, "teacher", permissions=TEACHER_PERMS, scope_unit=cls.stack["chair"])

    def _client(self):
        client = Client()
        client.force_login(self.head)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_pool_labels_surname_first_with_patronymic(self):
        response = self._client().get(reverse("workload:teachers"), {"chair": str(self.stack["chair"].pk)})

        self.assertEqual(response.status_code, 200)
        names = {row["username"]: row["full_name"] for row in response.json()["results"]}
        self.assertEqual(names["aynur.m"], "Məmmədova Aynur Vüqar")
        self.assertEqual(names["aynur.m2"], "Məmmədova Aynur")

    def test_search_by_patronymic(self):
        response = self._client().get(
            reverse("workload:teachers"), {"chair": str(self.stack["chair"].pk), "q": "Vüqar"}
        )

        self.assertEqual([row["username"] for row in response.json()["results"]], ["aynur.m"])
