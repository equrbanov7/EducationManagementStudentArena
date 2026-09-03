"""Saat balansı, müəllim üzvlüyü və qalıq hesabı."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import OrgUnit
from apps.workload.constants import Activity, TaskStatus
from apps.workload.models import TeacherAssignment
from apps.workload.services import (
    WorkloadDenied,
    assign_teacher,
    balance_for_rows,
    is_assignable_teacher,
    remaining_hours,
    resolve_actor,
    unassign,
)
from core.constants import OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]


class AssignmentBalanceTest(TestCase):
    def setUp(self):
        self.org = make_org("wl-assign")
        self.stack = make_structure(self.org, code="WLB")
        self.head = User.objects.create_user("wlb_head", "wlb_head@x.test", "pw")
        activate_member(
            self.org,
            self.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=self.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        self.teacher = User.objects.create_user("wlb_teacher", "wlb_teacher@x.test", "pw")
        activate_member(
            self.org,
            self.teacher,
            "teacher",
            permissions=TEACHER_PERMS,
            scope_unit=self.stack["chair"],
            level=50,
            scope_type=RoleScopeType.COURSE,
        )
        self.actor = resolve_actor(self.head, self.org)
        self.task = make_task(self.org, self.stack["chair"], created_by=self.head)
        self.row = make_row(self.task, self.stack, lecture_total=30, seminar_total=30)

    def test_assignment_reduces_remaining_hours(self):
        assign_teacher(
            row=self.row,
            actor=self.actor,
            activity=Activity.LECTURE,
            teacher_id=self.teacher.pk,
            hours=20,
        )
        self.assertEqual(remaining_hours(self.row, Activity.LECTURE), 10)
        self.assertEqual(remaining_hours(self.row, Activity.SEMINAR), 30)

    def test_over_allocation_is_blocked(self):
        assign_teacher(
            row=self.row,
            actor=self.actor,
            activity=Activity.LECTURE,
            teacher_id=self.teacher.pk,
            hours=20,
        )
        with self.assertRaises(WorkloadDenied) as ctx:
            assign_teacher(
                row=self.row,
                actor=self.actor,
                activity=Activity.LECTURE,
                teacher_id=None,
                hours=11,
            )
        self.assertEqual(ctx.exception.code, "workload.hours_exceeded")
        self.assertEqual(TeacherAssignment.objects.filter(row=self.row).count(), 1)

    def test_zero_or_negative_hours_are_rejected(self):
        with self.assertRaises(WorkloadDenied) as ctx:
            assign_teacher(row=self.row, actor=self.actor, activity=Activity.LECTURE, teacher_id=None, hours=0)
        self.assertEqual(ctx.exception.code, "workload.hours_positive")

    def test_vacant_assignment_is_allowed(self):
        assignment = assign_teacher(
            row=self.row, actor=self.actor, activity=Activity.SEMINAR, teacher_id=None, hours=30
        )
        self.assertTrue(assignment.is_vacant)

    def test_first_assignment_moves_task_to_distributing(self):
        self.assertEqual(self.task.status, TaskStatus.DRAFT)
        assign_teacher(
            row=self.row,
            actor=self.actor,
            activity=Activity.LECTURE,
            teacher_id=self.teacher.pk,
            hours=5,
        )
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DISTRIBUTING)

    def test_teacher_from_another_chair_is_not_assignable(self):
        other_chair = OrgUnit.objects.create(
            organization=self.org,
            name="Yad kafedra",
            slug="wl-assign-other",
            unit_type=OrgUnitType.CHAIR,
            parent=self.stack["faculty"],
        )
        outsider = User.objects.create_user("wlb_outsider", "wlb_out@x.test", "pw")
        activate_member(
            self.org,
            outsider,
            "teacher_other",
            permissions=TEACHER_PERMS,
            scope_unit=other_chair,
            level=50,
            scope_type=RoleScopeType.COURSE,
        )
        self.assertFalse(is_assignable_teacher(self.org, self.stack["chair"], outsider))
        with self.assertRaises(WorkloadDenied) as ctx:
            assign_teacher(
                row=self.row,
                actor=self.actor,
                activity=Activity.LECTURE,
                teacher_id=outsider.pk,
                hours=5,
            )
        self.assertEqual(ctx.exception.code, "workload.teacher_not_in_chair")

    def test_balance_map_reports_completion(self):
        assign_teacher(
            row=self.row,
            actor=self.actor,
            activity=Activity.LECTURE,
            teacher_id=self.teacher.pk,
            hours=30,
        )
        balance = balance_for_rows([self.row])[str(self.row.pk)]
        self.assertTrue(balance["activities"]["lecture"]["is_complete"])
        self.assertFalse(balance["teaching_complete"])
        assign_teacher(
            row=self.row,
            actor=self.actor,
            activity=Activity.SEMINAR,
            teacher_id=self.teacher.pk,
            hours=30,
        )
        balance = balance_for_rows([self.row])[str(self.row.pk)]
        self.assertTrue(balance["teaching_complete"])

    def test_unassign_frees_hours(self):
        assignment = assign_teacher(
            row=self.row,
            actor=self.actor,
            activity=Activity.LECTURE,
            teacher_id=self.teacher.pk,
            hours=30,
        )
        unassign(assignment=assignment, actor=self.actor)
        self.assertEqual(remaining_hours(self.row, Activity.LECTURE), 30)
