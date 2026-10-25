"""Sahib 2026-10-17: «Elektron jurnalda yeni dərs əlavə edərkən otaq nömrəsi cədvəldəki avtomatik gəlsin, müəllim
istəsə dəyişə bilər.»

Nəyi qoruyur
------------
* otaqsız göndərilən «Yeni dərs» (slot bağı olmadan) həmin tarix/saatın cədvəl slotunun otağını alır; üst/alt
  həftəsi uyğun gəlməyən tarixdə həmin slotun otağı YAZILMIR;
* müəllimin açıq seçdiyi otaq saxlanılır; başqa təşkilatın otağı dərsə bağlanmır (və cədvələ də keçilmir);
* modalın ``#jdSlotPattern`` adası saat / tip / pariteti və reyestr otağını (``room_id`` + ``room_label``) daşıyır;
* ``schedule_slot_for`` seçimi: saatı uyğun (eyni tip üstün) → eyni tip → günün ilk slotu (JS ilə eyni).
"""

from __future__ import annotations

import datetime

from apps.exams.models import ExamRoom
from apps.organizations.models import Organization
from apps.registrar import journal_lesson_prefill
from apps.registrar.models import LessonKind, ScheduleSlot, SlotKind
from apps.registrar.tests.test_journal_lesson_prefill_2026_10_10 import LessonPrefillBase, _t
from core.constants import OrganizationType
from core.rls import bypass_rls


class ScheduleRoomTest(LessonPrefillBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.room_b = ExamRoom.objects.create(organization=cls.org, name="101", code="B101", building="B")
            other = Organization.objects.create(
                name="LP Other",
                slug="lp-other",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.alien_room = ExamRoom.objects.create(organization=other, name="305", code="X305", building="A")

    def _seminar(self, **overrides):
        """Cədvəldəki seminar saatına (10:10, otaq «305») slot bağı OLMADAN «Yeni dərs»."""
        data = {"slot_id": "", "lesson_kind": LessonKind.SEMINAR, "lesson_time": "10:10|11:40"}
        data.update(overrides)
        return self._add(**data)

    def test_lesson_without_room_gets_the_timetable_slot_room(self):
        self._seminar()
        (lesson,) = self._lessons()
        self.assertEqual(lesson.room_id, self.room.pk)
        self.assertEqual(lesson.off_schedule_reason, "")

    def test_other_week_parity_does_not_take_that_slot_room(self):
        # Bir həftə əvvəl paritet tərsdir: 10:10 seminarı o gün keçirilmir → cədvəldən kənar, otaq «305» deyil.
        # (Gələcək tarixə dərs açılmır — sahib 2026-10-25; keçən həftə yazma pəncərəsindədir.)
        last_week = (self.today - datetime.timedelta(days=7)).isoformat()
        self._seminar(lesson_date=last_week, off_schedule_reason="Kompensasiya dərsi")
        (lesson,) = self._lessons()
        self.assertIsNone(lesson.room_id)  # həmin günün yeganə slotu (laboratoriya) otaqsızdır

    def test_explicit_room_is_kept(self):
        self._seminar(lesson_room=str(self.room_b.pk))
        (lesson,) = self._lessons()
        self.assertEqual(lesson.room_id, self.room_b.pk)

    def test_foreign_org_room_is_rejected(self):
        self._seminar(lesson_room=str(self.alien_room.pk))
        (lesson,) = self._lessons()
        self.assertIsNone(lesson.room_id)  # yad otaq bağlanmır, cədvəl otağı ilə də əvəzlənmir

    def test_slot_path_still_copies_the_slot_room(self):
        self._add(lesson_kind=LessonKind.SEMINAR, lesson_time="10:10|11:40", slot_id=str(self.seminar.pk))
        (lesson,) = self._lessons()
        self.assertEqual(lesson.room_id, self.room.pk)

    def test_modal_island_carries_parity_time_kind_and_room(self):
        resp = self._journal()
        self.assertContains(resp, 'id="jdSlotPattern"')
        self.assertContains(resp, "data-jd-room-restore")
        self.assertContains(resp, "journal_lesson_schedule.js")
        pattern = resp.context["lesson_slot_pattern"]
        self.assertIn(
            {
                "weekday": self.today.isoweekday(),
                "week_type": self.parity,
                "start": "10:10",
                "end": "11:40",
                "kind": "seminar",
                "room_id": str(self.room.pk),
                "room_label": "305",
            },
            pattern,
        )
        lab = next(item for item in pattern if item["start"] == "12:00")
        self.assertEqual((lab["kind"], lab["room_id"], lab["week_type"]), ("lab", "", "all"))
        self.assertNotIn("15:15", [item["start"] for item in pattern])  # parklanmış slot


class ScheduleSlotForTest(LessonPrefillBase):
    def test_time_then_kind_then_first(self):
        offering = self._fresh()
        with bypass_rls():
            ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.offering,
                weekday=self.today.isoweekday(),
                start_time=_t("10:10"),
                end_time=_t("11:40"),
                kind=SlotKind.LECTURE,
                room="101",
                week_type=self.parity,
            )
            pick = journal_lesson_prefill.schedule_slot_for
            self.assertEqual(pick(offering, self.today, _t("10:10"), LessonKind.SEMINAR), self.seminar)
            self.assertEqual(pick(offering, self.today, _t("10:10"), LessonKind.LECTURE).room, "101")
            self.assertEqual(pick(offering, self.today, _t("12:00"), LessonKind.SEMINAR), self.lab)  # saat üstün
            self.assertEqual(pick(offering, self.today, None, LessonKind.LAB), self.lab)
            self.assertEqual(pick(offering, self.today, _t("18:40"), "lecture").start_time, _t("10:10"))
            self.assertEqual(pick(offering, self.today, _t("18:40"), "other").start_time, _t("10:10"))  # ilk slot
            far = self.today + datetime.timedelta(days=365)
            self.assertIsNone(pick(offering, far, _t("10:10"), LessonKind.SEMINAR))  # dövrdən kənar
