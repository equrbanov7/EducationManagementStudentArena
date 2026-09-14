"""``ExamScoreSheet`` tenant/əlaqə invariantları — model + servis qatı (Codex audit P2-09, 2026-09-13).

Trigger tərəfi ``test_exam_score_sheet_integrity_postgres.py``-dədir; burada
backend-dən asılı olmayan iki qat yoxlanır:

* model ``clean()`` — vərəq ↔ açılış təşkilatı (I1), skanın org-prefiksi (I4),
  sətir ↔ qeydiyyat ↔ vərəq zənciri (I3);
* servis — ``create_sheet`` yad təşkilatın yoxlayanını rədd edir (I2),
  ``record_exam_score`` / ``save_roster_scores`` / ``apply_plan`` başqa açılışın
  vərəqini fail-closed rədd edir, düzgün vərəq isə sətirlərə bağlanır;
* sorğu büdcəsi — qoruyucular defolt yolda ƏLAVƏ sorğu vermir (vərəqli/vərəqsiz
  yazı eyni sayda), açıq verilən yoxlayan üçün düz 1 üzvlük sorğusu.

``build_tenant`` köməkçisi qardaş test modulları tərəfindən də istifadə olunur
(iki açılışlı bir tenant: eyni tələbə, iki fənn — cross-offering halı üçün).
"""

import tempfile
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import exam_score_entry as service
from apps.registrar import exam_score_import as importer
from apps.registrar import exam_score_sheets as sheets
from apps.registrar import services
from apps.registrar.models import (
    Curriculum,
    CurriculumSubject,
    ExamScoreEntry,
    ExamScoreSheet,
    FinalGrade,
    Program,
    StudentAcademicRecord,
    Subject,
)
from apps.registrar.models.exam_score_entry import exam_score_sheet_evidence_prefix
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

_MEDIA = tempfile.mkdtemp(prefix="essi-media-")


def _pdf(name="verq.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


def build_tenant(tag, *, subject_codes=("S1", "S2")):
    """Bir tenant: qrup, dövr, proqram, iki fənn → tələbənin İKİ açılışı, müəllim, imtahan mərkəzi.

    ``offerings`` fənn koduna görə sıralanır (``[0]`` və ``[1]`` eyni tenantın
    fərqli açılışlarıdır); ``enrollments`` eyni sırada.
    """
    owner = User.objects.create_user(f"{tag}_owner", f"{tag}_owner@qku.edu.az", "pw")
    with bypass_rls():
        org = Organization.objects.create(
            name=f"{tag} Univ",
            slug=f"{tag}-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        group = OrgUnit.objects.create(
            organization=org, name=f"{tag}-101", slug=f"{tag}-g1", unit_type=OrgUnitType.GROUP
        )
        period = AcademicPeriod.objects.create(
            organization=org,
            name="Payız",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2024/2025",
            start_date="2024-09-01",
            end_date="2025-01-31",
            is_current=True,
        )
        program = Program.objects.create(
            organization=org, code=f"{tag}P", name=f"{tag} proqram", absence_limit_percent=25
        )
        curriculum = Curriculum.objects.create(organization=org, program=program, admission_year=2024)
        subjects = []
        for code in subject_codes:
            subject = Subject.objects.create(organization=org, code=f"{tag}-{code}", name=f"{tag} {code}")
            CurriculumSubject.objects.create(
                organization=org, curriculum=curriculum, subject=subject, semester_number=1
            )
            subjects.append(subject)
        center = User.objects.create_user(f"{tag}_center", f"{tag}_center@qku.edu.az", "pw")
        teacher = User.objects.create_user(f"{tag}_teacher", f"{tag}_teacher@qku.edu.az", "pw")
        student = User.objects.create_user(f"{tag}_student", f"{tag}_student@qku.edu.az", "pw")
        for user, role in ((center, "exam_center_head"), (teacher, "teacher"), (student, "student")):
            Membership.objects.create(
                user=user, organization=org, role=org.roles.get(name=role), is_primary=True, is_active=True
            )
        record = StudentAcademicRecord.objects.create(
            organization=org, student=student, program=program, curriculum=curriculum, group=group, admission_year=2024
        )
        services.enroll_mandatory_subjects(record=record, period=period, semester_number=1)
        enrollments = list(
            student.enrollments.select_related("offering", "offering__subject", "organization").order_by(
                "offering__subject__code"
            )
        )
        offerings = [enrollment.offering for enrollment in enrollments]
        for offering in offerings:
            offering.lesson_hours = 60
            offering.instructor = teacher
            offering.save(update_fields=["lesson_hours", "instructor"])
    return SimpleNamespace(
        org=org,
        owner=owner,
        group=group,
        period=period,
        subjects=subjects,
        center=center,
        teacher=teacher,
        student=student,
        enrollments=enrollments,
        offerings=offerings,
    )


class _TwoTenantCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = build_tenant("essi_a")
        cls.b = build_tenant("essi_b")


@override_settings(MEDIA_ROOT=_MEDIA)
class SheetModelCleanTest(_TwoTenantCase):
    """I1 + I4 — ``ExamScoreSheet.clean()``."""

    def _sheet(self, **kwargs):
        defaults = {"organization": self.a.org, "offering": self.a.offerings[0], "created_by_name": "test"}
        defaults.update(kwargs)
        return ExamScoreSheet(**defaults)

    def test_offering_must_belong_to_sheet_organization(self):
        sheet = self._sheet(organization=self.b.org)
        with self.assertRaises(ValidationError) as caught:
            sheet.full_clean(exclude=["created_by", "examiner"])
        self.assertIn("offering", caught.exception.message_dict)

    def test_evidence_must_live_under_own_organization_prefix(self):
        sheet = self._sheet(evidence=f"exam_score_sheets/{self.b.org.id}/CODEX_TEST.pdf")
        with self.assertRaises(ValidationError) as caught:
            sheet.full_clean(exclude=["created_by", "examiner"])
        self.assertIn("evidence", caught.exception.message_dict)

        sheet = self._sheet(evidence="journal_corrections/CODEX_TEST.pdf")
        with self.assertRaises(ValidationError):
            sheet.full_clean(exclude=["created_by", "examiner"])

        sheet = self._sheet(evidence=f"{exam_score_sheet_evidence_prefix(self.a.org.id)}CODEX_TEST.pdf")
        sheet.full_clean(exclude=["created_by", "examiner"])  # keçir

    def test_fresh_upload_is_not_flagged_and_lands_under_prefix(self):
        # Yeni yüklənən fayl hələ ``upload_to``-dan keçməyib — adı «verq.pdf»-dir;
        # ``clean()`` onu prefikssiz deyə rədd etməməlidir; ``save()`` prefiksə qoyur.
        sheet = self._sheet(evidence=_pdf())
        sheet.full_clean(exclude=["created_by", "examiner"])
        sheet.save()
        self.assertTrue(sheet.evidence.name.startswith(exam_score_sheet_evidence_prefix(self.a.org.id)))
        sheet.full_clean(exclude=["created_by", "examiner"])  # saxlanmış ad da keçir


class EntryModelCleanTest(_TwoTenantCase):
    """I3 — ``ExamScoreEntry.clean()``."""

    def _entry(self, **kwargs):
        defaults = {
            "organization": self.a.org,
            "enrollment": self.a.enrollments[0],
            "new_score": Decimal("10"),
            "entered_by_name": "test",
        }
        defaults.update(kwargs)
        return ExamScoreEntry(**defaults)

    def _errors(self, entry):
        with self.assertRaises(ValidationError) as caught:
            entry.full_clean(exclude=["entered_by", "sheet"])
        return caught.exception.message_dict

    def test_enrollment_must_belong_to_entry_organization(self):
        self.assertIn("enrollment", self._errors(self._entry(organization=self.b.org)))

    def test_sheet_must_share_organization_and_offering(self):
        other_offering_sheet = sheets.create_sheet(offering=self.a.offerings[1], by_user=self.a.center)
        self.assertIn("sheet", self._errors(self._entry(sheet=other_offering_sheet)))

        foreign_sheet = sheets.create_sheet(offering=self.b.offerings[0], by_user=self.b.center)
        self.assertIn("sheet", self._errors(self._entry(sheet=foreign_sheet)))

        own_sheet = sheets.create_sheet(offering=self.a.offerings[0], by_user=self.a.center)
        self._entry(sheet=own_sheet).full_clean(exclude=["entered_by", "sheet"])  # keçir


@override_settings(MEDIA_ROOT=_MEDIA)
class SheetServiceGuardTest(_TwoTenantCase):
    """Servis qatı: I2 (yoxlayan), I3 (vərəq ↔ açılış) — fail-closed, düzgün yol işləyir."""

    def _csv(self, score="32"):
        return SimpleUploadedFile(
            "CODEX_TEST_scores.csv", f"username,score\n{self.a.student.username},{score}\n".encode()
        )

    def _plan(self):
        roster = service.roster_for_offering(offering=self.a.offerings[0])
        return importer.build_plan(roster=roster, rows=importer.read_rows(self._csv()))

    # ── I2: yoxlayan müəllim ─────────────────────────────────────────────
    def test_create_sheet_rejects_examiner_without_active_membership(self):
        with self.assertRaises(ValidationError):
            sheets.create_sheet(offering=self.a.offerings[0], by_user=self.a.center, examiner=self.b.teacher)
        self.assertFalse(ExamScoreSheet.objects.filter(offering=self.a.offerings[0]).exists())

        Membership.objects.filter(user=self.a.center, organization=self.a.org).update(is_active=False)
        with self.assertRaises(ValidationError):
            sheets.create_sheet(offering=self.a.offerings[0], by_user=self.a.center, examiner=self.a.center)

    def test_create_sheet_accepts_member_examiner_and_defaults_to_instructor(self):
        explicit = sheets.create_sheet(offering=self.a.offerings[0], by_user=self.a.center, examiner=self.a.center)
        self.assertEqual(explicit.examiner_id, self.a.center.pk)
        default = sheets.create_sheet(offering=self.a.offerings[0], by_user=self.a.center)
        self.assertEqual(default.examiner_id, self.a.teacher.pk)
        self.assertEqual(default.organization_id, self.a.org.pk)

    # ── I3: vərəq ↔ açılış ───────────────────────────────────────────────
    def test_record_exam_score_rejects_sheet_of_other_offering(self):
        sheet = sheets.create_sheet(offering=self.a.offerings[1], by_user=self.a.center)
        with self.assertRaises(ValidationError):
            service.record_exam_score(enrollment=self.a.enrollments[0], score="40", by_user=self.a.center, sheet=sheet)
        self.assertFalse(ExamScoreEntry.objects.filter(enrollment=self.a.enrollments[0]).exists())
        self.assertFalse(FinalGrade.objects.filter(enrollment=self.a.enrollments[0]).exists())

    def test_record_exam_score_rejects_sheet_of_other_tenant(self):
        sheet = sheets.create_sheet(offering=self.b.offerings[0], by_user=self.b.center)
        with self.assertRaises(ValidationError):
            service.record_exam_score(enrollment=self.a.enrollments[0], score="40", by_user=self.a.center, sheet=sheet)
        self.assertFalse(ExamScoreEntry.objects.filter(enrollment=self.a.enrollments[0]).exists())

    def test_record_exam_score_attaches_entry_to_matching_sheet(self):
        sheet = sheets.create_sheet(offering=self.a.offerings[0], by_user=self.a.center, protocol_number="P-7")
        entry = service.record_exam_score(
            enrollment=self.a.enrollments[0], score="40", by_user=self.a.center, sheet=sheet
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry.sheet_id, sheet.pk)
        self.assertEqual(entry.organization_id, sheet.organization_id)

    def test_save_roster_scores_fails_closed_before_any_row(self):
        sheet = sheets.create_sheet(offering=self.a.offerings[1], by_user=self.a.center)
        rows = [{"enrollment_id": str(self.a.enrollments[0].pk), "score": "40"}]
        with self.assertRaises(ValidationError):
            service.save_roster_scores(offering=self.a.offerings[0], rows=rows, by_user=self.a.center, sheet=sheet)
        self.assertFalse(ExamScoreEntry.objects.filter(enrollment=self.a.enrollments[0]).exists())

    # ── idxal axını ──────────────────────────────────────────────────────
    def test_apply_plan_attaches_entries_to_the_right_sheet(self):
        sheet = sheets.create_sheet(offering=self.a.offerings[0], by_user=self.a.center, protocol_number="IMP-1")
        result = importer.apply_plan(
            offering=self.a.offerings[0], plan=self._plan(), by_user=self.a.center, sheet=sheet
        )
        self.assertEqual(result["written"], 1)
        entry = ExamScoreEntry.objects.get(enrollment=self.a.enrollments[0])
        self.assertEqual(entry.sheet_id, sheet.pk)
        self.assertEqual(entry.new_score, Decimal("32"))
        sheets.finalize_sheet(sheet, result, by_user=self.a.center)
        sheet.refresh_from_db()
        self.assertEqual((sheet.rows_total, sheet.rows_written, sheet.rows_failed), (1, 1, 0))

    def test_apply_plan_rejects_sheet_of_other_offering(self):
        sheet = sheets.create_sheet(offering=self.a.offerings[1], by_user=self.a.center)
        with self.assertRaises(ValidationError):
            importer.apply_plan(offering=self.a.offerings[0], plan=self._plan(), by_user=self.a.center, sheet=sheet)
        self.assertFalse(ExamScoreEntry.objects.filter(enrollment=self.a.enrollments[0]).exists())


class SheetGuardQueryBudgetTest(_TwoTenantCase):
    """P2-09 qoruyucularının qiyməti: ``clean()`` + ``assert_sheet_matches`` keşlənmiş
    əlaqələrlə işləyir (0 sorğu); yoxlayan üzvlüyü yalnız AÇIQ verilən, müəllimdən
    fərqli şəxs üçün 1 sorğudur."""

    def test_record_exam_score_with_sheet_costs_no_extra_queries(self):
        sheet = sheets.create_sheet(offering=self.a.offerings[1], by_user=self.a.center)
        # 2026-09-14: hər iki ölçü eyni (soyuq) keş vəziyyətindən başlasın — test sırasından
        # asılı olaraq hərf-şkalası/sxem keşi bir tərəfi isidib 3 sorğu fərqi verirdi.
        from django.contrib.contenttypes.models import ContentType

        from apps.audit.models import AuditLog

        # 2026-09-14: `AuditLog` manager-i prosesdə BİR dəfə sxem introspeksiyası edir
        # (2 sorğu) — hansı ölçü əvvəl gəlirsə onu ödəyirdi (xdist-də sıra dəyişir).
        # Hər iki ölçüdən əvvəl isidilir; keşlər isə hər ikisi üçün soyuq edilir.
        AuditLog.objects._missing_field_names(AuditLog.objects.db)
        cache.clear()
        ContentType.objects.clear_cache()
        with CaptureQueriesContext(connection) as without_sheet:
            service.record_exam_score(enrollment=self.a.enrollments[0], score="40", by_user=self.a.center)
        cache.clear()
        ContentType.objects.clear_cache()
        with CaptureQueriesContext(connection) as with_sheet:
            service.record_exam_score(enrollment=self.a.enrollments[1], score="40", by_user=self.a.center, sheet=sheet)
        self.assertEqual(len(with_sheet), len(without_sheet))
        self.assertEqual(ExamScoreEntry.objects.filter(sheet=sheet).count(), 1)

    def test_create_sheet_examiner_check_costs_one_query_only_when_explicit(self):
        with CaptureQueriesContext(connection) as default_path:
            sheets.create_sheet(offering=self.a.offerings[0], by_user=self.a.center)
        with CaptureQueriesContext(connection) as explicit:
            sheets.create_sheet(offering=self.a.offerings[0], by_user=self.a.center, examiner=self.a.center)

        def membership_queries(captured):
            return [q["sql"] for q in captured.captured_queries if "organizations_membership" in q["sql"]]

        # Defolt yol (açılışın müəllimi) üzvlük sorğusu ETMİR; açıq verilən yoxlayan
        # üçün DÜZ BİR üzvlük sorğusu var. Ümumi say müqayisəsi aldadıcıdır: defolt
        # yol `offering.instructor`-u lazy yükləyir, açıq yol isə onu ötürür.
        self.assertEqual(membership_queries(default_path), [])
        self.assertEqual(len(membership_queries(explicit)), 1)
        self.assertLessEqual(len(explicit), len(default_path) + 1)
