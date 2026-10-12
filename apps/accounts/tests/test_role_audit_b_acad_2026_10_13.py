"""Rol auditi 2026-10-13, B hissəsi (acad): B2 / B5 / B11 / B16 — menyu + data EYNİ açardan.

Hesabat: ``docs/audits/2026-10-13-claude/ROL_AUDITI.md``. Sahib: «hər rol öz səlahiyyəti qədər» — icazə
redaktoru doğru danışmalıdır: açar vermək açmalı, almaq bağlamalıdır. Rollar mümkün olduqca REAL default
şablonlardan gəlir (təşkilat yaradılanda toxumlanır, ``default_roles_role_audit`` tətbiq olunmuş halda).

* B2  — «Akademik qeydlər» yalnız ``student.records_view`` əhatəsi ilə (rol adı / ``_CENTRAL_ROLES`` yox).
* B5  — Tədris şöbəsi: jurnal linki (``journal.view``), «Keçilmiş dərslər» (``journal.lessons_unit``),
  «Akademik qeydlər», rəhbər üçün «Tələbə reyestri».
* B11 — ``schedule.view`` «Cədvəl idarəetməsi»ni YALNIZ-OXU açır; yazı endpoint-i 403.
* B16 — «Dərs yüküm» ``workload.object`` VƏ YA faktiki bölgü sətri ilə.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.tests.test_academic_records import _RecordsBase
from apps.accounts.tests.test_schedule_editor_ui import ScheduleEditorUIBase
from apps.organizations.models import Membership, Role
from core.constants import RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

PASSWORD = "StrongPass123!"


def _client_for(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


def _sections(user, organization):
    response = _client_for(user, organization).get(reverse("accounts:profile"))
    assert response.status_code == 200, response.status_code
    return set(response.context["allowed_sections"])


def _member(organization, username, role_name, *, scope_unit=None):
    user = User.objects.create_user(username, f"{username}@qku.edu.az", PASSWORD)
    Membership.objects.create(
        user=user,
        organization=organization,
        role=organization.roles.get(name=role_name),
        scope_unit=scope_unit,
        is_primary=True,
        is_active=True,
    )
    return user


def _custom_member(organization, username, *, permissions, scope_type=RoleScopeType.ORGANIZATION, scope_unit=None):
    role = Role.objects.create(
        organization=organization,
        name=f"{username}_role",
        display_name=username,
        level=50,
        scope_type=scope_type,
        permissions=list(permissions),
        is_active=True,
    )
    user = User.objects.create_user(username, f"{username}@qku.edu.az", PASSWORD)
    Membership.objects.create(
        user=user, organization=organization, role=role, scope_unit=scope_unit, is_primary=True, is_active=True
    )
    return user


# ── B2 + B5 — akademik qeydlər, jurnal, keçilmiş dərslər, reyestr ───────────────────────────


@override_settings(UNIVERSITY_MODE=True)
class RecordsPermissionGateTest(_RecordsBase):
    """«Akademik qeydlər»: açar varsa açılır, yoxdursa (rol adından asılı olmayaraq) bağlıdır."""

    def _data(self, user):
        return _client_for(user, self.org).get(reverse("accounts:records_overview_data")).json()

    def test_custom_role_with_the_key_gets_menu_and_org_wide_data(self):
        """Köhnə kodda rol ADI siyahıda olmadığına görə həm menyu, həm data bağlı idi."""
        officer = _custom_member(self.org, "b2_officer", permissions=["student.records_view"])

        self.assertIn("academic-records", _sections(officer, self.org))
        payload = self._data(officer)
        self.assertTrue(payload["has_access"])
        self.assertEqual(payload["total"], 5)

    def test_exam_center_without_the_key_loses_menu_and_data(self):
        """Köhnə kodda `_CENTRAL_ROLES` açarsız org-wide əhatə verirdi — redaktorda almaq heç nəyi bağlamırdı."""
        role = self.org.roles.get(name="exam_center_head")
        role.permissions = [key for key in role.permissions if key != "student.records_view"]
        role.save(update_fields=["permissions"])

        self.assertNotIn("academic-records", _sections(self.exam_center, self.org))
        self.assertFalse(self._data(self.exam_center)["has_access"])

    def test_grade_view_alone_opens_nothing(self):
        auditor = _custom_member(self.org, "b2_grade_only", permissions=["grade.view"])

        self.assertNotIn("academic-records", _sections(auditor, self.org))
        self.assertFalse(self._data(auditor)["has_access"])

    def test_unit_role_with_the_key_sees_only_its_subtree(self):
        chair = _custom_member(
            self.org,
            "b2_unit",
            permissions=["student.records_view"],
            scope_type=RoleScopeType.UNIT,
            scope_unit=self.chair_b,
        )

        self.assertIn("academic-records", _sections(chair, self.org))
        payload = self._data(chair)
        self.assertTrue(payload["has_access"])
        self.assertEqual(payload["total"], 2)  # yalnız fakültə B / kafedra B

    def test_unit_role_without_scope_unit_gets_no_section(self):
        dean = _member(self.org, "b2_dean_unscoped", "dean")

        self.assertNotIn("academic-records", _sections(dean, self.org))
        self.assertFalse(self._data(dean)["has_access"])

    def test_student_detail_needs_the_key_too(self):
        auditor = _custom_member(self.org, "b2_detail_denied", permissions=["grade.view"])
        response = _client_for(auditor, self.org).get(
            reverse("accounts:records_student_detail"), {"student": self.students_a[0].id}
        )
        self.assertFalse(response.json()["has_access"])


@override_settings(UNIVERSITY_MODE=True)
class TeachingOfficeSurfacesTest(_RecordsBase):
    """B5 — Tədris şöbəsinin REAL şablon açarları qapıları həqiqətən açır."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.office_head = _member(cls.org, "b5_office_head", "teaching_office_head")
            cls.office_staff = _member(cls.org, "b5_office_staff", "teaching_office_staff")

    def test_staff_gets_journal_lessons_and_records_sections(self):
        sections = _sections(self.office_staff, self.org)

        self.assertIn("my-journal", sections)
        self.assertIn("lessons-log", sections)
        self.assertIn("academic-records", sections)
        self.assertIn("schedule-manage", sections)
        self.assertNotIn("student-registry", sections)

    def test_head_also_gets_the_student_registry(self):
        sections = _sections(self.office_head, self.org)

        self.assertIn("student-registry", sections)
        self.assertIn("my-journal", sections)
        fragment = _client_for(self.office_head, self.org).get(
            reverse("accounts:profile_section_fragment", kwargs={"section": "student-registry"})
        )
        self.assertEqual(fragment.status_code, 200)

    def test_journal_link_opens_a_read_only_org_wide_journal_list(self):
        client = _client_for(self.office_staff, self.org)
        response = client.get(reverse("registrar:journal_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["journal_is_broad"])
        offering = self.students_a[0].enrollments.get().offering
        self.assertIn(offering.id, {row.id for row in response.context["offerings"]})

        from apps.registrar import journal_access

        self.assertTrue(journal_access.can_observe_journal(self.office_staff, offering))
        self.assertFalse(journal_access.is_direct_editor(self.office_staff, offering))

    def test_journal_view_without_scope_does_not_open_the_link(self):
        unscoped = _custom_member(
            self.org, "b5_unit_no_scope", permissions=["journal.view"], scope_type=RoleScopeType.UNIT
        )
        self.assertNotIn("my-journal", _sections(unscoped, self.org))

    def test_disabled_journal_module_stays_hidden(self):
        from apps.organizations.public import set_module_enabled

        set_module_enabled(self.org, "journal", False)
        self.assertNotIn("my-journal", _sections(self.office_staff, self.org))

    def test_lessons_log_supervision_is_org_wide(self):
        from apps.registrar import lessons_log

        self.assertTrue(lessons_log.is_supervisor(self.office_staff, self.org))
        with bypass_rls():
            self.assertTrue(lessons_log.scoped_lessons(self.office_staff, self.org, supervisor=True).exists())

    def test_staff_sees_org_wide_academic_records(self):
        payload = _client_for(self.office_staff, self.org).get(reverse("accounts:records_overview_data")).json()
        self.assertTrue(payload["has_access"])
        self.assertEqual(payload["total"], 5)


# ── B11 — `schedule.view` → «Cədvəl idarəetməsi» YALNIZ-OXU ──────────────────────────────


class ScheduleReadOnlyTest(ScheduleEditorUIBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.vice_rector = _member(cls.org, "b11_vice_rector", "vice_rector")
            cls.office_staff = _member(cls.org, "b11_office_staff", "teaching_office_staff")
            cls.rim_staff = _member(cls.org, "b11_rim_staff", "rim_staff")

    def test_view_holders_get_the_section(self):
        for user in (self.vice_rector, self.office_staff, self.rim_staff):
            with self.subTest(user=user.username):
                self.assertIn("schedule-manage", _sections(user, self.org))

    def test_read_only_render_has_no_write_controls(self):
        response = self._section(self.vice_rector, sm_group=str(self.group.id))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("smtx__table", body)
        self.assertIn("data-sedit-read-only", body)
        self.assertIn('data-can-edit="0"', body)
        for marker in ("data-sedit-new", "data-sedit-slot", 'id="seditCell"', 'id="seditMove"', 'id="seditParked"'):
            self.assertNotIn(marker, body, marker)
        # Qrup siyahısı `schedule.view` əhatəsindən gəlir (org-wide rol → hər iki qrup).
        self.assertIn("231B", body)

    def test_existing_slots_render_as_read_only_cards(self):
        from apps.registrar.models import ScheduleSlot

        self.assertEqual(self._act(self.coordinator, self._cell()).status_code, 200)
        with bypass_rls():
            self.assertEqual(ScheduleSlot.objects.filter(offering=self.offering).count(), 1)
        body = self._section(self.vice_rector, sm_group=str(self.group.id)).content.decode()
        self.assertIn("smtx-card", body)
        self.assertIn("data-sgx-slot", body)
        self.assertNotIn("data-sedit-slot", body)

    def test_write_endpoints_still_require_schedule_manage(self):
        response = self._act(self.vice_rector, self._cell())
        self.assertEqual(response.status_code, 403)
        check = _client_for(self.vice_rector, self.org).post(reverse("accounts:schedule_manage_check"), {})
        self.assertEqual(check.status_code, 403)

    def test_manager_keeps_the_full_editor(self):
        body = self._section(self.coordinator, sm_group=str(self.group.id)).content.decode()
        self.assertIn("data-sedit-new", body)
        self.assertIn('id="seditCell"', body)
        self.assertNotIn("data-sedit-read-only", body)

    def test_plain_teacher_still_has_no_section(self):
        self.assertNotIn("schedule-manage", _sections(self.teacher, self.org))

    def test_unit_view_holder_without_scope_sees_the_locked_state(self):
        unscoped = _custom_member(
            self.org, "b11_unit_no_scope", permissions=["schedule.view"], scope_type=RoleScopeType.UNIT
        )
        body = self._section(unscoped).content.decode()
        self.assertNotIn("smtx__table", body)


# ── B16 — «Dərs yüküm» yalnız dərs deyənə ─────────────────────────────────────────────────


@override_settings(UNIVERSITY_MODE=True)
class MyWorkloadVisibilityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.workload.tests.factories import make_org, make_row, make_structure, make_task

        cls.org = make_org("b16-wl")
        cls.stack = make_structure(cls.org, code="B16")
        cls.office_staff = _member(cls.org, "b16_office", "teaching_office_staff")
        cls.rim_staff = _member(cls.org, "b16_rim", "rim_staff")
        cls.trustee = _member(cls.org, "b16_trustee", "trustee")
        cls.teacher = _member(cls.org, "b16_teacher", "teacher", scope_unit=cls.stack["chair"])
        cls.dean = _member(cls.org, "b16_dean", "dean", scope_unit=cls.stack["faculty"])
        cls.teaching_dean = _member(cls.org, "b16_teaching_dean", "dean", scope_unit=cls.stack["faculty"])
        task = make_task(cls.org, cls.stack["chair"])
        cls.row = make_row(task, cls.stack)

    def _assign(self, teacher):
        from apps.workload.models import TeacherAssignment

        with bypass_rls():
            TeacherAssignment.objects.create(
                organization=self.org, row=self.row, teacher=teacher, activity="lecture", hours=10
            )

    def test_non_teaching_view_holders_do_not_get_an_empty_page(self):
        for user in (self.office_staff, self.rim_staff, self.trustee, self.dean):
            with self.subTest(user=user.username):
                self.assertNotIn("my-workload", _sections(user, self.org))

    def test_teacher_template_keeps_the_section_without_rows(self):
        self.assertIn("my-workload", _sections(self.teacher, self.org))

    def test_dean_who_teaches_keeps_the_section(self):
        self._assign(self.teaching_dean)
        self.assertIn("my-workload", _sections(self.teaching_dean, self.org))
        fragment = _client_for(self.teaching_dean, self.org).get(
            reverse("accounts:profile_section_fragment", kwargs={"section": "my-workload"})
        )
        self.assertEqual(fragment.status_code, 200)

    def test_workload_object_holder_does_not_query_assignments(self):
        """Kabinet qabığı sorğu büdcəlidir: açar yoxlaması keçəndə `TeacherAssignment` EXISTS getmir."""
        from apps.accounts.views._helpers.rbac import _role_capabilities

        user = User.objects.get(pk=self.teacher.pk)
        user.set_active_organization_context(self.org)
        with CaptureQueriesContext(connection) as captured:
            capabilities = _role_capabilities(user, user.profile)
        self.assertIn("my-workload", capabilities["allowed_sections"])
        self.assertFalse(any("workload_teacherassignment" in q["sql"] for q in captured.captured_queries))
