"""``Program.official_code`` müqaviləsi — rəsmi kod vs daxili kod.

SAHİB TƏLƏBİ (2026-08): «ixtisas kodu hər kəs görə bilməlidi» — 1-ci gün dəqiq
dövlət kodlarını özü dolduracaq. Amma köçürmə xətti (``apps.legacy_import``)
``Program.code``-un tenant-unikallığına söykənir: ``program_pk_index()``,
``rehearsal_structure_targets`` və ``rehearsal_catalog_targets`` təkrar (və ya
boş) kodda ``_INDEX_AMBIGUOUS`` atır. Ona görə kod İKİYƏ AYRILIB:

* ``code`` — DAXİLİ sabit identifikator (``MYEDU-<id>``), unikal QALIR,
  istifadəçiyə HEÇ VAXT göstərilmir;
* ``official_code`` — RƏSMİ dövlət ixtisas kodu, QƏSDƏN unikal DEYİL.

Bu modul üç şeyi kilidləyir:
  1. iki proqram eyni rəsmi kodu paylaşa bilir (real hal: 060209 → dörd magistr
     psixologiya proqramı), daxili kod isə hələ də təkrarlana bilmir;
  2. ``display_label`` — rəsmi kod varsa ``Ad · kod``, yoxsa yalnız ``Ad``
     (asılı qalmış "·" quyruğu yoxdur);
  3. ``MYEDU-*`` daxili kodu heç bir istifadəçi səthində görünmür.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.organizations.models import Membership, Organization, OrgUnit
from apps.registrar.analytics import _Bucket
from apps.registrar.forms import ProgramForm
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class ProgramOfficialCodeTest(TestCase):
    """Sahə davranışı: unikallıq, boşluq, etiket."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("poc_owner", "poc_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="POC Univ",
                slug="poc-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )

    def _program(self, *, code, official_code="", name="Psixologiya"):
        with bypass_rls():
            return Program.objects.create(organization=self.org, code=code, official_code=official_code, name=name)

    # ── 1. Unikallıq qaydaları ───────────────────────────────────────────
    def test_two_programs_share_one_official_code(self):
        """060209 real olaraq DÖRD magistr psixologiya proqramına aiddir."""
        names = [
            "Psixologiya (klinik)",
            "Psixologiya (təşkilati)",
            "Psixologiya (təhsil)",
            "Psixologiya (sosial)",
        ]
        for index, name in enumerate(names):
            self._program(code=f"MYEDU-{index}", official_code="060209", name=name)

        with bypass_rls():
            self.assertEqual(Program.objects.filter(organization=self.org, official_code="060209").count(), 4)

    def test_official_code_may_repeat_for_language_and_form_variants(self):
        """050201 → AZ/EN bölmələri; 050620 → əyani/qiyabi."""
        self._program(code="MYEDU-az", official_code="050201", name="Kompüter elmləri (AZ)")
        self._program(code="MYEDU-en", official_code="050201", name="Kompüter elmləri (EN)")
        self._program(code="MYEDU-full", official_code="050620", name="Menecment (əyani)")
        self._program(code="MYEDU-part", official_code="050620", name="Menecment (qiyabi)")

        with bypass_rls():
            self.assertEqual(Program.objects.filter(organization=self.org, official_code="050201").count(), 2)
            self.assertEqual(Program.objects.filter(organization=self.org, official_code="050620").count(), 2)

    def test_internal_code_is_still_unique_per_org(self):
        """Köçürmə xətti bundan asılıdır — məhdudiyyət YERİNDƏ qalmalıdır."""
        self._program(code="MYEDU-7", official_code="060209")
        with bypass_rls(), self.assertRaises(IntegrityError):
            with transaction.atomic():
                Program.objects.create(organization=self.org, code="MYEDU-7", official_code="050201", name="Dublikat")

    def test_official_code_may_be_blank(self):
        """Sahib kodları 1-ci gün dolduracaq — o vaxta qədər sahə boşdur."""
        program = self._program(code="MYEDU-blank")
        self.assertEqual(program.official_code, "")

    # ── 2. display_label ─────────────────────────────────────────────────
    def test_display_label_appends_the_official_code(self):
        program = self._program(code="MYEDU-1", official_code="060209", name="Psixologiya")
        self.assertEqual(program.display_label, "Psixologiya · 060209")

    def test_display_label_is_name_only_when_the_official_code_is_blank(self):
        """Boş kod göstərilmir — asılı qalmış "Ad · " quyruğu OLMAMALIDIR."""
        program = self._program(code="MYEDU-2", official_code="", name="Psixologiya")
        self.assertEqual(program.display_label, "Psixologiya")
        self.assertNotIn("·", program.display_label)

    def test_display_label_ignores_surrounding_whitespace(self):
        program = self._program(code="MYEDU-3", official_code="   ", name="  Psixologiya  ")
        self.assertEqual(program.display_label, "Psixologiya")

    def test_str_never_exposes_the_internal_code(self):
        program = self._program(code="MYEDU-4242", official_code="060209", name="Psixologiya")
        self.assertEqual(str(program), "Psixologiya · 060209")
        self.assertNotIn("MYEDU", str(program))

    # ── 3. Redaktə forması ───────────────────────────────────────────────
    def test_form_exposes_official_code_with_help_text(self):
        form = ProgramForm(organization=self.org)
        self.assertIn("official_code", form.fields)
        self.assertTrue(str(form.fields["official_code"].help_text))

    def test_form_accepts_an_official_code_already_used_by_another_program(self):
        """UNİKALLIQ YOXLAMASI QOYULMAYIB — təkrar rəsmi kod qanunidir."""
        self._program(code="MYEDU-a", official_code="060209", name="Psixologiya (klinik)")
        form = ProgramForm(
            data={
                "code": "MYEDU-b",
                "official_code": "060209",
                "name": "Psixologiya (sosial)",
                "degree_level": "master",
                "ects_total": "120",
                "absence_limit_percent": "25",
                "is_active": "on",
            },
            organization=self.org,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_still_rejects_a_duplicate_internal_code(self):
        self._program(code="MYEDU-c", official_code="060209")
        form = ProgramForm(
            data={
                "code": "MYEDU-c",
                "official_code": "050201",
                "name": "Dublikat",
                "degree_level": "bachelor",
                "ects_total": "240",
                "absence_limit_percent": "25",
                "is_active": "on",
            },
            organization=self.org,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("code", form.errors)

    def test_form_strips_the_official_code(self):
        form = ProgramForm(
            data={
                "code": "MYEDU-d",
                "official_code": "  060209  ",
                "name": "Psixologiya",
                "degree_level": "master",
                "ects_total": "120",
                "absence_limit_percent": "25",
                "is_active": "on",
            },
            organization=self.org,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["official_code"], "060209")


class InternalCodeNeverReachesASurfaceTest(TestCase):
    """``MYEDU-*`` heç bir istifadəçi səthində görünməməlidir.

    Bu, uydurma köçürmə açarıdır — insan üçün mənası yoxdur və sahibin
    «kod görünsün» tələbini YANLIŞ kodla yerinə yetirmək daha pisdir.
    """

    MYEDU = "MYEDU-9001"

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("poc2_owner", "poc2_owner@qku.edu.az", "pw")
        cls.student = User.objects.create_user("poc2_student", "poc2_student@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="POC2 Univ",
                slug="poc2-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            # AKTİV membership şərtdir (registrar_guard_active_member trigger-i).
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="POC2-G1", slug="poc2-g1", unit_type=OrgUnitType.GROUP
            )
            cls.program = Program.objects.create(
                organization=cls.org,
                code=cls.MYEDU,
                official_code="060209",
                name="Psixologiya",
            )
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2025)
            cls.record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=cls.program,
                curriculum=cls.curriculum,
                group=cls.group,
                admission_year=2025,
            )

    def test_program_and_record_reprs_are_clean(self):
        with bypass_rls():
            self.assertNotIn("MYEDU", str(self.program))
            self.assertNotIn("MYEDU", str(self.record))
            self.assertNotIn("MYEDU", str(self.curriculum))

    def test_student_structure_cards_show_the_official_code(self):
        from apps.accounts.views.profile.context_builder._helpers import build_student_structure_levels

        with bypass_rls():
            levels = build_student_structure_levels(self.record)

        specialty = next(lvl for lvl in levels if lvl["unit_type"] == OrgUnitType.SPECIALTY)
        self.assertEqual(specialty["value"], "Psixologiya")
        self.assertEqual(specialty["code"], "060209")
        self.assertNotIn("MYEDU", str(levels))

    def test_people_directory_program_options_use_the_official_code(self):
        from apps.accounts.services.people.lookups import _program_options

        class _OrgWideScope:
            """Yalnız etiket formatı yoxlanılır — scope daralması bu testin mövzusu deyil."""

            is_org_wide = True

        with bypass_rls():
            options = _program_options(self.org, _OrgWideScope())

        self.assertTrue(options)
        self.assertEqual(options[0]["text"], "Psixologiya · 060209")
        self.assertNotIn("MYEDU", str(options))

    def test_analytics_program_bucket_carries_the_official_code(self):
        bucket = _Bucket(self.program.pk, self.program.name, self.program.official_code)
        self.assertEqual(bucket.sublabel, "060209")
        self.assertNotIn("MYEDU", bucket.sublabel)

    def test_transcript_pdf_prints_the_official_code_not_the_internal_one(self):
        import fitz

        from apps.registrar import transcript, transcript_pdf

        with bypass_rls():
            data = transcript.build_student_transcript(
                student=self.student, organization=self.org, program=self.program
            )
            payload = transcript_pdf.render_transcript_pdf(
                organization=self.org, student=self.student, record=self.record, data=data
            )

        self.assertTrue(payload.startswith(b"%PDF"))
        with fitz.open(stream=payload, filetype="pdf") as doc:
            text = "\n".join(page.get_text() for page in doc)
        self.assertIn("060209", text)
        self.assertNotIn("MYEDU", text)


class ProgramCodePairTest(TestCase):
    """HƏR İKİ nəslin rəsmi şifri — sahibin «yeni və köhnə kodlar» tələbi.

    Azərbaycanda ixtisas təsnifatı 2024-cü ildə dəyişdi (NK 503) və uyğunluq
    bire-bir DEYİL: ixtisas ləğv oluna, yenidən yarana və ya bölünə bilər. Ona
    görə iki sütun var və göstərmə qaydası burada kilidlənir:

    * :attr:`Program.display_code` — kompakt səthlər üçün TƏK şifr (cari, yoxsa
      köhnə): ləğv olunmuş ixtisas şifrsiz qalmır;
    * :attr:`Program.official_code_pair` — hər iki şifr;
    * heç bir halda asılı qalmış ayırıcı («Ad · ») olmur.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("pair_owner", "pair_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Pair Univ",
                slug="pair-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )

    def _program(self, *, code, official_code="", legacy_official_code="", name="Kompüter mühəndisliyi"):
        with bypass_rls():
            return Program.objects.create(
                organization=self.org,
                code=code,
                official_code=official_code,
                legacy_official_code=legacy_official_code,
                name=name,
            )

    def test_both_generations_are_stored_side_by_side(self):
        program = self._program(code="MYEDU-p1", official_code="6006022", legacy_official_code="050631")
        self.assertEqual(program.official_code_current, "6006022")
        self.assertEqual(program.official_code_legacy, "050631")

    def test_the_pair_shows_the_current_code_first_and_marks_the_legacy_one(self):
        program = self._program(code="MYEDU-p2", official_code="6006004", legacy_official_code="050624")
        self.assertTrue(program.official_code_pair.startswith("6006004"))
        self.assertIn("050624", program.official_code_pair)

    def test_the_compact_code_prefers_the_current_generation(self):
        program = self._program(code="MYEDU-p3", official_code="6006022", legacy_official_code="050631")
        self.assertEqual(program.display_code, "6006022")
        self.assertEqual(program.display_label, "Kompüter mühəndisliyi · 6006022")

    def test_an_abolished_programme_falls_back_to_the_legacy_code(self):
        """Yeni təsnifatda ləğv olunub — şifrsiz qalmamalıdır."""
        program = self._program(code="MYEDU-p4", legacy_official_code="050401", name="Dünya iqtisadiyyatı")
        self.assertEqual(program.display_code, "050401")
        self.assertEqual(program.display_label, "Dünya iqtisadiyyatı · 050401")
        self.assertEqual(program.official_code_pair, "050401")

    def test_a_brand_new_programme_shows_only_the_current_code(self):
        program = self._program(code="MYEDU-p5", official_code="6006017", name="İnformasiya təhlükəsizliyi")
        self.assertEqual(program.official_code_pair, "6006017")
        self.assertEqual(program.display_label, "İnformasiya təhlükəsizliyi · 6006017")

    def test_no_dangling_separator_when_both_codes_are_missing(self):
        program = self._program(code="MYEDU-p6", name="Ümumi idarəetmə")
        self.assertEqual(program.display_code, "")
        self.assertEqual(program.official_code_pair, "")
        self.assertEqual(program.display_label, "Ümumi idarəetmə")
        self.assertEqual(program.display_label_full, "Ümumi idarəetmə")
        self.assertNotIn("·", program.display_label_full)

    def test_whitespace_only_codes_are_treated_as_absent(self):
        program = self._program(code="MYEDU-p7", official_code="   ", legacy_official_code="  ", name="  Boş  ")
        self.assertEqual(program.display_label, "Boş")
        self.assertNotIn("·", program.display_label)

    def test_the_full_label_carries_both_codes(self):
        program = self._program(code="MYEDU-p8", official_code="6006004", legacy_official_code="050624")
        self.assertIn("6006004", program.display_label_full)
        self.assertIn("050624", program.display_label_full)
        self.assertNotIn("MYEDU", program.display_label_full)

    def test_the_internal_code_never_leaks_into_any_label(self):
        program = self._program(code="MYEDU-p9", official_code="6006022", legacy_official_code="050631")
        for label in (program.display_label, program.display_label_full, program.official_code_pair, str(program)):
            self.assertNotIn("MYEDU", label)

    def test_the_legacy_code_may_repeat_across_programs(self):
        """Unikallıq QƏSDƏN yoxdur — hər iki sütunda."""
        self._program(code="MYEDU-p10", official_code="7002013", legacy_official_code="060209", name="Klinik psix.")
        self._program(code="MYEDU-p11", official_code="7002013", legacy_official_code="060209", name="Sosial psix.")
        with bypass_rls():
            self.assertEqual(Program.objects.filter(organization=self.org, legacy_official_code="060209").count(), 2)

    def test_form_exposes_both_code_fields(self):
        form = ProgramForm(organization=self.org)
        self.assertIn("official_code", form.fields)
        self.assertIn("legacy_official_code", form.fields)
        self.assertTrue(str(form.fields["legacy_official_code"].help_text))

    def test_form_strips_the_legacy_code(self):
        form = ProgramForm(
            data={
                "code": "MYEDU-p12",
                "official_code": "6006022",
                "legacy_official_code": "  050631  ",
                "name": "Kompüter mühəndisliyi",
                "degree_level": "bachelor",
                "ects_total": "240",
                "absence_limit_percent": "25",
                "is_active": "on",
            },
            organization=self.org,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["legacy_official_code"], "050631")
