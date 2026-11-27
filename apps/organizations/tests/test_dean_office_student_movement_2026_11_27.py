"""Dekanlıq tələbə hərəkəti + bərpada hədəf qrup + «Dekanlıq laborantı» (sahib 2026-11-27).

Qurğu (``SubgroupFixture``): ``Fakültə → Kafedra → {G1, G2}`` + ``Uzaq fakültə → GX``. Aktorlar REAL şablon rolları ilə
(``dean``, ``vice_dean``, ``dean_office_assistant``, ``tutor``) fakültəyə bağlanır; ``far`` — uzaq fakültənin dekanı.
"""

from __future__ import annotations

import importlib
from io import StringIO

from django.apps import apps as django_apps
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.services.staff_roster import role_for
from apps.audit.models import AuditLog
from apps.organizations import dean_office_laborants
from apps.organizations.default_roles_dean_office import (
    DEAN_OFFICE_ASSISTANT_PERMISSIONS,
    DEAN_OFFICE_ASSISTANT_ROLE,
    DEAN_OFFICE_GRANTS,
    DEAN_OFFICE_MOVEMENT_PERMISSIONS,
)
from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.models import Membership, OrgUnit
from apps.organizations.permissions import get_all_permissions
from apps.registrar.models import Enrollment, StudentAcademicRecord
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.constants import OrgUnitType
from core.rls import bypass_rls

MIGRATION = importlib.import_module("apps.organizations.migrations.0089_dean_office_student_movement")
ACTION_URL = "accounts:student_registry_action"
_MOVEMENT_KEYS = {"student.movement", "people.manage_academic"}


class DeanOfficeBase(SubgroupFixture, TestCase):
    PREFIX = "dom"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            roles = {name: cls.org.roles.get(name=name) for name in ("dean", "vice_dean", "tutor")}
            roles["doa"] = cls.org.roles.get(name=DEAN_OFFICE_ASSISTANT_ROLE)
            cls.real_dean = cls._member("dom_rdean", roles["dean"], cls.faculty)
            cls.vice = cls._member("dom_vice", roles["vice_dean"], cls.faculty)
            cls.doa = cls._member("dom_doa", roles["doa"], cls.faculty)
            cls.tutor = cls._member("dom_tutor", roles["tutor"], cls.faculty)
            cls.far = cls._member("dom_fardean", roles["dean"], cls.far_faculty)
            for user in (cls.host, cls.student, cls.far_student):
                user.profile.organization = cls.org
                user.profile.save(update_fields=["organization"])

    # ── köməkçilər ──────────────────────────────────────────────────────────

    def record_of(self, student):
        with bypass_rls():
            return StudentAcademicRecord.objects.select_related("group").get(organization=self.org, student=student)

    def post(self, user, record, kind, **extra):
        data = {"record_id": str(record.pk), "kind": kind, "order_number": "27/D", "order_date": "2026-11-27"}
        if kind == "academic_leave":
            data.update(effective_until="2030-06-30", leave_reason="maternity")
        data.update(extra)
        with bypass_rls():
            return self.client_for(user).post(reverse(ACTION_URL), data)

    def freeze(self, user, student):
        record = self.record_of(student)
        response = self.post(user, record, "academic_leave")
        self.assertEqual(response.status_code, 200, response.content)
        return self.record_of(student)


class RoleTemplateTest(DeanOfficeBase):
    def test_templates_carry_movement_keys_and_match_frozen_migration(self):
        templates = {role["name"]: role for role in UNIVERSITY_ROLES}
        catalog = set(get_all_permissions())
        for name in ("dean", "vice_dean", DEAN_OFFICE_ASSISTANT_ROLE):
            permissions = set(templates[name]["permissions"])
            self.assertTrue(set(DEAN_OFFICE_MOVEMENT_PERMISSIONS) <= permissions, name)
            self.assertEqual(templates[name]["scope_type"], "unit", name)
            for key in (key for key in permissions if not key.endswith("*")):
                self.assertIn(key, catalog, f"{name}: {key}")
        self.assertIn("unit.group_manage", templates["vice_dean"]["permissions"])
        for key in ("member.invite", "member.edit", "unit.edit", "journal.reassign"):
            self.assertNotIn(key, templates["vice_dean"]["permissions"])
        doa = templates[DEAN_OFFICE_ASSISTANT_ROLE]
        self.assertEqual(set(doa["permissions"]), set(MIGRATION._PERMISSIONS))
        self.assertEqual(set(doa["permissions"]), set(DEAN_OFFICE_ASSISTANT_PERMISSIONS))
        self.assertEqual(doa["display_name"], "Dekanlıq laborantı")
        self.assertLess(doa["level"], 60)
        self.assertLess(doa["level"], templates["vice_dean"]["level"])
        for key in doa["permissions"]:
            self.assertFalse(key.startswith(("workload.", "syllabus.", "question.", "member.invite", "role.")), key)
        self.assertEqual(
            {k: set(v) for k, v in DEAN_OFFICE_GRANTS.items()}, {k: set(v) for k, v in MIGRATION.GRANTS.items()}
        )
        # Tyutor / koordinator: «dekanlıq, tyutor yox».
        for name in ("tutor", "program_coordinator"):
            self.assertNotIn("student.movement", templates[name]["permissions"], name)

    def test_seeded_roles_satisfy_db_reinstate_check(self):
        """``accounts/0021`` funksiyası ``?&`` ilə BİR rolda iki açarı tələb edir."""
        with bypass_rls():
            for name in ("dean", "vice_dean", DEAN_OFFICE_ASSISTANT_ROLE):
                self.assertTrue(_MOVEMENT_KEYS <= set(self.org.roles.get(name=name).permissions), name)

    def test_sidebar_shows_registry_and_movement(self):
        from apps.accounts.views._helpers.rbac_sections import apply_permission_section_gates

        for user in (self.real_dean, self.vice, self.doa):
            sections: set = set()
            with bypass_rls():
                flags = apply_permission_section_gates(user, self.org, sections, is_superadmin=False, is_owner=False)
            self.assertTrue(flags["can_move_students"], user.username)
            self.assertIn("student-registry", sections, user.username)
            self.assertIn("groups-registry", sections, user.username)


class MovementScopeTest(DeanOfficeBase):
    def test_each_dean_office_role_freezes_restores_expels_in_own_faculty(self):
        for user, student in ((self.real_dean, self.host), (self.vice, self.student), (self.doa, self.host)):
            record = self.freeze(user, student)
            self.assertEqual(record.status, "academic_leave", user.username)
            response = self.post(user, record, "reinstatement", target_group=str(record.group_id))
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(self.record_of(student).status, "enrolled")
        record = self.record_of(self.student)
        response = self.post(self.doa, record, "expulsion")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.record_of(self.student).status, "expelled")
        with bypass_rls():
            self.assertEqual(UserProfile.objects.get(user=self.student).access_state, "archived")
        # Bərpa əmri girişi də açır — DB funksiyası (`accounts/0021`) laborant rolunu qəbul edir.
        response = self.post(self.doa, self.record_of(self.student), "reinstatement", target_group=str(self.group2.pk))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["movement"]["access_notice"], "")
        with bypass_rls():
            self.assertEqual(UserProfile.objects.get(user=self.student).access_state, "active")

    def test_other_faculty_student_is_not_found(self):
        for user in (self.real_dean, self.vice, self.doa):
            response = self.post(user, self.record_of(self.far_student), "academic_leave")
            self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(self.record_of(self.far_student).status, "enrolled")
        # Uzaq fakültənin dekanı bizim tələbəyə toxunmur.
        response = self.post(self.far, self.record_of(self.host), "expulsion")
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(self.record_of(self.host).status, "enrolled")

    def test_tutor_is_still_refused(self):
        response = self.post(self.tutor, self.record_of(self.host), "academic_leave")
        self.assertIn(response.status_code, (403, 404), response.content)
        self.assertEqual(self.record_of(self.host).status, "enrolled")


class ReinstateTargetTest(DeanOfficeBase):
    def test_reinstate_into_chosen_other_group_joins_its_journals(self):
        record = self.freeze(self.real_dean, self.host)
        self.assertEqual(record.group_id, self.group1.pk)
        response = self.post(self.real_dean, record, "reinstatement", target_group=str(self.group2.pk))
        self.assertEqual(response.status_code, 200, response.content)
        record = self.record_of(self.host)
        self.assertEqual((record.status, record.group_id), ("enrolled", self.group2.pk))
        with bypass_rls():
            self.assertTrue(
                Enrollment.objects.filter(student=self.host, offering=self.own_history, status="enrolled").exists()
            )
            self.assertFalse(
                Enrollment.objects.filter(student=self.host, offering=self.history_g1, status="enrolled").exists()
            )
        self.assertIn("G2", response.json()["movement"]["to_label"])

    def test_reinstate_default_old_group(self):
        record = self.freeze(self.vice, self.host)
        response = self.post(self.vice, record, "reinstatement", target_group=str(self.group1.pk))
        self.assertEqual(response.status_code, 200, response.content)
        record = self.record_of(self.host)
        self.assertEqual((record.status, record.group_id), ("enrolled", self.group1.pk))
        with bypass_rls():
            self.assertTrue(
                Enrollment.objects.filter(student=self.host, offering=self.history_g1, status="enrolled").exists()
            )

    def test_target_group_is_required(self):
        record = self.freeze(self.real_dean, self.host)
        response = self.post(self.real_dean, record, "reinstatement")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.record_of(self.host).status, "academic_leave")

    def test_out_of_scope_target_group_is_refused(self):
        record = self.freeze(self.real_dean, self.host)
        response = self.post(self.real_dean, record, "reinstatement", target_group=str(self.far_group.pk))
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(response.json()["error"], "target_group_outside_scope")
        self.assertEqual(self.record_of(self.host).status, "academic_leave")

    def test_archived_old_group_needs_another_active_group(self):
        record = self.freeze(self.doa, self.host)
        with bypass_rls():
            OrgUnit.objects.filter(pk=self.group1.pk).update(is_active=False)
        refused = self.post(self.doa, record, "reinstatement", target_group=str(self.group1.pk))
        self.assertEqual(refused.status_code, 404, refused.content)
        # Arxiv qrupun çekmecəsi: tələbə «çıxanlar» siyahısındadır, düymələr açıqdır.
        with bypass_rls():
            drawer = self.client_for(self.doa).get(
                reverse("organizations:group_students", args=[self.org.slug, self.group1.pk])
            )
        self.assertEqual(drawer.status_code, 200, drawer.content)
        body = drawer.json()
        self.assertFalse(body["group"]["is_active"])
        self.assertTrue(body["can_move_students"])
        self.assertEqual([row["username"] for row in body["removed_rows"]], [self.host.username])
        response = self.post(self.doa, record, "reinstatement", target_group=str(self.group2.pk))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.record_of(self.host).group_id, self.group2.pk)

    def test_picker_options_follow_movement_scope(self):
        from apps.organizations.groups_registry import movement_group_options

        with bypass_rls():
            response = self.client_for(self.real_dean).get(
                reverse("organizations:group_students", args=[self.org.slug, self.group1.pk])
            )
            request = response.wsgi_request
            options = {row["value"] for row in movement_group_options(request, self.org)}
        self.assertTrue(response.json()["can_move_students"])
        self.assertEqual(options, {str(self.group1.pk), str(self.group2.pk)})

    def test_pages_render_reinstate_picker(self):
        with bypass_rls():
            client = self.client_for(self.doa)
            groups = client.get(reverse("accounts:profile") + "?section=groups-registry")
            registry = client.get(reverse("accounts:profile") + "?section=student-registry")
        self.assertEqual(groups.status_code, 200)
        html = groups.content.decode()
        self.assertIn('id="tofStudentReinstateDialog"', html)
        self.assertIn("data-tof-reinstate-group", html)
        self.assertIn(f'value="{self.group2.pk}"', html)
        self.assertNotIn(f'value="{self.far_group.pk}"', html)
        self.assertEqual(registry.status_code, 200)
        page = registry.content.decode()
        self.assertIn("data-sr-reinstate-hint", page)
        self.assertIn(f'data-sr-group-id="{self.group1.pk}"', page)


class DrawerFlagScopeTest(DeanOfficeBase):
    def test_movement_buttons_only_inside_write_scope(self):
        """Oxu əhatəsi fakültə, hərəkət əhatəsi bir qrup → başqa qrupun çekmecəsində düymə yoxdur."""
        from apps.organizations.models import Role

        with bypass_rls():
            reader = Role.objects.create(
                organization=self.org,
                name="dom_reader",
                display_name="Oxu",
                level=40,
                scope_type="unit",
                permissions=["unit.view", "people.view_students"],
            )
            writer = Role.objects.create(
                organization=self.org,
                name="dom_writer",
                display_name="Hərəkət",
                level=40,
                scope_type="unit",
                permissions=["student.movement", "people.manage_academic"],
            )
            user = self._member("dom_narrow", reader, self.faculty)
            Membership.objects.create(user=user, organization=self.org, role=writer, scope_unit=self.group1)
            client = self.client_for(user)
            own = client.get(reverse("organizations:group_students", args=[self.org.slug, self.group1.pk])).json()
            other = client.get(reverse("organizations:group_students", args=[self.org.slug, self.group2.pk])).json()
        self.assertTrue(own["can_move_students"])
        self.assertFalse(other["can_move_students"])


class RosterMappingTest(TestCase):
    def test_laborant_at_faculty_maps_to_dean_office(self):
        self.assertEqual(role_for("Təbiət elmləri fakültəsi", "Laborant"), (DEAN_OFFICE_ASSISTANT_ROLE, True))
        self.assertEqual(role_for("İqtisadiyyat məktəbi", "Laborant"), (DEAN_OFFICE_ASSISTANT_ROLE, True))
        self.assertEqual(role_for("Filologiya fakültəsinin dekanlığı", "laborant"), (DEAN_OFFICE_ASSISTANT_ROLE, True))
        self.assertEqual(role_for("Dekanlıq", "Laborant"), (DEAN_OFFICE_ASSISTANT_ROLE, True))
        self.assertEqual(role_for("Tarix kafedrası", "Laborant"), ("lab_assistant", True))
        self.assertEqual(role_for("Məktəbəqədər təhsil kafedrası", "Laborant"), ("lab_assistant", True))
        # Dekanlıqdakı başqa vəzifələr dəyişmir.
        self.assertEqual(role_for("Təbiət elmləri fakültəsi", "Dekan"), ("dean", True))
        self.assertEqual(role_for("Təbiət elmləri fakültəsi", "Dekan müavini"), ("vice_dean", True))


class ReassignCommandTest(DeanOfficeBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            lab = cls.org.roles.get(name="lab_assistant")
            cls.faculty_lab = cls._member("dom_flab", lab, cls.faculty)
            cls.chair_lab = cls._member("dom_clab", lab, cls.chair)

    def _run(self, *args):
        out = StringIO()
        call_command("reassign_dean_office_laborants_20261127", "--org", self.org.slug, *args, stdout=out)
        return out.getvalue()

    def _roles(self, user):
        with bypass_rls():
            return set(
                Membership.objects.filter(user=user, organization=self.org, is_active=True).values_list(
                    "role__name", flat=True
                )
            )

    def test_dry_run_changes_nothing(self):
        with bypass_rls():
            before = list(Membership.objects.filter(organization=self.org).values_list("pk", "role_id", "is_active"))
        output = self._run()
        with bypass_rls():
            after = list(Membership.objects.filter(organization=self.org).values_list("pk", "role_id", "is_active"))
        self.assertEqual(sorted(before), sorted(after))
        self.assertIn("mode=dry_run", output)
        self.assertIn("candidates=1", output)
        self.assertNotIn("dom_flab", output)
        self.assertIn("dom_flab", self._run("--names"))

    def test_apply_switches_only_faculty_laborant_and_is_idempotent(self):
        output = self._run("--apply")
        self.assertIn("written=1", output)
        self.assertEqual(self._roles(self.faculty_lab), {DEAN_OFFICE_ASSISTANT_ROLE})
        self.assertEqual(self._roles(self.chair_lab), {"lab_assistant"})
        with bypass_rls():
            self.assertTrue(AuditLog.objects.filter(resource_type="organizations.dean_office_laborant").exists())
        self.assertIn("candidates=0", self._run("--apply"))

    def test_existing_target_row_is_reactivated(self):
        with bypass_rls():
            Membership.objects.create(
                user=self.faculty_lab,
                organization=self.org,
                role=self.org.roles.get(name=DEAN_OFFICE_ASSISTANT_ROLE),
                scope_unit=self.faculty,
                is_active=False,
            )
            counts, rows = dean_office_laborants.plan(self.org)
        self.assertEqual(counts["reactivate"], 1)
        self._run("--apply")
        self.assertEqual(self._roles(self.faculty_lab), {DEAN_OFFICE_ASSISTANT_ROLE})


class MigrationTest(DeanOfficeBase):
    def test_forward_is_idempotent_and_updates_dean_office_handlers(self):
        ApplicationUnit = django_apps.get_model("applications", "ApplicationUnit")
        with bypass_rls():
            unit = ApplicationUnit.objects.filter(organization=self.org, code="dekan").first()
            if unit is None:
                unit = ApplicationUnit.objects.create(organization=self.org, code="dekan", name="Dekanlıq")
            unit.handler_role_names = ["dean", "vice_dean"]
            unit.save(update_fields=["handler_role_names"])
            Membership.objects.filter(role__name=DEAN_OFFICE_ASSISTANT_ROLE).delete()
            self.org.roles.filter(name=DEAN_OFFICE_ASSISTANT_ROLE).delete()
            vice = self.org.roles.get(name="vice_dean")
            vice.permissions = [key for key in vice.permissions if key not in DEAN_OFFICE_GRANTS["vice_dean"]]
            vice.save(update_fields=["permissions"])
            MIGRATION.forward(django_apps, None)
            MIGRATION.forward(django_apps, None)
            role = self.org.roles.get(name=DEAN_OFFICE_ASSISTANT_ROLE)
            self.assertEqual(set(role.permissions), set(MIGRATION._PERMISSIONS))
            self.assertEqual(role.level, 58)
            vice.refresh_from_db()
            self.assertTrue(set(DEAN_OFFICE_GRANTS["vice_dean"]) <= set(vice.permissions))
            self.assertEqual(len(vice.permissions), len(set(vice.permissions)))
            unit.refresh_from_db()
            self.assertEqual(unit.handler_role_names, ["dean", "vice_dean", DEAN_OFFICE_ASSISTANT_ROLE])


class GroupUnitTypeTest(TestCase):
    def test_dean_office_unit_types_exist(self):
        from apps.organizations.default_roles_dean_office import DEAN_OFFICE_UNIT_TYPES

        self.assertEqual(DEAN_OFFICE_UNIT_TYPES, {OrgUnitType.FACULTY, OrgUnitType.DEANERY})
