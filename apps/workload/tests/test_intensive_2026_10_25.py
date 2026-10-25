"""«İntensiv kurs» — dərs yükü qatı (sahib 2026-10-25).

* bir addım: tapşırıq sətri (``row_kind=intensive``) + müəllim bölgüsü + qrupsuz jurnal + qeydiyyat;
* müəllimin «Mənim dərs yüküm»ündə görünür (sənəd hələ qaralama olsa da) və jurnal keçidi intensiv açılışdır;
* ümumi sətir/bölgü redaktoru intensiv sətrə yazmır;
* HTTP: ``/ders-yuku/emel/`` (intensive_preview / intensive_create / intensive_cancel) + axtarış endpoint-i,
  səlahiyyətsiz istifadəçi üçün fail-closed;
* jurnal: cədvəlsiz kursda bir gündə bir neçə dərs, səbəb soruşulmur; kurs aralığından kənar tarix — rədd.
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import Membership
from apps.registrar import gradebook, journal_activation
from apps.registrar.models import (
    CourseFormat,
    CourseOffering,
    Curriculum,
    Enrollment,
    LessonKind,
    StudentAcademicRecord,
)
from apps.workload.constants import RowKind, TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTaskRow
from apps.workload.services import WorkloadDenied, assign_teacher, resolve_actor, save_row, teacher_workload_rows
from apps.workload.services.intensive import cancel_intensive, create_intensive
from core.constants import RoleScopeType

from .factories import TEACHER_PERMS, YEAR, activate_member, make_org, make_structure

User = get_user_model()
CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]


class _IntensiveBase(TestCase):
    def setUp(self):
        self.org = make_org("wl-intensive")
        self.stack = make_structure(self.org, code="INT")
        self.chair = self.stack["chair"]
        self.head = User.objects.create_user("int_head", "ih@x.test", "pw")
        activate_member(
            self.org, self.head, "chair_head", permissions=CHAIR_PERMS, scope_unit=self.chair, level=70,
            scope_type=RoleScopeType.UNIT,
        )  # fmt: skip
        self.teacher = User.objects.create_user("int_t", "it@x.test", "pw", first_name="Nərmin", last_name="Quliyeva")
        activate_member(
            self.org, self.teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=self.chair,
            scope_type=RoleScopeType.UNIT,
        )  # fmt: skip
        self.curriculum = Curriculum.objects.create(
            organization=self.org, program=self.stack["program"], admission_year=2025
        )
        self.student = self._student("int_s1")
        self.today = timezone.localdate()

    def _student(self, username):
        user = User.objects.create_user(username, f"{username}@x.test", "pw", first_name="Aytac", last_name="Ələkbərli")
        Membership.objects.create(
            user=user, organization=self.org, role=self.org.roles.get(name="student"), is_primary=True, is_active=True
        )
        StudentAcademicRecord.objects.create(
            organization=self.org,
            student=user,
            program=self.stack["program"],
            curriculum=self.curriculum,
            group=self.stack["group"],
            admission_year=2025,
        )
        return user

    def _create(self, actor_user=None, **kwargs):
        params = {
            "organization": self.org,
            "actor": resolve_actor(actor_user or self.head, self.org),
            "chair_id": str(self.chair.pk),
            "subject_id": str(self.stack["subject"].pk),
            "teacher_id": str(self.teacher.pk),
            "student_ids": [str(self.student.pk)],
            "lecture_hours": 4,
            "seminar_hours": 6,
            "starts_on": (self.today - datetime.timedelta(days=2)).isoformat(),
            "ends_on": (self.today + datetime.timedelta(days=5)).isoformat(),
            "note": "Yenidən tədris",
        }
        params.update(kwargs)
        return create_intensive(**params)


class IntensiveWorkloadTests(_IntensiveBase):
    def test_one_step_creates_row_assignments_offering_enrollment(self):
        result = self._create()
        row = TeachingTaskRow.objects.get(pk=result["row_id"])
        self.assertEqual(row.row_kind, RowKind.INTENSIVE)
        self.assertEqual(row.task.academic_year, YEAR)
        self.assertEqual(row.task.status, TaskStatus.DRAFT)
        self.assertEqual((row.lecture_total, row.seminar_total, row.total_hours), (4, 6, 10))
        self.assertEqual(row.groups.count(), 0)
        hours = dict(TeacherAssignment.objects.filter(row=row).values_list("activity", "hours"))
        self.assertEqual(hours, {"lecture": 4, "seminar": 6})
        offering = row.intensive_offering
        self.assertEqual(offering.course_format, CourseFormat.INTENSIVE)
        self.assertEqual((offering.instructor_id, offering.lesson_hours), (self.teacher.pk, 10))
        enrollment = Enrollment.objects.get(offering=offering, student=self.student)
        self.assertEqual(enrollment.source_group_id, self.stack["group"].pk)

    def test_teacher_sees_intensive_load_even_in_draft_task(self):
        result = self._create()
        rows = teacher_workload_rows(organization=self.org, teacher=self.teacher, academic_year=YEAR)
        self.assertEqual({row["offering_id"] for row in rows}, {result["offering_id"]})
        self.assertTrue(all(row["is_intensive"] for row in rows))
        self.assertEqual(sum(row["hours"] for row in rows), 10)

    def test_generic_editors_refuse_intensive_row(self):
        result = self._create()
        row = TeachingTaskRow.objects.select_related("task").get(pk=result["row_id"])
        actor = resolve_actor(self.head, self.org)
        with self.assertRaises(WorkloadDenied) as ctx:
            save_row(task=row.task, actor=actor, data={"lecture_total": 30}, row=row)
        self.assertEqual(ctx.exception.code, "workload.intensive_row")
        with self.assertRaises(WorkloadDenied):
            assign_teacher(row=row, actor=actor, activity="lecture", teacher_id=self.teacher.pk, hours=1)

    def test_teacher_without_distribute_cannot_create(self):
        with self.assertRaises(WorkloadDenied) as ctx:
            self._create(actor_user=self.teacher)
        self.assertEqual(ctx.exception.code, "workload.forbidden")
        self.assertFalse(CourseOffering.objects.filter(course_format=CourseFormat.INTENSIVE).exists())

    def test_invalid_input_rolls_back_everything(self):
        with self.assertRaises(WorkloadDenied) as ctx:
            self._create(ends_on=(self.today - datetime.timedelta(days=5)).isoformat())
        self.assertEqual(ctx.exception.code, "workload.intensive_dates")
        self.assertFalse(TeachingTaskRow.objects.filter(row_kind=RowKind.INTENSIVE).exists())
        self.assertFalse(CourseOffering.objects.filter(course_format=CourseFormat.INTENSIVE).exists())

    def test_journal_allows_several_lessons_a_day_without_reason(self):
        offering = CourseOffering.objects.get(pk=self._create()["offering_id"])
        for start, end in (("09:00", "10:20"), ("10:30", "11:50"), ("12:00", "13:20")):
            reason, error = journal_activation.check_manual_lesson(
                offering, date=self.today, start_time=start, hours=2, raw_reason=""
            )
            self.assertEqual((reason, error), ("", ""))
            gradebook.create_lesson(
                offering=offering,
                date=self.today,
                kind=LessonKind.SEMINAR,
                hours=2,
                start_time=datetime.time.fromisoformat(start),
                end_time=datetime.time.fromisoformat(end),
                created_by=self.teacher,
            )
        self.assertEqual(offering.lessons.count(), 3)
        with self.assertRaises(gradebook.LessonRuleError):
            gradebook.create_lesson(
                offering=offering,
                date=self.today - datetime.timedelta(days=3),
                kind=LessonKind.SEMINAR,
                hours=2,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(10, 20),
                created_by=self.teacher,
            )

    def test_cancel_removes_row_and_deactivates_journal(self):
        result = self._create()
        cancel_intensive(organization=self.org, actor=resolve_actor(self.head, self.org), row_id=result["row_id"])
        self.assertFalse(TeachingTaskRow.objects.filter(pk=result["row_id"]).exists())
        self.assertFalse(CourseOffering.objects.get(pk=result["offering_id"]).is_active)


class IntensiveHttpTests(_IntensiveBase):
    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _payload(self, action):
        return {
            "action": action,
            "chair": str(self.chair.pk),
            "subject": str(self.stack["subject"].pk),
            "teacher": str(self.teacher.pk),
            "students": [str(self.student.pk)],
            "lecture_hours": "0",
            "seminar_hours": "10",
            "starts_on": self.today.isoformat(),
            "ends_on": (self.today + datetime.timedelta(days=4)).isoformat(),
            "note": "Akademik fərq",
        }

    def test_preview_create_and_lookup(self):
        client = self._client(self.head)
        url = reverse("workload:action")
        preview = client.post(url, self._payload("intensive_preview"))
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual([item["status"] for item in preview.json()["students"]], ["ok"])
        created = client.post(url, self._payload("intensive_create"))
        self.assertEqual(created.status_code, 200, created.content)
        self.assertTrue(TeachingTaskRow.objects.filter(pk=created.json()["row_id"]).exists())
        lookup = client.get(
            reverse("workload:intensive_lookup"), {"kind": "students", "chair": str(self.chair.pk), "q": "Ələkbərli"}
        )
        self.assertEqual(lookup.status_code, 200)
        self.assertEqual([item["id"] for item in lookup.json()["results"]], [str(self.student.pk)])
        rows = client.get(reverse("workload:rows"), {"chair": str(self.chair.pk), "year": YEAR})
        self.assertEqual(rows.status_code, 200)
        intensive_rows = [row for row in rows.json()["rows"] if row["intensive"]]
        self.assertEqual(len(intensive_rows), 1)
        self.assertIn("/", intensive_rows[0]["intensive"]["journal_url"])

    def test_validation_error_is_400_and_teacher_is_403(self):
        payload = self._payload("intensive_create")
        payload["note"] = ""
        response = self._client(self.head).post(reverse("workload:action"), payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "workload.intensive_note")
        teacher = self._client(self.teacher)
        self.assertEqual(teacher.post(reverse("workload:action"), self._payload("intensive_create")).status_code, 403)
        lookup = teacher.get(reverse("workload:intensive_lookup"), {"kind": "students", "chair": str(self.chair.pk)})
        self.assertEqual(lookup.status_code, 403)
