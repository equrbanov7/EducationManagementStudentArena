"""Audit 2026-09-28 W2 / W4 — sətir saatı döşəməsi və müəllim dəyişikliyində cədvəl toqquşması.

* W2 — bölünmüş saatdan AZ cəm qəbul edilmir (409), artıq bölgü «tamamlanmış» sayılmır;
* W4 — yük sinxronu açılışın müəllimini dəyişəndə yeni müəllimin cədvəl
  toqquşması hesabata / audit-ə / bölgü cavabına düşür (səssiz ikiqat yük yox).

W1 (göndərilməmiş qaralama) — ``test_audit_2026_09_13_draft_distribution_gate.py``.
"""

from __future__ import annotations

import datetime
import json

from django.test import Client
from django.urls import reverse

from apps.registrar.models import CourseOffering, ScheduleSlot, Subject
from apps.workload.constants import Activity
from apps.workload.models import TeachingTaskRow
from apps.workload.services import WorkloadDenied, balance_for_rows, distribution_readiness, save_row
from apps.workload.services.tasks import TOTAL_BELOW_ASSIGNED

from .test_plan_offering_instructors import _TeacherBase


class RowTotalFloorTest(_TeacherBase):
    code = "A28W2"

    def test_total_below_assigned_hours_is_refused(self):
        task, row = self.approved_row()
        self.assign(row, self.teacher_a, hours=30)
        task.refresh_from_db()

        with self.assertRaises(WorkloadDenied) as ctx:
            save_row(task=task, actor=self.actor(self.chair_head), data={"lecture_total": 10}, row=row)

        self.assertEqual(ctx.exception.code, TOTAL_BELOW_ASSIGNED)
        self.assertEqual(TeachingTaskRow.objects.get(pk=row.pk).lecture_total, 30)

    def test_total_equal_to_assigned_is_accepted(self):
        task, row = self.approved_row()
        self.assign(row, self.teacher_a, hours=20)
        task.refresh_from_db()

        save_row(task=task, actor=self.actor(self.chair_head), data={"lecture_total": 20}, row=row)

        self.assertEqual(TeachingTaskRow.objects.get(pk=row.pk).lecture_total, 20)

    def test_http_row_save_returns_409(self):
        task, row = self.approved_row()
        self.assign(row, self.teacher_a, hours=30)
        client = Client()
        client.force_login(self.chair_head)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = client.post(
            reverse("workload:row_save"),
            data=json.dumps({"task_id": str(task.pk), "row_id": str(row.pk), "lecture_total": 5}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"], TOTAL_BELOW_ASSIGNED)

    def test_over_assignment_is_not_complete(self):
        _task, row = self.approved_row()
        self.assign(row, self.teacher_a, hours=30)
        # Köhnə məlumat: cəm döşəmədən ƏVVƏL bölgünün altına endirilib (DB trigger-i
        # yalnız bölgü yazısını yoxlayır, sətir cəminin azaldılmasını yox).
        TeachingTaskRow.objects.filter(pk=row.pk).update(lecture_total=20)

        balance = balance_for_rows([TeachingTaskRow.objects.get(pk=row.pk)])[str(row.pk)]

        lecture = balance["activities"][str(Activity.LECTURE)]
        self.assertFalse(lecture["is_complete"])
        self.assertTrue(lecture["is_over"])
        self.assertFalse(distribution_readiness(row.task)["is_ready"])


class InstructorChangeTimetableTest(_TeacherBase):
    code = "A28W4"

    def _slot(self, offering, *, instructor=None):
        return ScheduleSlot.objects.create(
            organization=self.org,
            offering=offering,
            weekday=1,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(10, 20),
            instructor=instructor,
        )

    def _busy_elsewhere(self, teacher):
        subject = Subject.objects.create(organization=self.org, code=f"{self.code}X", name="Başqa fənn")
        other = CourseOffering.objects.create(
            organization=self.org,
            subject=subject,
            period=self.stack["period"],
            group=self.stack["group"],
            instructor=teacher,
            lesson_hours=30,
        )
        return self._slot(other)

    def test_changing_the_teacher_reports_the_double_booking(self):
        _task, row = self.approved_row()
        assignment = self.assign(row, self.teacher_a)
        self._slot(self.offering())
        self._busy_elsewhere(self.teacher_b)

        changed = self.assign(row, self.teacher_b, assignment=assignment)

        self.assertEqual(self.offering().instructor_id, self.teacher_b.pk)
        self.assertEqual(changed.offering_sync.get("schedule_conflicts"), 1)

    def test_no_report_when_the_new_teacher_is_free(self):
        _task, row = self.approved_row()
        assignment = self.assign(row, self.teacher_a)
        self._slot(self.offering())

        changed = self.assign(row, self.teacher_b, assignment=assignment)

        self.assertFalse(changed.offering_sync.get("schedule_conflicts"))

    def test_assign_api_warns_about_the_conflict(self):
        _task, row = self.approved_row()
        assignment = self.assign(row, self.teacher_a)
        self._slot(self.offering())
        self._busy_elsewhere(self.teacher_b)
        client = Client()
        client.force_login(self.chair_head)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = client.post(
            reverse("workload:assign"),
            data=json.dumps(
                {
                    "row_id": str(row.pk),
                    "assignment_id": str(assignment.pk),
                    "activity": Activity.LECTURE,
                    "teacher_id": self.teacher_b.pk,
                    "hours": 30,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["schedule_conflicts"], 1)
        self.assertTrue(body["warning"])
