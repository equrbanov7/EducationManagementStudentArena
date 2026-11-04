"""RİM scope correction is selected, tenant-bound and separate from personal edit."""

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.organizations.models import Membership, OrgUnit
from core.constants import OrgUnitType, RoleScopeType

from .test_rim_center import RimCenterTestBase, make_role


class RimStaffScopeTests(RimCenterTestBase):
    def setUp(self):
        super().setUp()
        self.rim_role.permissions += ["role.assign"]
        self.rim_role.save(update_fields=["permissions"])
        self.old = OrgUnit.objects.create(
            organization=self.org, name="Sosial iş", slug="social", unit_type=OrgUnitType.CHAIR
        )
        self.new = OrgUnit.objects.create(
            organization=self.org, name="Fəlsəfə", slug="philosophy", unit_type=OrgUnitType.CHAIR
        )
        self.lab = make_role(self.org, "lab_assistant", 40, ["journal.view"])
        self.lab.scope_type = RoleScopeType.UNIT
        self.lab.save(update_fields=["scope_type"])
        self.source = Membership.objects.create(
            organization=self.org,
            user=self.teacher,
            role=self.lab,
            scope_unit=self.old,
            is_primary=False,
        )
        self.login_operator()

    def move(self, **overrides):
        payload = {
            "membership_id": str(self.source.pk),
            "unit_id": str(self.new.pk),
            "expected_unit_id": str(self.old.pk),
            "reason": "Səhv kafedra düzəldilir",
        }
        payload.update(overrides)
        return self.act("move_staff_scope", self.teacher, **payload)

    def test_moves_only_selected_scope_and_preserves_personal_fields_and_teacher_role(self):
        password, email = self.teacher.password, self.teacher.email
        other = list(Membership.objects.filter(user=self.teacher).exclude(pk=self.source.pk).values())
        response = self.move()
        self.assertEqual(response.status_code, 200, response.content)
        self.source.refresh_from_db()
        self.assertEqual(self.source.scope_unit_id, self.new.pk)
        self.assertEqual(other, list(Membership.objects.filter(user=self.teacher).exclude(pk=self.source.pk).values()))
        self.teacher.refresh_from_db()
        self.assertEqual((self.teacher.password, self.teacher.email), (password, email))
        # 2026-11-04: lab-only card replaced by the general «Vəzifə və bölmə» placement card.
        rows = {row["id"]: row for row in response.json()["user"]["placement"]["memberships"]}
        self.assertEqual(rows[str(self.source.pk)]["unit_name"], "Fəlsəfə")
        self.assertTrue(AuditLog.objects.filter(changes__action="rim.staff_scope_corrected").exists())

    def test_personal_edit_permission_does_not_grant_staff_scope_permission(self):
        self.rim_role.permissions.remove("role.assign")
        self.rim_role.save(update_fields=["permissions"])
        self.assertEqual(self.move().status_code, 404)
        self.source.refresh_from_db()
        self.assertEqual(self.source.scope_unit_id, self.old.pk)

    def test_stale_source_fails_closed(self):
        self.assertEqual(self.move(expected_unit_id=str(self.new.pk)).status_code, 409)
        self.source.refresh_from_db()
        self.assertEqual(self.source.scope_unit_id, self.old.pk)

    def test_same_target_idempotent(self):
        self.assertEqual(self.move().status_code, 200)
        response = self.move()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["staff_scope_result"]["changed"])

    def test_existing_target_collision_preserves_inactive_source_history(self):
        destination = Membership.objects.create(
            organization=self.org,
            user=self.teacher,
            role=self.lab,
            scope_unit=self.new,
            is_active=False,
        )
        response = self.move()
        self.assertEqual(response.status_code, 200, response.content)
        self.source.refresh_from_db()
        destination.refresh_from_db()
        self.assertFalse(self.source.is_active)
        self.assertEqual(self.source.scope_unit_id, self.old.pk)
        self.assertTrue(destination.is_active)
        repeated = self.move()
        self.assertEqual(repeated.status_code, 200, repeated.content)
        self.assertFalse(repeated.json()["staff_scope_result"]["changed"])
        self.assertEqual(Membership.objects.filter(user=self.teacher, role=self.lab, is_active=True).count(), 1)

    def test_other_role_cannot_be_moved_through_staff_correction(self):
        teacher_membership = Membership.objects.get(user=self.teacher, role=self.teacher_role)
        self.assertEqual(self.move(membership_id=str(teacher_membership.pk)).status_code, 404)
        teacher_membership.refresh_from_db()
        self.assertIsNone(teacher_membership.scope_unit_id)

    def test_foreign_organization_destination_is_denied(self):
        from apps.organizations.models import Organization

        foreign = Organization.objects.create(name="Other", slug="rim-other-scope", owner=self.owner)
        unit = OrgUnit.objects.create(organization=foreign, name="Foreign", slug="foreign", unit_type=OrgUnitType.CHAIR)
        self.assertEqual(self.move(unit_id=str(unit.pk)).status_code, 404)
        self.source.refresh_from_db()
        self.assertEqual(self.source.scope_unit_id, self.old.pk)

    def test_wrong_user_membership_rejected(self):
        self.assertEqual(self.move(membership_id=str(self.operator.memberships.first().pk)).status_code, 404)

    def test_scope_limited_actor_cannot_move_outside_scope(self):
        self.rim_role.scope_type = RoleScopeType.UNIT
        self.rim_role.save(update_fields=["scope_type"])
        Membership.objects.filter(user=self.operator, role=self.rim_role).update(scope_unit=self.old)
        self.assertEqual(self.move().status_code, 404)

    def test_missing_reason_is_rejected(self):
        self.assertEqual(self.move(reason="").status_code, 400)

    def test_scope_correction_changes_only_lab_journal_read_scope(self):
        from apps.organizations.public import get_permission_scope

        before = get_permission_scope(self.teacher, self.org, "journal.view")
        self.assertIn(self.old.pk, before.unit_ids)
        self.assertEqual(self.move().status_code, 200)
        # A fresh request/user must see the corrected membership, not profile labels.
        fresh = get_user_model().objects.get(pk=self.teacher.pk)
        after = get_permission_scope(fresh, self.org, "journal.view")
        self.assertIn(self.new.pk, after.unit_ids)
        self.assertNotIn(self.old.pk, after.unit_ids)

    def test_detail_contains_role_specific_current_scope_not_profile_department(self):
        self.teacher.profile.department = "Stale display-only label"
        self.teacher.profile.save(update_fields=["department"])
        response = self.client.get(reverse("accounts:rim_user_detail", args=[self.teacher.pk]))
        self.assertEqual(response.status_code, 200)
        rows = {row["id"]: row for row in response.json()["user"]["placement"]["memberships"]}
        self.assertEqual(rows[str(self.source.pk)]["unit_name"], "Sosial iş")
