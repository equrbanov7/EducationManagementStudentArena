"""Sahib 2026-10-10: jurnalda «Aktivləşdir» yoxdur — müəllim «Yeni dərs» basır, modal ƏVVƏLCƏDƏN DOLU açılır.

Nəyi qoruyur
------------
* bayraq söndürülü (defolt): zolaqda aktivləşdirmə forması/ünvanı yoxdur, slot kartında «Yeni dərs»
  (``data-jd-prefill-slot``), aktivləşdirmə POST-u 404, mətnlər «Aktivləşdir»-ə yönləndirmir;
  yandırılı (``JOURNAL_LESSON_ACTIVATION=True``) — köhnə davranış (geri dönüş yolu);
* doldurmanın slot seçimi: indi gedən → 30 dəq. içində bitən → növbəti → ən son keçmiş; slot yoxdursa
  tip kilidi → son dərs → tədris planı; dərs saatı son dərsdən yalnız cədvəlsiz açılışda;
* slot yolu (gizli ``slot_id``): təşkilatın öz zəng saatı qəbul olunur, səbəb tələb olunmur; yad /
  parklanmış / başqa günün slotu rədd olunur; saat dəyişibsə əl ilə dərs qaydaları;
* redaktə: slot dərsinin öz zəng saatı silinmir; redaktə çipi üçün dərs müəllimlərinin adları adadadır;
* sorğu büdcəsi: grid tabında dərs sətirləri zolaqla paylaşılır (≤ 2 əlavə sorğu).
"""

from __future__ import annotations

import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.exams.models import ExamRoom
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import (
    journal_activation,
    journal_extras,
    journal_lesson_prefill,
    lesson_rooms,
    schedule,
    services,
)
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonKind, ScheduleSlot, SlotKind, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

TOPICS = [
    {"title": "Giriş", "kinds": ["lecture", "seminar"]},
    {"title": "SQL", "kinds": ["seminar", "lab"]},
    {"title": "İndekslər", "kinds": ["lecture", "lab"]},
]


def _t(text):
    return datetime.time.fromisoformat(text)


def _at(day, text):
    return timezone.make_aware(datetime.datetime.combine(day, _t(text)))


class PickSlotTest(SimpleTestCase):
    """Slot seçimi — bazasız (``ScheduleSlot`` obyektləri yaddaşda)."""

    day = datetime.date(2026, 10, 12)

    def setUp(self):
        self.morning = ScheduleSlot(start_time=_t("08:30"), end_time=_t("10:00"))
        self.seminar = ScheduleSlot(start_time=_t("10:10"), end_time=_t("11:40"))
        self.lab = ScheduleSlot(start_time=_t("12:00"), end_time=_t("13:30"))
        self.slots = [self.morning, self.seminar, self.lab]

    def pick(self, clock, slots=None):
        return journal_lesson_prefill.pick_slot(self.slots if slots is None else slots, _at(self.day, clock))

    def test_running_slot_wins(self):
        self.assertIs(self.pick("10:30"), self.seminar)
        self.assertIs(self.pick("12:00"), self.lab)

    def test_slot_that_ended_within_grace_beats_the_next_one(self):
        self.assertIs(self.pick("11:50"), self.seminar)  # 10 dəq. əvvəl bitib, laboratoriya 12:00-da
        self.assertIs(self.pick("10:05"), self.morning)  # növbəti 10:10-da olsa da

    def test_next_upcoming_after_grace(self):
        self.assertIs(self.pick("07:00"), self.morning)
        only_lab = [self.morning, self.lab]
        self.assertIs(self.pick("10:45", only_lab), self.lab)  # səhər dərsi 45 dəq. əvvəl bitib

    def test_latest_past_when_nothing_is_left(self):
        self.assertIs(self.pick("18:00"), self.lab)

    def test_no_slots(self):
        self.assertIsNone(self.pick("10:30", []))


class TopicsCoveredTest(SimpleTestCase):
    def test_marks_use_every_lesson_not_only_the_window(self):
        older = Lesson(topic="Giriş", kind=LessonKind.LECTURE, date=datetime.date(2026, 9, 14))
        newer = Lesson(topic="Giriş", kind=LessonKind.SEMINAR, date=datetime.date(2026, 9, 21))
        rows = [{"title": "Giriş", "kinds": ["lecture"], "covered": False, "date": None}, {"title": "SQL", "kinds": []}]
        marked = journal_lesson_prefill.topics_covered_by(rows, [newer, older])  # ən yenisi birinci
        self.assertTrue(marked[0]["covered"])
        self.assertEqual(marked[0]["date"], datetime.date(2026, 9, 21))
        self.assertEqual(marked[0]["covered_kinds"], ["lecture", "seminar"])
        self.assertEqual(marked[0]["kinds"], ["lecture"])
        self.assertFalse(marked[1]["covered"])


class LessonPrefillBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        monday = cls.today - datetime.timedelta(days=cls.today.weekday())
        cls.owner = User.objects.create_user("lp_owner", "lp_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="LP Univ",
                slug="lp-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="lp-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Cari semestr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=monday - datetime.timedelta(days=14),
                end_date=cls.today + datetime.timedelta(days=90),
                is_current=True,
            )
            cls.parity = schedule.week_parity(cls.period, monday)
            cls.teacher = User.objects.create_user(
                "lp_teacher", "lp_teacher@qku.edu.az", "pw", first_name="Leyla", last_name="Quliyeva"
            )
            cls.assistant = User.objects.create_user(
                "lp_assistant", "lp_assistant@qku.edu.az", "pw", first_name="Bəhruz", last_name="Həsənov"
            )
            cls.student = User.objects.create_user("lp_student", "lp_student@qku.edu.az", "pw")
            for user in (cls.teacher, cls.assistant):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name="teacher"),
                    is_primary=True,
                    is_active=True,
                )
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )

            def offering(code, name):
                subject = Subject.objects.create(organization=cls.org, code=code, name=name)
                item = services.get_or_create_offering(
                    organization=cls.org, subject=subject, period=cls.period, group=cls.group
                )
                item.instructor = cls.teacher
                item.lesson_hours = 60
                item.save(update_fields=["instructor", "lesson_hours"])
                Enrollment.objects.create(organization=cls.org, student=cls.student, offering=item)
                return item

            cls.offering = offering("LP101", "Verilənlər bazası")
            cls.plain = offering("LP102", "Şəbəkələr")  # cədvəlsiz
            cls.foreign = offering("LP103", "Alqoritmlər")  # başqa fənn (yad slot üçün)
            cls.room = ExamRoom.objects.create(organization=cls.org, name="305", code="A305", building="A", capacity=30)
            weekday = cls.today.isoweekday()

            def slot(owner_offering=None, **kwargs):
                data = {
                    "organization": cls.org,
                    "offering": owner_offering or cls.offering,
                    "weekday": weekday,
                    "room": "",
                    "kind": SlotKind.LECTURE,
                }
                data.update(kwargs)
                return ScheduleSlot.objects.create(**data)

            cls.seminar = slot(
                start_time=_t("10:10"), end_time=_t("11:40"), kind=SlotKind.SEMINAR, room="305", week_type=cls.parity
            )
            # Təşkilatın öz zəng saatı (standart siyahıda YOX) + slotun öz müəllimi (bölünmüş tədris).
            cls.lab = slot(start_time=_t("12:00"), end_time=_t("13:30"), kind=SlotKind.LAB, instructor=cls.assistant)
            cls.other_day = slot(weekday=weekday % 7 + 1, start_time=_t("08:30"), end_time=_t("10:00"))
            cls.parked = slot(start_time=_t("15:15"), end_time=_t("16:45"), is_parked=True)
            cls.foreign_slot = slot(cls.foreign, start_time=_t("13:35"), end_time=_t("15:05"))

    # ── köməkçilər ───────────────────────────────────────────────────────────

    def _client(self, user=None):
        client = Client()
        client.force_login(user or self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _fresh(self, offering=None):
        """Memo-suz təzə obyekt (``lesson_rows``/``offering_slots`` obyektə yapışır)."""
        with bypass_rls():
            return CourseOffering.objects.select_related("period", "organization").get(
                pk=(offering or self.offering).pk
            )

    def _context(self, offering, **extra):
        with bypass_rls():
            context = {
                "can_edit": True,
                "active_tab": "grid",
                "topic_choices_meta": [dict(row) for row in TOPICS],
                "lesson_room_memory": lesson_rooms.remembered_rooms(offering),
                "locked_lesson_kind": journal_extras.locked_lesson_kind(offering),
            }
        context.update(extra)
        return context

    def _prefill(self, clock, offering=None, **extra):
        offering = self._fresh(offering)
        with bypass_rls():
            return journal_lesson_prefill.build(offering, self._context(offering, **extra), now=_at(self.today, clock))

    def _lesson(self, offering=None, days_ago=0, **kwargs):
        data = {
            "organization": self.org,
            "offering": offering or self.offering,
            "date": self.today - datetime.timedelta(days=days_ago),
            "kind": LessonKind.LECTURE,
        }
        data.update(kwargs)
        with bypass_rls():
            return Lesson.objects.create(**data)

    def _lessons(self, offering=None):
        with bypass_rls():
            return list(Lesson.objects.filter(offering=offering or self.offering).order_by("start_time"))

    def _journal(self, **params):
        return self._client().get(reverse("registrar:journal_detail", args=[self.offering.id]), params)

    def _add(self, offering=None, **overrides):
        payload = {
            "action": "add_lesson",
            "lesson_date": self.today.isoformat(),
            "lesson_kind": LessonKind.LAB,
            "lesson_hours": "2",
            "lesson_time": "12:00|13:30",
            "slot_id": str(self.lab.pk),
        }
        payload.update(overrides)
        url = reverse("registrar:journal_detail", args=[(offering or self.offering).id])
        return self._client().post(url, payload, follow=True)


class PrefillBuildTest(LessonPrefillBase):
    def test_running_slot_fills_every_field_from_the_timetable(self):
        data = self._prefill("10:30")
        self.assertEqual(data["source"], "slot")
        self.assertEqual(data["slot_id"], str(self.seminar.pk))
        self.assertEqual(data["date"], self.today.isoformat())
        self.assertEqual(data["kind"], LessonKind.SEMINAR)
        self.assertEqual(data["time"], "10:10|11:40")
        self.assertEqual(data["hours"], 2)
        self.assertEqual(data["room"], str(self.room.pk))  # «305» reyestrdə tapılır
        self.assertEqual(data["instructor"], str(self.teacher.pk))
        self.assertEqual(data["topic"], "Giriş")
        self.assertTrue(data["label"].startswith("10:10–11:40 · "))
        self.assertEqual(data["parity"], self.parity)

    def test_slot_teacher_and_own_bell_time(self):
        data = self._prefill("12:20")
        self.assertEqual(data["slot_id"], str(self.lab.pk))
        self.assertEqual(data["time"], "12:00|13:30")
        self.assertEqual(data["instructor"], str(self.assistant.pk))
        self.assertEqual(data["topic"], "SQL")  # laboratoriya üçün ilk mövzu
        # Slotun öz müəllimi seçicinin namizəd siyahısında olmaya bilər — çip adı doldurmadan gəlir (sahib yox).
        self.assertEqual(data["instructor_labels"], {str(self.assistant.pk): "Bəhruz Həsənov"})

    def test_grace_next_and_latest_past(self):
        self.assertEqual(self._prefill("11:50")["slot_id"], str(self.seminar.pk))  # 10 dəq. əvvəl bitib
        self.assertEqual(self._prefill("08:00")["slot_id"], str(self.seminar.pk))  # növbəti
        self.assertEqual(self._prefill("18:00")["slot_id"], str(self.lab.pk))  # ən son keçmiş

    def test_slot_with_a_lesson_is_skipped_and_every_open_slot_is_offered(self):
        self._lesson(kind=LessonKind.SEMINAR, topic="Giriş", start_time=_t("10:10"), end_time=_t("11:40"))
        data = self._prefill("10:30")
        self.assertEqual(data["slot_id"], str(self.lab.pk))
        self.assertEqual(set(data["slots"]), {str(self.lab.pk)})
        # Parklanmış, başqa günün və yad fənnin slotu heç vaxt təklif olunmur.
        self.assertNotIn(str(self.parked.pk), data["slots"])
        self.assertNotIn(str(self.other_day.pk), data["slots"])

    def test_kind_maps_follow_the_syllabus_and_the_last_lessons(self):
        self._lesson(days_ago=7, kind=LessonKind.SEMINAR, topic="Giriş", hours=1, instructor=self.assistant)
        data = self._prefill("10:30")
        self.assertEqual(data["topic_by_kind"], {"lecture": "Giriş", "seminar": "SQL", "lab": "SQL"})
        self.assertEqual(data["topic"], "SQL")  # seminarda «Giriş» artıq keçilib
        self.assertEqual(data["instructor_by_kind"]["seminar"], str(self.assistant.pk))
        self.assertEqual(data["instructor_by_kind"]["lecture"], str(self.teacher.pk))
        self.assertEqual(data["hours_by_kind"], {"lecture": 2, "seminar": 1, "lab": 2})
        self.assertEqual(data["instructor"], str(self.assistant.pk))  # slotun müəllimi yox → seminarın son müəllimi

    def test_labels_name_every_lesson_teacher_for_the_edit_chip(self):
        self._lesson(self.plain, days_ago=14, kind=LessonKind.LECTURE, instructor=self.assistant)
        self._lesson(self.plain, days_ago=7, kind=LessonKind.LECTURE, instructor=self.teacher)
        data = self._prefill("10:30", self.plain)
        self.assertEqual(data["instructor_by_kind"]["lecture"], str(self.teacher.pk))
        # Köhnə dərsin müəllimi seçicinin namizəd siyahısında olmaya bilər — redaktə çipi adı buradan alır.
        self.assertEqual(data["instructor_labels"], {str(self.assistant.pk): "Bəhruz Həsənov"})

    def test_without_timetable_the_last_lesson_gives_kind_hours_teacher_and_time(self):
        self._lesson(self.plain, days_ago=14, kind=LessonKind.LECTURE, hours=2)
        self._lesson(
            self.plain,
            days_ago=7,
            kind=LessonKind.SEMINAR,
            hours=1,
            instructor=self.assistant,
            start_time=_t("13:35"),
            end_time=_t("15:05"),
            topic="Giriş",
        )
        self._lesson(self.plain, days_ago=-3, kind=LessonKind.LAB, hours=3)  # irəli tarixli plan — sayılmır
        data = self._prefill("10:30", self.plain)
        self.assertEqual(data["source"], "last")
        self.assertEqual(data["slot_id"], "")
        self.assertEqual(data["slots"], {})
        self.assertEqual((data["kind"], data["hours"]), (LessonKind.SEMINAR, 1))
        self.assertEqual(data["instructor"], str(self.assistant.pk))
        self.assertEqual(data["time"], "13:35|15:05")
        self.assertEqual(data["topic"], "SQL")

    def test_offering_with_timetable_leaves_the_time_to_the_teacher(self):
        for start, end in (("10:10", "11:40"), ("12:00", "13:30")):
            self._lesson(kind=LessonKind.SEMINAR, start_time=_t(start), end_time=_t(end))
        data = self._prefill("10:30")
        self.assertEqual(data["source"], "last")
        self.assertEqual(data["time"], "")

    def test_locked_kind_and_plan_hours(self):
        data = self._prefill("10:30", self.plain, locked_lesson_kind=LessonKind.LAB)
        self.assertEqual((data["kind"], data["source"]), (LessonKind.LAB, ""))
        with mock.patch(
            "apps.registrar.plan_hours.plan_hours_for_offering", return_value={"lecture": 30, "seminar": 45}
        ):
            data = self._prefill("10:30", self.plain)
        self.assertEqual((data["kind"], data["source"]), (LessonKind.SEMINAR, "plan"))
        with mock.patch("apps.registrar.plan_hours.plan_hours_for_offering", return_value={}):
            data = self._prefill("10:30", self.plain)
        self.assertEqual((data["kind"], data["source"], data["hours"]), (LessonKind.LECTURE, "", 2))

    def test_prefill_shares_the_lesson_query_with_the_strip(self):
        offering = self._fresh()
        context = self._context(offering)
        with bypass_rls():
            journal_activation.strip_context(offering, context)  # slotlar + dərs sətirləri (memo)
            with self.assertNumQueries(1):  # yalnız slot otaqlarının reyestr axtarışı («305»)
                extra = journal_lesson_prefill.modal_context(offering, context)
        self.assertIn("lesson_prefill", extra)
        other_tab = self._fresh()
        context = self._context(other_tab, active_tab="yekun")
        with bypass_rls():
            journal_activation.strip_context(other_tab, context)
            with self.assertNumQueries(2):  # dərs sətirləri + otaq axtarışı
                journal_lesson_prefill.modal_context(other_tab, context)

    def test_read_only_page_gets_no_prefill(self):
        offering = self._fresh()
        self.assertEqual(journal_lesson_prefill.modal_context(offering, self._context(offering, can_edit=False)), {})


class SlotPathPostTest(LessonPrefillBase):
    def test_slot_lesson_keeps_the_own_bell_time_and_needs_no_reason(self):
        self._add()
        (lesson,) = self._lessons()
        self.assertEqual((lesson.start_time, lesson.end_time), (_t("12:00"), _t("13:30")))
        self.assertEqual(lesson.kind, LessonKind.LAB)
        self.assertEqual(lesson.off_schedule_reason, "")
        self.assertEqual(lesson.instructor_id, self.assistant.pk)  # seçici göndərilməyib → slotun müəllimi

    def test_without_slot_id_the_own_bell_time_is_refused(self):
        resp = self._add(slot_id="")
        self.assertContains(resp, "Dərs saatı seçilməlidir")
        self.assertEqual(self._lessons(), [])

    def test_foreign_parked_and_garbage_slots_are_refused(self):
        for slot_id in (str(self.foreign_slot.pk), str(self.parked.pk), "not-a-uuid"):
            resp = self._add(slot_id=slot_id)
            self.assertContains(resp, "Bu cədvəl dərsi bu fənnə aid deyil")
        self.assertEqual(self._lessons(), [])

    def test_slot_of_another_weekday_is_refused(self):
        resp = self._add(slot_id=str(self.other_day.pk), lesson_kind=LessonKind.LECTURE, lesson_time="08:30|10:00")
        self.assertContains(resp, "tarixində keçirilmir")
        self.assertEqual(self._lessons(), [])

    def test_changed_time_falls_back_to_the_manual_rules(self):
        resp = self._add(slot_id=str(self.seminar.pk), lesson_kind=LessonKind.SEMINAR, lesson_time="13:35|15:05")
        self.assertContains(resp, "cədvəldən kənar dərs üçün səbəbi yazın")
        self.assertEqual(self._lessons(), [])
        self._add(
            slot_id=str(self.seminar.pk),
            lesson_kind=LessonKind.SEMINAR,
            lesson_time="13:35|15:05",
            off_schedule_reason="Kompensasiya dərsi",
        )
        (lesson,) = self._lessons()
        self.assertEqual((lesson.start_time, lesson.off_schedule_reason), (_t("13:35"), "Kompensasiya dərsi"))

    def test_changed_kind_falls_back_to_the_manual_rules(self):
        resp = self._add(lesson_kind=LessonKind.LECTURE)  # laboratoriya slotu, tip mühazirə → standart saat lazımdır
        self.assertContains(resp, "Dərs saatı seçilməlidir")
        self.assertEqual(self._lessons(), [])

    def test_duplicate_slot_lesson_is_refused(self):
        self._add()
        resp = self._add()
        self.assertContains(resp, "eyni dərs saatına artıq dərs var")
        self.assertEqual(len(self._lessons()), 1)

    def test_editing_a_slot_lesson_keeps_its_own_bell_time(self):
        # Əvvəl redaktə (məs. yalnız mövzu) standart olmayan saatı silirdi → zolaq slotu yenidən «açılmayıb»
        # göstərirdi (dublikat dərs riski). Başqa standart saat seçiləndə isə saat dəyişir.
        self._add()
        (lesson,) = self._lessons()
        url = reverse("registrar:journal_lesson_action", args=[self.offering.id, lesson.id])
        payload = {
            "action": "update_lesson",
            "lesson_date": self.today.isoformat(),
            "lesson_kind": LessonKind.LAB,
            "lesson_hours": "2",
            "lesson_time": "12:00|13:30",
            "lesson_topic": "SQL",
            "lesson_instructor": str(self.assistant.pk),
        }
        self._client().post(url, payload)
        (lesson,) = self._lessons()
        self.assertEqual((lesson.topic, lesson.start_time, lesson.end_time), ("SQL", _t("12:00"), _t("13:30")))
        self._client().post(url, dict(payload, lesson_time="13:35|15:05"))
        (lesson,) = self._lessons()
        self.assertEqual((lesson.start_time, lesson.end_time), (_t("13:35"), _t("15:05")))


class ActivationFlagTest(LessonPrefillBase):
    def _activate(self, slot):
        return self._client().post(reverse("registrar:journal_activate_slot", args=[self.offering.id, slot.id]))

    def test_default_off_strip_offers_new_lesson_instead_of_activation(self):
        resp = self._journal()
        strip = resp.context["today_strip"]
        self.assertFalse(strip["activation"])
        self.assertFalse(strip["can_activate"])
        self.assertTrue(strip["can_add"])
        self.assertTrue(all(item["activate_url"] == "" for item in strip["items"]))
        self.assertNotContains(resp, "data-jd-activate-form")
        self.assertNotContains(
            resp, reverse("registrar:journal_activate_slot", args=[self.offering.id, self.seminar.id])
        )
        self.assertContains(resp, f'data-jd-prefill-slot="{self.seminar.pk}"')
        self.assertContains(resp, 'id="jdLessonPrefill"')
        self.assertContains(resp, "registrar/js/journal_lesson_prefill.js")
        self.assertContains(resp, 'name="slot_id"')
        self.assertContains(resp, '<option value="4">4</option>')  # akademik saat 1..4
        self.assertNotContains(resp, "«Aktivləşdir» düyməsini işlədin")
        self.assertIn(str(self.seminar.pk), resp.context["lesson_prefill"]["slots"])

    def test_default_off_activation_post_is_404(self):
        self.assertEqual(self._activate(self.seminar).status_code, 404)
        self.assertEqual(self._lessons(), [])

    def _manual_error(self):
        with bypass_rls():
            _reason, error = journal_activation.check_manual_lesson(
                self._fresh(), date=self.today.isoformat(), start_time=_t("13:35"), hours=2, raw_reason=""
            )
        return error

    def test_default_off_manual_error_does_not_point_to_activation(self):
        error = self._manual_error()
        self.assertIn("cədvəldən kənar dərs üçün səbəbi yazın", error)
        self.assertIn("tarixi və saatı cədvələ uyğun seçin", error)
        self.assertNotIn("Aktivləşdir", error)
        resp = self._add(slot_id="", lesson_kind=LessonKind.LECTURE, lesson_time="13:35|15:05")
        self.assertContains(resp, "cədvəldən kənar dərs üçün səbəbi yazın")
        self.assertNotContains(resp, "«Aktivləşdir» düyməsini işlədin")
        self.assertEqual(self._lessons(), [])

    @override_settings(JOURNAL_LESSON_ACTIVATION=True)
    def test_switched_on_restores_the_activation_flow(self):
        self.assertIn("«Aktivləşdir» düyməsini işlədin", self._manual_error())
        resp = self._journal()
        strip = resp.context["today_strip"]
        self.assertTrue(strip["can_activate"])
        self.assertFalse(strip["can_add"])
        self.assertContains(resp, "data-jd-activate-form")
        self.assertNotContains(resp, "data-jd-prefill-slot")
        self.assertContains(resp, "«Aktivləşdir» düyməsini işlədin")
        self.assertEqual(self._activate(self.seminar).status_code, 302)
        (lesson,) = self._lessons()
        self.assertEqual(lesson.start_time, _t("10:10"))

    def test_read_only_strip_says_not_opened_without_activation_wording(self):
        from apps.registrar import gradebook
        from apps.registrar.models import ApprovalStatus, AssessmentScheme

        with bypass_rls():
            gradebook.ensure_assessment_scheme(offering=self.offering)
            AssessmentScheme.objects.filter(offering=self.offering).update(
                is_published=True, approval_status=ApprovalStatus.APPROVED
            )
        resp = self._journal()
        strip = resp.context["today_strip"]
        self.assertFalse(strip["can_add"])
        self.assertFalse(strip["can_activate"])
        self.assertNotIn("lesson_prefill", resp.context)
        self.assertContains(resp, "Dərs açılmayıb")
        self.assertNotContains(resp, "Aktivləşdirilməyib")
        self.assertNotContains(resp, "data-jd-prefill-slot")
