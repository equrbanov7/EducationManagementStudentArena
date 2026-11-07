"""Sahib 2026-11-08: lab qrupu siyahıda ayrıca sətir, jurnalda yalnız o qrup; jurnalın içində növ düymələri yoxdur.

* ``?kind=lab&lab=1`` — yalnız Lab-1 tələbələri və Lab-1 + qrupsuz lab dərsləri, başlıqda «<qrup> · Lab-1»;
  mövcud olmayan qrup → adi görünüş;
* jurnal səhifəsində «Hamısı / Mühazirə / Seminar / Laboratoriya» düymələri (``jd2-kindnav``) yoxdur;
* siyahıda lab qrupu olan jurnalın altında «<qrup> · Lab-N» sətirləri (say + keçid); mühazirə süzgəcində yox.
"""

from django.test import TestCase
from django.urls import reverse

from apps.registrar import journal_lab_view
from apps.registrar.models import LessonKind
from apps.registrar.tests.test_lab_groups_2026_11_06 import _LabWorld
from core.rls import bypass_rls


class JournalLabViewTest(_LabWorld, TestCase):
    def setUp(self):
        self.lab1 = self._lesson(lab_group=1)
        self.lab2 = self._lesson(lab_group=2)
        self.whole = self._lesson()
        self.lecture = self._lesson(kind=LessonKind.LECTURE)

    def _get(self, **params):
        url = reverse("registrar:journal_detail", args=[self.offering.id])
        return self._client(self.teacher).get(url, params)

    def test_lab_view_shows_only_its_students_and_lessons(self):
        response = self._get(kind="lab", lab="1")
        journal = response.context["journal"]
        self.assertEqual([row["enrollment"].pk for row in journal["rows"]], [self.e1.pk])
        self.assertEqual({lesson.pk for lesson in journal["lessons"]}, {self.lab1.pk, self.whole.pk})
        self.assertTrue(all(len(row["cells"]) == 2 for row in journal["rows"]))
        self.assertContains(response, "LAB-G1 · Lab-1")
        self.assertContains(response, 'data-jd-default-lab-group="1"')

    def test_unknown_lab_falls_back_to_normal_view(self):
        journal = self._get(kind="lab", lab="7").context["journal"]
        self.assertEqual(len(journal["rows"]), 3)

    def test_kind_tabs_are_gone(self):
        self.assertNotContains(self._get(), "jd2-kindnav")

    def test_list_rows(self):
        offering = self._fresh()
        with bypass_rls():
            journal_lab_view.attach_list_rows([offering])
        self.assertEqual(
            offering.lab_sections,
            [
                {"number": 1, "label": "LAB-G1 · Lab-1", "count": 1},
                {"number": 2, "label": "LAB-G1 · Lab-2", "count": 1},
            ],
        )
        with bypass_rls():
            journal_lab_view.attach_list_rows([offering], LessonKind.LECTURE)
        self.assertEqual(offering.lab_sections, [])
