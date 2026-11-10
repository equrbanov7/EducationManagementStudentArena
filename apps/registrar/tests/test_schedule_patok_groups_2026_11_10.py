"""Patokun BÜTÜN qruplarının mühazirə vaxtı müəllim cədvəlində görünür (sahib 2026-11-10).

Sahib: «patok dərslərində müəllimlər 2 qrupun dərs saatını görür, patokda 4 qrup varsa qalan 2 qrupun saatı
görünmür … patokdakı bütün qrupların dərs cədvəli müəllimlərə görünməlidir».

Kök səbəb: patokda mühazirə yükə BİR dəfə düşür — aparıcı sətirdə (``lecture_total > 0``, mühazirə bölgüsü),
tərəfdaş sətirdə ``lecture_total = 0`` və mühazirə bölgüsü yoxdur. Müəllim cədvəlinin «növ üzrə yük» qaydası
(:mod:`apps.registrar.schedule_stale_teachers`, 2026-11-05) yalnız açılışın ÖZ qrupunun sətrinə baxırdı, ona görə
tərəfdaş qrupların mühazirə slotu mühazirəçinin cədvəlindən düşürdü.
"""

from __future__ import annotations

from apps.organizations.models import OrgUnit, OrgUnitType
from apps.registrar import schedule, schedule_slot_teachers, schedule_stale_teachers
from apps.registrar.models import ScheduleSlot, SlotKind
from apps.registrar.tests.test_schedule_slot_instructor import SlotInstructorBase
from core.rls import bypass_rls


class PatokGroupsScheduleTest(SlotInstructorBase):
    """Aparıcı sətir: 231A + 231B (mühazirə A-da); tərəfdaş sətir: 231C + 231D (``lecture_total = 0``)."""

    code = "patoksch"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.patok = [
                cls.offering,  # 231A — A-nın jurnalı
                cls._offering(cls.subject, cls.groups[1], cls.teacher_a),
                cls._offering(cls.subject, cls.groups[2], cls.teacher_b),
                cls.offering_d,  # 231D — D-nin jurnalı
            ]

    def _rows(self, *, link=True, partner_subject=None):
        from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow

        chair = OrgUnit.objects.create(
            organization=self.org,
            parent=self.faculty,
            name="Kafedra",
            slug=f"{self.code}-chair",
            unit_type=OrgUnitType.CHAIR,
        )
        task = TeachingTask.objects.create(organization=self.org, chair=chair, academic_year="2026/2027")
        lead = TeachingTaskRow.objects.create(
            organization=self.org,
            task=task,
            period=self.period,
            subject=self.subject,
            lecture_plan=30,
            lecture_total=30,
            total_hours=30,
            union_count=2,
        )
        lead.groups.set(self.groups[:2])
        partner = TeachingTaskRow.objects.create(
            organization=self.org,
            task=task,
            period=self.period,
            subject=partner_subject or self.subject,
            lecture_plan=30,
            lecture_total=0,
            seminar_plan=30,
            seminar_total=30,
            total_hours=30,
            patok_lead=lead if link else None,
        )
        partner.groups.set(self.groups[2:])
        TeacherAssignment.objects.create(
            organization=self.org, row=lead, teacher=self.teacher_a, activity="lecture", hours=30
        )
        TeacherAssignment.objects.create(
            organization=self.org, row=partner, teacher=self.teacher_b, activity="seminar", hours=30
        )
        return lead, partner

    def _lectures(self):
        return [self._slot(offering, weekday=2) for offering in self.patok]

    def _view(self, teacher):
        slots = schedule.get_teacher_schedule(organization=self.org, teacher=teacher, period=self.period)
        return {slot.pk for slot in slots}

    def test_lecturer_sees_the_lecture_time_of_all_four_groups(self):
        with bypass_rls():
            self._rows()
            slots = self._lectures()
            lecturer = self._view(self.teacher_a)
            seminar_teacher = self._view(self.teacher_b)
        self.assertEqual(lecturer, {slot.pk for slot in slots})
        self.assertEqual(seminar_teacher, set())  # tərəfdaşın seminarçısı mühazirəni aparmır

    def test_unlinked_partner_uses_the_same_task_heuristic(self):
        with bypass_rls():
            self._rows(link=False)
            slots = self._lectures()
            lecturer = self._view(self.teacher_a)
        self.assertEqual(lecturer, {slot.pk for slot in slots})

    def test_partner_seminar_and_other_subject_stay_out(self):
        with bypass_rls():
            self._rows(partner_subject=self.subject_b)  # başqa fənnin «tərəfdaşı» patok deyil
            lead_slots = [self._slot(offering, weekday=2) for offering in self.patok[:2]]
            self._slot(self.patok[2], weekday=2)
            self._slot(self.patok[3], weekday=4, kind=SlotKind.SEMINAR)
            lecturer = self._view(self.teacher_a)
        self.assertEqual(lecturer, {slot.pk for slot in lead_slots})

    def test_release_keeps_the_lecturer_written_on_a_partner_slot(self):
        with bypass_rls():
            self._rows()
            slot = self._slot(self.patok[3], weekday=2, instructor=self.teacher_a)
            released = schedule_stale_teachers.release(offering_ids=[self.patok[3].pk])
            slot.refresh_from_db()
        self.assertEqual(released, 0)
        self.assertEqual(slot.instructor_id, self.teacher_a.pk)
        self.assertEqual(ScheduleSlot.objects.filter(pk=slot.pk).count(), 1)

    def test_slot_editor_offers_the_patok_lecturer_on_partner_groups(self):
        with bypass_rls():
            self._rows()
            allowed = schedule_slot_teachers.allowed_teacher_ids(self.patok[3])
        self.assertIn(self.teacher_a.pk, allowed)

    def test_teacher_schedule_stays_one_query(self):
        with bypass_rls():
            self._rows()
            self._lectures()
            with self.assertNumQueries(1):
                schedule.get_teacher_schedule(organization=self.org, teacher=self.teacher_a, period=self.period)
