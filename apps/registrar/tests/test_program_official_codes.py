"""``set_program_official_codes`` — data faylının intizamı və komandanın davranışı.

Bu testin ƏSAS işi **uydurma şifrin qarşısını almaqdır**. Modulun əvvəlki
variantı əl ilə yığılmış 5 sətirlik cədvəli kilidləyirdi — və həmin cədvəlin
2 sətri SƏHV idi (``MYEDU-40`` «İqtisadiyyat» → ``050405``, əslində «Sənayenin
təşkili»; ``MYEDU-43`` «Maliyyə» → ``050406``, əslində «Statistika»). Hər ikisi
«iki müstəqil mənbə ilə təsdiqlənib» qeydi daşıyırdı. Yəni SAYI kilidləmək
kifayət etmir — şifrin RƏSMİ KATALOQDA olduğunu yoxlamaq lazımdır.

Ona görə burada kilidlənən şey cədvəlin ölçüsü deyil, **invariantdır**:

  1. ``validate()`` fayldakı hər şifri rəsmi kataloqa qarşı yoxlayır
     (mövcudluq + ad + pillə prefiksi) və heç bir problem tapmır;
  2. kataloqda OLMAYAN şifr fayla düşsə, komanda heç nə yazmadan dayanır;
  3. yazılan şifrlərin hamısı kataloqdadır — bir dənə də uydurma yoxdur;
  4. «şübhəli» və «tapılmadı» sətirlərinə şifr YAZILMIR;
  5. komanda idempotentdir və fail-closed-dur.
"""

from dataclasses import replace
from io import StringIO
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.organizations.models import Organization
from apps.registrar.management.commands import _program_official_codes as data
from apps.registrar.models import DegreeLevel, Program
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()


class OfficialCodeDataTest(TestCase):
    """Data faylı ↔ rəsmi kataloq — uydurma şifr ola bilməz."""

    def test_the_shipped_data_passes_the_catalogue_validation(self):
        self.assertEqual(data.validate(), [])

    def test_the_catalogues_have_the_documented_sizes(self):
        current, legacy = data.load_catalogs()
        # NK 503/2024: bakalavr 154 + baza tibb 3 + magistratura 129 + rezidentura 43.
        self.assertEqual(len(current), 329)
        # e-qanun 16051 (169 bakalavr) + 21781 (202 magistr); fəzalar kəsişmir.
        self.assertEqual(len(legacy), 169 + 202)

    def test_every_emitted_code_exists_in_the_official_catalogue(self):
        current, legacy = data.load_catalogs()
        for row in data.load_rows():
            if row.current_code:
                self.assertIn(row.current_code, current, row.internal_code)
            if row.legacy_code:
                self.assertIn(row.legacy_code, legacy, row.internal_code)

    def test_code_generations_never_mix_levels(self):
        for row in data.load_rows():
            if row.legacy_code:
                self.assertTrue(row.legacy_code.startswith(data.LEGACY_LEVEL_PREFIXES[row.degree_level]))
            if row.current_code:
                self.assertTrue(row.current_code.startswith(data.CURRENT_LEVEL_PREFIXES[row.degree_level]))

    def test_rows_that_are_not_programs_carry_no_code(self):
        for hold in data.non_program_rows():
            row = next(r for r in data.load_rows() if r.internal_code == hold.internal_code)
            self.assertEqual(row.legacy_code, "")
            self.assertEqual(row.current_code, "")

    def test_owner_decision_rows_are_never_writable(self):
        for row in data.owner_decision_rows():
            self.assertFalse(row.is_writable)
            self.assertNotIn(row, data.writable_rows())

    def test_a_code_missing_from_the_catalogue_is_rejected(self):
        """Uydurma şifrin qarşısını alan yeganə mexanizm — bu yoxlama."""
        fake = replace(data.load_rows()[0], current_code="6999999", current_name="Uydurma ixtisas")
        with mock.patch.object(data, "load_rows", lambda: (fake,)):
            problems = data.validate()
        self.assertTrue(any("RƏSMİ KATALOQDA YOXDUR" in line for line in problems))

    def test_a_name_that_disagrees_with_the_catalogue_is_rejected(self):
        row = next(r for r in data.load_rows() if r.current_code)
        fake = replace(row, current_name="Başqa ad")
        with mock.patch.object(data, "load_rows", lambda: (fake,)):
            problems = data.validate()
        self.assertTrue(any("kataloqda" in line for line in problems))

    def test_a_level_prefix_violation_is_rejected(self):
        """Magistr şifri bakalavr sətrində — 2024 təsnifatında 7… vs 6…."""
        row = next(r for r in data.load_rows() if r.degree_level == "bachelor" and r.current_code)
        current, _legacy = data.load_catalogs()
        master_code = next(code for code in current if code.startswith("7"))
        fake = replace(row, current_code=master_code, current_name=current[master_code])
        with mock.patch.object(data, "load_rows", lambda: (fake,)):
            problems = data.validate()
        self.assertTrue(any("pilləsinə uyğun deyil" in line for line in problems))


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
            # Hər iki şifri olan sətir.
            self.comp_eng = Program.objects.create(
                organization=self.org,
                code="050620",
                name="Kompüter Mühəndisliyi",
                degree_level=DegreeLevel.BACHELOR,
            )
            # YALNIZ cari şifr — köhnə təsnifatda yox idi.
            self.infosec = Program.objects.create(
                organization=self.org,
                code="050615",
                name="İnformasiya Təhlükəsizliyi",
                degree_level=DegreeLevel.BACHELOR,
            )
            # YALNIZ köhnə şifr — yeni təsnifatda ləğv olunub.
            self.world_econ = Program.objects.create(
                organization=self.org,
                code="MYEDU-41",
                name="Dünya iqtisadiyyatı",
                degree_level=DegreeLevel.BACHELOR,
            )
            # «şübhəli» — sahibin qərarını gözləyir, şifr YAZILMIR.
            self.general_mgmt = Program.objects.create(
                organization=self.org,
                code="MYEDU-73-M",
                name="Ümumi idarəetmə",
                degree_level=DegreeLevel.MASTER,
            )
            # «tapılmadı» — ixtisas deyil.
            self.not_a_program = Program.objects.create(
                organization=self.org,
                code="MYEDU-65",
                name="aaa",
                degree_level=DegreeLevel.BACHELOR,
            )

    _ROWS = ("comp_eng", "infosec", "world_econ", "general_mgmt", "not_a_program")

    def _run(self, *args):
        out = StringIO()
        call_command("set_program_official_codes", *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def _reload(self):
        with bypass_rls():
            for attr in self._ROWS:
                setattr(self, attr, Program.objects.get(pk=getattr(self, attr).pk))

    # ── dry-run ─────────────────────────────────────────────────────────────

    def test_dry_run_is_the_default_and_writes_nothing(self):
        output = self._run()
        self.assertIn("DRY-RUN", output)
        self._reload()
        self.assertEqual(self.comp_eng.official_code, "")
        self.assertEqual(self.comp_eng.legacy_official_code, "")

    def test_holds_report_needs_no_database(self):
        output = self._run("--holds")
        self.assertIn("MYEDU-73-M", output)  # sahibin qərarı
        self.assertIn("MYEDU-65", output)  # ixtisas deyil
        self.assertNotIn("DRY-RUN", output)

    # ── yazma ───────────────────────────────────────────────────────────────

    def test_apply_writes_both_generations_and_never_touches_the_internal_code(self):
        self._run("--apply")
        self._reload()
        self.assertEqual(self.comp_eng.official_code, "6006022")
        self.assertEqual(self.comp_eng.legacy_official_code, "050631")
        self.assertEqual(self.comp_eng.code, "050620")  # daxili kod toxunulmadı

    def test_a_programme_only_in_the_new_classifier_keeps_the_legacy_column_blank(self):
        self._run("--apply")
        self._reload()
        self.assertEqual(self.infosec.official_code, "6006017")
        self.assertEqual(self.infosec.legacy_official_code, "")

    def test_a_programme_abolished_in_the_new_classifier_keeps_the_legacy_code(self):
        self._run("--apply")
        self._reload()
        self.assertEqual(self.world_econ.official_code, "")
        self.assertEqual(self.world_econ.legacy_official_code, "050401")
        # Şifrsiz qalmır: kompakt etiket köhnə şifrə geri çəkilir.
        self.assertEqual(self.world_econ.display_code, "050401")

    def test_uncertain_and_non_programme_rows_stay_blank(self):
        self._run("--apply")
        self._reload()
        for row in (self.general_mgmt, self.not_a_program):
            self.assertEqual(row.official_code, "")
            self.assertEqual(row.legacy_official_code, "")
            self.assertEqual(row.display_label, row.name)  # asılı ayırıcı yoxdur

    def test_no_written_code_is_absent_from_the_official_catalogue(self):
        self._run("--apply")
        self._reload()
        current, legacy = data.load_catalogs()
        with bypass_rls():
            for row in Program.objects.filter(organization=self.org):
                if row.official_code:
                    self.assertIn(row.official_code, current)
                if row.legacy_official_code:
                    self.assertIn(row.legacy_official_code, legacy)

    def test_second_run_is_idempotent(self):
        self._run("--apply")
        AuditLog = django_apps.get_model("audit", "AuditLog")
        first = AuditLog.objects.filter(resource_type="registrar.Program").count()
        output = self._run("--apply")
        self.assertEqual(AuditLog.objects.filter(resource_type="registrar.Program").count(), first)
        self.assertIn("artıq düzgündür", output)

    def test_every_write_lands_in_the_audit_trail(self):
        self._run("--apply")
        AuditLog = django_apps.get_model("audit", "AuditLog")
        entry = AuditLog.objects.filter(resource_type="registrar.Program", resource_id=str(self.comp_eng.pk)).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.changes["official_code"], {"old": "", "new": "6006022"})
        self.assertEqual(entry.changes["legacy_official_code"], {"old": "", "new": "050631"})
        self.assertEqual(entry.changes["internal_code_unchanged"], "050620")

    # ── fail-closed ─────────────────────────────────────────────────────────

    def test_a_name_mismatch_blocks_the_whole_run(self):
        with bypass_rls():
            Program.objects.filter(pk=self.comp_eng.pk).update(name="Başqa ixtisas")
        with self.assertRaises(CommandError):
            self._run("--apply")
        self._reload()
        self.assertEqual(self.infosec.official_code, "")  # heç nə yazılmadı

    def test_a_degree_level_mismatch_blocks_the_whole_run(self):
        with bypass_rls():
            Program.objects.filter(pk=self.comp_eng.pk).update(degree_level=DegreeLevel.MASTER)
        with self.assertRaises(CommandError):
            self._run("--apply")
        self._reload()
        self.assertEqual(self.infosec.official_code, "")

    def test_an_existing_different_code_is_never_silently_overwritten(self):
        with bypass_rls():
            Program.objects.filter(pk=self.comp_eng.pk).update(official_code="6999999")
        with self.assertRaises(CommandError):
            self._run("--apply")
        self._reload()
        self.assertEqual(self.comp_eng.official_code, "6999999")
        self.assertEqual(self.infosec.official_code, "")

    def test_force_overwrites_an_existing_different_code(self):
        with bypass_rls():
            Program.objects.filter(pk=self.comp_eng.pk).update(official_code="6999999")
        self._run("--apply", "--force")
        self._reload()
        self.assertEqual(self.comp_eng.official_code, "6006022")

    def test_a_broken_data_file_stops_the_command_before_any_write(self):
        fake = replace(data.load_rows()[0], current_code="6999999", current_name="Uydurma")
        with mock.patch.object(data, "load_rows", lambda: (fake,)):
            with self.assertRaises(CommandError):
                self._run("--apply")
        self._reload()
        self.assertEqual(self.comp_eng.official_code, "")
