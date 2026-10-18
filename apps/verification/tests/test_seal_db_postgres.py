"""``DocumentSeal`` DB qoruyucuları: append-only trigger, birdəfəlik ləğv, CHECK-lər və RLS (PostgreSQL)."""

from __future__ import annotations

from django.db import DatabaseError, IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

import pytest

from apps.verification.models import DocType, DocumentSeal
from core.rls import bypass_rls

from .world import User, build_world

pytestmark = pytest.mark.postgres

RLS_ROLE = "rls_app_role"
HEX = "a" * 64


def _seal(org, user, code, **extra):
    fields = {
        "organization": org,
        "code": code,
        "doc_type": DocType.TRANSCRIPT,
        "subject_user": user,
        "title": "Akademik transkript",
        "issued_at": timezone.now(),
        "payload": {"holder": "Elvin Q."},
        "payload_sha256": HEX,
        "file_sha256": HEX,
    }
    fields.update(extra)
    with bypass_rls(), transaction.atomic():  # SAVEPOINT bypass-ın İÇİNDƏ: xəta bypass bərpasını zəhərləməsin
        return DocumentSeal.objects.create(**fields)


def _tenant_query(org_id, sql, params=()):
    """``rls_app_role`` (NOBYPASSRLS) kimi, verilən tenant kontekstində SQL (superuser RLS-i keçir)."""
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
        cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(org_id or "")])
        cursor.execute(f"SET LOCAL ROLE {RLS_ROLE}")
        cursor.execute(sql, list(params))
        rows = cursor.fetchall() if cursor.description else []
        cursor.execute("RESET ROLE")
        return rows


class SealGuardTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("qkudb")

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL tələb olunur")

    def _raw(self, sql, params):
        with bypass_rls():
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, params)

    def test_delete_is_blocked(self):
        seal = _seal(self.w["org"], self.w["student"], "QKU-AAAA-AAAA-AAAA-AAA1")
        with self.assertRaises(DatabaseError):
            self._raw("DELETE FROM verification_documentseal WHERE id = %s", [seal.pk])

    def test_content_update_is_blocked(self):
        seal = _seal(self.w["org"], self.w["student"], "QKU-AAAA-AAAA-AAAA-AAA2")
        for column, value in (("payload_sha256", "b" * 64), ("code", "QKU-BBBB-BBBB-BBBB-BBBB"), ("title", "Saxta")):
            with self.subTest(column=column), self.assertRaises(DatabaseError):
                self._raw(f"UPDATE verification_documentseal SET {column} = %s WHERE id = %s", [value, seal.pk])

    def test_one_time_revocation_is_allowed_then_frozen(self):
        seal = _seal(self.w["org"], self.w["student"], "QKU-AAAA-AAAA-AAAA-AAA3")
        self._raw(
            "UPDATE verification_documentseal SET revoked_at = now(), revoked_by_id = %s, revoke_reason = %s "
            "WHERE id = %s",
            [self.w["office"].pk, "Səhv məlumatla verilib, yenisi verildi.", seal.pk],
        )
        with bypass_rls():
            seal.refresh_from_db()
        self.assertIsNotNone(seal.revoked_at)
        with self.assertRaises(DatabaseError):  # ikinci ləğv / səbəbi dəyişmək olmaz
            self._raw(
                "UPDATE verification_documentseal SET revoke_reason = %s WHERE id = %s", ["Başqa səbəb yazdım", seal.pk]
            )
        with self.assertRaises(DatabaseError):  # «ləğvi geri al» olmaz
            self._raw(
                "UPDATE verification_documentseal SET revoked_at = NULL, revoke_reason = '' WHERE id = %s", [seal.pk]
            )

    def test_revocation_cannot_smuggle_other_changes_or_skip_reason(self):
        seal = _seal(self.w["org"], self.w["student"], "QKU-AAAA-AAAA-AAAA-AAA4")
        with self.assertRaises(DatabaseError):
            self._raw(
                "UPDATE verification_documentseal SET revoked_at = now(), revoke_reason = %s, title = 'X' WHERE id = %s",
                ["Kifayət qədər uzun səbəb mətni", seal.pk],
            )
        with self.assertRaises(DatabaseError):
            self._raw(
                "UPDATE verification_documentseal SET revoked_at = now(), revoke_reason = 'qısa' WHERE id = %s",
                [seal.pk],
            )

    def test_check_constraints(self):
        with self.assertRaises(IntegrityError):
            _seal(self.w["org"], self.w["student"], "QKU-AAAA-AAAA-AAAA-AAA5", payload_sha256="not-a-hash")
        with self.assertRaises(IntegrityError):
            _seal(self.w["org"], self.w["student"], "QKU-AAAA-AAAA-AAAA-AAA6", revoked_at=timezone.now())

    def test_code_is_unique(self):
        _seal(self.w["org"], self.w["student"], "QKU-AAAA-AAAA-AAAA-AAA7")
        with self.assertRaises(IntegrityError):
            _seal(self.w["other"], None, "QKU-AAAA-AAAA-AAAA-AAA7")

    def test_account_deletion_nulls_user_links_and_keeps_the_seal(self):
        doomed = User.objects.create_user("qkudb_doomed", "qkudb_doomed@qku.edu.az", "x")
        seal = _seal(self.w["org"], doomed, "QKU-AAAA-AAAA-AAAA-AAA8", issued_by=doomed)
        with bypass_rls():
            doomed.delete()
            seal.refresh_from_db()
        self.assertIsNone(seal.subject_user_id)
        self.assertIsNone(seal.issued_by_id)
        self.assertEqual(seal.payload["holder"], "Elvin Q.")


class SealRlsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("qkurls")
        cls.mine = _seal(cls.w["org"], cls.w["student"], "QKU-CCCC-CCCC-CCCC-CCC1")
        cls.theirs = _seal(cls.w["other"], None, "QKU-CCCC-CCCC-CCCC-CCC2")

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL tələb olunur")

    def test_policy_is_forced(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'verification_documentseal'"
            )
            self.assertEqual(cursor.fetchone(), (True, True))

    def test_tenant_sees_only_its_own_seals(self):
        rows = _tenant_query(self.w["org"].pk, "SELECT code FROM verification_documentseal ORDER BY code")
        self.assertEqual([r[0] for r in rows], [self.mine.code])

    def test_no_tenant_context_sees_nothing(self):
        self.assertEqual(_tenant_query("", "SELECT code FROM verification_documentseal"), [])

    def test_cross_tenant_insert_is_rejected(self):
        with self.assertRaises(DatabaseError):
            _tenant_query(
                self.w["org"].pk,
                "INSERT INTO verification_documentseal (id, organization_id, code, doc_type, title, issued_at, "
                "scope_path, language, payload, payload_sha256, file_sha256, revoke_reason) VALUES "
                "(gen_random_uuid(), %s, 'QKU-CCCC-CCCC-CCCC-CCC3', 'transcript', 't', now(), '', '', '{}'::jsonb, "
                "%s, '', '')",
                [self.w["other"].pk, HEX],
            )
