"""Jurnal sahibi dəyişəndə keçilmiş dərslər köhnə müəllimdə qalır (sahib 2026-11-13, ``lesson_author_freeze``).

Boş ``Lesson.instructor`` «açılışın cari sahibi» oxunur — təhvildən sonra köhnə müəllimin keçdiyi dərslər yeni
sahibə «sürüşürdü». Yoxlanılır: tam / növ təhvili (sahiblik köçəndə) keçmiş boş dərsləri köhnə sahibə yazır,
gələcək dərs boş qalır; ``CourseOffering.save()`` siqnalı da eyni işi görür; geri qaytarma yazılanı saxlayır;
təhvildən sonra slotdan açılan yeni dərs yeni sahibə düşür (köhnə «son müəllim» yox).
"""

import datetime

from django.utils import timezone

from apps.registrar import handover_actions, journal_activation, journal_shares, lessons_log
from apps.registrar.lesson_author_freeze import freeze
from apps.registrar.models import CourseOffering, JournalShare, Lesson, LessonKind, ScheduleSlot
from core.rls import bypass_rls

from .test_teaching_handover import HandoverBase


class _FreezeBase(HandoverBase):
    def setUp(self):
        super().setUp()
        future = timezone.localdate() + datetime.timedelta(days=30)
        with bypass_rls():
            self.past_lecture = self._lesson(datetime.date(2024, 10, 1), LessonKind.LECTURE)
            self.past_seminar = self._lesson(datetime.date(2024, 10, 2), LessonKind.SEMINAR)
            self.future = self._lesson(future, LessonKind.LECTURE)
            self.foreign = self._lesson(datetime.date(2024, 10, 3), LessonKind.SEMINAR, instructor=self.other_teacher)

    def _lesson(self, day, kind, **extra):
        return Lesson.objects.create(
            organization=self.org, offering=self.offering_a, date=day, kind=kind, hours=2, **extra
        )

    def _owners(self):
        with bypass_rls():
            return {
                name: Lesson.objects.get(pk=getattr(self, name).pk).instructor_id
                for name in ("past_lecture", "past_seminar", "future", "foreign")
            }

    def _visible(self, user):
        with bypass_rls():
            return set(lessons_log.scoped_lessons(user, self.org, supervisor=False).values_list("pk", flat=True))

    def _give(self, kinds=None):
        with bypass_rls():
            return handover_actions.reassign(
                actor=self.rim,
                organization=self.org,
                offering_id=self.offering_a.pk,
                new_instructor_id=self.new_teacher.pk,
                reason="Müəllim dəyişdi",
                kinds=kinds,
            )

    def _fresh(self):
        offering = CourseOffering.objects.get(pk=self.offering_a.pk)
        journal_shares.forget(offering)
        return offering


class HandoverFreezeTest(_FreezeBase):
    def test_full_handover_keeps_past_lessons_on_the_old_owner(self):
        self._give()
        old, new = self.old_teacher.pk, self.new_teacher.pk
        self.assertEqual(
            self._owners(),
            {"past_lecture": old, "past_seminar": old, "future": None, "foreign": self.other_teacher.pk},
        )
        self.assertEqual(self._fresh().instructor_id, new)
        mine_old, mine_new = self._visible(self.old_teacher), self._visible(self.new_teacher)
        self.assertEqual(mine_old, {self.past_lecture.pk, self.past_seminar.pk})
        self.assertEqual(mine_new, {self.future.pk})

    def test_lecture_handover_moving_ownership_freezes_to_old_owner(self):
        result = self._give(["lecture"])
        self.assertTrue(result["moved"][0]["owner_move"])
        owners = self._owners()
        self.assertEqual(owners["past_lecture"], self.old_teacher.pk)
        self.assertEqual(owners["past_seminar"], self.old_teacher.pk)
        self.assertIsNone(owners["future"])

    def test_seminar_handover_without_owner_move_writes_nothing(self):
        result = self._give(["seminar"])
        self.assertFalse(result["moved"][0]["owner_move"])
        owners = self._owners()
        self.assertIsNone(owners["past_lecture"])
        self.assertIsNone(owners["past_seminar"])

    def test_revert_keeps_the_stamped_lessons(self):
        record_id = self._give()["handover_ids"][0]
        with bypass_rls():
            handover_actions.revert(actor=self.rim, organization=self.org, handover_id=record_id, reason="Səhv təyinat")
        self.assertEqual(self._fresh().instructor_id, self.old_teacher.pk)
        owners = self._owners()
        self.assertEqual(owners["past_lecture"], self.old_teacher.pk)
        self.assertEqual(owners["past_seminar"], self.old_teacher.pk)
        self.assertIsNone(owners["future"])
        self.assertTrue({self.past_lecture.pk, self.past_seminar.pk, self.future.pk} <= self._visible(self.old_teacher))


class SaveSignalFreezeTest(_FreezeBase):
    def test_save_with_instructor_in_update_fields_freezes(self):
        with bypass_rls():
            offering = CourseOffering.objects.get(pk=self.offering_a.pk)
            offering.instructor = self.new_teacher
            offering.save(update_fields=["instructor"])
        owners = self._owners()
        self.assertEqual(owners["past_lecture"], self.old_teacher.pk)
        self.assertEqual(owners["past_seminar"], self.old_teacher.pk)
        self.assertIsNone(owners["future"])

    def test_full_save_freezes(self):
        with bypass_rls():
            offering = CourseOffering.objects.get(pk=self.offering_a.pk)
            offering.instructor = self.new_teacher
            offering.save()
        self.assertEqual(self._owners()["past_lecture"], self.old_teacher.pk)

    def test_save_without_instructor_field_does_nothing(self):
        with bypass_rls():
            offering = CourseOffering.objects.get(pk=self.offering_a.pk)
            offering.instructor = self.new_teacher
            offering.lesson_hours = 30
            offering.save(update_fields=["lesson_hours"])
            self.assertEqual(CourseOffering.objects.get(pk=offering.pk).instructor_id, self.old_teacher.pk)
        self.assertIsNone(self._owners()["past_lecture"])

    def test_same_owner_save_does_nothing(self):
        with bypass_rls():
            offering = CourseOffering.objects.get(pk=self.offering_a.pk)
            offering.save(update_fields=["instructor"])
        self.assertIsNone(self._owners()["past_lecture"])

    def test_ownerless_to_owner_does_nothing(self):
        with bypass_rls():
            CourseOffering.objects.filter(pk=self.offering_a.pk).update(instructor=None)
            offering = CourseOffering.objects.get(pk=self.offering_a.pk)
            offering.instructor = self.new_teacher
            offering.save(update_fields=["instructor"])
        self.assertIsNone(self._owners()["past_lecture"])
        self.assertIsNone(self._owners()["past_seminar"])

    def test_freeze_guards(self):
        with bypass_rls():
            self.assertEqual(freeze(self.offering_a.pk, None), 0)
            self.assertEqual(freeze(None, self.old_teacher.pk), 0)
            self.assertEqual(freeze(self.offering_a.pk, self.old_teacher.pk), 2)
            self.assertEqual(freeze(self.offering_a.pk, self.new_teacher.pk), 0)  # artıq dolu — toxunulmur


class SlotTeacherAfterHandoverTest(_FreezeBase):
    """Təhvildən sonra slotdan açılan dərs yeni sahibə düşür — köhnə sahib «son müəllim» kimi qayıtmır."""

    def _slot(self, kind, instructor=None):
        return ScheduleSlot(
            organization=self.org,
            offering=self.offering_a,
            weekday=1,
            start_time=datetime.time(10, 10),
            end_time=datetime.time(11, 30),
            kind=kind,
            instructor=instructor,
        )

    def _teacher(self, kind, instructor=None):
        offering = self._fresh()
        _covered, last, _todays = journal_activation.lesson_facts(offering, timezone.localdate())
        return journal_activation.slot_teacher(offering, self._slot(kind, instructor), last)

    def test_new_slot_lesson_goes_to_the_new_owner(self):
        with bypass_rls():
            Lesson.objects.filter(pk=self.foreign.pk).delete()  # son seminar da köhnə sahibindir
        self._give()
        with bypass_rls():
            self.assertEqual(self._teacher(LessonKind.LECTURE), self.new_teacher)
            self.assertEqual(self._teacher(LessonKind.SEMINAR), self.new_teacher)
            # slotun öz müəllimi həmişə üstündür
            self.assertEqual(self._teacher(LessonKind.LECTURE, self.dean), self.dean)

    def test_shareless_assistant_stays_after_owner_handover(self):
        """2026-09-25 bölünmüş tədris: payı olmayan seminar assistenti təhvil edilməyib — son müəllim qalır."""
        self._give()
        with bypass_rls():
            self.assertEqual(self._teacher(LessonKind.SEMINAR), self.other_teacher)
            self.assertEqual(self._teacher(LessonKind.LECTURE), self.new_teacher)

    def test_last_instructor_still_holding_the_kind_is_kept(self):
        with bypass_rls():
            JournalShare.objects.create(
                organization=self.org,
                offering=self.offering_a,
                teacher=self.other_teacher,
                source="workload",
                kinds=["seminar"],
            )
            self.assertEqual(self._teacher(LessonKind.SEMINAR), self.other_teacher)
            freeze(self.offering_a.pk, self.old_teacher.pk)
            self.assertEqual(self._teacher(LessonKind.LECTURE), self.old_teacher)

    def test_current_last_instructor_drops_a_former_holder(self):
        self._give()
        with bypass_rls():
            offering = self._fresh()
            last = {LessonKind.LECTURE: self.old_teacher}
            self.assertIsNone(journal_activation.current_last_instructor(offering, LessonKind.LECTURE, last))
            self.assertIsNone(journal_activation.current_last_instructor(offering, LessonKind.LAB, last))
            self.assertEqual(
                journal_activation.current_last_instructor(
                    offering, LessonKind.LECTURE, {LessonKind.LECTURE: self.new_teacher}
                ),
                self.new_teacher,
            )
