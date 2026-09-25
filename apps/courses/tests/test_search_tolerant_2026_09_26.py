"""Dözümlü axtarış (sahib 2026-09-26) — kursa tələbə əlavə etmə modalının axtarışı."""

from django.test import TestCase
from django.urls import reverse

from apps.courses.tests.test_members_page_query_budget import _MembersFixtureMixin


class AvailableStudentsTolerantSearchTest(_MembersFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("courses:available_students", kwargs={"course_id": self.course.id})

    def _ids(self, query):
        response = self.client.get(self.url, {"q": query})
        self.assertEqual(response.status_code, 200)
        return [row["id"] for row in response.json()["users"]]

    def test_ascii_query_finds_azerbaijani_names(self):
        rauf = self._student(1, first_name="Şahzad", last_name="Əliyev")
        other = self._student(2, first_name="Aysel", last_name="Məmmədova")
        for query in ("Aliyev", "eliyev", "Shahzad", "sahzad aliyev", "ŞAHZAD ƏLİYEV"):
            with self.subTest(query=query):
                self.assertEqual(self._ids(query), [rauf.id])
        self.assertEqual(self._ids("memmedova"), [other.id])
        self.assertEqual(self._ids("Aysel Aliyev"), [])
        self.assertEqual(sorted(self._ids("")), sorted([rauf.id, other.id]))
