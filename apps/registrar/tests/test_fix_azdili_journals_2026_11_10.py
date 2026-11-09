"""``fix_azdili_journals_20261110`` (sahib 2026-11-10): 236 M ADİAK paylarının siyahısı köhnə sistemin siyahısı ilə
ƏVƏZ olunur (əvvəlki fərqli siyahının üzərinə yazılır — ``apply_first_year_splits`` bunu ``_conflict`` sayırdı),
sahib dəyişibsə / ikinci müəllimin payı yoxdursa toxunulmur; boş əkiz cütü boş plan ilə heç nə etmir; stdout-da yalnız
saylar; idempotent; prod-data-ops-a qoşulub."""

from __future__ import annotations

import io
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from apps.registrar import first_year_splits_2026_11_07 as splits
from apps.registrar.management.commands import fix_azdili_journals_20261110 as command
from apps.registrar.models import JournalShare
from apps.registrar.tests.test_lab_groups_2026_11_06 import WORKFLOW, User, _LabWorld
from core.rls import bypass_rls


class FixAzdiliJournalsTest(_LabWorld, TestCase):
    def setUp(self):
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            self.second = User.objects.create_user("azj_second", "azj_second@x.test", "pw")
        self._member(self.second, "teacher", ["grade.input"])
        self.plan = {
            "lab": {},
            "shares": {
                "adiak_m": {
                    "offering": str(self.offering.pk),
                    "owner": self.teacher.pk,
                    "owner_rows": [str(self.e1.pk)],
                    "other_rows": [str(self.e2.pk)],
                }
            },
        }
        for patch in (
            mock.patch.object(splits, "plan", lambda: self.plan),
            mock.patch.object(command, "plan", lambda: self.plan),
            mock.patch.object(command, "SECOND_TEACHER", self.second.pk),
            mock.patch.object(command, "TWIN_PAIRS", ()),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        with bypass_rls():
            self.own = JournalShare.objects.create(
                organization=self.org, offering=self.offering, teacher=self.teacher, kinds=["seminar"]
            )
            self.other = JournalShare.objects.create(
                organization=self.org, offering=self.offering, teacher=self.second, kinds=["seminar"]
            )
            # əvvəlki (köhnə sistemə uyğun olmayan) siyahılar
            self.own.enrollments.set([self.e0, self.e1, self.e2])
            self.other.enrollments.set([self.e0, self.e2])

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "fix_azdili_journals_20261110", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out
        )
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, r"^lab_groups: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("lab_groups: ") :].split())
        return counts

    def test_dry_run_apply_idempotent(self):
        dry = self._call()
        self.assertEqual((dry["adiak_m_owner_replaced"], dry["adiak_m_other_replaced"]), ("1", "1"))
        with bypass_rls():
            self.assertEqual(self.own.enrollments.count(), 3)
        self._call("--apply")
        with bypass_rls():
            self.assertEqual(set(self.own.enrollments.all()), {self.e1})
            self.assertEqual(set(self.other.enrollments.all()), {self.e2})
        again = self._call("--apply")
        self.assertEqual((again["adiak_m_owner_already"], again["adiak_m_other_already"]), ("1", "1"))

    def test_guards(self):
        with bypass_rls():
            self.other.is_active = False
            self.other.save(update_fields=["is_active"])
        self.assertEqual(self._call("--apply")["adiak_m_share_missing_skipped"], "1")
        self.plan["shares"]["adiak_m"]["owner"] = self.second.pk
        self.assertEqual(self._call("--apply")["adiak_m_owner_changed_skipped"], "1")

    def test_failure_code_is_sanitized(self):
        self.assertRegex(command.failure_code(ValueError("Bad: x/y")), r"^[a-z0-9_]+$")

    def test_workflow_wiring(self):
        text = Path(WORKFLOW).read_text(encoding="utf-8")
        self.assertIn("          - fix_azdili_journals_20261110\n", text)
        self.assertIn('[ "$COMMAND" = "fix_azdili_journals_20261110" ]', text)
