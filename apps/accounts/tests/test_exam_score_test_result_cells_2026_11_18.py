"""Sahib 2026-11-18 — «İmtahan balının daxil edilməsi»:

* bal TESTDƏN gəlibsə (ekranda imtahan yazısı yoxdur, müəllimin əl yazısı deyil) S-xanaları kilidlidir və tək sütunda
  S1 yekunu göstərir; düzəliş yalnız «Apellyasiya balı» ilə;
* «Apellyasiya balı» S-xanaları kimi seçimdir, yekun sütundan ƏVVƏL gəlir (sütun sırası şablon testindədir).
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.accounts.templatetags.exam_score_cells import ese_question_cells
from apps.accounts.views.profile._sections.exam_score_entry_offering import _attach_question_cells


def _row(**extra):
    row = {
        "enrollment": SimpleNamespace(id="e1"),
        "name": "Tələbə",
        "exam_score": 28,
        "has_score": True,
        "question_scores": [],
        "entries": [],
    }
    row.update(extra)
    return row


class TestResultCellsTest(SimpleTestCase):
    def test_test_score_fills_s1_and_locks_it(self):
        row = _row()
        _attach_question_cells([row], 10, [30])
        self.assertTrue(row["from_test"])
        self.assertEqual(row["question_cells"][0]["value"], "28")
        html = ese_question_cells(row)
        first = html.split("</td>")[0]
        self.assertIn('<option value="28" selected>28</option>', first)
        self.assertIn(" disabled", first)

    def test_screen_written_and_teacher_written_scores_stay_editable(self):
        screen = _row(entries=[{"kind": "initial", "new": "28"}], question_scores=[28])
        teacher = _row(teacher_written=True)
        empty = _row(exam_score=None, has_score=False)
        _attach_question_cells([screen, teacher, empty], 10, [30])
        self.assertEqual([r["from_test"] for r in (screen, teacher, empty)], [False, False, False])
        self.assertEqual(teacher["question_cells"][0]["value"], "")

    def test_appeal_on_test_score_keeps_s1_as_test_result(self):
        row = _row(
            entries=[{"kind": "appeal", "old": "28", "new": "30"}],
            appeal_set=True,
            exam_base_display="28",
        )
        _attach_question_cells([row], 10, [30])
        self.assertTrue(row["from_test"])
        self.assertEqual(row["question_cells"][0]["value"], "28")

    def test_multi_column_test_score_is_locked_but_not_split(self):
        row = _row(exam_score=40)
        _attach_question_cells([row], 10, [10, 10, 10, 10, 10])
        self.assertTrue(row["from_test"])
        self.assertEqual([cell["value"] for cell in row["question_cells"][:5]], [""] * 5)
