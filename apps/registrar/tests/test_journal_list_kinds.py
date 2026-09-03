"""Jurnal siyahısında dərs tipi sütunu — slot + dərs (Lesson.kind) birləşməsi.

Köçürülmüş (legacy) açılışların cədvəl slotu yoxdur — tip yalnız ``Lesson.kind``-dadır.
Siyahı səhifəsi əvvəllər yalnız ``ScheduleSlot``-dan oxuyurdu → sütun «—», filtr
çipləri işləmirdi. İndi tip yığımı slot və dərs tiplərinin BİRLƏŞMƏSİDİR.
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import Lesson, LessonKind, ScheduleSlot, SlotKind, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class JournalListKindTest(TestCase):
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
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="jk-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.teacher = User.objects.create_user("jk_teacher", "jk_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            # Legacy ssenarisi: slotu OLMAYAN, yalnız dərsləri olan açılış.
            cls.subject_legacy = Subject.objects.create(organization=cls.org, code="LG101", name="Legacy fənn")
            cls.off_lessons = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject_legacy, period=cls.period, group=cls.group
            )
            cls.off_lessons.instructor = cls.teacher
            cls.off_lessons.save(update_fields=["instructor"])
            for day, kind in ((1, LessonKind.SEMINAR), (2, LessonKind.LECTURE), (8, LessonKind.SEMINAR)):
                Lesson.objects.create(
                    organization=cls.org,
                    offering=cls.off_lessons,
                    date=datetime.date(2024, 10, day),
                    kind=kind,
                )
            # Qarışıq ssenari: HƏM slot (mühazirə), HƏM dərslər (mühazirə + seminar).
            cls.subject_mixed = Subject.objects.create(organization=cls.org, code="MX102", name="Qarışıq fənn")
            cls.off_mixed = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject_mixed, period=cls.period, group=cls.group
            )
            cls.off_mixed.instructor = cls.teacher
            cls.off_mixed.save(update_fields=["instructor"])
            ScheduleSlot.objects.create(
                organization=cls.org,
                offering=cls.off_mixed,
                weekday=1,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(10, 20),
                kind=SlotKind.LECTURE,
            )
            for day, kind in ((3, LessonKind.LECTURE), (4, LessonKind.SEMINAR)):
                Lesson.objects.create(
                    organization=cls.org,
                    offering=cls.off_mixed,
                    date=datetime.date(2024, 10, day),
                    kind=kind,
                )

    def _get(self, params=None):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client.get(reverse("registrar:journal_list"), {"year": "2024/2025", **(params or {})})

    def _offering_by_code(self, resp, code):
        return next((o for o in resp.context["offerings"] if o.subject.code == code), None)

    def test_lesson_only_offering_gets_kind_label(self):
        # (a) Slotu olmayan açılışda tip Lesson.kind-dan dolur; sıra SlotKind.choices üzrə.
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        off = self._offering_by_code(resp, "LG101")
        self.assertIsNotNone(off)
        self.assertEqual(off.slot_kinds, ["lecture", "seminar"])
        expected = f"{SlotKind.LECTURE.label} · {SlotKind.SEMINAR.label}"
        self.assertEqual(off.kind_label, expected)

    def test_kind_filter_matches_lesson_derived_kinds(self):
        # (b) Filtr çipi dərs-əsaslı tipləri də tutur.
        resp = self._get({"kind": "seminar"})
        self.assertIsNotNone(self._offering_by_code(resp, "LG101"))
        self.assertIsNotNone(self._offering_by_code(resp, "MX102"))
        # Lab dərsi heç birində yoxdur → hər ikisi süzülür.
        resp_lab = self._get({"kind": "lab"})
        self.assertIsNone(self._offering_by_code(resp_lab, "LG101"))
        self.assertIsNone(self._offering_by_code(resp_lab, "MX102"))

    def test_slot_and_lesson_union_is_deduplicated(self):
        # (c) Slot (mühazirə) + dərslər (mühazirə, seminar) → təkrarsız birləşmə.
        resp = self._get()
        off = self._offering_by_code(resp, "MX102")
        self.assertIsNotNone(off)
        self.assertEqual(off.slot_kinds, ["lecture", "seminar"])
        self.assertEqual(off.kind_label.count(str(SlotKind.LECTURE.label)), 1)
