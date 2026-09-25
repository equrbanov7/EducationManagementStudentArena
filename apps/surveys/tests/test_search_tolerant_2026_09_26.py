"""Sorğu nəticələrində axtarış kanonik ``core.search_text.tolerant_q`` ilədir (sahib 2026-09-26).

Səhnə ``test_results_api.ResultsApiTest``-in eyni ``setUpTestData``-sıdır (testləri təkrarlanmır).
"""

from __future__ import annotations

from django.test import TestCase

from apps.surveys import public
from core.rls import bypass_rls

from . import test_results_api as _base  # modul importu: ResultsApiTest burada TƏKRAR toplanmasın


class SurveyTolerantSearchTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        _base.ResultsApiTest.setUpTestData.__func__(cls)
        teacher = cls.w["teacher_a"]
        teacher.first_name, teacher.last_name = "Şahzad", "Əliyev"
        teacher.save(update_fields=["first_name", "last_name"])

    def _scope(self):
        with bypass_rls():
            return public.results_scope(self.rector, self.w["org"])

    def test_teacher_search_folds_azerbaijani_letters(self):
        scope = self._scope()
        for query in ("Aliyev", "shahzad", "sahzad eliyev"):
            with self.subTest(query=query):
                with bypass_rls():
                    found = public.search_teachers(self.w["org"], scope, query)
                self.assertEqual({row["id"] for row in found}, {self.w["teacher_a"].pk})
        with bypass_rls():
            self.assertEqual(public.search_teachers(self.w["org"], scope, "Zzqx"), [])

    def test_comment_search_is_case_and_letter_tolerant(self):
        with bypass_rls():
            found = public.general_suggestions(self.w["org"], self._scope(), query="KİTABXANA")
        self.assertEqual(len(found["items"]), 5)
        self.assertTrue(all("Kitabxana" in item["text"] for item in found["items"]))
