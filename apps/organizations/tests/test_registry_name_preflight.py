"""PostgreSQL upgrade paths for historical registry names and live directory edits."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse

from apps.organizations.models import Membership, Organization, OrgUnit, Role
from apps.organizations.name_matching import is_registry_name_collision
from core.constants import OrganizationType, OrgUnitType, RoleScopeType
from core.rls import set_rls_tenant


class RegistryNameMigrationTests(TransactionTestCase):
    base = ("organizations", "0088_credit_recognition_rim_staff")
    old_release = ("organizations", "0089_unique_registry_unit_names")
    guarded = ("organizations", "0090_registry_name_guard")

    def setUp(self):
        executor = MigrationExecutor(connection)
        if self.base not in executor.loader.graph.nodes:
            self.skipTest("MigrationExecutor requires the PostgreSQL migration graph.")
        leaves = executor.loader.graph.leaf_nodes()
        self.user = get_user_model().objects.create_user("schema_registry_head")
        self.org = Organization.objects.create(
            name="Sınaq universiteti",
            slug="schema-registry",
            owner=self.user,
            org_type=OrganizationType.UNIVERSITY,
            status="active",
        )
        executor.migrate([self.base])
        self.addCleanup(self.restore_schema, leaves)
        self.faculty = self.unit("Birinci fakültə", "faculty-one", OrgUnitType.FACULTY)
        self.other_faculty = self.unit("İkinci fakültə", "faculty-two", OrgUnitType.FACULTY)

    def restore_schema(self, leaves):
        # Restore the test worker even if a partially applied upgrade failed with a duplicate key.
        OrgUnit.objects.filter(organization=self.org).update(is_active=False)
        MigrationExecutor(connection).migrate(leaves)

    def unit(self, name, slug, kind=OrgUnitType.CHAIR, **kwargs):
        return OrgUnit.objects.create(organization=self.org, name=name, slug=slug, unit_type=kind, **kwargs)

    def legacy_pair(self):
        first = self.unit("Sınaq kafedrası", "first", parent=self.faculty, head=self.user, code="K1")
        second = self.unit("SINAQ KAFEDRASI", "second", OrgUnitType.DEPARTMENT, parent=self.other_faculty, code="K2")
        return first, second

    def guarded_migration(self):
        MigrationExecutor(connection).migrate([self.guarded])

    def assert_name_taken(self, write):
        with self.assertRaises(IntegrityError) as raised, transaction.atomic():
            write()
        self.assertTrue(is_registry_name_collision(raised.exception), raised.exception)

    def test_legacy_links_writes_and_eventual_name_reuse(self):
        first, second = self.legacy_pair()
        for chair in (first, second):
            self.unit("Sınaq ixtisası", f"child-{chair.slug}", OrgUnitType.SPECIALTY, parent=chair)
        role = Role.objects.create(organization=self.org, name="schema_chair", scope_type=RoleScopeType.UNIT)
        for chair in (first, second):
            Membership.objects.create(organization=self.org, user=self.user, role=role, scope_unit=chair)
        units = OrgUnit.objects.filter(organization=self.org).order_by("pk")
        links = Membership.objects.filter(organization=self.org).order_by("pk")
        before = list(units.values())
        linked_before = list(links.values())
        self.guarded_migration()
        self.assertEqual(list(units.values()), before)
        self.assertEqual(list(links.values()), linked_before)
        self.assertFalse(MigrationExecutor(connection).migration_plan([self.guarded]))

        MigrationExecutor(connection).migrate([self.base])
        self.assertEqual(list(units.values()), before)
        self.assertEqual(list(links.values()), linked_before)
        self.guarded_migration()
        self.assertEqual(list(units.values()), before)
        with transaction.atomic():
            units.filter(pk=first.pk).update(name="Müvəqqəti ad")
            transaction.set_rollback(True)
        self.assertEqual(list(units.values()), before)
        self.unit("Müvəqqəti ad", "released-after-rollback", parent=self.faculty)

        self.unit(first.name, "same-faculty-name", OrgUnitType.FACULTY)
        self.unit(first.name, "same-group-name", OrgUnitType.GROUP, parent=first)
        other_org = Organization.objects.create(name="İkinci sınaq", slug="schema-other", owner=self.user)
        OrgUnit.objects.create(organization=other_org, unit_type=OrgUnitType.CHAIR, name=first.name, slug="same")
        third = self.unit("Ayrı kafedra", "third", parent=self.faculty)
        archived = self.unit(first.name, "archived", parent=self.faculty, is_active=False)
        for spelling in (first.name, second.name):
            with self.subTest(spelling=spelling):
                self.assert_name_taken(lambda spelling=spelling: self.unit(spelling, "new", parent=self.faculty))
                self.assert_name_taken(lambda spelling=spelling: units.filter(pk=third.pk).update(name=spelling))
        self.assert_name_taken(lambda: units.filter(pk=archived.pk).update(is_active=True))
        self.assertEqual(units.filter(pk=second.pk).update(code="K2-edited"), 1)
        self.assertEqual(units.filter(pk=first.pk).update(name="Adı yenilənmiş kafedra"), 1)
        self.assert_name_taken(lambda: units.filter(pk=first.pk).update(name=first.name))
        self.assert_name_taken(lambda: units.filter(pk=archived.pk).update(is_active=True))
        self.assertEqual(units.filter(pk=second.pk).update(is_active=False), 1)
        self.assertEqual(units.filter(pk=archived.pk).update(is_active=True), 1)
        self.assert_name_taken(lambda: units.filter(pk=second.pk).update(is_active=True))
        self.assertEqual(list(links.values()), linked_before)

        owned_state = list(units.values())
        MigrationExecutor(connection).migrate([self.base])
        self.assertEqual(list(units.values()), owned_state)
        self.guarded_migration()
        self.assertEqual(list(units.values()), owned_state)
        self.assertEqual(list(links.values()), linked_before)
        self.assert_name_taken(lambda: self.unit(first.name, "after-reapply", parent=self.faculty))

    def test_authorized_registry_form_can_edit_code_and_parent_of_legacy_unit(self):
        first, second = self.legacy_pair()
        original_name = f" {first.name} "
        first.name = original_name
        first.save(update_fields=["name"])
        self.guarded_migration()
        role, _ = Role.objects.update_or_create(
            organization=self.org,
            name="teaching_office_head",
            defaults={
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": ["unit.view", "unit.create", "unit.edit"],
            },
        )
        Membership.objects.create(organization=self.org, user=self.user, role=role, is_primary=True)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        url = reverse("organizations:structure_unit_action", args=[self.org.slug])
        form = {"action": "save_unit", "kind": "kafedra", "id": first.pk, "name": first.name}
        response = self.client.post(url, {**form, "code": "NEW", "parent": self.other_faculty.pk})
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(response.json()["ok"])
        first.refresh_from_db()
        self.assertEqual((first.code, first.parent_id, first.name), ("NEW", self.other_faculty.pk, original_name))
        second.refresh_from_db()
        self.assertEqual((second.code, second.name, second.is_active), ("K2", "SINAQ KAFEDRASI", True))
        duplicate = self.client.post(url, {**form, "id": "", "parent": self.faculty.pk})
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual((duplicate.json()["error"], duplicate.json()["field"]), ("name_taken", "name"))

    def test_model_validation_and_recreating_the_legacy_constraint(self):
        first, second = self.legacy_pair()
        self.guarded_migration()
        constraint = next(c for c in OrgUnit._meta.constraints if c.name == "orgunit_active_registry_name_uniq")
        with connection.schema_editor() as editor:
            editor.remove_constraint(OrgUnit, constraint)
            editor.add_constraint(OrgUnit, constraint)

        first.code = "Edited"
        first.full_clean()
        first.save(update_fields=["code"])
        second.refresh_from_db()
        self.assertEqual((second.name, second.is_active), ("SINAQ KAFEDRASI", True))
        self.assert_name_taken(lambda: self.unit(second.name, "same-new"))
        fresh = OrgUnit(organization=self.org, name=first.name, slug="new", unit_type=OrgUnitType.CHAIR)
        unrelated = self.unit("Ayrıca kafedra", "separate", parent=self.faculty)
        archived = self.unit(first.name, "old", is_active=False)
        unrelated.name = second.name
        archived.is_active = True
        for unit in (fresh, unrelated, archived):
            with self.subTest(slug=unit.slug), self.assertRaises(ValidationError):
                unit.validate_constraints()

    def test_concurrent_release_and_acquisition_of_legacy_name(self):
        first, second = self.legacy_pair()
        self.guarded_migration()
        barrier = Barrier(2)

        def rename(chair):
            try:
                with transaction.atomic():
                    set_rls_tenant(self.org.pk)
                    row = OrgUnit.objects.select_for_update().get(pk=chair.pk)
                    barrier.wait(timeout=10)
                    return OrgUnit.objects.filter(pk=row.pk).update(name=f"Yeni {row.slug}")
            finally:
                connections.close_all()

        def acquire(slug):
            try:
                with transaction.atomic():
                    set_rls_tenant(self.org.pk)
                    barrier.wait(timeout=10)
                    self.unit(first.name, slug, parent=self.faculty)
                return "created"
            except IntegrityError as exc:
                if not is_registry_name_collision(exc):
                    raise
                return "taken"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(rename, (first, second))), [1, 1])
            self.assertCountEqual(list(pool.map(acquire, ("contender-a", "contender-b"))), ["created", "taken"])
        self.assertEqual(OrgUnit.objects.filter(organization=self.org, name=first.name).count(), 1)

    def test_database_with_original_0089_index_already_applied(self):
        first = self.unit("İşıq", "clean", parent=self.faculty)
        # An already released database recorded 0089 and has its original partial unique index.
        # Recreate that exact physical schema before upgrading, independently of the revised 0089.
        projected = MigrationExecutor(connection).loader.project_state([self.old_release]).apps
        old_unit = projected.get_model("organizations", "OrgUnit")
        constraint = next(c for c in old_unit._meta.constraints if c.name == "orgunit_active_registry_name_uniq")
        with connection.schema_editor() as editor:
            editor.add_constraint(old_unit, constraint)
        MigrationExecutor(connection).migrate([self.old_release], fake=True)
        self.assert_name_taken(lambda: self.unit("işıq", "old-index", parent=self.faculty))
        units = OrgUnit.objects.filter(organization=self.org).order_by("pk")
        before = list(units.values())
        self.guarded_migration()
        self.assertEqual(list(units.values()), before)
        self.assert_name_taken(lambda: self.unit("İŞIQ", "after-upgrade", parent=self.faculty))
        self.assertEqual(units.filter(pk=first.pk).update(name="Yeni ad"), 1)
        self.unit("işıq", "reused", parent=self.faculty)
        MigrationExecutor(connection).migrate([self.old_release])
        self.assert_name_taken(lambda: self.unit("İŞIQ", "rollback", parent=self.faculty))
