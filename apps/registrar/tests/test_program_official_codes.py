"""``set_program_official_codes`` — cədvəlin intizamı və komandanın davranışı.

Bu testin əsas işi **cədvəli kilidləməkdir**: əvvəlki iki cəhd düşmən
doğrulayıcısının «tətbiq etmə» hökmü olan şifrləri yenə də yazdı. Burada həm
yazılanların sayı, həm də hər buraxılmış sətrin cədvəldən KƏNARDA qalması
yoxlanılır.
"""

from io import StringIO
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.organizations.models import Organization
from apps.registrar.management.commands import _program_official_codes as table
from apps.registrar.models import DegreeLevel, Program
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()

#: Doğrulayıcının açıq «TƏTBİQ ET» hökmü — sayı və məzmunu kilidlənir.
EXPECTED_ASSIGNMENTS = {
    ("050620-M", "060631"),
    ("060411-M", "060411"),
    ("MYEDU-40", "050405"),
    ("MYEDU-43", "050406"),
    ("MYEDU-62", "050509"),
}

#: Doğrulayıcının RƏDD etdiyi və namizəd qalan sətirlər — cədvəldə OLMAMALIDIR.
MUST_NOT_BE_ASSIGNED = {
    "050708-M",
    "MYEDU-86-M",
    "MYEDU-90-M",
    "MYEDU-20",
    "MYEDU-67",
    "050501-63",
    "MYEDU-14",
    "MYEDU-18",
    "MYEDU-42",
    "MYEDU-44",
    "MYEDU-47",
    "MYEDU-48",
    "MYEDU-49",
    "MYEDU-50",
    "MYEDU-72-M",
    "MYEDU-74-M",
    "MYEDU-81-M",
    "MYEDU-26",
    "MYEDU-27",
    "MYEDU-41",
    "MYEDU-53",
    "MYEDU-68",
    "MYEDU-75-M",
    "MYEDU-83-M",
    "MYEDU-87-M",
    "MYEDU-88-M",
}


class OfficialCodeTableTest(TestCase):
    """Cədvəlin öz intizamı — bazaya toxunmur."""

    def test_only_the_five_verified_codes_are_assigned(self):
        actual = {(item.internal_code, item.official_code) for item in table.ASSIGNMENTS}
        self.assertEqual(actual, EXPECTED_ASSIGNMENTS)

    def test_every_assignment_carries_two_independent_sources(self):
        for item in table.ASSIGNMENTS:
            self.assertTrue(item.source_primary, item.internal_code)
            self.assertTrue(item.source_secondary, item.internal_code)
            self.assertNotEqual(item.source_primary, item.source_secondary, item.internal_code)

    def test_rejected_and_candidate_rows_are_never_assigned(self):
        assigned = {item.internal_code for item in table.ASSIGNMENTS}
        self.assertEqual(assigned & MUST_NOT_BE_ASSIGNED, set())

    def test_the_twentyone_site_candidates_are_all_held_back(self):
        self.assertEqual(len(table.SITE_SEARCH_CANDIDATES), 21)

    def test_the_eight_non_program_rows_are_listed(self):
        self.assertEqual(len(table.NON_PROGRAM_ROWS), 8)

    def test_the_three_source_contradictions_are_listed(self):
        self.assertEqual(len(table.SOURCE_CONTRADICTIONS), 3)

    def test_the_wrong_code_is_kept_blank_not_replaced(self):
        self.assertEqual([row.internal_code for row in table.WRONG_CODES], ["050624"])

    def test_the_table_passes_its_own_health_check(self):
        self.assertEqual(table.check_table_health(), [])

    def test_health_check_catches_a_level_prefix_violation(self):
        broken = table.CodeAssignment(
            internal_code="MYEDU-999",
            official_code="060631",  # magistr şifri, bakalavr sətrində
            expected_name="Uydurma",
            degree_level="bachelor",
            source_primary="a",
            source_secondary="b",
        )
        with mock.patch.object(table, "ASSIGNMENTS", table.ASSIGNMENTS + (broken,)):
            problems = table.check_table_health()
        self.assertTrue(any("MYEDU-999" in line for line in problems))


class SetProgramOfficialCodesTest(TestCase):
    """Komandanın davranışı — dry-run, idempotentlik, fail-closed, audit."""

    def setUp(self):
        self.owner = User.objects.create_user("oc_owner", "oc_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="Kod Univ",
                slug="kod-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.economics = Program.objects.create(
                organization=self.org,
                code="MYEDU-40",
                name="İqtisadiyyat",
                degree_level=DegreeLevel.BACHELOR,
            )
            self.comp_eng = Program.objects.create(
                organization=self.org,
                code="050620-M",
                name="Kompüter Mühəndisliyi",
                degree_level=DegreeLevel.MASTER,
            )
            # Yanlış daxili şifr — official_code BOŞ qalmalıdır.
            self.instrument = Program.objects.create(
                organization=self.org,
                code="050624",
                name="Cihazqayırma mühəndisliyi",
                degree_level=DegreeLevel.BACHELOR,
            )
            # Təmiz daxili şifr — yalnız --adopt-clean-codes ilə mənimsənilir.
            self.law = Program.objects.create(
                organization=self.org,
                code="050204",
                name="Hüquqşünaslıq",
                degree_level=DegreeLevel.BACHELOR,
            )

    def _run(self, *args):
        out = StringIO()
        call_command("set_program_official_codes", *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def _reload(self):
        with bypass_rls():
            for attr in ("economics", "comp_eng", "instrument", "law"):
                setattr(self, attr, Program.objects.get(pk=getattr(self, attr).pk))

    # ── dry-run ─────────────────────────────────────────────────────────────

    def test_dry_run_is_the_default_and_writes_nothing(self):
        output = self._run()
        self.assertIn("DRY-RUN", output)
        self._reload()
        self.assertEqual(self.economics.official_code, "")
        self.assertEqual(self.comp_eng.official_code, "")

    def test_holds_report_needs_no_database(self):
        output = self._run("--holds")
        self.assertIn("MYEDU-86-M", output)
        self.assertIn("MYEDU-72-M", output)  # namizəd — yazılmır
        self.assertIn("Kollec 2", output)
        self.assertNotIn("DRY-RUN", output)

    def test_table_export_leaves_the_approved_column_empty(self):
        output = self._run("--table")
        self.assertIn("**Təsdiqlənmiş şifr**", output)
        self.assertIn("| `MYEDU-40` | İqtisadiyyat |", output)
        self.assertIn("| `050624` | Cihazqayırma mühəndisliyi |", output)
        self.assertIn("YANLIŞ şifr — boş qalır", output)
        # Sahib doldurana qədər hər sətir boş qutu ilə bitir.
        rows = [line for line in output.splitlines() if line.startswith("| `")]
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(line.rstrip().endswith("| ☐ |") for line in rows))

    # ── yazma ───────────────────────────────────────────────────────────────

    def test_apply_writes_the_official_code_and_never_touches_the_internal_code(self):
        self._run("--apply")
        self._reload()
        self.assertEqual(self.economics.official_code, "050405")
        self.assertEqual(self.economics.code, "MYEDU-40")
        self.assertEqual(self.comp_eng.official_code, "060631")
        self.assertEqual(self.comp_eng.code, "050620-M")

    def test_display_label_shows_the_official_code_not_the_internal_one(self):
        self._run("--apply")
        self._reload()
        self.assertEqual(self.economics.display_label, "İqtisadiyyat · 050405")
        self.assertNotIn("MYEDU", str(self.economics))

    def test_the_wrong_code_row_is_left_blank_on_purpose(self):
        self._run("--apply")
        self._reload()
        self.assertEqual(self.instrument.official_code, "")
        self.assertEqual(self.instrument.code, "050624")

    def test_clean_internal_codes_are_only_adopted_on_demand(self):
        self._run("--apply")
        self._reload()
        self.assertEqual(self.law.official_code, "")

        self._run("--apply", "--adopt-clean-codes")
        self._reload()
        self.assertEqual(self.law.official_code, "050204")
        # ...amma yanlış şifr mənimsənilmir.
        self.assertEqual(self.instrument.official_code, "")

    def test_second_run_is_idempotent(self):
        self._run("--apply")
        AuditLog = django_apps.get_model("audit", "AuditLog")
        first = AuditLog.objects.filter(resource_type="registrar.Program").count()
        output = self._run("--apply")
        self.assertEqual(AuditLog.objects.filter(resource_type="registrar.Program").count(), first)
        self.assertIn("artıq düzgündür", output)

    def test_every_write_lands_in_the_audit_trail_with_both_sources(self):
        self._run("--apply")
        AuditLog = django_apps.get_model("audit", "AuditLog")
        entry = AuditLog.objects.filter(resource_type="registrar.Program", resource_id=str(self.economics.pk)).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.changes["official_code"], {"old": "", "new": "050405"})
        self.assertEqual(entry.changes["internal_code_unchanged"], "MYEDU-40")
        self.assertIn("milli bakalavriat", entry.changes["source_primary"])
        self.assertIn("wcu.edu.az", entry.changes["source_secondary"])

    # ── fail-closed ─────────────────────────────────────────────────────────

    def test_a_name_mismatch_blocks_the_whole_run(self):
        with bypass_rls():
            Program.objects.filter(pk=self.economics.pk).update(name="Başqa ixtisas")
        with self.assertRaises(CommandError):
            self._run("--apply")
        self._reload()
        self.assertEqual(self.comp_eng.official_code, "")  # heç nə yazılmadı

    def test_a_degree_level_mismatch_blocks_the_whole_run(self):
        with bypass_rls():
            Program.objects.filter(pk=self.comp_eng.pk).update(degree_level=DegreeLevel.BACHELOR)
        with self.assertRaises(CommandError):
            self._run("--apply")
        self._reload()
        self.assertEqual(self.economics.official_code, "")

    def test_an_existing_different_code_is_never_silently_overwritten(self):
        with bypass_rls():
            Program.objects.filter(pk=self.economics.pk).update(official_code="999999")
        with self.assertRaises(CommandError):
            self._run("--apply")
        self._reload()
        self.assertEqual(self.economics.official_code, "999999")
        self.assertEqual(self.comp_eng.official_code, "")
