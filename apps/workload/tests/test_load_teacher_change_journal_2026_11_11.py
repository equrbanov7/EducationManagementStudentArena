"""«Yük bölgüsü»ndə müəllim dəyişəndə jurnal da yeni müəllimə keçir (sahib 2026-11-11).

Sahib: «kafedra müdiri sətrin müəllimini dəyişəndə ekran "köçürüldü" deyir, amma jurnal yeni müəllimin
siyahısına düşmür». Kök səbəblər:

* ``offering_rules.decide_instructor`` açılışın cari müəllimi «Fənn təhvili» ilə gəlibsə (və ya cədvəl
  redaktoru/köhnə sistem qoyubsa) kafedranın AÇIQ dəyişikliyini də «qoruyurdu» — yeni müəllim heç vaxt sahib
  olmurdu;
* ``journal_workload_shares`` açılışda bir dəfə də olsa təhvil olubsa seminar/lab paylarını HEÇ VAXT
  sinxronlamırdı — seminarçının dəyişməsi jurnala çatmırdı;
* «Fənn təhvili» ilə verilmiş növ payı yükün sonrakı açıq dəyişikliyini əzirdi.

Yük dəyişikliyi və «Fənn təhvili» eyni registrar servisindən keçir (``journal_transfer``).
"""

from __future__ import annotations

from apps.registrar import handover_actions, journal_access, journal_shares
from apps.registrar.models import CourseOffering, JournalShare, LessonMark, TeachingHandover
from apps.workload.constants import Activity

from .test_plan_offering_instructors import _TeacherBase


class LoadTeacherChangeMovesJournalTest(_TeacherBase):
    code = "LTC"

    def _handover(self, target, *, kinds=None):
        extra = {"kinds": kinds} if kinds else {}
        return handover_actions.reassign(
            actor=self.office_rim,
            organization=self.org,
            offering_id=self.offering().pk,
            new_instructor_id=target.pk,
            reason="Fənn təhvili — test",
            **extra,
        )

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from django.contrib.auth import get_user_model

        from .factories import activate_member

        cls.office_rim = get_user_model().objects.create_user("ltc.rim", "ltcrim@x.test", "pw")
        activate_member(cls.org, cls.office_rim, "handover_office", permissions=["journal.reassign"], level=90)
        cls.teacher_d = cls._teacher("d")

    def _share(self, teacher):
        return JournalShare.objects.filter(offering=self.offering(), teacher=teacher, is_active=True).first()

    def test_chair_change_after_handover_moves_the_journal(self):
        _task, row = self.approved_row()
        assignment = self.assign(row, self.teacher_a)
        self._handover(self.teacher_c)
        self.assertEqual(self.offering().instructor_id, self.teacher_c.pk)
        changed = self.assign(row, self.teacher_b, assignment=assignment)
        offering = self.offering()
        self.assertEqual(offering.instructor_id, self.teacher_b.pk)
        self.assertTrue(journal_access.is_direct_editor(self.teacher_b, offering))
        self.assertFalse(journal_access.can_edit_journal(self.teacher_c, offering))
        self.assertEqual(changed.offering_sync.get("instructor_replaced"), 1)
        # Yük dəyişikliyi də «Fənn təhvili» qeydi buraxır (eyni servis) — tarixçədə görünür.
        self.assertTrue(
            TeachingHandover.objects.filter(
                offering=offering, to_instructor=self.teacher_b, reverted_at__isnull=True
            ).exists()
        )

    def test_chair_change_overrides_a_foreign_instructor(self):
        _task, row = self.approved_row()
        assignment = self.assign(row, self.teacher_a)
        CourseOffering.objects.filter(pk=self.offering().pk).update(instructor=self.teacher_c)  # köhnə sistem
        self.assign(row, self.teacher_b, assignment=assignment)
        self.assertEqual(self.offering().instructor_id, self.teacher_b.pk)

    def test_seminar_teacher_change_reaches_the_journal_after_a_handover(self):
        _task, row = self.approved_row()
        lecture = self.assign(row, self.teacher_a)
        seminar = self.assign(row, self.teacher_b, activity=Activity.SEMINAR, hours=30)
        self.assertIsNotNone(self._share(self.teacher_b))
        self._handover(self.teacher_c)  # tam təhvil A → C
        self.assign(row, self.teacher_c, assignment=lecture)  # kafedra yükü uyğunlaşdırır
        self.assertEqual(self.offering().instructor_id, self.teacher_c.pk)
        self.assign(row, self.teacher_d, activity=Activity.SEMINAR, hours=30, assignment=seminar)
        share = self._share(self.teacher_d)
        self.assertIsNotNone(share)
        self.assertEqual(share.kinds, ["seminar"])
        self.assertIsNone(self._share(self.teacher_b))
        scope = journal_shares.journal_scope(self.teacher_d, self.offering())
        self.assertEqual(scope.kinds, frozenset({"seminar"}))

    def test_load_change_overrides_an_earlier_seminar_handover(self):
        _task, row = self.approved_row()
        self.assign(row, self.teacher_a)
        seminar = self.assign(row, self.teacher_b, activity=Activity.SEMINAR, hours=30)
        self._handover(self.teacher_c, kinds=["seminar"])
        self.assertEqual(self._share(self.teacher_c).kinds, ["seminar"])
        self.assign(row, self.teacher_d, activity=Activity.SEMINAR, hours=30, assignment=seminar)
        self.assertIsNone(self._share(self.teacher_c))
        self.assertEqual(self._share(self.teacher_d).kinds, ["seminar"])
        self.assertEqual(self.offering().instructor_id, self.teacher_a.pk)

    def test_lecturer_change_keeps_old_teacher_seminar_share_and_marks(self):
        _task, row = self.approved_row()
        lecture = self.assign(row, self.teacher_a)
        self.assign(row, self.teacher_a, activity=Activity.SEMINAR, hours=30)
        marks_before = LessonMark.objects.filter(lesson__offering=self.offering()).count()
        self.assign(row, self.teacher_b, assignment=lecture)
        offering = self.offering()
        self.assertEqual(offering.instructor_id, self.teacher_b.pk)
        old = self._share(self.teacher_a)
        self.assertIsNotNone(old)  # A seminarı hələ də keçir — jurnal ondan getmir
        self.assertEqual(old.kinds, ["seminar"])
        self.assertEqual(self._share(self.teacher_b).kinds, ["lecture"])
        self.assertEqual(LessonMark.objects.filter(lesson__offering=offering).count(), marks_before)
