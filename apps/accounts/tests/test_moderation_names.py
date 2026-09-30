"""Hesab adları — nalayiq ad filtri (sahib 2026-09-30, WP MOD).

Tətbiq nöqtələri:

* profil «Məlumatları redaktə et» (``profile_form=edit-profile``) — ad / soyad;
* RİM şəxsi məlumat redaktəsi (``accounts:rim_action`` → ``edit``) — ad / soyad / ata adı;
* RİM «Yeni hesab» (``services.rim.create.create_account``) — ad / soyad / ata adı;
* açıq qeydiyyat (``accounts:register``, prod-da söndürülüb) — ad / soyad.

Hər biri: rədd (söz təkrarlanmır), heç nə saxlanmır, audit qeydi (kim, IP, sahə).
DƏYİŞMƏYƏN köhnə ad yenidən yoxlanmır — idxal olunmuş ad başqa sahənin
redaktəsinə mane olmasın.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.services import get_pending_registration
from apps.accounts.services.rim import create as rim_create
from apps.audit.models import AuditLog
from apps.organizations.models import Country
from core import rate_limit as rate_limit_module
from core.constants import OrganizationType
from core.moderation.enforcement import PROFANITY_RESOURCE_TYPE, rejection_message
from core.roles import ProfileRole

from .test_rim_account_create import RimCreateBase, base_payload
from .test_rim_center import RimCenterTestBase

User = get_user_model()
IP = "192.0.2.55"


def _rows():
    return AuditLog.objects.filter(resource_type=PROFANITY_RESOURCE_TYPE).order_by("created_at")


class ProfileEditModerationTest(TestCase):
    def setUp(self):
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        self.user = User.objects.create_user(
            "mod_profile", "mod_profile@example.com", "StrongPass123!", first_name="Old", last_name="Name"
        )
        self.client = Client(REMOTE_ADDR=IP, HTTP_USER_AGENT="MOD-UA")
        self.client.force_login(self.user)

    def _post(self, **fields):
        data = {"profile_form": "edit-profile", "email": self.user.email, "first_name": "Old", "last_name": "Name"}
        data.update(fields)
        return self.client.post(reverse("accounts:profile"), data)

    def test_profane_name_is_rejected_and_logged(self):
        response = self._post(first_name="Blyat", last_name="Məmmədov")
        self.assertEqual(response.status_code, 302)
        self.assertIn("section=edit-profile", response.url)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn(rejection_message(), messages)
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name), ("Old", "Name"))

        row = _rows().get()
        self.assertEqual(row.user_id, self.user.pk)
        self.assertEqual(row.ip_address, IP)
        self.assertEqual(row.user_agent, "MOD-UA")
        self.assertEqual(row.resource_repr, "accounts.profile.first_name")
        self.assertEqual(row.new_values["value_masked"], "B****")

    def test_real_names_are_saved(self):
        response = self._post(first_name="Pənah", last_name="Səmədov")
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name), ("Pənah", "Səmədov"))
        self.assertFalse(_rows().exists())

    def test_unchanged_legacy_name_does_not_block_other_edits(self):
        User.objects.filter(pk=self.user.pk).update(last_name="Siktirov")
        response = self._post(last_name="Siktirov", phone="0501234567")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(UserProfile.objects.get(user=self.user).phone, "0501234567")
        self.assertFalse(_rows().exists())


class RimEditModerationTest(RimCenterTestBase):
    def test_rim_operator_cannot_set_a_profane_name(self):
        self.login_operator()
        response = self.client.post(
            reverse("accounts:rim_action"),
            data={"action": "edit", "user_id": self.teacher.pk, "last_name": "Qəhbəyev", "reason": "test"},
            content_type="application/json",
            REMOTE_ADDR=IP,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "name_inappropriate")
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.last_name, "Əliyev")

        row = _rows().get()
        self.assertEqual(row.user_id, self.operator.pk)
        self.assertEqual(row.organization_id, self.org.pk)
        self.assertEqual(row.ip_address, IP)
        self.assertEqual(row.resource_id, str(self.teacher.pk))
        self.assertEqual(row.resource_repr, "accounts.rim.edit.last_name")

    def test_rim_operator_can_fix_a_real_name(self):
        self.login_operator()
        response = self.client.post(
            reverse("accounts:rim_action"),
            data={"action": "edit", "user_id": self.teacher.pk, "patronymic": "Pənah oğlu", "reason": "sənəd"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(_rows().exists())


class RimCreateModerationTest(RimCreateBase):
    def test_profane_patronymic_is_a_field_error_and_is_logged(self):
        with self.assertRaises(rim_create.RimCreateError) as caught:
            self.create(self.rim, "student", group=str(self.group.pk), patronymic="Fuck")
        self.assertEqual(caught.exception.reason_code, "name_inappropriate")
        self.assertEqual(caught.exception.fields, {"patronymic": rejection_message()})
        self.assertFalse(User.objects.filter(profile__fin="1AAAAA1").exists())
        row = _rows().get()
        self.assertEqual(row.user_id, self.rim.pk)
        self.assertEqual(row.organization_id, self.org.pk)
        self.assertEqual(row.resource_repr, "accounts.rim.create.patronymic")

    def test_real_names_are_created(self):
        result = self.create(self.rim, "student", group=str(self.group.pk), first_name="Səkinə", last_name="Pənahova")
        self.assertTrue(User.objects.filter(pk=result["user_id"], first_name="Səkinə").exists())
        self.assertFalse(_rows().exists())

    def test_payload_helper_is_clean(self):
        self.assertEqual(base_payload()["first_name"], "Nigar")


class RegisterModerationTest(TestCase):
    def setUp(self):
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        Country.objects.get_or_create(code="AZ", defaults={"name": "Azerbaijan", "is_active": True})
        self.client = Client(REMOTE_ADDR=IP)

    def _payload(self, **overrides):
        payload = {
            "username": "modnewuser",
            "email": "modnewuser@example.com",
            "password": "StrongPass123!",
            "password2": "StrongPass123!",
            "first_name": "Aysel",
            "last_name": "Quliyeva",
            "country": "AZ",
            "organization_type": OrganizationType.INDIVIDUAL,
            "join_organization": "",
            "institution": "",
            "institution_not_listed_name": "",
            "organization_identifier": "ORG-001",
            "organization_license_identifier": "LIC-001",
            "initial_role": ProfileRole.MEMBER,
            "accept_privacy_policy": "on",
        }
        payload.update(overrides)
        return payload

    def test_profane_signup_name_is_a_form_error_and_is_logged_anonymously(self):
        response = self.client.post(reverse("accounts:register"), self._payload(last_name="Orospuoğlu"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(rejection_message(), response.context["form"].errors.get("last_name", []))
        self.assertIsNone(get_pending_registration("modnewuser@example.com"))
        row = _rows().get()
        self.assertIsNone(row.user_id)
        self.assertEqual(row.ip_address, IP)
        self.assertEqual(row.resource_repr, "accounts.register.last_name")

    def test_real_signup_name_passes_the_filter(self):
        response = self.client.post(reverse("accounts:register"), self._payload())
        self.assertRedirects(response, reverse("accounts:verify_code"))
        self.assertFalse(_rows().exists())
