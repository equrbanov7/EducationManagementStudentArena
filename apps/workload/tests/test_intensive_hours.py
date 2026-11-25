"""İntensiv kursun saatını ləğvsiz dəyişmək (sahib 2026-11-25).

Real hal: 3 dərs keçilmiş intensiv mühazirə 5 + seminar 5 → mühazirə 10 + seminar 5. Ləğv dərs olanda qadağandır,
ona görə ``intensive_hours`` əməli sətri + bölgünü + jurnalın saat həddini yerində dəyişir.
"""

from __future__ import annotations

import datetime

from django.urls import reverse

from apps.audit.models import AuditLog
from apps.registrar import gradebook
from apps.registrar.models import CourseOffering, Enrollment, LessonKind
from apps.workload.models import TeacherAssignment, TeachingTaskRow
from apps.workload.services import WorkloadDenied, resolve_actor
from apps.workload.services.intensive_hours import change_intensive_hours

from . import test_intensive_2026_10_25 as base
from .test_intensive_2026_10_25 import _IntensiveBase

REASON = "Tədris planına əlavə saat verildi"


class IntensiveHoursTests(_IntensiveBase):
    def setUp(self):
        super().setUp()
        self.result = self._create(lecture_hours=5, seminar_hours=5)
        self.offering = CourseOffering.objects.get(pk=self.result["offering_id"])

    def _change(self, lecture, seminar, *, user=None, reason=REASON):
        return change_intensive_hours(
            organization=self.org,
            actor=resolve_actor(user or self.head, self.org),
            row_id=self.result["row_id"],
            lecture_hours=lecture,
            seminar_hours=seminar,
            reason=reason,
        )

    def _lesson(self, kind, hours, *, passive=False, start="09:00"):
        return gradebook.create_lesson(
            offering=self.offering,
            date=self.today,
            kind=kind,
            hours=hours,
            start_time=datetime.time.fromisoformat(start),
            created_by=self.teacher,
            passive=passive,
        )

    def _hours(self):
        return dict(TeacherAssignment.objects.filter(row_id=self.result["row_id"]).values_list("activity", "hours"))

    def test_success_updates_row_assignments_offering_and_audit(self):
        self._lesson(LessonKind.LECTURE, 2, start="09:00")
        self._lesson(LessonKind.SEMINAR, 2, start="10:30")
        self._lesson(LessonKind.LECTURE, 2, start="12:00")
        enrolled = Enrollment.objects.filter(offering=self.offering).count()
        result = self._change(10, 5)
        self.assertEqual(result["held"], {"lecture": 4, "seminar": 2})
        row = TeachingTaskRow.objects.get(pk=self.result["row_id"])
        self.assertEqual(
            (row.lecture_plan, row.lecture_total, row.seminar_plan, row.seminar_total, row.total_hours),
            (10, 10, 5, 5, 15),
        )
        self.assertEqual(self._hours(), {"lecture": 10, "seminar": 5})
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.lesson_hours, 15)
        self.assertTrue(self.offering.is_active)
        self.assertEqual(self.offering.lessons.count(), 3)
        self.assertEqual(Enrollment.objects.filter(offering=self.offering).count(), enrolled)
        log = AuditLog.objects.filter(reason="workload.intensive_hours_changed").get()
        self.assertEqual(log.resource_id, self.result["row_id"])
        self.assertEqual((log.old_values["lecture"], log.old_values["seminar"]), (5, 5))
        self.assertEqual((log.new_values["lecture"], log.new_values["seminar"]), (10, 5))
        self.assertEqual(log.new_values["reason_text"], REASON)

    def test_zero_removes_and_recreates_activity_assignment(self):
        self._change(10, 0)
        self.assertEqual(self._hours(), {"lecture": 10})
        self._change(10, 4)
        self.assertEqual(self._hours(), {"lecture": 10, "seminar": 4})
        teachers = set(TeacherAssignment.objects.filter(row_id=self.result["row_id"]).values_list("teacher", flat=True))
        self.assertEqual(teachers, {self.teacher.pk})

    def test_below_held_hours_is_rejected(self):
        self._lesson(LessonKind.SEMINAR, 2, start="09:00")
        self._lesson(LessonKind.LAB, 2, start="10:30")  # laboratoriya seminar saatına sayılır
        with self.assertRaises(WorkloadDenied) as ctx:
            self._change(5, 3)
        self.assertEqual(ctx.exception.code, "workload.intensive_hours_below_held")
        self.assertIn("4 saat", ctx.exception.message)
        row = TeachingTaskRow.objects.get(pk=self.result["row_id"])
        self.assertEqual((row.lecture_total, row.seminar_total), (5, 5))
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.lesson_hours, 10)

    def test_passive_lessons_are_not_counted(self):
        self._lesson(LessonKind.LECTURE, 2, start="09:00")
        self._lesson(LessonKind.LECTURE, 2, passive=True, start="10:30")
        result = self._change(2, 5)
        self.assertEqual(result["held"]["lecture"], 2)
        self.assertEqual(self._hours(), {"lecture": 2, "seminar": 5})

    def test_non_distributor_is_denied(self):
        with self.assertRaises(WorkloadDenied) as ctx:
            self._change(10, 5, user=self.teacher)
        self.assertEqual(ctx.exception.code, "workload.forbidden")
        self.assertEqual(self._hours(), {"lecture": 5, "seminar": 5})

    def test_invalid_totals_and_reason(self):
        for lecture, seminar in ((0, 0), (100, 21)):
            with self.assertRaises(WorkloadDenied) as ctx:
                self._change(lecture, seminar)
            self.assertEqual(ctx.exception.code, "workload.intensive_hours")
        with self.assertRaises(WorkloadDenied) as ctx:
            self._change("x", 5)
        self.assertEqual(ctx.exception.code, "workload.invalid_number")
        with self.assertRaises(WorkloadDenied) as ctx:
            self._change(10, 5, reason="qısa")
        self.assertEqual(ctx.exception.code, "workload.intensive_reason")
        self.assertFalse(AuditLog.objects.filter(reason="workload.intensive_hours_changed").exists())

    def test_inactive_offering_is_rejected(self):
        CourseOffering.objects.filter(pk=self.offering.pk).update(is_active=False)
        with self.assertRaises(WorkloadDenied) as ctx:
            self._change(10, 5)
        self.assertEqual(ctx.exception.code, "workload.intensive_inactive")


class IntensiveHoursHttpTests(_IntensiveBase):
    # Modul adı ilə — sinfi birbaşa import etsək pytest onun testlərini burada da toplayardı.
    _client = base.IntensiveHttpTests._client
    _payload = base.IntensiveHttpTests._payload

    def test_hours_action(self):
        client = self._client(self.head)
        url = reverse("workload:action")
        row_id = client.post(url, self._payload("intensive_create")).json()["row_id"]
        payload = {"action": "intensive_hours", "row": row_id, "lecture_hours": "3", "seminar_hours": "10"}
        short = client.post(url, {**payload, "reason": "qısa"})
        self.assertEqual(short.status_code, 400)
        self.assertEqual(short.json()["error"], "workload.intensive_reason")
        response = client.post(url, {**payload, "reason": REASON})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["total"], 13)
        forbidden = self._client(self.teacher).post(url, {**payload, "reason": REASON})
        self.assertEqual(forbidden.status_code, 403)
