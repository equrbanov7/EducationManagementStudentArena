"""``exam_score_sheets/`` media checker — org-prefiks və tenant sərhədi (Codex audit P2-09, 2026-09-13).

``check_exam_score_sheet_access`` sətri ``evidence = path`` (DƏQİQ ad) ilə tapır və
təşkilatı SƏTİRDƏN oxuyur. Yoxlanır ki:

* başqa təşkilatın prefiksi altındakı yol A-nın sətrini TAPA BİLMİR — yol
  yalnız həmin adı daşıyan sətri qaytarır, «prefiks»ə görə heç nə seçilmir;
* sətrin skanı öz təşkilat prefiksindən kənara göstərilə bilmir
  (``ExamScoreSheet.clean()``; PostgreSQL-də eyni yazı ``0073`` trigger-i ilə də
  rədd olunur — bax ``apps/registrar/tests/test_exam_score_sheet_integrity_postgres.py``);
* yad tenantın imtahan mərkəzi A-nın vərəqini görmür (fail-closed).
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.registrar import exam_score_sheets as sheets
from apps.registrar.tests.test_exam_score_sheet_invariants import build_tenant
from core.media_policies import check_exam_score_sheet_access
from core.media_views import _is_private


class ExamScoreSheetMediaPolicyTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = build_tenant("mess_a")
        cls.b = build_tenant("mess_b")

    def _sheet_with_path(self, tenant, path):
        sheet = sheets.create_sheet(offering=tenant.offerings[0], by_user=tenant.center)
        sheet.evidence = path
        sheet.save(update_fields=["evidence"])
        return sheet

    def test_prefix_is_private(self):
        self.assertTrue(_is_private(f"exam_score_sheets/{self.a.org.id}/CODEX_TEST.pdf"))

    def test_lookup_is_exact_and_organization_comes_from_the_row(self):
        path = f"exam_score_sheets/{self.a.org.id}/CODEX_TEST.pdf"
        self._sheet_with_path(self.a, path)

        self.assertTrue(check_exam_score_sheet_access(self.a.center, path))
        self.assertTrue(check_exam_score_sheet_access(self.a.teacher, path))
        # Yad tenantın imtahan mərkəzi / müəllimi — sətrin təşkilatı A-dır.
        self.assertFalse(check_exam_score_sheet_access(self.b.center, path))
        self.assertFalse(check_exam_score_sheet_access(self.b.teacher, path))
        # B-nin prefiksi altındakı eyni fayl adı A-nın sətrini seçmir (sətir yoxdur).
        self.assertFalse(
            check_exam_score_sheet_access(self.a.center, f"exam_score_sheets/{self.b.org.id}/CODEX_TEST.pdf")
        )
        self.assertFalse(
            check_exam_score_sheet_access(self.b.center, f"exam_score_sheets/{self.b.org.id}/CODEX_TEST.pdf")
        )
        # A-nın prefiksi altında başqa ad da sətirsizdir.
        self.assertFalse(check_exam_score_sheet_access(self.a.center, f"exam_score_sheets/{self.a.org.id}/other.pdf"))

    def test_same_file_name_in_two_tenants_resolves_to_each_tenants_own_row(self):
        path_a = f"exam_score_sheets/{self.a.org.id}/CODEX_TEST.pdf"
        path_b = f"exam_score_sheets/{self.b.org.id}/CODEX_TEST.pdf"
        self._sheet_with_path(self.a, path_a)
        self._sheet_with_path(self.b, path_b)
        self.assertTrue(check_exam_score_sheet_access(self.a.center, path_a))
        self.assertFalse(check_exam_score_sheet_access(self.a.center, path_b))
        self.assertTrue(check_exam_score_sheet_access(self.b.center, path_b))
        self.assertFalse(check_exam_score_sheet_access(self.b.center, path_a))

    def test_sheet_cannot_point_outside_its_own_organization_prefix(self):
        sheet = sheets.create_sheet(offering=self.a.offerings[0], by_user=self.a.center)
        sheet.evidence = f"exam_score_sheets/{self.b.org.id}/CODEX_TEST.pdf"
        with self.assertRaises(ValidationError) as caught:
            sheet.full_clean(exclude=["created_by", "examiner"])
        self.assertIn("evidence", caught.exception.message_dict)
