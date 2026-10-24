"""Sahib 2026-10-25: «Fənn 75 saatdır. Patok dərsidir — mühazirədə birdir, amma seminarda bölünür. Müəllimin dərs
yükü 105 saat olsa da, sillabus olaraq 75 saat yazmalıdır.»

Sillabusun plan saatı = fənnin BİR QRUP üçün saatı: (1) qrupun ixtisas planı, (2) yük sətirlərində bir qrupa düşən
pay (birgə mühazirə bir dəfə, seminar/lab bir qrupun payı, bir neçə sətir → növ üzrə ən böyüyü), (3) istənilən plan.
"""

from types import SimpleNamespace

from django.test import TestCase

from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Curriculum, CurriculumSubject
from apps.registrar.plan_hours import plan_hours_for_offering
from apps.registrar.plan_hours_load import merge_group_hours, row_group_hours, workload_hours_by_offering
from core.constants import OrgUnitType

from .factories import make_org, make_row, make_structure, make_task


def _row(**fields):
    base = {
        "union_count": 1,
        "subgroup_count": 1,
        "student_count_text": "",
        "lecture_plan": 0,
        "lecture_total": 0,
        "seminar_plan": 0,
        "seminar_total": 0,
        "lab_plan": 0,
        "lab_total": 0,
    }
    base.update(fields)
    return SimpleNamespace(**base)


class RowGroupHoursUnitTests(TestCase):
    def test_plan_column_is_one_group(self):
        row = _row(subgroup_count=3, lecture_plan=60, lecture_total=60, seminar_plan=30, seminar_total=90)
        self.assertEqual(row_group_hours(row, group_count=5), {"lecture": 60, "seminar": 30})

    def test_total_only_subgroups_divide_exactly(self):
        row = _row(subgroup_count=2, lecture_total=30, seminar_total=40, lab_total=20)
        self.assertEqual(row_group_hours(row, group_count=1), {"lecture": 30, "seminar": 20, "lab": 10})

    def test_total_only_union_is_joint(self):
        row = _row(union_count=5, seminar_total=105)
        self.assertEqual(row_group_hours(row, group_count=5), {"seminar": 105})

    def test_ambiguous_split_stays_joint(self):
        # 30 + 30, iki qrup: seminar 15 + 15 də, birgə 30 da ola bilər → birgə (kafedra düzəldə bilir).
        row = _row(lecture_total=30, seminar_total=30, student_count_text="27\n21")
        self.assertEqual(row_group_hours(row), {"lecture": 30, "seminar": 30})
        # Tam bölünmür → birgə.
        row = _row(lecture_total=10, seminar_total=5, student_count_text="7 5 4")
        self.assertEqual(row_group_hours(row), {"lecture": 10, "seminar": 5})

    def test_group_count_fallback_without_student_text(self):
        row = _row(lecture_total=45, seminar_total=90)
        self.assertEqual(row_group_hours(row, group_count=lambda: 2), {"lecture": 45, "seminar": 45})

    def test_merge_takes_max_per_kind(self):
        merged = merge_group_hours([{"lecture": 30}, {"lecture": 15, "seminar": 15}, {}])
        self.assertEqual(merged, {"lecture": 30, "seminar": 15})


class StreamOfFiveGroupsTests(TestCase):
    """Birgə mühazirə 5 qrup + bölünmüş seminar → sillabus 75, müəllimin yükü 105."""

    def setUp(self):
        self.org = make_org("qku-stream5")
        self.stack = make_structure(self.org, code="S5")
        self.task = make_task(self.org, self.stack["chair"])
        self.groups = [self.stack["group"]] + [
            OrgUnit.objects.create(
                organization=self.org, name=f"S5-23{i}", unit_type=OrgUnitType.GROUP, parent=self.stack["specialty"]
            )
            for i in range(4)
        ]
        self.offerings = [
            CourseOffering.objects.create(
                organization=self.org, subject=self.stack["subject"], period=self.stack["period"], group=group
            )
            for group in self.groups
        ]

    def _load(self):
        # Axın sətri: mühazirə 45 — 5 qrup birlikdə (seminar yoxdur).
        stream = make_row(self.task, self.stack, lecture_total=45, seminar_total=0)
        stream.groups.set(self.groups)
        type(stream).objects.filter(pk=stream.pk).update(union_count=5)
        # Seminar sətri: bizim qrup + qonşu, hər birinə 30 (yalnız cəm idxal olunub: 60).
        seminar = make_row(self.task, self.stack, lecture_total=0, seminar_total=60)
        seminar.groups.set(self.groups[:2])
        type(seminar).objects.filter(pk=seminar.pk).update(seminar_plan=0, student_count_text="25  40")
        return stream, seminar

    def test_syllabus_is_75_while_teacher_load_is_105(self):
        stream, seminar = self._load()
        stream.refresh_from_db()
        seminar.refresh_from_db()
        teacher_load = sum(row.lecture_total + row.seminar_total + row.lab_total for row in (stream, seminar))
        self.assertEqual(teacher_load, 105)
        hours = plan_hours_for_offering(self.offerings[0])
        self.assertEqual(hours, {"lecture": 45, "seminar": 30})
        self.assertEqual(sum(hours.values()), 75)

    def test_group_without_seminar_row_gets_only_the_stream_lecture(self):
        self._load()
        self.assertEqual(plan_hours_for_offering(self.offerings[4]), {"lecture": 45})

    def test_bulk_matches_single(self):
        self._load()
        bulk = workload_hours_by_offering(self.offerings)
        for offering in self.offerings:
            self.assertEqual(bulk[offering.pk], plan_hours_for_offering(offering))

    def test_group_programme_curriculum_wins(self):
        self._load()
        curriculum = Curriculum.objects.create(
            organization=self.org, program=self.stack["program"], admission_year=2026, status="approved"
        )
        CurriculumSubject.objects.create(
            organization=self.org,
            curriculum=curriculum,
            subject=self.stack["subject"],
            semester_number=1,
            lecture_hours=30,
            seminar_hours=45,
        )
        self.assertEqual(plan_hours_for_offering(self.offerings[0]), {"lecture": 30, "seminar": 45})
