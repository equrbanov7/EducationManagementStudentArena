"""Dərs yükü göndəriş qapıları — QA 2026-09-05 P2-35 / P2-37 reqressiya qapısı."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.workload.services import save_row, submit_task
from apps.workload.services.scoping import WorkloadDenied, resolve_actor

from .factories import activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

OFFICE_PERMS = ["workload.view", "workload.manage", "workload.submit"]


class SubmitGateBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("wgate")
        cls.stack = make_structure(cls.org, code="WG")
        cls.office = User.objects.create_user("wgate.office", "wgate.office@x.test", "pw")
        activate_member(cls.org, cls.office, "teaching_office_head", permissions=OFFICE_PERMS, level=85)

    def actor(self):
        return resolve_actor(self.office, self.org)


class ZeroHourRowTest(SubmitGateBase):
    def test_zero_hour_row_blocks_submission(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        make_row(task, self.stack, lecture_total=0, seminar_total=0, lab_total=0)
        with self.assertRaises(WorkloadDenied) as ctx:
            submit_task(task=task, actor=self.actor())
        self.assertEqual(ctx.exception.code, "workload.rows_zero_hours")

    def test_filled_row_still_submits(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        make_row(task, self.stack)
        result = submit_task(task=task, actor=self.actor())
        self.assertEqual(result["slices"], 1)


class DuplicateRowTest(SubmitGateBase):
    def test_second_identical_row_is_refused(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        first = make_row(task, self.stack)
        with self.assertRaises(WorkloadDenied) as ctx:
            save_row(
                task=task,
                actor=self.actor(),
                data={
                    "subject_id": str(first.subject_id),
                    "specialty_id": str(first.specialty_id),
                    "group_ids": [str(self.stack["group"].pk)],
                    "lecture_total": 30,
                },
            )
        self.assertEqual(ctx.exception.code, "workload.duplicate_row")
        self.assertEqual(task.rows.count(), 1, "dublikat sətir yazılmamalıdır")

    def test_different_group_set_is_allowed(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        first = make_row(task, self.stack)
        row = save_row(
            task=task,
            actor=self.actor(),
            data={
                "subject_id": str(first.subject_id),
                "specialty_id": str(first.specialty_id),
                "group_ids": [],
                "lecture_total": 30,
            },
        )
        self.assertIsNotNone(row.pk)
        self.assertEqual(task.rows.count(), 2)

    def test_editing_the_same_row_is_not_a_duplicate(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        first = make_row(task, self.stack)
        save_row(task=task, actor=self.actor(), row=first, data={"lecture_total": 40})
        self.assertEqual(task.rows.count(), 1)
