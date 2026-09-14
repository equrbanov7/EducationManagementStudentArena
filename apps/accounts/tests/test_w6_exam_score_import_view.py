"""W6 `w6paper` (2026-09-14) — kağız bal idxalı view-ları: şablon şəbəkəsi, quru icra = tətbiq.

`docs/features/kagiz_imtahan_bali.md` §10 «məlum açıq məqamlar»:

* `exam_score_import_template` ``?question_count`` / ``?question_max`` /
  ``?exam_kind`` ilə şablon verir; parametr yoxdursa SONUNCU vərəqin şəbəkəsi
  (vərəq məlumatları kartının ilkin dəyərləri ilə eyni mənbə); yanlış → 400;
* `exam_score_import_preview` POST şəbəkəsini plana ötürür — 3 sual seçilibsə
  S4 dəyəri quru icrada da, tətbiqdə də EYNİ mesajla rədd olunur; heç nə yazılmır;
* `_import.html` keçidləri `data-esi-template` daşıyır (JS klik anında şəbəkəni
  URL-ə yazır).
"""

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.tests import test_exam_score_entry_section as fixtures
from apps.registrar import exam_score_sheets as sheets
from apps.registrar.models import ExamScoreEntry, ExamScoreSheet, FinalGrade
from apps.registrar.models.exam_score_entry import ExamScoreSheetKind
from core.rls import bypass_rls

PRACTICAL_LABEL = str(ExamScoreSheetKind.PRACTICAL.label)
WRITTEN_LABEL = str(ExamScoreSheetKind.WRITTEN.label)


@override_settings(UNIVERSITY_MODE=True, MEDIA_ROOT=fixtures._MEDIA)
class ImportViewGridTest(TestCase):
    """Bölmə fixture-u KOMPOZİSİYA ilə (`test_exam_score_import.py` naxışı) — köhnə testlər təkrar yığılmır."""

    setUpTestData = classmethod(fixtures.ExamScoreEntrySectionTest.setUpTestData.__func__)
    _client = fixtures.ExamScoreEntrySectionTest._client

    def _csv(self, *questions):
        line = ",".join([self.student.username, *questions])
        header = ",".join(["username", *[f"S{i}" for i in range(1, len(questions) + 1)]])
        return SimpleUploadedFile("QA_TEST_ballar.csv", f"{header}\n{line}\n".encode())

    def _template_header(self, **params):
        response = self._client(self.center).get(
            reverse("accounts:exam_score_import_template"),
            {"offering": self.offering.pk, "format": "csv", **params},
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8-sig").splitlines()

    # ── şablon ───────────────────────────────────────────────────────────────
    def test_template_honours_query_grid_and_kind(self):
        header, first = self._template_header(question_count="3", question_max="7", exam_kind="practical")[:2]
        self.assertIn("S3 (0–7)", header)
        self.assertNotIn("S4", header)
        self.assertIn(PRACTICAL_LABEL, first)

    def test_template_defaults_to_last_sheet_grid(self):
        header = self._template_header()[0]
        self.assertIn("S5 (0–10)", header)  # vərəq yoxdur → defolt 5 × 10
        with bypass_rls():
            sheets.create_sheet(
                offering=self.offering,
                by_user=self.center,
                question_count=2,
                question_max=6,
                exam_kind="practical",
                protocol_number="P-W6",
                evidence=fixtures._pdf(),
            )
        header, first = self._template_header()[:2]
        self.assertIn("S2 (0–6)", header)
        self.assertNotIn("S3", header)
        self.assertIn(PRACTICAL_LABEL, first)
        # Açıq parametr sonuncu vərəqi üstələyir.
        header, first = self._template_header(question_count="1", exam_kind="written")[:2]
        self.assertIn("S1 (0–6)", header)  # question_max verilməyib → vərəqdən (6)
        self.assertNotIn("S2", header)
        self.assertIn(WRITTEN_LABEL, first)

    def test_template_clamps_legacy_sheet_max_but_rejects_explicit_param(self):
        # Tavan-10 qaydasından ƏVVƏLKİ vərəq (max 20): parametrsiz endirmə 400 verməməlidir.
        with bypass_rls():
            sheet = sheets.create_sheet(
                offering=self.offering,
                by_user=self.center,
                question_count=4,
                protocol_number="P-OLD",
                evidence=fixtures._pdf(),
            )
            ExamScoreSheet.objects.filter(pk=sheet.pk).update(question_max=20)
        header = self._template_header()[0]
        self.assertIn("S4 (0–10)", header)
        response = self._client(self.center).get(
            reverse("accounts:exam_score_import_template"), {"offering": self.offering.pk, "question_max": "20"}
        )
        self.assertEqual(response.status_code, 400)

    def test_template_rejects_invalid_grid(self):
        for params in ({"question_count": "11"}, {"question_max": "11"}, {"exam_kind": "oral"}):
            response = self._client(self.center).get(
                reverse("accounts:exam_score_import_template"), {"offering": self.offering.pk, **params}
            )
            self.assertEqual(response.status_code, 400, params)
            self.assertEqual(response.json()["error"], "validation_error")

    def test_template_links_carry_grid_hook(self):
        response = self._client(self.center).get(
            reverse("accounts:profile"), {"section": "exam-score-entry", "ese_offering": self.offering.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode().count("data-esi-template"), 2)

    # ── quru icra = tətbiq ───────────────────────────────────────────────────
    def _post(self, action, upload, **grid):
        return self._client(self.center).post(
            reverse(f"accounts:exam_score_import_{action}"),
            {"offering_id": self.offering.pk, "file": upload, **grid},
        )

    def test_preview_with_three_questions_rejects_s4_exactly_like_apply(self):
        grid = {"question_count": "3", "question_max": "10"}
        preview = self._post("preview", self._csv("5", "5", "5", "5"), **grid)
        self.assertEqual(preview.status_code, 200)
        row = preview.json()["rows"][0]
        self.assertEqual(row["status"], "error")
        self.assertIn("(3)", row["message"])
        self.assertEqual(preview.json()["summary"]["writes"], 0)
        applied = self._post("apply", self._csv("5", "5", "5", "5"), **grid)
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.json()["rows"][0]["message"], row["message"])
        self.assertEqual(applied.json()["result"]["written"], 0)
        self.assertFalse(FinalGrade.objects.filter(enrollment=self.enrollment, exam_score__isnull=False).exists())
        self.assertEqual(ExamScoreEntry.objects.count(), 0)
        # Rədd olunan sətir partiya tarixçəsində görünür (mövcud qayda: yazılan=0, rədd=1).
        sheet = ExamScoreSheet.objects.get()
        self.assertEqual((sheet.rows_written, sheet.rows_failed, sheet.question_count), (0, 1, 3))

    def test_preview_and_apply_agree_on_question_max(self):
        grid = {"question_count": "3", "question_max": "5"}
        preview = self._post("preview", self._csv("6", "1", "1"), **grid).json()
        self.assertEqual(preview["rows"][0]["status"], "error")
        self.assertIn("S1", preview["rows"][0]["message"])
        ok_preview = self._post("preview", self._csv("5", "4", "3"), **grid).json()
        self.assertEqual(ok_preview["rows"][0]["status"], "new")
        self.assertEqual(ok_preview["rows"][0]["question_scores"], [5, 4, 3])
        self.assertEqual(ok_preview["rows"][0]["score"], "12")
        applied = self._post("apply", self._csv("5", "4", "3"), **grid).json()
        self.assertTrue(applied["rows"][0]["written"])
        self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal(12))
        self.assertEqual(ExamScoreEntry.objects.get().question_scores, [5, 4, 3])
        sheet = ExamScoreSheet.objects.get()
        self.assertEqual((sheet.question_count, sheet.question_max), (3, 5))

    def test_preview_rejects_invalid_grid_before_building_plan(self):
        response = self._post("preview", self._csv("1"), question_count="12")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "validation_error")
        self.assertEqual(ExamScoreEntry.objects.count(), 0)

    def test_kind_column_mismatch_is_row_error_in_preview_and_apply(self):
        upload = SimpleUploadedFile(
            "QA_TEST_nov.csv",
            f"username,İmtahan növü,S1\n{self.student.username},{PRACTICAL_LABEL},7\n".encode(),
        )
        preview = self._post("preview", upload, exam_kind="written", question_count="1").json()
        self.assertEqual(preview["rows"][0]["status"], "error")
        self.assertIn(WRITTEN_LABEL, preview["rows"][0]["message"])
        upload.seek(0)
        ok = self._post("preview", upload, exam_kind="practical", question_count="1").json()
        self.assertEqual(ok["rows"][0]["status"], "new")
