"""Rol auditi 2026-10-13, B hissəsi (struct) — «hər rol öz səlahiyyəti qədər» (sahib 2026-10-11).

REAL default universitet rolları ilə (toxum şablonu — `dean`-da `member.edit` + `member.invite` var,
`role.assign` / `role.view` yoxdur):

* B9 — struktur reyestrində ROL VERMƏK (`assign_head`, `add_role`, rol üzvlüyünü silmək) `role.assign`
  tələb edir (`assign_head` həm də `unit.assign_head` ilə); `member.edit` yalnız müəllim köçürmə/ayırma.
  Dekan artıq kafedra müdiri / müavin / koordinator təyin etmir; HR edir; Tədris şöbəsi rəhbəri yalnız
  rəhbər; prorektor (`member.*`, `role.assign` yox) yalnız rəhbər (`unit.assign_head`), müavin yox.
* B8 — `student-organization-management` dəvət/təsdiq yazıları səviyyə ≥ 65 ilə yox, org-wide
  `member.invite` ilə: dekan (UNIT əhatə) və dekan müavini (açarsız) dəvət edə / təsdiqləyə bilmir.
* B15 — «Təşkilat rolları» datası `role.view` ilə (kafedra müdiri boş); üzv CSV ixracı REAL
  `member.edit` ilə (kafedra müdiri / dekan müavini 403, dekan alt-ağacla 200).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.organizations.models import Membership, Organization, OrgUnit
from apps.organizations.public import build_organization_roles_context
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
PW = "StructPass123!"
PENDING_INVITE_TITLE = "__student_pending_invite__"


class _RealRolesOrg(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.owner = User.objects.create_user("rbs_owner", "rbs_owner@qku.edu.az", PW)
            cls.org = Organization.objects.create(
                name="RBS Univ",
                slug="rbs-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə A", slug="rbs-fa", unit_type=OrgUnitType.FACULTY
            )
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra A", slug="rbs-ka", unit_type=OrgUnitType.CHAIR, parent=cls.faculty
            )
            cls.other_faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə B", slug="rbs-fb", unit_type=OrgUnitType.FACULTY
            )
            cls.users = {}
            cls.memberships = {}
            for key, role_name, unit in (
                ("rector", "rector", None),
                ("vice_rector", "vice_rector", None),
                ("hr", "hr", None),
                ("office_head", "teaching_office_head", None),
                ("exam_center_head", "exam_center_head", None),
                ("dean", "dean", cls.faculty),
                ("vice_dean", "vice_dean", cls.faculty),
                ("chair_head", "chair_head", cls.chair),
                ("coordinator", "program_coordinator", cls.faculty),
                ("teacher", "teacher", None),
                ("teacher2", "teacher", None),
            ):
                user = User.objects.create_user(f"rbs_{key}", f"rbs_{key}@qku.edu.az", PW, first_name=key.title())
                cls.memberships[key] = Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role_name),
                    scope_unit=unit,
                    is_primary=True,
                    is_active=True,
                )
                cls.users[key] = user

    def client_for(self, key):
        client = Client()
        client.force_login(self.users[key] if isinstance(key, str) else key)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client


# ─── B9: struktur reyestri — rol vermək `role.assign` ilə ─────────────────────


class StructureRoleGrantTest(_RealRolesOrg):
    def _action(self, key, payload):
        return self.client_for(key).post(
            reverse("organizations:structure_unit_action", kwargs={"slug": self.org.slug}), payload
        )

    def _head(self, key, unit, user_key="teacher"):
        return self._action(key, {"action": "assign_head", "id": str(unit.id), "head": str(self.users[user_key].id)})

    def _vice_dean(self, key, user_key="teacher"):
        return self._action(
            key,
            {
                "action": "add_role",
                "id": str(self.faculty.id),
                "role": "vice_dean",
                "user": str(self.users[user_key].id),
            },
        )

    def test_dean_with_member_edit_cannot_appoint_chair_head_or_vice_dean(self):
        head = self._head("dean", self.chair)
        self.assertEqual(head.status_code, 403, head.content)
        self.chair.refresh_from_db()
        self.assertNotEqual(self.chair.head_id, self.users["teacher"].id)
        self.assertFalse(
            Membership.objects.filter(
                organization=self.org, user=self.users["teacher"], role__name="chair_head", is_active=True
            ).exists()
        )
        role = self._vice_dean("dean")
        self.assertEqual(role.status_code, 403, role.content)
        self.assertFalse(
            Membership.objects.filter(
                organization=self.org, user=self.users["teacher"], role__name="vice_dean", is_active=True
            ).exists()
        )

    def test_dean_cannot_revoke_a_coordinator_but_still_moves_teachers(self):
        coordinator = self.memberships["coordinator"]
        removed = self._action(
            "dean", {"action": "remove_role", "id": str(self.faculty.id), "membership": str(coordinator.id)}
        )
        self.assertEqual(removed.status_code, 403, removed.content)
        coordinator.refresh_from_db()
        self.assertTrue(coordinator.is_active)

        teacher = self.memberships["teacher"]
        moved = self._action("dean", {"action": "add_teacher", "id": str(self.chair.id), "membership": str(teacher.id)})
        self.assertEqual(moved.status_code, 200, moved.content)
        detached = self._action(
            "dean", {"action": "remove_role", "id": str(self.chair.id), "membership": str(teacher.id)}
        )
        self.assertEqual(detached.status_code, 200, detached.content)
        teacher.refresh_from_db()
        self.assertTrue(teacher.is_active)
        self.assertIsNone(teacher.scope_unit_id)

    def test_hr_with_role_assign_appoints_head_and_vice_dean(self):
        head = self._head("hr", self.chair)
        self.assertEqual(head.status_code, 200, head.content)
        self.assertTrue(
            Membership.objects.filter(
                organization=self.org,
                user=self.users["teacher"],
                role__name="chair_head",
                scope_unit=self.chair,
                is_active=True,
            ).exists()
        )
        role = self._vice_dean("hr", user_key="teacher2")
        self.assertEqual(role.status_code, 200, role.content)

    def test_office_head_and_vice_rector_assign_heads_only(self):
        """`unit.assign_head` → yalnız rəhbər; müavin/koordinator `role.assign` istəyir."""
        for key in ("office_head", "vice_rector"):
            with self.subTest(role=key):
                self.assertEqual(self._head(key, self.chair).status_code, 200)
                self.assertEqual(self._vice_dean(key).status_code, 403)

    def test_dean_lookups_and_staff_drawer_follow_the_split(self):
        lookup = reverse("organizations:structure_role_candidates", kwargs={"slug": self.org.slug})
        dean = self.client_for("dean")
        self.assertEqual(dean.get(lookup, {"kind": "staff"}).status_code, 403)
        self.assertEqual(dean.get(lookup, {"kind": "teacher"}).status_code, 200)
        self.assertEqual(self.client_for("hr").get(lookup, {"kind": "staff"}).status_code, 200)

        staff_url = reverse(
            "organizations:structure_unit_staff", kwargs={"slug": self.org.slug, "unit_id": self.faculty.id}
        )
        payload = dean.get(staff_url).json()
        self.assertFalse(payload["can_assign_head"])
        self.assertFalse(payload["can_assign_roles"])
        groups = {group["key"]: group for group in payload["groups"]}
        self.assertFalse(groups["vice_dean"]["addable"])
        self.assertFalse(groups["vice_dean"]["removable"])
        self.assertTrue(groups["teacher"]["removable"])
        hr = self.client_for("hr").get(staff_url).json()
        self.assertTrue(hr["can_assign_head"])
        self.assertTrue({group["key"]: group for group in hr["groups"]}["vice_dean"]["addable"])

    def test_dean_faculty_registry_hides_the_role_dialog(self):
        response = self.client_for("dean").get(reverse("accounts:profile"), {"section": "org-faculties"})
        section = response.context["org_faculties_section"]
        self.assertFalse(section["can_assign_head"])
        self.assertFalse(section["can_assign_roles"])
        self.assertNotContains(response, 'id="ouRoleDialog"')
        self.assertNotContains(response, 'id="ouHeadDialog"')


# ─── B8: student-organization-management — `member.invite` + əhatə ───────────


class StudentOrgInviteGateTest(_RealRolesOrg):
    URL = "accounts:student_organization_management"

    def _free_user(self, username, *, requested=False):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", PW)
        profile = user.profile
        profile.organization = None
        profile.organization_type = OrganizationType.INDIVIDUAL
        profile.requested_organization = self.org if requested else None
        profile.requested_organization_name = self.org.name if requested else ""
        profile.save()
        return user

    def _invite(self, key, target):
        return self.client_for(key).post(
            reverse(self.URL), {"action": "invite_student", "user_id": str(target.id), "next": reverse(self.URL)}
        )

    def _invited(self, target):
        return Membership.objects.filter(
            user=target, organization=self.org, is_active=False, title=PENDING_INVITE_TITLE
        ).exists()

    def test_vice_dean_without_member_invite_cannot_invite(self):
        target = self._free_user("rbs_free_vd")
        response = self._invite("vice_dean", target)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._invited(target))

    def test_unit_scoped_dean_cannot_send_an_org_wide_invite(self):
        """Dekanın `member.invite`-i öz fakültəsi ilədir; bu axının dəvəti bölməsizdir (org-wide) → rədd —
        başqa fakültəyə də, bütün təşkilata da üzv sala bilmir."""
        target = self._free_user("rbs_free_dean")
        response = self._invite("dean", target)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._invited(target))

    def test_hr_without_student_key_cannot_invite_rector_can(self):
        """Sahib 2026-10-17 (FIX-H): bölmə tələbə tərəfi açarı ilə açılır — HR (`member.invite` olsa da) yox."""
        target = self._free_user("rbs_free_hr")
        response = self._invite("hr", target)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._invited(target))
        self._invite("rector", target)
        self.assertTrue(self._invited(target))

    def test_keyless_high_level_role_cannot_approve_a_student_request(self):
        target = self._free_user("rbs_req_ecc", requested=True)
        response = self.client_for("exam_center_head").post(
            reverse(self.URL),
            {
                "action": "bulk_approve_requested_students",
                "selected_pending_user_ids": [str(target.id)],
                "next": reverse(self.URL),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Membership.objects.filter(user=target, organization=self.org, is_active=True).exists())

        approved = self.client_for("rector").post(
            reverse(self.URL),
            {
                "action": "bulk_approve_requested_students",
                "selected_pending_user_ids": [str(target.id)],
                "next": reverse(self.URL),
            },
        )
        self.assertEqual(approved.status_code, 302)
        self.assertTrue(Membership.objects.filter(user=target, organization=self.org, is_active=True).exists())


# ─── B15: rol kataloqu `role.view`, üzv ixracı `member.edit` ──────────────────


class RoleCatalogAndExportGateTest(_RealRolesOrg):
    def _roles_context(self, key):
        request = RequestFactory().get("/")
        request.user = self.users[key]
        return build_organization_roles_context(request, self.org)

    def test_chair_head_without_role_view_gets_no_catalog(self):
        for key in ("chair_head", "dean", "vice_rector"):
            with self.subTest(role=key):
                context = self._roles_context(key)
                self.assertFalse(context["can_view"])
                self.assertEqual(context["roles"], [])
                self.assertEqual(context["ui"], {})
        rector = self._roles_context("rector")
        self.assertTrue(rector["can_view"])
        self.assertTrue(rector["roles"])

    def test_chair_head_cabinet_section_renders_no_role_data(self):
        response = self.client_for("chair_head").get(reverse("accounts:profile"), {"section": "org-roles"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="rolreg-data"')

    def _export(self, key):
        return self.client_for(key).get(reverse("organizations:members_export", args=[self.org.slug]))

    def test_alias_roles_without_member_edit_cannot_export(self):
        for key in ("chair_head", "vice_dean"):
            with self.subTest(role=key):
                self.assertEqual(self._export(key).status_code, 403)

    def test_dean_with_member_edit_exports_own_subtree(self):
        response = self._export("dean")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("rbs_vice_dean", body)
        self.assertNotIn("rbs_hr", body)
