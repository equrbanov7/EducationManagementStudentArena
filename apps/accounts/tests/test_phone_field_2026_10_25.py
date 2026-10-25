"""Telefon sahəsi (ölkə seçicisi + E.164) bütün yazma yollarında — sahib 2026-10-25.

Səthlər: məcburi profil tamamlama (ayrıca ``test_profile_completion_2026_10_17``), profil redaktəsi (əsas +
əlavə telefon), RİM «Yeni hesab» və RİM redaktə paneli, Excel idxalı, ictimai əlaqə forması.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.services.intake import validate as intake_validate
from apps.accounts.services.rim import create as rim_create
from apps.contact.forms import ContactForm
from apps.contact.models import ContactMessage
from core.roles import ProfileRole

from . import test_rim_account_create as create_base
from . import test_rim_center as rim_base
from .test_academic_profile_and_password_otp import _make_user

User = get_user_model()


class ProfileEditPhoneTest(TestCase):
    def setUp(self):
        self.user = _make_user("phone_edit_user", ProfileRole.TEACHER)
        self.client.force_login(self.user)
        self.url = reverse("accounts:profile") + "?section=edit-profile"

    def post(self, **phones):
        data = {
            "profile_form": "edit-profile",
            "section": "edit-profile",
            "first_name": "Tel",
            "last_name": "Redaktə",
            "email": "phone_edit_user@example.com",
            "bio": "",
            "location": "",
        }
        data.update(phones)
        return self.client.post(self.url, data=data)

    def profile(self):
        return UserProfile.objects.get(user=self.user)

    def test_form_renders_country_picker_for_both_phones_and_azerbaijan_default(self):
        html = self.client.get(self.url).content.decode()
        for name in ("phone", "phone_secondary"):
            self.assertIn(f'name="{name}_country"', html)
            self.assertIn(f'name="{name}"', html)
        self.assertIn("selected>🇦🇿 Azərbaycan +994</option>", html)
        self.assertIn("data-phone-field", html)

    def test_foreign_primary_and_azerbaijani_secondary_are_stored_as_e164(self):
        response = self.post(
            phone="0555 123 45 67", phone_country="TR", phone_secondary="055 000 00 02", phone_secondary_country="AZ"
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.profile().phone, "+905551234567")
        self.assertEqual(self.profile().phone_secondary, "+994550000002")

    def test_existing_number_is_shown_with_its_country_recognised(self):
        UserProfile.objects.filter(user=self.user).update(phone="+905551234567", phone_secondary="+994501234567")
        html = self.client.get(self.url).content.decode()
        self.assertIn("selected>🇹🇷 Türkiyə +90</option>", html)
        self.assertIn('value="0555 123 45 67"', html)
        self.assertIn('value="050 123 45 67"', html)

    def test_wrong_length_is_rejected_and_nothing_is_saved(self):
        UserProfile.objects.filter(user=self.user).update(phone="+994501234567")
        response = self.post(phone="12 34", phone_country="AZ", phone_secondary="")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.profile().phone, "+994501234567")
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.first_name, "Tel")  # xəta varsa heç nə saxlanmır

    def test_unreadable_legacy_value_does_not_block_saving_other_fields(self):
        UserProfile.objects.filter(user=self.user).update(phone="555000")
        response = self.post(phone="555000", phone_country="AZ", phone_secondary="")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.profile().phone, "555000")
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_name, "Redaktə")

    def test_clearing_the_number_is_allowed(self):
        UserProfile.objects.filter(user=self.user).update(phone="+994501234567", phone_secondary="+994551234567")
        self.post(phone="", phone_country="AZ", phone_secondary="", phone_secondary_country="AZ")
        self.assertEqual(self.profile().phone, "")
        self.assertEqual(self.profile().phone_secondary, "")


class RimPhoneEditTest(rim_base.RimCenterTestBase):
    def test_edit_with_country_stores_e164(self):
        self.login_operator()
        response = self.act("edit", self.teacher, phone="532 123 45 67", phone_country="TR", reason="xarici əməkdaş")
        self.assertEqual(response.status_code, 200)
        self.teacher.profile.refresh_from_db()
        self.assertEqual(self.teacher.profile.phone, "+905321234567")
        card = response.json()["user"]
        self.assertEqual((card["phone_country"], card["phone_national"]), ("TR", "0532 123 45 67"))

    def test_azerbaijan_is_default_without_country(self):
        self.login_operator()
        self.act("edit", self.teacher, phone="050 123 45 67", reason="düzəliş")
        self.teacher.profile.refresh_from_db()
        self.assertEqual(self.teacher.profile.phone, "+994501234567")

    def test_wrong_length_is_a_400_with_country_specific_message(self):
        self.login_operator()
        response = self.act("edit", self.teacher, phone="12 34", phone_country="TR", reason="səhv")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_phone")
        self.teacher.profile.refresh_from_db()
        self.assertNotEqual(self.teacher.profile.phone, "12 34")

    def test_unchanged_unreadable_legacy_phone_does_not_block_other_edits(self):
        self.teacher.profile.phone = "555000"
        self.teacher.profile.save(update_fields=["phone"])
        self.login_operator()
        response = self.act(
            "edit", self.teacher, patronymic="Yeni", phone="555000", phone_country="AZ", reason="ata adı"
        )
        self.assertEqual(response.status_code, 200)
        self.teacher.profile.refresh_from_db()
        self.assertEqual(self.teacher.profile.patronymic, "Yeni")
        self.assertEqual(self.teacher.profile.phone, "555000")

    def test_edit_panel_ships_the_phone_template_for_the_js_form(self):
        self.login_operator()
        html = self.client.get(reverse("accounts:profile") + "?section=rim-center").content.decode()
        self.assertIn("data-rim-phone-template", html)
        self.assertIn('data-rim-edit-field="phone_country"', html)
        self.assertIn('data-rim-edit-field="phone"', html)


class RimCreatePhoneTest(create_base.RimCreateBase):
    def test_teacher_with_foreign_country_is_stored_as_e164(self):
        result = self.create(self.rim, "teacher", fin="7PHONE7", phone="532 123 45 67", phone_country="TR")
        profile = UserProfile.objects.get(user_id=result["user_id"])
        self.assertEqual(profile.phone, "+905321234567")

    def test_azerbaijan_default_and_blank_phone(self):
        result = self.create(self.rim, "teacher", fin="7PHONE8")
        self.assertEqual(UserProfile.objects.get(user_id=result["user_id"]).phone, "+994501112233")
        blank = self.create(self.rim, "teacher", fin="7PHONE9", phone="")
        self.assertEqual(UserProfile.objects.get(user_id=blank["user_id"]).phone, "")

    def test_wrong_length_is_a_phone_field_error(self):
        with self.assertRaises(rim_create.RimCreateError) as caught:
            self.create(self.rim, "teacher", fin="7PHONEA", phone="123", phone_country="AZ")
        self.assertIn("phone", caught.exception.fields)
        self.assertFalse(User.objects.filter(profile__fin="7PHONEA").exists())


class IntakePhoneTest(TestCase):
    def test_excel_phone_is_normalised_when_readable_and_kept_otherwise(self):
        self.assertEqual(intake_validate._normalized_phone("0501112233"), "+994501112233")
        self.assertEqual(intake_validate._normalized_phone("+90 532 123 45 67"), "+905321234567")
        self.assertEqual(intake_validate._normalized_phone("zəng edin"), "zəng edin")
        self.assertEqual(intake_validate._normalized_phone(None), "")


class ContactPhoneTest(TestCase):
    payload = {
        "name": "Test İstifadəçi",
        "email": "ziyaretci@example.com",
        "subject": ContactMessage.SUBJECT_CHOICES[0][0],
        "message": "Salam, bu sınaq mesajıdır və kifayət qədər uzundur.",
        "website": "",
    }

    def form(self, **extra):
        return ContactForm({**self.payload, **extra})

    def test_azerbaijan_default_normalised_to_e164(self):
        form = self.form(phone="050 123 45 67")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["phone"], "+994501234567")

    def test_foreign_country(self):
        form = self.form(phone="0532 123 45 67", phone_country="TR")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["phone"], "+905321234567")

    def test_wrong_length_and_garbage_rejected_blank_allowed(self):
        self.assertIn("phone", self.form(phone="123", phone_country="TR").errors)
        self.assertIn("phone", self.form(phone="abc").errors)
        blank = self.form(phone="")
        self.assertTrue(blank.is_valid(), blank.errors)
        self.assertEqual(blank.cleaned_data["phone"], "")

    def test_page_renders_country_picker(self):
        html = self.client.get(reverse("contact")).content.decode()
        self.assertIn('name="phone_country"', html)
        self.assertIn("selected>🇦🇿 Azərbaycan +994</option>", html)
