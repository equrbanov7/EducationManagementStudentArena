"""Review 2026-11-26: «Bölgü sehrbazı»nın yazdığı ``lab_group_count`` bütün çarpan oxucularında nəzərə alınır.

Tipik nəticə: lab planı 30, lab cəmi 120, alt qrup 2, lab qrupu 4. Əvvəl ``overcount_detect`` bunu «plan aşımı»
(30 × 2 = 60 < 120) sayırdı, sillabus planı (``plan_hours_load``) isə qrupa 60 lab saatı yazırdı.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase

from apps.registrar.plan_hours_load import row_group_hours, section_count
from apps.workload.services.offering_rules import per_group_hours
from apps.workload.services.overcount_detect import RowInfo, find_plan_overrun, row_multiplier

from .factories import make_org


def _row(**extra):
    fields = {
        "subject_id": None,
        "union_count": 1,
        "subgroup_count": 2,
        "lab_group_count": 4,
        "lecture_plan": 30,
        "lecture_total": 30,
        "seminar_plan": 30,
        "seminar_total": 60,
        "lab_plan": 30,
        "lab_total": 120,
        "student_count_text": "",
    }
    fields.update(extra)
    return SimpleNamespace(**fields)


def _info(row):
    return RowInfo(
        row=row,
        chair_id="c",
        chair_name="K",
        task_status="distributed",
        subject="Fizika",
        key="fizika",
        groups=frozenset(),
        group_names={},
        source="manual",
        hours={"lecture": row.lecture_total, "seminar": row.seminar_total, "lab": row.lab_total},
        assignments=[],
    )


class LabMultiplierTests(SimpleTestCase):
    def test_row_multiplier_prefers_lab_group_count(self):
        row = _row()
        self.assertEqual((row_multiplier(row, "seminar"), row_multiplier(row, "lab")), (2, 4))
        self.assertEqual(row_multiplier(_row(lab_group_count=0), "lab"), 2)

    def test_per_group_hours_from_totals(self):
        self.assertEqual(per_group_hours(_row(lab_plan=0, seminar_plan=0))["lab"], 30)
        self.assertEqual(_info(_row(lab_plan=0)).per_group("lab"), 30)

    def test_syllabus_plan_hours_use_lab_groups(self):
        self.assertEqual(section_count(_row(), kind="lab"), (4, True))
        self.assertEqual(section_count(_row(), kind="seminar"), (2, True))
        self.assertEqual(row_group_hours(_row(lab_plan=0, seminar_plan=0)), {"lecture": 30, "seminar": 30, "lab": 30})


class PlanOverrunTests(TestCase):
    def test_wizard_result_is_not_a_plan_overrun(self):
        org = make_org("labmult-1126")
        self.assertEqual(find_plan_overrun(org, [_info(_row())]), [])
        found = find_plan_overrun(org, [_info(_row(lab_group_count=0))])
        self.assertEqual([(item["activity"], item["limit"]) for item in found], [("lab", 60)])
