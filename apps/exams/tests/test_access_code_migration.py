"""PostgreSQL migration regression for reversible access-code encryption."""

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

import pytest

from apps.exams.models import Exam
from apps.exams.services.access_code_crypto import decrypt_access_code
from apps.organizations.models import Organization
from core.constants import OrganizationType

# Miqrasiya round-trip (migrate → sıfıra → geri) testləri xdist-də 4 worker-in
# paralel miqrasiyası altında 300 s qlobal limiti keçə bilir (Develop run
# 33778014237 flake-i); modul üçün limit ayrıca qaldırılır.
pytestmark = [pytest.mark.postgres, pytest.mark.timeout(1200)]
User = get_user_model()


@pytest.mark.skipif(connection.vendor != "postgresql", reason="Migration rollback is verified on PostgreSQL.")
class AccessCodeMigrationRollbackTests(TransactionTestCase):
    reset_sequences = True

    migrate_from = ("exams", "0050_access_code_encrypted_at_rest")
    migrate_to = ("exams", "0049_attempt_autosave_revision")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        self.latest_targets = executor.loader.graph.leaf_nodes()
        executor.migrate([self.migrate_from])
        self._realign_sequences()

    def _realign_sequences(self):
        # Qraf-dakı seed data-migration-ları ``auth_user`` sətirlərini EXPLICIT PK
        # ilə yaradır və serial sequence-i irəli aparmır; ``reset_sequences`` isə
        # onu 1-ə salır. Nəticədə aşağıdakı ``create_user`` mövcud id ilə toqquşur.
        # Integer-serial pk-lı cədvəllərin sequence-ini max(id)-ə köklə (org UUID-
        # pk-dır — sequence-i yoxdur, toqquşmur).
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence('auth_user', 'id'), "
                "GREATEST((SELECT COALESCE(MAX(id), 1) FROM auth_user), 1))"
            )

    def tearDown(self):
        # Restore the full graph before TransactionTestCase flushes the DB.
        MigrationExecutor(connection).migrate(self.latest_targets)
        super().tearDown()

    def test_reverse_migration_restores_plaintext_for_the_old_charfield(self):
        teacher = User.objects.create_user("access_migration_teacher", password="pw")
        org = Organization.objects.create(
            name="Access migration org",
            org_type=OrganizationType.SCHOOL,
            owner=teacher,
            status="active",
            is_active=True,
        )
        exam = Exam.objects.create(
            title="Encrypted rollback exam",
            author=teacher,
            organization=org,
            access_code="135790",
        )

        with connection.cursor() as cursor:
            cursor.execute("SELECT access_code FROM exams_exam WHERE id = %s", [exam.pk])
            encrypted = cursor.fetchone()[0]
        self.assertNotEqual(encrypted, "135790")
        self.assertEqual(decrypt_access_code(encrypted), "135790")

        MigrationExecutor(connection).migrate([self.migrate_to])

        with connection.cursor() as cursor:
            cursor.execute("SELECT access_code FROM exams_exam WHERE id = %s", [exam.pk])
            rolled_back = cursor.fetchone()[0]
        self.assertEqual(rolled_back, "135790")
