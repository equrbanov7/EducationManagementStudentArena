"""Səbinə nümunəsi: laborantın öz kafedra jurnalları və aktiv staff təsnifatı."""

import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.models import ProfileRole
from apps.accounts.services.view_as import MODE_FULL, build_target_queryset
from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.middleware import OrganizationMiddleware
from apps.organizations.models import Membership, OrgUnit
from apps.organizations.scoping import get_permission_scope
from apps.registrar import journal_access, journal_scope
from apps.registrar.journal_list_scope import journal_list_base
from apps.registrar.models import CourseOffering, Subject
from apps.workload.models import TeacherAssignment
from apps.workload.tests.factories import make_org, make_row, make_structure, make_task
from core.constants import RoleScopeType
from core.rls import apply_rls_request_context, bypass_rls, reset_rls_context

User = get_user_model()
MIGRATION = "apps.organizations.migrations.0078_lab_assistant_journal_view"
NATURE = "99856a60-d755-497c-a475-eb5f79fb26eb"


@override_settings(RLS_TRANSACTION_SCOPED=True)
class LaborantJournalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("lab_visibility_admin", "admin@x.test", "pw")
        cls.org = make_org("lab-journals", owner=cls.admin)
        cls.stack = make_structure(cls.org, code="LABVIEW")
        cls.nature = OrgUnit.objects.create(
            pk=NATURE,
            organization=cls.org,
            name="Təbiət elmləri kafedrası",
            slug="lab-nature",
            unit_type="chair",
            parent=cls.stack["faculty"],
        )
        cls.foreign_chair = cls.stack["chair"]
        cls.lab = User.objects.create_user(
            pk=9496, username="sebine.memmedova.2", first_name="Səbinə", last_name="Məmmədova"
        )
        cls.lab_membership = Membership.objects.create(
            organization=cls.org,
            user=cls.lab,
            role=cls.org.roles.get(name="lab_assistant"),
            scope_unit=cls.nature,
            is_active=True,
        )
        # Primary student identity must neither hide an employee nor lend its group's journal scope.
        Membership.objects.create(
            organization=cls.org,
            user=cls.lab,
            role=cls.org.roles.get(name="student"),
            scope_unit=cls.stack["group"],
            is_primary=True,
            is_active=True,
        )
        profile = cls.lab.profile
        profile.organization, profile.role, profile.patronymic = cls.org, ProfileRole.STUDENT, "Natiq"
        profile.save(update_fields=["organization", "role", "patronymic"])
        cls.teacher = User.objects.create_user("lab_nature_teacher")
        Membership.objects.create(
            organization=cls.org,
            user=cls.teacher,
            role=cls.org.roles.get(name="teacher"),
            scope_unit=cls.nature,
            is_primary=True,
            is_active=True,
        )
        # A secondary appointment in Nature does not make all this teacher's Finance courses Nature's.
        cls.other_teacher = User.objects.create_user("lab_other_teacher")
        for chair, primary in ((cls.foreign_chair, True), (cls.nature, False)):
            Membership.objects.create(
                organization=cls.org,
                user=cls.other_teacher,
                role=cls.org.roles.get(name="teacher"),
                scope_unit=chair,
                is_primary=primary,
                is_active=True,
            )
        cls.task = make_task(cls.org, cls.nature, status="distributed")
        cls.other_task = make_task(cls.org, cls.foreign_chair, status="distributed")
        own_subject = Subject.objects.create(
            organization=cls.org, code="LAB-OWN", name="Nature load", chair_unit=cls.foreign_chair
        )
        cls.own = CourseOffering.objects.create(
            organization=cls.org,
            subject=own_subject,
            period=cls.stack["period"],
            group=cls.stack["group"],
            instructor=cls.teacher,
            lesson_hours=60,
        )
        row = make_row(cls.task, {**cls.stack, "subject": own_subject})
        TeacherAssignment.objects.create(
            organization=cls.org, row=row, activity="lecture", teacher=cls.teacher, hours=30
        )
        # Even a group under the Nature tree must not expose a different chair's actual load.
        group_under_chair = OrgUnit.objects.create(
            organization=cls.org, name="Own tree group", slug="lab-under", unit_type="group", parent=cls.nature
        )
        cls.other = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.stack["subject"],
            period=cls.stack["period"],
            group=group_under_chair,
            instructor=cls.other_teacher,
            lesson_hours=60,
        )
        make_row(cls.other_task, {**cls.stack, "group": group_under_chair})
        catalogue = Subject.objects.create(
            organization=cls.org, code="LAB-CATALOGUE", name="Nature catalogue", chair_unit=cls.nature
        )
        cls.by_catalogue = CourseOffering.objects.create(
            organization=cls.org,
            subject=catalogue,
            period=cls.stack["period"],
            group=cls.stack["group"],
            instructor=cls.other_teacher,
        )
        cls.foreign_org = make_org("lab-foreign")
        fs = make_structure(cls.foreign_org, code="LABFOREIGN")
        teacher = User.objects.create_user("lab_foreign_teacher")
        Membership.objects.create(
            organization=cls.foreign_org,
            user=teacher,
            role=cls.foreign_org.roles.get(name="teacher"),
            scope_unit=fs["chair"],
            is_primary=True,
            is_active=True,
        )
        cls.foreign_journal = CourseOffering.objects.create(
            organization=cls.foreign_org,
            subject=fs["subject"],
            period=fs["period"],
            group=fs["group"],
            instructor=teacher,
        )
        cls.foreign_lab = User.objects.create_user("foreign_laborant")
        Membership.objects.create(
            organization=cls.foreign_org,
            user=cls.foreign_lab,
            role=cls.foreign_org.roles.get(name="lab_assistant"),
            scope_unit=fs["chair"],
            is_active=True,
        )

    def setUp(self):
        apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)

    def tearDown(self):
        cache.delete(OrganizationMiddleware.org_switcher_cache_key(self.lab.pk))
        reset_rls_context()

    def listed(self, user=None):
        user = user or User.objects.get(pk=self.lab.pk)
        request = RequestFactory().get("/jurnal/")
        request.user, request.organization = user, self.org
        base, broad = journal_list_base(user, request)
        self.assertTrue(broad)
        return set(base.values_list("pk", flat=True))

    def targets(self, kind="staff"):
        return build_target_queryset(
            self.admin,
            self.org,
            mode=MODE_FULL,
            actor_level=999,
            memberships=[],
            q="sebine.memmedova.2",
            role_filter=kind,
        )

    def test_real_9496_nature_scope_sees_only_nature_load_and_catalogue(self):
        self.assertEqual(self.listed(), {self.own.pk, self.by_catalogue.pk})
        membership = Membership.objects.get(pk=self.lab_membership.pk)
        self.assertEqual(str(membership.scope_unit_id), NATURE)
        self.assertTrue(membership.is_active)
        self.assertFalse(membership.is_primary)

    def test_list_and_detail_agree_and_foreign_course_under_same_tree_is_excluded(self):
        user = User.objects.get(pk=self.lab.pk)
        visible = self.listed(user)
        for journal in (self.own, self.other, self.by_catalogue):
            self.assertEqual(journal_access.can_observe_journal(user, journal), journal.pk in visible)
        self.assertNotIn(self.other.pk, visible)
        self.assertNotIn(self.foreign_journal.pk, visible)

    def test_observation_does_not_grant_writing_correction_or_roster_management(self):
        role = self.org.roles.get(name="lab_assistant")
        self.assertEqual(role.scope_type, RoleScopeType.UNIT)
        self.assertIn("journal.view", role.permissions)
        self.assertFalse(
            {"journal.correct", "journal.roster", "journal.close", "org.manage_members", "role.assign"}
            & set(role.permissions)
        )
        self.assertFalse(journal_access.can_edit_journal(self.lab, self.own))
        self.assertFalse(journal_access.is_direct_editor(self.lab, self.own))

    def test_no_scope_or_inactive_lab_membership_does_not_borrow_student_scope(self):
        Membership.objects.filter(pk=self.lab_membership.pk).update(scope_unit=None)
        user = User.objects.get(pk=self.lab.pk)
        self.assertIsNone(journal_scope.journal_view_q(user, self.org))
        Membership.objects.filter(pk=self.lab_membership.pk).update(scope_unit=self.nature, is_active=False)
        self.assertIsNone(journal_scope.journal_view_q(User.objects.get(pk=self.lab.pk), self.org))

    def test_staff_picker_includes_active_dual_student_lab_membership(self):
        self.assertEqual(set(self.targets().values_list("pk", flat=True)), {self.lab.pk})
        self.assertEqual(set(self.targets("").values_list("pk", flat=True)), {self.lab.pk})

    def test_staff_picker_excludes_inactive_lab_and_other_tenant(self):
        Membership.objects.filter(pk=self.lab_membership.pk).update(is_active=False)
        self.assertFalse(self.targets().exists())
        self.assertTrue(self.targets("").exists())
        Membership.objects.filter(pk=self.lab_membership.pk).update(is_active=True)
        self.org.roles.filter(name="lab_assistant").update(is_active=False)
        self.assertFalse(self.targets().exists())
        with bypass_rls():
            self.assertNotIn(
                self.foreign_lab.pk,
                build_target_queryset(
                    self.admin, self.org, mode=MODE_FULL, actor_level=999, memberships=[], role_filter="staff"
                ).values_list("pk", flat=True),
            )

    def test_template_adds_only_readonly_journal_key(self):
        role = next(r for r in UNIVERSITY_ROLES if r["name"] == "lab_assistant")
        self.assertIn("journal.view", role["permissions"])
        self.assertEqual(role["scope_type"], RoleScopeType.UNIT)

    def test_additional_explicit_faculty_scope_is_preserved(self):
        from apps.organizations.models import Role

        role = Role.objects.create(
            organization=self.org,
            name="extra_faculty_observer",
            scope_type=RoleScopeType.UNIT,
            permissions=["journal.view"],
        )
        Membership.objects.create(
            organization=self.org, user=self.lab, role=role, scope_unit=self.stack["faculty"], is_active=True
        )
        self.assertEqual(self.listed(), {self.own.pk, self.by_catalogue.pk, self.other.pk})

    def test_migration_is_idempotent_and_preserves_scope_and_other_permissions(self):
        migration = importlib.import_module(MIGRATION)
        role = self.org.roles.get(name="lab_assistant")
        role.permissions = ["course.view", "workload.view", "workload.manage", "workload.distribute"]
        role.save(update_fields=["permissions"])
        migration.forward(django_apps, None)
        migration.forward(django_apps, None)
        role.refresh_from_db()
        self.assertEqual(
            role.permissions, ["course.view", "workload.view", "workload.manage", "workload.distribute", "journal.view"]
        )
        self.assertEqual(role.scope_type, RoleScopeType.UNIT)
        migration.backward(django_apps, None)
        role.refresh_from_db()
        self.assertEqual(role.permissions, ["course.view", "workload.view", "workload.manage", "workload.distribute"])

    def test_migration_respects_journal_and_global_wildcards(self):
        migration = importlib.import_module(MIGRATION)
        role = self.org.roles.get(name="lab_assistant")
        for permissions in (["journal.*"], ["*"]):
            role.permissions = permissions
            role.save(update_fields=["permissions"])
            migration.forward(django_apps, None)
            migration.backward(django_apps, None)
            role.refresh_from_db()
            self.assertEqual(role.permissions, permissions)

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    def test_stale_navbar_redis_entry_is_not_a_permission_source(self):
        migration = importlib.import_module(MIGRATION)
        role = self.org.roles.get(name="lab_assistant")
        role.permissions = [p for p in role.permissions if p != "journal.view"]
        role.save(update_fields=["permissions"])
        old = User.objects.get(pk=self.lab.pk)
        self.assertFalse(get_permission_scope(old, self.org, "journal.view").has_structure_access)
        OrganizationMiddleware._cached_active_memberships(old)
        self.assertIsNotNone(cache.get(OrganizationMiddleware.org_switcher_cache_key(old.pk)))
        migration.forward(django_apps, None)
        fresh = User.objects.get(pk=old.pk)
        live = OrganizationMiddleware._session_memberships_queryset(fresh, self.org.slug)
        self.assertTrue(any("journal.view" in m.role.permissions for m in live if m.role.name == "lab_assistant"))
        self.assertTrue(get_permission_scope(fresh, self.org, "journal.view").has_structure_access)
        self.assertEqual(self.listed(fresh), {self.own.pk, self.by_catalogue.pk})
