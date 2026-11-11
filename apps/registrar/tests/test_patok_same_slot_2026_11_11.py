"""Patok: müəllim eyni saatda bir neçə qrupun dərsini yaza bilir (sahib 2026-11-11).

Sahib: patok dərslərində müəllim ikinci qrupun dərsini EYNİ saata yaza bilmir («xana tutulub») — icazə verilsin.

* Cədvəl: patok = eyni effektiv müəllim + eyni fənn + eyni növ + eyni/boş otaq, qruplar fərqli
  (``schedule.is_joint_lecture``). «Eyni fənn» əvvəl yalnız eyni id idi — fakültələrin ayrı kodlu, adı eyni
  dublikat fənni (dublikat birləşməsindən qalan «Fizika» / «FİZİKA») patok sayılmırdı → «Müəllimin … dərsi var».
* Jurnal: patokun hər qrupunun dərsi öz jurnalındadır (toqquşmur); bir jurnal daxilində FƏRQLİ alt qrupların
  (Lab-1 / Lab-2, seminar alt qrupları) eyni saatdakı dərsi də artıq toqquşma deyil.
* Həqiqi toqquşmalar qalır və mesaj nəyin əskik olduğunu deyir.
"""

from __future__ import annotations

import datetime

from django.utils import timezone

from apps.registrar import gradebook, schedule, schedule_conflicts
from apps.registrar.models import LabGroup, Lesson, ScheduleSlot, SeminarGroup, SlotKind, Subject, WeekType
from apps.registrar.tests.test_schedule_slot_instructor import SlotInstructorBase, _t
from core.rls import bypass_rls

FIRST_PAIR = datetime.time(8, 30)
TUESDAY = {"weekday": 2, "start_time": _t("08:30"), "end_time": _t("10:00"), "week_type": WeekType.ALL}


class PatokScheduleTest(SlotInstructorBase):
    """231A-nın «Fizika»sı (F-101) və 231D-nin dublikat «FİZİKA»sı (F-202), ikisini də A aparır."""

    code = "patokslot"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.physics = Subject.objects.create(organization=cls.org, code="F-101", name="Fizika")
            cls.physics_dup = Subject.objects.create(organization=cls.org, code="F-202", name=" FİZİKA ")
            cls.lead = cls._offering(cls.physics, cls.groups[0], cls.teacher_a)
            cls.partner = cls._offering(cls.physics_dup, cls.groups[3], cls.teacher_a)
            cls.same_subject_partner = cls._offering(cls.physics, cls.groups[2], cls.teacher_a)

    def _lead_slot(self, room=""):
        return self._slot(self.lead, weekday=2, start="08:30", end="10:00", room=room)

    def _detect(self, offering, *, kind=SlotKind.LECTURE, room=""):
        return schedule_conflicts.detect(
            organization=self.org,
            **TUESDAY,
            room=room,
            group_id=offering.group_id,
            instructor_id=self.teacher_a.pk,
            period_id=self.period.pk,
            subject_id=offering.subject_id,
            kind=kind,
            offering_id=offering.pk,
        )

    def test_duplicate_subject_patok_is_not_a_teacher_clash(self):
        with bypass_rls():
            self._lead_slot(room="A-1")
            found = self._detect(self.partner, room="A-1")
            created = schedule.create_slot(offering=self.partner, room="A-1", kind=SlotKind.LECTURE, **TUESDAY)
        self.assertEqual(found, [])
        self.assertTrue(ScheduleSlot.objects.filter(pk=created.pk).exists())

    def test_same_subject_patok_with_empty_room_still_passes(self):
        with bypass_rls():
            self._lead_slot(room="A-1")
            found = self._detect(self.same_subject_partner)
        self.assertEqual(found, [])

    def test_other_subject_is_still_a_clash_without_patok_hint(self):
        with bypass_rls():
            self._lead_slot()
            other = self._offering(self.subject_b, self.groups[1], self.teacher_a)
            found = self._detect(other)
            with self.assertRaises(schedule.ScheduleConflict):
                schedule.create_slot(offering=other, kind=SlotKind.LECTURE, **TUESDAY)
        teacher = [row for row in found if row["kind"] == schedule_conflicts.KIND_TEACHER]
        self.assertEqual(len(teacher), 1)
        self.assertNotIn("Patok", teacher[0]["message"])

    def test_other_kind_is_a_clash_and_says_why(self):
        with bypass_rls():
            self._lead_slot()
            found = self._detect(self.partner, kind=SlotKind.SEMINAR)
        teacher = [row for row in found if row["kind"] == schedule_conflicts.KIND_TEACHER]
        self.assertEqual(len(teacher), 1)
        self.assertIn("eyni dərs növü", teacher[0]["message"])

    def test_other_room_is_a_clash_and_says_why(self):
        with bypass_rls():
            self._lead_slot(room="A-1")
            found = self._detect(self.partner, room="B-2")
        teacher = [row for row in found if row["kind"] == schedule_conflicts.KIND_TEACHER]
        self.assertEqual(len(teacher), 1)
        self.assertIn("A-1", teacher[0]["message"])
        self.assertIn("auditoriya eyni olmalıdır", teacher[0]["message"])

    def test_same_group_is_always_a_clash(self):
        with bypass_rls():
            self._lead_slot()
            twin = self._offering(self.physics_dup, self.groups[0], self.teacher_a)
            found = self._detect(twin)
        self.assertIn(schedule_conflicts.KIND_GROUP, {row["kind"] for row in found})


class PatokJournalLessonTest(SlotInstructorBase):
    """Dərs yazısı: patokun ikinci qrupunun jurnalı və bir jurnal daxilində alt qruplar."""

    code = "patokles"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.day = timezone.localdate()
        with bypass_rls():
            cls.partner = cls._offering(cls.subject, cls.groups[1], cls.teacher_a)
            for number in (1, 2):
                LabGroup.objects.create(organization=cls.org, offering=cls.offering, number=number)
                SeminarGroup.objects.create(organization=cls.org, offering=cls.offering, number=number)

    def _create(self, offering, *, kind="lecture", start=FIRST_PAIR, **extra):
        return gradebook.create_lesson(
            offering=offering,
            date=self.day,
            kind=kind,
            start_time=start,
            end_time=datetime.time(10, 0),
            instructor=self.teacher_a,
            allow_past=True,
            **extra,
        )

    def test_patok_lecture_is_written_in_every_group_journal_at_the_same_hour(self):
        with bypass_rls():
            first = self._create(self.offering)
            second = self._create(self.partner)
        self.assertNotEqual(first.offering_id, second.offering_id)
        self.assertEqual((first.date, first.start_time), (second.date, second.start_time))

    def test_second_whole_group_lesson_in_the_same_journal_is_refused_with_a_clear_message(self):
        with bypass_rls():
            self._create(self.offering)
            with self.assertRaises(gradebook.LessonRuleError) as caught:
                self._create(self.offering)
        message = str(caught.exception)
        self.assertIn("08:30", message)
        self.assertIn("öz jurnalına", message)

    def test_lab_groups_of_one_journal_share_the_hour(self):
        with bypass_rls():
            self._create(self.offering, kind="lab", lab_group=1)
            self._create(self.offering, kind="lab", lab_group=2)
            with self.assertRaises(gradebook.LessonRuleError):
                self._create(self.offering, kind="lab", lab_group=1)  # eyni alt qrup — dublikat
            with self.assertRaises(gradebook.LessonRuleError):
                self._create(self.offering, kind="lab")  # bütün qrup — hər alt qrupla kəsişir
        self.assertEqual(Lesson.objects.filter(offering=self.offering, kind="lab").count(), 2)

    def test_seminar_subgroups_share_the_hour(self):
        with bypass_rls():
            self._create(self.offering, kind="seminar", seminar_group=1)
            self._create(self.offering, kind="seminar", seminar_group=2)
        self.assertEqual(Lesson.objects.filter(offering=self.offering, kind="seminar").count(), 2)

    def test_moving_a_subgroup_lesson_onto_the_same_subgroup_hour_is_refused(self):
        with bypass_rls():
            self._create(self.offering, kind="lab", lab_group=1)
            other = self._create(self.offering, kind="lab", lab_group=2, start=datetime.time(10, 10))
            self.assertTrue(
                gradebook.update_lesson(
                    lesson=other, start_time=datetime.time(8, 30), allow_past=True, allow_locked=True, audit=False
                )
            )
            with self.assertRaises(gradebook.LessonRuleError):
                gradebook.update_lesson(lesson=other, lab_group=1, allow_past=True, allow_locked=True, audit=False)
