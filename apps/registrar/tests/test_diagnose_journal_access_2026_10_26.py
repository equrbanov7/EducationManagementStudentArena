"""``diagnose_journal_access`` — «Yeni dərs» şərtləri ayrıca, yalnız oxu, ad çap olunmur (sahib 2026-10-26)."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.registrar.tests.subgroup_base import SubgroupFixture


class DiagnoseJournalAccessTest(SubgroupFixture, TestCase):
    PREFIX = "dja"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()

    def _run(self, *extra):
        out = StringIO()
        call_command(
            "diagnose_journal_access", "--org", self.org.slug, "--offering", str(self.physics_g1.pk), *extra, stdout=out
        )
        return out.getvalue()

    def test_instructor_can_edit(self):
        text = self._run()
        self.assertIn("user_is_instructor=yes", text)
        self.assertIn("can_edit=yes", text)
        self.assertNotIn(self.teacher.username, text)

    def test_other_user_cannot(self):
        text = self._run("--user", self.plain.username)
        self.assertIn("user_is_instructor=no", text)
        self.assertIn("can_edit=no", text)
