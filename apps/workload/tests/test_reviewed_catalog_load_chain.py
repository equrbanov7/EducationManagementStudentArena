"""Real PG atomic3: source2 and fallback receipt chain all commit or all roll back."""

import copy
from io import StringIO
from unittest.mock import patch

from django.apps import apps
from django.core.management import call_command
from django.test import TestCase

from apps.syllabus.public import content_fingerprints
from apps.workload.services import reviewed_catalog_load_chain as chain
from apps.workload.services import reviewed_two_catalog_repair as core
from apps.workload.services import reviewed_two_catalog_spec as two
from apps.workload.services import reviewed_two_catalog_state as state
from apps.workload.services import reviewed_vefa_catalog_spec as vefa
from apps.workload.services.reviewed_leyla_catalog_graph import RepairError, bounded, digest, normal
from apps.workload.tests import test_reviewed_two_catalog as fixtures


class AtomicCatalogTests(TestCase):
    setUpTestData = classmethod(fixtures.TwoCatalogTests.setUpTestData.__func__)

    def setUp(self):
        fixtures.TwoCatalogTests.setUp(self)
        self.third = fixtures.fixtures.make_row(self.task, self.stacks[2], seminar_total=30)
        self.third.subject = self.empty[2].subject
        self.third.save()
        Assignment = apps.get_model("workload", "TeacherAssignment")
        for activity, hours in (("lecture", 30), ("seminar", 30)):
            Assignment.objects.create(
                organization=self.org, row=self.third, teacher=self.teacher, activity=activity, hours=hours
            )
        pin = copy.deepcopy(two.CASES[1])
        raw = normal(type(self.third).objects.filter(pk=self.third.pk).values().get())
        a, b = self.empty[2], self.filled[2]
        group = self.stacks[2]["group"]
        syl, version = self.syllabi[2]
        counts = normal(state.snapshots.offering_counts([a.pk, b.pk]))
        users = sorted(
            apps.get_model("registrar", "Enrollment").objects.filter(offering=b).values_list("student_id", flat=True)
        )
        ass = bounded(Assignment.objects.filter(row=self.third))
        pin.update(
            row_id=str(self.third.pk),
            row_fields={k: v for k, v in raw.items() if k not in ("id", "subject_id")},
            empty=str(a.pk),
            filled=str(b.pk),
            group=normal(
                {
                    k: getattr(group, k)
                    for k in ("id", "code", "name", "parent_id", "unit_type", "settings", "is_active")
                }
            ),
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
            assignments=[
                {k: r[k] for k in ("id", "row_id", "teacher_id", "hours", "activity", "is_hourly_paid")} for r in ass
            ],
            counts={r["offering_id"]: r for r in counts},
            roster={"count": len(users), "sha256": digest(users)},
            bridge=[
                r
                for r in self.bridge
                if r["entity_type"] in ("worker", "worker_materialisation")
                or r["entity_type"] == "group_unit"
                and r["legacy_pk"] == "602"
                or r["entity_type"] == "lesson_subject"
                and r["legacy_pk"] == "2501"
            ],
            donor={
                "id": str(syl.pk),
                "approved_version_id": str(version.pk),
                "body_sha256": content_fingerprints({r.section_id: r.data for r in version.sections.all()})[
                    "canonical_body_sha256"
                ],
            },
        )
        for name, value in {
            "ORG": two.ORG,
            "PERIOD": two.PERIOD,
            "YEAR": two.YEAR,
            "SCHEMA": two.SCHEMA,
            "CASES": [pin],
        }.items():
            self.patches.enter_context(patch.object(vefa, name, value))

    def run_chain(self, **kwargs):
        return chain.run(organization=self.org, actor=self.actor, **kwargs)

    def test_atomic_three_rows_apply_native_receipts_repeat_and_complete_graph_preserved(self):
        before = {name: state.snapshot(self.org, contract=c) for name, c, _ in chain.STAGES}
        dry = self.run_chain()
        self.assertEqual((dry["status"], dry["rows"], dry["applied"]), ("dry_run", 3, False))
        result = self.run_chain(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual((result["rows"], result["applied"]), (3, True))
        repeat = self.run_chain()
        self.assertEqual(
            (repeat["status"], repeat["rows"], repeat["receipt"]), ("already_applied", 0, result["receipt"])
        )
        for name, c, _ in chain.STAGES:
            self.assertEqual(core.protected(before[name]), core.protected(state.snapshot(self.org, contract=c)))
        audit = apps.get_model("audit", "AuditLog").objects.get(
            resource_type=chain.RESOURCE, resource_id=result["receipt"]
        )
        self.assertEqual(len(set(audit.new_values["native_receipts"].values())), 2)
        self.assertEqual(apps.get_model("workload", "WorkloadAmendment").objects.count(), 3)

    def test_fallback_apply_failure_rolls_back_previously_applied_two_rows_and_receipts(self):
        dry = self.run_chain()
        native = core.run

        def failing(**kwargs):
            if kwargs.get("contract") is vefa and kwargs.get("apply"):
                raise RepairError("catalog_chain_native_apply_required")
            return native(**kwargs)

        with patch.object(core, "run", side_effect=failing):
            with self.assertRaisesRegex(RepairError, "native_apply"):
                self.run_chain(apply=True, expected_baseline=dry["baseline"])
        for row, course in zip([*self.rows, self.third], self.empty):
            row.refresh_from_db()
            self.assertEqual(row.subject_id, course.subject_id)
        self.assertEqual(apps.get_model("workload", "WorkloadAmendment").objects.count(), 0)
        self.assertFalse(
            apps.get_model("audit", "AuditLog")
            .objects.filter(resource_type__in=[chain.RESOURCE, core.RESOURCE, vefa.RESOURCE])
            .exists()
        )

    def test_stale_combined_baseline_and_previously_partial_state_hold(self):
        with self.assertRaisesRegex(RepairError, "fresh_baseline"):
            self.run_chain(apply=True, expected_baseline="a" * 64)
        native = core.run(organization=self.org, actor=self.actor)
        core.run(organization=self.org, actor=self.actor, apply=True, expected_baseline=native["baseline"])
        with self.assertRaisesRegex(RepairError, "partial_existing"):
            self.run_chain()

    def test_command_safe_dry_summary_has_three_fixed_rows_no_body(self):
        out = StringIO()
        call_command("repair_reviewed_catalog_load_chain", actor=self.actor.username, stdout=out)
        self.assertIn("reviewed_catalog_load_chain: status=dry_run rows=3 applied=0", out.getvalue())
        self.assertNotIn("Meaningful human", out.getvalue())

    def test_encrypted_metadata_binding_matches_native_dry_full_graph(self):
        from apps.workload.services.scoped_snapshot.two_catalog_references import collect_two_catalog_references
        from apps.workload.services.scoped_snapshot.vefa_catalog_references import collect_vefa_catalog_references

        data = {**collect_two_catalog_references(), **collect_vefa_catalog_references()}
        parts = {}
        for name, _, _ in chain.STAGES:
            parts[name] = digest(
                {
                    node["model"]: {
                        "count": node["count"],
                        "sha256": node.get("subject_invariant_sha256", node["sha256"]),
                    }
                    for node in data[name + "_reference_graph"]
                }
            )
        self.assertEqual(self.run_chain()["graph"], digest(parts))

    def test_real_exam_answer_drift_after_atomic_apply_blocks_repeat(self):
        exam = apps.get_model("exams", "Exam").objects.create(
            organization=self.org, author=self.teacher, subject=self.empty[0].subject, title="Retained real exam"
        )
        exam.journal_offerings.add(self.empty[0])
        attempt = apps.get_model("exams", "ExamAttempt").objects.create(
            exam=exam, user=self.enrs[0].student, status="submitted"
        )
        question = apps.get_model("exams", "ExamQuestion").objects.create(exam=exam, text="Exact source")
        answer = apps.get_model("exams", "ExamAnswer").objects.create(
            attempt=attempt, question=question, is_correct=False
        )
        dry = self.run_chain()
        self.run_chain(apply=True, expected_baseline=dry["baseline"])
        type(answer).objects.filter(pk=answer.pk).update(is_correct=True)
        with self.assertRaises(RepairError):
            self.run_chain()
