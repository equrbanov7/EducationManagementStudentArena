"""Əhatə (scope) qapıları — fail-closed davranışın sübutu."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import OrgUnit
from apps.workload.constants import PERM_DISTRIBUTE, PERM_MANAGE, PERM_VIEW
from apps.workload.services import (
    WorkloadDenied,
    can_distribute_chair,
    can_manage_chair,
    get_or_create_task,
    manageable_chairs,
    resolve_actor,
    save_row,
)
from core.constants import OrgUnitType, RoleScopeType

from .factories import YEAR, activate_member, make_org, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = [PERM_VIEW, PERM_MANAGE, PERM_DISTRIBUTE, "workload.report"]


class WorkloadScopeTest(TestCase):
    def setUp(self):
        self.org = make_org("wl-scope")
        self.stack = make_structure(self.org, code="WLA")
        self.other_chair = OrgUnit.objects.create(
            organization=self.org,
            name="Başqa kafedra",
            slug="wl-scope-other-chair",
            unit_type=OrgUnitType.CHAIR,
            parent=self.stack["faculty"],
        )
        self.head = User.objects.create_user("wl_head", "wl_head@x.test", "pw")
        activate_member(
            self.org,
            self.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=self.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        self.teacher = User.objects.create_user("wl_teacher", "wl_teacher@x.test", "pw")
        activate_member(
            self.org,
            self.teacher,
            "teacher",
            permissions=[PERM_VIEW],
            scope_unit=self.stack["chair"],
            level=50,
            scope_type=RoleScopeType.COURSE,
        )

    def test_chair_head_manages_only_own_chair(self):
        actor = resolve_actor(self.head, self.org)
        self.assertTrue(can_manage_chair(actor, self.stack["chair"].pk))
        self.assertFalse(can_manage_chair(actor, self.other_chair.pk))

    def test_manageable_chairs_is_scoped(self):
        actor = resolve_actor(self.head, self.org)
        names = {unit.pk for unit in manageable_chairs(actor)}
        self.assertEqual(names, {self.stack["chair"].pk})

    def test_creating_a_task_for_a_foreign_chair_is_denied(self):
        actor = resolve_actor(self.head, self.org)
        with self.assertRaises(WorkloadDenied) as ctx:
            get_or_create_task(
                organization=self.org,
                chair_id=self.other_chair.pk,
                academic_year=YEAR,
                actor=actor,
            )
        self.assertEqual(ctx.exception.code, "workload.manage_denied")

    def test_teacher_cannot_manage_or_distribute(self):
        actor = resolve_actor(self.teacher, self.org)
        self.assertTrue(actor.has(PERM_VIEW))
        self.assertFalse(can_manage_chair(actor, self.stack["chair"].pk))
        self.assertFalse(can_distribute_chair(actor, self.stack["chair"].pk))

    def test_teacher_cannot_edit_rows(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.head)
        actor = resolve_actor(self.teacher, self.org)
        with self.assertRaises(WorkloadDenied):
            save_row(task=task, actor=actor, data={"subject_text": "Fənn"})

    def test_unit_role_without_scope_unit_is_fail_closed(self):
        """`scope_unit` təyin edilməyib → əhatə YOXDUR (bütün org AÇILMIR)."""
        rogue = User.objects.create_user("wl_rogue", "wl_rogue@x.test", "pw")
        activate_member(
            self.org,
            rogue,
            "chair_head_no_scope",
            permissions=CHAIR_PERMS,
            scope_unit=None,
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        actor = resolve_actor(rogue, self.org)
        self.assertFalse(can_manage_chair(actor, self.stack["chair"].pk))
        self.assertEqual(list(manageable_chairs(actor)), [])
