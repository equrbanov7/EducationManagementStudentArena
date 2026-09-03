"""``archive_non_program_rows`` — ixtisas OLMAYAN sətirlərin arxivləşdirilməsi.

Sahibin qərarı (2026-08-31): «lazımlıdırsa saxla», sistem magistr/doktorantura
üçün də işlədiləcək → **SİLMƏ, arxivlə**.  Testin əsas işi iki şeyi kilidləmək:

1. Arxivləşdirmə YALNIZ ``Program.is_active`` bayrağına toxunur — bağlı tarixi
   qeydlər (tələbə akademik qeydi, tədris planı) **BİRİ DƏ** dəyişmir/silinmir.
2. Arxivlənmiş sətir SEÇİCİDƏN itir, amma ona bağlı mövcud qeydin formasını
   saxlanılmaz etmir (cari dəyər siyahıda qalır) — yəni arxivləşdirmə tarixi
   datanı DOLAYI YOLLA da zədələmir.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.organizations.models import Membership, Organization
from apps.registrar.forms import CurriculumForm, program_choices
from apps.registrar.management.commands._program_official_codes import NON_PROGRAM_ROWS
from apps.registrar.models import Curriculum, DegreeLevel, Program, StudentAcademicRecord
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()

#: Sahibin sənədindəki (§4) 8 sətir — say və məzmun kilidlənir.
EXPECTED_NON_PROGRAM_CODES = {
    "MYEDU-61",
    "MYEDU-65",
    "MYEDU-66",
    "MYEDU-36-M",
    "MYEDU-91",
    "MYEDU-91-M",
    "MYEDU-92",
    "MYEDU-101",
}


class NonProgramTableTests(TestCase):
    def test_table_matches_the_owner_decision_document(self):
        assert {row.internal_code for row in NON_PROGRAM_ROWS} == EXPECTED_NON_PROGRAM_CODES
        assert len(NON_PROGRAM_ROWS) == 8

    def test_masters_structure_row_is_the_only_masters_entry(self):
        """«Magistratura və doktorantura» STRUKTUR bölməsidir — real magistr
        proqramları ayrıca sətirlərdir, ona görə onu arxivləşdirmək magistratura
        funksionallığını bağlamır."""
        masters = [row for row in NON_PROGRAM_ROWS if row.internal_code.endswith("-M")]
        assert {row.internal_code for row in masters} == {"MYEDU-36-M", "MYEDU-91-M"}


class ArchiveNonProgramRowsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("anp_owner", "anp_owner@qku.edu.az", "pw")
        self.student = User.objects.create_user("anp_student", "anp_student@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="Arxiv Univ",
                slug="arxiv-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            # İxtisas OLMAYAN sətirlərdən ikisi.
            self.level = Program.objects.create(
                organization=self.org, code="MYEDU-61", name="Level", degree_level=DegreeLevel.BACHELOR
            )
            self.college = Program.objects.create(
                organization=self.org, code="MYEDU-92", name="Kollec", degree_level=DegreeLevel.BACHELOR
            )
            # Real ixtisas — TOXUNULMAMALIDIR.
            self.real = Program.objects.create(
                organization=self.org, code="MYEDU-40", name="İqtisadiyyat", degree_level=DegreeLevel.BACHELOR
            )
            # PG ``registrar_guard_active_member`` trigger-i AKTİV üzvlük tələb edir.
            Membership.objects.create(
                user=self.student,
                organization=self.org,
                role=self.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            # Arxivlənəcək sətrə bağlı TARİXİ qeydlər.
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.level, admission_year=2019, name="Level 2019"
            )
            self.record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=self.level,
                curriculum=self.curriculum,
                admission_year=2019,
            )

    def _run(self, *args):
        out = StringIO()
        call_command("archive_non_program_rows", *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    # ── dry-run ─────────────────────────────────────────────────────────────

    def test_default_is_dry_run_and_writes_nothing(self):
        output = self._run()
        assert "DRY-RUN" in output
        with bypass_rls():
            assert Program.objects.get(pk=self.level.pk).is_active is True
            assert Program.objects.get(pk=self.college.pk).is_active is True

    def test_dry_run_reports_attached_history_counts(self):
        output = self._run()
        # Sahib arxivləşdirmənin nəyə toxunduğunu rəqəmlə görməlidir.
        assert "1 tələbə qeydi" in output
        assert "1 tədris planı" in output

    # ── apply ───────────────────────────────────────────────────────────────

    def test_apply_archives_only_the_non_program_rows(self):
        self._run("--apply")
        with bypass_rls():
            assert Program.objects.get(pk=self.level.pk).is_active is False
            assert Program.objects.get(pk=self.college.pk).is_active is False
            # Real ixtisas toxunulmadı.
            assert Program.objects.get(pk=self.real.pk).is_active is True

    def test_attached_history_is_untouched(self):
        self._run("--apply")
        with bypass_rls():
            # Sətirlər NƏ silindi, NƏ deaktiv edildi, NƏ də proqramı dəyişdi.
            record = StudentAcademicRecord.objects.get(pk=self.record.pk)
            assert record.program_id == self.level.pk
            assert record.is_active is True
            assert Curriculum.objects.filter(pk=self.curriculum.pk).exists()
            assert Curriculum.objects.get(pk=self.curriculum.pk).program_id == self.level.pk

    def test_internal_code_is_never_touched(self):
        self._run("--apply")
        with bypass_rls():
            assert Program.objects.get(pk=self.level.pk).code == "MYEDU-61"

    def test_is_idempotent(self):
        self._run("--apply")
        output = self._run("--apply")
        assert "artıq arxivləşdirmə" in output
        with bypass_rls():
            assert Program.objects.get(pk=self.level.pk).is_active is False

    def test_restore_reactivates(self):
        self._run("--apply")
        self._run("--restore", "--apply")
        with bypass_rls():
            assert Program.objects.get(pk=self.level.pk).is_active is True

    # ── fail-closed ─────────────────────────────────────────────────────────

    def test_name_mismatch_blocks_everything(self):
        with bypass_rls():
            Program.objects.filter(pk=self.level.pk).update(name="Başqa bir ixtisas")
        with self.assertRaises(CommandError):
            self._run("--apply")
        with bypass_rls():
            # Kor-koranə yazılmadı — HEÇ BİR sətir dəyişmədi.
            assert Program.objects.get(pk=self.level.pk).is_active is True
            assert Program.objects.get(pk=self.college.pk).is_active is True


class ProgramPickerTests(TestCase):
    """Arxivlənmiş sətir SEÇİCİDƏ görünmür, amma mövcud qeydi sındırmır."""

    def setUp(self):
        self.owner = User.objects.create_user("pick_owner", "pick_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="Seçici Univ",
                slug="secici-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.archived = Program.objects.create(
                organization=self.org,
                code="MYEDU-92",
                name="Kollec",
                degree_level=DegreeLevel.BACHELOR,
                is_active=False,
            )
            self.active = Program.objects.create(
                organization=self.org, code="MYEDU-40", name="İqtisadiyyat", degree_level=DegreeLevel.BACHELOR
            )
            self.legacy_curriculum = Curriculum.objects.create(
                organization=self.org, program=self.archived, admission_year=2018, name="Kollec 2018"
            )

    def test_archived_program_is_hidden_from_a_fresh_picker(self):
        with bypass_rls():
            choices = set(program_choices(self.org))
        assert choices == {self.active}

    def test_archived_program_stays_selectable_on_the_record_that_uses_it(self):
        with bypass_rls():
            choices = set(program_choices(self.org, current_pk=self.archived.pk))
        assert choices == {self.active, self.archived}

    def test_editing_a_historic_curriculum_does_not_break(self):
        """Arxivləşdirmə tarixi qeydi DOLAYI YOLLA da zədələməməlidir: mövcud
        sətrin formasını açıb saxlamaq işləməlidir."""
        with bypass_rls():
            form = CurriculumForm(
                data={
                    "program": str(self.archived.pk),
                    "admission_year": 2018,
                    "name": "Kollec 2018",
                    "is_active": True,
                },
                instance=self.legacy_curriculum,
                organization=self.org,
            )
            assert form.is_valid(), form.errors

    def test_a_new_record_cannot_choose_an_archived_program(self):
        with bypass_rls():
            form = CurriculumForm(
                data={"program": str(self.archived.pk), "admission_year": 2026, "name": "", "is_active": True},
                organization=self.org,
            )
            assert not form.is_valid()
            assert "program" in form.errors

    def test_no_organization_gives_no_choices(self):
        assert list(program_choices(None)) == []
