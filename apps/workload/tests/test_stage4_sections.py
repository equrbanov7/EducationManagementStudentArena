"""Mərhələ 4 bölmələri: qeydiyyat müqaviləsi, rol qapıları, aqreqasiya, arxiv.

Dörd yeni bölmə (`workload-center` / `workload-visa` / `workload-approval` /
`workload-overview`) DÖRD yerdə qeydiyyatdan keçməlidir; hər biri ÖZ icazə
açarındadır və başqa rola SIZMIR.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.constants import RoleScopeType

from ..constants import SliceStatus, TaskStatus
from ..models import TaskFacultySlice
from ..services import approve_slice, assign_teacher, build_overview, resolve_actor, review_all, submit_task
from ..services.overview import load_band
from .factories import TEACHER_PERMS, YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

SECTIONS = ("workload-center", "workload-visa", "workload-approval", "workload-overview")

OFFICE_PERMS = ["workload.view", "workload.manage", "workload.submit", "workload.report"]
COORD_PERMS = ["workload.view", "workload.review"]
DEAN_PERMS = ["workload.view", "workload.approve", "workload.report"]
CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute"]
RECTOR_PERMS = ["workload.view", "workload.report"]


class SectionRegistrationContractTest(TestCase):
    def test_sections_are_registered_in_all_four_places(self):
        from apps.accounts.views.profile._sections.labels import (
            DIRECT_PROFILE_SECTION_TEMPLATES,
            build_section_titles,
        )
        from apps.accounts.views.profile.sections_api import AJAX_SAFE_SECTIONS, SECTION_PARTIALS

        titles = build_section_titles()
        for section in SECTIONS:
            self.assertIn(section, SECTION_PARTIALS, section)
            self.assertIn(section, AJAX_SAFE_SECTIONS, section)
            self.assertIn(section, DIRECT_PROFILE_SECTION_TEMPLATES, section)
            self.assertIn(section, titles, section)

    def test_profile_template_lists_the_sections_for_ajax(self):
        from pathlib import Path

        import apps.accounts as accounts_pkg

        template = (Path(accounts_pkg.__file__).parent / "templates" / "accounts" / "profile.html").read_text(
            encoding="utf-8"
        )
        for section in SECTIONS:
            self.assertIn(section, template, f"{section} profile.html-də yoxdur")


class ChainSectionBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("ds4-sec")
        cls.stack = make_structure(cls.org, code="DS4S")
        cls.office = User.objects.create_user("s4.office", "s4office@x.test", "pw")
        cls.coordinator = User.objects.create_user("s4.coord", "s4coord@x.test", "pw")
        cls.dean = User.objects.create_user("s4.dean", "s4dean@x.test", "pw")
        cls.chair_head = User.objects.create_user("s4.chair", "s4chair@x.test", "pw")
        cls.rector = User.objects.create_user("s4.rector", "s4rector@x.test", "pw")
        cls.teacher = User.objects.create_user("s4.teacher", "s4teacher@x.test", "pw")
        cls.student = User.objects.create_user("s4.student", "s4student@x.test", "pw")
        activate_member(cls.org, cls.office, "teaching_office_head", permissions=OFFICE_PERMS, level=85)
        activate_member(
            cls.org,
            cls.coordinator,
            "program_coordinator",
            permissions=COORD_PERMS,
            scope_unit=cls.stack["specialty"],
            scope_type=RoleScopeType.UNIT,
            level=45,
        )
        activate_member(
            cls.org,
            cls.dean,
            "dean",
            permissions=DEAN_PERMS,
            scope_unit=cls.stack["faculty"],
            scope_type=RoleScopeType.UNIT,
            level=70,
        )
        activate_member(
            cls.org,
            cls.chair_head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=cls.stack["chair"],
            scope_type=RoleScopeType.UNIT,
            level=60,
        )
        activate_member(cls.org, cls.rector, "rector_view", permissions=RECTOR_PERMS, level=90)
        activate_member(
            cls.org,
            cls.teacher,
            "teacher",
            permissions=TEACHER_PERMS + ["workload.object"],
            scope_unit=cls.stack["chair"],
            scope_type=RoleScopeType.COURSE,
            level=30,
        )
        activate_member(
            cls.org,
            cls.student,
            "student",
            permissions=["course.view"],
            scope_unit=cls.stack["group"],
            scope_type=RoleScopeType.UNIT,
            level=10,
        )

    def fragment(self, section):
        return reverse("accounts:profile_section_fragment", kwargs={"section": section})


class SectionAccessTest(ChainSectionBase):
    def test_each_role_opens_only_its_own_screen(self):
        matrix = (
            (self.office, {"workload-center", "workload-overview"}),
            (self.coordinator, {"workload-visa"}),
            (self.dean, {"workload-approval", "workload-overview"}),
            (self.rector, {"workload-overview"}),
        )
        for user, expected in matrix:
            self.client.force_login(user)
            for section in SECTIONS:
                response = self.client.get(self.fragment(section))
                wanted = 200 if section in expected else 403
                self.assertEqual(response.status_code, wanted, f"{user.username} → {section}")

    def test_teacher_and_student_see_none_of_the_chain_screens(self):
        for user in (self.teacher, self.student):
            self.client.force_login(user)
            for section in SECTIONS:
                response = self.client.get(self.fragment(section))
                self.assertEqual(response.status_code, 403, f"{user.username} → {section}")

    def test_chair_head_gets_the_center_but_not_approval(self):
        self.client.force_login(self.chair_head)
        self.assertEqual(self.client.get(self.fragment("workload-center")).status_code, 200)
        self.assertEqual(self.client.get(self.fragment("workload-approval")).status_code, 403)
        self.assertEqual(self.client.get(self.fragment("workload-visa")).status_code, 403)


class ActionEndpointGateTest(ChainSectionBase):
    def setUp(self):
        self.task = make_task(self.org, self.stack["chair"], created_by=self.office)
        self.row = make_row(self.task, self.stack)

    def url(self):
        return reverse("workload:action")

    def test_get_is_rejected(self):
        self.client.force_login(self.office)
        self.assertEqual(self.client.get(self.url()).status_code, 405)

    def test_unknown_action_is_rejected(self):
        self.client.force_login(self.office)
        response = self.client.post(self.url(), {"action": "uydurma"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "unknown_action")

    def test_chair_head_cannot_submit(self):
        self.client.force_login(self.chair_head)
        response = self.client.post(self.url(), {"action": "submit", "task": str(self.task.pk)})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "workload.submit_denied")

    def test_office_submits_and_dean_approves_over_http(self):
        self.client.force_login(self.office)
        response = self.client.post(self.url(), {"action": "submit", "task": str(self.task.pk)})
        self.assertEqual(response.status_code, 200, response.content)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.SUBMITTED)

        slice_obj = TaskFacultySlice.objects.get(task=self.task)
        self.client.force_login(self.coordinator)
        denied = self.client.post(self.url(), {"action": "approve_slice", "slice": str(slice_obj.pk)})
        self.assertEqual(denied.status_code, 403)

        # Koordinator vizası (P2-36) — bunsuz dekan təsdiqi `visa_missing` ilə bağlıdır.
        review_all(actor=resolve_actor(self.coordinator, self.org))
        self.client.force_login(self.dean)
        ok = self.client.post(self.url(), {"action": "approve_slice", "slice": str(slice_obj.pk)})
        self.assertEqual(ok.status_code, 200, ok.content)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.APPROVED)

    def test_return_without_reason_is_400(self):
        self.client.force_login(self.office)
        self.client.post(self.url(), {"action": "submit", "task": str(self.task.pk)})
        slice_obj = TaskFacultySlice.objects.get(task=self.task)
        self.client.force_login(self.dean)
        response = self.client.post(
            self.url(), {"action": "return_slice", "slice": str(slice_obj.pk), "reason": "qısa"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "workload.reason_too_short")

    def test_malformed_uuid_is_not_a_500(self):
        self.client.force_login(self.office)
        response = self.client.post(self.url(), {"action": "submit", "task": "belə-id-yoxdur"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "workload.task_not_found")


class ArchiveTest(ChainSectionBase):
    def test_past_year_is_read_only(self):
        from ..center_registry import is_archive_year

        self.assertTrue(is_archive_year(self.org, "2020/2021"))
        self.assertFalse(is_archive_year(self.org, YEAR))

        old_task = make_task(self.org, self.stack["chair"], created_by=self.office)
        old_task.academic_year = "2020/2021"
        old_task.save(update_fields=["academic_year"])
        make_row(old_task, self.stack)

        self.client.force_login(self.office)
        response = self.client.post(reverse("workload:action"), {"action": "submit", "task": str(old_task.pk)})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "workload.archive_readonly")


class OverviewAggregationTest(ChainSectionBase):
    """§8/13 — kafedra → fakültə → universitet, YEKUN SAXLANILMIR."""

    def setUp(self):
        self.task = make_task(self.org, self.stack["chair"], created_by=self.office)
        self.row = make_row(self.task, self.stack, lecture_total=30, seminar_total=30)
        submit_task(task=self.task, actor=resolve_actor(self.office, self.org))
        self.task.refresh_from_db()
        # Koordinator vizası (P2-36) — bunsuz dekan təsdiqi `visa_missing` ilə bağlıdır.
        review_all(actor=resolve_actor(self.coordinator, self.org))
        approve_slice(slice_obj=TaskFacultySlice.objects.get(task=self.task), actor=resolve_actor(self.dean, self.org))
        self.task.refresh_from_db()
        self.row.refresh_from_db()
        assign_teacher(
            row=self.row,
            actor=resolve_actor(self.chair_head, self.org),
            activity="lecture",
            teacher_id=self.teacher.pk,
            hours=30,
        )

    def test_numbers_match_the_fixture(self):
        data = build_overview(actor=resolve_actor(self.rector, self.org), academic_year=YEAR)
        chair = next(row for row in data["chairs"] if row["id"] == str(self.stack["chair"].pk))
        self.assertEqual(chair["planned_hours"], 60)
        self.assertEqual(chair["assigned_hours"], 30)
        self.assertEqual(chair["remaining_hours"], 30)
        self.assertEqual(chair["teachers"], 1)
        self.assertEqual(chair["percent"], 50)

        faculty = next(row for row in data["faculties"] if row["id"] == str(self.stack["faculty"].pk))
        self.assertEqual(faculty["planned_hours"], 60)
        self.assertEqual(faculty["assigned_hours"], 30)

        self.assertEqual(data["totals"]["planned_hours"], 60)
        self.assertEqual(data["totals"]["assigned_hours"], 30)
        self.assertEqual(data["totals"]["chairs"], len(data["chairs"]))

    def test_vacant_hours_roll_up(self):
        assign_teacher(
            row=self.row,
            actor=resolve_actor(self.chair_head, self.org),
            activity="seminar",
            teacher_id=None,
            hours=30,
        )
        data = build_overview(actor=resolve_actor(self.rector, self.org), academic_year=YEAR)
        self.assertEqual(data["totals"]["vacant_hours"], 30)
        self.assertEqual(data["totals"]["assigned_hours"], 60)
        self.assertEqual(data["totals"]["percent"], 100)

    def test_aggregation_uses_a_bounded_number_of_queries(self):
        """Kafedra sayı nə olursa olsun — sətir-sətir dövr YOXDUR."""
        for index in range(5):
            extra = make_structure(self.org, code=f"AGG{index}")
            extra_task = make_task(self.org, extra["chair"], created_by=self.office)
            make_row(extra_task, extra)
        with self.assertNumQueries(9):
            build_overview(actor=resolve_actor(self.rector, self.org), academic_year=YEAR)

    def test_scope_rule_no_scope_is_not_the_whole_university(self):
        stranger = User.objects.create_user("s4.nobody", "nobody@x.test", "pw")
        activate_member(
            self.org,
            stranger,
            "unit_reporter",
            permissions=RECTOR_PERMS,
            scope_unit=None,
            scope_type=RoleScopeType.UNIT,
            level=40,
        )
        data = build_overview(actor=resolve_actor(stranger, self.org), academic_year=YEAR)
        self.assertEqual(data["chairs"], [])
        self.assertEqual(data["totals"]["planned_hours"], 0)

    def test_load_bands(self):
        self.assertEqual(load_band(50), "under")
        self.assertEqual(load_band(95), "normal")
        self.assertEqual(load_band(110), "over")
        self.assertEqual(load_band(200), "critical")

    def test_slice_status_catalogue_is_complete(self):
        self.assertEqual({value for value, _ in SliceStatus.choices}, {"pending", "approved", "returned"})
