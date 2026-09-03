"""PostgreSQL negative matrix for the append-only correction ledger."""

import datetime
import os
from contextlib import contextmanager

from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext

import pytest

from apps.organizations.models import Membership, Organization
from apps.registrar import corrections, gradebook, journal_extras
from apps.registrar.models import (
    AttendanceStatus,
    ComponentScoreCorrection,
    CorrectionField,
    CorrectionReason,
    CorrectionReversal,
    CourseWorkCorrection,
    JournalCorrection,
    LessonCorrection,
    LessonKind,
    LessonMark,
    SelfWorkCorrection,
)
from apps.registrar.tests.test_corrections_bridge import _BaseJournalSetup, _pdf
from core.constants import OrganizationType
from core.rls import bypass_rls, journal_unlock

User = get_user_model()

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL triggers are required."),
]


class CorrectionReversalPostgresTests(_BaseJournalSetup):
    def _apply_grade(self, mark, score, note="pg ledger"):
        return corrections.apply_correction(
            mark=mark,
            field=CorrectionField.SCORE,
            new_score=score,
            reason=CorrectionReason.TECHNICAL,
            note=note,
            document=_pdf(),
            by_user=self.admin,
        )

    # PostgreSQL rolları KLASTER səviyyəsindədir (DB-yə bağlı deyil): pytest-xdist
    # worker-ləri paralel işləyəndə eyni adlı rol yarat/sil toqquşur (başqa
    # worker-in DB-sindəki GRANT DROP ROLE-u bloklayır). Ad worker-ə görə ayrılır.
    _PROBE_ROLE = "ems_guard_probe" + os.environ.get("PYTEST_XDIST_WORKER", "")
    # TRUNCATE ... CASCADE needs the TRUNCATE privilege on every table the
    # cascade reaches; the reversal ledger references all evidence tables.
    _PROBE_TABLES = (
        "registrar_journalcorrection",
        "registrar_lessoncorrection",
        "registrar_selfworkcorrection",
        "registrar_courseworkcorrection",
        "registrar_componentscorecorrection",
        "registrar_correctionreversal",
    )

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

    def _rejects(self, statement, params):
        if statement.lstrip().upper().startswith("TRUNCATE"):
            # Django TestCase wraps the test in a transaction.  Flush deferred
            # FK events first so PostgreSQL reaches our BEFORE TRUNCATE guard.
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            # The guard waves superusers through (they could DROP the trigger
            # anyway) by checking session_user, which SET ROLE does not change.
            # Probe it under a guaranteed non-superuser role instead.
            with self._nonsuper_probe_role():
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        with connection.cursor() as cursor:
                            cursor.execute(f"SET SESSION AUTHORIZATION {self._PROBE_ROLE}")
                            cursor.execute(statement, params)
            return
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(statement, params)

    def test_raw_update_delete_and_truncate_cannot_erase_history(self):
        _lesson, mark = self._seminar_mark(20, 3)
        with bypass_rls():
            correction = self._apply_grade(mark, 8)
            topic = journal_extras.add_selfwork_topic(offering=self.offering, title="PG evidence")
            component = list(journal_extras.ensure_kollokviums(self.offering))[0]
            lesson_correction = LessonCorrection.objects.create(
                organization=self.org,
                lesson=mark.lesson,
                old_date=mark.lesson.date,
                new_date=mark.lesson.date,
                reason=CorrectionReason.TECHNICAL,
                note="lesson evidence",
                document="journal_lesson_corrections/evidence.pdf",
                corrected_by=self.admin,
                corrected_by_name=self.admin.username,
            )
            selfwork_correction = SelfWorkCorrection.objects.create(
                organization=self.org,
                topic=topic,
                enrollment=self.enrollment,
                old_done=False,
                new_done=True,
                reason=CorrectionReason.TECHNICAL,
                note="self-work evidence",
                document="journal_selfwork_corrections/evidence.pdf",
                corrected_by=self.admin,
                corrected_by_name=self.admin.username,
            )
            coursework_correction = CourseWorkCorrection.objects.create(
                organization=self.org,
                enrollment=self.enrollment,
                old_score=None,
                new_score=7,
                reason=CorrectionReason.TECHNICAL,
                note="course-work evidence",
                document="journal_coursework_corrections/evidence.pdf",
                corrected_by=self.admin,
                corrected_by_name=self.admin.username,
            )
            component_correction = ComponentScoreCorrection.objects.create(
                organization=self.org,
                component=component,
                enrollment=self.enrollment,
                old_score=None,
                new_score=7,
                reason=CorrectionReason.TECHNICAL,
                note="component evidence",
                document="journal_component_corrections/evidence.pdf",
                corrected_by=self.admin,
                corrected_by_name=self.admin.username,
            )

        evidence = [
            ("registrar_journalcorrection", correction),
            ("registrar_lessoncorrection", lesson_correction),
            ("registrar_selfworkcorrection", selfwork_correction),
            ("registrar_courseworkcorrection", coursework_correction),
            ("registrar_componentscorecorrection", component_correction),
        ]
        for table, row in evidence:
            with self.subTest(table=table, operation="update"):
                self._rejects(f"UPDATE {table} SET note = %s WHERE id = %s", ["rewritten", row.pk])
            with self.subTest(table=table, operation="delete"):
                self._rejects(f"DELETE FROM {table} WHERE id = %s", [row.pk])
            with self.subTest(table=table, operation="truncate"):
                self._rejects(f"TRUNCATE TABLE {table} CASCADE", [])

        self._rejects(
            "UPDATE registrar_journalcorrection SET lesson_mark_ref = %s WHERE id = %s",
            [self.enrollment.pk, correction.pk],
        )

        with bypass_rls():
            corrections.revert_last_grade_correction(
                mark=mark,
                by_user=self.admin,
                correction_id=correction.pk,
            )
        reversal = CorrectionReversal.objects.get(journal_correction=correction)
        self._rejects(
            "UPDATE registrar_correctionreversal SET reason_code = %s WHERE id = %s",
            ["rewritten", reversal.pk],
        )
        self._rejects(
            "DELETE FROM registrar_correctionreversal WHERE id = %s",
            [reversal.pk],
        )
        self._rejects("TRUNCATE TABLE registrar_correctionreversal", [])

        self.assertTrue(JournalCorrection.objects.filter(pk=correction.pk).exists())
        self.assertTrue(CorrectionReversal.objects.filter(pk=reversal.pk).exists())

    def test_insert_guard_rejects_cross_tenant_forged_actor_and_two_targets(self):
        _lesson, mark = self._seminar_mark(21, 3)
        with bypass_rls():
            correction = self._apply_grade(mark, 8)
            owner_b = User.objects.create_user("reversal_pg_owner_b", password="pw")
            org_b = Organization.objects.create(
                name="Reversal PG B",
                slug="reversal-pg-b",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner_b,
                status="active",
                is_active=True,
            )
            outsider = User.objects.create_user("reversal_pg_outsider", password="pw")
            inactive = User.objects.create_user("reversal_pg_inactive", password="pw", is_active=False)
            Membership.objects.create(
                organization=self.org,
                user=inactive,
                role=self.org.roles.get(name="member"),
                is_active=True,
            )
            lesson_correction = LessonCorrection.objects.create(
                organization=self.org,
                lesson=mark.lesson,
                old_date=mark.lesson.date,
                new_date=mark.lesson.date,
                reason=CorrectionReason.TECHNICAL,
                note="second typed target",
                document="journal_lesson_corrections/second.pdf",
                corrected_by=self.admin,
                corrected_by_name=self.admin.username,
            )

        cases = [
            {
                "organization": org_b,
                "journal_correction": correction,
                "reverted_by": owner_b,
                "reverted_by_ref": str(owner_b.pk),
            },
            {
                "organization": self.org,
                "journal_correction": correction,
                "reverted_by": self.admin,
                "reverted_by_ref": str(outsider.pk),
            },
            {
                "organization": self.org,
                "journal_correction": correction,
                "reverted_by": inactive,
                "reverted_by_ref": str(inactive.pk),
            },
            {
                "organization": self.org,
                "journal_correction": correction,
                "reverted_by": outsider,
                "reverted_by_ref": str(outsider.pk),
            },
            {
                "organization": self.org,
                "journal_correction": correction,
                "lesson_correction": lesson_correction,
                "reverted_by": self.admin,
                "reverted_by_ref": str(self.admin.pk),
            },
            {
                "organization": self.org,
                "reverted_by": self.admin,
                "reverted_by_ref": str(self.admin.pk),
            },
            {
                "organization": self.org,
                "journal_correction": correction,
                "reverted_by": self.admin,
                "reverted_by_ref": str(self.admin.pk),
                "reason_code": "unknown_reason",
            },
        ]
        for values in cases:
            with self.subTest(values=sorted(values)):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        CorrectionReversal.objects.create(**values)
        self.assertFalse(CorrectionReversal.objects.exists())

    def test_rls_hides_reversal_from_another_tenant(self):
        _lesson, mark = self._seminar_mark(22, 3)
        with bypass_rls():
            correction = self._apply_grade(mark, 8)
            corrections.revert_last_grade_correction(
                mark=mark,
                by_user=self.admin,
                correction_id=correction.pk,
            )
            owner_b = User.objects.create_user("reversal_rls_owner_b", password="pw")
            org_b = Organization.objects.create(
                name="Reversal RLS B",
                slug="reversal-rls-b",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner_b,
                status="active",
                is_active=True,
            )
            _second_lesson, second_mark = self._seminar_mark(23, 4)
            second_correction = self._apply_grade(second_mark, 9, "RLS write check")

        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(org_b.pk)])
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:
            self.assertEqual(CorrectionReversal.objects.count(), 0)
            with self.assertRaises(DatabaseError) as blocked:
                with transaction.atomic():
                    CorrectionReversal.objects.create(
                        organization=self.org,
                        journal_correction=second_correction,
                        reverted_by=self.admin,
                        reverted_by_ref=str(self.admin.pk),
                    )
            self.assertIn("row-level security policy", str(blocked.exception).lower())
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.org.pk)])
            self.assertEqual(CorrectionReversal.objects.count(), 1)
            self.assertFalse(CorrectionReversal.objects.filter(journal_correction=second_correction).exists())
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")

    def test_guard_functions_and_trigger_matrix_are_hardened(self):
        expected = {
            "registrar_assert_correction_reversal_integrity",
            "registrar_guard_correction_evidence_immutable",
            "registrar_guard_correction_no_delete",
            "registrar_guard_correction_reversal_immutable",
            "registrar_guard_correction_reversal_insert",
        }
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT p.proname, p.prosecdef, p.proconfig, "
                "has_function_privilege('rls_app_role', p.oid, 'EXECUTE'), "
                "EXISTS (SELECT 1 FROM aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) acl "
                "WHERE acl.grantee = 0 AND acl.privilege_type = 'EXECUTE') "
                "FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace "
                "AND p.proname = ANY(%s)",
                [list(expected)],
            )
            functions = cursor.fetchall()
            cursor.execute(
                "SELECT tgname, count(*) FROM pg_trigger WHERE NOT tgisinternal "
                "AND tgname = ANY(%s) GROUP BY tgname",
                [
                    [
                        "registrar_correction_evidence_immutable_guard",
                        "registrar_correction_evidence_delete_guard",
                        "registrar_correction_evidence_truncate_guard",
                        "registrar_correction_reversal_insert_guard",
                        "registrar_correction_reversal_immutable_guard",
                    ]
                ],
            )
            trigger_counts = dict(cursor.fetchall())
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE oid = 'public.registrar_correctionreversal'::regclass"
            )
            rls = cursor.fetchone()

        self.assertEqual({row[0] for row in functions}, expected)
        for _name, security_definer, config, restricted_execute, public_execute in functions:
            self.assertTrue(security_definer)
            self.assertIn("search_path=pg_catalog, public", config)
            self.assertFalse(restricted_execute)
            self.assertFalse(public_execute)
        self.assertEqual(trigger_counts["registrar_correction_evidence_immutable_guard"], 5)
        self.assertEqual(trigger_counts["registrar_correction_evidence_delete_guard"], 6)
        self.assertEqual(trigger_counts["registrar_correction_evidence_truncate_guard"], 6)
        self.assertEqual(trigger_counts["registrar_correction_reversal_insert_guard"], 1)
        self.assertEqual(trigger_counts["registrar_correction_reversal_immutable_guard"], 1)
        self.assertEqual(rls, (True, True))

    def test_fabricated_mark_can_return_to_empty_without_losing_locator(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                allow_past=True,
                offering=self.offering,
                date=datetime.date(2024, 10, 23),
                kind=LessonKind.SEMINAR,
            )
            unsaved = LessonMark(
                organization=self.org,
                lesson=lesson,
                enrollment=self.enrollment,
                status=AttendanceStatus.PRESENT,
            )
            correction = corrections.apply_correction(
                mark=unsaved,
                field=CorrectionField.SCORE,
                new_score=8,
                reason=CorrectionReason.TECHNICAL,
                note="fabricated",
                document=_pdf(),
                by_user=self.admin,
                was_empty=True,
            )
            mark_id = correction.lesson_mark_id
            self.assertTrue(
                corrections.revert_last_grade_correction(
                    mark=correction.lesson_mark,
                    by_user=self.admin,
                    correction_id=correction.pk,
                )
            )

        correction.refresh_from_db()
        self.assertIsNone(correction.lesson_mark_id)
        self.assertEqual(correction.lesson_mark_ref, mark_id)
        self.assertEqual(correction.lesson_ref, lesson.pk)
        self.assertEqual(correction.enrollment_ref, self.enrollment.pk)

    def test_apply_refetches_canonical_target_before_snapshot(self):
        _lesson, mark = self._seminar_mark(24, 5)
        stale_mark = LessonMark.objects.get(pk=mark.pk)
        with bypass_rls(), journal_unlock():
            LessonMark.objects.filter(pk=mark.pk).update(score=3)
            correction = self._apply_grade(stale_mark, 8, "canonical refetch")

        self.assertEqual(correction.old_score, 3)
        mark.refresh_from_db()
        self.assertEqual(mark.score, 8)

    def test_exact_id_reversal_locks_evidence_and_targets_are_unique(self):
        _lesson, mark = self._seminar_mark(26, 3)
        with bypass_rls():
            correction = corrections.apply_correction(
                mark=mark,
                field=CorrectionField.SCORE,
                new_score=8,
                reason=CorrectionReason.TECHNICAL,
                note="concurrent reversal",
                document=_pdf(),
                by_user=self.admin,
            )
            with CaptureQueriesContext(connection) as queries:
                self.assertTrue(
                    corrections.revert_last_grade_correction(
                        mark=mark,
                        by_user=self.admin,
                        correction_id=correction.pk,
                    )
                )

        locking_sql = [query["sql"] for query in queries if "FOR UPDATE" in query["sql"].upper()]
        self.assertTrue(any("registrar_journalcorrection" in sql for sql in locking_sql))
        self.assertTrue(any("registrar_lessonmark" in sql for sql in locking_sql))
        expected_targets = {
            "journal_correction_id",
            "lesson_correction_id",
            "selfwork_correction_id",
            "coursework_correction_id",
            "component_correction_id",
        }
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT a.attname FROM pg_index i "
                "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                "WHERE i.indrelid = 'public.registrar_correctionreversal'::regclass "
                "AND i.indisunique AND a.attname = ANY(%s)",
                [list(expected_targets)],
            )
            unique_targets = {row[0] for row in cursor.fetchall()}
        self.assertEqual(unique_targets, expected_targets)
        self.assertEqual(CorrectionReversal.objects.filter(journal_correction=correction).count(), 1)
        mark.refresh_from_db()
        self.assertEqual(mark.score, 3)
