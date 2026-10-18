"""«Fənləri birləşdir» — PostgreSQL qoruyucuları (``pytest -m postgres``, 2026-10-19).

* canlı ``registrar_guard_conditional_parent_identity`` funksiyası ``audit.0004`` icazəsini SAXLAYIR
  (gələcək registrar miqrasiyası funksiyanı icazəsiz yenidən yazsa — bu test düşür);
* icazə birləşmədən kənarda və başqa hədəfə İŞLƏMİR;
* sübutlu açılış birləşmədə qiymətləri ilə köçür;
* geri qaytarmanın dry-run-ı gecikdirilmiş ``syllabus_reuse_same_org_subject`` FK-nı da görür;
* köçürmədə DB xətası ilk (əsl) xəta kimi çıxır — təmizləmə SQL-i onu «aborted transaction» ilə örtmür.
"""

from __future__ import annotations

from unittest import mock

from django.apps import apps as django_apps
from django.db import DatabaseError, DataError, connection, transaction

import pytest

from apps.registrar import subject_merge, subject_merge_apply, subject_merge_undo
from apps.registrar.models import CourseOffering, Subject
from core.rls import bypass_rls

from .subject_merge_fixture import REASON, SubjectMergeBase

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL triggers are required."),
]


class SubjectMergePostgresGuardTest(SubjectMergeBase):
    def _merge(self):
        with bypass_rls():
            payload = subject_merge.preview(self.org, str(self.target.pk), [str(self.source.pk)])
            return subject_merge_apply.apply(
                organization=self.org,
                actor=self.office,
                target_ref=str(self.target.pk),
                source_refs=[str(self.source.pk)],
                reason=REASON,
                expected_digest=payload["digest"],
            )

    def test_live_guard_function_keeps_the_merge_allowance(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_get_functiondef('public.registrar_guard_conditional_parent_identity()'::regprocedure)"
            )
            body = cursor.fetchone()[0]
        for marker in (
            "app.registrar_subject_merge_txid",
            "app.registrar_subject_merge_from",
            "app.registrar_subject_merge_to",
            "pg_current_xact_id()",
            "registrar parent identity has dependent evidence",
        ):
            self.assertIn(marker, body, marker)

    def test_guard_blocks_subject_change_outside_a_merge(self):
        offering = self.offering(self.source, self.group1)
        self.enroll(offering)
        with bypass_rls(), self.assertRaises(DatabaseError), transaction.atomic():
            CourseOffering.objects.filter(pk=offering.pk).update(subject=self.target)
        with bypass_rls(), self.assertRaises(DatabaseError), transaction.atomic():
            other = Subject.objects.create(organization=self.org, code="QA-SM-X", name="X")
            subject_merge_apply.allow_offering_subject_change([self.source.pk], other.pk)
            CourseOffering.objects.filter(pk=offering.pk).update(subject=self.target)

    def test_offering_with_evidence_moves_in_a_merge(self):
        offering = self.offering(self.source, self.group1)
        self.enroll(offering, grade="35")
        self._merge()
        with bypass_rls():
            self.assertEqual(CourseOffering.objects.get(pk=offering.pk).subject_id, self.target.pk)

    def test_undo_dry_run_surfaces_deferred_syllabus_reuse_constraint(self):
        moved = self.syllabus(self.source, period=self.period, author=self.teacher)
        result = self._merge()
        Syllabus = django_apps.get_model("syllabus", "Syllabus")
        with bypass_rls():
            # birləşmədən sonra hədəfdə YENİ sillabus köçən sillabusdan təkrar istifadə edir — geri qaytarma
            # `moved`-i mənbəyə aparsa kompozit FK (reused_from, org, subject) pozulur
            Syllabus.objects.filter(pk=self.syllabus(self.target, author=self.teacher).pk).update(reused_from=moved)
            report = subject_merge_undo.undo(audit_id=result["audit_id"])
        self.assertFalse(report["applied"])
        self.assertTrue(any("DB qaydası" in issue for issue in report["issues"]), report["issues"])
        self.assertTrue(Subject.objects.get(pk=self.source.pk).is_archived)

    def test_repoint_error_is_not_masked_by_cleanup(self):
        self.offering(self.source, self.group1)

        def broken(*_args, **_kwargs):
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 / 0")

        with bypass_rls():
            payload = subject_merge.preview(self.org, str(self.target.pk), [str(self.source.pk)])
            with mock.patch.object(subject_merge_apply, "repoint_rows", broken), self.assertRaises(DataError):
                subject_merge_apply.apply(
                    organization=self.org,
                    actor=self.office,
                    target_ref=str(self.target.pk),
                    source_refs=[str(self.source.pk)],
                    reason=REASON,
                    expected_digest=payload["digest"],
                )
            self.assertFalse(Subject.objects.get(pk=self.source.pk).is_archived)

    def test_apply_locks_offerings_before_collecting(self):
        from django.test.utils import CaptureQueriesContext

        self.offering(self.source, self.group1)
        with bypass_rls():
            payload = subject_merge.preview(self.org, str(self.target.pk), [str(self.source.pk)])
            with CaptureQueriesContext(connection) as captured:
                subject_merge_apply.apply(
                    organization=self.org,
                    actor=self.office,
                    target_ref=str(self.target.pk),
                    source_refs=[str(self.source.pk)],
                    reason=REASON,
                    expected_digest=payload["digest"],
                )
        sqls = [query["sql"] for query in captured.captured_queries]
        lock = next(
            index for index, sql in enumerate(sqls) if "registrar_courseoffering" in sql and "FOR UPDATE" in sql
        )
        first_enrollment_read = next(index for index, sql in enumerate(sqls) if "registrar_enrollment" in sql)
        self.assertLess(lock, first_enrollment_read)
