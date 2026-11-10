"""Sahib 2026-11-10: «dərs yükünə baxılan yerdə patokları birlikdə yaz, ayrı-ayrı alt-alta yazma».

«Dərs yüküm»də (``group_workload_lines``) eyni patok axınının sətirləri (``patok_lead_id or row_id`` + eyni
semestr) BİR xətdir: qruplar «236 BT, 536 T», fəaliyyətlər cəmlənir, saat = cəm, hər qrupun jurnalı ayrıca.

* aparıcı + tərəfdaş → «Mühazirə 15 · Seminar 30», 45 saat, iki jurnal, aparıcının redaktə keçidi;
* aparıcı sətri başqa müəllimdədir → tərəfdaş(lar) yenə görünür (bir neçəsi varsa öz aralarında birləşir);
* patoksuz sətirlər əvvəlki kimidir; fərqli semestrlər heç vaxt birləşmir;
* ``teacher_workload_rows`` ``patok_lead_id`` verir (əlavə sorğusuz), ekran və Excel ixracı eyni xətti göstərir.
"""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase

from openpyxl import load_workbook

from apps.workload.constants import TaskStatus
from apps.workload.models import TeachingTaskRow
from apps.workload.services import teacher_workload_rows
from apps.workload.services.my_workload_lines import group_workload_lines
from apps.workload.views import teacher_api

from .factories import YEAR
from .test_patok_lead_link_2026_11_08 import _PatokMixin

User = get_user_model()


def _row(row_id, activity, hours, *, groups, lead="", offering="", season="fall", assignment=None, **extra):
    labels = {"lecture": "Mühazirə", "seminar": "Seminar", "lab": "Laboratoriya"}
    return {
        "id": assignment or f"{row_id}-{activity}",
        "row_id": row_id,
        "patok_lead_id": lead,
        "task_id": "t1",
        "chair_id": "c1",
        "chair_name": "Fəlsəfə kafedrası",
        "academic_year": "2026/2027",
        "season": season,
        "season_label": "Payız" if season == "fall" else "Yaz",
        "subject": "Fəlsəfə",
        "groups": groups,
        "activity": activity,
        "activity_label": labels[activity],
        "hours": hours,
        "education_form": "eyani",
        "degree_level": "bachelor",
        "is_hourly_paid": False,
        "offering_id": offering,
        "is_intensive": False,
        **extra,
    }


class PatokLineMergeTests(SimpleTestCase):
    def test_lead_and_partner_merge_into_one_line(self):
        rows = [
            # Tərəfdaş əvvəl gəlsə də aparıcı birinci yazılır.
            _row("P", "seminar", 15, groups="536 T", lead="L", offering="o-536", is_hourly_paid=True),
            _row("L", "lecture", 15, groups="236 BT", offering="o-236"),
            _row("L", "seminar", 15, groups="236 BT", offering="o-236"),
        ]
        lines = group_workload_lines(rows, edit_chair_ids=["c1"])
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertTrue(line["is_patok"])
        self.assertEqual(line["groups"], "236 BT, 536 T")
        self.assertEqual(line["activity_label"], "Mühazirə 15 · Seminar 30")
        self.assertEqual(line["hours"], 45)
        self.assertTrue(line["is_hourly_paid"])
        self.assertEqual(line["row_id"], "L")
        self.assertIn("L", line["edit_url"])
        self.assertEqual(line["row_ids"], ["L", "P"])
        self.assertEqual(sorted(line["assignment_ids"]), ["L-lecture", "L-seminar", "P-seminar"])
        self.assertEqual(
            line["journals"],
            [{"offering_id": "o-236", "label": "236 BT"}, {"offering_id": "o-536", "label": "536 T"}],
        )
        self.assertEqual(line["offering_id"], "o-236")
        self.assertNotIn("patok_lead_id", line)

    def test_partner_only_teacher_still_renders(self):
        # Aparıcı sətir (L) başqa müəllimdədir — iki tərəfdaş öz aralarında bir xətdir, qrup adına görə.
        rows = [
            _row("P2", "seminar", 15, groups="536 T", lead="L", offering="o-536"),
            _row("P1", "seminar", 15, groups="336 A", lead="L", offering="o-336"),
        ]
        lines = group_workload_lines(rows, edit_chair_ids=["c1"])
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual((line["groups"], line["hours"], line["row_id"]), ("336 A, 536 T", 30, "P1"))
        self.assertEqual(line["activity_label"], "Seminar")
        self.assertIn("P1", line["edit_url"])
        self.assertEqual([item["label"] for item in line["journals"]], ["336 A", "536 T"])

        single = group_workload_lines([_row("P2", "seminar", 15, groups="536 T", lead="L", offering="o-536")])
        self.assertEqual(len(single), 1)
        self.assertFalse(single[0]["is_patok"])
        self.assertEqual(single[0]["journals"], [{"offering_id": "o-536", "label": "536 T"}])

    def test_non_patok_rows_are_unchanged(self):
        rows = [
            _row("A", "lecture", 30, groups="631/5K", offering="o-a"),
            _row("A", "seminar", 15, groups="631/5K", offering="o-a"),
            _row("B", "seminar", 15, groups="632/5K"),
        ]
        lines = group_workload_lines(rows)
        self.assertEqual([line["groups"] for line in lines], ["631/5K", "632/5K"])
        first, second = lines
        self.assertEqual(
            (first["activity_label"], first["hours"], first["is_patok"]), ("Mühazirə 30 · Seminar 15", 45, False)
        )
        self.assertEqual(first["journals"], [{"offering_id": "o-a", "label": "631/5K"}])
        self.assertEqual((second["journals"], second["offering_id"], second["edit_url"]), ([], "", ""))

    def test_different_seasons_never_merge(self):
        rows = [
            _row("L", "lecture", 15, groups="236 BT", season="fall"),
            _row("P", "seminar", 15, groups="536 T", lead="L", season="spring"),
        ]
        lines = group_workload_lines(rows)
        self.assertEqual(len(lines), 2)
        self.assertFalse(any(line["is_patok"] for line in lines))

    def test_export_prints_one_row_per_stream(self):
        rows = [
            _row("L", "lecture", 15, groups="236 BT", offering="o-236"),
            _row("L", "seminar", 15, groups="236 BT", offering="o-236"),
            _row("P", "seminar", 15, groups="536 T", lead="L", offering="o-536"),
        ]
        request = RequestFactory().get("/workload/mene/ixrac/")
        request.user = SimpleNamespace(pk=1, is_authenticated=True)
        request.organization = SimpleNamespace(pk=1)
        actor = SimpleNamespace(has=lambda perm: True)
        with (
            mock.patch.object(teacher_api, "actor_for", return_value=actor),
            mock.patch.object(teacher_api, "teacher_workload_rows", return_value=rows),
        ):
            response = teacher_api.my_export(request)
        values = [[cell.value for cell in row] for row in load_workbook(BytesIO(response.content)).active.iter_rows()]
        self.assertEqual(len(values), 3)  # başlıq + bir axın + CƏMİ
        self.assertEqual(values[1][3:6], ["236 BT, 536 T", "Mühazirə 15 · Seminar 30", 45])
        self.assertEqual(values[2][4:6], ["CƏMİ", 45])


class TeacherRowsPatokLeadTests(_PatokMixin, TestCase):
    code = "MWP"

    @classmethod
    def setUpTestData(cls):
        cls._setup_org(status=TaskStatus.DISTRIBUTED)
        cls.teacher = cls._teacher("t")
        cls.lead = cls._row(cls._group("236 BT"), lecture_total=15, seminar=15)
        cls.partner = cls._row(cls._group("536 T"), lecture_total=0, seminar=15)
        cls.plain = cls._row(cls._group("631 K"), lecture_total=30, seminar=15)
        TeachingTaskRow.objects.filter(pk=cls.partner.pk).update(patok_lead=cls.lead)
        cls._assign(cls.lead, cls.teacher, "lecture", 15)
        cls._assign(cls.lead, cls.teacher, "seminar", 15)
        cls._assign(cls.partner, cls.teacher, "seminar", 15)
        cls._assign(cls.plain, cls.teacher, "seminar", 15)

    def test_rows_carry_patok_lead_and_lines_merge(self):
        rows = teacher_workload_rows(organization=self.org, teacher=self.teacher, academic_year=YEAR)
        leads = {row["row_id"]: row["patok_lead_id"] for row in rows}
        self.assertEqual(
            leads, {str(self.lead.pk): "", str(self.partner.pk): str(self.lead.pk), str(self.plain.pk): ""}
        )
        self.assertEqual(sum(row["hours"] for row in rows), 60)  # cəmlər birləşməmiş sətirlərdən

        lines = {line["groups"]: line for line in group_workload_lines(rows)}
        self.assertEqual(set(lines), {"236 BT, 536 T", "631 K"})
        merged = lines["236 BT, 536 T"]
        self.assertEqual((merged["activity_label"], merged["hours"]), ("Mühazirə 15 · Seminar/təcrübi 30", 45))
        self.assertEqual(merged["row_id"], str(self.lead.pk))
        self.assertFalse(lines["631 K"]["is_patok"])

    def test_patok_lead_adds_no_queries(self):
        # Təyinatlar (sətir JOIN — ``patok_lead_id`` sütunu orada) + qruplar prefetch + jurnal açılışları.
        with self.assertNumQueries(3):
            teacher_workload_rows(organization=self.org, teacher=self.teacher, academic_year=YEAR)
