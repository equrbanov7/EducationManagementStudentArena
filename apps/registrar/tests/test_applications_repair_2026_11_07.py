"""RİM 2026-11-07: ``repair_applications_20261107`` — MR-247/253 passiv jurnallar, MR-245 fənn düzəlişi + undo."""

from __future__ import annotations

import datetime
import pathlib
import re
import uuid
from collections import Counter
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.audit.models import AuditLog
from apps.registrar import applications_repair_2026_11_07 as repair
from apps.registrar.models import CourseOffering, Enrollment, Lesson, ScheduleSlot
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _counts(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith("twin_merge: ") and "mode=" not in line:
            out.update(pair.split("=", 1) for pair in line[len("twin_merge: ") :].split())
    return out


class SpecTest(SimpleTestCase):
    def test_spec_is_ids_only_with_counter_safe_keys(self):
        for spec in repair.DEACTIVATIONS:
            self.assertRegex(spec["key"], r"^[a-z_]+$")
            for field in ("offering", "subject", "group"):
                self.assertRegex(spec[field], _UUID)
            self.assertIn(spec["instructor"], (repair.REYHAN, repair.GOVHAR))
        self.assertEqual(len({spec["offering"] for spec in repair.DEACTIVATIONS}), 3)
        for field in ("offering", "group", "row", "wrong", "right"):
            self.assertRegex(repair.SUBJECT_FIX[field], _UUID)
        self.assertNotEqual(repair.SUBJECT_FIX["wrong"], repair.SUBJECT_FIX["right"])

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - repair_applications_20261107\n", text)
        self.assertIn("            repair_applications_20261107)\n", text)
        self.assertIn('[ "$COMMAND" = "repair_applications_20261107" ]', text)
        pattern = re.search(r"grep -E '(\^\(twin_relocate[^']+)'", text).group(1)
        self.assertRegex(
            "twin_merge: ecology_deactivated=1 enrollments_dropped=29 offerings_deactivated=3 si_merge_applied=1 "
            "subject_changes=2 subject_offering_subject_changed=1",
            pattern,
        )
        self.assertRegex("twin_merge: undo_offerings_reactivated=3 undo_subject_row_subject_changed=1", pattern)


class _Base(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])

    def setUp(self):
        offering = self.offering
        spec = {
            "key": "psy",
            "offering": str(offering.pk),
            "subject": str(offering.subject_id),
            "group": str(offering.group_id),
            "instructor": offering.instructor_id,
            "reason": "test",
        }
        self.spec = spec
        patches = [
            mock.patch.object(repair, "PERIOD", str(self.period.pk)),
            mock.patch.object(repair, "DEACTIVATIONS", (spec,)),
            mock.patch.object(repair, "SI2_MERGED_SOURCE", str(uuid.uuid4())),
            mock.patch.object(repair, "SI2_TARGET", str(uuid.uuid4())),
            mock.patch.dict(repair.SUBJECT_FIX, {"offering": str(uuid.uuid4())}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def _call(self, *extra):
        out = StringIO()
        call_command(
            "repair_applications_20261107", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out
        )
        return _counts(out.getvalue())


class DeactivateTest(_Base):
    def test_dry_run_apply_idempotent_and_undo(self):
        with bypass_rls():
            enrolled = Enrollment.objects.filter(offering=self.offering, status="enrolled").count()
            slot = ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.offering,
                weekday=4,
                start_time=datetime.time(13, 35),
                end_time=datetime.time(15, 5),
            )
        self.assertGreater(enrolled, 0)

        dry = self._call()
        self.assertEqual((dry["psy_deactivated"], dry["enrollments_dropped"]), ("1", str(enrolled)))
        self.assertEqual((dry["slots_parked"], dry["si_merge_pending"], dry["subject_offering_missing"]), ("1",) * 3)
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).is_active)

        self._call("--apply")
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.get(pk=self.offering.pk).is_active)
            self.assertFalse(Enrollment.objects.filter(offering=self.offering, status="enrolled").exists())
            slot.refresh_from_db()
            self.assertTrue(slot.is_parked)
            self.assertEqual(AuditLog.objects.filter(resource_type=repair.DEACTIVATED).count(), 1)
        self.assertEqual(self._call("--apply")["psy_already_inactive"], "1")

        self.assertEqual(self._call("--undo")["undo_offerings_reactivated"], "1")  # dry-run undo
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.get(pk=self.offering.pk).is_active)
        undone = self._call("--undo", "--apply")
        self.assertEqual(
            (undone["undo_offerings_reactivated"], undone["undo_enrollments_restored"], undone["undo_slots_unparked"]),
            ("1", str(enrolled), "1"),
        )
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).is_active)
            self.assertEqual(Enrollment.objects.filter(offering=self.offering, status="enrolled").count(), enrolled)
            slot.refresh_from_db()
            self.assertFalse(slot.is_parked)
        self.assertEqual(self._call("--undo", "--apply")["undo_already"], "1")

    def test_changed_owner_writes_nothing(self):
        with mock.patch.dict(self.spec, {"instructor": self.coordinator.pk}):
            counts = self._call("--apply")
        self.assertEqual(counts["psy_state_changed_skipped"], "1")
        self.assertNotIn("offerings_deactivated", counts)
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).is_active)

    def test_journal_used_in_new_system_is_kept(self):
        with bypass_rls():
            Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=datetime.date(2025, 10, 15),
                kind="seminar",
                created_by=self.teacher,
            )
        self.assertEqual(self._call("--apply")["psy_in_use_skipped"], "1")
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).is_active)

    def test_si2_merge_is_only_checked(self):
        with bypass_rls():
            source = self.other_offering
            CourseOffering.objects.filter(pk=source.pk).update(is_active=False)
        with (
            mock.patch.object(repair, "SI2_MERGED_SOURCE", str(source.pk)),
            mock.patch.object(repair, "SI2_TARGET", str(self.offering.pk)),
            bypass_rls(),
        ):
            counts = Counter()
            repair.check_si2_merge(organization=self.org, counts=counts)
        self.assertEqual(counts, Counter({"si_merge_applied": 1}))


class SubjectFixTest(_Base):
    def setUp(self):
        super().setUp()
        patch = mock.patch.dict(
            repair.SUBJECT_FIX,
            {
                "offering": str(self.offering.pk),
                "group": str(self.offering.group_id),
                "row": str(uuid.uuid4()),
                "wrong": str(self.history.pk),
                "right": str(self.math.pk),
                "instructor": self.offering.instructor_id,
            },
        )
        patch.start()
        self.addCleanup(patch.stop)

    def _fix(self, side_effect):
        counts = Counter()
        with mock.patch.object(repair, "call_command", side_effect=side_effect) as command, bypass_rls():
            repair.fix_subject(organization=self.org, actor=self.owner, counts=counts, apply=True)
        return counts, command

    def test_delegates_to_fix_offering_subject_with_pinned_ids(self):
        def fake(name, *args, stdout):
            stdout.write(
                "offering_subject_fix: mode=apply\noffering_subject_fix: changes=2 offering_subject_changed=1\n"
            )

        counts, command = self._fix(fake)
        self.assertEqual((counts["subject_changes"], counts["subject_offering_subject_changed"]), (2, 1))
        name, *args = command.call_args.args
        self.assertEqual(name, "fix_offering_subject")
        self.assertIn(f"--subject={self.math.pk}", args)
        self.assertIn(f"--offering={self.offering.pk}", args)
        self.assertIn("--apply", args)

    def test_refusal_is_counted_not_raised(self):
        counts, _ = self._fix(CommandError("target_offering_exists"))
        self.assertEqual((counts["subject_refused"], counts["subject_refused_target_offering_exists"]), (1, 1))

    def test_already_fixed_and_foreign_subject_skip(self):
        with mock.patch.dict(repair.SUBJECT_FIX, {"right": str(self.history.pk), "wrong": str(self.math.pk)}):
            counts, command = self._fix(None)
        self.assertEqual(counts["subject_already_fixed"], 1)
        command.assert_not_called()
        with mock.patch.dict(repair.SUBJECT_FIX, {"wrong": str(uuid.uuid4())}):
            counts, command = self._fix(None)
        self.assertEqual(counts["subject_state_changed_skipped"], 1)
        command.assert_not_called()
