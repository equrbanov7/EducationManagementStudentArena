"""Plan qurucuları (sahib 2026-10-27): ``journal-shares/1`` (paylar + yanlış səviyyə çıxarışları, «(pre-intermadiate)»
də səviyyədir), ``level-merge/1`` (bölünmüş səviyyə jurnalının evi), ``chair_journal_health`` (müəllim üzrə saylar).

Köhnə sistemin jurnalları birbaşa :class:`LegacyJournal` kimi verilir (paketin həlli ``legacy_delta_apply`` testlərində
yoxlanılır); hədəf — :class:`LevelFixture` (bax ``apps/registrar/tests/level_fixture.py``).
"""

from __future__ import annotations

import json
import os
import tempfile
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.legacy_import.services.chair_journal_health import COLUMNS, ChairHealth, write_xlsx
from apps.legacy_import.services.delta.bundle import SECTIONS, write_bundle
from apps.legacy_import.services.journal_share_plan import SharePlan, level_classes
from apps.legacy_import.services.level_journal_index import LegacyIndex, LegacyJournal
from apps.legacy_import.services.level_merge_plan import LevelMergePlan
from apps.registrar.models import JournalShare, JournalShareSource
from apps.registrar.tests.level_fixture import D, LevelFixture
from core.rls import bypass_rls


class _Base(LevelFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.build_levels()

    def _journals(self):
        slots = {(D(2025, 10, 7), "10:10"): "seminar", (D(2025, 10, 14), "10:10"): None}
        return [
            LegacyJournal(
                legacy_id=1,
                uniqid="J1",
                subject_id=self.level.pk,
                subject_name=self.level.name,
                teacher_id=self.t.pk,
                students=[(11, self.host.pk), (12, self.student.pk)],
                slots=slots,
                points={11: 3, 12: 2},
            ),
            LegacyJournal(
                legacy_id=2,
                uniqid="J2",
                subject_id=self.level.pk,
                subject_name=self.level.name,
                teacher_id=self.z.pk,
                students=[(13, self.s3.pk)],
                points={13: 1},
            ),
            LegacyJournal(
                legacy_id=3,
                uniqid="J3",
                subject_id=self.level2.pk,
                subject_name=self.level2.name,
                teacher_id=self.z.pk,
                students=[(14, self.s4.pk)],
            ),
        ]

    def _index(self):
        with bypass_rls():
            return LegacyIndex(organization=self.org, bundle=None, period=self.period, journals=self._journals())


class SharePlanTest(_Base):
    def test_shares_and_wrong_level_drops(self):
        with bypass_rls():
            self.lesson(self.lvl_b, D(2025, 10, 7), kind="lab")
            index = self._index()
            classes = level_classes(index)
            plan_builder = SharePlan(index, deactivate=[(str(self.lvl_c.pk), self.t.pk)])
            plan = plan_builder.build()
        # «(pre-intermadiate)» yazı xətası olan fənn də səviyyədir (s4 L2-də köhnə siyahıdadır).
        self.assertEqual(classes[self.e_s4_c.pk], "covered")
        self.assertEqual(classes[self.e_s4.pk], "wrong_level")
        self.assertEqual(classes[self.e_s5.pk], "unlisted")
        self.assertEqual(plan["format"], "journal-shares/1")
        self.assertEqual(plan["drop_enrollments"], [str(self.e_s4.pk)])
        rows = {(row["offering"], row["teacher"]): row for row in plan["shares"]}
        t_row = rows[(str(self.lvl_b.pk), self.t.pk)]
        self.assertEqual((t_row["enrollments"], t_row["is_owner"]), ([str(self.e_student.pk)], False))
        self.assertEqual(t_row["kinds"], ["lab"], "növ yeni sistemin eyni tarix + saat dərsindən")
        self.assertTrue(rows[(str(self.lvl_b.pk), self.z.pk)]["is_owner"])
        self.assertNotIn((str(self.lvl_a.pk), self.t.pk), rows, "yalnız sahibin jurnalı — pay yazılmır")
        self.assertEqual(
            rows[(str(self.lvl_c.pk), self.t.pk)],
            {"offering": str(self.lvl_c.pk), "teacher": self.t.pk, "active": False},
        )
        self.assertEqual(plan_builder.counts["wrong_level"], 1)
        self.assertEqual(plan_builder.counts["level_unlisted"], 1)

    def test_data_bearing_wrong_level_row_is_not_dropped(self):
        with bypass_rls():
            self.mark(self.lesson(self.lvl_b, D(2025, 10, 7)), self.e_s4, score=5)
            plan_builder = SharePlan(self._index())
            plan = plan_builder.build()
        self.assertEqual(plan["drop_enrollments"], [])
        self.assertEqual(plan_builder.counts["wrong_level_with_data"], 1)

    def test_owner_without_legacy_students_gets_unlisted_only_share(self):
        with bypass_rls():
            journals = [entry for entry in self._journals() if entry.legacy_id != 2]
            index = LegacyIndex(organization=self.org, bundle=None, period=self.period, journals=journals)
            plan = SharePlan(index).build()
        rows = {(row["offering"], row["teacher"]): row for row in plan["shares"]}
        owner_row = rows[(str(self.lvl_b.pk), self.z.pk)]
        self.assertEqual(set(owner_row["enrollments"]), {str(self.e_s3.pk), str(self.e_s5.pk)})


class LevelMergePlanTest(_Base):
    def test_split_journal_gets_owned_host(self):
        with bypass_rls():
            plan_builder = LevelMergePlan(self._index())
            plan = plan_builder.build()
        self.assertEqual(plan["format"], "level-merge/1")
        self.assertEqual(len(plan["journals"]), 1)
        item = plan["journals"][0]
        self.assertEqual(
            (item["legacy_journal"], item["teacher"], item["host"], item["via"]),
            (1, self.t.pk, str(self.lvl_a.pk), "owner"),
        )
        self.assertEqual(item["moves"], [{"enrollment": str(self.e_student.pk), "student": self.student.pk}])
        self.assertEqual(plan_builder.counts["level_split"], 1)
        self.assertEqual(plan_builder.counts["level_single_offering"], 2)

    def test_no_owned_host_is_counted_unless_share_mode(self):
        with bypass_rls():
            self.lvl_a.instructor = self.z
            self.lvl_a.save(update_fields=["instructor"])
            strict = LevelMergePlan(self._index())
            self.assertEqual(strict.build()["journals"], [])
            loose = LevelMergePlan(self._index(), host_via_share=True).build()
        self.assertEqual(strict.counts["host_none_owned"], 1)
        self.assertEqual(loose["journals"][0]["via"], "share")


class ChairHealthTest(_Base):
    def test_rows_per_teacher_with_and_without_legacy(self):
        with bypass_rls():
            share = JournalShare.objects.create(
                organization=self.org, offering=self.lvl_b, teacher=self.t, source=JournalShareSource.LEGACY
            )
            share.enrollments.set([self.e_student])
            report = ChairHealth(self.org, self.period, index=self._index())
            rows = {row["teacher"]: row for row in report.rows([self.chair])}
            plain = {row["teacher"]: row for row in ChairHealth(self.org, self.period).rows([self.chair])}
        z, t = rows[str(self.z.pk)], rows[str(self.t.pk)]
        self.assertEqual((z["journals"], z["wrong_level"], z["unlisted"]), (2, 1, 1))
        # Paysız sahib (Z) B-də T-nin tələbəsini görür.
        self.assertEqual((z["foreign_journals"], z["foreign_rows"]), (1, 1))
        self.assertEqual((t["journals"], t["shared_journals"], t["split_level_journals"]), (1, 1, 1))
        self.assertEqual(t["legacy_unmapped"], 2, "xanası olan iki tələbə, yeni sistemdə xana yox")
        self.assertEqual(plain[str(self.z.pk)]["wrong_level"], "", "paket yoxdur — köhnə sistem sütunu boş")
        self.assertEqual(plain[str(self.z.pk)]["foreign_rows"], 1)

    def test_command_csv_md_and_xlsx_guard(self):
        out = StringIO()
        with bypass_rls():
            call_command("chair_journal_health", "--org", self.org.slug, "--chair", self.chair.slug, stdout=out)
        text = out.getvalue()
        self.assertTrue(text.startswith("chair,teacher,journals"))
        self.assertIn("chair_health: ", text)
        self.assertNotIn(self.t.username, text)
        inside = os.path.join(str(settings.BASE_DIR), "kafedra.xlsx")
        with self.assertRaisesMessage(CommandError, "chair_health_xlsx_inside_repo"):
            call_command("chair_journal_health", "--org", self.org.slug, "--xlsx", inside, stdout=StringIO())
        with self.assertRaisesMessage(CommandError, "chair_health_chair_unknown"):
            call_command("chair_journal_health", "--org", self.org.slug, "--chair", "yoxdur", stdout=StringIO())
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "kafedra.xlsx")
            md = os.path.join(folder, "kafedra.md")
            with bypass_rls():
                call_command(
                    "chair_journal_health",
                    "--org",
                    self.org.slug,
                    "--chair",
                    str(self.chair.pk),
                    "--xlsx",
                    path,
                    "--format",
                    "md",
                    "--out",
                    md,
                    stdout=StringIO(),
                )
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with open(md, encoding="utf-8") as handle:
                self.assertTrue(handle.read().startswith("| chair | teacher |"))
            from openpyxl import load_workbook

            sheet = load_workbook(path).active
            names = {cell.value for cell in sheet["B"]}
            self.assertIn(self.t.get_full_name() or self.t.username, names, "Excel-də adlar var (yalnız lokal)")

    def test_write_xlsx_handles_unassigned_row(self):
        with tempfile.TemporaryDirectory() as folder, bypass_rls():
            path = os.path.join(folder, "x.xlsx")
            row = {column: 0 for column in COLUMNS[2:]}
            write_xlsx(path, [{"chair": str(self.chair.pk), "teacher": "-", **row}])
            self.assertTrue(os.path.exists(path))


class BuildCommandTest(_Base):
    def test_command_writes_private_plans_with_ids_only(self):
        bundle = {name: [] for name in SECTIONS}
        bundle["snapshot"] = {"sha256": "0" * 64, "full_semesters": [14]}
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "delta.json.gz")
            write_bundle(source, bundle)
            out = StringIO()
            with bypass_rls():
                call_command(
                    "build_journal_share_plans",
                    "--org",
                    self.org.slug,
                    "--bundle",
                    source,
                    "--out-dir",
                    os.path.join(folder, "plans"),
                    stdout=out,
                )
            self.assertRegex(out.getvalue().strip(), r"^share_plans: [a-z_]+=[0-9]+( [a-z_]+=[0-9]+)*$")
            for name in ("shares.json", "levelmerge.json"):
                self.assertEqual(os.stat(os.path.join(folder, "plans", name)).st_mode & 0o777, 0o600)
            with open(os.path.join(folder, "plans", "shares.json"), encoding="utf-8") as handle:
                shares = json.load(handle)
            # Köhnə jurnal yoxdur → hər səviyyə qeydiyyatı «siyahıda yox» (çıxarış YOX).
            self.assertEqual((shares["format"], shares["drop_enrollments"]), ("journal-shares/1", []))
        with self.assertRaisesMessage(CommandError, "share_plans_bad_deactivate"):
            call_command(
                "build_journal_share_plans",
                "--org",
                self.org.slug,
                "--bundle",
                "x",
                "--out-dir",
                "y",
                "--deactivate",
                "nope",
                stdout=StringIO(),
            )
