"""``add_legacy_guest_students_20261109`` — köhnə jurnalda iştirakı olan tələbə alt qrupdan jurnala (sahib 2026-11-09)."""

import json
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.registrar.models import Enrollment
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls

User = get_user_model()


class AddLegacyGuestStudentsCommandTests(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.actor = User.objects.create_superuser("lg_actor", "lg_actor@qku.edu.az", "pw")

    def _plan(self, items):
        path = Path(tempfile.mkdtemp()) / "plan.json"
        path.write_text(json.dumps({"format": "legacy-guests/1", "items": items}, ensure_ascii=False))
        return str(path)

    def _call(self, items, *, apply=False):
        out = StringIO()
        call_command(
            "add_legacy_guest_students_20261109",
            org=self.org.slug,
            actor=self.actor.username,
            file=self._plan(items),
            apply=apply,
            stdout=out,
        )
        counts = {}
        for line in out.getvalue().splitlines():
            for part in line.split()[1:]:
                key, _sep, value = part.partition("=")
                counts[key] = value
        return counts

    def _items(self):
        return [
            {
                "offering": str(self.offering.pk),
                "name": f"{self.guest.last_name} {self.guest.first_name}".strip() or "gr_guest",
                "reason": "Köhnə jurnal 4uHKOTrG3i",
            },
            {"offering": str(self.offering.pk), "fin": "ZZZ9999", "name": "Yoxdur Belə"},
            {"offering": "00000000-0000-0000-0000-000000000000", "name": "Kimsə Biri"},
        ]

    def test_dry_run_counts_without_writing(self):
        self._drop_own_history(self.guest)
        self.guest.first_name, self.guest.last_name = "Qonaq", "Tələbə"
        self.guest.save(update_fields=["first_name", "last_name"])
        counts = self._call(self._items())
        self.assertEqual(counts["mode"], "dry_run")
        self.assertEqual(counts["added"], "1")
        self.assertEqual(counts["skip_student_unresolved"], "1")
        self.assertEqual(counts["skip_offering_unknown"], "1")
        with bypass_rls():
            self.assertFalse(
                Enrollment.objects.filter(offering=self.offering, student=self.guest, status="enrolled").exists()
            )

    def test_apply_adds_once_and_refuses_active_own_journal(self):
        self._drop_own_history(self.guest)
        self.guest.first_name, self.guest.last_name = "Qonaq", "Tələbə"
        self.guest.save(update_fields=["first_name", "last_name"])
        # far_student öz Tarix jurnalında aktivdir → birləşmə edilmir, atlanır.
        self.far_student.first_name, self.far_student.last_name = "Uzaq", "Tələbə"
        self.far_student.save(update_fields=["first_name", "last_name"])
        items = self._items() + [{"offering": str(self.offering.pk), "name": "Tələbə Uzaq"}]
        counts = self._call(items, apply=True)
        self.assertEqual(counts["mode"], "apply")
        self.assertEqual(counts["added"], "1")
        self.assertEqual(counts["added_group"], "1")
        self.assertEqual(counts["skip_other_journal_active"], "1")
        with bypass_rls():
            enrollment = Enrollment.objects.get(offering=self.offering, student=self.guest)
            self.assertEqual((enrollment.status, enrollment.source_group_id), ("enrolled", self.group2.pk))
        again = self._call(items, apply=True)
        self.assertEqual(again.get("added", "0"), "0")
        self.assertEqual(again["skip_already_enrolled"], "1")

    def test_bad_plan_is_refused(self):
        path = Path(tempfile.mkdtemp()) / "plan.json"
        path.write_text(json.dumps({"format": "other/1", "items": []}))
        with self.assertRaises(CommandError):
            call_command(
                "add_legacy_guest_students_20261109", org=self.org.slug, actor=self.actor.username, file=str(path)
            )
