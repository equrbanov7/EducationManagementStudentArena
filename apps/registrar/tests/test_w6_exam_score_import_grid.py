"""W6 `w6paper` (2026-09-14) — kağız bal idxalı: şablon vərəqin şəbəkəsi ilə, «İmtahan növü» sütunu, plan şəbəkəsi.

`docs/features/kagiz_imtahan_bali.md` §10-dakı «məlum açıq məqamlar»:

* şablon (CSV / XLSX) ``question_count`` / ``question_max`` / ``exam_kind`` ilə
  gəlir — S sütunlarının sayı və tavanı, «İmtahan növü» sütunu cari dildə etiket;
* başlıq sətri oxuyucu ilə uyğundur (şablonu olduğu kimi geri yükləyəndə
  «İmtahan növü» ``exam_kind`` açarına düşür, S sütunları ``q<n>``);
* ``build_plan(..., exam_kind=)`` sətrin növ xanasını vərəqin növü ilə tutuşdurur
  (boş xana sərbəst; fərqli növ → sətir xətası);
* ``build_plan(..., question_count=3)`` S4 dəyərini rədd edir — view eyni
  şəbəkəni quru icraya da ötürür (`apps/accounts/tests/test_w6_exam_score_import_view.py`).
"""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.registrar import exam_score_entry as service
from apps.registrar import exam_score_import as importer
from apps.registrar.models.exam_score_entry import ExamScoreSheetKind
from apps.registrar.tests import test_exam_score_entry as fixtures
from core.rls import bypass_rls

WRITTEN_LABEL = str(ExamScoreSheetKind.WRITTEN.label)
PRACTICAL_LABEL = str(ExamScoreSheetKind.PRACTICAL.label)


@override_settings(MEDIA_ROOT=fixtures._MEDIA)
class ImportTemplateGridTest(TestCase):
    """Şablon + plan — mövcud iki-qruplu fixture üzərində (``setUp`` KOMPOZİSİYA ilə: köhnə testlər təkrar yığılmır)."""

    setUp = fixtures.ExamScoreEntryServiceTest.setUp

    def _roster(self):
        with bypass_rls():
            return service.roster_for_offering(offering=self.offering_a)

    def _csv_lines(self, **grid):
        payload, ctype, name = importer.build_template(roster=self._roster(), fmt="csv", **grid)
        self.assertEqual(ctype, "text/csv; charset=utf-8")
        self.assertTrue(name.endswith(".csv"))
        return payload.decode("utf-8-sig").splitlines()

    # ── şablon ───────────────────────────────────────────────────────────────
    def test_template_uses_given_grid_and_kind(self):
        header, first = self._csv_lines(question_count=3, question_max=7, exam_kind="practical")[:2]
        self.assertIn("S3 (0–7)", header)
        self.assertNotIn("S4", header)
        self.assertNotIn("(0–10)", header)
        self.assertIn(PRACTICAL_LABEL, first)
        self.assertNotIn(WRITTEN_LABEL, first)

    def test_template_defaults_to_written_and_five_by_ten(self):
        header, first = self._csv_lines()[:2]
        self.assertIn("S5 (0–10)", header)
        self.assertNotIn("S6", header)
        self.assertIn(WRITTEN_LABEL, first)
        self.assertEqual(importer.exam_kind_label(""), WRITTEN_LABEL)
        self.assertEqual(importer.exam_kind_label("practical"), PRACTICAL_LABEL)

    def test_template_zero_questions_has_no_s_columns(self):
        header = self._csv_lines(question_count=0)[0]
        self.assertNotIn("S1", header)

    def test_template_columns_order_matches_reader(self):
        columns = importer.template_columns(50, 2, 10)
        self.assertEqual(columns[4:7], ["İmtahan növü", "Cari bal", "Bal (0–50)"])
        self.assertEqual(columns[7:], ["S1 (0–10)", "S2 (0–10)"])

    def test_csv_template_round_trips_through_reader(self):
        lines = self._csv_lines(question_count=3, question_max=10, exam_kind="written")
        # Operator yalnız S xanalarını doldurur — başlıq olduğu kimi qalır.
        cells = lines[1].split(",")
        cells[-3:] = ["4", "5", "6"]
        uploaded = SimpleUploadedFile("sablon.csv", ("\n".join([lines[0], ",".join(cells)]) + "\n").encode())
        rows = importer.read_rows(uploaded)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["exam_kind"], WRITTEN_LABEL)
        self.assertEqual(rows[0]["questions"], {1: "4", 2: "5", 3: "6"})
        plan = importer.build_plan(
            roster=self._roster(), rows=rows, question_count=3, question_max=10, exam_kind="written"
        )
        self.assertEqual(plan[0]["status"], importer.STATUS_NEW)
        self.assertEqual(plan[0]["score"], "15")
        self.assertEqual(plan[0]["question_scores"], [4, 5, 6])

    def test_xlsx_template_round_trips_and_has_kind_list_validation(self):
        openpyxl = __import__("openpyxl")
        payload, ctype, name = importer.build_template(
            roster=self._roster(), fmt="xlsx", question_count=2, question_max=8, exam_kind="practical"
        )
        self.assertTrue(name.endswith(".xlsx"))
        workbook = openpyxl.load_workbook(io.BytesIO(payload))
        sheet = workbook[importer.SHEET_NAME]
        header = [cell.value for cell in sheet[1]]
        self.assertEqual(header[4], "İmtahan növü")
        self.assertEqual(header[7:], ["S1 (0–8)", "S2 (0–8)"])
        self.assertEqual(sheet["E2"].value, PRACTICAL_LABEL)
        ranges = {str(dv.sqref): (dv.type, dv.formula1, dv.formula2) for dv in sheet.data_validations.dataValidation}
        last = sheet.max_row
        self.assertEqual(ranges[f"E2:E{last}"][0], "list")
        self.assertIn(PRACTICAL_LABEL, ranges[f"E2:E{last}"][1])
        self.assertEqual(ranges[f"G2:G{last}"][:1], ("whole",))
        self.assertEqual(ranges[f"H2:I{last}"], ("whole", "0", "8"))
        # Eyni faylı oxuyucu tanıyır (başlıq sətri parser ilə uyğundur).
        sheet["H2"], sheet["I2"] = 3, 4
        buffer = io.BytesIO()
        workbook.save(buffer)
        rows = importer.read_rows(SimpleUploadedFile("sablon.xlsx", buffer.getvalue()))
        self.assertEqual(rows[0]["questions"], {1: "3", 2: "4"})
        self.assertEqual(rows[0]["exam_kind"], PRACTICAL_LABEL)

    # ── plan şəbəkəsi ────────────────────────────────────────────────────────
    def _rows(self, questions, exam_kind=""):
        return [
            {
                "_row": 2,
                "key": self.students["a1"].username,
                "score": "",
                "exam_kind": exam_kind,
                "questions": dict(enumerate(questions, start=1)),
            }
        ]

    def test_plan_with_three_questions_rejects_s4_like_apply(self):
        rows = self._rows(["5", "5", "5", "5"])
        loose = importer.build_plan(roster=self._roster(), rows=rows)
        self.assertEqual(loose[0]["status"], importer.STATUS_NEW)  # şəbəkəsiz: fayldan 4 sual
        strict = importer.build_plan(roster=self._roster(), rows=rows, question_count=3, question_max=10)
        self.assertEqual(strict[0]["status"], importer.STATUS_ERROR)
        self.assertIn("(3)", strict[0]["message"])

    def test_plan_question_max_from_grid(self):
        rows = self._rows(["6", "1"])
        plan = importer.build_plan(roster=self._roster(), rows=rows, question_count=5, question_max=5)
        self.assertEqual(plan[0]["status"], importer.STATUS_ERROR)
        self.assertIn("S1", plan[0]["message"])

    def test_plan_kind_cell_matches_or_errors(self):
        roster = self._roster()
        for cell in ("", WRITTEN_LABEL, "written", "Yazılı", "YAZILI"):
            plan = importer.build_plan(roster=roster, rows=self._rows(["1"], cell), exam_kind="written")
            self.assertEqual(plan[0]["status"], importer.STATUS_NEW, cell)
        for cell in (PRACTICAL_LABEL, "practical", "Praktiki", "nəsə"):
            plan = importer.build_plan(roster=roster, rows=self._rows(["1"], cell), exam_kind="written")
            self.assertEqual(plan[0]["status"], importer.STATUS_ERROR, cell)
            self.assertIn(WRITTEN_LABEL, plan[0]["message"])
        plan = importer.build_plan(roster=roster, rows=self._rows(["1"], PRACTICAL_LABEL), exam_kind="practical")
        self.assertEqual(plan[0]["status"], importer.STATUS_NEW)
        # Növ verilməyəndə (köhnə çağıran) xana yoxlanmır.
        plan = importer.build_plan(roster=roster, rows=self._rows(["1"], PRACTICAL_LABEL))
        self.assertEqual(plan[0]["status"], importer.STATUS_NEW)
