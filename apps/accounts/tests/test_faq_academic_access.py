"""The actual academic operation, its FAQ entry, and both media types agree."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import FaqVideoGuide
from apps.accounts.views.profile.faq_academic_access import academic_capabilities, academic_flags
from apps.accounts.views.profile.faq_catalog import GUIDES
from apps.exams.models import ExamRoom, InvigilatorDuty
from apps.subject_folder.tests import factories as f
from core.constants import RoleScopeType

from .test_faq_media import _client, _url

PAPER_GUIDES = {"exam-import", "published-paper-score", "section-exam-score-entry"}


@override_settings(UNIVERSITY_MODE=True)
class AcademicFAQAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.other = f.make_org(), f.make_org()

        def member(name, role, org=cls.org):
            user = f.make_user(name)
            org.roles.get(name=role).memberships.create(user=user, organization=org, is_active=True)
            return user

        cls.teacher = member("teacher", "teacher")
        cls.student = member("student", "student")
        cls.exam_staff = member("centre", "exam_center_staff")
        cls.exam_head = member("decision", "exam_center_head")
        cls.accountant = member("finance", "accountant")
        cls.other.roles.get(name="exam_center_head").memberships.create(
            user=cls.teacher, organization=cls.other, is_active=True
        )

    def assert_visibility(self, client, allowed, denied):
        response = client.get(reverse("accounts:profile"), {"section": "faq"})
        self.assertEqual(response.status_code, 200)
        faq = response.context["faq"]
        keys = faq["allowed_guide_keys"]
        self.assertTrue(set(allowed) <= keys, set(allowed) - keys)
        self.assertFalse(set(denied) & keys, set(denied) & keys)
        for key in [*allowed, *denied]:
            for ext in ("mp4", "vtt"):
                with self.subTest(key=key, extension=ext):
                    response = client.head(_url(key, ext), HTTP_RANGE="bytes=0-7")
                    self.assertEqual(response.status_code, 206 if key in allowed else 404)
        return keys

    def test_teacher_journal_is_separate_from_paper_import_across_tenants_and_overrides(self):
        self.assertEqual({g.key for g in GUIDES if g.video == "paper"}, PAPER_GUIDES)
        self.assertTrue(all("faq_enter_paper_scores" in academic_flags(g) for g in GUIDES if g.video == "paper"))
        FaqVideoGuide.objects.create(
            organization=self.org, key="exam-import", title="Kağız imtahanı", audience_roles=["teacher"]
        )
        own = _client(self.teacher, self.org)
        self.assert_visibility(own, {"journal-entry", "locked-mark", "section-my-exams"}, PAPER_GUIDES | {"grades"})
        # The real import rejects this role before it tries to resolve a teaching unit.
        endpoint = reverse("accounts:exam_score_import_template")
        self.assertEqual(own.get(endpoint).status_code, 403)
        other = _client(self.teacher, self.other)
        self.assert_visibility(other, PAPER_GUIDES, {"grades"})
        self.assertEqual(other.get(endpoint, {"offering": "not-an-offering"}).status_code, 404)
        self.assert_visibility(
            _client(self.student, self.org), {"grades", "quiz-start"}, PAPER_GUIDES | {"journal-entry"}
        )

    def test_scope_for_an_exam_entry_operator_matches_the_actual_workbook_route(self):
        # An empty unit scope is insufficient even though the same permission key appears on the role.
        examiner = f.make_user("unit-examiner")
        assigned, foreign = f.make_group(self.org), f.make_group(self.org)
        role = f.activate_member(
            self.org, examiner, "scoped-paper-input", permissions=["final_score.entry"], scope_type=RoleScopeType.UNIT
        )
        client = _client(examiner, self.org)
        self.assert_visibility(client, set(), PAPER_GUIDES)
        member = role.memberships.get(user=examiner)
        member.scope_unit = assigned
        member.save(update_fields=["scope_unit"])
        self.assert_visibility(client, PAPER_GUIDES, set())
        period = f.make_period(self.org)
        subject = f.make_subject(self.org)
        found = f.make_offering(self.org, subject=subject, period=period, instructor=self.teacher, group=assigned)
        outside = f.make_offering(self.org, subject=subject, period=period, instructor=self.teacher, group=foreign)
        url = reverse("accounts:exam_score_import_template")
        self.assertEqual(client.get(url, {"offering": str(found.pk)}).status_code, 200)
        self.assertEqual(client.get(url, {"offering": str(outside.pk)}).status_code, 403)

    def test_payment_and_appeal_desk_readers_need_the_corresponding_write_grants(self):
        # Both centre members can open their inbox. Only a member with appeal.decide can issue a decision.
        role = self.org.roles.get(name="exam_center_staff")
        role.permissions = [key for key in role.permissions if key not in {"appeal.*", "appeal.decide", "*"}]
        role.save(update_fields=["permissions"])
        self.assert_visibility(
            _client(self.exam_staff, self.org),
            {"section-exam-center-pins", *PAPER_GUIDES},
            {"section-manage-appeals", "section-retake-desk", "section-question-submissions"},
        )
        self.assert_visibility(_client(self.exam_head, self.org), {"section-manage-appeals"}, {"section-retake-desk"})
        self.assert_visibility(_client(self.accountant, self.org), {"section-retake-desk"}, PAPER_GUIDES)

    def test_teacher_quiz_and_journal_grants_can_be_revoked_independently(self):
        role = self.org.roles.get(name="teacher")
        role.permissions = ["unit.view", "exam.view", "grade.input"]
        role.save(update_fields=["permissions"])
        self.assert_visibility(_client(self.teacher, self.org), {"journal-entry"}, {"section-my-exams", *PAPER_GUIDES})
        role.permissions = ["unit.view", "exam.create"]
        role.save(update_fields=["permissions"])
        self.assert_visibility(_client(self.teacher, self.org), {"section-my-exams"}, {"journal-entry", "locked-mark"})

    def test_active_invigilator_may_learn_how_to_monitor_their_room(self):
        client = _client(self.teacher, self.org)
        rooms = reverse("exams:exam_center_room_list")
        self.assertEqual(client.get(rooms).status_code, 403)
        self.assert_visibility(client, {"journal-entry"}, {"room-monitor"})
        room = ExamRoom.objects.create(organization=self.org, name="Təlim zalı", code="faq-room")
        now = timezone.now()
        duty = InvigilatorDuty.objects.create(
            organization=self.org, room=room, user=self.teacher, starts_at=now, ends_at=now + timedelta(hours=2)
        )
        self.assertEqual(client.get(rooms).status_code, 200)
        self.assert_visibility(client, {"room-monitor"}, PAPER_GUIDES)
        duty.revoked_at = now
        duty.save(update_fields=["revoked_at"])
        self.assert_visibility(client, {"journal-entry"}, {"room-monitor"})

    def test_range_request_confines_computation_to_its_actual_operation(self):
        response = _client(self.exam_head, self.org).get(reverse("accounts:profile"), {"section": "faq"})
        request = response.wsgi_request
        capabilities = {"allowed_sections": {"exam-score-entry"}}
        module = "apps.accounts.views.profile.faq_academic_access"
        with (
            patch(module + ".can_enter_supervision_surface", side_effect=AssertionError("unrelated duty lookup")),
            patch(module + ".exam_score_entry.can_enter_exam_scores", return_value=True) as score,
        ):
            with self.assertNumQueries(0):
                self.assertEqual(academic_capabilities(request, capabilities, required=set()), {})
                self.assertEqual(
                    academic_capabilities(request, capabilities, required={"faq_enter_paper_scores"}),
                    {"faq_enter_paper_scores": True},
                )
            score.assert_called_once_with(request.user, self.org)

    def test_room_buttons_and_gates_follow_each_authorization(self):
        reports = reverse("exams:exam_center_reports")
        rooms_url = reverse("exams:exam_center_room_list")
        for user, org, reports_allowed, designate, administer in (
            (self.exam_head, self.org, True, True, False),
            (self.exam_staff, self.org, True, False, False),
            (self.teacher, self.other, True, True, False),
        ):
            with self.subTest(user=user.username, organization=org):
                client = _client(user, org)
                response = client.get(rooms_url)
                self.assertEqual(response.status_code, 200)
                flags = academic_capabilities(
                    response.wsgi_request,
                    {"allowed_sections": set()},
                    required={
                        "faq_exam_center",
                        "faq_supervise_rooms",
                        "faq_designate_exam_halls",
                        "faq_manage_exam_rooms",
                    },
                )
                self.assertEqual(flags["faq_exam_center"], reports_allowed)
                self.assertTrue(flags["faq_supervise_rooms"])
                self.assertEqual(flags["faq_designate_exam_halls"], designate)
                self.assertEqual(flags["faq_manage_exam_rooms"], administer)
                self.assertEqual(response.context["can_designate"], designate)
                self.assertEqual(response.context["can_manage_rooms"], administer)
                self.assertEqual(client.get(reports).status_code, 200 if reports_allowed else 403)

    def test_academic_group_toolbar_tour_and_server_need_scoped_group_management(self):
        uid = f.make_user("groupeditor")
        role = f.activate_member(
            self.org,
            uid,
            "group-faq-operator",
            permissions=["unit.view", "unit.group_manage"],
            scope_type=RoleScopeType.UNIT,
        )
        group = f.make_group(self.org)
        member = role.memberships.get(user=uid)
        client = _client(uid, self.org)
        for attach in (False, True):
            member.scope_unit = group if attach else None
            member.save(update_fields=["scope_unit"])
            page = client.get(reverse("accounts:profile"), {"section": "groups-registry"})
            self.assertEqual(page.status_code, 200)
            flag = academic_capabilities(
                page.wsgi_request, {"allowed_sections": {"groups-registry"}}, required={"faq_manage_academic_groups"}
            )
            self.assertIs(flag["faq_manage_academic_groups"], attach)
            toolbar = page.context["groups_registry_section"]
            self.assertIs(toolbar["can_manage"], attach)
            response = client.post(
                reverse("organizations:group_action", kwargs={"slug": self.org.slug}), {"action": "unknown"}
            )
            self.assertEqual(response.status_code, 400 if attach else 403)

    def test_cabinet_shows_only_the_creation_forms_the_same_user_may_open(self):
        role = self.org.roles.get(name="teacher")
        role.permissions = ["unit.view", "exam.view"]
        for granted in (False, True):
            if granted:
                role.permissions += ["exam.create", "course.create"]
            role.save(update_fields=["permissions"])
            client = _client(self.teacher, self.org)
            for section, marker, endpoint in (
                ("my-courses", 'class="ems-btn ems-btn--primary js-open-create-course"', "courses:create_course"),
                ("my-exams", 'data-exam-modal-mode="create"', "exams:create_exam"),
            ):
                with self.subTest(section=section, granted=granted):
                    response = client.get(reverse("accounts:profile_section_fragment", kwargs={"section": section}))
                    self.assertEqual(response.status_code, 200)
                    self.assertIs(marker in response.json()["html"], granted)
                    self.assertEqual(client.get(reverse(endpoint), {"modal": "1"}).status_code, 200 if granted else 403)
        assistant = f.make_user("assistant")
        self.org.roles.get(name="assistant").memberships.create(user=assistant, organization=self.org, is_active=True)
        client = _client(assistant, self.org)
        url = reverse("exams:question_submission_create")
        response = client.get(reverse("accounts:profile_section_fragment", kwargs={"section": "question-submissions"}))
        self.assertNotIn(url, response.json()["html"])
        self.assertNotIn("data-qsub-live-hint", response.json()["html"])
        self.assertEqual(client.get(url).status_code, 403)

    def test_workload_without_a_chair_and_distribution_only_never_show_row_creation_controls(self):
        from apps.workload.tests.factories import make_structure

        operator = f.make_user("workload-faq")
        structure = make_structure(self.org, code="FAQWL")
        role = f.activate_member(
            self.org,
            operator,
            "workload-faq-ops",
            scope_type=RoleScopeType.UNIT,
            permissions=["unit.view", "workload.view", "workload.manage", "workload.distribute"],
        )
        member = role.memberships.get(user=operator)
        client = _client(operator, self.org)
        for mode, writable, can_distribute in (
            ("no-scope", False, False),
            ("full", True, True),
            ("distribute", False, True),
        ):
            if mode == "full":
                member.scope_unit = structure["chair"]
                member.save(update_fields=["scope_unit"])
            if mode == "distribute":
                role.permissions = ["unit.view", "workload.view", "workload.distribute"]
                role.save(update_fields=["permissions"])
            page = client.get(reverse("accounts:profile_section_fragment", kwargs={"section": "workload-distribution"}))
            self.assertEqual(page.status_code, 200)
            html = page.json()["html"]
            self.assertIs("data-wl-create-task" in html, writable)
            self.assertIs("data-wl-open-row-modal" in html, writable)
            self.assertIs("data-wl-filters" in html, can_distribute)
            center = client.get(reverse("accounts:profile_section_fragment", kwargs={"section": "workload-center"}))
            if mode == "distribute":
                if center.status_code == 403:
                    continue
            self.assertEqual(center.status_code, 200)
            self.assertIs('data-tof-open="wlTaskDialog"' in center.json()["html"], writable)
