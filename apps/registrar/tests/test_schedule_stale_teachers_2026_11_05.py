"""Jurnalı və dərs yükü olmayan müəllimin cədvəlində qalan dərs (sahib 2026-11-05).

Nəyi qoruyur
------------
* oxu: slota yazılmış müəllim sahib/pay sahibi deyil, jurnalda dərs aparmayıb və yükü yoxdursa həmin dərs onun
  cədvəlində GÖRÜNMÜR; pay / dərs / ləğv olunmamış bölgü onu saxlayır; qrupun cədvəli dəyişmir;
* oxu: deaktiv jurnalın slotu heç bir cədvəldə görünmür; müəllim cədvəli yenə TƏK sorğudur;
* qarşısının alınması: ``release`` köhnəlmiş müəllimi boşaldır (audit ilə), carini saxlayır; tam təhvil köhnə
  sahibə yazılmış slotu yeni sahibə ötürür, geri qaytarma simmetrikdir;
* təmizləmə əmri ``release_stale_slot_teachers``: defolt dry-run, ``--apply``, idempotent, stdout yalnız saylar,
  deaktiv jurnalın duran slotu parklanır; prod-data-ops naqilləri.
"""

from __future__ import annotations

import pathlib
import re
from io import StringIO

from django.core.management import call_command

from apps.audit.models import AuditLog
from apps.registrar import handover_actions, schedule, schedule_stale_teachers
from apps.registrar.models import CourseOffering, JournalShare, Lesson, ScheduleSlot, SlotKind
from apps.registrar.tests.test_schedule_slot_instructor import SlotInstructorBase
from apps.registrar.tests.test_teaching_handover import HandoverBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


def _ids(slots):
    return [slot.pk for slot in slots]


class StaleTeacherReadTest(SlotInstructorBase):
    code = "stread"

    def _teacher_c(self):
        return schedule.get_teacher_schedule(organization=self.org, teacher=self.teacher_c, period=self.period)

    def test_teacher_without_journal_or_load_does_not_see_the_slot(self):
        with bypass_rls():
            slot = self._slot(self.offering, weekday=2, kind=SlotKind.SEMINAR, instructor=self.teacher_c)
            mine = self._teacher_c()
            group = schedule.get_group_schedule(organization=self.org, group=self.groups[0], period=self.period)
            owner = schedule.get_teacher_schedule(organization=self.org, teacher=self.teacher_a, period=self.period)
        self.assertEqual(mine, [])
        self.assertEqual(_ids(group), [slot.pk])  # dərs qrupun cədvəlində qalır
        self.assertEqual(owner, [])  # slot hələ C-yə yazılıb — sahibə yalnız boşaldılanda düşür

    def test_active_share_keeps_the_slot_and_an_inactive_one_does_not(self):
        with bypass_rls():
            slot = self._slot(self.offering, weekday=2, kind=SlotKind.SEMINAR, instructor=self.teacher_c)
            share = JournalShare.objects.create(
                organization=self.org, offering=self.offering, teacher=self.teacher_c, kinds=["seminar"]
            )
            shared = self._teacher_c()
            share.is_active = False
            share.save(update_fields=["is_active"])
            revoked = self._teacher_c()
        self.assertEqual(_ids(shared), [slot.pk])
        self.assertEqual(revoked, [])

    def test_recorded_lesson_keeps_the_slot(self):
        with bypass_rls():
            slot = self._slot(self.offering, weekday=2, kind=SlotKind.SEMINAR, instructor=self.teacher_c)
            Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=self.today,
                kind="seminar",
                instructor=self.teacher_c,
            )
            mine = self._teacher_c()
        self.assertEqual(_ids(mine), [slot.pk])

    def test_workload_keeps_the_slot_unless_the_task_is_cancelled(self):
        with bypass_rls():
            slot = self._slot(self.offering, weekday=2, kind=SlotKind.SEMINAR, instructor=self.teacher_c)
            self._seminar_load(self.teacher_c, status="cancelled")
            cancelled = self._teacher_c()
            self._seminar_load(self.teacher_c)
            draft = self._teacher_c()
        self.assertEqual(cancelled, [])
        self.assertEqual(_ids(draft), [slot.pk])

    def test_load_on_another_group_does_not_count(self):
        with bypass_rls():
            self._slot(self.offering, weekday=2, kind=SlotKind.SEMINAR, instructor=self.teacher_c)
            self._seminar_load(self.teacher_c, offering=self.offering_d)  # eyni fənn, başqa qrup
            mine = self._teacher_c()
        self.assertEqual(mine, [])

    def test_ownerless_journal_keeps_the_slot_only_with_a_recorded_lesson(self):
        with bypass_rls():
            CourseOffering.objects.filter(pk=self.offering.pk).update(instructor=None)
            slot = self._slot(self.offering, weekday=2, instructor=self.teacher_c)
            without = self._teacher_c()
            Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=self.today,
                kind="lecture",
                instructor=self.teacher_c,
            )
            taught = self._teacher_c()
        self.assertEqual(without, [])
        self.assertEqual(_ids(taught), [slot.pk])

    def test_inactive_journal_slot_is_hidden_everywhere(self):
        with bypass_rls():
            self._slot(self.offering, weekday=2)
            CourseOffering.objects.filter(pk=self.offering.pk).update(is_active=False)
            owner = schedule.get_teacher_schedule(organization=self.org, teacher=self.teacher_a, period=self.period)
            group = schedule.get_group_schedule(organization=self.org, group=self.groups[0], period=self.period)
        self.assertEqual((owner, group), ([], []))

    def test_teacher_schedule_stays_one_query_with_a_stale_override(self):
        with bypass_rls():
            self._slot(self.offering, weekday=2, kind=SlotKind.SEMINAR, instructor=self.teacher_c)
            self._slot(self.offering_b, weekday=3, instructor=self.teacher_c)
            with self.assertNumQueries(1):
                slots = self._teacher_c()
        self.assertEqual(slots, [])


class OwnerFallbackTest(SlotInstructorBase):
    """Sahib 2026-11-05 (Firəngiz): «müəllimin yükündə yoxdursa müəllim cədvəlində görməsin o fənni»."""

    code = "stowner"

    def _load(self, teacher, activity):
        from apps.workload.models import TeacherAssignment, TeachingTaskRow

        seed = self._seminar_load(teacher)
        TeachingTaskRow.objects.filter(pk=seed.row_id).update(lecture_plan=30, lecture_total=30, total_hours=60)
        if activity != "seminar":
            TeacherAssignment.objects.filter(pk=seed.pk).update(activity=activity)
        return seed

    def _view(self, teacher):
        return schedule.get_teacher_schedule(organization=self.org, teacher=teacher, period=self.period)

    def test_owner_without_load_loses_the_slot_and_the_load_teacher_gets_it(self):
        with bypass_rls():
            lecture = self._slot(self.offering, weekday=1, kind=SlotKind.LECTURE)
            seminar = self._slot(self.offering, weekday=3, kind=SlotKind.SEMINAR)
            before = self._view(self.teacher_a)
            self._load(self.teacher_c, "lecture")
            owner = self._view(self.teacher_a)
            new_teacher = self._view(self.teacher_c)
            group = schedule.get_group_schedule(organization=self.org, group=self.groups[0], period=self.period)
        self.assertEqual(sorted(_ids(before), key=str), sorted([lecture.pk, seminar.pk], key=str))  # yük yoxdur
        self.assertEqual(_ids(owner), [seminar.pk])  # mühazirə C-nin yükündədir; seminarın yükü heç kimdə yoxdur
        self.assertEqual(_ids(new_teacher), [lecture.pk])  # yalnız öz növü (mühazirə)
        self.assertEqual(sorted(_ids(group), key=str), sorted([lecture.pk, seminar.pk], key=str))

    def test_recorded_lesson_alone_does_not_keep_the_slot_but_own_load_does(self):
        with bypass_rls():
            slot = self._slot(self.offering, weekday=1, kind=SlotKind.LECTURE)
            self._load(self.teacher_c, "lecture")
            Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=self.today,
                kind="lecture",
                instructor=self.teacher_a,
            )
            taught = self._view(self.teacher_a)
            self._load(self.teacher_a, "lecture")
            loaded = self._view(self.teacher_a)
        self.assertEqual(taught, [])  # keçmiş dərs saxlamır — yük lazımdır
        self.assertEqual(_ids(loaded), [slot.pk])

    def test_vacant_load_does_not_take_the_slot_from_the_owner(self):
        from apps.workload.models import TeacherAssignment

        with bypass_rls():
            slot = self._slot(self.offering, weekday=1, kind=SlotKind.SEMINAR)
            TeacherAssignment.objects.filter(pk=self._seminar_load(self.teacher_c).pk).update(teacher=None)
            owner = self._view(self.teacher_a)
        self.assertEqual(_ids(owner), [slot.pk])


class ReleaseTest(SlotInstructorBase):
    code = "strel"

    def test_release_clears_only_stale_slots_with_an_audit_row(self):
        with bypass_rls():
            stale = self._slot(self.offering, weekday=2, kind=SlotKind.SEMINAR, instructor=self.teacher_c)
            parked = self._slot(self.offering, weekday=5, instructor=self.teacher_c, is_parked=True)
            current = self._slot(self.offering, weekday=3, kind=SlotKind.SEMINAR, instructor=self.teacher_b)
            self._seminar_load(self.teacher_b)
            plain = self._slot(self.offering, weekday=4)
            released = schedule_stale_teachers.release(offering_ids=[self.offering.pk], by_user=self.owner)
            again = schedule_stale_teachers.release(offering_ids=[self.offering.pk], by_user=self.owner)
            values = dict(
                ScheduleSlot.objects.filter(pk__in=[stale.pk, parked.pk, current.pk, plain.pk]).values_list(
                    "pk", "instructor_id"
                )
            )
            audit = AuditLog.objects.filter(resource_type="registrar.ScheduleSlot", resource_id=str(stale.pk)).first()
            owner = schedule.get_teacher_schedule(organization=self.org, teacher=self.teacher_a, period=self.period)
        self.assertEqual((released, again), (2, 0))
        self.assertEqual(values[stale.pk], None)
        self.assertEqual(values[parked.pk], None)
        self.assertEqual(values[current.pk], self.teacher_b.pk)
        self.assertIsNone(values[plain.pk])
        self.assertIsNotNone(audit)
        self.assertEqual(audit.old_values, {"instructor": str(self.teacher_c.pk)})
        self.assertEqual(audit.reason, schedule_stale_teachers.RELEASE_REASON)
        seminar_teacher = schedule.get_teacher_schedule(
            organization=self.org, teacher=self.teacher_b, period=self.period
        )
        # Seminar B-nin yükündədir — boşaldılan seminar slotu B-yə düşür, sahib A onu görmür (sahib 2026-11-05);
        # mühazirənin yükü heç kimdə yoxdur — sahibdə qalır.
        self.assertEqual(_ids(owner), [plain.pk])
        self.assertEqual(sorted(_ids(seminar_teacher), key=str), sorted([stale.pk, current.pk], key=str))

    def test_inactive_journal_slots_are_left_as_repair_evidence(self):
        with bypass_rls():
            slot = self._slot(self.offering, weekday=2, instructor=self.teacher_c, is_parked=True)
            CourseOffering.objects.filter(pk=self.offering.pk).update(is_active=False)
            released = schedule_stale_teachers.release(offering_ids=[self.offering.pk])
            slot.refresh_from_db()
        self.assertEqual(released, 0)
        self.assertEqual(slot.instructor_id, self.teacher_c.pk)


class HandoverSlotTest(HandoverBase):
    def _slot(self, instructor=None, weekday=1):
        import datetime

        return ScheduleSlot.objects.create(
            organization=self.org,
            offering=self.offering_a,
            weekday=weekday,
            start_time=datetime.time(10, 10),
            end_time=datetime.time(11, 40),
            instructor=instructor,
        )

    def test_full_handover_moves_the_previous_owners_slot_and_revert_is_symmetric(self):
        with bypass_rls():
            owners = self._slot(instructor=self.old_teacher)  # sahib olmamışdan əvvəl yazılıb
            others = self._slot(instructor=self.other_teacher, weekday=2)
            record_id = self._reassign()["handover_ids"][0]
            owners.refresh_from_db()
            others.refresh_from_db()
            moved = (owners.instructor_id, others.instructor_id)
            new_view = schedule.get_teacher_schedule(
                organization=self.org, teacher=self.new_teacher, period=self.period
            )
            old_view = schedule.get_teacher_schedule(
                organization=self.org, teacher=self.old_teacher, period=self.period
            )
            handover_actions.revert(actor=self.rim, organization=self.org, handover_id=record_id, reason="Səhv")
            back = schedule.get_teacher_schedule(organization=self.org, teacher=self.old_teacher, period=self.period)
        self.assertEqual(moved, (None, self.other_teacher.pk))
        self.assertEqual(_ids(new_view), [owners.pk])
        self.assertEqual(old_view, [])
        self.assertEqual(_ids(back), [owners.pk])


class ReleaseCommandTest(SlotInstructorBase):
    code = "stcmd"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])

    def _run(self, *extra):
        out = StringIO()
        call_command(
            "release_stale_slot_teachers", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out
        )
        return out.getvalue()

    @staticmethod
    def _counts(text):
        line = [row for row in text.splitlines() if row.startswith("slot_teachers: ") and "mode=" not in row][0]
        return dict(pair.split("=", 1) for pair in line.split()[1:])

    def test_dry_run_apply_and_idempotency(self):
        with bypass_rls():
            stale = self._slot(self.offering, weekday=2, kind=SlotKind.SEMINAR, instructor=self.teacher_c)
            self._slot(self.offering, weekday=3, kind=SlotKind.SEMINAR, instructor=self.teacher_b)
            self._seminar_load(self.teacher_b)
            live = self._slot(self.offering_d, weekday=4)
            CourseOffering.objects.filter(pk=self.offering_d.pk).update(is_active=False)
        dry = self._run()
        with bypass_rls():
            stale.refresh_from_db()
            live.refresh_from_db()
        self.assertEqual(
            self._counts(dry),
            {"checked": "2", "current": "1", "released": "1", "inactive_live": "1", "inactive_parked": "1"},
        )
        self.assertEqual((stale.instructor_id, live.is_parked), (self.teacher_c.pk, False))  # dry-run yazmır

        applied = self._run("--period", str(self.period.pk), "--apply")
        with bypass_rls():
            stale.refresh_from_db()
            live.refresh_from_db()
        self.assertIn("slot_teachers: mode=apply", applied)
        self.assertEqual(self._counts(applied)["released"], "1")
        self.assertIsNone(stale.instructor_id)
        self.assertTrue(live.is_parked)
        self.assertTrue(live.park_reason)

        again = self._counts(self._run("--apply"))
        self.assertEqual((again["released"], again["inactive_parked"]), ("0", "0"))
        for line in (dry + applied).splitlines():
            self.assertRegex(line, r"^slot_teachers: [a-z_]+=[0-9a-z_]+( [a-z_]+=[0-9a-z_]+)*$")

    def test_prod_data_ops_wiring(self):
        text = WORKFLOW.read_text()
        self.assertIn("          - release_stale_slot_teachers\n", text)
        self.assertIn("            release_stale_slot_teachers)\n", text)
        self.assertIn('[ "$COMMAND" = "release_stale_slot_teachers" ]', text)
        summary = re.search(r"grep -E '\^\(([a-z_|]+)\): \[a-z_\]\+=", text.split('"release_stale_slot_teachers" ]')[1])
        self.assertIsNotNone(summary)
        self.assertIn("slot_teachers", summary.group(1).split("|"))
