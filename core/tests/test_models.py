"""
Tests for core abstract models.

Covers:
* ``TitleSlugModel`` – slug auto-generation and collision handling.
* ``SoftDeleteModel`` – default manager excludes soft-deleted rows;
  ``all_objects`` escape hatch exposes every row.
"""

from __future__ import annotations

from django.db import connection, models
from django.test import TransactionTestCase
from django.utils import timezone

from core.models import SoftDeleteModel, TitleSlugModel


# ---------------------------------------------------------------------------
# Concrete models for testing (not backed by migrations)
# ---------------------------------------------------------------------------


class ConcreteSlugModel(TitleSlugModel):
    """Minimal concrete model to exercise TitleSlugModel."""

    class Meta:
        app_label = "core"


class ConcreteSoftDeleteModel(SoftDeleteModel):
    """Minimal concrete model to exercise SoftDeleteModel."""

    name = models.CharField(max_length=64, default="test")

    class Meta:
        app_label = "core"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_table(model_class):
    with connection.schema_editor() as editor:
        editor.create_model(model_class)


def _drop_table_if_exists(model_class):
    table = model_class._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {table}")


# ---------------------------------------------------------------------------
# TitleSlugModel tests
# ---------------------------------------------------------------------------


class TitleSlugModelTest(TransactionTestCase):
    """Tests for TitleSlugModel slug generation and collision handling.

    TransactionTestCase is used so the schema editor can run DDL outside of an
    open transaction (required by SQLite's FK-check enforcement).
    """

    def setUp(self):
        _drop_table_if_exists(ConcreteSlugModel)
        _create_table(ConcreteSlugModel)

    def tearDown(self):
        _drop_table_if_exists(ConcreteSlugModel)

    def test_slug_auto_generated_from_title(self):
        """Saving without a slug should set it from the title."""
        obj = ConcreteSlugModel.objects.create(title="Hello World")
        self.assertEqual(obj.slug, "hello-world")

    def test_provided_slug_is_kept(self):
        """If a slug is already set, it must not be overwritten."""
        obj = ConcreteSlugModel.objects.create(title="Hello World", slug="custom-slug")
        self.assertEqual(obj.slug, "custom-slug")

    def test_duplicate_slug_gets_numeric_suffix(self):
        """A second object with the same title must receive a de-duplicated slug."""
        obj1 = ConcreteSlugModel.objects.create(title="Duplicate Title")
        obj2 = ConcreteSlugModel.objects.create(title="Duplicate Title")
        self.assertEqual(obj1.slug, "duplicate-title")
        self.assertNotEqual(obj1.slug, obj2.slug)
        self.assertTrue(obj2.slug.startswith("duplicate-title-"))

    def test_triple_collision_increments_further(self):
        """Three colliding titles should get three distinct slugs."""
        o1 = ConcreteSlugModel.objects.create(title="Triple")
        o2 = ConcreteSlugModel.objects.create(title="Triple")
        o3 = ConcreteSlugModel.objects.create(title="Triple")
        slugs = {o1.slug, o2.slug, o3.slug}
        self.assertEqual(len(slugs), 3)

    def test_update_does_not_change_existing_slug(self):
        """Updating other fields on an already-saved object must not alter its slug."""
        obj = ConcreteSlugModel.objects.create(title="Stable Slug")
        original_slug = obj.slug
        obj.title = "Changed Title"
        obj.save()
        obj.refresh_from_db()
        self.assertEqual(obj.slug, original_slug)


# ---------------------------------------------------------------------------
# SoftDeleteModel tests
# ---------------------------------------------------------------------------


class SoftDeleteModelTest(TransactionTestCase):
    """Tests for SoftDeleteModel default manager and all_objects escape hatch.

    TransactionTestCase is used so the schema editor can run DDL outside of an
    open transaction (required by SQLite's FK-check enforcement).
    """

    def setUp(self):
        _drop_table_if_exists(ConcreteSoftDeleteModel)
        _create_table(ConcreteSoftDeleteModel)
        self.live = ConcreteSoftDeleteModel.objects.create(name="alive")
        self.dead = ConcreteSoftDeleteModel.all_objects.create(
            name="deleted",
            is_deleted=True,
            deleted_at=timezone.now(),
        )

    def tearDown(self):
        _drop_table_if_exists(ConcreteSoftDeleteModel)

    def test_default_manager_excludes_deleted(self):
        """objects (default) must not return soft-deleted rows."""
        qs = ConcreteSoftDeleteModel.objects.all()
        pks = list(qs.values_list("pk", flat=True))
        self.assertIn(self.live.pk, pks)
        self.assertNotIn(self.dead.pk, pks)

    def test_all_objects_includes_deleted(self):
        """all_objects must return every row, including soft-deleted ones."""
        qs = ConcreteSoftDeleteModel.all_objects.all()
        pks = list(qs.values_list("pk", flat=True))
        self.assertIn(self.live.pk, pks)
        self.assertIn(self.dead.pk, pks)

    def test_newly_created_object_not_deleted_by_default(self):
        """A freshly created object must have is_deleted=False."""
        obj = ConcreteSoftDeleteModel.objects.create(name="fresh")
        self.assertFalse(obj.is_deleted)
        self.assertIsNone(obj.deleted_at)

    def test_soft_deleted_row_not_returned_by_default_filter(self):
        """Filtering via objects must transparently exclude deleted rows."""
        count_default = ConcreteSoftDeleteModel.objects.filter(name="deleted").count()
        self.assertEqual(count_default, 0)

    def test_all_objects_filter_can_reach_deleted(self):
        """all_objects.filter() must be able to find deleted rows by name."""
        count_all = ConcreteSoftDeleteModel.all_objects.filter(name="deleted").count()
        self.assertEqual(count_all, 1)


# ---------------------------------------------------------------------------
# Task 8: concurrent slug generation (race-condition hardening)
# ---------------------------------------------------------------------------


class TitleSlugModelConcurrencyTest(TransactionTestCase):
    """
    Verify that the ``IntegrityError`` retry loop in ``TitleSlugModel.save()``
    correctly handles slug collisions without surfacing errors to callers.

    The IntegrityError path is exercised by pre-inserting a row that occupies
    the first candidate slug, so that the ``super().save()`` call inside
    ``transaction.atomic()`` raises ``IntegrityError`` and the retry loop
    advances to the next suffix.

    TransactionTestCase is required so that savepoint-based error handling
    works correctly (it must not be wrapped in the test transaction).
    """

    def setUp(self):
        _drop_table_if_exists(ConcreteSlugModel)
        _create_table(ConcreteSlugModel)

    def tearDown(self):
        _drop_table_if_exists(ConcreteSlugModel)

    def test_integrity_error_retry_resolves_slug_collision(self):
        """
        When a concurrent writer has already taken the base slug,
        ``TitleSlugModel.save()`` must catch the ``IntegrityError`` raised by
        the unique constraint and succeed by retrying with the next suffix.
        """
        # Pre-occupy the base slug – simulates the "other writer wins" scenario.
        ConcreteSlugModel.objects.create(title="Collision Test", slug="collision-test")

        # Create a second object with the same title and no explicit slug.
        # The retry loop must survive the IntegrityError on "collision-test"
        # and save successfully with "collision-test-1".
        obj = ConcreteSlugModel(title="Collision Test")
        obj.save()  # Must NOT raise IntegrityError

        self.assertIsNotNone(obj.pk)
        self.assertTrue(
            obj.slug.startswith("collision-test-"),
            f"Expected 'collision-test-<N>', got '{obj.slug}'",
        )

    def test_sequential_creation_produces_unique_slugs(self):
        """
        Creating multiple objects with the same title sequentially must
        produce distinct slugs without any errors.
        """
        objects = [ConcreteSlugModel.objects.create(title="Same Title") for _ in range(5)]
        slugs = [o.slug for o in objects]
        self.assertEqual(len(set(slugs)), 5, f"Duplicate slugs detected: {slugs}")
