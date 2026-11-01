"""Migrated PG: both load FKs only; every exam/body/cell/credit stays in place."""

import copy
from contextlib import ExitStack
from io import StringIO
from unittest.mock import patch

from django.apps import apps
from django.core.management import call_command
from django.test import TestCase

from apps.syllabus.public import content_fingerprints
from apps.workload.services import reviewed_two_catalog_repair as repair
from apps.workload.services import reviewed_two_catalog_schema as schema
from apps.workload.services import reviewed_two_catalog_spec as spec
from apps.workload.services import reviewed_two_catalog_state as state
from apps.workload.services.reviewed_leyla_catalog_graph import RepairError, bounded, digest, normal
from apps.workload.tests import test_reviewed_leyla_catalog as fixtures


class TwoCatalogTests(TestCase):
    setUpTestData = classmethod(fixtures.ReviewedLeylaCatalogTests.setUpTestData.__func__)

    def setUp(self):
        self.rows[1].groups.set([self.stacks[1]["group"]])
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        cases = []
        # Own Named human draft is retained even when its workload moves to the real journal.
        syl = apps.get_model("syllabus", "Syllabus").objects.create(
            organization=self.org,
            offering=self.empty[0],
            subject=self.empty[0].subject,
            period=self.period,
            author=self.teacher,
            chair_unit=self.task.chair,
        )
        self.draft = apps.get_model("syllabus", "SyllabusVersion").objects.create(
            organization=self.org, syllabus=syl, major=1, minor=0, status="draft", created_by=self.teacher
        )
        self.draft_section = apps.get_model("syllabus", "SyllabusSection").objects.create(
            organization=self.org,
            version=self.draft,
            section_id="desc",
            data={"description": "Meaningful human draft preserved exactly"},
        )
        for idx, row in enumerate(self.rows):
            a, b = self.empty[idx], self.filled[idx]
            group = self.stacks[idx]["group"]
            raw = normal(type(row).objects.filter(pk=row.pk).values().get())
            assignments = bounded(apps.get_model("workload", "TeacherAssignment").objects.filter(row=row))
            bridge = [
                r
                for r in self.bridge
                if r["entity_type"] in ("worker", "worker_materialisation")
                or r["entity_type"] == "group_unit"
                and r["legacy_pk"] == str(600 + idx)
                or r["entity_type"] == "lesson_subject"
                and r["legacy_pk"] == str(2500 + idx)
            ]
            syl, version = self.syllabi[idx]
            roster = sorted(
                apps.get_model("registrar", "Enrollment")
                .objects.filter(offering=b)
                .values_list("student_id", flat=True)
            )
            with patch.object(state.snapshots, "ORG", str(self.org.pk)):
                counts = normal(state.snapshots.offering_counts([a.pk, b.pk]))
            cases.append(
                dict(
                    row_id=str(row.pk),
                    row_fields={k: v for k, v in raw.items() if k not in ("id", "subject_id")},
                    before_subject=str(a.subject_id),
                    after_subject=str(b.subject_id),
                    teacher=self.teacher.pk,
                    offerings={
                        str(o.pk): normal(
                            {
                                k: getattr(o, k)
                                for k in (
                                    "id",
                                    "group_id",
                                    "period_id",
                                    "subject_id",
                                    "instructor_id",
                                    "lesson_hours",
                                    "is_active",
                                )
                            }
                        )
                        for o in (a, b)
                    },
                    empty=str(a.pk),
                    filled=str(b.pk),
                    group=normal(
                        {
                            k: getattr(group, k)
                            for k in ("id", "code", "name", "parent_id", "unit_type", "settings", "is_active")
                        }
                    ),
                    subjects={
                        str(o.subject_id): {
                            "id": str(o.subject_id),
                            "name": o.subject.name,
                            "code": o.subject.code,
                            "chair_unit_id": normal(o.subject.chair_unit_id),
                        }
                        for o in (a, b)
                    },
                    assignments=[
                        {k: r[k] for k in ("id", "row_id", "teacher_id", "hours", "activity", "is_hourly_paid")}
                        for r in assignments
                    ],
                    roster={"count": len(roster), "sha256": digest(roster)},
                    counts={r["offering_id"]: r for r in counts},
                    donor={
                        "id": str(syl.pk),
                        "approved_version_id": str(version.pk),
                        "body_sha256": content_fingerprints({s.section_id: s.data for s in version.sections.all()})[
                            "canonical_body_sha256"
                        ],
                    },
                    bridge=bridge,
                    source={
                        "chair_id": str(self.task.chair_id),
                        "original_evidence": "fixture-only exact source authority",
                    },
                )
            )
        for name, value in {
            "ORG": str(self.org.pk),
            "PERIOD": str(self.period.pk),
            "YEAR": self.period.academic_year,
            "CASES": cases,
            "SCHEMA": schema.fingerprints(),
        }.items():
            self.patches.enter_context(patch.object(spec, name, copy.deepcopy(value)))
        self.patches.enter_context(patch.object(state.snapshots, "ORG", str(self.org.pk)))

    def run_repair(self, **kwargs):
        return repair.run(organization=self.org, actor=self.actor, **kwargs)

    def apply(self):
        dry = self.run_repair()
        return self.run_repair(apply=True, expected_baseline=dry["baseline"])

    def test_apply_repeat_undo_preserves_all_graph_credit_human_body_and_schedule(self):
        before = state.snapshot(self.org)
        rowcredits = [row.credits for row in self.rows]
        applied = self.apply()
        after = state.snapshot(self.org)
        self.assertEqual(repair.protected(before), repair.protected(after))
        self.assertTrue(after["corrected"])
        self.assertEqual(self.run_repair(apply=True)["status"], "already_applied")
        self.draft_section.refresh_from_db()
        self.assertEqual(self.draft_section.data, {"description": "Meaningful human draft preserved exactly"})
        self.assertEqual([type(r).objects.get(pk=r.pk).credits for r in self.rows], rowcredits)
        self.assertEqual(after["protected"]["registrar.ScheduleSlot"], before["protected"]["registrar.ScheduleSlot"])
        dry = self.run_repair(undo=applied["receipt"])
        self.run_repair(undo=applied["receipt"], apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(state.snapshot(self.org), before)
        self.assertEqual(self.run_repair(undo=applied["receipt"], apply=True)["status"], "already_undone")

    def test_stale_baseline_and_partial_state_refused(self):
        with self.assertRaisesRegex(RepairError, "fresh_baseline"):
            self.run_repair(apply=True, expected_baseline="a" * 64)
        row = self.rows[0]
        type(row).objects.filter(pk=row.pk).update(subject=self.old_subjects[0])
        with self.assertRaisesRegex(RepairError, "partial_relink"):
            self.run_repair()

    def test_mark_drift_refuses_apply_without_touching_other_row(self):
        dry = self.run_repair()
        mark = apps.get_model("registrar", "LessonMark").objects.filter(lesson__offering=self.filled[0]).first()
        type(mark).objects.filter(pk=mark.pk).update(score=1)
        with self.assertRaisesRegex(RepairError, "content_fingerprint"):
            self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.rows[1].refresh_from_db()
        self.assertEqual(self.rows[1].subject_id, self.empty[1].subject_id)

    def test_exam_upstream_attempt_answers_and_exact_links_are_retained(self):
        exam = apps.get_model("exams", "Exam").objects.create(
            organization=self.org, author=self.teacher, subject=self.empty[0].subject, title="Exam-only Named history"
        )
        exam.journal_offerings.add(self.empty[0])
        student = self.enrs[0].student
        attempt = apps.get_model("exams", "ExamAttempt").objects.create(
            exam=exam, user=student, status="submitted", correct_count=0, wrong_count=20
        )
        question = apps.get_model("exams", "ExamQuestion").objects.create(exam=exam, text="Exact question")
        answer = apps.get_model("exams", "ExamAnswer").objects.create(
            attempt=attempt, question=question, is_correct=False
        )
        before = state.snapshot(self.org)
        for label, count in (
            ("exams.Exam", 1),
            ("exams.ExamAttempt", 1),
            ("exams.ExamAnswer", 1),
            ("exams.Exam_journal_offerings", 1),
        ):
            self.assertEqual(before["protected"][label]["count"], count)
        applied = self.apply()
        self.assertEqual(repair.protected(before), repair.protected(state.snapshot(self.org)))
        self.assertEqual(set(exam.journal_offerings.values_list("pk", flat=True)), {self.empty[0].pk})
        type(answer).objects.filter(pk=answer.pk).update(is_correct=True)
        with self.assertRaisesRegex(RepairError, "undo_state_changed"):
            self.run_repair(undo=applied["receipt"])

    def test_schema_drift_holds_even_when_new_reverse_table_is_empty(self):
        altered = {**spec.SCHEMA, "unreviewed.Child": "a" * 64}
        with patch.object(schema, "fingerprints", return_value=altered):
            with self.assertRaisesRegex(RepairError, "unreviewed_relation_schema"):
                self.run_repair()

    def test_donor_body_change_and_teacher_tenant_revocation_hold(self):
        self.syllabi[0][1].sections.filter(section_id="desc").update(data={"description": "Changed"})
        with self.assertRaisesRegex(RepairError, "source_body_changed"):
            self.run_repair()

    def test_unreviewed_group_expansion_holds(self):
        self.rows[0].groups.add(self.stacks[2]["group"])
        with self.assertRaisesRegex(RepairError, "row_groups"):
            self.run_repair()

    def test_existing_target_schedule_conflict_is_never_parked_or_copied(self):
        Slot = apps.get_model("registrar", "ScheduleSlot")
        slot = Slot.all_objects.filter(offering=self.empty[0]).first()
        target = Slot.objects.create(
            organization=self.org,
            offering=self.filled[0],
            weekday=slot.weekday,
            start_time=slot.start_time,
            end_time=slot.end_time,
            week_type=slot.week_type,
            kind=slot.kind,
            room=slot.room,
        )
        with self.assertRaisesRegex(RepairError, "target_schedule_conflict"):
            self.run_repair()
        target.refresh_from_db()
        self.assertFalse(target.is_parked)

    def test_exact_actor_and_safe_command_summary_only(self):
        output = StringIO()
        call_command("repair_reviewed_two_catalog", actor=self.actor.username, stdout=output)
        self.assertIn("reviewed_two_catalog: status=dry_run rows=2 applied=0 baseline=", output.getvalue())
        self.assertNotIn("Meaningful human", output.getvalue())
        self.actor.is_active = False
        with self.assertRaisesRegex(RepairError, "tenant_superadmin"):
            self.run_repair()

    def test_new_canonical_positive_load_is_not_merged(self):
        rival = fixtures.make_row(self.task, self.stacks[0])
        rival.subject = self.filled[0].subject
        rival.save()
        with self.assertRaisesRegex(RepairError, "canonical_workload_authority"):
            self.run_repair()

    def test_teacher_profile_or_permission_revocation_holds(self):
        apps.get_model("accounts", "UserProfile").objects.filter(user=self.teacher).update(access_state="blocked")
        with self.assertRaisesRegex(RepairError, "teacher_permission"):
            self.run_repair()

    def test_source_pin_conflict_is_not_guessed_from_matching_title(self):
        cases = copy.deepcopy(spec.CASES)
        cases[0]["bridge"][0]["source_row_hash"] = "f" * 64
        with patch.object(spec, "CASES", cases):
            with self.assertRaisesRegex(RepairError, "typed_source_bridge"):
                self.run_repair()

    def test_second_snapshot_failure_rolls_back_both_fks_and_amendments(self):
        dry = self.run_repair()
        original = state.snapshot
        calls = []

        def failing(org, **kwargs):
            calls.append(org.pk)
            value = original(org, **kwargs)
            if len(calls) == 2:
                raise RepairError("two_catalog_full_graph_preservation_failed")
            return value

        with patch.object(state, "snapshot", side_effect=failing):
            with self.assertRaisesRegex(RepairError, "preservation_failed"):
                self.run_repair(apply=True, expected_baseline=dry["baseline"])
        for row, course in zip(self.rows, self.empty):
            row.refresh_from_db()
            self.assertEqual(row.subject_id, course.subject_id)
        self.assertEqual(apps.get_model("workload", "WorkloadAmendment").objects.count(), 0)

    def test_credit_manual_edit_after_apply_is_never_overwritten_by_undo(self):
        result = self.apply()
        type(self.rows[0]).objects.filter(pk=self.rows[0].pk).update(credits="9")
        with self.assertRaisesRegex(RepairError, "row_fields_changed"):
            self.run_repair(undo=result["receipt"])
        self.rows[0].refresh_from_db()
        self.assertEqual(self.rows[0].credits, "9")

    def test_encrypted_snapshot_graph_metadata_reads_complete_human_body_without_writes(self):
        import json

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from apps.workload.services.scoped_snapshot.two_catalog_references import collect_two_catalog_references

        with CaptureQueriesContext(connection) as captured:
            data = collect_two_catalog_references()
        self.assertTrue(data["two_catalog_reference_scope"][0]["schema_matches_reviewed"])
        self.assertFalse(data["two_catalog_reference_scope"][0]["eligible_for_apply"])
        fields = {key: sorted({field for row in values for field in row}) for key, values in data.items()}
        self.assertEqual(fields["two_catalog_reference_scope"], sorted(data["two_catalog_reference_scope"][0]))
        graph = {r["model"]: r for r in data["two_catalog_reference_graph"]}
        self.assertGreater(graph["syllabus.SyllabusVersion"]["count"], 2)
        native = state.snapshot(self.org)["protected"]
        derived = {
            label: {"count": node["count"], "sha256": node.get("subject_invariant_sha256", node["sha256"])}
            for label, node in graph.items()
        }
        self.assertEqual(derived, native)
        self.assertNotIn("Meaningful human draft", json.dumps(data))
        self.assertFalse(
            any(q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "ALTER")) for q in captured)
        )
