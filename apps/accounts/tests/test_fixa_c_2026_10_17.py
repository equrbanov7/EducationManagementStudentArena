"""FIX-A üçüncü dalğa (QA 2026-10-17 baxışı) — HR tələbəyə qalan yollarla da çatmır.

1. «Rol təyin et» `attach_user` — gizli tələbə «tapılmadı» (olmayan id ilə EYNİ cavab); İKT rəhbəri işləyir.
2. «Tələbə/üzv idarəetməsi» (student-organization-management) — siyahıda tələbə yoxdur, «uzaqlaşdır» POST-u
   tələbəyə toxunmur; İKT rəhbəri (`people.view_students` + `member.remove`) uzaqlaşdırır.
3. Başlıq axtarışı — HR tələbə tapmır; Tədris şöbəsi əməkdaşı (`student.records_view`) tapır.
4. «Qruplar» — starostanın adı HR-a göstərilmir, HR starosta idarə etmir (`role.assign` tələbə açarısız sayılmır).
5. «Rolları idarə et» — gizli tələbə üçün mesaj üzv olmayanla EYNİDİR.
6. `attach_user` — təşkilatı seçməmiş hədəf 500 deyil, 403 JSON verir (tənbəl mətn audit JSON-unda).
"""

from __future__ import annotations

from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.views.group_lead import can_manage_group_leads
from apps.accounts.views.roles._gates import manage_roles_gate_error
from apps.organizations.models import Membership, Role
from apps.organizations.public import build_groups_registry
from core.constants import RoleScopeType
from core.rls import bypass_rls

from .people_fixture import add_membership, make_role
from .test_fixa_2026_10_17 import _client
from .test_fixa_b_2026_10_17 import FixBFixture, _BBase

PROFILE_URL = "/accounts/profile/"


class FixCFixture(FixBFixture):
    def _build_fixa(self):
        super()._build_fixa()
        for role in (self.role_hr_full, self.role_ikt):
            Role.objects.filter(pk=role.pk).update(permissions=[*role.permissions, "member.remove"])
            role.refresh_from_db()
        Role.objects.filter(pk=self.role_office_staff.pk).update(
            permissions=[*self.role_office_staff.permissions, "unit.view", "unit.group_manage"]
        )
        self.role_office_staff.refresh_from_db()
        # Starosta: qrupun öz tələbəsi `lead_student` üzvlüyü ilə.
        self.role_lead = make_role(
            self.org, "lead_student", level=30, scope_type=RoleScopeType.UNIT, permissions=["course.view"]
        )
        add_membership(self.org, self.student_a, self.role_lead, unit=self.group_a1)


class _CBase(_BBase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = FixCFixture()

    def request_for(self, user, role):
        request = RequestFactory().get(PROFILE_URL)
        request.user = user
        request.organization = self.fx.org
        request.org_permissions = list(role.permissions)
        return request


class AttachUserHiddenStudentTest(_CBase):
    def prepare(self, actor, user_id):
        with bypass_rls():
            response = _client(actor, self.fx.org).post(
                reverse("accounts:role_assignment"),
                {
                    "action": "prepare_operation",
                    "target_action": "attach_user",
                    "user_id": str(user_id),
                    "new_role_id": str(self.fx.role_teacher.id),
                },
                HTTP_ACCEPT="application/json",
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        return response.status_code, response.json()

    def test_hr_attach_hidden_student_equals_missing_id(self):
        hidden = self.prepare(self.fx.hr_full, self.fx.student_b.pk)
        missing = self.prepare(self.fx.hr_full, 987654321)
        self.assertEqual(hidden, missing)
        self.assertEqual(hidden[1]["reason_code"], "target_user_not_found")

    def test_ikt_can_prepare_attach_for_student(self):
        with bypass_rls():
            UserProfile.objects.filter(user=self.fx.student_b).update(requested_organization=self.fx.org)
        status, payload = self.prepare(self.fx.ikt, self.fx.student_b.pk)
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["success"])

    def test_target_without_signup_choice_is_403_json_not_500(self):
        status, payload = self.prepare(self.fx.ikt, self.fx.student_b.pk)
        self.assertEqual(status, 403)
        self.assertEqual(payload["reason_code"], "user_did_not_select_this_org_on_signup")
        self.assertIsInstance(payload["message"], str)


class StudentOrgManagementTest(_CBase):
    def names(self, actor):
        with bypass_rls():
            response = _client(actor, self.fx.org).get(
                PROFILE_URL, {"section": "student-organization-management", "hm_q": "ppl"}
            )
        self.assertEqual(response.status_code, 200)
        section = response.context["student_org_management_section"]
        return {row["username"] for row in section.get("rows", [])}

    def test_hr_does_not_list_students_but_ikt_does(self):
        hr_names = self.names(self.fx.hr_full)
        self.assertIn(self.fx.teacher_a.username, hr_names)
        self.assertNotIn(self.fx.student_a.username, hr_names)
        self.assertIn(self.fx.student_a.username, self.names(self.fx.ikt))

    def remove(self, actor, target):
        with bypass_rls():
            _client(actor, self.fx.org).post(
                reverse("accounts:student_organization_management"),
                {"action": "remove_org_member", "user_id": str(target.pk), "remove_reason": "Yoxlama səbəbi"},
            )
            return Membership.objects.filter(user=target, organization=self.fx.org, is_active=True).exists()

    def test_hr_cannot_remove_student(self):
        self.assertTrue(self.remove(self.fx.hr_full, self.fx.student_b))

    def test_ikt_can_remove_student(self):
        self.assertFalse(self.remove(self.fx.ikt, self.fx.student_b))


class HeaderSearchStudentPrivacyTest(_CBase):
    def students(self, actor):
        with bypass_rls():
            payload = _client(actor, self.fx.org).get(reverse("accounts:global_search"), {"q": "Ağayeva"}).json()
        return [group for group in payload["groups"] if group["key"] == "students"]

    def test_hr_finds_no_students(self):
        self.assertEqual(self.students(self.fx.hr_full), [])

    def test_teaching_office_staff_finds_student(self):
        groups = self.students(self.fx.office_staff)
        self.assertEqual(len(groups), 1)
        self.assertTrue(groups[0]["items"])


class GroupLeadPrivacyTest(_CBase):
    def lead_names(self, actor, role):
        from apps.accounts.views.profile._sections import groups_leads

        with bypass_rls():
            rows = build_groups_registry(self.request_for(actor, role), self.fx.org)["rows"]
            groups_leads.attach_group_leads(self.fx.org, rows)
        return {row.get("lead_name", "") for row in rows if row["id"] == str(self.fx.group_a1.pk)}

    def test_hr_does_not_see_starosta_name(self):
        self.assertEqual(self.lead_names(self.fx.hr_full, self.fx.role_hr_full), {""})

    def test_group_manager_sees_starosta_name(self):
        names = self.lead_names(self.fx.office_staff, self.fx.role_office_staff)
        self.assertEqual(names, {self.fx.student_a.get_full_name()})

    def test_lead_management_needs_student_key_with_role_assign(self):
        with bypass_rls():
            self.assertFalse(
                can_manage_group_leads(self.request_for(self.fx.hr_full, self.fx.role_hr_full), self.fx.org)
            )
            self.assertTrue(can_manage_group_leads(self.request_for(self.fx.ikt, self.fx.role_ikt), self.fx.org))
            self.assertTrue(
                can_manage_group_leads(self.request_for(self.fx.office_staff, self.fx.role_office_staff), self.fx.org)
            )

    def test_hr_lead_action_is_forbidden(self):
        with bypass_rls():
            response = _client(self.fx.hr_full, self.fx.org).post(
                reverse("accounts:group_lead_action"), {"action": "remove", "group_id": str(self.fx.group_a1.pk)}
            )
            still_lead = Membership.objects.filter(
                user=self.fx.student_a, role=self.fx.role_lead, is_active=True
            ).exists()
        self.assertEqual(response.status_code, 403)
        self.assertTrue(still_lead)


class ManageRolesGateMessageTest(_CBase):
    def test_hidden_student_message_equals_non_member(self):
        request = self.request_for(self.fx.hr_full, self.fx.role_hr_full)
        with bypass_rls():
            message = manage_roles_gate_error(request, self.fx.org, self.fx.student_a, is_superadmin=False)
            allowed = manage_roles_gate_error(
                self.request_for(self.fx.ikt, self.fx.role_ikt), self.fx.org, self.fx.student_a, is_superadmin=False
            )
        from django.utils.translation import pgettext

        self.assertEqual(str(message), pgettext("accounts.manage_roles.message", "manage_only_own_org_users"))
        self.assertIsNone(allowed)
