"""Sahib 2026-10-10: «Sərbəst iş» yeni qayda dövrlərində (2026/2027+) jurnalda YOXDUR.

RİM «Sistem tənzimləmələri»ndə sərbəst iş söndürülüdür (defolt) → 2026/2027 açılışında tab, stepper
addımı, birbaşa POST, sənədli düzəliş hədəfi və fənn qovluğu hook-u yoxdur. Köhnə (2025/2026, K1–K3)
semestrdə JURNAL əvvəlki kimidir (tarix dəyişmir), tənzimləmə yandırılanda 2026/2027-də də geri qayıdır —
kod, model və data toxunulmur. Sillabus SƏNƏDİ isə (sahib 2026-10-11) semestrdən asılı deyil — hər iki
açılışda cari qayda (bax ``apps.syllabus.rules``).
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import item_corrections, selfwork_hook, services
from apps.registrar.models import Enrollment, SelfWorkTopic, Subject
from apps.syllabus import services as syllabus_services
from apps.syllabus.tests.factories import complete_section_data
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

TAB = 'data-jtab="serbest"'
STEP = 'data-jd-step="5"'
PANEL = 'id="jd-panel-serbest"'


class SelfworkHiddenJournalTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("swh_owner", "swh_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SWH Univ",
                slug="swh-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="SWH101", name="Sərbəst işsiz fənn")
            cls.teacher = User.objects.create_user("swh_teacher", "swh_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("swh_student", "swh_student@qku.edu.az", "pw")
            for user, role in ((cls.teacher, "teacher"), (cls.student, "student")):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    is_primary=True,
                    is_active=True,
                )
            cls.new_offering, cls.new_enrollment = cls._offering("2026/2027", datetime.date(2026, 9, 15), True)
            cls.old_offering, cls.old_enrollment = cls._offering("2025/2026", datetime.date(2025, 9, 15), False)

    @classmethod
    def _offering(cls, year, start, current):
        group = OrgUnit.objects.create(
            organization=cls.org, name=f"SWH-{year[:4]}", slug=f"swh-g-{year[:4]}", unit_type=OrgUnitType.GROUP
        )
        period = AcademicPeriod.objects.create(
            organization=cls.org,
            name=f"Payız {year}",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year=year,
            start_date=start,
            end_date=start + datetime.timedelta(days=130),
            is_current=current,
        )
        offering = services.get_or_create_offering(
            organization=cls.org, subject=cls.subject, period=period, group=group
        )
        offering.instructor = cls.teacher
        offering.lesson_hours = 60
        offering.save(update_fields=["instructor", "lesson_hours"])
        enrollment = Enrollment.objects.create(organization=cls.org, student=cls.student, offering=offering)
        return offering, enrollment

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _detail(self, offering, query="", user=None):
        url = reverse("registrar:journal_detail", args=[offering.id]) + query
        response = self._client(user or self.teacher).get(url)
        self.assertEqual(response.status_code, 200)
        return response

    def _add_topic(self, offering):
        url = reverse("registrar:journal_selfwork_action", args=[offering.id])
        return self._client(self.teacher).post(url, {"action": "add_topic", "topic_title": "Mövzu 1"})

    def _topic(self, offering):
        with bypass_rls():
            return SelfWorkTopic.objects.create(organization=self.org, offering=offering, title="Köhnə mövzu", order=1)

    # ── 2026/2027 (defolt — sərbəst iş söndürülüb) ─────────────────────────
    def test_new_rule_journal_has_no_selfwork_tab_step_or_stylesheet(self):
        response = self._detail(self.new_offering)
        self.assertFalse(response.context["selfwork_active"])
        self.assertNotContains(response, TAB)
        self.assertNotContains(response, STEP)
        self.assertNotContains(response, "selfwork_archive.css")
        self.assertContains(response, 'data-jtab="yekun"')  # qalan tablar yerindədir
        self.assertContains(response, 'data-jd-step="6"')  # daxili nömrə dəyişmir (journal_grid.js setStep)

    def test_new_rule_serbest_tab_falls_back_to_the_grid(self):
        response = self._detail(self.new_offering, "?jt=serbest")
        self.assertEqual(response.context["active_tab"], "grid")
        self.assertIsNone(response.context["selfwork_board"])
        self.assertNotContains(response, PANEL)

    def test_new_rule_direct_post_is_refused_and_writes_nothing(self):
        response = self._add_topic(self.new_offering)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(SelfWorkTopic.objects.filter(offering=self.new_offering).exists())

    def test_new_rule_documented_correction_is_refused(self):
        topic = self._topic(self.new_offering)
        with bypass_rls(), self.assertRaises(ValidationError):
            item_corrections.apply_selfwork_correction(
                offering=self.new_offering,
                topic=topic,
                enrollment=self.new_enrollment,
                new_done=True,
                reason="other",
                note="qeyd",
                document=None,
                by_user=self.teacher,
            )
        with bypass_rls(), self.assertRaises(ValidationError):
            item_corrections.revert_last_selfwork_correction(
                topic=topic, enrollment=self.new_enrollment, by_user=self.teacher
            )

    def test_new_rule_correction_modal_offers_no_selfwork_target(self):
        with bypass_rls():
            admin = User.objects.create_user("swh_admin", "swh_admin@qku.edu.az", "pw", is_superuser=True)
        new = self._detail(self.new_offering, "?correct=1", user=admin)
        old = self._detail(self.old_offering, "?correct=1", user=admin)
        self.assertNotContains(new, "data-corr-sw-wrap")
        self.assertContains(old, "data-corr-sw-wrap")

    def test_new_rule_subject_folder_hook_writes_nothing(self):
        with bypass_rls():
            ok, message = selfwork_hook.record_points(
                offering=self.new_offering,
                enrollment=self.new_enrollment,
                slot_index=1,
                slot_title="Sərbəst iş 1",
                max_points="5",
                points="5",
                source_ref="test:1",
                by_user=self.teacher,
            )
            preview = selfwork_hook.preview(
                offering=self.new_offering, enrollment=self.new_enrollment, slot_index=1, points="5"
            )
        self.assertFalse(ok)
        self.assertIn("tətbiq olunmur", message)
        self.assertTrue(preview["blocked"])
        self.assertFalse(SelfWorkTopic.objects.filter(offering=self.new_offering).exists())

    def test_journal_list_stepper_follows_the_current_rule(self):
        response = self._client(self.teacher).get(reverse("registrar:journal_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, STEP)
        with override_settings(ACADEMIC_SELFWORK_ENABLED=True):
            response = self._client(self.teacher).get(reverse("registrar:journal_list"))
        self.assertContains(response, STEP)

    def _syllabus_documents(self):
        client = self._client(self.teacher)
        documents = {}
        for name, offering in (("new", self.new_offering), ("old", self.old_offering)):
            response = client.get(reverse("registrar:offering_syllabus_json", args=[offering.id]))
            self.assertEqual(response.status_code, 200)
            documents[name] = {block["key"]: block["body"] for block in response.json()["blocks"]}
        return documents

    def test_syllabus_document_follows_the_current_rule_in_both_semesters(self):
        """Sahib 2026-10-11: sillabus sənədi İRƏLİYƏ baxan sənəddir — baxılan açılışın semestri (2025/2026 də)
        onu dəyişmir: sərbəst iş bloku yoxdur, midterm 30. Jurnalın özü (tab, stepper, bal) isə köhnə
        semestrdə əvvəlki kimidir — bax aşağıdakı ``test_legacy_period_keeps_the_tab_step_panel_and_post``."""
        with bypass_rls():
            syllabus_services.import_migrated_version(
                organization=self.org,
                subject=self.subject,
                approved_at=timezone.now(),
                author=self.teacher,
                section_data=complete_section_data(),
            )
        documents = self._syllabus_documents()
        for name in ("new", "old"):
            self.assertNotIn("selfwork", documents[name])
            self.assertIn("Midterm (aralıq imtahan) 30", documents[name]["assessment"])
            self.assertNotIn("Sərbəst iş", documents[name]["assessment"])
            self.assertTrue(documents[name]["literature"].startswith("Cormen"))
        # RİM açarı yandırılanda sərbəst iş bloku və midterm 20 HƏR iki semestrdə geri qayıdır.
        with override_settings(ACADEMIC_SELFWORK_ENABLED=True):
            documents = self._syllabus_documents()
        for name in ("new", "old"):
            self.assertIn("Birinci sərbəst iş mövzusu", documents[name]["selfwork"])
            self.assertIn("Midterm (aralıq imtahan) 20", documents[name]["assessment"])

    # ── 2025/2026 (köhnə qayda — tarix dəyişmir) ─────────────────────────────
    def test_legacy_period_keeps_the_tab_step_panel_and_post(self):
        response = self._detail(self.old_offering)
        self.assertTrue(response.context["selfwork_active"])
        self.assertContains(response, TAB)
        self.assertContains(response, STEP)
        self.assertContains(self._detail(self.old_offering, "?jt=serbest"), PANEL)
        response = self._add_topic(self.old_offering)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SelfWorkTopic.objects.filter(offering=self.old_offering).exists())

    # ── Tənzimləmə yandırılıb — 2026/2027-də də geri qayıdır ─────────────────
    @override_settings(ACADEMIC_SELFWORK_ENABLED=True)
    def test_toggle_brings_selfwork_back_for_the_new_period(self):
        response = self._detail(self.new_offering)
        self.assertTrue(response.context["selfwork_active"])
        self.assertContains(response, TAB)
        self.assertContains(response, STEP)
        self.assertContains(self._detail(self.new_offering, "?jt=serbest"), PANEL)
        response = self._add_topic(self.new_offering)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SelfWorkTopic.objects.filter(offering=self.new_offering).exists())
