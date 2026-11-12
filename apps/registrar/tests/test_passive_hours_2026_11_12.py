"""«Passiv saat» — intensiv tədrisin auditoriyadan kənar saatları (sahib 2026-11-12, MR-000303).

İntensiv kursda həmişə açıqdır; adi jurnalda kafedra müdiri / RİM açarı ilə. Dərs deyil: «Keçirilmiş X / Y»,
davamiyyət, dərs saatı həddi dəyişmir; başlıqda ayrıca «Passiv saat: N saat».
"""

from __future__ import annotations

import datetime

from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.registrar import journal_extras, passive_hours
from apps.registrar.models import CourseOffering, Lesson, PassiveHour
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.rls import bypass_rls

D = datetime.date


class PassiveBase(SubgroupFixture, TestCase):
    PREFIX = "pasv"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])
            cls.history.chair_unit = cls.chair
            cls.history.save(update_fields=["chair_unit"])
            cls.offering = cls.history_g1
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            Lesson.objects.create(
                organization=cls.org, offering=cls.offering, date=D(2025, 10, 7), kind="lecture", hours=2
            )
            cls.chair_head = cls._member(f"{cls.PREFIX}_head", cls.org.roles.get(name="chair_head"), cls.chair)

    def enable(self, value=True):
        with bypass_rls():
            CourseOffering.objects.filter(pk=self.offering.pk).update(passive_hours_enabled=value)

    def fresh(self):
        with bypass_rls():
            return CourseOffering.objects.select_related("organization", "period", "subject").get(pk=self.offering.pk)

    def detail(self, user):
        return self.client_for(user).get(reverse("registrar:journal_detail", args=[self.offering.pk]))


class RuleTest(PassiveBase):
    def test_regular_offering_disabled_by_default(self):
        offering = self.fresh()
        self.assertFalse(passive_hours.enabled(offering))
        with bypass_rls(), self.assertRaises(passive_hours.PassiveHourError):
            passive_hours.add(offering=offering, user=self.teacher, day=D(2025, 10, 9), hours=2)

    def test_intensive_always_enabled_without_flag(self):
        offering = self.fresh()
        offering.course_format = "intensive"
        self.assertTrue(passive_hours.enabled(offering))
        self.assertFalse(passive_hours.can_switch(self.owner, offering))

    def test_validation(self):
        self.enable()
        offering = self.fresh()
        today = D(2025, 11, 1)
        for kwargs, code in (
            ({"day": "", "hours": 2}, "date"),
            ({"day": "2025-08-31", "hours": 2}, "date"),  # semestrdən əvvəl
            ({"day": "2025-11-02", "hours": 2}, "date"),  # gələcək
            ({"day": "2025-10-09", "hours": 0}, "hours"),
            ({"day": "2025-10-09", "hours": 9}, "hours"),
            ({"day": "2025-10-09", "hours": "x"}, "hours"),
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(passive_hours.PassiveHourError) as ctx:
                passive_hours.clean(offering, note="", today=today, **kwargs)
            self.assertEqual(ctx.exception.code, code)
        day, hours, note = passive_hours.clean(offering, day="2025-10-09", hours="3", note="  mövzu   1 ", today=today)
        self.assertEqual((day, hours, note), (D(2025, 10, 9), 3, "mövzu 1"))

    def test_intensive_upper_bound_is_ends_on(self):
        offering = self.fresh()
        offering.course_format = "intensive"
        offering.ends_on = D(2025, 10, 20)
        with self.assertRaises(passive_hours.PassiveHourError):
            passive_hours.clean(offering, day="2025-10-21", hours=1, note="", today=D(2025, 11, 1))

    def test_passive_hours_do_not_change_held_total(self):
        self.enable()
        offering = self.fresh()
        before = journal_extras.journal_teaching_summary(offering)
        with bypass_rls():
            passive_hours.add(offering=offering, user=self.teacher, day=D(2025, 10, 9), hours=4, note="müstəqil iş")
            self.assertEqual(passive_hours.total_hours(offering), 4)
            self.assertEqual(Lesson.objects.filter(offering=offering).count(), 1)
        after = journal_extras.journal_teaching_summary(offering)
        self.assertEqual(before["held_total"], after["held_total"])
        self.assertEqual(before["scheduled_total"], after["scheduled_total"])


class PageTest(PassiveBase):
    def test_teacher_sees_nothing_when_disabled(self):
        response = self.detail(self.teacher)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["passive_hours"])
        self.assertNotContains(response, "jd2-passive")

    def test_chair_head_switch_then_teacher_adds_and_deletes(self):
        switch_url = reverse("registrar:journal_passive_hours_switch", args=[self.offering.pk])
        response = self.detail(self.chair_head)
        self.assertContains(response, "jd2-passive-switch__btn")
        self.assertEqual(self.client_for(self.teacher).post(switch_url, {"on": "1"}).status_code, 404)
        self.client_for(self.chair_head).post(switch_url, {"on": "1"})
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).passive_hours_enabled)
            self.assertTrue(
                AuditLog.objects.filter(
                    object_id=str(self.offering.pk), new_values__passive_hours_enabled=True
                ).exists()
            )

        page = self.detail(self.teacher)
        self.assertTrue(page.context["passive_hours"]["can_edit"])
        self.assertContains(page, "registrar/css/journal_passive_hours.css")
        self.assertContains(page, "jd2-passive__form")
        self.assertNotContains(page, "jd2-passive-switch__btn")

        client = self.client_for(self.teacher)
        add_url = reverse("registrar:journal_passive_hours_add", args=[self.offering.pk])
        response = client.post(add_url, {"date": "2025-10-09", "hours": "3", "note": "Mənbə təhlili"})
        self.assertRedirects(
            response, reverse("registrar:journal_detail", args=[self.offering.pk]), fetch_redirect_response=False
        )
        with bypass_rls():
            row = PassiveHour.objects.get(offering=self.offering)
        self.assertEqual(
            (row.date, row.hours, row.note, row.created_by_id), (D(2025, 10, 9), 3, "Mənbə təhlili", self.teacher.pk)
        )
        page = self.detail(self.teacher)
        self.assertEqual(page.context["passive_hours"]["total"], 3)
        self.assertContains(page, "Mənbə təhlili")

        client.post(add_url, {"date": "2025-10-09", "hours": "99"})
        with bypass_rls():
            self.assertEqual(PassiveHour.objects.filter(offering=self.offering).count(), 1)

        client.post(reverse("registrar:journal_passive_hours_delete", args=[self.offering.pk]), {"entry": str(row.pk)})
        with bypass_rls():
            self.assertFalse(PassiveHour.objects.filter(offering=self.offering).exists())
            self.assertEqual(
                AuditLog.objects.filter(resource_type="registrar.PassiveHour", resource_id=str(row.pk)).count(), 2
            )

    def test_outsider_cannot_write(self):
        self.enable()
        url = reverse("registrar:journal_passive_hours_add", args=[self.offering.pk])
        self.assertEqual(self.client_for(self.plain).post(url, {"date": "2025-10-09", "hours": "2"}).status_code, 404)
        self.assertEqual(self.client_for(self.teacher).get(url).status_code, 405)
        with bypass_rls():
            self.assertFalse(PassiveHour.objects.exists())

    def test_disabled_flag_blocks_write(self):
        url = reverse("registrar:journal_passive_hours_add", args=[self.offering.pk])
        self.assertEqual(self.client_for(self.teacher).post(url, {"date": "2025-10-09", "hours": "2"}).status_code, 404)
