"""RİM staff creation uses canonical credentials and strict role/scope gates."""

from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.services.rim import RimAccessError
from apps.accounts.services.rim import create as service
from apps.accounts.services.rim.create_options import search_catalog
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from apps.registrar.models import StudentAcademicRecord
from core.constants import OrgUnitType, RoleScopeType
from core.rls import bypass_rls

from .test_rim_account_create import RimCreateBase, User, base_payload


class RimStaffCreateTests(RimCreateBase):
    def payload(self, **values):
        return base_payload(
            **{
                "fin": "",
                "birth_date": "",
                "phone": "",
                "unit": str(self.chair.pk),
                "role": str(self.org.roles.get(name="lab_assistant").pk),
                **values,
            }
        )

    def test_lab_assistant_is_exact_single_membership_with_generated_password_and_no_academic_record(self):
        result = service.create_account(self.actor_for(self.rim), kind="staff", data=self.payload())
        user = User.objects.get(pk=result["user_id"])
        membership = Membership.objects.get(user=user, organization=self.org)
        self.assertEqual(membership.role.name, "lab_assistant")
        self.assertEqual(membership.scope_unit_id, self.chair.pk)
        self.assertFalse(Membership.objects.filter(user=user, role__name="teacher").exists())
        self.assertFalse(StudentAcademicRecord.objects.filter(student=user).exists())
        self.assertTrue(user.check_password(result["password"]))
        profile = UserProfile.objects.get(user=user)
        self.assertTrue(profile.password_change_required)
        self.assertFalse(profile.email_verified)
        self.assertEqual(profile.department, self.chair.name)
        audit = AuditLog.objects.get(organization=self.org, resource_id=str(user.pk))
        self.assertNotIn(result["password"], str(audit.changes))
        self.assertEqual(audit.changes["kind"], "staff")

    def test_role_and_unit_invalid_or_cross_tenant_values_cannot_create_account(self):
        other_org = Organization.objects.create(
            name="Foreign staff organization", slug="foreign-staff-create", org_type="university", owner=self.owner
        )
        foreign = other_org.roles.filter(is_active=True).first()
        other_group = OrgUnit.objects.create(
            organization=other_org, name="Foreign chair", slug="foreign-staff-unit", unit_type=OrgUnitType.CHAIR
        )
        count = User.objects.count()
        for values, field in (
            ({"role": ""}, "role"),
            ({"role": str(foreign.pk)}, "role"),
            ({"role": "malformed"}, "role"),
            ({"unit": ""}, "unit"),
            ({"unit": "malformed"}, "unit"),
            ({"unit": str(other_group.pk)}, "unit"),
        ):
            with self.subTest(values=values):
                with self.assertRaises(service.RimCreateError) as caught:
                    service.create_account(self.actor_for(self.rim), kind="staff", data=self.payload(**values))
                self.assertIn(field, caught.exception.fields)
                self.assertEqual(User.objects.count(), count)

    def actor_with(self, permissions, *, scope_type=RoleScopeType.ORGANIZATION, scope_unit=None):
        user = User.objects.create_user("staff_actor_" + str(User.objects.count()))
        role = Role.objects.create(
            organization=self.org,
            name="staff_creator_" + str(user.pk),
            display_name="Staff creator",
            level=95,
            permissions=permissions,
            scope_type=scope_type,
        )
        Membership.objects.create(organization=self.org, user=user, role=role, scope_unit=scope_unit)
        user.profile.organization = self.org
        user.profile.save(update_fields=["organization"])
        return self.actor_for(user)

    def test_import_staff_and_role_assignment_permissions_are_both_required(self):
        for permissions in (("user.import_staff",), ("role.assign",), ("user.import", "role.assign")):
            with self.subTest(permissions=permissions), bypass_rls():
                actor = self.actor_with(list(permissions))
                with self.assertRaises(RimAccessError):
                    service.create_account(actor, kind="staff", data=self.payload())

    def test_privileged_role_cannot_be_granted_with_only_regular_staff_create_permissions(self):
        actor = self.actor_with(["user.import_staff", "role.assign"])
        role = Role.objects.create(
            organization=self.org,
            name="custom_admin",
            display_name="Admin",
            level=80,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["org.manage_members"],
        )
        with self.assertRaises(service.RimCreateError) as caught:
            service.create_account(actor, kind="staff", data=self.payload(role=str(role.pk), unit=""))
        self.assertIn("role", caught.exception.fields)

    def test_unit_scoped_creator_cannot_escape_own_chair_or_grant_organization_role(self):
        actor = self.actor_with(
            ["user.import_staff", "role.assign"], scope_type=RoleScopeType.UNIT, scope_unit=self.chair
        )
        other = OrgUnit.objects.create(
            organization=self.org, unit_type=OrgUnitType.CHAIR, name="Other chair", slug="staff-other-chair"
        )
        with self.assertRaises(service.RimCreateError) as caught:
            service.create_account(actor, kind="staff", data=self.payload(unit=str(other.pk)))
        self.assertIn("unit", caught.exception.fields)
        results = search_catalog(actor, catalog="staff_unit")["results"]
        self.assertEqual({r["id"] for r in results}, {str(self.chair.pk)})
        service.create_account(actor, kind="staff", data=self.payload())

    def test_role_scope_catalogues_and_endpoint_are_searchable_and_gated(self):
        client = self.client_for(self.rim)
        url = reverse("accounts:rim_create_catalog")
        result = client.get(url, {"catalog": "staff_role", "q": "lab_assistant"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["results"][0]["id"], str(self.org.roles.get(name="lab_assistant").pk))
        units = client.get(url, {"catalog": "staff_unit", "q": self.chair.name}).json()["results"]
        self.assertEqual({r["id"] for r in units}, {str(self.chair.pk)})
        self.assertEqual(self.client_for(self.rim_staff).get(url, {"catalog": "staff_role"}).status_code, 403)
        response = client.post(
            reverse("accounts:rim_create_account"),
            {"kind": "staff", **self.payload()},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["kind"], "staff")
        self.assertTrue(response.json()["password"])

    def test_staff_chooser_and_role_scope_form_are_rendered(self):
        response = self.client_for(self.rim).get(reverse("accounts:profile"), {"section": "rim-center"})
        self.assertContains(response, 'data-rimc-open="staff"')
        self.assertContains(response, 'data-rimc-catalog="staff_role"')
        self.assertContains(response, 'data-rimc-staff-catalog="staff_unit"')

    def test_actor_catalog_level_uses_existing_effective_role_hierarchy(self):
        role = self.org.roles.get(name="chair_head")
        role.level = 70
        role.permissions = ["user.import_staff", "role.assign"]
        role.save(update_fields=["level", "permissions"])
        actor_user = User.objects.create_user("staff_chair_creator")
        Membership.objects.create(organization=self.org, user=actor_user, role=role, scope_unit=self.chair)
        actor_user.profile.organization = self.org
        actor_user.profile.save(update_fields=["organization"])
        target = Role.objects.create(
            organization=self.org,
            name="reviewed_unit_staff",
            display_name="Unit staff",
            level=75,
            scope_type=RoleScopeType.UNIT,
            permissions=[],
        )
        actor = self.actor_for(actor_user)
        self.assertEqual(actor.level, 70)
        result = service.create_account(actor, kind="staff", data=self.payload(role=str(target.pk)))
        self.assertEqual(Membership.objects.get(user_id=result["user_id"]).role_id, target.pk)
