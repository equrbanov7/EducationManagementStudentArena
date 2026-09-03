"""Köçürülmüş qiymətin GÖRÜNƏN nişanı — müəyyənetmə və səth müqaviləsi.

Burada yoxlanan sual bir dənədir: «istifadəçi hansı balın köhnə sistemdən
gəldiyini ayırd edə bilirmi?»  Nişan sübut qatından HESABLANIR (ayrıca bayraq
sütunu yoxdur), ona görə testlər həm hesablamanı, həm də onun bütün səthlərə
EYNİ mənbədən çatmasını kilidləyir.
"""

from apps.registrar import legacy_grade_read, transcript
from apps.registrar.models import LegacyGradeMappingStatus
from apps.registrar.tests.test_legacy_grade_evidence import LegacyGradeEvidenceModelTests
from core.rls import clear_rls_user, set_rls_user


class LegacyProvenanceTests(LegacyGradeEvidenceModelTests):
    """``LegacyGradeEvidenceModelTests``-in fikstur köməkçilərini təkrar işlədir.

    (``_fact`` / ``_review`` / ``_BaseJournalSetup`` orada qurulub; ikinci dəfə
    yazmaq iki fərqli «köhnə fakt» tərifi yaradardı.)
    """

    def setUp(self):
        super().setUp()
        # İstehsal importerinin etdiyi kimi DB trigger-inə real aktor verilir.
        # Təşkilat sahibi trigger-in import səlahiyyətindən keçir; bypass açmaq
        # bu müqaviləni PostgreSQL-də sınaqdan kənarda qoyardı.
        set_rls_user(self.owner.pk, local=False)

    def tearDown(self):
        # Session-scope GUC növbəti testə sızmamalıdır.
        clear_rls_user(local=False)
        super().tearDown()

    # ── Müəyyənetmə ─────────────────────────────────────────────────────────

    def test_enrollment_with_legacy_fact_is_marked(self):
        self._fact(source_pk=101)
        provenance = legacy_grade_read.legacy_provenance_for_enrollments(
            organization=self.org, enrollment_ids=[self.enrollment.id]
        )
        badge = provenance[self.enrollment.id]
        self.assertTrue(badge["is_legacy"])
        self.assertEqual(badge["source_system"], "myedudb")

    def test_enrollment_without_legacy_fact_is_not_marked(self):
        provenance = legacy_grade_read.legacy_provenance_for_enrollments(
            organization=self.org, enrollment_ids=[self.enrollment.id]
        )
        self.assertNotIn(self.enrollment.id, provenance)

    def test_badge_exposes_raw_source_values_without_reformatting(self):
        """Tooltip mənbənin XAM dəyərini göstərməlidir — clamp/round OLMADAN.

        ``final_score_text='117'`` qəsdən 100-dən böyükdür: köhnə sistemdə belə
        sətirlər var (ölçülüb: 339-u canlı ``registrar_finalgrade``-dədir) və
        nişanın işi məhz onları GÖRÜNƏN etməkdir, düzəltmək yox.
        """
        self._fact(source_pk=102)
        badge = legacy_grade_read.legacy_provenance_for_enrollments(
            organization=self.org, enrollment_ids=[self.enrollment.id]
        )[self.enrollment.id]
        self.assertEqual(badge["raw_entry"], "59")
        self.assertEqual(badge["raw_exam"], "58")
        self.assertEqual(badge["raw_final"], "117")

    # ── İmtahan Mərkəzinin yoxlaması ────────────────────────────────────────

    def test_unreviewed_fact_requires_exam_center_review(self):
        self._fact(source_pk=103)
        badge = legacy_grade_read.legacy_provenance_for_enrollments(
            organization=self.org, enrollment_ids=[self.enrollment.id]
        )[self.enrollment.id]
        self.assertTrue(badge["review_required"])
        self.assertTrue(str(badge["review_notice"]))

    def test_verified_fact_clears_the_review_flag(self):
        fact = self._fact(source_pk=104)
        self._review(fact)
        badge = legacy_grade_read.legacy_provenance_for_enrollments(
            organization=self.org, enrollment_ids=[self.enrollment.id]
        )[self.enrollment.id]
        self.assertFalse(badge["review_required"])
        self.assertEqual(badge["review_notice"], "")
        # VERIFIED workflow statusudur; balın legacy mənşəsi və sahibin
        # tələb etdiyi qırmızı qeyd statusdan sonra da qalır.
        self.assertEqual(str(badge["warning"]), str(legacy_grade_read.LEGACY_EXAM_CENTER_WARNING))
        # MƏNŞƏ isə qalır: dəyər hələ də köhnə sistemdəndir və yenidən
        # hesablanmayıb — bunu boz qlifin etiketi/tooltip-i daşıyır.
        self.assertEqual(str(badge["label"]), str(legacy_grade_read.LEGACY_BADGE_LABEL))
        self.assertTrue(str(badge["notice"]))

    def test_one_unreviewed_fact_keeps_the_whole_row_flagged(self):
        """Nişan ən pis haldan xəbər verməlidir, ortalamadan yox."""
        verified = self._fact(source_pk=105)
        self._review(verified)
        self._fact(source_pk=106, source_enrollment_ref="journal-1:student-1")
        badge = legacy_grade_read.legacy_provenance_for_enrollments(
            organization=self.org, enrollment_ids=[self.enrollment.id]
        )[self.enrollment.id]
        self.assertEqual(badge["fact_count"], 2)
        self.assertTrue(badge["review_required"])

    # ── Tenant sərhədi ──────────────────────────────────────────────────────

    def test_other_organization_never_receives_the_badge(self):
        self._fact(source_pk=107)
        other = self._second_organization()
        provenance = legacy_grade_read.legacy_provenance_for_enrollments(
            organization=other, enrollment_ids=[self.enrollment.id]
        )
        self.assertEqual(provenance, {})

    # ── Səth müqaviləsi ─────────────────────────────────────────────────────

    def test_transcript_rows_carry_the_badge_for_every_surface(self):
        """Transkript, transkript PDF-i və «Ümumi tədris məlumatı» EYNİ qurucudan
        çıxır — nişan hamısına bir yerdən düşməlidir, yoxsa eyni sətir bir
        ekranda nişanlı, digərində nişansız görünər."""
        self._fact(source_pk=108)
        data = transcript.build_student_transcript(student=self.student, organization=self.org)
        rows = [row for sem in data["semesters"] for row in sem["rows"]]
        target = next(row for row in rows if row["enrollment_id"] == self.enrollment.id)
        self.assertIsNotNone(target["legacy"])
        self.assertTrue(target["legacy"]["is_legacy"])

        overall = transcript.build_student_overall_record(student=self.student, organization=self.org)
        flat = [row for sem in overall["semesters"] for row in sem["rows"]]
        mirrored = next(row for row in flat if row["enrollment_id"] == self.enrollment.id)
        self.assertIsNotNone(mirrored["legacy"])
        self.assertEqual(mirrored["legacy"]["source_system"], "myedudb")

    def test_rows_without_evidence_expose_an_explicit_none(self):
        """«Köhnə deyil» ilə «hələ qoşulmayıb» qarışmasın deyə açar HƏMİŞƏ var."""
        data = transcript.build_student_transcript(student=self.student, organization=self.org)
        rows = [row for sem in data["semesters"] for row in sem["rows"]]
        self.assertTrue(rows)
        for row in rows:
            self.assertIn("legacy", row)
            self.assertIsNone(row["legacy"])

    def test_unresolved_fact_is_not_attached_to_any_enrollment(self):
        """Qeydiyyata bağlanmamış fakt heç bir tələbənin sətrini nişanlamamalıdır."""
        self._fact(
            source_pk=109,
            enrollment=None,
            mapping_status=LegacyGradeMappingStatus.UNRESOLVED,
            source_enrollment_ref="",
        )
        data = transcript.build_student_transcript(student=self.student, organization=self.org)
        rows = [row for sem in data["semesters"] for row in sem["rows"]]
        self.assertTrue(all(row["legacy"] is None for row in rows))
