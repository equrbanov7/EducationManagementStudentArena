"""Prorektorun real standart rolu: başqa müəllimin jurnalına oxu, tenant sərhədi, yazı rəddi."""

from importlib import import_module

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import Membership
from apps.registrar import journal_access
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org
from core.constants import RoleScopeType
from core.rls import bypass_rls

User = get_user_model()
migration = import_module("apps.organizations.migrations.0075_vice_rector_journal_view")


class ViceRectorJournalViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("vice-journal")
            cls.other_org = make_org("other-vice-journal")
            cls.viewer = User.objects.create_user("vice-viewer", password="pw")
            cls.role = cls.org.roles.get(name="vice_rector")
            cls.membership = Membership.objects.create(
                organization=cls.org, user=cls.viewer, role=cls.role, is_active=True
            )
            cls.offerings = []
            for org in (cls.org, cls.other_org):
                teacher = User.objects.create_user(f"teacher-{org.slug}", password="pw")
                activate_member(org, teacher, "teacher", permissions=["grade.input", "course.view"])
                stack = make_academic_stack(org)
                cls.offerings.append(make_offering(org, stack, teacher))

    def _client(self):
        client = Client()
        client.force_login(self.viewer)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_default_role_adds_only_observation_permission(self):
        self.assertIn("journal.view", self.role.permissions)
        for key in ("journal.correct", "journal.close", "journal.*"):
            self.assertNotIn(key, self.role.permissions)
        offering = self.offerings[0]
        self.assertTrue(journal_access.can_observe_journal(self.viewer, offering))
        self.assertFalse(journal_access.can_edit_journal(self.viewer, offering))
        self.assertFalse(journal_access.is_direct_editor(self.viewer, offering))

    def test_lists_and_opens_other_teachers_journals_only_in_active_tenant(self):
        client = self._client()
        response = client.get(reverse("registrar:journal_list"), {"year": "2025/2026", "season": "Payız"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row.pk for row in response.context["offerings"]}, {self.offerings[0].pk})
        self.assertEqual(client.get(reverse("registrar:journal_detail", args=[self.offerings[0].pk])).status_code, 200)
        self.assertEqual(client.get(reverse("registrar:journal_detail", args=[self.offerings[1].pk])).status_code, 404)

    def test_observer_cannot_add_lesson_or_write_marks(self):
        client = self._client()
        url = reverse("registrar:journal_detail", args=[self.offerings[0].pk])
        for action in ("add_lesson", "save_marks", "delete_lesson"):
            with self.subTest(action=action):
                self.assertEqual(client.post(url, {"action": action}).status_code, 404)

    def test_inactive_membership_loses_journal_access(self):
        with bypass_rls():
            Membership.objects.filter(pk=self.membership.pk).update(is_active=False)
        fresh_viewer = User.objects.get(pk=self.viewer.pk)
        self.assertFalse(journal_access.can_observe_journal(fresh_viewer, self.offerings[0]))

    def test_custom_unit_scope_does_not_expand_to_other_groups(self):
        with bypass_rls():
            extra_stack = make_academic_stack(self.org, code="OUTSIDE")
            outside = make_offering(self.org, extra_stack, self.offerings[0].instructor)
            self.role.scope_type = RoleScopeType.UNIT
            self.role.save(update_fields=["scope_type"])
            Membership.objects.filter(pk=self.membership.pk).update(scope_unit=self.offerings[0].group)
        fresh_viewer = User.objects.get(pk=self.viewer.pk)
        self.assertTrue(journal_access.can_observe_journal(fresh_viewer, self.offerings[0]))
        self.assertFalse(journal_access.can_observe_journal(fresh_viewer, outside))
        client = self._client()
        self.assertEqual(client.get(reverse("registrar:journal_detail", args=[outside.pk])).status_code, 404)

    def test_inactive_role_loses_journal_access(self):
        with bypass_rls():
            self.role.is_active = False
            self.role.save(update_fields=["is_active"])
        fresh_viewer = User.objects.get(pk=self.viewer.pk)
        self.assertFalse(journal_access.can_observe_journal(fresh_viewer, self.offerings[0]))

    def test_existing_tenant_migration_is_idempotent_and_reversible(self):
        with bypass_rls():
            self.role.permissions = [key for key in self.role.permissions if key != "journal.view"]
            self.role.save(update_fields=["permissions"])
            before = list(self.role.permissions)
            unrelated_role = self.org.roles.get(name="student")
            unrelated = list(unrelated_role.permissions)
            migration.forward(apps, None)
            migration.forward(apps, None)
            self.role.refresh_from_db()
            self.assertEqual(self.role.permissions, before + ["journal.view"])
            unrelated_role.refresh_from_db()
            self.assertEqual(unrelated_role.permissions, unrelated)
            migration.backward(apps, None)
            self.role.refresh_from_db()
            self.assertEqual(self.role.permissions, before)

    def test_migration_preserves_custom_wildcard_and_scope(self):
        with bypass_rls():
            self.role.permissions = ["journal.*", "course.view"]
            self.role.save(update_fields=["permissions"])
            scope = self.role.scope_type
            migration.forward(apps, None)
            migration.backward(apps, None)
            self.role.refresh_from_db()
            self.assertEqual(self.role.permissions, ["journal.*", "course.view"])
            self.assertEqual(self.role.scope_type, scope)
