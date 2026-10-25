"""``core.phone`` — ölkə seçimi, E.164 saxlama, ölkəyə uyğun yoxlama (sahib 2026-10-25)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.template import Context, Template
from django.test import SimpleTestCase

from core import phone


class CleanPhoneTest(SimpleTestCase):
    def test_azerbaijan_is_default_and_local_forms_are_equivalent(self):
        for raw in ("050 123 45 67", "0501234567", "501234567", "(050) 123-45-67", "994501234567", "+994 50 123 45 67"):
            self.assertEqual(phone.clean_phone(raw), "+994501234567", raw)

    def test_every_azerbaijani_operator_prefix_is_accepted(self):
        for prefix in ("050", "051", "055", "070", "077", "099", "010", "060"):
            self.assertEqual(phone.clean_phone(f"{prefix} 123 45 67"), "+994" + prefix[1:] + "1234567", prefix)

    def test_foreign_country_uses_its_own_local_form(self):
        self.assertEqual(phone.clean_phone("0555 123 45 67", "TR"), "+905551234567")
        self.assertEqual(phone.clean_phone("555 123 45 67", "TR"), "+905551234567")
        self.assertEqual(phone.clean_phone("(201) 555-0123", "US"), "+12015550123")
        self.assertEqual(phone.clean_phone("8 912 345 67 89", "RU"), "+79123456789")
        self.assertEqual(phone.clean_phone("07400 123456", "GB"), "+447400123456")

    def test_international_prefix_overrides_selected_country(self):
        self.assertEqual(phone.clean_phone("+90 555 123 45 67", "AZ"), "+905551234567")
        self.assertEqual(phone.clean_phone("0090 555 123 45 67", "AZ"), "+905551234567")

    def test_wrong_length_is_rejected_per_country(self):
        with self.assertRaises(ValidationError) as short:
            phone.clean_phone("50 123", "AZ")
        self.assertEqual(short.exception.code, "too_short")
        with self.assertRaises(ValidationError) as long:
            phone.clean_phone("050 123 45 67 89", "AZ")
        self.assertEqual(long.exception.code, "too_long")
        # 9 rəqəm Azərbaycan üçün düzgündür, ABŞ üçün qısadır.
        phone.clean_phone("501234567", "AZ")
        with self.assertRaises(ValidationError):
            phone.clean_phone("501234567", "US")

    def test_garbage_is_rejected_and_error_shows_country_example(self):
        for bad in ("abc 123 45 67", "+999 123 456", "12-ab-34"):
            with self.assertRaises(ValidationError, msg=bad):
                phone.clean_phone(bad)
        with self.assertRaises(ValidationError) as exc:
            phone.clean_phone("abc", "TR")
        self.assertIn(phone.example_national("TR"), exc.exception.messages[0])

    def test_blank_is_required_only_on_request(self):
        self.assertEqual(phone.clean_phone("  "), "")
        with self.assertRaises(ValidationError) as exc:
            phone.clean_phone("", required=True)
        self.assertEqual(exc.exception.code, "required")

    def test_unknown_country_falls_back_to_azerbaijan(self):
        self.assertEqual(phone.clean_phone("050 123 45 67", "ZZ"), "+994501234567")
        self.assertEqual(phone.normalize_region("tr"), "TR")
        self.assertEqual(phone.normalize_region(None), "AZ")

    def test_clean_phone_field_reads_country_companion(self):
        self.assertEqual(phone.clean_phone_field({"phone": "532 123 45 67", "phone_country": "TR"}), "+905321234567")
        self.assertEqual(phone.clean_phone_field({"phone": "050 123 45 67"}), "+994501234567")
        self.assertEqual(
            phone.clean_phone_field({"other": "532 123 45 67", "other_country": "TR"}, "other"), "+905321234567"
        )


class SplitPhoneTest(SimpleTestCase):
    def test_existing_azerbaijani_number_is_shown_as_az_local(self):
        parts = phone.split_phone("+994501234567")
        self.assertEqual((parts.region, parts.national, parts.parsed), ("AZ", "050 123 45 67", True))

    def test_country_is_recognised_from_the_number(self):
        self.assertEqual(phone.split_phone("+905551234567").region, "TR")
        self.assertEqual(phone.split_phone("+79123456789").region, "RU")
        self.assertEqual(phone.split_phone("+12015550123").region, "US")
        self.assertEqual(phone.split_phone("+447400123456").region, "GB")

    def test_legacy_values(self):
        # «+»-sız köhnə dəyər Azərbaycan sayılır; boş dəyər defolt ölkəni verir; oxunmayan dəyər olduğu kimi qalır.
        self.assertEqual(phone.split_phone("050 123 45 67").region, "AZ")
        self.assertEqual(phone.split_phone("").region, "AZ")
        garbage = phone.split_phone("zəng edin")
        self.assertEqual((garbage.region, garbage.national, garbage.parsed), ("AZ", "zəng edin", False))

    def test_roundtrip_through_form_values(self):
        for stored in ("+994501234567", "+905551234567", "+12015550123", "+79123456789", "+4915123456789"):
            parts = phone.split_phone(stored)
            self.assertEqual(phone.clean_phone(parts.national, parts.region), stored, stored)


class ResolvePhoneUpdateTest(SimpleTestCase):
    def test_unchanged_unreadable_legacy_value_is_kept(self):
        # Köhnə sərbəst mətn («555000») dəyişməyibsə profilin saxlanmasını bloklamır.
        legacy = "555000"
        self.assertEqual(
            phone.resolve_phone_update({"phone": "555000", "phone_country": "AZ"}, "phone", legacy), legacy
        )

    def test_unchanged_valid_value_is_normalised(self):
        posted = {"phone": "050 123 45 67", "phone_country": "AZ"}
        self.assertEqual(phone.resolve_phone_update(posted, "phone", "050 123 45 67"), "+994501234567")

    def test_changed_value_is_validated(self):
        with self.assertRaises(ValidationError):
            phone.resolve_phone_update({"phone": "555000", "phone_country": "AZ"}, "phone", "+994501234567")
        self.assertEqual(
            phone.resolve_phone_update({"phone": "532 123 45 67", "phone_country": "TR"}, "phone", "+994501234567"),
            "+905321234567",
        )

    def test_blank_clears(self):
        self.assertEqual(phone.resolve_phone_update({"phone": "", "phone_country": "AZ"}, "phone", "+994501234567"), "")


class CountryOptionsTest(SimpleTestCase):
    def test_azerbaijan_first_with_flag_name_and_code(self):
        options = phone.country_options("az")
        first = options[0]
        self.assertEqual((first.iso, first.dial, first.name, first.flag), ("AZ", "994", "Azərbaycan", "🇦🇿"))
        self.assertEqual(first.example, "050 123 45 67")

    def test_all_regions_present_with_unique_iso_and_example(self):
        options = phone.country_options("en")
        isos = [option.iso for option in options]
        self.assertEqual(len(isos), len(set(isos)))
        self.assertGreater(len(isos), 200)
        for option in options:
            self.assertTrue(option.dial.isdigit(), option.iso)
            self.assertTrue(option.example, option.iso)

    def test_names_follow_language_and_fall_back_to_english(self):
        names = {
            lang: {o.iso: o.name for o in phone.country_options(lang)}["DE"] for lang in ("az", "en", "ru", "tr", "de")
        }
        self.assertEqual(
            names, {"az": "Almaniya", "en": "Germany", "ru": "Германия", "tr": "Almanya", "de": "Deutschland"}
        )
        self.assertEqual({o.iso: o.name for o in phone.country_options("xx")}["DE"], "Germany")

    def test_shared_dial_code_has_one_main_region(self):
        by_dial = {}
        for option in phone.country_options("en"):
            by_dial.setdefault(option.dial, []).append(option)
        for dial, group in by_dial.items():
            self.assertEqual(sum(1 for option in group if option.main), 1, dial)


class PhoneFieldTagTest(SimpleTestCase):
    def render(self, source, **context):
        return Template("{% load phone_tags %}" + source).render(Context(context))

    def test_default_renders_azerbaijan_selected_with_example_placeholder(self):
        html = self.render('{% phone_field name="phone" value="" field_id="pf" %}')
        self.assertIn('name="phone_country"', html)
        self.assertIn('id="pf-country"', html)
        self.assertIn('name="phone"', html)
        self.assertIn('placeholder="050 123 45 67"', html)
        self.assertIn("selected>🇦🇿 Azərbaycan +994</option>", html)
        self.assertIn("data-bootstrap-select", html)
        self.assertNotIn("<style", html)
        self.assertNotIn("onchange", html)

    def test_existing_foreign_number_selects_its_country_and_shows_local_form(self):
        html = self.render('{% phone_field name="phone" value="+905551234567" %}')
        self.assertIn("selected>🇹🇷 Türkiyə +90</option>", html)
        self.assertIn('value="0555 123 45 67"', html)

    def test_posted_country_and_text_are_echoed_back(self):
        html = self.render('{% phone_field name="phone" value="555 12" country="TR" invalid=True %}')
        self.assertIn("selected>🇹🇷 Türkiyə +90</option>", html)
        self.assertIn('value="555 12"', html)
        self.assertIn('aria-invalid="true"', html)

    def test_data_attr_marks_both_controls(self):
        html = self.render('{% phone_field name="phone" value="" data_attr="data-rimc-field" %}')
        self.assertIn('data-rimc-field="phone"', html)
        self.assertIn('data-rimc-field="phone_country"', html)
