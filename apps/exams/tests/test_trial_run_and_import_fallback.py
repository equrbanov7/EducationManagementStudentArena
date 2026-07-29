"""Sınaq (trial) axını + vizual idxal fallback davranışları.

Əhatə olunan şikayətlər (2026-07-29):
  * sualsız/qaralama imtahanda "Sınaq keç" 404 verirdi;
  * layout-u ardıcıl olmayan real bank PDF-i bütün idxalı öldürürdü;
  * END_QUESTION marker-i vizual crop-un içində qalırdı;
  * sınaq cəhdi pozuntu limitində "suspended" vəziyyətində ilişirdi.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.exams.models import Exam
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


def _fixture(suffix=""):
    teacher = User.objects.create_user(
        username=f"trial-teacher{suffix}",
        email=f"trial-teacher{suffix}@example.com",
        password="pass123",
    )
    other = User.objects.create_user(
        username=f"trial-other{suffix}",
        email=f"trial-other{suffix}@example.com",
        password="pass123",
    )
    org = Organization.objects.create(
        name=f"Trial Org{suffix}",
        org_type=OrganizationType.SCHOOL,
        owner=teacher,
        status="active",
        is_active=True,
    )
    teacher.profile.organization = org
    teacher.profile.organization_type = org.org_type
    teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
    return teacher, other, org


class TrialRunStartGuardTests(TestCase):
    """`start_exam` sualsız/deaktiv imtahanda 404 yox, izahlı redirect verir."""

    def setUp(self):
        self.teacher, self.other, self.org = _fixture()

    def _start_url(self, exam):
        return f"{reverse('exams:start_exam', args=[exam.slug])}?trial=1"

    def test_author_gets_redirect_not_404_on_draft_exam(self):
        exam = Exam.objects.create(title="Qaralama", author=self.teacher, organization=self.org, is_active=False)
        self.client.force_login(self.teacher)

        response = self.client.get(self._start_url(exam))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}))

    def test_non_author_still_gets_404_on_draft_exam(self):
        """Deaktiv imtahan başqaları üçün gizli qalır — giriş genişlənməyib."""
        exam = Exam.objects.create(title="Qaralama", author=self.teacher, organization=self.org, is_active=False)
        self.client.force_login(self.other)

        response = self.client.get(self._start_url(exam))

        self.assertEqual(response.status_code, 404)

    def test_author_without_questions_is_sent_back_to_exam_detail(self):
        exam = Exam.objects.create(title="Sualsız", author=self.teacher, organization=self.org, is_active=True)
        self.client.force_login(self.teacher)

        response = self.client.get(self._start_url(exam))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}))


class ExamDefaultDurationTests(TestCase):
    def test_new_exam_defaults_to_60_minutes(self):
        teacher, _other, org = _fixture("-dur")
        exam = Exam.objects.create(title="Default müddət", author=teacher, organization=org)
        self.assertEqual(exam.total_duration_minutes, 60)


class EndQuestionVisualStripTests(TestCase):
    """END_QUESTION seqment mətnindən VƏ qutusundan çıxarılır (crop-da görünməsin)."""

    def _build_pdf(self, marker="END_QUESTION"):
        import fitz

        document = fitz.open()
        page = document.new_page()
        y = 60
        for number in (1, 2, 3):
            for line in (
                f"{number}. Sual {number} nədir?",
                "A) Birinci",
                "B) Ikinci",
                "C) Ucuncu",
                f"D) Dorduncu {marker}",
            ):
                page.insert_text((50, y), line, fontsize=11)
                y += 22
        payload = document.tobytes()
        document.close()
        return payload

    def test_marker_is_not_part_of_option_segment(self):
        """Marker seqment mətnindən VƏ qutusundan çıxmalıdır — crop-da görünməsin."""
        from apps.exams.services.pdf_layout import extract_pdf_layout

        # PDF kimi yükləyəndə istifadəçi alt-xətti təkrarlaya bilər.
        for marker in ("END_QUESTION", "END__QUESTION"):
            with self.subTest(marker=marker):
                manifest = extract_pdf_layout(self._build_pdf(marker), fail_closed=True).to_dict()

                self.assertTrue(manifest["confidence"]["is_confident"])
                self.assertNotIn("QUESTION", (manifest.get("canonical_text") or "").upper())
                for question in manifest["questions"]:
                    for label, segment in question["options"].items():
                        self.assertNotIn(
                            "QUESTION",
                            str(segment.get("text") or "").upper(),
                            msg=f"{label} variantında marker qaldı",
                        )


class EndQuestionParsingTests(TestCase):
    """Marker mətndən çıxır, A konvensiya kimi qəbul olunur, saxta ERROR yoxdur."""

    def _sample(self, marker):
        return (
            f"1. Sual?\nA) Bir\nB) Iki\nC) Uc\nD) Dord\nE) Bes {marker}\n"
            f"2. Ikinci?\nA) Bir\nB) Iki\nC) Uc\nD) Dord\nE) Bes {marker}\n"
        )

    def _analyze(self, marker):
        from apps.exams.services.bulk_workbench import analyze_mcq_bulk

        return (analyze_mcq_bulk(self._sample(marker)) or {}).get("parsed") or []

    def test_single_and_multi_underscore_markers_are_stripped(self):
        # İstifadəçi alt-xətti təkrarlaya bilər — hamısı marker sayılmalıdır.
        for marker in ("END_QUESTION", "END__QUESTION", "END___QUESTION"):
            with self.subTest(marker=marker):
                parsed = self._analyze(marker)
                self.assertEqual(len(parsed), 2)
                for question in parsed:
                    self.assertEqual(question["options"]["E"], "Bes")
                    for label, value in question["options"].items():
                        self.assertNotIn("QUESTION", str(value).upper(), msg=f"{label} variantında qaldı")

    def test_no_false_correct_defaulted_warning_in_end_question_format(self):
        """Bu formatda A razılaşdırılmış cavabdır — 299 saxta ERROR olmamalıdır."""
        for marker in ("END_QUESTION", "END__QUESTION"):
            with self.subTest(marker=marker):
                for question in self._analyze(marker):
                    self.assertEqual(question["correct"], ["A"])
                    types = {w.get("type") for w in (question.get("warnings") or [])}
                    self.assertNotIn("correct_defaulted", types)

    def test_plain_format_still_warns_when_no_marker(self):
        """Reqressiya qoruması: END_QUESTION-suz mətndə xəbərdarlıq QALIR."""
        from apps.exams.services.bulk_workbench import analyze_mcq_bulk

        plain = "1. Sual?\nA) Bir\nB) Iki\nC) Uc\nD) Dord\n"
        parsed = (analyze_mcq_bulk(plain) or {}).get("parsed") or []
        types = {w.get("type") for w in (parsed[0].get("warnings") or [])}
        self.assertIn("correct_defaulted", types)


class WarningTranslationTests(TestCase):
    """`exams.view.question_bank.warning` konteksti raw msgid göstərməməlidir."""

    def test_bank_warning_keys_are_translated(self):
        from django.utils import translation
        from django.utils.translation import pgettext

        keys = (
            "already_in_exam",
            "duplicate_in_import",
            "duplicate_in_import_first",
            "bulk_correct_too_long",
            "bulk_correct_too_short",
        )
        for language in ("az", "en"):
            with translation.override(language):
                for key in keys:
                    with self.subTest(language=language, key=key):
                        self.assertNotEqual(
                            pgettext("exams.view.question_bank.warning", key),
                            key,
                            msg="tərcümə yoxdur — istifadəçi raw açarı görür",
                        )


class VisualImportFallbackTests(TestCase):
    """Ardıcıl olmayan nömrələnmə idxalı dayandırmır — mətnə düşür."""

    def _pdf_with_number_gap(self):
        import fitz

        document = fitz.open()
        page = document.new_page()
        y = 50
        # 9 qəsdən buraxılıb → layout anchor-ları ardıcıl deyil.
        for number in (1, 2, 3, 4, 5, 6, 7, 8, 10, 11):
            for line in (
                f"{number}. Sual {number}?",
                "A) Bir",
                "B) Iki",
                "C) Uc",
                "D) Dord",
            ):
                page.insert_text((50, y), line, fontsize=9)
                y += 13
        payload = document.tobytes()
        document.close()
        return payload

    def test_prepare_question_upload_falls_back_to_text(self):
        from django.core.files.base import ContentFile

        from apps.exams.services.visual_import_upload import prepare_question_upload

        upload = ContentFile(self._pdf_with_number_gap(), name="gap.pdf")

        text, token = prepare_question_upload(upload, owner_id=1, organization_id=1)

        # Vizual token verilmir, amma mətn tam işlək qalır (xəta ATILMIR).
        self.assertEqual(token, "")
        self.assertIn("Sual 1", text)
        self.assertIn("Sual 11", text)
