"""Sahib 2026-11-10: ``hide_college_journals_20261110`` — Kollec jurnalları passiv + undo; kollec olmayan toxunulmur."""

from __future__ import annotations

import datetime
import pathlib
import re
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.audit.models import AuditLog
from apps.organizations.models import OrgUnit
from apps.registrar import college_journals_hide_2026_11_10 as hide
from apps.registrar.models import CourseOffering, Enrollment, ScheduleSlot
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


def _counts(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith("twin_merge: ") and "mode=" not in line:
            out.update(pair.split("=", 1) for pair in line[len("twin_merge: ") :].split())
    return out


class WiringTest(SimpleTestCase):
    def test_workflow_wiring_and_summary_keys(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - hide_college_journals_20261110\n", text)
        self.assertRegex(text, r"\|hide_college_journals_20261110[|)]")
        self.assertIn('[ "$COMMAND" = "hide_college_journals_20261110" ]', text)
        pattern = re.search(r"grep -E '(\^\(twin_relocate[^']+)'", text).group(1)
        self.assertRegex(
            "twin_merge: college_groups=30 enrollments_dropped=1100 offerings_hidden=103 slots_parked=14 with_teacher=40",
            pattern,
        )
        self.assertRegex("twin_merge: undo_enrollments_restored=5 undo_offerings_reactivated=3", pattern)


class HideCollegeJournalsTest(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])

    def _call(self, *extra):
        out = StringIO()
        call_command(
            "hide_college_journals_20261110", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out
        )
        return _counts(out.getvalue())

    def _mark_college(self):
        with bypass_rls():
            group = OrgUnit.objects.get(pk=self.offering.group_id)
            group.settings = {**(group.settings or {}), "legacy": {"kollec_or_uni": "Kollec"}}
            group.save(update_fields=["settings"])

    def test_nothing_hidden_without_college_groups(self):
        counts = self._call("--apply")
        self.assertNotIn("offerings_hidden", counts)
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).is_active)

    def test_ancestor_named_college_marks_the_group(self):
        with bypass_rls():
            group = OrgUnit.objects.get(pk=self.offering.group_id)
            parent = OrgUnit.objects.get(pk=group.parent_id)
            OrgUnit.objects.filter(pk=parent.pk).update(name="Kollec")
            self.assertIn(str(group.pk), hide.college_group_ids(self.org))

    def test_dry_run_apply_idempotent_and_undo(self):
        self._mark_college()
        with bypass_rls():
            enrolled = Enrollment.objects.filter(offering=self.offering, status="enrolled").count()
            slot = ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.offering,
                weekday=4,
                start_time=datetime.time(13, 35),
                end_time=datetime.time(15, 5),
            )
            others = set(
                CourseOffering.objects.filter(organization=self.org, is_active=True)
                .exclude(group_id=self.offering.group_id)
                .values_list("pk", flat=True)
            )
        self.assertGreater(enrolled, 0)

        dry = self._call()
        self.assertIn("offerings_hidden", dry)
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).is_active)
            self.assertFalse(AuditLog.objects.filter(resource_type=hide.HIDDEN).exists())

        applied = self._call("--apply")
        self.assertGreaterEqual(int(applied["enrollments_dropped"]), enrolled)
        self.assertEqual(applied["slots_parked"], "1")
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.get(pk=self.offering.pk).is_active)
            self.assertEqual(Enrollment.objects.filter(offering=self.offering, status="enrolled").count(), 0)
            self.assertTrue(ScheduleSlot.objects.get(pk=slot.pk).is_parked)
            self.assertEqual(
                set(
                    CourseOffering.objects.filter(organization=self.org, is_active=True)
                    .exclude(group_id=self.offering.group_id)
                    .values_list("pk", flat=True)
                ),
                others,
            )

        again = self._call("--apply")
        self.assertNotIn("offerings_hidden", again)

        undone = self._call("--apply", "--undo")
        self.assertEqual(undone["undo_offerings_reactivated"], applied["offerings_hidden"])
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.offering.pk).is_active)
            self.assertEqual(Enrollment.objects.filter(offering=self.offering, status="enrolled").count(), enrolled)
            self.assertFalse(ScheduleSlot.objects.get(pk=slot.pk).is_parked)
