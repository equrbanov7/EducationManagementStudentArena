"""Köhnə sistemdə jurnal aparan müəllimin «Forma 7» bloku açılır (sahib 2026-10-26: «adına nə isə aparıbsa bloklama»).

* İşi olan köhnə jurnal (xana / dərs tarixi) + «Forma 7» bloku → rəsmi ``unblock_account`` ilə açılır.
* Əl ilə qoyulan blok (təhlükəsizlik …) və boş köhnə jurnal → bağlı qalır (``--include-empty`` boş jurnalı açır).
* Dry-run yazmır; stdout-a istifadəçi adı düşmür.
* Gələcək «Forma 7» yoxlaması bölünmüş jurnalın pay sahibini «cari jurnalı var» sayır (yenidən bloklanmır).
"""

from __future__ import annotations

import json
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.services.account_deletion import block_account
from apps.accounts.services.staff_placement.facts import teaching_user_ids
from apps.accounts.services.teacher_roster.apply import BLOCK_REASON_CODE, block_text
from apps.registrar.models import JournalShare
from core.rls import bypass_rls

from .people_fixture import PeopleFixture


class UnblockLegacyJournalTeachersTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()
        with bypass_rls():
            cls.fx.owner.is_superuser = True
            cls.fx.owner.save(update_fields=["is_superuser"])
            block_account(
                cls.fx.teacher_a,
                reason=block_text("roster-20261025-000000-ab12", "2026/2027"),
                reason_code=BLOCK_REASON_CODE,
            )
            block_account(cls.fx.teacher_b, reason="test bloku", reason_code="security")

    def _run(self, rows, *extra):
        out = StringIO()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"format": "legacy-teachers/1", "teachers": rows}, handle)
        call_command(
            "unblock_legacy_journal_teachers",
            "--org",
            self.fx.org.slug,
            "--actor",
            self.fx.owner.username,
            "--file",
            handle.name,
            *extra,
            stdout=out,
        )
        return out.getvalue()

    def _active(self, user):
        user.refresh_from_db()
        return user.is_active

    def test_dry_run_then_apply_only_roster_block_with_work(self):
        rows = [
            {"user": self.fx.teacher_a.pk, "journals": 2, "points": 40, "dates": 6},
            {"user": self.fx.teacher_b.pk, "journals": 1, "points": 10, "dates": 2},
        ]
        output = self._run(rows)
        self.assertIn("unblocked=1", output)
        self.assertIn("manual_block_kept=1", output)
        self.assertNotIn("ppl_", output)
        self.assertFalse(self._active(self.fx.teacher_a))
        self._run(rows, "--apply")
        self.assertTrue(self._active(self.fx.teacher_a))
        self.assertFalse(self._active(self.fx.teacher_b))

    def test_empty_journal_needs_flag(self):
        rows = [{"user": self.fx.teacher_a.pk, "journals": 1, "points": 0, "dates": 0}]
        self.assertIn("empty_journal_kept=1", self._run(rows, "--apply"))
        self.assertFalse(self._active(self.fx.teacher_a))
        self.assertIn("unblocked=1", self._run(rows, "--apply", "--include-empty"))
        self.assertTrue(self._active(self.fx.teacher_a))

    def test_share_holder_counts_as_teaching_now(self):
        offering = self.fx.offering_a
        with bypass_rls():
            JournalShare.objects.create(organization=self.fx.org, offering=offering, teacher=self.fx.teacher_b)
            ids = teaching_user_ids(self.fx.org, "2026/2027", [offering.period_id])
        self.assertIn(self.fx.teacher_b.pk, ids)
