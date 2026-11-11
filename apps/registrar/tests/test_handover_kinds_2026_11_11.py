"""«Fənn təhvili» — yalnız bir dərs növünün (seminar / lab / mühazirə) təhvili (sahib 2026-11-11).

Sahib: «yalnız seminarı (mühazirəni yox) təhvil vermək işləmir». Əvvəl təhvil yalnız açılışın sahibini
(``instructor``) dəyişirdi — seminarçının payına heç bir yol yox idi. Yoxlanılır: seminar təhvili sahibə və
mühazirəyə toxunmur; mühazirə təhvili seminarçını saxlayır; sahib bütün növləri aparırsa seminar ondan alınır,
qalan növlər onda qalır; bal itmir; geri qaytarma əvvəlki payları bərpa edir.
"""

from apps.registrar import handover_actions, journal_access, journal_shares, journal_transfer
from apps.registrar.models import CourseOffering, JournalShare, TeachingHandover
from core.rls import bypass_rls

from .test_teaching_handover import HandoverBase


class KindHandoverTests(HandoverBase):
    def _split(self):
        """Mühazirə — köhnə müəllim (sahib), seminar — «other» (yükdən gələn bölünmüş jurnal)."""
        JournalShare.objects.create(
            organization=self.org,
            offering=self.offering_a,
            teacher=self.old_teacher,
            source="workload",
            kinds=["lecture"],
        )
        return JournalShare.objects.create(
            organization=self.org,
            offering=self.offering_a,
            teacher=self.other_teacher,
            source="workload",
            kinds=["seminar"],
        )

    def _give(self, kinds, target=None, **extra):
        return handover_actions.reassign(
            actor=self.rim,
            organization=self.org,
            offering_id=self.offering_a.pk,
            new_instructor_id=(target or self.new_teacher).pk,
            reason="Seminar müəllimi dəyişdi",
            kinds=kinds,
            **extra,
        )

    def _fresh(self):
        offering = CourseOffering.objects.get(pk=self.offering_a.pk)
        journal_shares.forget(offering)
        return offering

    def _active(self, teacher):
        return JournalShare.objects.filter(offering=self.offering_a, teacher=teacher, is_active=True).first()

    def test_seminar_only_handover_moves_the_seminar_share(self):
        with bypass_rls():
            seminar = self._split()
            result = self._give(["seminar"])
            offering = self._fresh()
            self.assertEqual(offering.instructor_id, self.old_teacher.pk)  # sahib / mühazirə yerində
            seminar.refresh_from_db()
            self.assertFalse(seminar.is_active)
            self.assertEqual(self._active(self.new_teacher).kinds, ["seminar"])
            self.assertEqual(self._active(self.old_teacher).kinds, ["lecture"])
            scope = journal_shares.journal_scope(self.new_teacher, offering)
            self.assertEqual(scope.kinds, frozenset({"seminar"}))
            self.assertTrue(journal_access.can_edit_journal(self.new_teacher, offering))
            self.assertFalse(journal_access.can_edit_journal(self.other_teacher, offering))
            self.assertEqual(result["moved"][0]["kinds"], ["seminar"])
            self.assertFalse(result["moved"][0]["owner_move"])

    def test_seminar_handover_when_owner_teaches_everything(self):
        with bypass_rls():
            self._give(["seminar"])
            offering = self._fresh()
            self.assertEqual(offering.instructor_id, self.old_teacher.pk)
            self.assertEqual(self._active(self.old_teacher).kinds, ["lecture", "lab"])
            self.assertEqual(self._active(self.new_teacher).kinds, ["seminar"])
            owner = journal_shares.journal_scope(self.old_teacher, offering)
            self.assertFalse(owner.allows_kind("seminar"))
            self.assertTrue(owner.allows_kind("lecture"))

    def test_lecture_handover_leaves_the_seminar_teacher_alone(self):
        with bypass_rls():
            seminar = self._split()
            self._give(["lecture"])
            offering = self._fresh()
            self.assertEqual(offering.instructor_id, self.new_teacher.pk)
            seminar.refresh_from_db()
            self.assertTrue(seminar.is_active)
            self.assertEqual(seminar.kinds, ["seminar"])
            self.assertIsNone(self._active(self.old_teacher))  # yalnız mühazirəni aparırdı
            self.assertEqual(self._active(self.new_teacher).kinds, ["lecture"])
            self.assertTrue(journal_access.can_edit_journal(self.other_teacher, offering))
            self.assertFalse(journal_access.can_edit_journal(self.old_teacher, offering))

    def test_lecture_handover_keeps_old_owner_seminar(self):
        with bypass_rls():
            self._give(["lecture"])
            offering = self._fresh()
            self.assertEqual(offering.instructor_id, self.new_teacher.pk)
            self.assertEqual(self._active(self.old_teacher).kinds, ["seminar", "lab"])
            self.assertTrue(journal_access.can_edit_journal(self.old_teacher, offering))

    def test_revert_restores_the_previous_shares(self):
        with bypass_rls():
            seminar = self._split()
            record_id = self._give(["seminar"])["handover_ids"][0]
            handover_actions.revert(actor=self.rim, organization=self.org, handover_id=record_id, reason="Səhv təyinat")
            seminar.refresh_from_db()
            self.assertTrue(seminar.is_active)
            self.assertIsNone(self._active(self.new_teacher))
            self.assertEqual(self._fresh().instructor_id, self.old_teacher.pk)
            self.assertTrue(TeachingHandover.objects.get(pk=record_id).is_reverted)

    def test_history_knows_the_kinds(self):
        with bypass_rls():
            self._split()
            record_id = self._give(["seminar"])["handover_ids"][0]
            record = TeachingHandover.objects.get(pk=record_id)
            self.assertEqual(journal_transfer.record_kinds([record])[record.pk], (False, frozenset({"seminar"})))

    def test_unknown_kind_is_rejected(self):
        with bypass_rls(), self.assertRaises(handover_actions.HandoverError) as error:
            self._give(["practice"])
        self.assertEqual(error.exception.code, "invalid_kind")

    def test_from_teacher_must_hold_the_kind(self):
        with bypass_rls():
            self._split()
            with self.assertRaises(handover_actions.HandoverError) as error:
                self._give(["seminar"], from_teacher_id=self.new_teacher.pk)
            self.assertEqual(error.exception.codes, ("kind_not_held",))

    def test_full_handover_is_unchanged(self):
        with bypass_rls():
            seminar = self._split()
            result = self._give(None)
            self.assertEqual(self._fresh().instructor_id, self.new_teacher.pk)
            seminar.refresh_from_db()
            self.assertTrue(seminar.is_active)
            self.assertTrue(result["moved"][0]["owner_move"])


class KindHandoverReviewTests(KindHandoverTests):
    """Review 2026-11-11 (PR #324) — #2 slotlar, #3 bir neçə növ sahibi, #5 qalıq payı iddia deyil."""

    def test_2_lecture_only_transfer_keeps_seminar_slots_with_the_old_owner(self):
        import datetime

        from django.db.models.functions import Coalesce

        from apps.registrar.models import ScheduleSlot

        with bypass_rls():
            slot = ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.offering_a,
                kind="seminar",
                weekday=1,
                start_time=datetime.time(9),
                end_time=datetime.time(10),
            )
            self._give(["lecture"])
            effective = (
                ScheduleSlot.objects.filter(pk=slot.pk)
                .annotate(teacher=Coalesce("instructor_id", "offering__instructor_id"))
                .values_list("teacher", flat=True)[0]
            )
            self.assertEqual(self._fresh().instructor_id, self.new_teacher.pk)
            self.assertEqual(effective, self.old_teacher.pk)

    def _two_lab_holders(self):
        from apps.registrar.models import Enrollment

        student = Enrollment.objects.filter(offering=self.offering_a).first()
        x = JournalShare.objects.create(
            organization=self.org,
            offering=self.offering_a,
            teacher=self.other_teacher,
            source="workload",
            kinds=["lab"],
        )
        x.enrollments.set([student])
        # Lab-2 — ikinci müəllim (eyni növ, başqa alt qrup kimi).
        y = JournalShare.objects.create(
            organization=self.org, offering=self.offering_a, teacher=self.dean, source="workload", kinds=["lab"]
        )
        y.enrollments.set([student])
        return x

    def test_3_two_lab_holders_require_choosing_the_source(self):
        with bypass_rls():
            self._two_lab_holders()  # Lab-1 «other», Lab-2 «dean»
            with self.assertRaises(handover_actions.HandoverError) as error:
                self._give(["lab"])
            self.assertEqual(error.exception.codes, ("kind_ambiguous",))
            self.assertEqual(self._fresh().instructor_id, self.old_teacher.pk)

    def test_3_from_teacher_moves_only_that_holders_lab(self):
        with bypass_rls():
            x = self._two_lab_holders()
            self._give(["lab"], from_teacher_id=self.other_teacher.pk)
            x.refresh_from_db()
            self.assertFalse(x.is_active)
            target = self._active(self.new_teacher)
            self.assertEqual(target.kinds, ["lab"])
            self.assertEqual(
                set(target.enrollments.values_list("pk", flat=True)), set(x.enrollments.values_list("pk", flat=True))
            )
            self.assertEqual(self._fresh().instructor_id, self.old_teacher.pk)
            self.assertIsNotNone(self._active(self.dean))  # Lab-2 müəllimi toxunulmur

    def test_5_only_the_target_share_is_a_handover_claim(self):
        with bypass_rls():
            self._give(["seminar"])
            owner_rest = self._active(self.old_teacher)
            target = self._active(self.new_teacher)
            self.assertFalse(journal_transfer.is_handover_share(owner_rest))
            self.assertTrue(journal_transfer.is_handover_share(target))
