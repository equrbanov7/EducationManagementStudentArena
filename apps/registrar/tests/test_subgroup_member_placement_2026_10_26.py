"""Ana qrupda qalmış tələbə → jurnal sübutu ilə alt qrup (sahib 2026-10-26: «göndərişdə olana baxaraq alt qrupa yığ»).

* Xanaları yalnız bir alt qrupun jurnallarındadırsa — oraya köçür (rəsmi köçürmə xidməti).
* Ana qrupun ÖZ jurnalında datası varsa — toxunulmur (mühazirə ana qrupda ola bilər).
* Xanası yoxdursa — toxunulmur.
* Xarici dil SƏVİYYƏ fənninin xanası sübut sayılmır (səviyyə jurnalı qrupları qarışdırır).
* Ana qrupun BOŞ jurnalı, hədəf alt qrupda həmin fənn yoxdursa, «Jurnal təmizliyi» qərarı ilə düşür — alt qrupda
  ikinci (boş) jurnal açılmır.
"""

from __future__ import annotations

import datetime
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.organizations.models import OrgUnit
from apps.registrar.language_levels import is_level_subject, level_family, level_of
from apps.registrar.models import (
    CourseOffering,
    Enrollment,
    JournalHygieneDecision,
    Lesson,
    LessonMark,
    StudentAcademicRecord,
    Subject,
)
from apps.registrar.subgroup_member_placement import plan, run
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.constants import OrgUnitType
from core.rls import bypass_rls


class LanguageLevelTest(TestCase):
    def test_level_names(self):
        name = "Xarici dildə işgüzar və akademik kommunikasiya-1(elementary)"
        self.assertTrue(is_level_subject(name))
        self.assertEqual(level_of(name), "elementary")
        self.assertEqual(level_of("X (Pre-Intermediate)"), "pre-intermediate")
        self.assertEqual(level_family(name), level_family(name.replace("elementary", "intermediate")))
        self.assertFalse(is_level_subject("Azərbaycan tarixi"))


class SubgroupMemberPlacementTest(SubgroupFixture, TestCase):
    PREFIX = "smp"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.parent = OrgUnit.objects.create(
                organization=cls.org, name="G", slug="smp-g", unit_type=OrgUnitType.GROUP, parent=cls.chair
            )
            for sub in (cls.group1, cls.group2):
                sub.settings = {**(sub.settings or {}), "parent_group": str(cls.parent.pk)}
                sub.save(update_fields=["settings"])
            cls.mover = cls._student("smp_mover", cls.parent)
            cls.lecture = cls._student("smp_lecture", cls.parent)
            cls.idle = cls._student("smp_idle", cls.parent)
            cls.level_only = cls._student("smp_level", cls.parent)
            # Ana qrupun YALNIZ özündə açılan fənni (alt qruplarda yoxdur) — köçürmə onu alt qrupa daşımamalıdır.
            cls.ikt = Subject.objects.create(organization=cls.org, code="SMPIKT", name="İKT", ects=3)
            cls.ikt_parent = CourseOffering.objects.create(
                organization=cls.org, subject=cls.ikt, period=cls.period, group=cls.parent, instructor=cls.teacher
            )
            for student in (cls.mover, cls.lecture, cls.idle, cls.level_only):
                Enrollment.objects.create(organization=cls.org, student=student, offering=cls.ikt_parent)
            cls.level = Subject.objects.create(
                organization=cls.org, code="SMPESP", name="Xarici dil-1(elementary)", ects=3
            )
            cls.level_g2 = CourseOffering.objects.create(
                organization=cls.org, subject=cls.level, period=cls.period, group=cls.group2, instructor=cls.teacher
            )

    def _mark(self, student, offering):
        with bypass_rls():
            enrollment, _ = Enrollment.objects.get_or_create(organization=self.org, student=student, offering=offering)
            lesson = Lesson.objects.create(
                organization=self.org, offering=offering, date=datetime.date(2026, 10, 1), kind="seminar", hours=2
            )
            LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=enrollment)

    def _plan(self):
        with bypass_rls():
            return {item.student_id: item for item in plan(self.org, self.period)}

    def test_statuses(self):
        self._mark(self.mover, self.history_g1)
        self._mark(self.lecture, self.history_g1)
        self._mark(
            self.lecture,
            self.lecture.enrollments.get(offering__group=self.parent, offering__subject=self.math).offering,
        )
        self._mark(self.level_only, self.level_g2)
        items = self._plan()
        self.assertEqual((items[self.mover.pk].status, items[self.mover.pk].target_id), ("place", self.group1.pk))
        self.assertEqual(items[self.lecture.pk].status, "parent_journal_data")
        self.assertEqual(items[self.idle.pk].status, "no_evidence")
        self.assertEqual(items[self.level_only.pk].status, "no_evidence")

    def test_dry_run_writes_nothing(self):
        self._mark(self.mover, self.history_g1)
        with bypass_rls():
            counts, _items = run(self.org, self.period, actor=self.owner, reason="sınaq köçürmə", apply=False)
            record = StudentAcademicRecord.objects.get(student=self.mover)
        self.assertEqual(counts["place"], 1)
        self.assertEqual(record.group_id, self.parent.pk)

    def test_apply_moves_and_drops_orphan_without_new_journal(self):
        self._mark(self.mover, self.history_g1)
        with bypass_rls():
            offerings_before = CourseOffering.objects.filter(organization=self.org, period=self.period).count()
            counts, _items = run(self.org, self.period, actor=self.owner, reason="sınaq köçürmə", apply=True)
            record = StudentAcademicRecord.objects.get(student=self.mover)
            ikt = Enrollment.objects.get(student=self.mover, offering=self.ikt_parent)
            self.assertEqual(record.group_id, self.group1.pk)
            self.assertEqual(ikt.status, Enrollment.Status.DROPPED)
            self.assertTrue(
                JournalHygieneDecision.objects.filter(enrollment=ikt, reason_code="subgroup_placement").exists()
            )
            self.assertFalse(
                CourseOffering.objects.filter(organization=self.org, subject=self.ikt, group=self.group1).exists()
            )
            self.assertEqual(
                CourseOffering.objects.filter(organization=self.org, period=self.period).count(), offerings_before
            )
            active = Enrollment.objects.filter(student=self.mover, status=Enrollment.Status.ENROLLED)
            self.assertFalse(active.filter(offering__group=self.parent).exists())
            self.assertTrue(active.filter(offering=self.history_g1).exists())
        self.assertEqual(counts["offerings_created"], 0)
        self.assertEqual(counts["enrollments_dropped_empty"], 1)

    def test_command_dry_run_prints_counts_only(self):
        self._mark(self.mover, self.history_g1)
        self.owner.is_superuser = True
        self.owner.save(update_fields=["is_superuser"])
        out = StringIO()
        call_command("place_parent_group_students", org=self.org.slug, actor=self.owner.username, stdout=out)
        text = out.getvalue()
        self.assertIn("mode=dry_run", text)
        self.assertIn("place=1", text)
        self.assertNotIn("smp_mover", text)


class PhantomOfferingTest(SubgroupMemberPlacementTest):
    """Reyestrdən əl ilə köçürülən tələbə alt qrupda ana qrupun fənninin boş jurnalını açıb (prod 2026-10-26):
    əmr onu «fənn var» saymır, ləğv edir və növbəti tələbəni ora köçürmür."""

    PREFIX = "smq"

    def test_phantom_from_manual_move_is_cancelled(self):
        from apps.registrar.transfer import transfer_student_group

        self._mark(self.mover, self.history_g1)
        with bypass_rls():
            first = StudentAcademicRecord.objects.select_related("organization", "student", "group").get(
                student=self.idle
            )
            transfer_student_group(
                record=first, new_group=self.group1, period=self.period, by_user=self.owner, reason="əl ilə"
            )
            phantom = CourseOffering.objects.get(organization=self.org, subject=self.ikt, group=self.group1)
            counts, _items = run(self.org, self.period, actor=self.owner, reason="sınaq köçürmə", apply=True)
            phantom.refresh_from_db()
            self.assertFalse(phantom.is_active)
            self.assertFalse(phantom.enrollments.filter(status=Enrollment.Status.ENROLLED).exists())
            mover_ikt = Enrollment.objects.get(student=self.mover, offering=self.ikt_parent)
            self.assertEqual(mover_ikt.status, Enrollment.Status.DROPPED)
        self.assertEqual(counts["phantom_offerings_cancelled"], 1)
        self.assertEqual(counts["offerings_created"], 0)
