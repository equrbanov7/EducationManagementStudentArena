"""Kabinet bölmələri: fraqment render + JSON endpoint qapıları.

Bölmə qeydiyyatının DÖRD yeri (SECTION_PARTIALS, AJAX_SAFE_SECTIONS,
`profile.html` data-ajax-sections, rbac allowed_sections) burada bir-birinə
qarşı yoxlanılır — sillabus fazasında bu müqavilə əl ilə saxlanılırdı.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.constants import RoleScopeType

from .factories import TEACHER_PERMS, activate_member, make_org, make_structure

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]
SECTIONS = ("workload-distribution", "my-workload")


class SectionRegistrationContractTest(TestCase):
    def test_sections_are_registered_in_all_four_places(self):
        from apps.accounts.views.profile._sections.labels import (
            DIRECT_PROFILE_SECTION_TEMPLATES,
            build_section_titles,
        )
        from apps.accounts.views.profile.sections_api import AJAX_SAFE_SECTIONS, SECTION_PARTIALS

        titles = build_section_titles()
        for section in SECTIONS:
            self.assertIn(section, SECTION_PARTIALS)
            self.assertIn(section, AJAX_SAFE_SECTIONS)
            self.assertIn(section, DIRECT_PROFILE_SECTION_TEMPLATES)
            self.assertIn(section, titles)

    def test_profile_template_lists_the_sections_for_ajax(self):
        from pathlib import Path

        import apps.accounts as accounts_pkg

        template = (Path(accounts_pkg.__file__).parent / "templates" / "accounts" / "profile.html").read_text(
            encoding="utf-8"
        )
        for section in SECTIONS:
            self.assertIn(section, template, f"{section} profile.html-də yoxdur")


class SectionAccessTest(TestCase):
    def setUp(self):
        self.org = make_org("wl-sec")
        self.stack = make_structure(self.org, code="WLE")
        self.head = User.objects.create_user("wle_head", "wle_head@x.test", "pw")
        activate_member(
            self.org,
            self.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=self.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        self.teacher = User.objects.create_user("wle_teacher", "wle_teacher@x.test", "pw")
        activate_member(
            self.org,
            self.teacher,
            "teacher",
            permissions=TEACHER_PERMS,
            scope_unit=self.stack["chair"],
            level=50,
            scope_type=RoleScopeType.COURSE,
        )
        self.student = User.objects.create_user("wle_student", "wle_student@x.test", "pw")
        activate_member(
            self.org,
            self.student,
            "student",
            permissions=["course.view"],
            scope_unit=self.stack["group"],
            level=10,
            scope_type=RoleScopeType.UNIT,
        )

    def _fragment(self, section):
        return reverse("accounts:profile_section_fragment", kwargs={"section": section})

    def test_chair_head_gets_the_distribution_fragment(self):
        self.client.force_login(self.head)
        response = self.client.get(self._fragment("workload-distribution"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("data-wl-root", payload["html"])

    def test_teacher_gets_my_workload_but_not_distribution(self):
        self.client.force_login(self.teacher)
        allowed = self.client.get(self._fragment("my-workload"))
        self.assertEqual(allowed.status_code, 200)
        self.assertIn("data-wlm-root", allowed.json()["html"])

        denied = self.client.get(self._fragment("workload-distribution"))
        self.assertEqual(denied.status_code, 403)

    def test_student_sees_neither_section(self):
        self.client.force_login(self.student)
        for section in SECTIONS:
            response = self.client.get(self._fragment(section))
            self.assertEqual(response.status_code, 403, f"{section} tələbəyə açıqdır!")


class JsonEndpointGateTest(TestCase):
    def setUp(self):
        self.org = make_org("wl-api")
        self.stack = make_structure(self.org, code="WLF")
        self.teacher = User.objects.create_user("wlf_teacher", "wlf_teacher@x.test", "pw")
        activate_member(
            self.org,
            self.teacher,
            "teacher",
            permissions=TEACHER_PERMS,
            scope_unit=self.stack["chair"],
            level=50,
            scope_type=RoleScopeType.COURSE,
        )

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("workload:rows"))
        self.assertIn(response.status_code, (302, 403))

    def test_teacher_cannot_read_chair_teacher_pool(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("workload:teachers"), {"chair": str(self.stack["chair"].pk)})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "workload.manage_denied")

    def test_teacher_can_read_own_rows_endpoint(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("workload:my_rows"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["rows"], [])

    def test_write_endpoints_reject_get(self):
        self.client.force_login(self.teacher)
        for name in ("workload:assign", "workload:confirm", "workload:row_save"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 405, name)
