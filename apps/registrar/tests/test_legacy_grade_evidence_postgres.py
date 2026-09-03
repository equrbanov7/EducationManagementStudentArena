"""PostgreSQL RLS and append-only guards for legacy-grade evidence."""

import os
import uuid
from contextlib import contextmanager

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction

import pytest

from apps.organizations.models import Membership, Organization, Role
from apps.registrar.models import (
    LegacyGradeArtifact,
    LegacyGradeFact,
    LegacyGradeMappingStatus,
    LegacyGradeReview,
    LegacyGradeReviewDecision,
)
from apps.registrar.tests.test_legacy_grade_evidence import (
    _REVIEW_DIGEST,
    LegacyGradeEvidenceModelTests,
)
from core.constants import OrganizationType
from core.rls import bypass_rls

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL triggers are required."),
]


class LegacyGradeEvidencePostgresTests(LegacyGradeEvidenceModelTests):
    # PostgreSQL rolları KLASTER səviyyəsindədir (DB-yə bağlı deyil): pytest-xdist
    # worker-ləri paralel işləyəndə eyni adlı rol yarat/sil toqquşur (başqa
    # worker-in DB-sindəki GRANT DROP ROLE-u bloklayır). Ad worker-ə görə ayrılır.
    _PROBE_ROLE = "ems_legacy_grade_probe" + os.environ.get("PYTEST_XDIST_WORKER", "")
    _TABLES = (
        "registrar_legacygradereview",
        "registrar_legacygradefact",
        "registrar_legacygradeartifact",
    )

    def setUp(self):
        super().setUp()
        self.owner_b = type(self.owner).objects.create_user(
            "legacy_pg_owner_b",
            "legacy-pg-owner-b@example.test",
            "pw",
        )
        self.outsider = type(self.owner).objects.create_user(
            "legacy_pg_outsider",
            "legacy-pg-outsider@example.test",
            "pw",
        )
        with bypass_rls():
            self.org_b = Organization.objects.create(
                name="Legacy PG B",
                slug="legacy-pg-b",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner_b,
                status="active",
                is_active=True,
            )

    def _enable_tenant(self, organization, user):
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(organization.pk)])
            cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(user.pk)])
            cursor.execute("SET LOCAL ROLE rls_app_role")

    def _reset_tenant(self):
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
            cursor.execute("SELECT set_config('app.current_org_id', '', true)")
            cursor.execute("SELECT set_config('app.current_user_id', '', true)")

    def _raw_review_insert(self, *, fact, actor, actor_name=None, organization=None):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO registrar_legacygradereview "
                "(created_at, updated_at, id, organization_id, fact_id, decision, reason_code, note, "
                "evidence_digest, reviewed_by_id, reviewed_by_name) "
                "VALUES (CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    uuid.uuid4(),
                    (organization or fact.organization).pk,
                    fact.pk,
                    LegacyGradeReviewDecision.VERIFIED,
                    "raw_review_probe",
                    "",
                    _REVIEW_DIGEST,
                    actor.pk,
                    actor_name if actor_name is not None else (actor.get_full_name() or actor.username),
                ],
            )

    def _raw_rejects(self, statement, params=()):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(statement, params)

    def _drop_probe_role(self, cursor):
        cursor.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{self._PROBE_ROLE}') THEN
                    DROP OWNED BY {self._PROBE_ROLE};
                    DROP ROLE {self._PROBE_ROLE};
                END IF;
            END
            $$
            """)

    @contextmanager
    def _nonsuper_probe_role(self):
        with connection.cursor() as cursor:
            self._drop_probe_role(cursor)
            cursor.execute(f"CREATE ROLE {self._PROBE_ROLE}")
            cursor.execute(f"GRANT TRUNCATE ON TABLE {', '.join(self._TABLES)} TO {self._PROBE_ROLE}")
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET SESSION AUTHORIZATION")
                self._drop_probe_role(cursor)

    def _truncate_rejects(self, table):
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        with self._nonsuper_probe_role():
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(f"SET SESSION AUTHORIZATION {self._PROBE_ROLE}")
                        cursor.execute(f"TRUNCATE TABLE {table} CASCADE")

    def test_rls_isolates_fact_and_review_and_blocks_cross_tenant_insert(self):
        with bypass_rls():
            fact_a = self._fact(source_pk=10)
            review_a = self._review(fact_a)
            artifact_a = self._artifact(source_pk=10)
            fact_b = self._fact(source_pk=11, organization=self.org_b, enrollment=None)
            artifact_b = self._artifact(source_pk=11, organization=self.org_b)
            review_b = LegacyGradeReview.objects.create(
                organization=self.org_b,
                fact=fact_b,
                decision=LegacyGradeReviewDecision.VERIFIED,
                reason_code="exam_center_verified",
                evidence_digest=_REVIEW_DIGEST,
                reviewed_by=self.owner_b,
                reviewed_by_name=self.owner_b.username,
            )

        self._enable_tenant(self.org, self.owner)
        try:
            self.assertEqual(list(LegacyGradeFact.objects.values_list("pk", flat=True)), [fact_a.pk])
            self.assertEqual(list(LegacyGradeReview.objects.values_list("pk", flat=True)), [review_a.pk])
            self.assertEqual(list(LegacyGradeArtifact.objects.values_list("pk", flat=True)), [artifact_a.pk])
            self.assertFalse(LegacyGradeFact.objects.filter(pk=fact_b.pk).exists())
            self.assertFalse(LegacyGradeReview.objects.filter(pk=review_b.pk).exists())
            self.assertFalse(LegacyGradeArtifact.objects.filter(pk=artifact_b.pk).exists())
            with self.assertRaises(DatabaseError) as blocked:
                with transaction.atomic():
                    self._fact(source_pk=12, organization=self.org_b, enrollment=None)
            # PostgreSQL BEFORE INSERT authorization trigger-i RLS WITH CHECK-dən
            # əvvəl işləyə bilər; hər iki fail-closed nəticə qanunidir.
            self.assertTrue(
                "row-level security" in str(blocked.exception).lower()
                or "import actor is not authorized" in str(blocked.exception).lower()
            )
            with self.assertRaises(DatabaseError) as blocked_review:
                with transaction.atomic():
                    # Model full_clean gizli FK-ni daha tez rədd edir; raw probe
                    # DB-də RLS + session-actor sərhədini birbaşa yoxlayır.
                    self._raw_review_insert(fact=fact_b, actor=self.owner_b, organization=self.org_b)
            self.assertTrue(
                "row-level security" in str(blocked_review.exception).lower()
                or "must match the authenticated actor" in str(blocked_review.exception).lower()
            )
        finally:
            self._reset_tenant()

    def test_insert_guards_reject_cross_organization_links(self):
        with bypass_rls():
            fact_a = self._fact(source_pk=20)
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    self._fact(source_pk=21, organization=self.org_b)
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    self._raw_review_insert(fact=fact_a, actor=self.owner_b, organization=self.org_b)

    def test_fact_insert_guard_rejects_inconsistent_mapping_evidence(self):
        cases = (
            {
                "enrollment": None,
                "mapping_status": LegacyGradeMappingStatus.LINKED,
                "mapping_issue_code": "",
            },
            {
                "mapping_status": LegacyGradeMappingStatus.UNRESOLVED,
                "mapping_issue_code": "legacy_grade_fact_unresolved",
            },
            {
                "mapping_status": LegacyGradeMappingStatus.LINKED,
                "mapping_issue_code": "legacy_grade_fact_conflict",
            },
            {
                "mapping_status": LegacyGradeMappingStatus.LINKED,
                "mapping_issue_code": "",
                "source_enrollment_ref": "",
            },
        )
        with bypass_rls():
            for offset, kwargs in enumerate(cases, start=1):
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(IntegrityError):
                        with transaction.atomic():
                            self._fact(source_pk=20 + offset, **kwargs)

    def test_authorized_reviewer_passes_and_outsider_is_rejected(self):
        with bypass_rls():
            fact = self._fact(source_pk=30)
        self._enable_tenant(self.org, self.owner)
        try:
            accepted = self._review(fact)
            self.assertIsNotNone(accepted.pk)
        finally:
            self._reset_tenant()

        self._enable_tenant(self.org, self.outsider)
        try:
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    self._raw_review_insert(fact=fact, actor=self.outsider)
        finally:
            self._reset_tenant()

    def test_authenticated_actor_binding_permission_and_name_snapshot_are_database_enforced(self):
        with bypass_rls():
            fact = self._fact(source_pk=31)

        self._enable_tenant(self.org, self.teacher)
        try:
            cases = (
                (self.owner, None),  # another authorized actor's identity cannot be borrowed
                (self.teacher, None),  # same actor still lacks final_score.entry
                (self.owner, "spoofed-name"),
            )
            for actor, actor_name in cases:
                with self.subTest(actor=actor.username, actor_name=actor_name):
                    with self.assertRaises(IntegrityError):
                        with transaction.atomic():
                            self._raw_review_insert(fact=fact, actor=actor, actor_name=actor_name)
        finally:
            self._reset_tenant()

    def test_ordinary_tenant_member_cannot_forge_imported_grade_fact(self):
        self._enable_tenant(self.org, self.student)
        try:
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    self._fact(source_pk=32)
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    self._artifact(source_pk=32)
        finally:
            self._reset_tenant()

        self._enable_tenant(self.org, self.owner)
        try:
            accepted = self._fact(source_pk=33)
            self.assertIsNotNone(accepted.pk)
            artifact = self._artifact(source_pk=33)
            self.assertIsNotNone(artifact.pk)
        finally:
            self._reset_tenant()

    def test_member_invite_permission_does_not_authorize_grade_import(self):
        importer = type(self.owner).objects.create_user(
            "legacy_pg_member_invite",
            "legacy-pg-member-invite@example.test",
            "pw",
        )
        with bypass_rls():
            role = Role.objects.create(
                organization=self.org,
                name="legacy_member_inviter",
                display_name="Legacy member inviter",
                level=50,
                permissions=["member.invite"],
                is_active=True,
            )
            Membership.objects.create(
                organization=self.org,
                user=importer,
                role=role,
                is_active=True,
            )

        self._enable_tenant(self.org, importer)
        try:
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    self._fact(source_pk=34)
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    self._artifact(source_pk=34)
        finally:
            self._reset_tenant()

    def test_raw_update_delete_and_material_truncate_are_rejected(self):
        with bypass_rls():
            fact = self._fact(source_pk=40)
            review = self._review(fact)
            artifact = self._artifact(source_pk=40)

        cases = (
            (
                "UPDATE registrar_legacygradefact SET final_score_text = %s WHERE id = %s",
                ["100", fact.pk],
            ),
            ("DELETE FROM registrar_legacygradefact WHERE id = %s", [fact.pk]),
            (
                "UPDATE registrar_legacygradereview SET note = %s WHERE id = %s",
                ["rewritten", review.pk],
            ),
            ("DELETE FROM registrar_legacygradereview WHERE id = %s", [review.pk]),
            (
                "UPDATE registrar_legacygradeartifact SET source_owner_ref = %s WHERE id = %s",
                ["18", artifact.pk],
            ),
            ("DELETE FROM registrar_legacygradeartifact WHERE id = %s", [artifact.pk]),
        )
        for statement, params in cases:
            with self.subTest(statement=statement):
                self._raw_rejects(statement, params)

        self._truncate_rejects("registrar_legacygradereview")
        self._truncate_rejects("registrar_legacygradefact")
        self._truncate_rejects("registrar_legacygradeartifact")
        with bypass_rls():
            self.assertTrue(LegacyGradeFact.objects.filter(pk=fact.pk).exists())
            self.assertTrue(LegacyGradeReview.objects.filter(pk=review.pk).exists())
            self.assertTrue(LegacyGradeArtifact.objects.filter(pk=artifact.pk).exists())

    def test_security_functions_triggers_and_forced_rls_are_hardened(self):
        functions = {
            "registrar_actor_can_import_legacy_grade",
            "registrar_actor_can_review_legacy_grade",
            "registrar_guard_legacy_grade_append_only",
            "registrar_guard_legacy_grade_fact_insert",
            "registrar_guard_legacy_grade_review_insert",
            "registrar_guard_legacy_grade_artifact_insert",
        }
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT p.proname, p.prosecdef, p.proconfig, "
                "has_function_privilege('rls_app_role', p.oid, 'EXECUTE'), "
                "EXISTS (SELECT 1 FROM aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) acl "
                "WHERE acl.grantee = 0 AND acl.privilege_type = 'EXECUTE') "
                "FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace "
                "AND p.proname = ANY(%s)",
                [list(functions)],
            )
            function_rows = cursor.fetchall()
            cursor.execute(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class " "WHERE oid = ANY(%s::regclass[])",
                [[f"public.{table}" for table in self._TABLES]],
            )
            rls_rows = cursor.fetchall()
            cursor.execute(
                "SELECT tgname, count(*) FROM pg_trigger WHERE NOT tgisinternal "
                "AND tgrelid = ANY(%s::regclass[]) GROUP BY tgname",
                [[f"public.{table}" for table in self._TABLES]],
            )
            triggers = dict(cursor.fetchall())

        self.assertEqual({row[0] for row in function_rows}, functions)
        for _name, security_definer, config, restricted_execute, public_execute in function_rows:
            self.assertTrue(security_definer)
            self.assertIn("search_path=pg_catalog, public", config)
            self.assertFalse(restricted_execute)
            self.assertFalse(public_execute)
        self.assertEqual(
            {(name, rls, forced) for name, rls, forced in rls_rows}, {(t, True, True) for t in self._TABLES}
        )
        self.assertEqual(triggers["registrar_legacy_grade_append_only_update"], 2)
        self.assertEqual(triggers["registrar_legacy_grade_append_only_delete"], 2)
        self.assertEqual(triggers["registrar_legacy_grade_append_only_truncate"], 2)
        self.assertEqual(triggers["registrar_legacy_grade_artifact_append_only_update"], 1)
        self.assertEqual(triggers["registrar_legacy_grade_artifact_append_only_delete"], 1)
        self.assertEqual(triggers["registrar_legacy_grade_artifact_append_only_truncate"], 1)
        self.assertEqual(triggers["registrar_legacy_grade_fact_insert"], 1)
        self.assertEqual(triggers["registrar_legacy_grade_review_insert"], 1)
        self.assertEqual(triggers["registrar_legacy_grade_artifact_insert"], 1)

    def test_queryset_guards_still_raise_before_postgres_write(self):
        with bypass_rls():
            fact = self._fact(source_pk=50)
        with self.assertRaises(ValidationError):
            LegacyGradeFact.objects.filter(pk=fact.pk).update(mapping_status=LegacyGradeMappingStatus.CONFLICT)
