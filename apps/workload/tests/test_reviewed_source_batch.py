"""A reusable reviewed batch preserves identity, content and rollback boundaries."""

import copy
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from apps.audit.models import AuditLog
from apps.registrar.models import CourseOffering, Lesson, LessonMark, Subject
from apps.workload.models import TeachingTaskRow
from apps.workload.services import reviewed_batch as repair
from apps.workload.services import reviewed_batch_state as state
from apps.workload.services.reviewed_batch_manifest import ORG, RESOURCE, YEAR, geometry, read_manifest, select_manifest
from apps.workload.services.sbio235_state import RepairError, records
from core.rls import apply_rls_request_context, reset_rls_context


class ReviewedManifestTests(SimpleTestCase):
    def test_strict_hour_geometry_retains_unit_and_total(self):
        for raw, expected in (
            (30, {"unit": 30, "total": 30, "count": 1}),
            ("15*2", {"unit": 15, "total": 30, "count": 2}),
            ("30 + 30", {"unit": 30, "total": 60, "count": 2}),
            ("10×3", {"unit": 10, "total": 30, "count": 3}),
            (" - ", {"unit": 0, "total": 0, "count": 1}),
        ):
            self.assertEqual(geometry(raw), expected)
        for raw in ("15+20", "15*2+30", "1.5", "-3", "10/2", "__import__('os')", "10*99"):
            with self.subTest(raw=raw), self.assertRaises(RepairError):
                geometry(raw)

    def test_private_file_and_exact_sha_required(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.json"
            path.write_text('{"format":"example"}')
            path.chmod(0o600)
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(read_manifest(path, sha)["format"], "example")
            with self.assertRaisesMessage(RepairError, "sha256_mismatch"):
                read_manifest(path, "0" * 64)
            path.chmod(0o644)
            with self.assertRaisesMessage(RepairError, "private_regular"):
                read_manifest(path, sha)

    def test_large_or_symbolic_manifest_is_not_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.json"
            path.write_text("{}")
            path.chmod(0o600)
            linked = Path(folder) / "linked.json"
            linked.symlink_to(path)
            with self.assertRaises(OSError):
                read_manifest(linked, hashlib.sha256(path.read_bytes()).hexdigest())


def source_entry(*, line, subject, group, task, teacher, hours, mode, offering=None, row=None):
    values = {season + "_" + kind: 0 for season in ("fall", "spring") for kind in ("lecture", "seminar", "lab")}
    values.update({"fall_" + kind: value for kind, value in hours.items()})
    expected = {kind: hours.get(kind, 0) for kind in ("lecture", "seminar", "lab")}
    current = []
    if row is not None:
        current = state.workload_records(TeachingTaskRow.objects.filter(pk=row.pk))
        current[0]["group_ids"] = current[0]["groups"]
    profile = teacher.profile
    return {
        "source_reference": {"line": line, "sha256": "a" * 64, "values": values},
        "desired_row": {
            "task_id": str(task.pk),
            "season": "fall",
            "group_ids": [str(group.pk)],
            "period_id": str(offering.period_id if offering else row.period_id),
            "groups_text": group.name,
            "education_form": "full_time",
            "degree_level": "bachelor",
            "credits": 5,
            "student_count": 7,
            "specialty_id": str(group.parent_id),
        },
        "physical_source_groups": [
            {"id": str(group.pk), "name": group.name, "parent_id": str(group.parent_id), "children": []}
        ],
        "desired_contacts": expected,
        "expected_assignments": [
            {"teacher_id": teacher.pk, "activity": kind, "hours": value, "is_hourly_paid": False}
            for kind, value in expected.items()
            if value
        ],
        "selected_subject_id": str(subject.pk),
        "subject_candidates": [{"id": str(subject.pk), "name": subject.name, "code": subject.code}],
        "existing_rows": current,
        "existing_journals": [{"id": str(offering.pk), "lesson_hours": offering.lesson_hours}] if offering else [],
        "teacher_identity": [
            {
                "id": teacher.pk,
                "first_name": teacher.first_name,
                "last_name": teacher.last_name,
                "patronymic": profile.patronymic,
            }
        ],
        "ready_class": mode,
    }


@override_settings(RLS_TRANSACTION_SCOPED=True)
class ReviewedBatchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Existing fixture has two different teachers/chairs, an unselected row,
        # approved own syllabus, seven roster rows and 84 historical marks.
        from .test_cavid_source_batch import CavidSourceBatchTests

        CavidSourceBatchTests.setUpTestData.__func__(cls)
        cls.new_subject = Subject.objects.create(organization=cls.org, code="SOURCE-NEW", name="Yeni rəsmi fənn")

    def setUp(self):
        apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
        restore = source_entry(
            line=50,
            subject=self.sa,
            group=self.ga,
            task=self.ta,
            teacher=self.teacher,
            hours={"lecture": 30, "seminar": 30},
            mode="existing_owner_no_load",
            offering=self.a,
        )
        changed = source_entry(
            line=3,
            subject=self.sb,
            group=self.gb,
            task=self.tb,
            teacher=self.previous,
            hours={"lecture": 30, "seminar": 15},
            mode="existing_course_patch_owner_preserved",
            offering=self.b,
            row=self.rb,
        )
        new = source_entry(
            line=7,
            subject=self.new_subject,
            group=self.ga,
            task=self.ta,
            teacher=self.teacher,
            hours={"lecture": 20, "seminar": 10},
            mode="literal_or_spelling_unique_existing_membership_newrow",
            offering=self.a,
        )
        new["existing_journals"] = []
        self.manifest = {
            "format": "reviewed-workload-source/1",
            "organization_id": ORG,
            "academic_year": YEAR,
            "chair_id": str(self.finance.pk),
            "source_entries": [restore, changed, new],
            "metadata_fixes": [],
        }
        self.plan = select_manifest(self.manifest, sha256="b" * 64, lines=[3, 7, 50])

    def tearDown(self):
        reset_rls_context()

    def run_batch(self, **kwargs):
        return repair.run(plan=self.plan, organization=self.org, user=self.admin, **kwargs)

    def apply(self):
        preview = self.run_batch()
        return self.run_batch(apply=True, expected_baseline=preview["baseline"])

    def test_dry_run_executes_all_operations_and_rolls_back(self):
        before = state.snapshot(self.plan)
        result = self.run_batch()
        self.assertEqual(result["created_rows"], 2)
        self.assertEqual(result["patched_rows"], 1)
        self.assertEqual(result["created_journals"], 1)
        self.assertEqual(state.snapshot(self.plan), before)
        self.assertFalse(AuditLog.objects.filter(resource_type=RESOURCE).exists())

    def test_apply_preserves_marks_syllabus_roster_membership_and_other_row(self):
        old_marks = list(LessonMark.objects.order_by("pk").values())
        old_primary = self.primary.is_primary
        old_syllabus = records(self.a.syllabi.all()) if hasattr(self.a, "syllabi") else None
        old_other = records(TeachingTaskRow.objects.filter(pk=self.other_row.pk))
        result = self.apply()
        self.rb.refresh_from_db()
        self.b.refresh_from_db()
        self.primary.refresh_from_db()
        self.assertEqual((self.rb.lecture_plan, self.rb.seminar_plan), (30, 15))
        self.assertEqual(self.b.instructor_id, self.previous.pk)
        self.assertEqual(list(LessonMark.objects.order_by("pk").values()), old_marks)
        self.assertEqual(records(TeachingTaskRow.objects.filter(pk=self.other_row.pk)), old_other)
        self.assertEqual(self.primary.is_primary, old_primary)
        self.assertEqual(self.a.enrollments.count(), 7)
        if old_syllabus is not None:
            self.assertEqual(records(self.a.syllabi.all()), old_syllabus)
        self.assertEqual(CourseOffering.objects.filter(subject=self.new_subject, group=self.ga).count(), 1)
        self.assertEqual(self.run_batch()["already_done"], 1)
        self.assertTrue(AuditLog.objects.filter(resource_type=RESOURCE, resource_id=result["batch"]).exists())

    def test_late_failure_rolls_back_every_row_and_journal(self):
        before = state.snapshot(self.plan)
        with patch(
            "apps.workload.services.reviewed_batch.guards.verify_after", side_effect=RepairError("late_failure")
        ):
            with self.assertRaisesMessage(RepairError, "late_failure"):
                self.run_batch()
        self.assertEqual(state.snapshot(self.plan), before)

    def test_stale_baseline_refuses_without_mutation(self):
        before = state.snapshot(self.plan)
        with self.assertRaisesMessage(RepairError, "baseline_conflict"):
            self.run_batch(apply=True, expected_baseline="f" * 64)
        self.assertEqual(state.snapshot(self.plan), before)

    def test_exact_subject_code_title_guard_including_cached_catalogue_class(self):
        self.manifest["source_entries"][2]["ready_class"] = "older_catalogue_fk_current_preflight_needed"
        self.plan = select_manifest(self.manifest, sha256="b" * 64, lines=[7])
        Subject.objects.filter(pk=self.new_subject.pk).update(name="Dəyişmiş başqa fənn")
        with self.assertRaisesMessage(RepairError, "subject_exact_code_title_org_guard"):
            self.run_batch()

    def test_cannot_change_owner_or_add_scoped_membership(self):
        self.manifest["source_entries"][1]["teacher_identity"] = self.manifest["source_entries"][0]["teacher_identity"]
        for assignment in self.manifest["source_entries"][1]["expected_assignments"]:
            assignment["teacher_id"] = self.teacher.pk
        self.plan = select_manifest(self.manifest, sha256="b" * 64, lines=[3])
        before = records(state.model("organizations.Membership").objects.filter(organization=self.org))
        with self.assertRaisesMessage(RepairError, "existing_scoped_teacher_membership_required"):
            self.run_batch()
        self.assertEqual(records(state.model("organizations.Membership").objects.filter(organization=self.org)), before)

    def test_reviewed_existing_row_change_is_rejected(self):
        TeachingTaskRow.objects.filter(pk=self.rb.pk).update(lecture_plan=44)
        with self.assertRaisesMessage(RepairError, "reviewed_existing_row_changed"):
            self.run_batch()

    def test_past_recorded_hours_above_source_plan_are_not_erased(self):
        Lesson.objects.create(
            organization=self.org,
            offering=self.b,
            date="2026-10-29",
            kind="seminar",
            hours=16,
            instructor=self.previous,
            created_by=self.admin,
        )
        with self.assertRaisesMessage(RepairError, "source_plan_below_recorded"):
            self.run_batch()

    def test_missing_restore_journal_and_existing_newrow_are_rejected(self):
        self.manifest["source_entries"][0]["existing_journals"] = []
        self.plan = select_manifest(self.manifest, sha256="b" * 64, lines=[50])
        with self.assertRaisesMessage(RepairError, "journal_allowlist_changed"):
            self.run_batch()

    def test_unsupported_handover_and_delegated_cavid_case_rejected(self):
        for field, value in (
            ("ready_class", "existing_course_requires_explicit_handover_preserving_history"),
            ("delegated_existing_repair", "Cavid35"),
        ):
            changed = copy.deepcopy(self.manifest)
            changed["source_entries"][0][field] = value
            with self.assertRaisesMessage(RepairError, "outside_reviewed_operation_classes"):
                select_manifest(changed, sha256="b" * 64, lines=[50])

    def test_undo_is_receipt_guarded_and_preserves_old_mark_history(self):
        before = state.snapshot(self.plan)
        result = self.apply()
        preview = self.run_batch(undo=result["batch"])
        self.run_batch(undo=result["batch"], apply=True, expected_baseline=preview["baseline"])
        self.assertEqual(TeachingTaskRow.objects.count(), len(before["rows"]))
        self.rb.refresh_from_db()
        self.assertEqual((self.rb.lecture_plan, self.rb.seminar_plan), (45, 0))
        self.assertEqual(LessonMark.objects.count(), 84)
        self.assertFalse(CourseOffering.objects.filter(subject=self.new_subject).exists())
        self.assertEqual(self.run_batch(undo=result["batch"])["already_done"], 1)

    def test_undo_rejects_later_lesson_or_manual_share(self):
        result = self.apply()
        new = CourseOffering.objects.get(subject=self.new_subject)
        Lesson.objects.create(
            organization=self.org,
            offering=new,
            date="2026-10-29",
            kind="lecture",
            hours=2,
            instructor=self.teacher,
            created_by=self.admin,
        )
        with self.assertRaisesMessage(RepairError, "undo_requires_unchanged_receipt_state"):
            self.run_batch(undo=result["batch"])
        self.assertTrue(CourseOffering.objects.filter(pk=new.pk).exists())

    def test_no_intermediate_offering_sync_during_row_and_assignment_writes(self):
        with (
            patch("apps.workload.services.tasks._sync_row_offerings", side_effect=AssertionError("interim_sync")),
            patch(
                "apps.workload.services.assignments._sync_row", side_effect=AssertionError("interim_assignment_sync")
            ),
        ):
            self.run_batch()

    def test_duplicate_source_line_and_duplicate_course_are_rejected(self):
        with self.assertRaisesMessage(RepairError, "explicit_unique"):
            select_manifest(self.manifest, sha256="b" * 64, lines=[7, 7])
        duplicated = copy.deepcopy(self.manifest["source_entries"][2])
        duplicated["source_reference"]["line"] = 8
        self.manifest["source_entries"].append(duplicated)
        with self.assertRaisesMessage(RepairError, "one_logical_row"):
            select_manifest(self.manifest, sha256="b" * 64, lines=[7, 8])
