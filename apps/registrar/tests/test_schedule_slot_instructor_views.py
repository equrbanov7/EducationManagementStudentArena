"""Slotun öz müəllimi — göstəriş səthləri (2026-09-25, bölünmüş tədris, ikinci mərhələ).

* iCal (.ics) təsvirində EFFEKTİV müəllim (assistent), jurnal sahibi yox;
* ana səhifənin «Bu gün / növbəti dərslərim» kartında başqasının jurnalındakı slota «Jurnalı aç» keçidi
  YOXDUR (jurnal sahibinindir; giriş qaydası dəyişmir), öz jurnalına isə var — kart sorğu ETMİR;
* müəllimin «Dərs cədvəli» detal modalında override slotun tələbə sayı (əvvəl 0 görünürdü).
"""

from __future__ import annotations

from django.test import RequestFactory
from django.urls import reverse

from apps.organizations.models import Membership
from apps.registrar import ical, page_contexts, schedule
from apps.registrar.models import Enrollment, SlotKind
from apps.registrar.tests.test_schedule_slot_instructor import SlotInstructorBase, User
from core.rls import bypass_rls


class IcsDescriptionTest(SlotInstructorBase):
    code = "siics"

    def test_description_names_the_effective_teacher(self):
        with bypass_rls():
            self._slot(self.offering, weekday=1, start="08:30", end="10:00")
            self._slot(self.offering, weekday=2, kind=SlotKind.SEMINAR, instructor=self.teacher_b)
            slots = schedule.get_group_schedule(organization=self.org, group=self.groups[0], period=self.period)
            with self.assertNumQueries(0):
                payload = ical.build_schedule_ics(slots=slots, period=self.period, calendar_name="231A")
        events = payload.split("BEGIN:VEVENT")[1:]
        self.assertEqual(len(events), 2)
        self.assertIn("DESCRIPTION:231A · Aytən Əliyeva", events[0])  # mühazirə — jurnal sahibi
        self.assertIn("DESCRIPTION:231A · Bəhruz Həsənov", events[1])  # seminar — assistent
        self.assertNotIn("Aytən", events[1])


class DashboardJournalLinkTest(SlotInstructorBase):
    code = "sidash"

    def _card(self, slots, **kwargs):
        from apps.accounts.views.profile._sections import dashboard_lessons

        return dashboard_lessons.build(
            slots, period=self.period, today=self.today, now=None, with_group=True, journal_links=True, **kwargs
        )

    def test_assistant_gets_no_link_to_the_owners_journal(self):
        today = self.today.isoweekday()
        with bypass_rls():
            self._slot(self.offering, weekday=today, kind=SlotKind.SEMINAR, instructor=self.teacher_b)
            self._slot(self.offering_b, weekday=today, start="13:35", end="15:05")
            slots = schedule.get_teacher_schedule(organization=self.org, teacher=self.teacher_b, period=self.period)
        with self.assertNumQueries(0):  # kart sorğu etmir — dashboard büdcəsi dəyişmir
            card = self._card(slots)
        own = reverse("registrar:journal_detail", args=[self.offering_b.pk])
        self.assertEqual([row["title"] for row in card["rows"]], ["Verilənlər bazası", "Şəbəkələr"])
        self.assertEqual([row.get("url") for row in card["rows"]], [None, own])

    def test_journal_owner_keeps_the_link(self):
        today = self.today.isoweekday()
        with bypass_rls():
            self._slot(self.offering, weekday=today, kind=SlotKind.SEMINAR, instructor=self.teacher_b)
            self._slot(self.offering, weekday=today, start="08:30", end="10:00")
            slots = schedule.get_group_schedule(organization=self.org, group=self.groups[0], period=self.period)
        journal = reverse("registrar:journal_detail", args=[self.offering.pk])
        as_owner = self._card(slots, viewer_id=self.teacher_a.pk)
        as_assistant = self._card(slots, viewer_id=self.teacher_b.pk)
        self.assertEqual([row.get("url") for row in as_owner["rows"]], [journal, journal])
        self.assertEqual([row.get("url") for row in as_assistant["rows"]], [journal, None])


class TeacherModalStudentCountTest(SlotInstructorBase):
    code = "sicnt"

    def test_override_slot_shows_the_groups_student_count(self):
        with bypass_rls():
            student = User.objects.create_user("sicnt_student", "sicnt_s@qku.edu.az", "pw")
            Membership.objects.create(
                user=student,
                organization=self.org,
                role=self.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            Enrollment.objects.create(organization=self.org, student=student, offering=self.offering)
            seminar = self._slot(self.offering, weekday=2, kind=SlotKind.SEMINAR, instructor=self.teacher_b)
            request = RequestFactory().get("/")
            request.user = self.teacher_b
            context = page_contexts.schedule_context(request, self.org)
        items = [
            item
            for row in context["matrix"]["rows"]
            for cell in row["cells"]
            for item in cell["items"]
            if item["slot"].pk == seminar.pk
        ]
        self.assertEqual(context["role"], "teacher")
        self.assertEqual([item["student_count"] for item in items], [1])  # A-nın jurnalının qrupu — əvvəl 0
