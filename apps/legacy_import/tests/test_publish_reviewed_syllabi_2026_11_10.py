"""``publish_reviewed_syllabi_20261110`` — sabit qaralama id-ləri; yoxdursa heç nə yazılmır, kod sanitar, iş axını bağlı."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.legacy_import.management.commands import publish_reviewed_syllabi_20261110 as command_module
from apps.workload.tests.factories import make_org
from core.rls import bypass_rls


class PublishReviewedSyllabiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("prs")
            cls.actor = get_user_model().objects.create_superuser("prs_actor", "prs@qku.edu.az", "pw")

    def _call(self, **kwargs):
        out = StringIO()
        call_command("publish_reviewed_syllabi_20261110", org=self.org.slug, stdout=out, **kwargs)
        counts = {}
        for line in out.getvalue().splitlines():
            for part in line.split()[1:]:
                key, _sep, value = part.partition("=")
                counts[key] = value
        return counts

    def test_missing_versions_are_counted_not_written(self):
        counts = self._call(actor=self.actor.username, apply=True)
        self.assertEqual(counts["mode"], "apply")
        for key in command_module.VERSIONS.values():
            self.assertEqual(counts[f"{key}_missing"], "1")

    def test_non_superuser_actor_refused(self):
        with self.assertRaisesMessage(CommandError, "actor_must_be_active_superuser"):
            self._call(actor="nobody")

    def test_failure_code_is_sanitized(self):
        code = command_module.failure_code(ValueError("Səhv: X/Y"))
        self.assertRegex(code, r"^reviewed_publish_failed_[a-z0-9_]+$")
        self.assertLessEqual(len(code), 120)

    def test_workflow_wiring(self):
        text = Path(__file__).resolve().parents[3].joinpath(".github/workflows/prod-data-ops.yml").read_text()
        self.assertEqual(text.count("- publish_reviewed_syllabi_20261110"), 1)
        self.assertIn('[ "$COMMAND" = "publish_reviewed_syllabi_20261110" ]', text)
        self.assertIn("|reviewed_publish|", text)
