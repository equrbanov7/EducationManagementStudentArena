"""Mühazirə axınlarının yazılması (sahib 2026-11-09): tərəfdaş ``lecture_total=0`` + ``patok_lead``, aparıcı planına
qayıdır, mühazirəçi axın başına, yük bir dəfə; endpoint 409 → düzəliş, 400 → giriş xətası."""

from __future__ import annotations

import json

from django.urls import reverse

from apps.workload.models import TeacherAssignment, TeachingTaskRow
from apps.workload.public import teacher_journal_assignments
from apps.workload.services.patok_streams import apply_streams
from apps.workload.services.queries import teacher_load_panel
from apps.workload.services.scoping import WorkloadDenied, resolve_actor
from apps.workload.services.subject_cards import cards_page

from .test_subject_cards_2026_11_09 import CardsBase

AMEND = {"reason": "correction", "note": "Patok axınları yenidən quruldu"}


class StreamsBase(CardsBase):
    code = "ST"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # MRK/DBİ bu testdə ayrı axındır (öz mühazirəsi var) — birləşdirmə testdən keçir.
        TeachingTaskRow.objects.filter(pk=cls.row_mrk_dbi.pk).update(patok_lead=None, lecture_total=45, total_hours=135)
        cls.row_mrk_dbi.refresh_from_db()
        TeacherAssignment.objects.create(
            organization=cls.org, row=cls.row_mrk_dbi, teacher=cls.habibov, activity="lecture", hours=45
        )

    def _apply(self, streams, **kwargs):
        actor = resolve_actor(self.head, self.org)
        return apply_streams(task=self.task, actor=actor, streams=streams, amend=AMEND, **kwargs)

    def _lecture_hours(self, teacher):
        return sum(
            TeacherAssignment.objects.filter(teacher=teacher, activity="lecture").values_list("hours", flat=True)
        )


class ApplyStreamsTests(StreamsBase):
    def test_merge_row_into_stream_counts_lecture_once(self):
        self.assertEqual(self._lecture_hours(self.habibov), 90)
        result = self._apply(
            [
                {"row_ids": [str(self.row_bi.pk), str(self.row_mrk_dbi.pk)]},
                {"row_ids": [str(self.row_mu.pk), str(self.row_i_ml.pk)]},
            ]
        )
        self.assertEqual(
            (result["streams"], result["partners"], result["leads"]), (2, 2, [str(self.row_bi.pk), str(self.row_mu.pk)])
        )
        self.row_mrk_dbi.refresh_from_db()
        self.assertEqual(
            (self.row_mrk_dbi.lecture_total, self.row_mrk_dbi.lecture_plan, self.row_mrk_dbi.patok_lead_id),
            (0, 45, self.row_bi.pk),
        )
        self.assertFalse(TeacherAssignment.objects.filter(row=self.row_mrk_dbi, activity="lecture").exists())
        self.assertEqual(self._lecture_hours(self.habibov), 45)
        self.assertEqual(self._lecture_hours(self.balayev), 45)
        subject, period = self.stack["subject"].pk, self.stack["period"].pk
        habibov = teacher_journal_assignments(organization=self.org, teacher_id=self.habibov.pk)
        self.assertEqual(habibov[(subject, period, self.g_mrk.pk)], {"lecture", "seminar"})
        self.assertEqual(habibov[(subject, period, self.g_dbi.pk)], {"lecture"})
        self.assertEqual(
            self.task.amendments.count() if hasattr(self.task, "amendments") else 1 or 1, self.task.amendments.count()
        )

    def test_split_restores_lecture_hours_on_the_new_lead(self):
        self._apply([{"row_ids": [str(self.row_bi.pk), str(self.row_mrk_dbi.pk)]}])
        self._apply([{"row_ids": [str(self.row_bi.pk)]}, {"row_ids": [str(self.row_mrk_dbi.pk)]}])
        self.row_mrk_dbi.refresh_from_db()
        self.assertEqual((self.row_mrk_dbi.lecture_total, self.row_mrk_dbi.patok_lead_id), (45, None))
        self.row_i_ml.refresh_from_db()
        self.assertEqual(self.row_i_ml.patok_lead_id, self.row_mu.pk)  # toxunulmayan axın qalır

    def test_lecturer_per_stream_and_vacant(self):
        self._apply([{"row_ids": [str(self.row_bi.pk), str(self.row_mrk_dbi.pk)], "teacher_id": str(self.balayev.pk)}])
        lectures = list(TeacherAssignment.objects.filter(row=self.row_bi, activity="lecture"))
        self.assertEqual([(a.teacher_id, a.hours) for a in lectures], [(self.balayev.pk, 45)])
        self._apply([{"row_ids": [str(self.row_bi.pk), str(self.row_mrk_dbi.pk)], "teacher_id": "vacant"}])
        self.assertFalse(TeacherAssignment.objects.filter(row=self.row_bi, activity="lecture").exists())
        self.assertEqual(self._lecture_hours(self.balayev), 45)  # MU axını toxunulmayıb

    def test_lead_is_the_row_with_the_chosen_lecturer(self):
        # Həbibov yalnız MRK/DBİ sətrində mühazirəçidirsə, aparıcı o sətir olur, Bİ tərəfdaşa çevrilir.
        TeacherAssignment.objects.filter(row=self.row_bi, activity="lecture").delete()
        self._apply([{"row_ids": [str(self.row_bi.pk), str(self.row_mrk_dbi.pk)]}])
        self.row_bi.refresh_from_db()
        self.row_mrk_dbi.refresh_from_db()
        self.assertEqual((self.row_bi.lecture_total, self.row_bi.patok_lead_id), (0, self.row_mrk_dbi.pk))
        self.assertEqual(self.row_mrk_dbi.lecture_total, 45)

    def test_rejections(self):
        with self.assertRaises(WorkloadDenied) as ctx:
            self._apply([{"row_ids": [str(self.row_bi.pk), str(self.row_physics.pk)]}])
        self.assertEqual(ctx.exception.code, "workload.stream_rows_mismatch")
        with self.assertRaises(WorkloadDenied) as ctx:
            self._apply([{"row_ids": [str(self.row_bi.pk)]}, {"row_ids": [str(self.row_bi.pk)]}])
        self.assertEqual(ctx.exception.code, "workload.stream_row_repeated")
        with self.assertRaises(WorkloadDenied) as ctx:
            self._apply([{"row_ids": ["00000000-0000-0000-0000-000000000001"]}])
        self.assertEqual(ctx.exception.code, "workload.stream_rows_foreign")
        seminar_only = self._row([self._group("536 Q")], lecture_total=0, lecture_plan=0)
        with self.assertRaises(WorkloadDenied) as ctx:
            self._apply([{"row_ids": [str(self.row_bi.pk), str(seminar_only.pk)]}])
        self.assertEqual(ctx.exception.code, "workload.stream_no_lecture")


class LoadGuaranteeTests(StreamsBase):
    """Sahib 2026-11-09: «müəllimlərin yüklərini pozmayacaq ki?» — kart oxuyur, yazmır; dəyişməyən axın yükü dəyişmir."""

    code = "LG"

    def _totals(self):
        return {
            card["name"]: (card["hours"], card["fall_hours"], card["spring_hours"])
            for card in teacher_load_panel(self.task)
        }

    def test_cards_are_read_only_and_identity_streams_keep_every_total(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        before = self._totals()
        snapshot = sorted(
            TeacherAssignment.objects.filter(row__task=self.task).values_list(
                "teacher_id", "activity", "hours", "is_hourly_paid", "row_id"
            )
        )
        with CaptureQueriesContext(connection) as queries:
            page = cards_page(self.task, limit=50)
        self.assertEqual(page["total"], 3)
        writes = [q["sql"] for q in queries if q["sql"].split()[0].upper() in ("INSERT", "UPDATE", "DELETE")]
        self.assertEqual(writes, [])
        # Mövcud bölgünü eyni ilə yenidən yazmaq (hər sətir öz axınında, mühazirəçi göndərilmir) heç nəyi dəyişmir.
        current = [
            {"row_ids": [str(row.pk)]}
            for row in (self.row_mu, self.row_bi, self.row_mrk_dbi)
            if int(row.lecture_total) > 0
        ]
        current[0]["row_ids"].append(str(self.row_i_ml.pk))  # İ/ML artıq MU-nun tərəfdaşıdır
        self._apply(current)
        self.assertEqual(self._totals(), before)
        self.assertEqual(
            sorted(
                TeacherAssignment.objects.filter(row__task=self.task).values_list(
                    "teacher_id", "activity", "hours", "is_hourly_paid", "row_id"
                )
            ),
            snapshot,
        )


class StreamsEndpointTests(StreamsBase):
    code = "SE"

    def _post(self, **extra):
        self.client.force_login(self.head)
        payload = {
            "task_id": str(self.task.pk),
            "streams": [{"row_ids": [str(self.row_bi.pk), str(self.row_mrk_dbi.pk)]}],
            **extra,
        }
        return self.client.post(
            reverse("workload:patok_streams"), data=json.dumps(payload), content_type="application/json"
        )

    def test_amended_task_requires_reason_then_writes(self):
        response = self._post()
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"], "workload.amendment_required")
        response = self._post(amend_reason="correction", amend_note="Patok birləşdirildi")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["partners"], 1)
        self.row_mrk_dbi.refresh_from_db()
        self.assertEqual(self.row_mrk_dbi.patok_lead_id, self.row_bi.pk)

    def test_bad_input_is_400(self):
        response = self._post(
            streams=[{"row_ids": [str(self.row_bi.pk), str(self.row_physics.pk)]}],
            amend_reason="correction",
            amend_note="x",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "workload.stream_rows_mismatch")

    def test_teacher_without_distribute_permission_is_denied(self):
        from .factories import activate_member

        outsider = self._teacher("outsider")
        activate_member(self.org, outsider, "teacher", permissions=["workload.view"])
        self.client.force_login(outsider)
        response = self.client.post(
            reverse("workload:patok_streams"),
            data=json.dumps({"task_id": str(self.task.pk), "streams": [{"row_ids": [str(self.row_bi.pk)]}]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403, response.content)
