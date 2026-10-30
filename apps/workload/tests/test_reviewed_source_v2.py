"""Reviewed handovers never rewrite historical authors, rosters or syllabus."""

import uuid
from unittest.mock import patch

from django.db.models import Count, Sum
from django.test import TestCase, override_settings

from apps.organizations.models import Membership
from apps.registrar.models import JournalShare, Lesson, Subject, TeachingHandover
from apps.workload.models import TeacherAssignment, TeachingTaskRow
from apps.workload.services import reviewed_batch as repair
from apps.workload.services import reviewed_batch_state as state
from apps.workload.services.reviewed_batch_manifest import ORG, YEAR, select_manifest
from apps.workload.services.sbio235_state import RepairError, records
from apps.workload.services.scoped_snapshot.data import offering_counts
from core.rls import apply_rls_request_context, reset_rls_context

from .test_reviewed_source_batch import source_entry


@override_settings(RLS_TRANSACTION_SCOPED=True)
class ReviewedV2Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .test_cavid_source_batch import CavidSourceBatchTests

        CavidSourceBatchTests.setUpTestData.__func__(cls)

    def setUp(self):
        apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
        self.manifest = {
            "format": "reviewed-workload-source/2",
            "organization_id": ORG,
            "academic_year": YEAR,
            "chair_id": str(self.finance.pk),
            "source_entries": [],
        }

    def tearDown(self):
        reset_rls_context()

    def plan(self, *entries):
        self.manifest["source_entries"] = list(entries)
        return select_manifest(self.manifest, sha256="c" * 64, lines=[e["source_reference"]["line"] for e in entries])

    def execute(self, plan, *, apply=False, **kwargs):
        return repair.run(plan=plan, organization=self.org, user=self.admin, apply=apply, **kwargs)

    def apply(self, plan):
        preview = self.execute(plan)
        return self.execute(plan, apply=True, expected_baseline=preview["baseline"])

    def handover(self, *, restore=False, legacy=False, retain=False):
        offering, row, task, group, subject = (
            (self.a, None, self.ta, self.ga, self.sa) if restore else (self.b, self.rb, self.tb, self.gb, self.sb)
        )
        target, previous = (self.previous, self.teacher) if restore else (self.teacher, self.previous)
        hours = {"lecture": 10, "seminar": 5} if legacy else {"lecture": 30, "seminar": 15}
        entry = source_entry(
            line=30,
            subject=subject,
            group=group,
            task=task,
            teacher=target,
            hours=hours,
            mode="reviewed_handover_missing_row" if restore else "reviewed_handover_existing_row",
            offering=offering,
            row=row,
        )
        policy = {
            "handover": {
                "from_instructor_id": previous.pk,
                "to_instructor_id": target.pk,
                "offering_ids": [str(offering.pk)],
            },
            "join_chair": {"teacher_id": target.pk, "chair_id": str(task.chair_id)},
        }
        if legacy:
            entry["desired_contacts"]["seminar"] = 0
            entry["source_reference"]["values"]["fall_seminar"] = 0
            entry["expected_assignments"] = [a for a in entry["expected_assignments"] if a["activity"] == "lecture"]
            policy["legacy_history"] = [
                {
                    "offering_id": str(offering.pk),
                    "lesson_hours": offering.lesson_hours,
                    "lessons": offering.lessons.count(),
                    "marks": sum(lesson.marks.count() for lesson in offering.lessons.all()),
                    "enrollments": offering.enrollments.count(),
                    "retain_capacity": retain,
                    "fingerprints": {
                        key: val for key, val in offering_counts([offering.pk])[0].items() if key.endswith("_md5")
                    },
                    "syllabi": [
                        {
                            "id": str(syllabus.pk),
                            "author_id": syllabus.author_id,
                            "current_version_id": (
                                str(syllabus.current_version_id) if syllabus.current_version_id else None
                            ),
                            "approved_version_id": (
                                str(syllabus.approved_version_id) if syllabus.approved_version_id else None
                            ),
                        }
                        for syllabus in offering.syllabi.all()
                    ],
                    "recorded": list(
                        offering.lessons.values("kind", "instructor_id").annotate(hours=Sum("hours"), count=Count("pk"))
                    ),
                }
            ]
        entry["reviewed_policy"] = policy
        return entry

    def new_subject(self):
        identity = {
            "id": str(uuid.uuid4()),
            "code": "QKU-SOURCE-EXACT",
            "name": "Maliyyə auditi",
            "chair_unit_id": str(self.finance.pk),
            "ects": 6,
            "kind": "core",
        }
        entry = source_entry(
            line=22,
            subject=self.sa,
            group=self.ga,
            task=self.ta,
            teacher=self.teacher,
            hours={"lecture": 30, "seminar": 15},
            mode="reviewed_catalogue_new_exact",
            offering=self.a,
        )
        entry["selected_subject_id"] = identity["id"]
        entry["subject_candidates"] = [{key: identity[key] for key in ("id", "name", "code")}]
        entry["source_reference"]["values"]["subject"] = identity["name"]
        entry["source_reference"]["values"]["credits"] = identity["ects"]
        entry["existing_journals"] = []
        entry["reviewed_policy"] = {"subject_create": identity}
        return entry

    def test_handover_keeps_content_assignment_ids_authors_and_primary_chair(self):
        entry = self.handover()
        before = records(self.b.lessons.all())
        old_assignments = set(self.rb.assignments.values_list("pk", flat=True))
        primary = records(Membership.objects.filter(is_primary=True))
        plan = self.plan(entry)
        result = self.apply(plan)
        self.b.refresh_from_db()
        self.assertEqual(self.b.instructor_id, self.teacher.pk)
        self.assertEqual(records(self.b.lessons.all()), before)
        self.assertEqual(
            set(self.rb.assignments.values_list("pk", flat=True)),
            old_assignments | set(self.rb.assignments.filter(activity="seminar").values_list("pk", flat=True)),
        )
        self.assertEqual(records(Membership.objects.filter(is_primary=True)), primary)
        self.assertEqual(TeachingHandover.objects.get(offering=self.b).from_instructor_id, self.previous.pk)
        self.assertEqual(self.execute(plan)["already_done"], 1)
        current = self.execute(plan)["baseline"]
        self.execute(plan, undo=result["batch"], expected_baseline=current, apply=True)
        self.b.refresh_from_db()
        self.assertEqual(self.b.instructor_id, self.previous.pk)
        self.assertEqual(set(self.rb.assignments.values_list("pk", flat=True)), old_assignments)

    def test_legacy_null_teacher_seminar_and_capacity_survive_smaller_current_plan(self):
        Lesson.objects.create(
            organization=self.org, offering=self.a, date="2026-10-20", kind="seminar", hours=2, instructor=None
        )
        entry = self.handover(restore=True, legacy=True, retain=True)
        before = state.snapshot(self.plan(entry))
        result = self.apply(self.plan(entry))
        self.a.refresh_from_db()
        row = TeachingTaskRow.objects.get(subject=self.sa, period=self.period, groups=self.ga)
        self.assertEqual((row.lecture_total, row.seminar_total), (10, 0))
        self.assertEqual(self.a.lesson_hours, before["offerings"][0]["lesson_hours"])
        self.assertTrue(self.a.lessons.filter(instructor__isnull=True, kind="seminar").exists())
        self.assertEqual(result["created_journals"], 0)

    def test_legacy_null_syllabus_author_is_preserved_and_idempotent(self):
        syllabus = self.a.syllabi.get()
        syllabus.author_id = None
        syllabus.save(update_fields=["author"])
        versions = (syllabus.current_version_id, syllabus.approved_version_id)
        entry = self.handover(restore=True, legacy=True, retain=True)
        self.assertIsNone(entry["reviewed_policy"]["legacy_history"][0]["syllabi"][0]["author_id"])
        plan = self.plan(entry)
        self.apply(plan)
        syllabus.refresh_from_db()
        self.assertIsNone(syllabus.author_id)
        self.assertEqual((syllabus.current_version_id, syllabus.approved_version_id), versions)
        self.assertEqual(self.execute(plan)["already_done"], 1)

    def test_reviewed_null_syllabus_author_cannot_hide_an_existing_real_author(self):
        entry = self.handover(restore=True, legacy=True, retain=True)
        entry["reviewed_policy"]["legacy_history"][0]["syllabi"][0]["author_id"] = None
        plan = self.plan(entry)
        before = state.snapshot(plan)
        with self.assertRaisesMessage(RepairError, "legacy_syllabus_author_version_changed"):
            self.execute(plan)
        self.assertEqual(state.snapshot(plan), before)

    def test_reviewed_non_null_syllabus_author_still_requires_positive_integer(self):
        entry = self.handover(restore=True, legacy=True, retain=True)
        for invalid in (0, -1, True, "1"):
            with self.subTest(author=invalid):
                entry["reviewed_policy"]["legacy_history"][0]["syllabi"][0]["author_id"] = invalid
                with self.assertRaisesMessage(RepairError, "manifest_integer_invalid"):
                    self.plan(entry)

    def test_removed_old_seminar_assignment_and_author_history_are_reversible(self):
        self.rb.seminar_plan = self.rb.seminar_total = 10
        self.rb.save(update_fields=["seminar_plan", "seminar_total"])
        old = TeacherAssignment.objects.create(
            organization=self.org, row=self.rb, teacher=self.previous, activity="seminar", hours=10
        )
        lesson = Lesson.objects.create(
            organization=self.org, offering=self.b, date="2026-10-20", kind="seminar", hours=2, instructor=None
        )
        entry = self.handover(legacy=True)
        plan = self.plan(entry)
        result = self.apply(plan)
        self.assertFalse(TeacherAssignment.objects.filter(pk=old.pk).exists())
        lesson.refresh_from_db()
        self.assertIsNone(lesson.instructor_id)
        current = self.execute(plan)["baseline"]
        self.execute(plan, undo=result["batch"], expected_baseline=current, apply=True)
        restored = TeacherAssignment.objects.get(pk=old.pk)
        self.assertEqual((restored.teacher_id, restored.hours, restored.activity), (self.previous.pk, 10, "seminar"))
        lesson.refresh_from_db()
        self.assertIsNone(lesson.instructor_id)

    def test_changed_legacy_count_or_null_authorship_refuses_and_rolls_back(self):
        entry = self.handover(restore=True, legacy=True)
        entry["reviewed_policy"]["legacy_history"][0]["marks"] += 1
        plan = self.plan(entry)
        before = state.snapshot(plan)
        with self.assertRaisesMessage(RepairError, "legacy_content_counts"):
            self.execute(plan)
        self.assertEqual(state.snapshot(plan), before)

    def test_new_exact_subject_is_dry_rolled_back_then_created_once_and_undone(self):
        entry = self.new_subject()
        plan = self.plan(entry)
        self.execute(plan)
        self.assertFalse(Subject.objects.filter(pk=entry["selected_subject_id"]).exists())
        result = self.apply(plan)
        subject = Subject.objects.get(pk=entry["selected_subject_id"])
        self.assertEqual((subject.name, subject.ects), ("Maliyyə auditi", 6))
        self.assertEqual(subject.offerings.count(), 1)
        current = self.execute(plan)["baseline"]
        self.execute(plan, undo=result["batch"], expected_baseline=current, apply=True)
        self.assertFalse(Subject.objects.filter(pk=subject.pk).exists())

    def test_catalogue_exact_title_even_with_another_code_refuses_new_identity(self):
        entry = self.new_subject()
        Subject.objects.create(organization=self.org, code="OTHER", name="Maliyyə auditi")
        plan = self.plan(entry)
        with self.assertRaisesMessage(Exception, "exact_title_already_exists"):
            self.execute(plan)
        self.assertFalse(Subject.objects.filter(pk=entry["selected_subject_id"]).exists())

    def test_new_subject_title_cannot_be_a_nearby_different_concept(self):
        entry = self.new_subject()
        entry["source_reference"]["values"]["subject"] = "Maliyyə nəzarəti və auditi"
        with self.assertRaisesMessage(RepairError, "exact_source_title"):
            self.plan(entry)

    def test_v1_file_cannot_enable_v2_exception(self):
        entry = self.new_subject()
        self.manifest["format"] = "reviewed-workload-source/1"
        with self.assertRaisesMessage(RepairError, "v2_policy_required"):
            self.plan(entry)

    def test_mismatched_offering_or_target_teacher_refuses_manifest(self):
        entry = self.handover()
        entry["reviewed_policy"]["handover"]["offering_ids"] = [str(self.a.pk)]
        with self.assertRaisesMessage(RepairError, "exact_journal_identity"):
            self.plan(entry)

    def test_post_handover_failure_rolls_back_access_and_history(self):
        plan = self.plan(self.handover())
        before = state.snapshot(plan)
        with patch("apps.workload.services.reviewed_batch.guards.verify_after", side_effect=RepairError("late")):
            with self.assertRaisesMessage(RepairError, "late"):
                self.execute(plan)
        self.assertEqual(state.snapshot(plan), before)
        self.assertFalse(TeachingHandover.objects.exists())

    def test_reviewed_hourly_flag_patch_and_undo_preserve_assignment_identity(self):
        entry = source_entry(
            line=92,
            subject=self.sb,
            group=self.gb,
            task=self.tb,
            teacher=self.previous,
            hours={"lecture": 45},
            mode="existing_course_patch_owner_preserved",
            offering=self.b,
            row=self.rb,
        )
        entry["source_reference"]["values"]["hourly"] = "bəli"
        entry["expected_assignments"][0]["is_hourly_paid"] = True
        old_ids = set(self.rb.assignments.values_list("pk", flat=True))
        plan = self.plan(entry)
        result = self.apply(plan)
        self.assertTrue(self.rb.assignments.get(activity="lecture").is_hourly_paid)
        self.assertEqual(set(self.rb.assignments.values_list("pk", flat=True)), old_ids)
        self.execute(plan, undo=result["batch"], expected_baseline=self.execute(plan)["baseline"], apply=True)
        self.assertFalse(self.rb.assignments.get(activity="lecture").is_hourly_paid)
        self.assertEqual(set(self.rb.assignments.values_list("pk", flat=True)), old_ids)

    def test_unreviewed_manual_share_change_rolls_back(self):
        plan = self.plan(self.handover())
        # A manual observer's grant is unrelated to either handover party.
        observer = type(self.teacher).objects.create_user(username="observer")
        share = JournalShare.objects.create(
            organization=self.org, offering=self.b, teacher=observer, source="manual", kinds=["lecture"]
        )
        before = state.snapshot(plan)
        original = repair.actions.forward

        def tamper(*args, **kwargs):
            result = original(*args, **kwargs)
            JournalShare.objects.filter(pk=share.pk).update(is_active=False)
            return result

        with patch("apps.workload.services.reviewed_batch.actions.forward", side_effect=tamper):
            with self.assertRaises(RepairError):
                self.execute(plan)
        self.assertEqual(state.snapshot(plan), before)
