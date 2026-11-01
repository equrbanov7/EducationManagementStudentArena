"""Real PG: closed Source58 authority, insert-only QB, credits, history and guarded undo."""

import copy
import datetime
import json
import uuid
from unittest.mock import patch

from django.apps import apps
from django.db import transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.legacy_import.models import LegacyEntityMap
from apps.legacy_import.services import reviewed_source58 as service
from apps.legacy_import.services import reviewed_source58_guards as guards
from apps.legacy_import.services import reviewed_source58_source as source
from apps.legacy_import.services.ledger import create_run, start_run
from apps.legacy_import.services.reviewed_content_contract import ContentError
from apps.legacy_import.services.reviewed_content_state import digest
from apps.legacy_import.services.reviewed_source58_undo import undo
from apps.registrar.models import Curriculum, Lesson, LessonMark, StudentAcademicRecord
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.public import fixed_source58_source_scope
from apps.workload.services.scoped_snapshot import source58_evidence_spec as fixed
from apps.workload.services.scoped_snapshot.history_scope import CompiledHistoryScope
from apps.workload.tests.test_source58_evidence import Source58Fixture
from core.rls import apply_rls_request_context, journal_unlock, reset_rls_context


class CompiledSource58Tests(SimpleTestCase):
    def test_public_compiled_scope_is_exact_and_cannot_be_mutated_by_caller(self):
        scope = fixed_source58_source_scope()
        self.assertEqual((len(scope["cases"]), len(scope["slots"]), len(scope["offerings"])), (58, 9, 6))
        self.assertEqual(len({c["enrollment_id"] for c in scope["cases"].values()}), 44)
        scope["cases"].clear()
        self.assertEqual(len(fixed_source58_source_scope()["cases"]), 58)
        from apps.workload import public

        self.assertIn("fixed_source58_recovery_evidence", public.__all__)
        self.assertIn("fixed_source58_source_scope", public.__all__)


class Source58WriterTests(Source58Fixture, TestCase):
    def test_compiler_proven_empty_protected_query_has_exact_empty_digest(self):
        import hashlib

        self.assertEqual(
            guards.fingerprint(Lesson.objects.filter(pk__in=[])),
            {"count": 0, "sha256": hashlib.sha256(b"").hexdigest()},
        )

    def setUp(self):
        self.make_fixture()
        self.pin = {
            **fixed.OFFERINGS[str(self.offering.pk)],
            "source_teacher": 126,
            "source_subject": 1002,
            "source_groups": ["770"],
            "source_uniqid": "gxtZns0tjC",
        }
        self.patches.enter_context(patch.object(fixed, "OFFERINGS", {str(self.offering.pk): self.pin}))
        self.task = TeachingTask.objects.create(
            organization=self.org, chair=self.stack["chair"], academic_year="2026/2027", status="amended"
        )
        self.row = TeachingTaskRow.objects.create(
            organization=self.org,
            task=self.task,
            subject=self.offering.subject,
            period=self.offering.period,
            seminar_plan=30,
            seminar_total=30,
            total_hours=30,
            row_kind="teaching",
        )
        self.row.groups.add(self.offering.group)
        TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=self.teacher, activity="seminar", hours=30
        )
        curriculum = Curriculum.objects.create(
            organization=self.org, program=self.stack["program"], admission_year=2024
        )
        StudentAcademicRecord.objects.create(
            organization=self.org,
            student=self.student,
            program=self.stack["program"],
            curriculum=curriculum,
            admission_year=2024,
            group=self.offering.group,
        )
        run = create_run(
            organization=self.org,
            actor=self.actor,
            authorize=lambda **kw: True,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            source_row_count=4,
            schema_version="test",
            transform_version="test",
            mode="rehearsal",
        )
        run = start_run(run_id=run.pk, actor=self.actor, authorize=lambda **kw: True)
        keys = {}
        for entity, legacy, label, target in [
            ("worker", 126, "auth.user", self.teacher.pk),
            ("student", 9571, "auth.user", self.student.pk),
            ("lesson_subject", 1002, "registrar.subject", self.offering.subject_id),
            ("group_unit", 770, "organizations.orgunit", self.offering.group_id),
        ]:
            LegacyEntityMap.objects.create(
                organization=self.org,
                source_system="myedu_mariadb",
                entity_type=entity,
                legacy_pk=str(legacy),
                target_model_label=label,
                target_pk=str(target),
                state="migrated",
                source_row_hash="b" * 64,
                transform_version="test",
                created_run=run,
            )
            keys.setdefault(entity, []).append(str(legacy))
        keys.update(course_offering=["gxtZns0tjC:770"], journal_enrollment=["gxtZns0tjC:9571"])
        self.patches.enter_context(
            patch.object(
                fixed,
                "HISTORY_SCOPE",
                CompiledHistoryScope(
                    "source58_history", "source58_unregistered_undo", json.dumps({5447859: self.case}), json.dumps(keys)
                ),
            )
        )
        self.data = dict(
            organization_id=str(self.org.pk),
            points=[dict(id=5447859)],
            students=[dict(id=9571, group_id=770)],
            point_allowlist=[
                dict(
                    id=5447859,
                    target_offering_id=str(self.offering.pk),
                    target_enrollment_id=str(self.enrollment.pk),
                    current_student_id=self.student.pk,
                    status="absent",
                    score=None,
                )
            ],
            lesson_metadata=[
                dict(
                    target_offering_id=str(self.offering.pk),
                    date=self.case["date"],
                    start_time=self.case["start_time"],
                    kind="seminar",
                    hours=2,
                    topic="Source58 exact original topic",
                    instructor_id=None,
                    created_by_id=None,
                    end_time=None,
                    explicit_source_calendar_rows=[385784],
                )
            ],
        )
        self.patches.enter_context(patch.object(source, "PAYLOAD_DIGEST", digest(self.data)))
        self.patches.enter_context(patch.object(service.timezone, "localdate", return_value=datetime.date(2026, 11, 1)))
        self.context()
        self.addCleanup(reset_rls_context)

    def context(self, **changes):
        apply_rls_request_context(
            user_id=self.actor.pk,
            org_id=changes.get("org", self.org.pk),
            bypass=changes.get("bypass", False),
            local=True,
        )

    def run_service(self, **kwargs):
        return service.execute(
            data=kwargs.pop("data", self.data),
            source_sha256=kwargs.pop("source_sha256", fixed.SOURCE_SHA256),
            user=self.actor,
            organization=self.org,
            **kwargs,
        )

    def apply_source(self):
        return self.run_service(apply=True, expected_baseline=self.run_service()["baseline"])

    def undo_source(self, applied, **kwargs):
        return undo(
            data=self.data,
            source_sha256=fixed.SOURCE_SHA256,
            user=self.actor,
            organization=self.org,
            batch=applied["batch"],
            receipt_sha256=kwargs.pop("receipt_sha256", applied["receipt_sha256"]),
            **kwargs,
        )

    def test_insert_only_preserves_zero_ie_excused_authors_then_repeat_and_canonical_undo(self):
        zero = self.make_mark(self.enrollment, hours=2, status="present", score=0, date="2026-09-02")
        ie = self.make_mark(self.enrollment, hours=2, status="present", date="2026-09-03")
        excused = self.make_mark(self.enrollment, hours=2, status="excused", date="2026-09-04")
        old = guards.fingerprint(LessonMark.objects.filter(pk__in=[zero.pk, ie.pk, excused.pk, self.mark.pk]))
        dry = self.run_service()
        self.assertEqual((dry["missing_marks"], dry["missing_lessons"]), (1, 1))
        applied = self.apply_source()
        self.assertEqual((applied["created_marks"], applied["created_lessons"]), (1, 1))
        self.assertEqual(old, guards.fingerprint(LessonMark.objects.exclude(lesson_id=self.source_lesson)))
        created = LessonMark.objects.get(lesson_id=self.source_lesson)
        self.assertEqual((created.status, created.score, created.entered_by_id), ("absent", None, None))
        self.assertEqual(Lesson.objects.get(pk=self.source_lesson).topic, self.data["lesson_metadata"][0]["topic"])
        self.assertEqual(self.run_service()["already_done"], 1)
        undo_dry = self.undo_source(applied)
        undone = self.undo_source(applied, apply=True, expected_baseline=undo_dry["baseline"])
        self.assertEqual((undone["deleted_marks"], undone["deleted_lessons"]), (1, 1))
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 2)  # canonical before, never stale99
        self.assertEqual(self.undo_source(applied)["already_undone"], 1)
        self.assertEqual(old, guards.fingerprint(LessonMark.objects.all()))

    def test_credit_clipping_and_stale_cache_reconciliation_are_separate(self):
        prior = self.make_mark(self.enrollment, hours=2, date="2026-09-05")
        self.credit(self.enrollment, 3)
        with journal_unlock():
            LessonMark.objects.filter(pk=prior.pk).update(status="present")
        dry = self.run_service()
        self.assertEqual((dry["source_effect"], dry["cache_reconciliation"]), (1, -99))
        before = guards.fingerprint(apps.get_model("registrar.AbsenceCredit").objects.all())
        applied = self.apply_source()
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 1)
        self.assertEqual(before, guards.fingerprint(apps.get_model("registrar.AbsenceCredit").objects.all()))
        preview = self.undo_source(applied)
        self.undo_source(applied, apply=True, expected_baseline=preview["baseline"])
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 0)

    def test_direct_predecessor_credit_ignores_stale_cache_and_grandparent(self):
        parent = self.history_enrollment("parent", successor=self.enrollment)
        grandparent = self.history_enrollment("grandparent", successor=parent)
        self.make_mark(parent, hours=6)
        self.make_mark(grandparent, hours=10)
        self.credit(parent, 4)
        self.credit(self.enrollment, 3)
        self.assertEqual(self.run_service()["source_effect"], 2)
        self.apply_source()
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 3)  # own2 + new2 + clipped parent2 - target3

    def test_credit_reversal_is_preserved_and_only_active_root_is_subtracted(self):
        root = self.credit(self.enrollment, 2)
        self.credit(self.enrollment, 2, reverses=root)
        self.credit(self.enrollment, 1)
        before = guards.fingerprint(apps.get_model("registrar.AbsenceCredit").objects.all())
        self.apply_source()
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 3)
        self.assertEqual(before, guards.fingerprint(apps.get_model("registrar.AbsenceCredit").objects.all()))

    def test_later_credit_reversal_and_created_attribution_drift_hold_undo(self):
        root = self.credit(self.enrollment, 1)
        applied = self.apply_source()
        self.credit(self.enrollment, 1, reverses=root)
        with self.assertRaisesRegex(ContentError, "undo_content_credit_or_history_drift"):
            self.undo_source(applied)
        with journal_unlock():
            LessonMark.objects.filter(lesson_id=self.source_lesson).update(entered_by=self.teacher)
        with self.assertRaisesRegex(ContentError, "created_mark_changed"):
            self.run_service()

    def test_extra_intent_cannot_hide_behind_own_receipt_resource(self):
        applied = self.apply_source()
        audit = apps.get_model("audit.AuditLog").objects.get(
            resource_type=source.RESOURCE, resource_id=applied["batch"]
        )
        value = dict(audit.new_values, unknown_clear_intent=True)
        apps.get_model("audit.AuditLog").objects.create(
            organization=self.org,
            user=self.actor,
            action="create",
            resource_type=source.RESOURCE,
            resource_id=applied["batch"] + "-extra",
            reason=source.APPLY_REASON,
            new_values=value,
        )
        with self.assertRaisesRegex(ContentError, "closed_apply_receipt_required"):
            self.run_service()

    def test_current_any_slot_or_kind_claim_is_never_overwritten(self):
        for status, score in [("present", 0), ("excused", None), ("absent", None)]:
            with self.subTest(status=status), transaction.atomic():
                mark = self.make_mark(self.enrollment, hours=2, date=self.case["date"], status=status, score=score)
                before = guards.fingerprint(LessonMark.objects.all())
                with self.assertRaisesRegex(ContentError, "canonical_claim"):
                    self.run_service()
                mark.refresh_from_db()
                self.assertEqual((mark.status, mark.score), (status, score))
                self.assertEqual(before, guards.fingerprint(LessonMark.objects.all()))
                transaction.set_rollback(True)

    def test_formal_excuse_covering_source_date_holds(self):
        apps.get_model("registrar.LegacyExcuseDocument").objects.create(
            organization=self.org,
            student=self.student,
            source_system="myedu_mariadb",
            source_table="allowed_qb",
            source_pk=123,
            source_snapshot_sha256="a" * 64,
            source_row_hash="b" * 64,
            materialization_digest="c" * 64,
            transform_version="test",
            mapping_status="linked",
            starts_on="2026-10-01",
            ends_on="2026-10-05",
            note="PRIVATE_FORMAL_REASON",
        )
        with self.assertRaisesRegex(ContentError, "formal_excuse_covers"):
            self.run_service()
        self.assertFalse(Lesson.objects.filter(pk=self.source_lesson).exists())

    def test_unknown_masked_grade_history_and_explicit_counter_override_hold(self):
        for code, resource, changes in [
            ("registrar.grade.full-edit", str(uuid.uuid4()), None),
            ("registrar.manual_counter_override", str(self.enrollment.pk), []),
        ]:
            with self.subTest(code=code), transaction.atomic():
                apps.get_model("audit.AuditLog").objects.create(
                    organization=self.org,
                    user=self.actor,
                    action="update",
                    resource_type=code,
                    resource_id=resource,
                    changes=changes,
                    new_values={"private": "MASKED_UNKNOWN"},
                )
                with self.assertRaisesRegex(ContentError, "history|override"):
                    self.run_service()
                transaction.set_rollback(True)

    def test_old_uuid_clear_with_exact_date_kind_label_holds(self):
        label = str(Lesson(date=self.case["date"], kind="seminar").get_kind_display())
        apps.get_model("audit.AuditLog").objects.create(
            organization=self.org,
            user=self.actor,
            action="update",
            resource_type="registrar.grade.mark",
            resource_id=str(self.offering.pk),
            changes=[
                dict(
                    lesson_id=str(uuid.uuid4()),
                    enrollment_id=str(self.enrollment.pk),
                    student=self.student.get_full_name(),
                    item=self.case["date"] + " · " + label,
                    old="qb",
                    new="",
                )
            ],
        )
        with self.assertRaisesRegex(ContentError, "contrary|clear"):
            self.run_service()

    def test_credit_grant_or_created_row_drift_blocks_undo(self):
        applied = self.apply_source()
        self.credit(self.enrollment, 1)
        with self.assertRaisesRegex(ContentError, "undo_content_credit_or_history_drift"):
            self.undo_source(applied)
        self.assertTrue(Lesson.objects.filter(pk=self.source_lesson).exists())

    def test_existing_raw_grade_drift_blocks_undo_and_wrong_receipt_sha_holds(self):
        applied = self.apply_source()
        with journal_unlock():
            LessonMark.objects.filter(pk=self.mark.pk).update(status="present", score=0)
        with self.assertRaisesRegex(ContentError, "undo_content_credit_or_history_drift"):
            self.undo_source(applied)
        with self.assertRaisesRegex(ContentError, "receipt_full_row_changed"):
            self.undo_source(applied, receipt_sha256="0" * 64)

    def test_atomic_failure_rolls_back_inserted_raw_and_canonical_cache(self):
        before = guards.fingerprint(LessonMark.objects.all())
        dry = self.run_service()
        with patch.object(service, "verify_created_rows", side_effect=RuntimeError("injected")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.run_service(apply=True, expected_baseline=dry["baseline"])
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 99)
        self.assertFalse(Lesson.objects.filter(pk=self.source_lesson).exists())
        self.assertEqual(before, guards.fingerprint(LessonMark.objects.all()))

    def test_fresh_baseline_roster_and_scope_fail_closed(self):
        dry = self.run_service()
        self.credit(self.enrollment, 1)
        with self.assertRaisesRegex(ContentError, "baseline_changed"):
            self.run_service(apply=True, expected_baseline=dry["baseline"])
        with self.assertRaisesRegex(ContentError, "fresh_baseline_required"):
            self.run_service(apply=True)
        with self.assertRaisesRegex(ContentError, "boolean_apply_required"):
            self.run_service(apply="false")
        with self.assertRaisesRegex(ContentError, "sealed_source_package"):
            self.run_service(source_sha256="0" * 64)
        altered = copy.deepcopy(self.data)
        altered["points"] = []
        with self.assertRaisesRegex(ContentError, "sealed_source_package"):
            self.run_service(data=altered)

    def test_current_roster_profile_and_home_group_authority_are_mandatory(self):
        queries = [
            (apps.get_model("registrar.Enrollment").objects.filter(pk=self.enrollment.pk), dict(status="dropped")),
            (
                apps.get_model("accounts.UserProfile").objects.filter(user_id=self.teacher.pk),
                dict(blocked_at=timezone.now()),
            ),
            (StudentAcademicRecord.objects.filter(student=self.student), dict(is_active=False)),
        ]
        for query, change in queries:
            with self.subTest(change=list(change)), transaction.atomic():
                query.update(**change)
                with self.assertRaises(ContentError):
                    self.run_service()
                self.assertFalse(Lesson.objects.filter(pk=self.source_lesson).exists())
                transaction.set_rollback(True)

    def test_both_rls_modes_require_same_tenant_no_bypass(self):
        for scoped in (False, True):
            with override_settings(RLS_TRANSACTION_SCOPED=scoped):
                self.context()
                self.assertEqual(self.run_service()["missing_marks"], 1)
        for changes in ({"bypass": True}, {"org": uuid.uuid4()}):
            self.context(**changes)
            with self.assertRaisesRegex(ContentError, "evidence_unavailable"):
                self.run_service()
        self.context()

    def test_existing_released_plan_policy_accepts_real_statuses_and_holds_drafts(self):
        for status, submitted, released in [
            ("approved", None, True),
            ("distributed", None, True),
            ("amended", None, True),
            ("distributing", timezone.now(), True),
            ("distributing", None, False),
            ("draft", None, False),
            ("cancelled", None, False),
        ]:
            with self.subTest(status=status, submitted=bool(submitted)), transaction.atomic():
                TeachingTask.objects.filter(pk=self.task.pk).update(status=status, submitted_at=submitted)
                if released:
                    self.assertEqual(self.run_service()["missing_marks"], 1)
                else:
                    with self.assertRaisesRegex(ContentError, "kind_workload_authority"):
                        self.run_service()
                transaction.set_rollback(True)
