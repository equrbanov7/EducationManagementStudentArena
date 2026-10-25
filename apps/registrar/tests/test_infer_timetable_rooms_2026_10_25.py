"""``infer_timetable_from_lessons`` — slotun otağı (sahib 2026-10-25: «müəllimin ən çox yazdığı otağı çıxardaq ki,
harada dərs keçir — dərs cədvəlindəki kimi»).

Müəllim ``T``, dövr 6 həftə əvvəl başlayıb:

* B.e. 08:30 G1 mühazirəsi — 2 dəfə A-101, 2 dəfə B-202 (sonra) → bərabərlikdə ƏN SON: B-202 (dərslərdən);
* B.c.a. 10:10 G2 seminarı — otaqsız → müəllimin ümumən ən çox otağı A-101 (``teacher``);
* Ç. 11:50 G3 seminarı — hər dəfə A-101, amma həmin saat A-101 başqa müəllimin rəsmi slotundadır → otaqsız;
* C.a. 13:35 G4 seminarı — otaqsız; T həmin saatda (G5, bircə dərs) C-303-dədir → C-303 (``teacher_slot``);
* Cümə 08:30 G6 — U müəlliminin rəsmi (docx) slotu otaqsızdır, jurnalda D-404 → rəsmi slota TOXUNULMUR.
"""

from __future__ import annotations

import datetime
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services, timetable_inference
from apps.registrar.models import Lesson, LessonKind, ScheduleSlot, SlotKind, Subject
from apps.registrar.tests.test_infer_timetable_rules_2026_10_25 import _counts
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
T = datetime.time


class InferTimetableRoomsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.start = today - datetime.timedelta(days=today.weekday() + 42)
        owner = User.objects.create_user("itm_owner", "itm_owner@qku.edu.az", "pw")
        cls.teacher = User.objects.create_user("itm.t", "itm_t@qku.edu.az", "pw")
        cls.other = User.objects.create_user("itm.u", "itm_u@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="ITM Univ",
                slug="itm-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=cls.start,
                end_date=today + datetime.timedelta(days=60),
                is_current=True,
            )
            role = cls.org.roles.get(name="teacher")
            for user in (cls.teacher, cls.other):
                Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True)
            rooms = {
                name: cls.org.exam_rooms.create(name=name, code=f"R{index}", building="Korpus A", is_active=True)
                for index, name in enumerate(("A-101", "B-202", "C-303", "D-404"))
            }
            cls.o = {}
            for index in range(1, 8):
                group = OrgUnit.objects.create(
                    organization=cls.org, name=f"M{index}", slug=f"itm-g{index}", unit_type=OrgUnitType.GROUP
                )
                subject = Subject.objects.create(organization=cls.org, code=f"ITM{index}", name=f"Fənn {index}")
                offering = services.get_or_create_offering(
                    organization=cls.org, subject=subject, period=cls.period, group=group
                )
                offering.instructor = cls.teacher if index <= 5 else cls.other
                offering.save(update_fields=["instructor"])
                cls.o[index] = offering

            def lesson(index, weekday, start, kind, week, room=None):
                Lesson.objects.create(
                    organization=cls.org,
                    offering=cls.o[index],
                    date=cls.start + datetime.timedelta(days=7 * (week - 1) + weekday - 1),
                    kind=kind,
                    start_time=start,
                    room=rooms[room] if room else None,
                )

            seminar, lecture = LessonKind.SEMINAR, LessonKind.LECTURE
            for week, room in zip(range(1, 7), ("A-101", "A-101", "B-202", "B-202", None, None)):
                lesson(1, 1, T(8, 30), lecture, week, room)
            for week in range(1, 7):
                lesson(2, 2, T(10, 10), seminar, week)
                lesson(3, 3, T(11, 50), seminar, week, "A-101")
                lesson(6, 5, T(8, 30), seminar, week, "D-404")
            for week in (1, 2, 3):
                lesson(4, 4, T(13, 35), seminar, week)
            lesson(5, 4, T(13, 35), seminar, 4, "C-303")
            ScheduleSlot.objects.create(
                organization=cls.org,
                offering=cls.o[7],
                weekday=3,
                start_time=T(11, 50),
                end_time=T(13, 20),
                kind=SlotKind.LECTURE,
                room="A-101",
            )
            cls.official = ScheduleSlot.objects.create(
                organization=cls.org,
                offering=cls.o[6],
                weekday=5,
                start_time=T(8, 30),
                end_time=T(10, 0),
                kind=SlotKind.SEMINAR,
            )

    def _call(self, *args) -> dict:
        out = StringIO()
        call_command(
            "infer_timetable_from_lessons", "--org", "itm-univ", "--period", "Payız 2026/2027", *args, stdout=out
        )
        return _counts(out.getvalue())

    def _room(self, index):
        with bypass_rls():
            return list(ScheduleSlot.objects.filter(offering=self.o[index]).values_list("room", flat=True))

    def test_room_sources_and_clash(self):
        counts = self._call("--apply", "--i-know-this-is-production")
        self.assertEqual(counts["written"], "4")
        self.assertEqual(
            (counts["room_from_lessons"], counts["room_from_teacher"], counts["room_from_teacher_slot"]),
            ("1", "1", "1"),
        )
        self.assertEqual(counts["reason_room_dropped"], "1")
        self.assertEqual(self._room(1), ["B-202"])  # 2 : 2 — ən son istifadə olunan
        self.assertEqual(self._room(2), ["A-101"])  # müəllimin ən çox otağı
        self.assertEqual(self._room(3), [""])  # A-101 həmin saat tutulub
        self.assertEqual(self._room(4), ["C-303"])  # müəllimin həmin gün/saat otağı
        self.assertEqual(self._room(6), [""])  # rəsmi slota toxunulmur

    def test_fill_rooms_only_on_own_slots_and_idempotent(self):
        self._call("--apply", "--i-know-this-is-production")
        with bypass_rls():
            ScheduleSlot.objects.filter(offering=self.o[2]).update(room="")
        counts = self._call("--no-fill-rooms")
        self.assertEqual(counts["room_filled"], "0")
        counts = self._call("--apply", "--i-know-this-is-production")
        self.assertEqual((counts["written"], counts["rooms_filled"], counts["reason_room_filled"]), ("0", "1", "1"))
        self.assertEqual(self._room(2), ["A-101"])
        self.assertEqual(self._room(6), [""])
        self.assertEqual(self._call("--apply", "--i-know-this-is-production")["rooms_filled"], "0")


class MostUsedRoomTest(SimpleTestCase):
    @staticmethod
    def _fact(day, room):
        return timetable_inference.LessonFact("o", "s", datetime.date(2026, 9, day), T(8, 30), None, "lecture", 1, room)

    def test_most_used_then_latest(self):
        pick = timetable_inference.most_used_room
        self.assertEqual(pick([self._fact(1, "A"), self._fact(2, "a"), self._fact(3, "B")]), "a")
        self.assertEqual(pick([self._fact(1, "A"), self._fact(8, "B")]), "B")
        self.assertEqual(pick([self._fact(9, "A"), self._fact(8, "B")]), "A")
        self.assertEqual(pick([self._fact(1, ""), self._fact(2, " ")]), "")
