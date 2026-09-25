"""Cədvəl generatoru axtarışları dözümlüdür (sahib 2026-09-26).

* «Əlçatanlıq»: müəllim adı az/ing hərfinə dözümlü («Aliyev» → «Əliyev»);
* «Qaydalar»: qrup adı kod rejimində («a101» → «A-101», «A-102» yox).
"""

from __future__ import annotations

from django.test import Client, TestCase
from django.urls import reverse

from apps.timetable.tests.fixtures import build_world


class TimetableTolerantSearchTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("tts")
        cls.teacher = cls.w["teachers"][0]
        cls.teacher.first_name, cls.teacher.last_name = "Şahzad", "Əliyev"
        cls.teacher.save(update_fields=["first_name", "last_name"])

    def _get(self, name, query):
        client = Client()
        client.force_login(self.w["coordinator"])
        session = client.session
        session["active_organization"] = self.w["org"].slug
        session.save()
        response = client.get(reverse(name), {"q": query})
        self.assertEqual(response.status_code, 200)
        return response.context

    def test_availability_teacher_search_folds_letters(self):
        for query in ("Aliyev", "shahzad", "sahzad eliyev"):
            with self.subTest(query=query):
                ids = [row["id"] for row in self._get("timetable:availability", query)["teachers"]]
                self.assertEqual(ids, [self.teacher.pk])
        self.assertEqual(self._get("timetable:availability", "Zzqx")["teachers"], [])

    def test_policy_group_search_is_compact(self):
        names = {row["name"] for row in self._get("timetable:policies", "a101")["groups"]}
        self.assertEqual(names, {"A-101"})
        names = {row["name"] for row in self._get("timetable:policies", "A 102")["groups"]}
        self.assertEqual(names, {"A-102"})
