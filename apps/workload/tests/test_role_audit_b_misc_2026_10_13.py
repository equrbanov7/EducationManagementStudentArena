"""Rol auditi 2026-10-13 B18 — iş yükü bildirişləri və viza əhatəsi AÇARLA, rol adı ilə yox.

* «Təsdiq gözləyir» (`workload_slice_submitted`) yalnız `workload.approve` daşıyanlara gedir —
  açarsız dekan müavini / koordinator almır (əvvəl rol adı ilə alırdı).
* Fakültə səviyyəsində təsdiqləyən yoxdursa — açarı daşıyan mərkəzi rol (dilim səssiz qalmır).
* Viza əhatəsi: ixtisası əhatə edən UNIT rolu `workload.review` daşıyırsa «baxan var» — rol adı
  istənilən ola bilər (redaktorda açar verilən rol); mərkəzi baxış rolu əhatə sayılmır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.constants import RoleScopeType

from ..models import TaskFacultySlice
from ..services import WorkloadDenied, approve_slice, resolve_actor, submit_task
from .factories import activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

OFFICE_PERMS = ["workload.view", "workload.manage", "workload.submit"]
DEAN_PERMS = ["workload.view", "workload.approve"]
VIEW_ONLY = ["workload.view"]
REVIEW_PERMS = ["workload.view", "workload.review"]


def _events(user):
    from apps.notifications.models import InAppNotification

    return [n.metadata.get("event") for n in InAppNotification.objects.filter(recipient=user)]


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("rab18")
        cls.stack = make_structure(cls.org, code="RB")
        cls.office = User.objects.create_user("rab18.office", "o@x.test", "pw")
        activate_member(cls.org, cls.office, "teaching_office_head", permissions=OFFICE_PERMS, level=85)

    def _unit_member(self, username, role_name, permissions, unit, level=60):
        user = User.objects.create_user(username, f"{username}@x.test", "pw")
        activate_member(
            self.org,
            user,
            role_name,
            permissions=permissions,
            scope_unit=unit,
            scope_type=RoleScopeType.UNIT,
            level=level,
        )
        return user

    def _submit(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        make_row(task, self.stack)
        submit_task(task=task, actor=resolve_actor(self.office, self.org))
        task.refresh_from_db()
        return task, TaskFacultySlice.objects.get(task=task)


class SliceSubmittedRecipientsTest(_Base):
    def test_only_approve_holders_are_notified(self):
        dean = self._unit_member("rab18.dean", "dean", DEAN_PERMS, self.stack["faculty"], level=70)
        vice = self._unit_member("rab18.vice", "vice_dean", VIEW_ONLY, self.stack["faculty"], level=65)
        coord = self._unit_member("rab18.coord", "program_coordinator", VIEW_ONLY, self.stack["specialty"], level=45)
        self._submit()
        self.assertIn("workload_slice_submitted", _events(dean))
        # Əvvəl rol ADI ilə (FACULTY_ACTOR_ROLES) bu ikisi də alırdı.
        self.assertNotIn("workload_slice_submitted", _events(vice))
        self.assertNotIn("workload_slice_submitted", _events(coord))

    def test_renamed_role_with_the_key_is_notified(self):
        """Redaktorda `workload.approve` verilən başqa adlı fakültə rolu da alıcıdır."""
        approver = self._unit_member("rab18.approver", "faculty_approver", DEAN_PERMS, self.stack["faculty"])
        self._submit()
        self.assertIn("workload_slice_submitted", _events(approver))

    def test_org_wide_approver_is_fallback_when_faculty_has_none(self):
        rector = User.objects.create_user("rab18.rector", "r@x.test", "pw")
        activate_member(self.org, rector, "rector", permissions=["workload.*"], level=95)
        self._submit()
        self.assertIn("workload_slice_submitted", _events(rector))

    def test_org_wide_approver_not_spammed_when_dean_exists(self):
        self._unit_member("rab18.dean2", "dean", DEAN_PERMS, self.stack["faculty"], level=70)
        rector = User.objects.create_user("rab18.rector2", "r2@x.test", "pw")
        activate_member(self.org, rector, "rector", permissions=["workload.*"], level=95)
        self._submit()
        self.assertNotIn("workload_slice_submitted", _events(rector))


class VisaCoverageByKeyTest(_Base):
    def test_renamed_unit_reviewer_counts_as_coverage(self):
        """Rol adı köhnə `COORDINATOR_ROLES`-da yoxdur, amma açar var → viza tələb olunur."""
        dean = self._unit_member("rab18.vdean", "faculty_dean", DEAN_PERMS, self.stack["faculty"], level=70)
        self._unit_member("rab18.visa", "visa_officer", REVIEW_PERMS, self.stack["specialty"], level=45)
        _task, slice_obj = self._submit()
        with self.assertRaises(WorkloadDenied) as ctx:
            approve_slice(slice_obj=slice_obj, actor=resolve_actor(dean, self.org))
        self.assertEqual(ctx.exception.code, "workload.visa_missing")

    def test_named_coordinator_without_key_is_not_coverage(self):
        dean = self._unit_member("rab18.vdean2", "faculty_dean", DEAN_PERMS, self.stack["faculty"], level=70)
        self._unit_member("rab18.coordnokey", "program_coordinator", VIEW_ONLY, self.stack["specialty"], level=45)
        _task, slice_obj = self._submit()
        result = approve_slice(slice_obj=slice_obj, actor=resolve_actor(dean, self.org))
        self.assertEqual(result["slice_status"], "approved")

    def test_org_wide_reviewer_does_not_lock_every_slice(self):
        dean = self._unit_member("rab18.vdean3", "faculty_dean", DEAN_PERMS, self.stack["faculty"], level=70)
        overseer = User.objects.create_user("rab18.overseer", "ov@x.test", "pw")
        activate_member(self.org, overseer, "vice_rector", permissions=REVIEW_PERMS, level=90)
        _task, slice_obj = self._submit()
        result = approve_slice(slice_obj=slice_obj, actor=resolve_actor(dean, self.org))
        self.assertEqual(result["slice_status"], "approved")
