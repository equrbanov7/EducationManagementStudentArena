"""Bölgünün struktur qrup bağı + alt qrup nömrəsi (sahib 2026-11-09): ``assign`` yoxlamaları, jurnal xəritəsi,
pay planında «sections», miqrasiya backfill-i."""

from __future__ import annotations

import json

from django.apps import apps as django_apps
from django.urls import reverse

from apps.workload.migrations import __name__ as _migrations_pkg  # noqa: F401 — paket var
from apps.workload.models import TeacherAssignment
from apps.workload.public import teacher_journal_assignments
from apps.workload.services.offering_shares import _assignment_group, plan_for_rows
from apps.workload.services.row_edit import assign_amended
from apps.workload.services.scoping import WorkloadDenied, resolve_actor

from .test_subject_cards_2026_11_09 import CardsBase

AMEND = {"reason": "correction", "note": "Qrup bölgüsü"}


class AssignmentGroupTests(CardsBase):
    code = "AG"

    def _assign_api(self, **kwargs):
        actor = resolve_actor(self.head, self.org)
        kwargs.setdefault("hours", 10)
        kwargs.setdefault("activity", "seminar")
        return assign_amended(row=self.row_i_ml, actor=actor, amend=AMEND, request=None, **kwargs)

    def test_group_is_stored_and_note_defaults_to_group_name(self):
        TeacherAssignment.objects.filter(row=self.row_i_ml).delete()
        saved = self._assign_api(teacher_id=self.habibov.pk, group_id=str(self.g_i.pk), hours=45, sub_number="")
        self.assertEqual((saved.group_id, saved.sub_number, saved.groups_note), (self.g_i.pk, None, self.g_i.name))
        self.assertIs(_assignment_group(saved, self.row_i_ml, self.g_i), True)
        self.assertIs(_assignment_group(saved, self.row_i_ml, self.g_ml), False)
        subject, period = self.stack["subject"].pk, self.stack["period"].pk
        mapping = teacher_journal_assignments(organization=self.org, teacher_id=self.habibov.pk)
        self.assertEqual(mapping.get((subject, period, self.g_i.pk)), {"seminar"})
        self.assertNotIn((subject, period, self.g_ml.pk), mapping)

    def _allow_lab(self):
        from apps.workload.models import TeachingTaskRow

        TeachingTaskRow.objects.filter(pk=self.row_i_ml.pk).update(lab_plan=5, lab_total=10)

    def test_structured_link_beats_a_contradicting_note(self):
        self._allow_lab()
        saved = TeacherAssignment.objects.create(
            organization=self.org,
            row=self.row_i_ml,
            teacher=self.habibov,
            activity="lab",
            hours=1,
            group=self.g_ml,
            groups_note="536 İ",
        )
        self.assertIs(_assignment_group(saved, self.row_i_ml, self.g_ml), True)
        self.assertIs(_assignment_group(saved, self.row_i_ml, self.g_i), False)

    def test_rejections(self):
        TeacherAssignment.objects.filter(row=self.row_i_ml).delete()
        with self.assertRaises(WorkloadDenied) as ctx:
            self._assign_api(teacher_id=self.habibov.pk, group_id=str(self.g_mu.pk))
        self.assertEqual(ctx.exception.code, "workload.group_not_in_row")
        with self.assertRaises(WorkloadDenied) as ctx:
            self._assign_api(teacher_id=self.habibov.pk, group_id=str(self.g_i.pk), sub_number="12")
        self.assertEqual(ctx.exception.code, "workload.sub_number_invalid")
        with self.assertRaises(WorkloadDenied) as ctx:
            self._assign_api(teacher_id=self.habibov.pk, activity="lecture", group_id=str(self.g_i.pk), sub_number="1")
        self.assertEqual(ctx.exception.code, "workload.sub_number_activity")

    def test_endpoint_accepts_group_and_sub_number(self):
        TeacherAssignment.objects.filter(row=self.row_i_ml).delete()
        self.client.force_login(self.head)
        payload = {
            "row_id": str(self.row_i_ml.pk),
            "activity": "seminar",
            "teacher_id": str(self.orucova.pk),
            "hours": 45,
            "group_id": str(self.g_ml.pk),
            "sub_number": "2",
            "amend_reason": "correction",
            "amend_note": "qrup bölgüsü",
        }
        response = self.client.post(
            reverse("workload:assign"), data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        saved = TeacherAssignment.objects.get(pk=response.json()["assignment_id"])
        self.assertEqual((saved.group_id, saved.sub_number), (self.g_ml.pk, 2))
        bad = dict(payload, group_id=str(self.g_mu.pk))
        response = self.client.post(reverse("workload:assign"), data=json.dumps(bad), content_type="application/json")
        self.assertEqual(response.status_code, 400, response.content)

    def test_plan_sections_disambiguate_two_lab_teachers(self):
        row = self._row(
            [self._group("536 LAB")],
            lecture_total=0,
            lecture_plan=0,
            seminar_total=0,
            seminar_plan=0,
            lab_plan=30,
            lab_total=30,
        )
        group = row.groups.get()
        a = TeacherAssignment.objects.create(
            organization=self.org, row=row, teacher=self.habibov, activity="lab", hours=15, sub_number=1
        )
        b = TeacherAssignment.objects.create(
            organization=self.org, row=row, teacher=self.orucova, activity="lab", hours=15, sub_number=2
        )
        plan = plan_for_rows([row], group=group)
        self.assertFalse(plan["ambiguous"])
        self.assertEqual(plan["sections"], {self.habibov.pk: {"lab": [1]}, self.orucova.pk: {"lab": [2]}})
        self.assertEqual(plan["teachers"], {self.habibov.pk: {"lab"}, self.orucova.pk: {"lab"}})
        TeacherAssignment.objects.filter(pk=b.pk).update(sub_number=None)
        self.assertTrue(plan_for_rows([row], group=group)["ambiguous"])
        TeacherAssignment.objects.filter(pk=b.pk).update(sub_number=1)
        self.assertTrue(plan_for_rows([row], group=group)["ambiguous"])  # eyni lab qrupu iki müəllimdə
        TeacherAssignment.objects.filter(pk=a.pk).update(sub_number=None, teacher=None)
        self.assertFalse(plan_for_rows([row], group=group)["ambiguous"])  # vakant sayılmır

    def test_migration_backfill_links_single_group_notes(self):
        from importlib import import_module

        migration = import_module("apps.workload.migrations.0011_assignment_group")
        self._allow_lab()
        exact = TeacherAssignment.objects.create(
            organization=self.org,
            row=self.row_i_ml,
            teacher=self.habibov,
            activity="lab",
            hours=1,
            groups_note=f"{self.g_i.name}",
        )
        two = TeacherAssignment.objects.create(
            organization=self.org,
            row=self.row_i_ml,
            teacher=self.habibov,
            activity="lab",
            hours=1,
            groups_note=f"{self.g_i.name}, {self.g_ml.name}",
        )
        free = TeacherAssignment.objects.create(
            organization=self.org,
            row=self.row_i_ml,
            teacher=self.habibov,
            activity="lab",
            hours=1,
            groups_note="2-ci yarımqrup",
        )
        migration._backfill(django_apps, None)
        exact.refresh_from_db()
        two.refresh_from_db()
        free.refresh_from_db()
        self.assertEqual(exact.group_id, self.g_i.pk)
        self.assertIsNone(two.group_id)
        self.assertIsNone(free.group_id)
        dbi = TeacherAssignment.objects.get(row=self.row_mrk_dbi, teacher=self.orucova)
        self.assertEqual(dbi.group_id, self.g_dbi.pk)  # «536 DBİ» qeydi → bağ
