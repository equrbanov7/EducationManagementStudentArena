"""Recorded hours survive handover without changing the official allocation."""

import datetime as dt

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.registrar.models import CourseOffering, Lesson, TeachingHandover
from apps.registrar.public import recorded_teaching_hours
from core.constants import RoleScopeType
from core.rls import bypass_rls

from ..constants import Activity, TaskStatus
from ..models import TeacherAssignment
from ..public import build_my_workload_context
from ..services.recorded_hours import teacher_recorded_hours
from ..services.scoping import resolve_actor
from ..views.teacher_api import my_rows
from .factories import TEACHER_PERMS, YEAR, activate_member, make_org, make_row, make_structure, make_task


class RecordedHoursTests(TestCase):
    def setUp(self):
        self.scope = bypass_rls()
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)
        self.org = make_org("recorded-hours")
        self.stack = make_structure(self.org)
        self.stack["subject"].chair_unit = self.stack["chair"]
        self.stack["subject"].save(update_fields=["chair_unit"])
        User = get_user_model()
        self.old = User.objects.create_user("recorded-old", first_name="Old", last_name="Teacher")
        self.new = User.objects.create_user("recorded-new", first_name="New", last_name="Teacher")
        for teacher in (self.old, self.new):
            activate_member(self.org, teacher, "teacher", permissions=TEACHER_PERMS)
        self.offering = CourseOffering.objects.create(
            organization=self.org,
            subject=self.stack["subject"],
            period=self.stack["period"],
            group=self.stack["group"],
            instructor=self.new,
        )
        self.record = TeachingHandover.objects.create(
            organization=self.org,
            offering=self.offering,
            from_instructor=self.old,
            to_instructor=self.new,
            from_instructor_name="Old Teacher",
            to_instructor_name="New Teacher",
            reason="Verified handover",
        )
        self.day = dt.date(2026, 10, 1)
        self.lesson("lecture", self.old, 2)
        self.lesson("seminar", self.old, 3)
        self.lesson("lab", self.new, 4)
        self.lesson("lecture", None, 6)
        Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date=timezone.localdate() + dt.timedelta(days=10),
            kind="lecture",
            hours=20,
            instructor=self.old,
        )

    def lesson(self, kind, teacher, hours):
        return Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date=self.day,
            kind=kind,
            instructor=teacher,
            hours=hours,
            created_by=self.new,
        )

    def actor(self, teacher=None):
        return resolve_actor(teacher or self.old, self.org)

    def test_explicit_teacher_hours_survive_owner_changes_and_revert(self):
        initial = recorded_teaching_hours(actor=self.actor(), as_of=dt.date(2026, 10, 28))
        self.assertEqual(len(initial), 1)
        self.assertEqual(initial[0]["hours"], {"lecture": 2, "seminar": 3})
        self.assertEqual(initial[0]["total_hours"], 5)
        self.assertEqual(recorded_teaching_hours(actor=self.actor(), as_of=dt.date(2099, 1, 1))[0]["total_hours"], 5)
        self.assertEqual(initial[0]["unknown_hours"], 6)
        self.assertEqual(initial[0]["current_teacher"], "New Teacher")
        CourseOffering.objects.filter(pk=self.offering.pk).update(instructor=self.old)
        TeachingHandover.objects.filter(pk=self.record.pk).update(reverted_at=timezone.now())
        after = recorded_teaching_hours(actor=self.actor(), as_of=dt.date(2026, 10, 28))[0]
        self.assertEqual(after["hours"], initial[0]["hours"])
        self.assertEqual(after["unknown_hours"], 6)
        self.assertTrue(after["history"][0]["reverted"])
        self.assertEqual(after["current_teacher"], "Old Teacher")

    def test_multiple_group_and_split_assignments_do_not_multiply_lessons(self):
        task = make_task(self.org, self.stack["chair"], status=TaskStatus.DISTRIBUTED)
        row = make_row(task, self.stack)
        row.groups.add(self.stack["specialty"])
        for hours in (10, 20):
            TeacherAssignment.objects.create(
                organization=self.org,
                row=row,
                teacher=self.old,
                activity=Activity.LECTURE,
                hours=hours,
            )
        request = RequestFactory().get("/", {"year": YEAR})
        request.user, request.organization = self.old, self.org
        data = build_my_workload_context(request, organization=self.org, academic_year=YEAR)
        self.assertEqual(data["summary"]["total_hours"], 30)
        self.assertEqual(data["recorded_hours"]["total_hours"], 5)
        self.assertEqual(len(data["recorded_hours"]["rows"]), 1)
        self.assertEqual(TeacherAssignment.objects.filter(teacher=self.old).count(), 2)

    def test_only_historical_work_still_renders_without_official_assignment(self):
        request = RequestFactory().get("/")
        request.user = self.old
        data = build_my_workload_context(request, organization=self.org)
        self.assertEqual(data["years"], [YEAR])
        self.assertEqual(data["rows"], [])
        self.assertEqual(data["recorded_hours"]["total_hours"], 5)
        self.assertEqual(teacher_recorded_hours(self.actor(), season="spring")["rows"], [])
        self.assertEqual(teacher_recorded_hours(self.actor(), season="fall")["total_hours"], 5)
        html = render_to_string(
            "accounts/profile/sections/_my_workload.html",
            {
                "allowed_sections": ["my-workload"],
                "my_workload_section": data,
            },
        )
        self.assertIn("Old Teacher → New Teacher", html)
        self.assertIn("Müəllifi dəqiqləşdirilməmiş saat", html)

    def test_self_cannot_query_colleague_and_report_scope_cannot_borrow_other_chair(self):
        with self.assertRaises(PermissionDenied):
            recorded_teaching_hours(actor=self.actor(), teacher_id=self.new.pk)
        manager = get_user_model().objects.create_user("recorded-chair")
        activate_member(
            self.org,
            manager,
            "reporter",
            permissions=["workload.report"],
            scope_unit=self.stack["chair"],
            scope_type=RoleScopeType.UNIT,
        )
        actor = self.actor(manager)
        self.assertEqual(len(recorded_teaching_hours(actor=actor, teacher_id=self.old.pk)), 1)
        other = make_structure(self.org, code="OTHER")
        self.stack["subject"].chair_unit = other["chair"]
        self.stack["subject"].save(update_fields=["chair_unit"])
        self.assertEqual(recorded_teaching_hours(actor=actor, teacher_id=self.old.pk), [])

    def test_foreign_tenant_same_teacher_is_never_returned(self):
        other = make_org("recorded-foreign")
        stack = make_structure(other, code="FOREIGN")
        activate_member(other, self.old, "teacher", permissions=TEACHER_PERMS)
        foreign = CourseOffering.objects.create(
            organization=other,
            subject=stack["subject"],
            period=stack["period"],
            instructor=self.old,
        )
        Lesson.objects.create(
            organization=other, offering=foreign, date=self.day, kind="lecture", hours=30, instructor=self.old
        )
        data = recorded_teaching_hours(actor=self.actor())
        self.assertEqual([r["offering_id"] for r in data], [str(self.offering.pk)])
        self.assertEqual(data[0]["total_hours"], 5)

    def test_json_refresh_uses_same_safe_html_and_permission_gate(self):
        request = RequestFactory().get(reverse("workload:my_rows"), {"year": YEAR, "season": "fall"})
        request.user, request.organization = self.old, self.org
        response = my_rows(request)
        import json

        data = json.loads(response.content)
        self.assertEqual(data["recorded_hours"]["total_hours"], 5)
        self.assertEqual(data["years"], [YEAR])
        self.assertIn("Old Teacher → New Teacher", data["recorded_hours_html"])
        self.assertNotIn("student", data["recorded_hours"]["rows"][0])
