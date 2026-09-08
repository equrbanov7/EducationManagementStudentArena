"""«Fakültələr» / «Kafedralar» kabinet reyestri (2026-09-08).

* fraqmentlər `unit.view` əhatəsi ilə DOLU gəlir (köhnə «0 fakültə» səhvi: RİM /
  Tədris şöbəsi kimi ORGANIZATION rolları boş siyahı alırdı); dekan yalnız öz
  fakültəsini görür; ikinci `<h1>` yoxdur;
* əməllər: yarat/redaktə (unikal ad), arxiv (səbəb ≥20, uşaq/üzv qapısı), dekan/müdir
  təyini (rol üzvlüyü ilə), müavin/koordinator (əhatə alt-ağacda), müəllim
  köçürmə, təyinat silmə — hamısı audit yazır;
* tələbə hesabına heyət rolu verilmir (409); səlahiyyətsiz aktor 403;
* «Heyət» JSON-u və namizəd lookup-u fail-closed.
"""

import uuid

from django.urls import reverse

from apps.audit.models import AuditLog
from apps.organizations.models import Membership, OrgUnit, Role
from core.constants import OrgUnitType, RoleScopeType

from .test_teaching_office_stage2 import Stage2BaseTest

REASON = "Struktur islahatı: fakültə 2026/2027 tədris ilindən ləğv edilir (əmr №12)."


class _OrgUnitsBase(Stage2BaseTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        head = cls.roles["teaching_office_head"]
        head.permissions = list(head.permissions) + [
            "unit.create",
            "unit.edit",
            "unit.delete",
            "unit.assign_head",
            "member.edit",
        ]
        head.save(update_fields=["permissions"])
        for name, level in (("vice_dean", 65), ("program_coordinator", 45)):
            cls.roles[name], _ = Role.objects.update_or_create(
                organization=cls.org,
                name=name,
                defaults={
                    "display_name": name.replace("_", " ").title(),
                    "level": level,
                    "scope_type": RoleScopeType.UNIT,
                    "permissions": ["unit.view"],
                    "is_system": True,
                    "is_active": True,
                },
            )
        cls.other_faculty = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Hüquq fakültəsi", slug="ou-huquq", code="HF"
        )
        cls.teacher_membership = Membership.objects.get(
            organization=cls.org, user=cls.users["teacher"], role=cls.roles["teacher"]
        )

    def _action(self, role, payload):
        return self._client(role).post(
            reverse("organizations:structure_unit_action", kwargs={"slug": self.org.slug}), payload
        )

    def _staff(self, role, unit):
        return self._client(role).get(
            reverse("organizations:structure_unit_staff", kwargs={"slug": self.org.slug, "unit_id": unit.id})
        )

    def _candidates(self, role, **params):
        return self._client(role).get(
            reverse("organizations:structure_role_candidates", kwargs={"slug": self.org.slug}), params
        )


class FragmentTest(_OrgUnitsBase):
    def test_office_head_sees_all_faculties_and_single_title(self):
        response = self._fragment("teaching_office_head", "org-faculties")
        self.assertEqual(response.status_code, 200)
        section = response.context["org_faculties_section"]
        self.assertTrue(section["has_access"])
        names = {row["name"] for row in section["rows"]}
        self.assertEqual(names, {self.faculty.name, self.other_faculty.name})
        row = next(r for r in section["rows"] if r["name"] == self.faculty.name)
        self.assertEqual(row["chairs"], 1)
        self.assertEqual(row["head_name"], "")
        html = response.json()["html"]
        self.assertNotIn("<h1", html)
        self.assertIn('data-tof-section="org-faculties"', html)
        self.assertIn("ouHeadDialog", html)
        self.assertIn("ouRoleDialog", html)
        self.assertIn('data-ems-filters-auto="1"', html)

    def test_kafedras_fragment_filters_by_faculty(self):
        response = self._fragment("teaching_office_head", "org-kafedras", kf_faculty=str(self.faculty.id))
        self.assertEqual(response.status_code, 200)
        section = response.context["org_kafedras_section"]
        self.assertEqual({row["name"] for row in section["rows"]}, {self.chair.name})
        row = section["rows"][0]
        self.assertEqual(row["faculty_name"], self.faculty.name)
        self.assertEqual(row["specialties"], 1)
        self.assertEqual(row["groups"], 1)
        self.assertIn("active_teachers", row)
        self.assertIn("offerings", row)
        html = response.json()["html"]
        self.assertNotIn("<h1", html)
        self.assertIn("ouTeacherDialog", html)

        empty = self._fragment("teaching_office_head", "org-kafedras", kf_faculty=str(uuid.uuid4()))
        self.assertEqual(empty.context["org_kafedras_section"]["rows"], [])
        self.assertEqual(empty.context["org_kafedras_section"]["table_state"], "empty")

    def test_dean_sees_only_own_faculty(self):
        response = self._fragment("dean", "org-faculties")
        self.assertEqual(response.status_code, 200)
        section = response.context["org_faculties_section"]
        self.assertTrue(section["has_access"])
        self.assertEqual({row["name"] for row in section["rows"]}, {self.faculty.name})
        # Dekan admin-ekvivalent roldur (`_can_manage_organization`) — bayraq açıqdır,
        # amma fakültə yaratmaq org-wide əhatə tələb edir (aşağıdakı 403 testi).
        self.assertFalse(section["is_org_wide"])

    def test_student_has_no_structure_sections(self):
        sections = self._sections("student")
        self.assertNotIn("org-faculties", sections)
        self.assertNotIn("org-kafedras", sections)


class UnitActionsTest(_OrgUnitsBase):
    def test_create_faculty_and_reject_duplicate_name(self):
        response = self._action(
            "teaching_office_head", {"action": "save_unit", "kind": "faculty", "name": "Yeni fakültə", "code": "YF"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        unit = OrgUnit.objects.get(organization=self.org, name="Yeni fakültə")
        self.assertEqual(unit.unit_type, OrgUnitType.FACULTY)
        self.assertIsNone(unit.parent_id)

        duplicate = self._action(
            "teaching_office_head", {"action": "save_unit", "kind": "faculty", "name": "yeni FAKÜLTƏ"}
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(duplicate.json()["error"], "name_taken")
        self.assertEqual(duplicate.json()["field"], "name")

    def test_create_kafedra_requires_faculty(self):
        missing = self._action("teaching_office_head", {"action": "save_unit", "kind": "kafedra", "name": "Riyaziyyat"})
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()["error"], "parent_required")

        ok = self._action(
            "teaching_office_head",
            {
                "action": "save_unit",
                "kind": "kafedra",
                "name": "Riyaziyyat",
                "code": "RK",
                "parent": str(self.faculty.id),
            },
        )
        self.assertEqual(ok.status_code, 200, ok.content)
        unit = OrgUnit.objects.get(organization=self.org, name="Riyaziyyat")
        self.assertEqual(unit.parent_id, self.faculty.id)
        self.assertEqual(unit.unit_type, OrgUnitType.CHAIR)

    def test_update_kafedra_moves_it_to_another_faculty(self):
        response = self._action(
            "teaching_office_head",
            {
                "action": "save_unit",
                "kind": "kafedra",
                "id": str(self.chair.id),
                "name": self.chair.name,
                "code": "KE-2",
                "parent": str(self.other_faculty.id),
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.chair.refresh_from_db()
        self.assertEqual(self.chair.parent_id, self.other_faculty.id)
        self.assertEqual(self.chair.code, "KE-2")

    def test_archive_guards_and_success(self):
        blocked = self._action(
            "teaching_office_head", {"action": "archive_unit", "id": str(self.faculty.id), "reason": REASON}
        )
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(blocked.json()["error"], "has_children")

        short = self._action(
            "teaching_office_head", {"action": "archive_unit", "id": str(self.other_faculty.id), "reason": "qısa"}
        )
        self.assertEqual(short.status_code, 400)
        self.assertEqual(short.json()["error"], "reason_too_short")

        ok = self._action(
            "teaching_office_head", {"action": "archive_unit", "id": str(self.other_faculty.id), "reason": REASON}
        )
        self.assertEqual(ok.status_code, 200, ok.content)
        self.other_faculty.refresh_from_db()
        self.assertFalse(self.other_faculty.is_active)
        self.assertTrue(
            AuditLog.objects.filter(organization=self.org, reason__icontains="structure registry: archived").exists()
        )

    def test_teacher_cannot_manage_structure(self):
        response = self._action("teacher", {"action": "save_unit", "kind": "faculty", "name": "X"})
        self.assertEqual(response.status_code, 403)

    def test_dean_scope_limits_creation(self):
        """Dekan (admin-ekvivalent, UNIT əhatə): fakültə yarada bilməz (org-wide deyil),
        öz fakültəsində kafedra yaradır, başqa fakültədə yox (əhatədən kənar)."""
        faculty = self._action("dean", {"action": "save_unit", "kind": "faculty", "name": "X"})
        self.assertEqual(faculty.status_code, 403)
        foreign = self._action(
            "dean", {"action": "save_unit", "kind": "kafedra", "name": "X", "parent": str(self.other_faculty.id)}
        )
        self.assertEqual(foreign.status_code, 400)
        self.assertEqual(foreign.json()["error"], "bad_parent")
        own = self._action(
            "dean",
            {"action": "save_unit", "kind": "kafedra", "name": "Dekan kafedrası", "parent": str(self.faculty.id)},
        )
        self.assertEqual(own.status_code, 200, own.content)
        self.assertTrue(
            OrgUnit.objects.filter(organization=self.org, name="Dekan kafedrası", parent=self.faculty).exists()
        )


class StaffAssignmentTest(_OrgUnitsBase):
    def test_assign_dean_sets_head_and_role_membership(self):
        user = self.users["teacher"]
        response = self._action(
            "teaching_office_head", {"action": "assign_head", "id": str(self.faculty.id), "head": str(user.id)}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.head_id, user.id)
        self.assertTrue(
            Membership.objects.filter(
                organization=self.org, user=user, role=self.roles["dean"], scope_unit=self.faculty, is_active=True
            ).exists()
        )
        # Yeni dekan — köhnəsinin rol üzvlüyü bağlanır, unit.head dəyişir.
        other = self.users["chair_head"]
        again = self._action(
            "teaching_office_head", {"action": "assign_head", "id": str(self.faculty.id), "head": str(other.id)}
        )
        self.assertEqual(again.status_code, 200, again.content)
        self.assertFalse(
            Membership.objects.filter(
                organization=self.org, user=user, role=self.roles["dean"], scope_unit=self.faculty, is_active=True
            ).exists()
        )
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.head_id, other.id)
        # Boş rəhbər = təyinat silinir.
        cleared = self._action(
            "teaching_office_head", {"action": "assign_head", "id": str(self.faculty.id), "head": ""}
        )
        self.assertEqual(cleared.status_code, 200)
        self.faculty.refresh_from_db()
        self.assertIsNone(self.faculty.head_id)

    def test_student_cannot_become_head_or_staff(self):
        student = self.users["student"]
        head = self._action(
            "teaching_office_head", {"action": "assign_head", "id": str(self.chair.id), "head": str(student.id)}
        )
        self.assertEqual(head.status_code, 409)
        self.assertEqual(head.json()["error"], "target_is_student")
        role = self._action(
            "teaching_office_head",
            {"action": "add_role", "id": str(self.faculty.id), "role": "vice_dean", "user": str(student.id)},
        )
        self.assertEqual(role.status_code, 409)
        self.assertEqual(role.json()["error"], "target_is_student")

    def test_add_vice_dean_then_duplicate_then_remove(self):
        user = self.users["teacher"]
        ok = self._action(
            "teaching_office_head",
            {
                "action": "add_role",
                "id": str(self.faculty.id),
                "role": "vice_dean",
                "user": str(user.id),
                "reason": "Əmr №4",
            },
        )
        self.assertEqual(ok.status_code, 200, ok.content)
        membership = Membership.objects.get(
            organization=self.org, user=user, role=self.roles["vice_dean"], scope_unit=self.faculty
        )
        self.assertTrue(membership.is_active)

        dup = self._action(
            "teaching_office_head",
            {"action": "add_role", "id": str(self.faculty.id), "role": "vice_dean", "user": str(user.id)},
        )
        self.assertEqual(dup.status_code, 409)
        self.assertEqual(dup.json()["error"], "already_assigned")

        fragment = self._fragment("teaching_office_head", "org-faculties")
        row = next(r for r in fragment.context["org_faculties_section"]["rows"] if r["name"] == self.faculty.name)
        self.assertEqual([p["name"] for p in row["vice_deans"]], [user.get_full_name() or user.username])

        removed = self._action(
            "teaching_office_head",
            {"action": "remove_role", "id": str(self.faculty.id), "membership": str(membership.id)},
        )
        self.assertEqual(removed.status_code, 200, removed.content)
        membership.refresh_from_db()
        self.assertFalse(membership.is_active)

    def test_coordinator_scope_must_be_in_subtree(self):
        user = self.users["teacher"]
        bad = self._action(
            "teaching_office_head",
            {
                "action": "add_role",
                "id": str(self.faculty.id),
                "role": "program_coordinator",
                "user": str(user.id),
                "scope": str(self.other_faculty.id),
            },
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"], "bad_scope")

        ok = self._action(
            "teaching_office_head",
            {
                "action": "add_role",
                "id": str(self.faculty.id),
                "role": "program_coordinator",
                "user": str(user.id),
                "scope": str(self.specialty.id),
            },
        )
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertTrue(
            Membership.objects.filter(
                organization=self.org,
                user=user,
                role=self.roles["program_coordinator"],
                scope_unit=self.specialty,
                is_active=True,
            ).exists()
        )
        row = next(
            r
            for r in self._fragment("teaching_office_head", "org-faculties").context["org_faculties_section"]["rows"]
            if r["name"] == self.faculty.name
        )
        self.assertEqual(row["coordinators"][0]["scope"], self.specialty.name)

    def test_vice_dean_is_not_allowed_on_kafedra(self):
        response = self._action(
            "teaching_office_head",
            {
                "action": "add_role",
                "id": str(self.chair.id),
                "role": "vice_dean",
                "user": str(self.users["teacher"].id),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "bad_role")

    def test_add_teacher_moves_membership_and_remove_detaches(self):
        ok = self._action(
            "teaching_office_head",
            {"action": "add_teacher", "id": str(self.chair.id), "membership": str(self.teacher_membership.id)},
        )
        self.assertEqual(ok.status_code, 200, ok.content)
        self.teacher_membership.refresh_from_db()
        self.assertEqual(self.teacher_membership.scope_unit_id, self.chair.id)

        dup = self._action(
            "teaching_office_head",
            {"action": "add_teacher", "id": str(self.chair.id), "membership": str(self.teacher_membership.id)},
        )
        self.assertEqual(dup.status_code, 409)

        row = self._fragment("teaching_office_head", "org-kafedras").context["org_kafedras_section"]["rows"][0]
        self.assertEqual(row["teachers"], 1)

        removed = self._action(
            "teaching_office_head",
            {"action": "remove_role", "id": str(self.chair.id), "membership": str(self.teacher_membership.id)},
        )
        self.assertEqual(removed.status_code, 200, removed.content)
        self.teacher_membership.refresh_from_db()
        self.assertTrue(self.teacher_membership.is_active)
        self.assertIsNone(self.teacher_membership.scope_unit_id)

    def test_teacher_member_cannot_assign(self):
        response = self._action(
            "teacher",
            {"action": "add_teacher", "id": str(self.chair.id), "membership": str(self.teacher_membership.id)},
        )
        self.assertEqual(response.status_code, 403)


class StaffAndCandidatesTest(_OrgUnitsBase):
    def test_staff_json_for_faculty_and_kafedra(self):
        response = self._staff("teaching_office_head", self.faculty)
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["unit"]["name"], self.faculty.name)
        self.assertEqual([g["key"] for g in payload["groups"]], ["vice_dean", "program_coordinator", "teacher"])
        self.assertEqual([c["name"] for c in payload["children"]], [self.chair.name])
        self.assertTrue(payload["can_assign_members"])

        chair = self._staff("teaching_office_head", self.chair).json()
        self.assertEqual([g["key"] for g in chair["groups"]], ["teacher", "program_coordinator"])
        self.assertEqual([c["name"] for c in chair["children"]], [self.specialty.name])
        (
            self.assertEqual(
                chair["unit"]["head"]["username"], self.users["chair_head"].username if self.chair.head_id else None
            )
            if self.chair.head_id
            else self.assertIsNone(chair["unit"]["head"])
        )

    def test_staff_json_is_scoped(self):
        response = self._staff("dean", self.other_faculty)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._staff("teacher", self.faculty).status_code, 403)

    def test_candidates_lookup(self):
        staff = self._candidates("teaching_office_head", kind="staff", q="ds2_teacher")
        self.assertEqual(staff.status_code, 200)
        self.assertEqual([row["id"] for row in staff.json()["results"]], [str(self.users["teacher"].id)])

        teachers = self._candidates("teaching_office_head", kind="teacher", unit=str(self.chair.id))
        ids = {row["id"] for row in teachers.json()["results"]}
        self.assertIn(str(self.teacher_membership.id), ids)
        self.teacher_membership.scope_unit = self.chair
        self.teacher_membership.save(update_fields=["scope_unit"])
        excluded = self._candidates("teaching_office_head", kind="teacher", unit=str(self.chair.id))
        self.assertNotIn(str(self.teacher_membership.id), {row["id"] for row in excluded.json()["results"]})

        denied = self._candidates("teacher", kind="staff")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["results"], [])
