"""Jurnalda DƏRS TİPİ süzgəci (sahib tələbi 2026-09-06).

Siyahıdakı «Mühazirə / Seminar / Laboratoriya» pilləsi jurnalın İÇİNƏ də keçir:
əvvəl bir açılışın bütün dərsləri qarışıq göstərilirdi (tələbə öz kabinetində
onsuz da ayrı görür), siyahıda isə süzgəc seçilsə də sətir «Mühazirə · Seminar»
yazırdı — yəni süzgəcin nə etdiyi görünmürdü.
"""

from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook
from apps.registrar import journal_window as jw
from apps.registrar.models import Lesson, Subject
from apps.registrar.page_contexts import attach_kind_labels
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class LessonKindFilterTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("jk_owner", "jk_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JK Univ",
                slug="jk-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.teacher = User.objects.create_user("jk_teacher", "jk_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
        cls.group = OrgUnit.objects.create(organization=cls.org, name="JK-1", slug="jk-1", unit_type=OrgUnitType.GROUP)
        cls.period = AcademicPeriod.objects.create(
            organization=cls.org,
            name="Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2025/2026",
            start_date="2025-09-01",
            end_date="2026-01-15",
            is_current=True,
        )
        cls.subject = Subject.objects.create(organization=cls.org, code="JK101", name="Test fənni")
        from apps.registrar import services

        cls.offering = services.get_or_create_offering(
            organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
        )
        cls.offering.instructor = cls.teacher
        cls.offering.save(update_fields=["instructor"])
        for index, kind in enumerate(("lecture", "lecture", "seminar")):
            Lesson.objects.create(
                organization=cls.org,
                offering=cls.offering,
                date=date(2025, 9, 10 + index),
                kind=kind,
                hours=2,
            )

    def test_the_grid_shows_only_the_requested_kind(self):
        full = gradebook.get_offering_journal(offering=self.offering)
        lecture = gradebook.get_offering_journal(offering=self.offering, lesson_kind="lecture")
        seminar = gradebook.get_offering_journal(offering=self.offering, lesson_kind="seminar")
        self.assertEqual(len(full["lessons"]), 3)
        self.assertEqual(len(lecture["lessons"]), 2)
        self.assertEqual(len(seminar["lessons"]), 1)

    def test_absence_totals_ignore_the_kind_filter(self):
        """Süzgəc YALNIZ sütunlara aiddir — qayıb/giriş rəqəmləri tam dəst üzrədir."""
        full = gradebook.get_offering_journal(offering=self.offering)
        seminar = gradebook.get_offering_journal(offering=self.offering, lesson_kind="seminar")
        self.assertEqual(
            [row["absence_hours"] for row in full["rows"]],
            [row["absence_hours"] for row in seminar["rows"]],
        )

    def test_the_list_label_follows_the_selected_kind(self):
        offerings = [self.offering]
        attach_kind_labels(offerings)
        self.assertIn("·", offerings[0].kind_label)  # hər iki tip
        attach_kind_labels(offerings, "seminar")
        self.assertNotIn("·", offerings[0].kind_label)
        self.assertEqual(offerings[0].slot_kinds, ["lecture", "seminar"])

    def test_kind_tabs_appear_only_when_several_kinds_exist(self):
        tabs = jw.kind_tabs(self.offering, "seminar")
        self.assertEqual([tab["value"] for tab in tabs], ["", "lecture", "seminar"])
        self.assertTrue(next(tab for tab in tabs if tab["value"] == "seminar")["active"])
        Lesson.objects.filter(offering=self.offering, kind="seminar").delete()
        self.assertEqual(jw.kind_tabs(self.offering, ""), [])


class SelectedFilterLabelTest(TestCase):
    """Seçilmiş kafedra/müəllim adı qutuda GÖRÜNMƏLİDİR.

    Etiket əvvəl yalnız açılışların qrup-yolundan qurulan siyahıdan axtarılırdı;
    kafedra orada olmayanda («qruplar ixtisas altındadır») seçim edilsə də qutu
    boş qalırdı — istifadəçi «seçirəm, gəlmir» deyirdi.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sf_owner", "sf_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SF Univ",
                slug="sf-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
        cls.chair = OrgUnit.objects.create(
            organization=cls.org, name="Mexanika və riyaziyyat", slug="sf-chair", unit_type=OrgUnitType.CHAIR
        )

    def test_a_unit_outside_the_dropdown_still_resolves_its_name(self):
        from apps.registrar import journal_list_query as jlq

        self.assertEqual(jlq.label_for_selection("unit", str(self.chair.pk)), "Mexanika və riyaziyyat")

    def test_a_broken_id_is_silently_empty(self):
        from apps.registrar import journal_list_query as jlq

        self.assertEqual(jlq.label_for_selection("unit", "not-a-uuid"), "")
        self.assertEqual(jlq.label_for_selection("unit", ""), "")

    def test_a_teacher_resolves_to_the_full_name(self):
        from apps.registrar import journal_list_query as jlq

        teacher = User.objects.create_user("sf_teacher", "sf_teacher@qku.edu.az", "pw")
        teacher.first_name, teacher.last_name = "Adıgözəl", "Dosiyev"
        teacher.save(update_fields=["first_name", "last_name"])
        self.assertEqual(jlq.label_for_selection("teacher", str(teacher.pk)), "Adıgözəl Dosiyev")
