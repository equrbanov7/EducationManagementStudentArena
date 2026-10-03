"""Hesab dayandırma: SEÇİLƏN səbəb + «blokdan çıxmaq üçün kimə yaxınlaşmalı» (sahib 2026-10-03).

Kilidlənən qaydalar:

* kataloq / reyestr «Dayandır» əməli səbəb KODU, müraciət ünvanı və tələbəyə qeyd saxlayır; «Digər» izah tələb edir;
* «Blokdan çıxar» hamısını təmizləyir;
* tələbə DOĞRU parolla giriş edəndə 403 «Hesabınız dayandırılıb» səhifəsi — səbəb, ünvan, qeyd; SESSİYA AÇILMIR;
* parol SƏHVDİRSƏ heç nə açıqlanmır (adi forma xətası) — istifadəçi adını təxmin edən səbəbi öyrənmir;
* reyestr kartı hesab vəziyyətini və səbəbi göstərir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.accounts.services import account_block_reasons
from apps.organizations.models import Membership, Role
from core.constants import RoleScopeType

from .test_student_services_sections import PASSWORD, StudentServicesBase

User = get_user_model()


class AccountBlockReasonTest(StudentServicesBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        role, _ = Role.objects.update_or_create(
            organization=cls.org,
            name="block_officer",
            defaults={
                "display_name": "Block officer",
                "level": 80,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": ["people.view_students", "people.manage_status", "student.registry_view"],
                "is_active": True,
            },
        )
        cls.officer = User.objects.create_user("ss_block_officer", "ss_block_officer@qku.edu.az", PASSWORD)
        Membership.objects.create(user=cls.officer, organization=cls.org, role=role, is_primary=True, is_active=True)

    def _officer(self):
        client = Client()
        client.force_login(self.officer)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _block(self, **payload):
        body = {"action": "block", "user_id": str(self.pupil.pk), **payload}
        return self._officer().post(reverse("accounts:people_action"), body)

    def test_catalog_normalizes_reason_and_default_contact(self):
        self.assertEqual(
            account_block_reasons.normalize_choice("tuition_debt", "", " 2-ci korpus  105 "),
            ("tuition_debt", "finance", "2-ci korpus 105"),
        )
        for bad in (("", "", ""), ("nope", "", ""), ("other", "", "x"), ("tuition_debt", "nope", "")):
            with self.assertRaises(account_block_reasons.BlockReasonError):
                account_block_reasons.normalize_choice(*bad)

    def test_block_with_reason_stores_codes_and_unblock_clears_them(self):
        response = self._block(reason_code="tuition_debt", contact_code="", contact_note="2-ci korpus, 105-ci otaq")
        self.assertEqual(response.status_code, 200, response.content)
        self.pupil.refresh_from_db()
        profile = self.pupil.profile
        self.assertFalse(self.pupil.is_active)
        self.assertEqual((profile.block_reason_code, profile.block_contact_code), ("tuition_debt", "finance"))
        self.assertEqual(profile.block_contact_note, "2-ci korpus, 105-ci otaq")
        self.assertIn("Təhsil haqqı", profile.block_reason)

        unblock = self._officer().post(
            reverse("accounts:people_action"), {"action": "unblock", "user_id": str(self.pupil.pk)}
        )
        self.assertEqual(unblock.status_code, 200, unblock.content)
        self.pupil.refresh_from_db()
        profile = self.pupil.profile
        self.assertTrue(self.pupil.is_active)
        self.assertEqual(
            (profile.block_reason_code, profile.block_contact_code, profile.block_contact_note), ("", "", "")
        )

    def test_block_requires_a_reason_choice(self):
        self.assertEqual(self._block().status_code, 400)
        self.assertEqual(self._block(reason_code="other").status_code, 400)  # «Digər» izahsız
        self.pupil.refresh_from_db()
        self.assertTrue(self.pupil.is_active)

    def test_blocked_student_sees_reason_and_contact_but_gets_no_session(self):
        self.pupil.set_password("Pupil-Pass-2026!")
        self.pupil.save(update_fields=["password"])
        self._block(reason_code="missing_documents", contact_code="dean_office", contact_note="Otaq 12")

        client = Client()
        response = client.post(
            reverse("accounts:student_login"), {"username": self.pupil.username, "password": "Pupil-Pass-2026!"}
        )
        self.assertEqual(response.status_code, 403)
        html = response.content.decode()
        self.assertIn("Sənədlər tam təqdim edilməyib", html)
        self.assertIn("Fakültənizin dekanlığı", html)
        self.assertIn("Otaq 12", html)
        self.assertNotIn("_auth_user_id", client.session)
        self.assertEqual(client.get(reverse("accounts:profile")).status_code, 302)  # kabinet bağlıdır

        wrong = Client().post(
            reverse("accounts:student_login"), {"username": self.pupil.username, "password": "wrong-1"}
        )
        self.assertEqual(wrong.status_code, 200)
        self.assertNotIn("Sənədlər tam təqdim edilməyib", wrong.content.decode())

    def test_registry_card_shows_account_block(self):
        self._block(reason_code="tuition_debt", contact_note="Kassa")
        url = reverse("accounts:student_registry_card", args=[self.record.pk])
        payload = self._officer().get(url).json()
        self.assertTrue(payload["can_block"])
        self.assertEqual(payload["account"]["status"], "blocked")
        self.assertEqual(payload["account"]["reason"], "Təhsil haqqı üzrə borc")
        self.assertEqual(payload["account"]["contact"], "Maliyyə şöbəsi (mühasibatlıq)")
        self.assertEqual(payload["account"]["note"], "Kassa")
