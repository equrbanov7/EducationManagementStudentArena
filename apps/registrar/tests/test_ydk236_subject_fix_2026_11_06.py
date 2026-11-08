"""Sahib 2026-11-06: QKU-2693 kartı «Ümumi xarici dil» olur; boş VoİP əkizləri əsl VoİP jurnalına birləşir."""

from __future__ import annotations

import pathlib
from collections import Counter
from unittest import mock

from apps.registrar import ydk236_subject_fix_2026_11_06 as fix
from apps.registrar.models import Subject
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class Ydk236SubjectFixTest(_GuestRosterBase):
    def test_card_is_renamed_once(self):
        with (
            mock.patch.object(fix, "SUBJECT", str(self.math.pk)),
            mock.patch.object(fix, "CHAIR", str(self.chair.pk)),
            mock.patch.object(fix, "TWIN_PAIRS", ()),
            mock.patch.object(fix, "SPRING_OFFERING", "00000000-0000-0000-0000-000000000000"),
            bypass_rls(),
        ):
            counts = Counter()
            fix.run(organization=self.org, actor=self.owner, counts=counts, apply=True)
            self.assertEqual((counts["subject_renamed"], counts["spring_missing"]), (1, 1))
            self.assertEqual(Subject.objects.get(pk=self.math.pk).name, "Ümumi xarici dil")
            again = Counter()
            fix.run(organization=self.org, actor=self.owner, counts=again, apply=True)
            self.assertEqual(again["subject_already_renamed"], 1)

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - fix_ydk236_subject_20261106\n", text)
        self.assertIn('[ "$COMMAND" = "fix_ydk236_subject_20261106" ]', text)
