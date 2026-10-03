"""Hesab aktivləşdirmə kampaniyası (sahib 2026-10-03): reyestrdə «qruplar üzrə» hesabat + çap vərəqi.

Kilidlənən qaydalar:

* hesabat reyestrin ÖZ əhatəsi və filtrləri ilə qurulur; arxiv / məzun / xaric sayılmır;
* ən geri qalan qrup birinci gəlir; «Siyahı» linki qrup + «ilkin parolda» süzgəcini daşıyır;
* çap vərəqində yalnız aktivləşdirməyənlərin ADI + İSTİFADƏÇİ ADI var — parol / e-poçt YOX;
* əhatəsi olmayan rol, icazəsiz rol, səhv və ya yad qrup → 404.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.accounts.services.people.study_state import current_academic_year_start
from apps.organizations.models import Membership
from apps.registrar.models import StudentAcademicRecord

from .test_student_services_sections import PASSWORD, StudentServicesBase

User = get_user_model()


class StudentActivationTest(StudentServicesBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        year = current_academic_year_start() - 1
        cls.people = {}

        def make(name, *, activated=False, logged_in=False, archived=False):
            user = User.objects.create_user(f"act_{name}", f"act_{name}@qku.edu.az", PASSWORD)
            Membership.objects.create(
                user=user, organization=cls.org, role=cls.student_role, is_primary=True, is_active=True
            )
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=user,
                program=cls.program,
                curriculum=cls.curriculum,
                group=cls.group_b,
                admission_year=year,
            )
            if logged_in:
                user.last_login = timezone.now()
                user.save(update_fields=["last_login"])
            profile = user.profile
            profile.password_change_required = not activated
            profile.email_verified = activated
            if archived:
                profile.access_state = "archived"
            profile.save()
            cls.people[name] = user

        make("done", activated=True, logged_in=True)
        make("never")
        make("started", logged_in=True)
        make("alumni", archived=True)

    def _section(self, role="student_services", **params):
        response = self._fragment(role, "student-registry", sr_view="activation", **params)
        self.assertEqual(response.status_code, 200)
        return response.context["student_registry_section"]

    def test_group_report_counts_and_order(self):
        section = self._section()
        rows = {row["group_id"]: row for row in section["activation"]["rows"]}
        row = rows[str(self.group_b.pk)]
        # arxiv (məzun) sayılmır: 3 tələbə, 1 aktivləşdirib, 2 ilkin parolda, 1 heç girməyib.
        self.assertEqual((row["total"], row["activated"], row["initial"], row["never"]), (3, 1, 2, 1))
        self.assertEqual(row["pct"], 33)
        self.assertIn("sr_account=initial", row["list_url"])
        self.assertIn(f"sr_group={self.group_b.pk}", row["list_url"])
        self.assertIn(f"group={self.group_b.pk}", row["sheet_url"])
        pcts = [item["pct"] for item in section["activation"]["rows"]]
        self.assertEqual(pcts, sorted(pcts))
        self.assertIn("sr_view=activation", section["activation_view_url"])
        self.assertNotIn("sr_view", section["list_view_url"])

    def test_student_list_view_is_unchanged(self):
        response = self._fragment("student_services", "student-registry")
        section = response.context["student_registry_section"]
        self.assertNotIn("activation", section)
        self.assertTrue(section["table_rows"])

    def _sheet(self, role="student_services", group=None):
        return self._client(role).get(
            reverse("accounts:student_activation_sheet"), {"group": group or str(self.group_b.pk)}
        )

    def test_sheet_lists_only_pending_students_without_secrets(self):
        response = self._sheet()
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("act_never", html)
        self.assertIn("act_started", html)
        self.assertNotIn("act_done", html)
        self.assertNotIn("act_alumni", html)
        self.assertNotIn("@qku.edu.az", html)
        self.assertNotIn(PASSWORD, html)
        self.assertIn("<svg", html)
        self.assertIn(reverse("accounts:student_login"), response.context["login_url"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        sheet = response.context["sheet"]
        self.assertEqual((sheet["total"], sheet["activated"], len(sheet["pending"])), (3, 1, 2))

    def test_sheet_is_gated_like_the_registry(self):
        self.assertEqual(self._sheet(role="program_coordinator").status_code, 404)  # əhatə yoxdur
        self.assertEqual(self._sheet(role="teacher").status_code, 404)  # reyestr icazəsi yoxdur
        self.assertEqual(self._sheet(group="not-a-uuid").status_code, 404)
        self.assertEqual(self._sheet(group="00000000-0000-0000-0000-000000000000").status_code, 404)

    def test_group_table_is_paginated_server_side(self):
        from unittest import mock

        with mock.patch("apps.accounts.views.profile._sections.student_activation.ACTIVATION_PAGE_SIZE", 1):
            first = self._section()["activation"]
            second = self._section(sr_page="2")["activation"]
        self.assertEqual(len(first["rows"]), 1)
        self.assertGreaterEqual(first["page_obj"].paginator.num_pages, 3)
        self.assertEqual(first["rows_total"], first["page_obj"].paginator.count)
        self.assertNotEqual(first["rows"][0]["group_id"], second["rows"][0]["group_id"])
        self.assertEqual(second["page_obj"].number, 2)
