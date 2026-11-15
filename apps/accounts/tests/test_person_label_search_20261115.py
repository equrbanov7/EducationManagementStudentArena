"""RİM axtarışı və parol sıfırlama axtarışı «Soyad Ad Ata adı» qaytarır (sahib 2026-11-15)."""

from __future__ import annotations

from django.urls import reverse

from .test_account_password_reset import PasswordResetTestBase
from .test_rim_center import RimCenterTestBase


class RimSearchPersonLabelTests(RimCenterTestBase):
    def test_result_full_name_is_surname_name_patronymic(self):
        self.client.force_login(self.operator)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

        payload = self.client.get(reverse("accounts:rim_user_search"), {"q": "Səməd"}).json()

        self.assertEqual([row["full_name"] for row in payload["results"]], ["Əliyev Elvin Səməd"])


class PasswordResetPersonLabelTests(PasswordResetTestBase):
    def setUp(self):
        super().setUp()
        self.teacher.profile.patronymic = "Səməd"
        self.teacher.profile.save(update_fields=["patronymic"])
        self.login(self.operator)

    def test_suggest_full_name(self):
        response = self.client.post(
            reverse("accounts:account_password_reset_suggest"), {"q": "Səməd"}, content_type="application/json"
        )

        self.assertEqual([row["full_name"] for row in response.json()["results"]], ["Əliyev Elvin Səməd"])

    def test_lookup_full_name(self):
        rows = self.lookup("Elvin Səməd").json()["results"]

        self.assertEqual([row["full_name"] for row in rows], ["Əliyev Elvin Səməd"])

    def test_without_patronymic_is_surname_name(self):
        rows = self.lookup("Quliyeva").json()["results"]

        self.assertEqual([row["full_name"] for row in rows], ["Quliyeva Aysel"])
