"""Akademik qaydalar bayraqları (sahib 2026-10-10 «Yeni qayda var»).

Kilidlənən qaydalar:

* defolt = YENİ qayda: sərbəst iş yoxdur → midterm 30, seminar/lab 5 + 5, «Aktivləşdir» yoxdur, AI düyməsi var;
* bayraq bazadan dəyişir (RİM səhifəsi «1»/«0» göndərir), söndürmə də yazılır, defolta qayıdış sətri silir;
* test/mühit dəyişəni (``ACADEMIC_SELFWORK_ENABLED`` …) defoltu dəyişir — köhnə qaydanın testləri bununla qurulur;
* səhifə bayrağı açar (switch) kimi göstərir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import RuntimeSetting
from apps.accounts.services import runtime_settings_admin
from apps.organizations.models import Membership, Organization, Role
from core import academic_rules
from core import runtime_settings as rs
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "academic-rules"}}


class BoolCoerceTest(SimpleTestCase):
    def test_bool_kind_accepts_form_and_json_values(self):
        spec = rs.SPECS["academic.selfwork_enabled"]
        for raw in (True, "1", "true", "on", "YES"):
            self.assertIs(rs.coerce(spec, raw), True, raw)
        for raw in (False, "0", "false", "off", "no"):
            self.assertIs(rs.coerce(spec, raw), False, raw)
        for raw in ("", None, "2", "maybe"):
            self.assertIsNone(rs.coerce(spec, raw), raw)


class AcademicRulesDefaultsTest(SimpleTestCase):
    """Testlərdə runtime settings sönülüdür — defoltlar (yeni qayda) oxunur."""

    def test_new_rule_is_the_default(self):
        self.assertFalse(academic_rules.selfwork_enabled())
        self.assertEqual(academic_rules.midterm_max(), 30)
        self.assertEqual(academic_rules.selfwork_max(), 0)
        self.assertTrue(academic_rules.activity_split())
        self.assertFalse(academic_rules.lesson_activation_enabled())
        self.assertTrue(academic_rules.ai_assistant_button_enabled())
        self.assertFalse(academic_rules.available_exams_page_enabled())
        snap = academic_rules.snapshot()
        self.assertEqual(snap["attendance_max"] + snap["activity_max"] + snap["midterm_max"] + snap["selfwork_max"], 50)

    @override_settings(ACADEMIC_SELFWORK_ENABLED=True, ACADEMIC_ACTIVITY_SPLIT=False, JOURNAL_LESSON_ACTIVATION=True)
    def test_environment_can_restore_the_previous_rule(self):
        self.assertTrue(academic_rules.selfwork_enabled())
        self.assertEqual(academic_rules.midterm_max(), 20)
        self.assertEqual(academic_rules.selfwork_max(), 10)
        self.assertFalse(academic_rules.activity_split())
        self.assertTrue(academic_rules.lesson_activation_enabled())
        snap = academic_rules.snapshot()
        self.assertEqual(snap["attendance_max"] + snap["activity_max"] + snap["midterm_max"] + snap["selfwork_max"], 50)


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class AcademicRulesSettingsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ar_owner", "ar_owner@qku.edu.az", "pw")
        cls.org = Organization.objects.create(
            name="AR Univ", slug="ar-univ", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active"
        )
        role, _ = Role.objects.update_or_create(
            organization=cls.org,
            name="ikt_rehber",
            defaults={
                "display_name": "ikt_rehber",
                "level": 95,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": ["semester.view"],
                "is_active": True,
            },
        )
        cls.rim = User.objects.create_user("ar_rim", "ar_rim@qku.edu.az", "pw")
        Membership.objects.create(user=cls.rim, organization=cls.org, role=role, is_primary=True, is_active=True)

    def setUp(self):
        RuntimeSetting.objects.all().delete()
        rs.invalidate()

    def tearDown(self):
        rs.invalidate()

    def test_switching_selfwork_back_on_and_off(self):
        runtime_settings_admin.save_values(actor=self.rim, data={"academic.selfwork_enabled": "1"})
        self.assertTrue(RuntimeSetting.objects.filter(key="academic.selfwork_enabled", value=True).exists())
        self.assertTrue(academic_rules.selfwork_enabled())
        self.assertEqual(academic_rules.midterm_max(), 20)

        # Defolta («0») qayıdış sətri silir — yeni qayda yenidən işləyir.
        result = runtime_settings_admin.save_values(actor=self.rim, data={"academic.selfwork_enabled": "0"})
        self.assertTrue(result["changed"][0]["reset"])
        self.assertFalse(RuntimeSetting.objects.filter(key="academic.selfwork_enabled").exists())
        self.assertEqual(academic_rules.midterm_max(), 30)

    def test_turning_a_default_on_flag_off_is_stored(self):
        runtime_settings_admin.save_values(actor=self.rim, data={"ai.assistant_button": "0"})
        self.assertTrue(RuntimeSetting.objects.filter(key="ai.assistant_button", value=False).exists())
        self.assertFalse(academic_rules.ai_assistant_button_enabled())
        # «override() or fallback» tələsi: söndürülmüş bayraq defolta düşməməlidir.
        self.assertIs(rs.get_bool("ai.assistant_button"), False)

    def test_unchanged_flag_is_not_rewritten(self):
        result = runtime_settings_admin.save_values(
            actor=self.rim, data={"academic.activity_split": "1", "journal.lesson_activation": "0"}
        )
        self.assertEqual(result["changed"], [])
        self.assertFalse(RuntimeSetting.objects.exists())

    def test_hygiene_prevention_switch_is_read_from_the_settings_page(self):
        from apps.registrar import journal_hygiene_guard

        self.assertTrue(journal_hygiene_guard.prevention_enabled())
        runtime_settings_admin.save_values(actor=self.rim, data={"journal.hygiene_prevention": "0"})
        self.assertFalse(journal_hygiene_guard.prevention_enabled())

    def test_invalid_flag_value_is_rejected(self):
        with self.assertRaises(runtime_settings_admin.RuntimeSettingsError) as ctx:
            runtime_settings_admin.save_values(actor=self.rim, data={"academic.activity_split": "maybe"})
        self.assertIn("academic.activity_split", ctx.exception.errors)

    def test_page_renders_flags_as_switches(self):
        client = Client()
        client.force_login(self.rim)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:profile_section_fragment", kwargs={"section": "system-settings"}))
        self.assertEqual(response.status_code, 200)
        content = response.json()["html"]
        self.assertIn('name="academic.selfwork_enabled"', content)
        self.assertIn('type="checkbox" role="switch" id="ss-academic.selfwork_enabled"', content)
        self.assertIn('id="ss-journal.lesson_activation"', content)
        groups = {group["key"]: group for group in response.context["system_settings_section"]["groups"]}
        self.assertEqual(
            [field["key"] for field in groups["academic"]["fields"]],
            [
                "academic.selfwork_enabled",
                "academic.activity_split",
                "academic.coursework_enabled",
                "syllabus.hours_from_load",  # sahib 2026-10-12
            ],
        )
        self.assertIn('id="ssConfirmDialog"', content)  # açar dəyişəndə təsdiq pəncərəsi


class PeriodScopeTest(SimpleTestCase):
    """Yeni qaydalar yalnız «midterm rejimi» dövrlərinə aiddir; köhnə dövrlərdə sərbəst iş tarix kimi qalır."""

    @staticmethod
    def _period(year_text, settings=None):
        from types import SimpleNamespace

        org = SimpleNamespace(settings=settings or {})
        return SimpleNamespace(academic_year=year_text, start_date=None, organization=org)

    def test_old_periods_keep_selfwork_new_periods_follow_the_flag(self):
        old, new = self._period("2025/2026"), self._period("2026/2027")
        self.assertFalse(academic_rules.period_uses_new_rules(old))
        self.assertTrue(academic_rules.period_uses_new_rules(new))
        self.assertTrue(academic_rules.selfwork_active_for_period(old))
        self.assertFalse(academic_rules.selfwork_active_for_period(new))
        self.assertFalse(academic_rules.selfwork_active_for_period(None))
        with self.settings(ACADEMIC_SELFWORK_ENABLED=True):
            self.assertTrue(academic_rules.selfwork_active_for_period(new))

    def test_org_override_and_interim_mode_agree(self):
        from apps.registrar import interim_assessment

        late = self._period("2026/2027", {"registrar": {"midterm_from_year": 2027}})
        self.assertFalse(academic_rules.period_uses_new_rules(late))
        self.assertEqual(interim_assessment.mode_for_period(late), interim_assessment.MODE_KOLLOKVIUM)
        self.assertTrue(academic_rules.selfwork_active_for_period(late))
        self.assertEqual(interim_assessment.mode_for_period(None), interim_assessment.MODE_MIDTERM)
