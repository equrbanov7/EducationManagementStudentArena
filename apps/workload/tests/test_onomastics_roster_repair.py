"""Migrated PG: exact five home students, ten additive links and protected history."""

import copy
import io
from contextlib import ExitStack
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, transaction
from django.test import TransactionTestCase, override_settings

from apps.registrar import reviewed_onomastics_roster as api
from apps.registrar.journal_shares import forget, journal_scope
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    GuestRosterDocument,
    JournalShare,
    Lesson,
    LessonMark,
    StudentAcademicRecord,
)
from apps.workload.services import onomastics_roster_repair as service
from apps.workload.services import onomastics_roster_state as state
from apps.workload.services import reviewed_kind_share_source as graph_spec
from apps.workload.services.reviewed_chair_contacts import retained_rights
from apps.workload.services.sbio235_state import RepairError
from apps.workload.services.scoped_snapshot.repair_contact_rights import sha
from apps.workload.tests import test_reviewed_chair_contacts as contact_fixture
from apps.workload.tests.factories import activate_member, make_org
from core.rls import reset_rls_context

User = get_user_model()


class OnomasticsRosterTests(TransactionTestCase):
    def setUp(self):
        contact_fixture.ReviewedChairContactsTests.setUpTestData.__func__(type(self))
        contact_fixture.ReviewedChairContactsTests.setUp(self)
        self.actor.set_active_organization_context(self.org)
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.addCleanup(reset_rls_context)
        self.case = copy.deepcopy(self.case)
        self.case["source"] = {"sha256": api.SOURCE_SHA}
        for row in self.case["rows"]:
            current = next(r for r in self.rows if str(r.pk) == row["id"])
            type(current).objects.filter(pk=current.pk).update(**row["new"])
            for pin in row["assignments"]:
                query = current.assignments.filter(pk=pin["id"])
                if pin["new"] is None:
                    query.delete()
                else:
                    query.update(**pin["new"])
        CourseOffering.objects.filter(pk__in=[o.pk for o in self.offerings]).update(
            instructor=self.new, lesson_hours=60
        )
        self.stack["program"].official_code = "6002006"
        self.stack["program"].save(update_fields=["official_code"])
        for syllabus in self.syllabi:
            type(syllabus).objects.filter(pk=syllabus.pk).update(plan_hours_override=self.case["plan_hours"])
            syllabus.versions.update(plan_hours=self.case["plan_hours"])
        self.shares, self.excluded = [], []
        roster = {}
        for index, offering in enumerate(self.offerings):
            offering.refresh_from_db()
            existing = list(offering.enrollments.all())
            historical = Lesson.objects.create(
                organization=self.org,
                offering=offering,
                date="2026-10-24",
                kind="seminar",
                hours=2,
                instructor=self.new,
            )
            LessonMark.objects.create(
                organization=self.org,
                lesson=historical,
                enrollment=existing[0],
                status="present",
                score=7,
                entered_by=self.new,
            )
            for number in range(28):
                student = User.objects.create_user(f"onom-existing-{index}-{number}")
                activate_member(self.org, student, "student", permissions=["grade.view"])
                existing.append(Enrollment.objects.create(organization=self.org, offering=offering, student=student))
            for teacher, kinds in ((self.new, ["lecture"]), (self.old, ["seminar"])):
                share = JournalShare.objects.create(
                    organization=self.org,
                    offering=offering,
                    teacher=teacher,
                    source="legacy",
                    kinds=kinds,
                    batch="preserve-original-batch",
                )
                share.enrollments.add(*existing)
                self.shares.append(share)
            for number in range(4 if index == 0 else 1):
                student = User.objects.create_user(f"onom-excluded-{index}-{number}")
                activate_member(self.org, student, "student", permissions=["grade.view"])
                record = StudentAcademicRecord.objects.create(
                    organization=self.org,
                    student=student,
                    group=offering.group,
                    program=self.stack["program"],
                    curriculum=Curriculum.objects.get(program=self.stack["program"]),
                    admission_year=2024,
                )
                enrollment = Enrollment.objects.create(organization=self.org, offering=offering, student=student)
                roster[str(enrollment.pk)] = {
                    "student_id": student.pk,
                    "record_id": str(record.pk),
                    "offering_id": str(offering.pk),
                    "group_id": str(offering.group_id),
                }
                self.excluded.append(enrollment)
        share_hashes = {str(s.pk): sha(JournalShare.objects.filter(pk=s.pk).values().get()) for s in self.shares}
        pins = {}
        for offering in self.offerings:
            shares = JournalShare.objects.filter(offering=offering)
            links = list(
                JournalShare.enrollments.through.objects.filter(journalshare__in=shares).order_by("pk").values()
            )
            selected = list(
                Enrollment.objects.filter(pk__in=[r["enrollment_id"] for r in links])
                .order_by("pk")
                .values(*retained_rights.ENROLLMENT_FIELDS)
            )
            pins[str(offering.pk)] = {
                "shares": {str(s.pk): share_hashes[str(s.pk)] for s in shares},
                "through_sha256": sha(links),
                "selected_enrollments_sha256": sha(selected),
            }
        replacements = [
            (api, "ORG", str(self.org.pk)),
            (api, "SHARES", share_hashes),
            (api, "ROSTER", roster),
            (api, "ORIGINAL_THROUGHS", {oid: pin["through_sha256"] for oid, pin in pins.items()}),
            (api, "OWNER", self.new.pk),
            (api, "PROGRAM_NAME", self.stack["program"].name),
            (api, "KINDS", {self.new.pk: ["lecture"], self.old.pk: ["seminar"]}),
            (api, "SUBJECT", str(self.stack["subject"].pk)),
            (api, "PERIOD", str(self.stack["period"].pk)),
            (state, "CASE", self.case),
            (state, "TEACHERS", (self.new.pk, self.old.pk)),
            (state, "ROOT_OFFERINGS", tuple(pins)),
            (retained_rights, "PINS", pins),
            (graph_spec, "ORG", str(self.org.pk)),
        ]
        for module, name, value in replacements:
            self.patches.enter_context(patch.object(module, name, value))

    def run_repair(self, **kwargs):
        return service.repair(organization=self.org, actor=self.actor, **kwargs)

    def apply(self):
        dry = self.run_repair()
        return self.run_repair(apply=True, expected_baseline=dry["baseline"])

    def test_append_repeat_undo_preserves_116_pks_source_cells_and_all_graph(self):
        before = state.capture(organization=self.org, actor=self.actor)
        old_links = state.links(before)
        scopes_before = {}
        for offering in self.offerings:
            for teacher in (self.new, self.old):
                forget(offering)
                scopes_before[(offering.pk, teacher.pk)] = journal_scope(teacher, offering).kinds
        applied = self.apply()
        self.assertEqual((applied["status"], applied["links"]), ("applied", 10))
        self.assertEqual(applied["owner_seminar_access_narrowed"], 1)
        after = state.capture(organization=self.org, actor=self.actor)
        self.assertEqual(len(state.links(after)), 126)
        self.assertEqual([r for r in state.links(after) if r["id"] in {x["id"] for x in old_links}], old_links)
        self.assertEqual(self.run_repair()["status"], "already_present")
        for offering in self.offerings:
            for teacher, kind in ((self.new, "lecture"), (self.old, "seminar")):
                forget(offering)
                scope = journal_scope(teacher, offering)
                if teacher == self.new:
                    # Full seminar coverage claims that kind from the owner's
                    # existing unclaimed-kind fallback; stored roles are unchanged.
                    self.assertIsNone(scopes_before[(offering.pk, teacher.pk)])
                    self.assertEqual(scope.kinds, frozenset(["lecture", "lab"]))
                    self.assertFalse(scope.allows_kind("seminar"))
                    owned_history = Lesson.objects.filter(offering=offering, kind="seminar", instructor=self.new)
                    self.assertTrue(owned_history.exists())
                    self.assertTrue(all(scope.allows_lesson(lesson) for lesson in owned_history))
                else:
                    self.assertEqual(scope.kinds, scopes_before[(offering.pk, teacher.pk)])
                self.assertIn(kind, scope.kinds)
                self.assertTrue(
                    {str(e.pk) for e in self.excluded if e.offering_id == offering.pk} <= scope.enrollment_ids
                )
                if teacher == self.old:
                    self.assertNotIn("lab", scope.kinds)
        undo = self.run_repair(undo=applied["receipt"])
        self.run_repair(undo=applied["receipt"], apply=True, expected_baseline=undo["baseline"])
        self.assertEqual(state.capture(organization=self.org, actor=self.actor), before)
        self.assertEqual(self.run_repair(undo=applied["receipt"])["status"], "already_undone")

    def test_numeric_through_pk_order_survives_digit_width_boundary(self):
        through = JournalShare.enrollments.through
        row = through.objects.order_by("pk").values().first()
        maximum = through.objects.order_by("-pk").values_list("pk", flat=True).first()
        sentinel = 10 ** (len(str(maximum)) + 2)
        through.objects.filter(pk=row["id"]).update(id=sentinel)
        oid = str(JournalShare.objects.get(pk=row["journalshare_id"]).offering_id)
        values = list(through.objects.filter(journalshare__offering_id=oid).order_by("pk").values())
        api.ORIGINAL_THROUGHS[oid] = sha(values)
        retained_rights.PINS[oid]["through_sha256"] = sha(values)
        original = set(through.objects.values_list("pk", flat=True))
        applied = self.apply()
        self.assertTrue(original <= set(through.objects.values_list("pk", flat=True)))
        undo = self.run_repair(undo=applied["receipt"])
        self.run_repair(undo=applied["receipt"], apply=True, expected_baseline=undo["baseline"])
        self.assertEqual(set(through.objects.values_list("pk", flat=True)), original)

    def test_old_contact_guard_holds_after_append_instead_of_overwriting(self):
        self.apply()
        with transaction.atomic(), self.assertRaisesRegex(RepairError, "selected_scope_changed"):
            retained_rights.validate(self.org, state.ROOT_OFFERINGS)
        self.assertEqual(JournalShare.enrollments.through.objects.count(), 126)

    def test_direct_public_append_refuses_changed_original_roster(self):
        links = list(
            JournalShare.enrollments.through.objects.filter(journalshare_id__in=api.SHARES).order_by("pk").values()
        )
        extra = self.excluded[0]
        self.shares[0].enrollments.add(extra)
        with self.assertRaises(ValidationError):
            api.append_reviewed_onomastics_roster(
                organization=self.org, actor=self.actor, source_sha256=api.SOURCE_SHA, expected_links=links
            )
        self.assertEqual(JournalShare.enrollments.through.objects.count(), 117)

    def test_foreign_actor_rejected_by_direct_public_api(self):
        other = make_org("onom-foreign")
        self.actor.set_active_organization_context(other)
        with self.assertRaises(ValidationError):
            api.append_reviewed_onomastics_roster(
                organization=self.org, actor=self.actor, source_sha256=api.SOURCE_SHA, expected_links=[]
            )
        with self.assertRaises(ValidationError):
            api.undo_reviewed_onomastics_roster(organization=self.org, actor=self.actor, created_links=[])
        self.assertEqual(JournalShare.enrollments.through.objects.count(), 116)

    def test_wrong_home_guest_status_program_or_source_share_refused(self):
        enrollment = self.excluded[0]
        record = StudentAcademicRecord.objects.get(student=enrollment.student, is_active=True)
        changes = [
            (StudentAcademicRecord, record.pk, {"status": "suspended"}),
            (StudentAcademicRecord, record.pk, {"is_active": False}),
            (type(self.stack["program"]), self.stack["program"].pk, {"official_code": "6002007"}),
            (Enrollment, enrollment.pk, {"source_group": self.groups[1]}),
            (Enrollment, enrollment.pk, {"status": "dropped"}),
            (Enrollment, enrollment.pk, {"kind": "retake"}),
            (JournalShare, self.shares[0].pk, {"source": "manual"}),
        ]
        for cls, pk, values in changes:
            with self.subTest(values=values), transaction.atomic():
                cls.objects.filter(pk=pk).update(**values)
                with self.assertRaises((RepairError, ValidationError)):
                    self.run_repair()
                transaction.set_rollback(True)
        self.assertEqual(JournalShare.enrollments.through.objects.count(), 116)
        Enrollment.objects.filter(pk=enrollment.pk).update(kind="elective")
        self.assertEqual(self.run_repair()["status"], "dry_run")

    def test_guest_document_provenance_is_not_mistaken_for_home_authority(self):
        GuestRosterDocument.objects.create(
            organization=self.org, enrollment=self.excluded[0], document="fixtures/no-file.pdf", uploaded_by=self.actor
        )
        with self.assertRaisesRegex(ValidationError, "guest_or_placement"):
            self.run_repair()
        self.assertEqual(JournalShare.enrollments.through.objects.count(), 116)

    def test_partial_load_or_uncorrected_owner_refuses(self):
        for section in ("half roster", self.groups[0].name):
            with transaction.atomic():
                self.rows[0].assignments.update(groups_note=section)
                with self.assertRaisesRegex(RepairError, "whole_source_group"):
                    self.run_repair()
                transaction.set_rollback(True)
        for row in self.rows:
            with transaction.atomic():
                type(row).objects.filter(pk=row.pk).update(total_hours=999)
                with self.assertRaises(RepairError):
                    self.run_repair()
                transaction.set_rollback(True)
        CourseOffering.objects.filter(pk=self.offerings[0].pk).update(lesson_hours=90)
        with self.assertRaises(ValidationError):
            self.run_repair()

    def test_baseline_drift_and_late_new_grades_block_undo(self):
        dry = self.run_repair()
        LessonMark.objects.all().update(score=8)
        with self.assertRaisesRegex(RepairError, "baseline_changed"):
            self.run_repair(apply=True, expected_baseline=dry["baseline"])
        applied = self.apply()
        original = LessonMark.objects.filter(lesson__offering=self.excluded[0].offering).first()
        LessonMark.objects.create(
            organization=self.org, enrollment=self.excluded[0], lesson=original.lesson, status="absent"
        )
        with self.assertRaisesRegex(RepairError, "undo_graph_changed_or_new_grades"):
            self.run_repair(undo=applied["receipt"])
        receipt = state.model("audit.AuditLog").objects.get(
            resource_type=state.RESOURCE, resource_id=applied["receipt"]
        )
        with self.assertRaisesRegex(ValidationError, "undo_new_grades"):
            api.undo_reviewed_onomastics_roster(
                organization=self.org, actor=self.actor, created_links=receipt.new_values["created_links"]
            )
        self.assertEqual(JournalShare.enrollments.through.objects.count(), 126)

    def test_creator_only_historical_seminar_that_would_be_hidden_holds(self):
        Lesson.objects.create(
            organization=self.org,
            offering=self.offerings[0],
            date="2026-10-27",
            kind="seminar",
            hours=2,
            instructor=None,
            created_by=self.new,
        )
        with self.assertRaisesRegex(RepairError, "owned_historical_seminar"):
            self.run_repair()
        self.assertEqual(JournalShare.enrollments.through.objects.count(), 116)

    def test_syllabus_plan_numeric_metadata_is_read_only_and_fractional_drift_rejected(self):
        syllabus = self.syllabi[0]
        type(syllabus).objects.filter(pk=syllabus.pk).update(
            plan_hours_override={"lecture": "30", "seminar": "30", "lab": 0}
        )
        self.assertEqual(self.run_repair()["status"], "dry_run")
        syllabus.refresh_from_db()
        self.assertEqual(syllabus.plan_hours_override, {"lecture": "30", "seminar": "30", "lab": 0})
        for plan in ({"lecture": 30.5, "seminar": 30}, {"lecture": 30, "seminar": 30, "lab": 1}):
            type(syllabus).objects.filter(pk=syllabus.pk).update(plan_hours_override=plan)
            with self.subTest(plan=plan), self.assertRaisesRegex(RepairError, "prior_contact_syllabus"):
                self.run_repair()

    def test_access_projection_rejects_unexpected_kind_roster_or_management_changes(self):
        before = state.capture(organization=self.org, actor=self.actor)["access"]
        projected = api.reviewed_onomastics_access_snapshot(organization=self.org, actor=self.actor, projected=True)
        state.validate_access(before, projected)
        oid = str(self.offerings[0].pk)
        for field, value in (
            ("kinds", ["lecture"]),
            ("active_roster", []),
            ("can_manage_scores", False),
            ("owned_seminar_readable", False),
        ):
            changed = copy.deepcopy(projected)
            changed[oid][str(self.new.pk)][field] = value
            with self.subTest(field=field), self.assertRaises(RepairError):
                state.validate_access(before, changed)

    def test_additional_kind_teacher_assignment_requires_separate_review(self):
        self.rows[1].assignments.update(hours=29)
        self.rows[1].assignments.create(organization=self.org, teacher=self.new, activity="seminar", hours=1)
        with self.assertRaisesRegex(RepairError, "exact_kind_teacher_hours"):
            self.run_repair()
        self.assertEqual(JournalShare.enrollments.through.objects.count(), 116)

    def test_atomic_second_offering_failure_rolls_back_first_links(self):
        dry = self.run_repair()
        original = state.capture
        calls = []

        def capture(**kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RepairError("injected_after_append")
            return original(**kwargs)

        with patch.object(state, "capture", side_effect=capture):
            with self.assertRaises(RepairError):
                self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(JournalShare.enrollments.through.objects.count(), 116)

    def test_command_real_readonly_rls_both_modes_no_writes(self):
        original = service.repair

        def verify(**kwargs):
            with connection.cursor() as cursor:
                cursor.execute("SHOW transaction_read_only")
                self.assertEqual(cursor.fetchone()[0], "on")
                cursor.execute("SET LOCAL ROLE rls_app_role")
                cursor.execute("SELECT current_setting('app.current_org_id',true)")
                self.assertEqual(cursor.fetchone()[0], str(self.org.pk))
            return original(**kwargs)

        for mode in (False, True):
            with self.subTest(mode=mode), override_settings(RLS_TRANSACTION_SCOPED=mode):
                output = io.StringIO()
                with patch("apps.workload.management.commands.repair_onomastics_roster.repair", side_effect=verify):
                    call_command(
                        "repair_onomastics_roster", actor=self.actor.username, org=self.org.slug, stdout=output
                    )
                self.assertIn("status=dry_run", output.getvalue())
                self.assertIn("owner_seminar_access_narrowed=1", output.getvalue())
                self.assertEqual(JournalShare.enrollments.through.objects.count(), 116)

    def test_command_apply_and_undo_nonbypass_both_modes(self):
        original = service.repair

        def verify(**kwargs):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE rls_app_role")
                cursor.execute("SELECT current_setting('app.current_org_id',true)")
                self.assertEqual(cursor.fetchone()[0], str(self.org.pk))
            return original(**kwargs)

        for mode in (False, True):
            with self.subTest(mode=mode), override_settings(RLS_TRANSACTION_SCOPED=mode):
                dry = self.run_repair()
                output = io.StringIO()
                with patch("apps.workload.management.commands.repair_onomastics_roster.repair", side_effect=verify):
                    call_command(
                        "repair_onomastics_roster",
                        actor=self.actor.username,
                        org=self.org.slug,
                        baseline=dry["baseline"],
                        apply=True,
                        stdout=output,
                    )
                receipt = next(
                    part.split("=", 1)[1] for part in output.getvalue().split() if part.startswith("receipt=")
                )
                undo = self.run_repair(undo=receipt)
                with patch("apps.workload.management.commands.repair_onomastics_roster.repair", side_effect=verify):
                    call_command(
                        "repair_onomastics_roster",
                        actor=self.actor.username,
                        org=self.org.slug,
                        baseline=undo["baseline"],
                        apply=True,
                        undo=receipt,
                        stdout=io.StringIO(),
                    )
                self.assertEqual(JournalShare.enrollments.through.objects.count(), 116)
