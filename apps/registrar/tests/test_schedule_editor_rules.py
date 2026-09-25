"""Redaktorun konflikt mühərriki (``schedule_conflicts.detect/suggest``) — ``find_conflict`` ilə EYNİ qaydalar.

2026-09-25: 4e0b986d-nin iki qaydası yalnız ``schedule.find_conflict``-ə düşmüşdü, dispetçerlərin
işlətdiyi əsas yol — «Cədvəl idarəetməsi» redaktoru — isə köhnə qalmışdı:

* keçən semestrin silinməmiş slotu bu semestrin eyni saatını bloklayırdı (müəllim / qrup / otaq);
* generatorun dərc etdiyi AXIN mühazirəsi (bir müəllim, bir fənn, bir otaq, bir neçə qrup) redaktorda
  «müəllim toqquşması» + «otaq toqquşması» kimi görünür, məcburi saxlamada yoldaş slot parklanırdı.

İndi: yalnız açılışın semestri sayılır (dövr yoxdursa köhnə davranış); eyni effektiv müəllim + eyni fənn +
hər ikisi mühazirə + eyni (və ya boş) otaq, qruplar FƏRQLİ → toqquşma deyil; qrup toqquşması HƏMİŞƏ
toqquşmadır; seminar və başqa fənn toqquşmadır.
"""

from __future__ import annotations

import datetime

from apps.organizations.models import AcademicPeriod
from apps.registrar import schedule_conflicts, schedule_editor
from apps.registrar import schedule_editor_actions as editor
from apps.registrar import schedule_publish, services
from apps.registrar.models import ScheduleSlot, SlotKind, WeekType
from apps.registrar.tests.test_schedule_slot_instructor import _t
from apps.registrar.tests.test_schedule_slot_instructor_editor import _EditorBase
from core.constants import AcademicPeriodType
from core.rls import bypass_rls

MONDAY_PAIR_2 = {"weekday": 1, "start_time": _t("10:10"), "end_time": _t("11:40"), "week_type": WeekType.ALL}


def _cleaned(kind=SlotKind.LECTURE, room="R-1", weekday=1, start="10:10", end="11:40"):
    return {
        "weekday": weekday,
        "start_time": _t(start),
        "end_time": _t(end),
        "week_type": WeekType.ALL,
        "kind": kind,
        "room": room,
    }


class LastSemesterTest(_EditorBase):
    """Keçən semestrin (silinməmiş) slotu bu semestrin redaktorunu bloklamır."""

    code = "serls"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.spring = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Keçən semestr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date=cls.period.start_date - datetime.timedelta(days=200),
                end_date=cls.period.start_date - datetime.timedelta(days=30),
            )
            old = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.spring, group=cls.groups[0]
            )
            old.instructor = cls.teacher_a
            old.save(update_fields=["instructor"])
            # Eyni qrup + eyni müəllim + eyni otaq + eyni saat — amma KEÇƏN semestr.
            cls.old_slot = ScheduleSlot.objects.create(
                organization=cls.org,
                offering=old,
                weekday=1,
                start_time=_t("10:10"),
                end_time=_t("11:40"),
                room="R-1",
            )

    def test_editor_check_ignores_last_semester(self):
        with bypass_rls():
            verdict = schedule_editor.check_cell(organization=self.org, offering=self.offering, cleaned=_cleaned())
            result = self._save(slot_kind=SlotKind.LECTURE, room="R-1", time_slot="10:10|11:40")
            self.old_slot.refresh_from_db()
        self.assertTrue(verdict["ok"], verdict["conflicts"])
        self.assertEqual(verdict["conflicts"], [])
        self.assertEqual(result["parked"], [])  # keçən semestrin slotu parklanmır
        self.assertFalse(self.old_slot.is_parked)

    def test_without_a_period_the_old_behaviour_stays(self):
        params = {**MONDAY_PAIR_2, "room": "R-1", "group_id": self.groups[0].pk, "instructor_id": self.teacher_a.pk}
        with bypass_rls():
            legacy = schedule_conflicts.detect(organization=self.org, **params)
            scoped = schedule_conflicts.detect(organization=self.org, period_id=self.period.pk, **params)
        kinds = {row["kind"] for row in legacy}
        self.assertEqual(set(schedule_conflicts.KIND_ORDER), kinds)  # müəllim + qrup + otaq
        self.assertEqual(scoped, [])

    def test_suggestions_offer_the_cell_again(self):
        cell = (1, "10:10|11:40")
        with bypass_rls():
            legacy = schedule_conflicts.suggest(
                organization=self.org, group_id=self.groups[0].pk, instructor_id=self.teacher_a.pk, limit=100
            )
            scoped = editor.suggestions_for(
                organization=self.org,
                group=self.groups[0],
                instructor_id=str(self.teacher_a.pk),
                period=self.period,
                limit=100,
            )
        self.assertNotIn(cell, {(row["weekday"], row["time_slot"]) for row in legacy})
        self.assertIn(cell, {(row["weekday"], row["time_slot"]) for row in scoped})

    def test_http_check_and_suggest_use_the_selected_semester(self):
        payload = self._payload(slot_kind=SlotKind.LECTURE, room="R-1")
        check = self._act(self.coordinator, {**payload, "action": "check"})
        suggest = self._act(
            self.coordinator,
            {
                "action": "suggest",
                "group_id": str(self.groups[0].pk),
                "period_id": str(self.period.pk),
                "instructor_id": str(self.teacher_a.pk),
            },
        )
        broken = self._act(self.coordinator, {"action": "suggest", "group_id": "abc", "period_id": "abc"})
        self.assertEqual(check.status_code, 200, check.content)
        self.assertTrue(check.json()["ok"], check.json())
        cells = {(row["weekday"], row["time_slot"]) for row in suggest.json()["suggestions"]}
        self.assertIn((1, "10:10|11:40"), cells)
        self.assertEqual(broken.status_code, 200)  # pozuq id-lər 500 vermir — «seçilməyib» sayılır


class StreamLectureTest(_EditorBase):
    """Generatorun dərc etdiyi axın mühazirəsi redaktorda toqquşma kimi görünmür."""

    code = "serst"

    def _publish_stream(self, room="A-1"):
        """SI101 mühazirəsi 231A + 231D üçün BİRGƏ (axın), mühazirəçi A (231D-nin jurnalı D-dədir)."""
        rows = [
            {
                "offering_id": str(offering.pk),
                "weekday": 2,
                "start_time": _t("08:30"),
                "end_time": _t("10:00"),
                "week_type": WeekType.ALL,
                "kind": SlotKind.LECTURE,
                "room": room,
                "teacher_id": self.teacher_a.pk,
                "stream": "si101-lecture",
            }
            for offering in (self.offering, self.offering_d)
        ]
        result = schedule_publish.publish_slots(
            actor=self.owner,
            organization=self.org,
            period=self.period,
            offering_ids=[str(self.offering.pk), str(self.offering_d.pk)],
            slots=rows,
            source="test:stream",
        )
        slots = {slot.offering_id: slot for slot in ScheduleSlot.objects.filter(pk__in=result["slot_ids"])}
        return slots[self.offering.pk], slots[self.offering_d.pk]

    def test_stream_partners_are_not_flagged_in_the_editor(self):
        with bypass_rls():
            slot_a, slot_d = self._publish_stream()
            for_a = schedule_editor.check_cell(
                organization=self.org,
                offering=self.offering,
                cleaned=_cleaned(room="A-1", weekday=2, start="08:30", end="10:00"),
                exclude_id=str(slot_a.pk),
            )
            for_d = schedule_editor.check_cell(
                organization=self.org,
                offering=self.offering_d,
                cleaned=_cleaned(room="", weekday=2, start="08:30", end="10:00"),  # otaq boş — yenə axın
                exclude_id=str(slot_d.pk),
                slot_instructor_id=self.teacher_a.pk,
            )
        self.assertIsNone(slot_a.instructor_id)  # jurnal sahibi A özü aparır
        self.assertEqual(slot_d.instructor_id, self.teacher_a.pk)  # D-nin jurnalında mühazirəçi A
        self.assertEqual(for_a["conflicts"], [])
        self.assertEqual(for_d["conflicts"], [])

    def test_stream_slot_can_be_moved_and_rechecked_over_http(self):
        with bypass_rls():
            slot_a, slot_d = self._publish_stream()
        # Redaktə dialoqu: D-nin slotunun müəllimi (A) seçici mənbələrində yoxdur, amma DƏYİŞMƏYİB.
        check = self._act(
            self.coordinator,
            {
                **self._payload(
                    subject_id=str(self.subject.pk),
                    instructor_id=str(self.teacher_d.pk),
                    slot_instructor_id=str(self.teacher_a.pk),
                    weekday="2",
                    time_slot="08:30|10:00",
                    slot_kind=SlotKind.LECTURE,
                    room="A-1",
                ),
                "group_id": str(self.groups[3].pk),
                "slot_id": str(slot_d.pk),
                "action": "check",
            },
        )
        with bypass_rls():
            moved = editor.move_slot(
                actor=self.coordinator,
                organization=self.org,
                slot=editor.get_slot(self.org, slot_a.pk),
                data={"weekday": 2, "time_slot": "10:10|11:40"},
            )
            back = editor.move_slot(
                actor=self.coordinator,
                organization=self.org,
                slot=editor.get_slot(self.org, slot_a.pk),
                data={"weekday": 2, "time_slot": "08:30|10:00"},
            )
            # D-nin override slotunun özü də köçür (müəllimi A seçici mənbələrində olmasa da) və A-nı saxlayır.
            moved_d = editor.move_slot(
                actor=self.coordinator,
                organization=self.org,
                slot=editor.get_slot(self.org, slot_d.pk),
                data={"weekday": 4, "time_slot": "13:35|15:05"},
            )
            slot_d.refresh_from_db()
        self.assertEqual(check.status_code, 200, check.content)
        self.assertEqual(check.json()["conflicts"], [])
        self.assertEqual(moved["parked"], [])
        self.assertEqual(back["parked"], [])  # yoldaş slota geri qayıtmaq onu PARKLAMIR
        self.assertEqual(moved_d["slot"]["slot_instructor_id"], str(self.teacher_a.pk))
        self.assertFalse(slot_d.is_parked)
        self.assertEqual((slot_d.weekday, slot_d.start_time), (4, _t("13:35")))
        self.assertEqual(slot_d.instructor_id, self.teacher_a.pk)

    def test_seminar_other_subject_and_other_room_are_still_clashes(self):
        with bypass_rls():
            self._publish_stream()
            teacher_args = {**MONDAY_PAIR_2, "weekday": 2, "start_time": _t("08:30"), "end_time": _t("10:00")}
            base = {"organization": self.org, "period_id": self.period.pk, "instructor_id": self.teacher_a.pk}
            seminar = schedule_conflicts.detect(
                **base,
                **teacher_args,
                room="A-1",
                group_id=self.groups[2].pk,
                subject_id=self.subject.pk,
                kind="seminar",
            )
            other_subject = schedule_conflicts.detect(
                **base,
                **teacher_args,
                room="A-1",
                group_id=self.groups[2].pk,
                subject_id=self.subject_b.pk,
                kind="lecture",
            )
            other_room = schedule_conflicts.detect(
                **base,
                **teacher_args,
                room="B-2",
                group_id=self.groups[2].pk,
                subject_id=self.subject.pk,
                kind="lecture",
            )
            joins = schedule_conflicts.detect(
                **base, **teacher_args, room="", group_id=self.groups[2].pk, subject_id=self.subject.pk, kind="lecture"
            )
        teacher = schedule_conflicts.KIND_TEACHER
        self.assertIn(teacher, {row["kind"] for row in seminar})
        self.assertIn(teacher, {row["kind"] for row in other_subject})
        self.assertIn(teacher, {row["kind"] for row in other_room})
        self.assertEqual(joins, [])  # 231C axına qoşulur (otaq boş)

    def test_same_group_is_always_a_clash(self):
        with bypass_rls():
            self._publish_stream()
            found = schedule_conflicts.detect(
                organization=self.org,
                weekday=2,
                start_time=_t("08:30"),
                end_time=_t("10:00"),
                week_type=WeekType.ALL,
                room="A-1",
                group_id=str(self.groups[0].pk),  # 231A — axının öz qrupu
                instructor_id=self.teacher_a.pk,
                period_id=self.period.pk,
                subject_id=self.subject.pk,
                kind=SlotKind.LECTURE,
            )
        self.assertIn(schedule_conflicts.KIND_GROUP, {row["kind"] for row in found})

    def test_forced_save_does_not_park_the_stream_partner(self):
        with bypass_rls():
            slot_a, slot_d = self._publish_stream()
            # 231A-nın mühazirəsini redaktə et (otaq eyni) — toqquşma yoxdur, məcburi rejim lazım deyil.
            result = self._save(
                slot_id=str(slot_a.pk),
                weekday="2",
                time_slot="08:30|10:00",
                slot_kind=SlotKind.LECTURE,
                room="A-1",
                force="1",
                reason="Axın yoxlaması — heç nə parklanmamalıdır",
            )
            slot_d.refresh_from_db()
        self.assertEqual(result["parked"], [])
        self.assertFalse(slot_d.is_parked)
