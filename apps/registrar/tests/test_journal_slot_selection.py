"""Jurnalda təkrar dərs seçimi yalnız birmənalı və görünən sütunu açır."""

import datetime as dt
from urllib.parse import urlsplit

from django.urls import reverse
from django.utils import timezone

from lxml import html

from apps.registrar.journal_slot_selection import slot_choice_message
from apps.registrar.models import JournalShare, Lesson, LessonMark
from apps.registrar.tests.test_journal_shares_2026_10_26 import _add_teacher
from apps.registrar.tests.test_lesson_modal_backdate_patok_2026_11_15 import TIME, _Base, _prod_settings
from core.rls import bypass_rls


class JournalSlotSelectionTest(_Base):
    prefix = "slotselection"

    def test_rendered_column_and_attendance_follow_each_selected_kind(self):
        lessons = {kind: self.lesson(kind=kind) for kind in ("lecture", "seminar", "lab")}
        for lesson in lessons.values():
            self.autosave(lesson, self.enrollment, status="absent")
        for kind, lesson in lessons.items():
            with self.subTest(kind=kind), _prod_settings():
                response = self.add(kind=kind, follow=False)
                target = urlsplit(response["Location"])
                self.assertEqual(target.fragment, f"jd-lesson-{lesson.pk}")
                page = self.client_for(self.teacher).get(target.path, target.query)
                document = html.fromstring(page.content)
                column = document.get_element_by_id(target.fragment)
                self.assertEqual(column.xpath(".//*[@data-lesson-kind]/@data-lesson-kind"), [kind])
                lesson_id = target.fragment.removeprefix("jd-lesson-")
                field = f"att__{lesson_id}__{self.enrollment.pk}"
                self.assertEqual(len(document.xpath("//input[@name=$name]", name=field)), 1)
                result = self.client_for(self.teacher).post(self.url(), {field: "present", "autosave": "1"})
                self.assertEqual(result.json()["written"], 1)
                with bypass_rls():
                    present = LessonMark.objects.filter(enrollment=self.enrollment, status="present")
                    self.assertEqual(list(present.values_list("lesson_id", flat=True)), [lesson.pk])
                self.autosave(lesson, self.enrollment, status="absent")
        self.assertEqual(len(self.lessons()), 3)

    def test_wrong_kind_in_prefilled_slot_keeps_marks_and_returns_to_journal(self):
        self.slot(kind="lecture")
        slot = self.slot(kind="lab")
        lecture = self.lesson()
        self.autosave(lecture, self.enrollment, status="absent")
        self.assertEqual(self.prefill(dt.time(9, 0))["slot_id"], str(slot.pk))
        with _prod_settings():
            resp = self.add(kind="lab", slot_id=str(slot.pk))
        self.assertEqual(resp.redirect_chain, [(self.url(), 302)])
        self.assertIn(slot_choice_message(), self.messages(resp))
        with bypass_rls():
            self.assertEqual(LessonMark.objects.get(lesson=lecture).status, "absent")
        self.assertEqual(len(self.lessons()), 1)

    def test_seminar_at_lab_time_does_not_hide_the_scheduled_lab(self):
        lab_slot = self.slot(kind="lab")
        self.slot(kind="lecture", start=(13, 35), end=(15, 5))
        self.lesson(kind="seminar")
        prefill = self.prefill(dt.time(9, 0))
        self.assertEqual((prefill["kind"], prefill["slot_id"]), ("lab", str(lab_slot.pk)))
        with _prod_settings():
            response = self.add(kind="lab", slot_id=prefill["slot_id"], follow=False)
        self.assertEqual(response["Location"], self.url())

    def test_identical_timetable_slots_do_not_claim_the_same_historical_lesson(self):
        slots = [self.slot(kind="lab"), self.slot(kind="lab")]
        self.lesson(kind="lab")
        with _prod_settings():
            for slot in slots:
                with self.subTest(slot=slot.pk):
                    response = self.add(kind="lab", slot_id=str(slot.pk), follow=False)
                    self.assertEqual(response["Location"], self.url())
        self.assertEqual(len(self.lessons()), 1)

    def test_two_matching_columns_require_a_choice(self):
        self.lesson(kind="lab")
        self.lesson(kind="lab")
        with _prod_settings():
            resp = self.add(kind="lab")
        self.assertEqual(resp.redirect_chain, [(self.url(), 302)])
        self.assertIn(slot_choice_message(), self.messages(resp))
        self.assertEqual(len(self.lessons()), 2)

    def test_scoped_teacher_opens_own_column_and_cannot_be_sent_to_other_teacher(self):
        own = self.lesson(kind="seminar")
        other = self.lesson(kind="seminar")
        with bypass_rls():
            assistant = _add_teacher(self, "slotselection_assistant")
            Lesson.objects.filter(pk=other.pk).update(instructor=assistant)
            share = JournalShare.objects.create(
                organization=self.org, offering=self.offering, teacher=assistant, kinds=["seminar"]
            )
            share.enrollments.add(self.enrollment)
        params = {
            "action": "add_lesson",
            "lesson_date": timezone.localdate(),
            "lesson_time": TIME,
            "lesson_kind": "seminar",
        }
        with _prod_settings():
            client = self.client_for(assistant)
            self.assertEqual(client.post(self.url(), params)["Location"], f"{self.url()}#jd-lesson-{other.pk}")
            with bypass_rls():
                Lesson.objects.filter(pk=other.pk).delete()
            self.assertEqual(client.post(self.url(), params)["Location"], self.url())
        self.assertEqual(self.lessons(), [own])

    def test_kind_only_share_prefills_the_teacher_who_will_open_the_lesson(self):
        self.slot(kind="seminar")
        with bypass_rls():
            assistant = _add_teacher(self, "slotselection_kind_teacher")
            JournalShare.objects.create(
                organization=self.org, offering=self.offering, teacher=assistant, kinds=["seminar"]
            )
        with _prod_settings():
            prefill = self.client_for(assistant).get(self.url()).context["lesson_prefill"]
        self.assertEqual((prefill["kind"], prefill["instructor"]), ("seminar", str(assistant.pk)))

    def test_subgroup_and_end_time_must_match(self):
        earlier = self.lesson(kind="lab", end="09:15")
        other_group = self.lesson(kind="lab")
        expected = self.lesson(kind="lab")
        with bypass_rls():
            type(self.enrollment).objects.filter(pk=self.enrollment.pk).update(lab_group=2)
            Lesson.objects.filter(pk__in=[earlier.pk, expected.pk]).update(lab_group=2)
            Lesson.objects.filter(pk=other_group.pk).update(lab_group=1)
        with _prod_settings():
            resp = self.add(kind="lab", lesson_lab_group="2", follow=False)
        self.assertEqual(resp["Location"], f"{self.url()}#jd-lesson-{expected.pk}")

    def test_validation_error_on_occupied_day_has_no_column_anchor(self):
        old = timezone.localdate() - dt.timedelta(days=120)
        self.lesson(day=old)
        with _prod_settings():
            resp = self.add(day=old)
        self.assertEqual(resp.redirect_chain, [(self.url(), 302)])
        self.assertNotIn(slot_choice_message(), self.messages(resp))
        self.assertTrue(any("semestrin başlanğıcından" in message for message in self.messages(resp)))

    def test_activation_strip_and_action_never_link_a_different_kind_or_an_ambiguous_column(self):
        slot = self.slot(kind="lab")
        self.lesson(kind="lecture")
        activate = reverse("registrar:journal_activate_slot", args=[self.offering.pk, slot.pk])
        client = self.client_for(self.teacher)
        with _prod_settings(JOURNAL_LESSON_ACTIVATION=True):
            for case, expected in (("wrong kind", None), ("unique lab", True), ("two labs", None)):
                if case != "wrong kind":
                    lab = self.lesson(kind="lab")
                with self.subTest(case=case):
                    item = client.get(self.url()).context["today_strip"]["items"][0]
                    self.assertEqual(item["lesson_id"], str(lab.pk) if expected else "")
                    response = client.post(activate)
                    self.assertEqual(
                        response["Location"], f"{self.url()}#jd-lesson-{lab.pk}" if expected else self.url()
                    )
