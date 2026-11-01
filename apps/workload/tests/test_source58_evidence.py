"""Real PostgreSQL read-only discovery, privacy, credit/carry and unknown-history contracts."""

import json
import uuid
from contextlib import ExitStack
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from apps.registrar.models import AbsenceCredit, CourseOffering, Enrollment, Lesson, LessonMark
from apps.registrar.public import absence_counter_preview, credit_hours_map, effective_hours
from apps.workload.services.scoped_snapshot import source58_evidence as evidence
from apps.workload.services.scoped_snapshot import source58_evidence_rows as row_tools
from apps.workload.services.scoped_snapshot import source58_evidence_spec as fixed
from apps.workload.services.scoped_snapshot.history_scope import CompiledHistoryScope
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_structure
from core.rls import apply_rls_request_context, journal_unlock, reset_rls_context

User = get_user_model()


class Source58CompiledScopeTests(SimpleTestCase):
    def test_exact_sealed_source_scope_has_58_points_44_enrollments_9_past_slots_6_courses(self):
        self.assertEqual(len(fixed.CASES), 58)
        self.assertEqual(len({c["enrollment_id"] for c in fixed.CASES.values()}), 44)
        self.assertEqual(len(fixed.SLOTS), 9)
        self.assertEqual(len(fixed.OFFERINGS), 6)
        self.assertEqual(sum(c["hours"] for c in fixed.CASES.values()), 116)
        self.assertTrue(all(c["date"] <= "2026-11-01" for c in fixed.CASES.values()))
        self.assertEqual(fixed.HISTORY_SCOPE.cases, fixed.CASES)
        self.assertEqual(fixed.SOURCE_SHA256, "203b48f81ef7a7a85db67e5c375667700ee5f2e9051987474a4c0f91a31e4fa0")
        self.assertIn("gxtZns0tjC:770", fixed.SOURCE_KEYS["course_offering"])
        self.assertNotIn("14025", fixed.SOURCE_KEYS["course_offering"])

    def test_no_external_selector_can_widen_the_collector(self):
        with self.assertRaises(TypeError):
            evidence.collect_source58_evidence(offering_ids=["arbitrary"])

    def test_registrar_public_facade_keeps_canonical_read_only_function_exports(self):
        from apps.registrar import public

        for name, owner in {
            "credit_hours_map": "apps.registrar.absence_credit_read",
            "effective_hours": "apps.registrar.absence_credit_read",
            "carry_over_map": "apps.registrar.guest_merge",
            "absence_counter_preview": "apps.registrar.absence_evidence",
        }.items():
            self.assertIn(name, public.__all__)
            self.assertEqual(getattr(public, name).__module__, owner)


class Source58Fixture:
    def make_fixture(self):
        self.org = make_org("source58-evidence")
        self.actor = self.org.owner
        self.actor.is_superuser = True
        self.actor.save(update_fields=["is_superuser"])
        self.stack = make_structure(self.org, code="S58")
        self.teacher = User.objects.create_user("source58-teacher", password="PRIVATE_PASSWORD_SENTINEL")
        self.student = User.objects.create_user("source58-student", first_name="PRIVATE_STUDENT_NAME")
        activate_member(self.org, self.teacher, "teacher", permissions=TEACHER_PERMS)
        activate_member(self.org, self.student, "student", permissions=["course.view", "grade.view"])
        apps.get_model("accounts.UserProfile").objects.filter(
            user_id__in=[self.actor.pk, self.teacher.pk, self.student.pk]
        ).update(organization=self.org)
        self.offering = CourseOffering.objects.create(
            organization=self.org,
            subject=self.stack["subject"],
            period=self.stack["period"],
            group=self.stack["group"],
            instructor=self.teacher,
            lesson_hours=60,
        )
        self.enrollment = Enrollment.objects.create(
            organization=self.org, offering=self.offering, student=self.student, absence_hours=99
        )
        self.mark = self.make_mark(self.enrollment, hours=2, status="absent", date="2026-09-01")
        self.source_lesson = str(uuid.uuid5(self.org.pk, "source58-fixture-lesson"))
        self.case = {
            "offering_id": str(self.offering.pk),
            "enrollment_id": str(self.enrollment.pk),
            "student_id": self.student.pk,
            "lesson_id": self.source_lesson,
            "date": "2026-10-03",
            "start_time": "15:15:00",
            "kind": "seminar",
            "hours": 2,
            "source_student_id": 9571,
            "source_worker_id": 126,
            "source_subject_id": 1002,
        }
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        pins = {
            "ORG": str(self.org.pk),
            "OFFERINGS": {
                str(self.offering.pk): {
                    "subject_id": str(self.offering.subject_id),
                    "period_id": str(self.offering.period_id),
                    "group_id": str(self.offering.group_id),
                    "instructor_id": self.teacher.pk,
                }
            },
            "SLOTS": [dict(self.case)],
            "CASES": {5447859: dict(self.case)},
            "HISTORY_SCOPE": CompiledHistoryScope(
                "source58_history",
                "source58_unregistered_undo",
                json.dumps({5447859: self.case}),
                json.dumps({"course_offering": ["gxtZns0tjC:770"], "worker": ["126"]}),
            ),
        }
        for name, value in pins.items():
            self.patches.enter_context(patch.object(fixed, name, value))

    def make_mark(self, enrollment, *, hours, status="absent", date="2026-09-01", score=None, kind="seminar"):
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=enrollment.offering,
            date=date,
            start_time="10:10:00",
            kind=kind,
            hours=hours,
            topic="PRIVATE_LESSON_TOPIC",
        )
        return LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=enrollment, status=status, score=score
        )

    def credit(self, enrollment, hours, *, reverses=None):
        before = absence_counter_preview(organization_id=self.org.pk, added_hours_by_enrollment={enrollment.pk: 0})[0][
            "derived_before"
        ]
        return AbsenceCredit.objects.create(
            organization=self.org,
            enrollment=enrollment,
            hours=hours,
            reason="PRIVATE_SIGNED_CREDIT_REASON",
            actor=self.actor,
            request_token=uuid.uuid4(),
            old_absence_hours=before,
            new_absence_hours=max(0, before + hours if reverses else before - hours),
            reverses=reverses,
        )

    def history_enrollment(self, name, *, successor=None, active=True):
        group = apps.get_model("organizations.OrgUnit").objects.create(
            organization=self.org, name=name, slug=name, unit_type="group"
        )
        offering = CourseOffering.objects.create(
            organization=self.org,
            subject=self.offering.subject,
            period=self.offering.period,
            group=group,
            instructor=self.teacher,
            lesson_hours=60,
            is_active=active,
        )
        return Enrollment.objects.create(
            organization=self.org,
            offering=offering,
            student=self.student,
            status="dropped" if successor else "enrolled",
            superseded_by=successor,
            absence_hours=500,
        )

    def collect(self):
        with patch.object(evidence, "require_readonly", return_value=self.actor.pk):
            return evidence.collect_source58_evidence()


class Source58EvidenceTests(Source58Fixture, TestCase):
    def setUp(self):
        self.make_fixture()

    def test_stale_cache_credit_clipping_and_source_effect_are_separate_and_never_written(self):
        changed = self.make_mark(self.enrollment, hours=2, date="2026-09-02")
        self.credit(self.enrollment, 3)
        with journal_unlock():
            LessonMark.objects.filter(pk=changed.pk).update(status="present")
        result = absence_counter_preview(
            organization_id=self.org.pk, added_hours_by_enrollment={self.enrollment.pk: 4}
        )[0]
        self.assertEqual((result["cached_before"], result["own_raw_before"], result["target_credit"]), (99, 2, 3))
        self.assertEqual((result["derived_before"], result["derived_after"], result["source_effect"]), (0, 3, 3))
        self.assertEqual(
            (result["cache_reconciliation"], result["actual_cache_delta_if_applied"], result["canonical_undo_hours"]),
            (-99, -96, 0),
        )
        self.assertFalse(result["cache_mismatch_alone_is_hold"])
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 99)

    def test_only_valid_direct_predecessor_raw_is_clipped_before_carry_not_grandparent_or_cache(self):
        parent = self.history_enrollment("source58-parent", successor=self.enrollment)
        grandparent = self.history_enrollment("source58-grandparent", successor=parent)
        self.make_mark(parent, hours=8)
        self.make_mark(grandparent, hours=10)
        self.credit(parent, 6)
        self.credit(self.enrollment, 3)
        self.make_mark(self.enrollment, hours=4, status="excused", date="2026-09-02")
        result = absence_counter_preview(
            organization_id=self.org.pk, added_hours_by_enrollment={self.enrollment.pk: 4}
        )[0]
        self.assertEqual(result["direct_carried_hours"], 2)
        self.assertEqual(result["derived_before"], 1)
        self.assertEqual(result["derived_after"], 5)
        self.assertEqual(result["direct_predecessor_ids"], [str(parent.pk)])
        closure = evidence._closure(
            row_tools.Rows(), "registrar.Enrollment", {str(self.enrollment.pk)}, "superseded_by_id"
        )
        self.assertEqual(set(closure), {str(self.enrollment.pk), str(parent.pk), str(grandparent.pk)})

    def test_credit_reversal_roots_follow_central_semantics_and_invalid_second_reversal_is_rejected(self):
        original = self.credit(self.enrollment, 2)
        reversal = self.credit(self.enrollment, 2, reverses=original)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.credit(self.enrollment, 2, reverses=reversal)
        self.credit(self.enrollment, 1)
        self.assertEqual(credit_hours_map([self.enrollment.pk])[self.enrollment.pk], 1)
        result = self.collect()
        lifecycle = result["source58_credit_lifecycle"]
        self.assertEqual(len(lifecycle), 3)
        self.assertEqual(sum(row["hours"] for row in lifecycle if row["active_root"]), 1)
        self.assertEqual(effective_hours(2, 3), 0)

    def test_full_projection_is_select_only_and_hides_grade_zero_names_topics_and_credit_reason(self):
        self.make_mark(self.enrollment, hours=2, status="present", date="2026-09-02", score=0)
        self.credit(self.enrollment, 1)

        def select_only(execute, sql, params, many, context):
            self.assertTrue(sql.lstrip().upper().startswith(("SELECT", "SHOW")), sql)
            self.assertNotIn("FOR UPDATE", sql.upper())
            if 'FROM "auth_user"' in sql:
                self.assertNotIn('"password"', sql)
                self.assertNotIn('row_to_json("auth_user")', sql)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(select_only):
            result = self.collect()
        self.assertTrue(result["source58_scope"][0]["bounded_reference_closure_collected"])
        encoded = json.dumps(result, default=str)
        for secret in (
            "PRIVATE_STUDENT_NAME",
            "PRIVATE_PASSWORD_SENTINEL",
            "PRIVATE_LESSON_TOPIC",
            "PRIVATE_SIGNED_CREDIT_REASON",
        ):
            self.assertNotIn(secret, encoded)
        marks = next(row for row in result["source58_reference_graph"] if row["model"] == "registrar.LessonMark")
        self.assertEqual(marks["count"], 2)
        self.assertTrue(all("score" not in row and len(row["_raw_sha"]) == 64 for row in marks["rows"]))
        self.assertEqual(LessonMark.objects.filter(enrollment=self.enrollment, score=0).count(), 1)

    def test_all_status_other_kind_and_inactive_family_claim_is_not_reported_as_missing(self):
        prior = self.history_enrollment("source58-inactive", successor=self.enrollment, active=False)
        self.make_mark(prior, hours=2, status="excused", date="2026-10-03", kind="lecture")
        result = self.collect()
        claims = result["source58_claims"][0]["existing_claims"]
        self.assertEqual(len(claims), 1)
        self.assertEqual((claims[0]["status"], claims[0]["enrollment_status"]), ("excused", "dropped"))
        self.assertFalse(claims[0]["exact_source_slot"])
        self.assertTrue(result["source58_counter_preview"][0]["current_claim_requires_review"])

    def test_formal_excuse_and_actual_typed_clear_claim_export_without_personal_or_grade_body(self):
        apps.get_model("registrar.LegacyExcuseDocument").objects.create(
            organization=self.org,
            student=self.student,
            source_system="myedu_mariadb",
            source_table="allowed_qb",
            source_pk=123,
            source_snapshot_sha256="a" * 64,
            source_row_hash="b" * 64,
            materialization_digest="c" * 64,
            transform_version="fixture",
            mapping_status="linked",
            starts_on="2026-10-01",
            ends_on="2026-10-05",
            note="PRIVATE_EXCUSE_NOTE",
        )
        apps.get_model("audit.AuditLog").objects.create(
            organization=self.org,
            user=self.actor,
            action="update",
            resource_type="registrar.grade.mark",
            resource_id=str(self.offering.pk),
            changes=[
                {
                    "lesson_id": self.source_lesson,
                    "enrollment_id": str(self.enrollment.pk),
                    "old": "qb",
                    "new": "",
                    "student": "PRIVATE_AUDIT_PERSON",
                }
            ],
        )
        result = self.collect()
        self.assertTrue(result["source58_history_changes"][0]["clear_evidence"])
        self.assertNotIn("old_numeric", result["source58_history_changes"][0])
        formal = next(
            row for row in result["source58_reference_graph"] if row["model"] == "registrar.LegacyExcuseDocument"
        )
        self.assertEqual(formal["rows"][0]["starts_on"], "2026-10-01")
        encoded = json.dumps(result, default=str)
        self.assertNotIn("PRIVATE_EXCUSE_NOTE", encoded)
        self.assertNotIn("PRIVATE_AUDIT_PERSON", encoded)

    def test_unlocatable_masked_grade_history_stays_explicit_hold(self):
        audit = apps.get_model("audit.AuditLog").objects.create(
            organization=self.org,
            user=self.actor,
            action="update",
            resource_type="registrar.grade.full-edit",
            resource_id="masked",
            changes=[{"student": "MASKED_PERSON", "old": "8", "new": ""}],
        )
        result = self.collect()
        rows = result["source58_unlocatable_grade_history"]
        self.assertEqual(rows[0]["id"], str(audit.pk))
        self.assertTrue(rows[0]["unresolved_history_hold"])
        self.assertFalse(result["source58_history_coverage"][0]["all_grade_history_resolved"])
        self.assertNotIn("MASKED_PERSON", json.dumps(result, default=str))

    def test_thousands_of_reference_ids_have_bounded_regex_compilation_and_keep_unknown_history(self):
        from apps.workload.services.scoped_snapshot.source58_evidence_history import collect_history

        audit = apps.get_model("audit.AuditLog").objects.create(
            organization=self.org,
            user=self.actor,
            action="update",
            resource_type="registrar.grade.full-edit",
            resource_id="masked",
            changes=[],
        )
        result = collect_history(referenced_ids={str(uuid.uuid4()) for _ in range(4000)})
        self.assertEqual(result["source58_unlocatable_grade_history"][0]["id"], str(audit.pk))
        self.assertTrue(result["source58_unlocatable_grade_history"][0]["unresolved_history_hold"])

    def test_unknown_large_workload_prefix_is_never_exempted_as_known_receipt(self):
        apps.get_model("audit.AuditLog").objects.create(
            organization=self.org,
            user=self.actor,
            action="update",
            resource_type="workload.reviewed_source_batch",
            resource_id=str(self.offering.pk),
            new_values={"unreviewed": "X" * (1024 * 1024 + 1)},
        )
        result = self.collect()
        self.assertEqual(result["source58_scope"][0]["status"], "source58_unknown_audit_byte_budget")
        self.assertEqual(result["source58_scope"][0]["credit_excuse_coverage"], "UNKNOWN")
        self.assertFalse(result["source58_scope"][0]["eligible_for_apply"])

    def test_exact_pinned_large_workload_receipt_uses_existing_thin_semantic_projection(self):
        from apps.workload.services.scoped_snapshot import workload_audit_receipt_spec as receipts
        from apps.workload.tests.test_fixed_workload_audit_receipts import FixedWorkloadReceiptTests

        with patch.dict(receipts.PINS, {}, clear=True), patch.dict(receipts.FIELD_PINS, {}, clear=True):
            audit = FixedWorkloadReceiptTests.receipt(self)
            result = self.collect()
            projected = next(row for row in result["source58_history_audits"] if row["id"] == str(audit.pk))
            self.assertEqual(projected["projection"], "verified_workload_receipt")
            self.assertFalse(projected["unresolved_scope_row"])
            self.assertNotIn("PRIVATE_NO_FETCH", json.dumps(result, default=str))
            self.assertEqual(result["source58_history_coverage"][0]["verified_pinned_workload_receipts"], 1)

    def test_unlinked_actual_source_point_fact_is_exported_as_claim_evidence_not_zero(self):
        apply_rls_request_context(user_id=self.actor.pk, org_id=self.org.pk, bypass=False, local=True)
        fact = apps.get_model("registrar.LegacyGradeFact").objects.create(
            organization=self.org,
            source_system="myedu_mariadb",
            source_table="journals_dates_points",
            source_pk=5447859,
            source_snapshot_sha256="a" * 64,
            source_row_hash="b" * 64,
            materialization_digest="c" * 64,
            transform_version="fixture",
            evidence_kind="other",
            mapping_status="unresolved",
            mapping_issue_code="legacy_grade_fact_unresolved",
            raw_score_text="PRIVATE_GRADE_BODY",
        )
        result = self.collect()
        facts = next(row for row in result["source58_reference_graph"] if row["model"] == "registrar.LegacyGradeFact")
        self.assertEqual(facts["rows"][0]["id"], str(fact.pk))
        self.assertEqual(facts["rows"][0]["source_pk"], 5447859)
        self.assertEqual(facts["rows"][0]["mapping_status"], "unresolved")
        self.assertNotIn("PRIVATE_GRADE_BODY", json.dumps(result, default=str))

    def test_budgets_are_unknown_not_silent_truncation_or_zero_coverage(self):
        with patch.object(row_tools, "MAX_ROWS", 1):
            result = self.collect()
        self.assertFalse(result["source58_scope"][0]["bounded_reference_closure_collected"])
        self.assertEqual(result["source58_scope"][0]["credit_excuse_coverage"], "UNKNOWN")

    def test_real_readwrite_transaction_is_refused_without_data_mutation(self):
        result = evidence.collect_source58_evidence()
        self.assertFalse(result["source58_scope"][0]["bounded_reference_closure_collected"])
        self.assertIn("readonly", result["source58_scope"][0]["status"])
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 99)

    def test_missing_fixed_course_or_enrollment_is_unknown_not_complete_zero_evidence(self):
        with patch.object(
            fixed, "OFFERINGS", {**fixed.OFFERINGS, str(uuid.uuid4()): dict(next(iter(fixed.OFFERINGS.values())))}
        ):
            result = self.collect()
        self.assertEqual(result["source58_scope"][0]["status"], "source58_fixed_courses_missing")
        self.assertEqual(result["source58_scope"][0]["credit_excuse_coverage"], "UNKNOWN")
        cases = {point: dict(case, enrollment_id=str(uuid.uuid4())) for point, case in fixed.CASES.items()}
        with patch.object(fixed, "CASES", cases):
            result = self.collect()
        self.assertEqual(result["source58_scope"][0]["status"], "source58_fixed_enrollments_missing")
        self.assertFalse(result["source58_scope"][0]["bounded_reference_closure_collected"])


class Source58RealReadOnlyTests(Source58Fixture, TransactionTestCase):
    def setUp(self):
        self.make_fixture()

    def test_real_repeatable_read_only_capture_in_both_rls_modes_preserves_cache_and_marks(self):
        self.credit(self.enrollment, 1)
        for scoped in (False, True):
            with self.subTest(scoped=scoped), override_settings(RLS_TRANSACTION_SCOPED=scoped):
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    apply_rls_request_context(user_id=self.actor.pk, org_id=self.org.pk, bypass=False, local=True)
                    result = evidence.collect_source58_evidence()
                    self.assertTrue(
                        result["source58_scope"][0]["bounded_reference_closure_collected"], result["source58_scope"]
                    )
                    self.assertEqual(result["source58_credit_lifecycle"][0]["hours"], 1)
                reset_rls_context()
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 99)
        self.assertEqual(LessonMark.objects.count(), 1)

    def test_wrong_tenant_and_bypass_are_unknown_not_an_empty_success(self):
        for org, bypass in ((uuid.uuid4(), False), (self.org.pk, True)):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                apply_rls_request_context(user_id=self.actor.pk, org_id=org, bypass=bypass, local=True)
                result = evidence.collect_source58_evidence()
                self.assertEqual(result["source58_scope"][0]["credit_excuse_coverage"], "UNKNOWN")
            reset_rls_context()
