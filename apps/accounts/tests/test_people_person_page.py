"""Şəxs səhifəsi («Ətraflı», yeni tab) + çekmecə xülasələri (2026-09-08).

* dekan öz fakültəsinin tələbə/müəllim səhifəsini görür (200, akademik/tədris
  blokları, ÜOMG/kredit/kəsr KPI-ları); başqa fakültənin şəxsi 404;
* kataloq icazəsi olmayan aktor 403;
* çekmecə JSON-u `page_url` + `academic_summary` / `teaching_summary` daşıyır.
"""

from __future__ import annotations

from django.test import Client, TestCase
from django.urls import reverse

from apps.registrar.models import CourseOffering
from core.rls import bypass_rls

from .people_fixture import PeopleFixture


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()
        with bypass_rls():
            # Fixture-in mövcud açılışı (subject/period/group unikaldır) — müəllim A-ya bağlanır.
            CourseOffering.objects.filter(pk=cls.fx.offering_a.pk).update(instructor=cls.fx.teacher_a, lesson_hours=30)
            cls.offering = CourseOffering.objects.get(pk=cls.fx.offering_a.pk)

    def setUp(self):
        self.client = Client()

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_organization_id"] = str(self.fx.org.pk)
        session.save()

    def _page(self, user_id):
        with bypass_rls():
            return self.client.get(reverse("accounts:people_person_page", kwargs={"user_id": user_id}))

    def _detail(self, user_id):
        with bypass_rls():
            return self.client.get(reverse("accounts:people_detail", kwargs={"user_id": user_id}))


class PersonPageTest(_Base):
    def test_dean_sees_student_page_with_academic_block(self):
        self._login(self.fx.dean_a)
        response = self._page(self.fx.student_a.pk)
        self.assertEqual(response.status_code, 200)
        page = response.context["page"]
        self.assertEqual(page["kind"], "student")
        self.assertEqual(page["academic"]["current"]["group"], self.fx.group_a1.name)
        self.assertEqual(page["academic"]["current"]["faculty"], self.fx.faculty_a.name)
        self.assertIn(page["academic"]["current"]["education_form_label"], ("Əyani", "Full-time", "Əyani (gündüz)"))
        labels = [tile["label"] for tile in page["kpis"]]
        self.assertIn("ÜOMG", labels)
        self.assertIn("Kəsr", labels)
        html = response.content.decode()
        self.assertIn("Akademik qeydlər", html)
        self.assertIn("Transkript", html)
        self.assertEqual(html.count("<h1"), 1)

    def test_dean_sees_teacher_page_with_teaching_block(self):
        self._login(self.fx.dean_a)
        response = self._page(self.fx.teacher_a.pk)
        self.assertEqual(response.status_code, 200)
        page = response.context["page"]
        self.assertEqual(page["kind"], "teacher")
        self.assertEqual(page["teaching"]["totals"]["offerings"], 1)
        self.assertEqual(page["teaching"]["totals"]["hours"], 30)
        self.assertEqual(page["structure"]["kafedra"], self.fx.kafedra_a1.name)
        self.assertEqual(page["structure"]["faculty"], self.fx.faculty_a.name)
        self.assertIsNotNone(page["structure"]["years"])
        self.assertIn(self.fx.subject.name, response.content.decode())
        self.assertIn("İş stajı", [tile["label"] for tile in page["kpis"]])

    def test_out_of_scope_person_is_404(self):
        self._login(self.fx.dean_a)
        self.assertEqual(self._page(self.fx.student_b.pk).status_code, 404)
        self.assertEqual(self._page(self.fx.teacher_b.pk).status_code, 404)

    def test_actor_without_catalog_permission_is_refused(self):
        """Kataloq açarı olmayan aktor (tələbə) səhifəni görmür — JSON API ilə eyni
        fail-closed cavab (mövcudluğu sızdırmamaq üçün 404 da qəbul olunur)."""
        self._login(self.fx.student_a)
        self.assertIn(self._page(self.fx.teacher_a.pk).status_code, (403, 404))


class DrawerSummaryTest(_Base):
    def test_student_detail_json_has_page_url_and_academic_summary(self):
        self._login(self.fx.dean_a)
        payload = self._detail(self.fx.student_a.pk).json()
        person = payload["person"]
        self.assertEqual(
            person["page_url"], reverse("accounts:people_person_page", kwargs={"user_id": self.fx.student_a.pk})
        )
        summary = person["academic_summary"]
        self.assertEqual(summary["group"], self.fx.group_a1.name)
        self.assertIn("uomg", summary)
        self.assertIn("failed", summary)
        self.assertIsNone(person["teaching_summary"])

    def test_teacher_detail_json_has_teaching_summary(self):
        self._login(self.fx.dean_a)
        payload = self._detail(self.fx.teacher_a.pk).json()
        summary = payload["person"]["teaching_summary"]
        self.assertEqual(summary["kafedra"], self.fx.kafedra_a1.name)
        self.assertEqual(summary["offerings"], 1)
        self.assertEqual(summary["subjects"], 1)
        self.assertIsNone(payload["person"]["academic_summary"])
