import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace

from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.test import TestCase

import pytest

from apps.accounts.identity import canonical_identity_queryset, staged_user_for_email
from apps.accounts.models import AccountActivationEvidence, UserProfile
from apps.accounts.services import activate_staged_account, stage_imported_account
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL identity guards are required."),
]


class IdentityPostgresGuardTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_superuser(
            "identity_pg_root",
            "identity-pg-root@example.com",
            "Root-Password-123!",
        )
        self.organization = Organization.objects.create(
            name="Identity PG University",
            slug="identity-pg-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.actor,
            status="active",
            is_active=True,
        )
        self.role = self.organization.roles.get(name="student")

    def _stage(self, suffix="1"):
        return stage_imported_account(
            organization=self.organization,
            role=self.role,
            actor=self.actor,
            username=f"identity_pg_staged_{suffix}",
            email=f"identity-pg-staged-{suffix}@example.com",
            student_identifier=f"PG-STU-{suffix}",
        ).user

    def _rejects(self, statement, params):
        with self.assertRaises((DatabaseError, IntegrityError)):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(statement, params)

    # PostgreSQL rolları KLASTER səviyyəsindədir (DB-yə bağlı deyil): pytest-xdist
    # worker-ləri paralel işləyəndə eyni adlı rol yarat/sil toqquşur (başqa
    # worker-in DB-sindəki GRANT DROP ROLE-u bloklayır). Ad worker-ə görə ayrılır.
    _PROBE_ROLE = "ems_guard_probe" + os.environ.get("PYTEST_XDIST_WORKER", "")
    _PROBE_TABLES = ("accounts_accountactivationevidence",)

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
            cursor.execute(f"GRANT TRUNCATE ON TABLE {', '.join(self._PROBE_TABLES)} TO {self._PROBE_ROLE}")
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET SESSION AUTHORIZATION")
                self._drop_probe_role(cursor)

    def _rejects_truncate_as_nonsuper(self, statement):
        # Flush deferred FK events so PostgreSQL reaches the BEFORE TRUNCATE
        # guard inside the wrapping test transaction.
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        # The guard waves superusers through (they could DROP the trigger
        # anyway) by checking session_user, which SET ROLE does not change.
        # Probe it under a guaranteed non-superuser role instead.
        with self._nonsuper_probe_role():
            with self.assertRaises((DatabaseError, IntegrityError)):
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(f"SET SESSION AUTHORIZATION {self._PROBE_ROLE}")
                        cursor.execute(statement)

    def test_nfkc_expression_indexes_reject_raw_unicode_canonical_duplicates(self):
        first = User.objects.create_user("FullWidthUser", email="fullwidth.email@example.com")
        first.profile.organization = self.organization
        first.profile.institutional_identifier = "STU-FullWidth"
        first.profile.save(update_fields=["organization", "institutional_identifier", "updated_at"])

        self._rejects(
            """
            INSERT INTO auth_user
                (password, last_login, is_superuser, username, first_name, last_name,
                 email, is_staff, is_active, date_joined)
            VALUES (%s, NULL, FALSE, %s, '', '', %s, FALSE, FALSE, CURRENT_TIMESTAMP)
            """,
            ["!", "ＦｕｌｌＷｉｄｔｈＵｓｅｒ", "another-unicode@example.com"],
        )
        self._rejects(
            """
            INSERT INTO auth_user
                (password, last_login, is_superuser, username, first_name, last_name,
                 email, is_staff, is_active, date_joined)
            VALUES (%s, NULL, FALSE, %s, '', '', %s, FALSE, FALSE, CURRENT_TIMESTAMP)
            """,
            ["!", "another_unicode_user", "ＦＵＬＬＷＩＤＴＨ．ＥＭＡＩＬ@example.com"],
        )
        self._rejects(
            """
            INSERT INTO auth_user
                (password, last_login, is_superuser, username, first_name, last_name,
                 email, is_staff, is_active, date_joined)
            VALUES (%s, NULL, FALSE, %s, '', '', %s, FALSE, FALSE, CURRENT_TIMESTAMP)
            """,
            ["!", "fullwidth.email@example.com", "cross-column@example.com"],
        )

        second = User.objects.create_user("unicode_student_second", email="unicode-second@example.com")
        self._rejects(
            """
            UPDATE accounts_userprofile
               SET organization_id = %s, institutional_identifier = %s
             WHERE user_id = %s
            """,
            [str(self.organization.pk), "ＳＴＵ－ＦｕｌｌＷｉｄｔｈ", second.pk],
        )

    def test_nfkc_login_and_staged_email_use_indexed_canonical_lookup(self):
        normal = User.objects.create_user(
            "IndexedCanonicalLogin",
            email="indexed-canonical-login@example.com",
            password="Indexed-Password-123!",
        )
        self.assertEqual(
            authenticate(
                username="ＩｎｄｅｘｅｄＣａｎｏｎｉｃａｌＬｏｇｉｎ",
                password="Indexed-Password-123!",
            ).pk,
            normal.pk,
        )
        self.assertEqual(
            authenticate(
                username="ｉｎｄｅｘｅｄ－ｃａｎｏｎｉｃａｌ－ｌｏｇｉｎ＠ｅｘａｍｐｌｅ．ｃｏｍ",
                password="Indexed-Password-123!",
            ).pk,
            normal.pk,
        )

        staged = self._stage("indexed-email")
        self.assertEqual(
            staged_user_for_email(
                "ｉｄｅｎｔｉｔｙ－ｐｇ－ｓｔａｇｅｄ－ｉｎｄｅｘｅｄ－ｅｍａｉｌ＠ｅｘａｍｐｌｅ．ｃｏｍ"
            ).pk,
            staged.pk,
        )
        lookup = canonical_identity_queryset(
            User.objects.all(),
            "username",
            "ＩｎｄｅｘｅｄＣａｎｏｎｉｃａｌＬｏｇｉｎ",
            alias="_explain_login_key",
        )
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL enable_seqscan = off")
        self.assertIn("accounts_auth_username_canon_uniq", lookup.explain())

    def test_raw_staged_activation_and_active_staged_profile_are_rejected(self):
        active = User.objects.create_user("identity_pg_active", email="identity-pg-active@example.com")
        self._rejects(
            "UPDATE accounts_userprofile SET access_state = 'staged' WHERE user_id = %s",
            [active.pk],
        )

        staged = self._stage()
        self._rejects("UPDATE auth_user SET is_active = TRUE WHERE id = %s", [staged.pk])
        self._rejects(
            "UPDATE accounts_userprofile SET access_state = 'active' WHERE user_id = %s",
            [staged.pk],
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.account_activation_unlock', 'on', true)")
            cursor.execute(
                "SELECT set_config('app.account_activation_evidence_id', %s, true)",
                [str(uuid.uuid4())],
            )
        self._rejects(
            "UPDATE accounts_userprofile SET access_state = 'active' WHERE user_id = %s",
            [staged.pk],
        )

    def test_service_uses_consumed_evidence_and_transaction_local_context(self):
        staged = self._stage("service")
        result = activate_staged_account(
            user=staged,
            organization=self.organization,
            expected_role=self.role,
            actor=self.actor,
            email_authoritative=True,
            email_authority_evidence_digest="b" * 64,
            email_authority_reason_code="signed_authoritative_export",
        )
        self.assertTrue(result.activated)
        evidence = AccountActivationEvidence.objects.get(user_ref=str(staged.pk))
        self.assertIsNotNone(evidence.consumed_at)
        self.assertGreater(evidence.transaction_id, 0)
        activation_log = AuditLog.objects.get(pk=evidence.pk)
        self.assertEqual(activation_log.user_id, self.actor.pk)
        self.assertEqual(activation_log.organization_id, self.organization.pk)
        self.assertEqual(
            activation_log.changes,
            {
                "activation_evidence_id": str(evidence.pk),
                "email_authority_evidence_digest": "b" * 64,
                "email_authority_reason_code": "signed_authoritative_export",
                "role_id": str(self.role.pk),
            },
        )

        self._rejects(
            "UPDATE accounts_accountactivationevidence SET reason_code = %s WHERE id = %s",
            ["manual_registry_verification", str(evidence.pk)],
        )
        self._rejects(
            "DELETE FROM accounts_accountactivationevidence WHERE id = %s",
            [str(evidence.pk)],
        )
        self._rejects_truncate_as_nonsuper("TRUNCATE TABLE accounts_accountactivationevidence")
        self._rejects(
            """
            INSERT INTO accounts_accountactivationevidence (
                id, organization_id, user_ref, role_ref, actor_ref,
                evidence_digest, reason_code, transaction_id, created_at, consumed_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, txid_current(), NOW(), NULL)
            """,
            [
                str(uuid.uuid4()),
                str(self.organization.pk),
                "raw-user",
                str(self.role.pk),
                str(self.actor.pk),
                "c" * 64,
                "signed_authoritative_export",
            ],
        )

        direct = connection.Database.connect(**connection.get_connection_params())
        try:
            with direct.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.account_activation_evidence_id', %s, true)",
                    [str(uuid.uuid4())],
                )
                cursor.execute("SELECT current_setting('app.account_activation_evidence_id', true)")
                self.assertNotEqual(cursor.fetchone(), ("",))
            direct.commit()
            with direct.cursor() as cursor:
                cursor.execute("SELECT current_setting('app.account_activation_evidence_id', true)")
                self.assertIn(cursor.fetchone()[0], ("", None))
        finally:
            direct.close()

    def test_guard_functions_are_security_definer_without_public_execute(self):
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT proc.proname, proc.prosecdef,
                       EXISTS (
                           SELECT 1
                             FROM aclexplode(
                                 COALESCE(proc.proacl, acldefault('f', proc.proowner))
                             ) AS acl
                            WHERE acl.grantee = 0
                              AND acl.privilege_type = 'EXECUTE'
                       ) AS public_execute
                  FROM pg_proc AS proc
                 WHERE proc.proname IN (
                    'accounts_activate_staged_identity',
                    'accounts_activation_evidence_immutable',
                    'accounts_reject_cross_field_identity_collision',
                    'accounts_reject_staged_user_activation',
                    'accounts_reject_active_staged_profile'
                 )
                 ORDER BY proname
                """)
            rows = cursor.fetchall()
        self.assertEqual(
            rows,
            [
                ("accounts_activate_staged_identity", True, False),
                ("accounts_activation_evidence_immutable", True, False),
                ("accounts_reject_active_staged_profile", True, False),
                ("accounts_reject_cross_field_identity_collision", True, False),
                ("accounts_reject_staged_user_activation", True, False),
            ],
        )
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT has_function_privilege(
                    'rls_app_role',
                    'public.accounts_activate_staged_identity('
                    'uuid,bigint,uuid,uuid,bigint,text,text)',
                    'EXECUTE'
                ),
                has_table_privilege(
                    'rls_app_role',
                    'public.accounts_accountactivationevidence',
                    'INSERT'
                )
                """)
            function_execute, table_insert = cursor.fetchone()
        self.assertTrue(function_execute)
        self.assertFalse(table_insert)

    def test_non_bypass_application_role_keeps_real_actor_rbac_and_tenant_scope(self):
        operator = User.objects.create_user(
            "identity_pg_operator",
            email="identity-pg-operator@example.com",
            password="Operator-Password-123!",
        )
        Membership.objects.create(
            user=operator,
            organization=self.organization,
            role=self.organization.roles.get(name="rector"),
            is_active=True,
            is_primary=True,
            assigned_by=self.actor,
        )
        other_owner = User.objects.create_user("identity_pg_other_owner", email="identity-other-owner@example.com")
        other_org = Organization.objects.create(
            name="Identity PG Other",
            slug="identity-pg-other",
            org_type=OrganizationType.UNIVERSITY,
            owner=other_owner,
            status="active",
            is_active=True,
        )
        other_role = other_org.roles.get(name="student")

        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.organization.pk)])
            cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(operator.pk)])
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:
            staged = stage_imported_account(
                organization=self.organization,
                role=self.role,
                actor=operator,
                username="identity_pg_rls_staged",
                email="identity-pg-rls-staged@example.com",
                student_identifier="PG-RLS-1",
            ).user
            self.assertEqual(staged.profile.access_state, UserProfile.AccessState.STAGED)

            with self.assertRaises(PermissionDenied):
                stage_imported_account(
                    organization=other_org,
                    role=other_role,
                    actor=operator,
                    username="identity_pg_cross_tenant",
                    email="identity-pg-cross-tenant@example.com",
                    student_identifier="PG-RLS-X",
                )
            with self.assertRaisesRegex(PermissionDenied, "identity_actor_mismatch"):
                stage_imported_account(
                    organization=self.organization,
                    role=self.role,
                    actor=operator,
                    username="identity_pg_fake_actor",
                    email="identity-pg-fake-actor@example.com",
                    student_identifier="PG-RLS-Y",
                    request=SimpleNamespace(real_user=self.actor, user=self.actor),
                )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def test_activation_function_rejects_wrong_actor_tenant_role_and_evidence(self):
        operator = User.objects.create_user(
            "identity_pg_activation_operator",
            email="identity-pg-activation-operator@example.com",
        )
        Membership.objects.create(
            user=operator,
            organization=self.organization,
            role=self.organization.roles.get(name="rector"),
            is_active=True,
            is_primary=True,
            assigned_by=self.actor,
        )
        staged = stage_imported_account(
            organization=self.organization,
            role=self.role,
            actor=operator,
            username="identity_pg_function_target",
            email="identity-pg-function-target@example.com",
            student_identifier="PG-FUNCTION-1",
        ).user
        inactive_actor = User.objects.create_user(
            "identity_pg_inactive_actor",
            email="identity-pg-inactive-actor@example.com",
            is_active=False,
        )
        other_org = Organization.objects.create(
            name="Identity Function Other",
            slug="identity-function-other",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.actor,
            status="active",
            is_active=True,
        )
        other_role = other_org.roles.get(name="student")
        other_target = stage_imported_account(
            organization=other_org,
            role=other_role,
            actor=self.actor,
            username="identity_pg_function_other_target",
            email="identity-pg-function-other-target@example.com",
            student_identifier="PG-FUNCTION-X",
        ).user

        def activation_params(*, target=staged, org=None, role=None, actor=operator, digest=None):
            return [
                str(uuid.uuid4()),
                target.pk,
                str((org or self.organization).pk),
                str((role or self.role).pk),
                actor.pk,
                digest or "d" * 64,
                "signed_authoritative_export",
            ]

        statement = """
            SELECT public.accounts_activate_staged_identity(
                %s, %s, %s, %s, %s, %s, %s
            )
        """
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.organization.pk)])
            cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(operator.pk)])
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:
            self._rejects(statement, activation_params(digest="not-a-digest"))
            self._rejects(
                statement,
                activation_params(role=self.organization.roles.get(name="member")),
            )
            self._rejects(
                statement,
                activation_params(target=other_target, org=other_org, role=other_role),
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.current_user_id', %s, true)",
                    [str(inactive_actor.pk)],
                )
            self._rejects(statement, activation_params(actor=inactive_actor))
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(operator.pk)])

            result = activate_staged_account(
                user=staged,
                organization=self.organization,
                expected_role=self.role,
                actor=operator,
                email_authoritative=True,
                email_authority_evidence_digest="d" * 64,
                email_authority_reason_code="signed_authoritative_export",
            )
            self.assertTrue(result.activated)
            evidence = AccountActivationEvidence.objects.get(user_ref=str(staged.pk))
            self.assertEqual(evidence.actor_ref, str(operator.pk))
            self.assertEqual(evidence.role_ref, str(self.role.pk))
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def test_evidence_rls_and_application_role_write_denials(self):
        first = self._stage("rls-first")
        activate_staged_account(
            user=first,
            organization=self.organization,
            expected_role=self.role,
            actor=self.actor,
            email_authoritative=True,
            email_authority_evidence_digest="e" * 64,
            email_authority_reason_code="institution_registry_match",
        )
        other_org = Organization.objects.create(
            name="Identity Evidence Other",
            slug="identity-evidence-other",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.actor,
            status="active",
            is_active=True,
        )
        other_role = other_org.roles.get(name="student")
        second = stage_imported_account(
            organization=other_org,
            role=other_role,
            actor=self.actor,
            username="identity_pg_rls_second",
            email="identity-pg-rls-second@example.com",
            student_identifier="PG-RLS-SECOND",
        ).user
        activate_staged_account(
            user=second,
            organization=other_org,
            expected_role=other_role,
            actor=self.actor,
            email_authoritative=True,
            email_authority_evidence_digest="f" * 64,
            email_authority_reason_code="manual_registry_verification",
        )

        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.organization.pk)])
            cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(self.actor.pk)])
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:
            visible = list(AccountActivationEvidence.objects.values_list("organization_id", flat=True))
            self.assertEqual(visible, [self.organization.pk])
            evidence = AccountActivationEvidence.objects.get(organization=self.organization)
            self._rejects(
                """
                INSERT INTO accounts_accountactivationevidence (
                    id, organization_id, user_ref, role_ref, actor_ref,
                    evidence_digest, reason_code, transaction_id,
                    created_at, consumed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, txid_current(), NOW(), NULL)
                """,
                [
                    str(uuid.uuid4()),
                    str(self.organization.pk),
                    "app-role-raw-user",
                    str(self.role.pk),
                    str(self.actor.pk),
                    "1" * 64,
                    "signed_authoritative_export",
                ],
            )
            self._rejects(
                "UPDATE accounts_accountactivationevidence SET reason_code = %s WHERE id = %s",
                ["signed_authoritative_export", str(evidence.pk)],
            )
            self._rejects(
                "DELETE FROM accounts_accountactivationevidence WHERE id = %s",
                [str(evidence.pk)],
            )
            self._rejects("TRUNCATE TABLE accounts_accountactivationevidence", [])
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def test_activation_audit_failure_rolls_back_function_and_evidence(self):
        staged = self._stage("audit-rollback")
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE FUNCTION accounts_test_reject_activation_audit()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $function$
                BEGIN
                    RAISE EXCEPTION USING
                        ERRCODE = 'P0001',
                        MESSAGE = 'identity_test_audit_failure';
                END;
                $function$;
                CREATE TRIGGER accounts_test_reject_activation_audit_trg
                BEFORE INSERT ON audit_auditlog
                FOR EACH ROW
                WHEN (NEW.reason = 'legacy_account_activated')
                EXECUTE FUNCTION accounts_test_reject_activation_audit();
                """)
        try:
            with self.assertRaisesRegex(DatabaseError, "identity_test_audit_failure"):
                activate_staged_account(
                    user=staged,
                    organization=self.organization,
                    expected_role=self.role,
                    actor=self.actor,
                    email_authoritative=True,
                    email_authority_evidence_digest="a" * 64,
                    email_authority_reason_code="signed_authoritative_export",
                )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("""
                    DROP TRIGGER accounts_test_reject_activation_audit_trg
                        ON audit_auditlog;
                    DROP FUNCTION accounts_test_reject_activation_audit();
                    """)
        staged.refresh_from_db()
        staged.profile.refresh_from_db()
        membership = Membership.objects.get(user=staged, organization=self.organization)
        self.assertFalse(staged.is_active)
        self.assertEqual(staged.profile.access_state, UserProfile.AccessState.STAGED)
        self.assertFalse(membership.is_active)
        self.assertFalse(AccountActivationEvidence.objects.filter(user_ref=str(staged.pk)).exists())

    def test_concurrent_nfkc_equivalent_username_inserts_have_one_winner(self):
        params = connection.get_connection_params()
        inserted = threading.Event()
        attempting = threading.Event()
        allow_commit = threading.Event()

        def insert_first():
            conn = connection.Database.connect(**params)
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO auth_user
                            (password, last_login, is_superuser, username, first_name, last_name,
                             email, is_staff, is_active, date_joined)
                        VALUES ('!', NULL, FALSE, %s, '', '', %s, FALSE, FALSE, CURRENT_TIMESTAMP)
                        """,
                        ["ConcurrentＮＦＫＣ", "concurrent-one@example.com"],
                    )
                inserted.set()
                allow_commit.wait(timeout=10)
                conn.commit()
                return "committed"
            finally:
                conn.close()

        def insert_second():
            inserted.wait(timeout=10)
            conn = connection.Database.connect(**params)
            try:
                attempting.set()
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO auth_user
                            (password, last_login, is_superuser, username, first_name, last_name,
                             email, is_staff, is_active, date_joined)
                        VALUES ('!', NULL, FALSE, %s, '', '', %s, FALSE, FALSE, CURRENT_TIMESTAMP)
                        """,
                        ["ConcurrentNFKC", "concurrent-two@example.com"],
                    )
                conn.commit()
                return "committed"
            except Exception as exc:  # psycopg v2/v3 expose different concrete classes
                conn.rollback()
                return type(exc).__name__
            finally:
                conn.close()

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(insert_first)
                second = pool.submit(insert_second)
                self.assertTrue(inserted.wait(timeout=10))
                self.assertTrue(attempting.wait(timeout=10))
                allow_commit.set()
                results = (first.result(timeout=10), second.result(timeout=10))
            self.assertEqual(results[0], "committed")
            self.assertNotEqual(results[1], "committed")
        finally:
            cleanup = connection.Database.connect(**params)
            try:
                with cleanup.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM auth_user WHERE username IN (%s, %s)",
                        ["ConcurrentＮＦＫＣ", "ConcurrentNFKC"],
                    )
                cleanup.commit()
            finally:
                cleanup.close()
