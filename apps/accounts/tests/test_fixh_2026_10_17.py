"""FIX-H (QA dalğası 2026-10-17) — qalan QA-2 / SEC-1 / SEC-2 tapıntıları.

1. «Heyət idarəetməsi» (tələbə qoşulma müraciətləri) tələbə tərəfi AÇARI ilə açılır — HR itirir, RİM saxlayır.
2. «Rolları idarə et»: gizli tələbə rol / üzvlük axtarışından ƏVVƏL «tapılmadı» alır (mesajlar eynidir).
3. Profil qapısı `/exams/` altında yalnız imtahan VERƏNİN yollarını buraxır (SEC-1 F6 / QA-2 F-12).
4. Rəhbər hesabda tam rəqəm / tarix parolu olmaz; `password.min_length` 8-dən aşağı yazılmır (SEC-1 F5).
5. «Məlumat natamam» süzgəci qapının azadlıqlarını sayır (QA-2 F-13); rate pəncərəsi xətası (QA-2 F-09).
6. Soft-deny 200 → 403 (SEC-2 F-4).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts import password_policy
from apps.accounts import profile_completion as policy
from apps.accounts.models import RuntimeSetting
from apps.accounts.services import runtime_settings_admin
from apps.accounts.views._helpers.student_org_access import holds_student_side_key
from apps.accounts.views.roles import _multi_role
from apps.organizations.models import Membership, Organization, Role
from core import runtime_settings as rs
from core.constants import OrganizationType, RoleScopeType
from core.rls import bypass_rls

from .people_fixture import add_membership, make_role, make_user
from .test_fixa_2026_10_17 import _client
from .test_fixa_c_2026_10_17 import _CBase

User = get_user_model()
PROFILE_URL = "/accounts/profile/"
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "fixh"}}


# ── 1–2. Heyət idarəetməsi + «Rolları idarə et» ─────────────────────────────────────────────────────────


class StudentOrgManagementByKeyTest(_CBase):
    def section_open(self, actor) -> bool:
        with bypass_rls():
            response = _client(actor, self.fx.org).get(PROFILE_URL, {"section": "student-organization-management"})
        self.assertEqual(response.status_code, 200)
        return response.context.get("active_section") == "student-organization-management"

    def test_hr_loses_the_section_rim_keeps_it(self):
        with bypass_rls():
            self.assertFalse(holds_student_side_key(self.fx.hr_full, self.fx.org))
            self.assertTrue(holds_student_side_key(self.fx.ikt, self.fx.org))
        self.assertFalse(self.section_open(self.fx.hr_full))
        self.assertTrue(self.section_open(self.fx.ikt))

    def test_hr_post_is_refused_before_any_action(self):
        with bypass_rls():
            response = _client(self.fx.hr_full, self.fx.org).post(
                reverse("accounts:student_organization_management"),
                {"action": "remove_org_member", "user_id": str(self.fx.teacher_a.pk), "remove_reason": "Yoxlama"},
            )
            still_member = Membership.objects.filter(
                user=self.fx.teacher_a, organization=self.fx.org, is_active=True
            ).exists()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("accounts:profile"))
        self.assertTrue(still_member)

    def test_key_not_role_name_decides(self):
        # «Hər rol öz səlahiyyəti qədər»: icazə redaktorunda HR-a tələbə açarı verilsə, bölmə qayıdır.
        with bypass_rls():
            Role.objects.filter(pk=self.fx.role_hr_full.pk).update(
                permissions=[*self.fx.role_hr_full.permissions, "people.view_students"]
            )
            self.assertTrue(holds_student_side_key(User.objects.get(pk=self.fx.hr_full.pk), self.fx.org))
        self.assertTrue(self.section_open(self.fx.hr_full))


class MultiRoleHiddenStudentOrderTest(_CBase):
    def call(self, handler, actor, data):
        request = RequestFactory().post("/accounts/roles/manage/", data)
        request.user = actor
        request.session = SessionStore()
        request._messages = FallbackStorage(request)
        with bypass_rls():
            handler(request, organization=self.fx.org, is_superadmin=False, actor_level=65, next_url="/x/")
        return [str(message) for message in get_messages(request)]

    def test_grant_with_bogus_role_hidden_student_equals_non_member(self):
        outsider = make_user("fxh_outsider", first="Kənar", last="Adam")
        bogus = {"action": "grant_role", "role_id": "999999"}
        hidden = self.call(_multi_role._grant, self.fx.hr_full, {**bogus, "user_id": str(self.fx.student_a.pk)})
        missing = self.call(_multi_role._grant, self.fx.hr_full, {**bogus, "user_id": str(outsider.pk)})
        self.assertEqual(hidden, missing)
        self.assertEqual(hidden, [pgettext("accounts.manage_roles.message", "manage_only_own_org_users")])

    def test_revoke_hidden_student_membership_is_not_found(self):
        with bypass_rls():
            membership = Membership.objects.filter(user=self.fx.student_a, organization=self.fx.org).first()
        hidden = self.call(_multi_role._revoke, self.fx.hr_full, {"membership_id": str(membership.pk)})
        missing = self.call(_multi_role._revoke, self.fx.hr_full, {"membership_id": "999999"})
        self.assertEqual(hidden, missing)

    def test_non_integer_user_id_is_not_selected_not_500(self):
        for raw in ("abc", "1.5", "", "  "):
            with self.subTest(raw=raw):
                messages = self.call(_multi_role._grant, self.fx.hr_full, {"action": "grant_role", "user_id": raw})
                self.assertEqual(messages, [pgettext("accounts.manage_roles.message", "user_not_selected")])

    def test_rim_is_not_affected(self):
        request = RequestFactory().post("/x/")
        request.user = self.fx.ikt
        with bypass_rls():
            self.assertFalse(
                _multi_role._is_hidden_student(request, self.fx.org, self.fx.student_a, is_superadmin=False)
            )


# ── 3. Profil qapısı və /exams/ ─────────────────────────────────────────────────────────────────────────


@override_settings(PROFILE_COMPLETION_ENABLED=True)
class ExamGateNarrowedTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("fxh_owner", "fxh_owner@qku.edu.az", "pw")
        cls.org = Organization.objects.create(
            name="FXH Univ", slug="fxh-univ", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
        )
        roles = {}
        for name, level in (("student", 10), ("teacher", 60)):
            roles[name], _ = Role.objects.update_or_create(
                organization=cls.org,
                name=name,
                defaults={
                    "display_name": name,
                    "level": level,
                    "scope_type": RoleScopeType.ORGANIZATION,
                    "permissions": [],
                    "is_active": True,
                },
            )
        cls.student = cls._member("fxh_student", roles["student"])
        cls.teacher = cls._member("fxh_teacher", roles["teacher"])

    @classmethod
    def _member(cls, username, role):
        user = User.objects.create_user(username, f"{username}@gmail.com", "pw")
        profile = user.profile
        profile.fin = None  # vacib sahə boşdur → qapı açıqdır
        profile.phone = "050 111 22 33"
        profile.organization = cls.org
        profile.save(update_fields=["fin", "phone", "organization", "updated_at"])
        Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
        return user

    def setUp(self):
        rs.invalidate()
        self.gate = reverse("accounts:complete_profile")

    def _gated(self, response) -> bool:
        if response.status_code == 403 and response.headers.get("Content-Type", "").startswith("application/json"):
            return bool(response.json().get("profile_completion_required"))
        return response.headers.get("Location", "").startswith(self.gate)

    def _client(self, user):
        client = Client()
        client.force_login(user)
        return client

    TAKER_PATHS = (
        "/exams/",
        "/exams/available/",
        "/exams/final/",
        "/exams/final/waiting/1/",
        "/exams/final/waiting/1/state/",
        "/exams/code-check/",
        "/exams/sinaq-imtahan/start/",
        "/exams/sinaq-imtahan/attempt/1/",
        "/exams/sinaq-imtahan/attempt/1/question-seen/",
        "/exams/sinaq-imtahan/attempt/1/result/",
        "/exams/sinaq-imtahan/attempt/1/coding/autosave/",
        "/exams/supervision/api/heartbeat/1/",
        "/exams/supervision/api/status/1/",
        # Cəhd səhifəsi tələbənin öz şəklini buradan yükləyir (review P2); view öz / heyət əhatəsini yoxlayır.
        "/exams/supervision/photo/1/",
        # Naməlum yol onsuz da 404-dür (review P1: həll olunmayan yol qapıda dayanmır).
        "/exams/yox/bele/bir/yol/",
    )
    STAFF_PATHS = (
        "/exams/center/rooms/",
        "/exams/center/reports/",
        "/exams/center/pin-lookup/search/",
        "/exams/question-bank/",
        "/exams/question-submissions/new/",
        "/exams/lookups/users/",
        "/exams/groups/",
        "/exams/create/",
        "/exams/sinaq-imtahan/",
        "/exams/sinaq-imtahan/results/",
        "/exams/sinaq-imtahan/edit/",
    )

    def test_exam_taker_paths_are_never_gated_for_anyone(self):
        for user in (self.student, self.teacher):
            client = self._client(user)
            for path in self.TAKER_PATHS:
                with self.subTest(user=user.username, path=path):
                    self.assertFalse(self._gated(client.get(path)), path)
            # Cəhd zamanı POST (proktorinq / avtosaxlama) da kəsilmir.
            for path in ("/exams/supervision/api/heartbeat/1/", "/exams/sinaq-imtahan/attempt/1/"):
                with self.subTest(user=user.username, post=path):
                    self.assertFalse(self._gated(client.post(path, {})), path)

    def test_hand_typed_final_urls_reach_the_pin_page(self):
        # Review P1: zalda «/exams/final» (sonda «/» yoxdur) və «/exmas/final» yazılır — heç biri qapıya düşmür.
        client = self._client(self.student)
        for path in ("/exams/final", "/exams", "/exmas/final", "/exmas/final/", "/exmas"):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertFalse(self._gated(response), path)
                followed = client.get(path, follow=True)
                for hop, _status in followed.redirect_chain:
                    self.assertFalse(hop.startswith(self.gate), (path, hop))
        final = client.get("/exams/final", follow=True)
        self.assertEqual(final.redirect_chain[-1][0], reverse("exams:final_exam_entry"))

    def test_staff_exam_management_is_gated(self):
        client = self._client(self.teacher)
        for path in self.STAFF_PATHS:
            with self.subTest(path=path):
                self.assertTrue(self._gated(client.get(path)), path)
        ajax = client.get("/exams/lookups/users/", {"q": "ab"}, headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(ajax.status_code, 403)
        self.assertTrue(ajax.json()["profile_completion_required"])

    def test_skip_still_lets_staff_through(self):
        client = self._client(self.teacher)
        session = client.session
        session[policy.SKIP_SESSION_KEY] = True
        session.save()
        self.assertFalse(self._gated(client.get("/exams/center/rooms/")))

    def test_view_as_cannot_be_started_past_the_gate(self):
        # SEC-1 F6 (view-as): aktor qapını view-as-a girəndə keçir — başlanğıc özü qapılıdır.
        response = self._client(self.teacher).post(reverse("accounts:view_as_start"), {})
        self.assertTrue(self._gated(response))


# ── 4. Parol siyasəti ───────────────────────────────────────────────────────────────────────────────────


def _codes(password, user=None):
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        return {error.code for error in exc.error_list}
    return set()


class PrivilegedPasswordTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("fxh_pw_owner", "fxh_pw_owner@qku.edu.az", "pw")
        cls.org = Organization.objects.create(
            name="FXH PW", slug="fxh-pw", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
        )
        org_scope = RoleScopeType.ORGANIZATION
        cls.rim = make_user("fxh_pw_rim", first="Rim", last="Rəhbər")
        add_membership(
            cls.org, cls.rim, make_role(cls.org, "ikt_rehber", level=95, scope_type=org_scope, permissions=["*"])
        )
        cls.full = make_user("fxh_pw_full", first="Tam", last="Admin")
        add_membership(
            cls.org, cls.full, make_role(cls.org, "custom_full", level=90, scope_type=org_scope, permissions=["*"])
        )
        cls.teacher = make_user("fxh_pw_teacher", first="Müəl", last="Lim")
        add_membership(
            cls.org,
            cls.teacher,
            make_role(cls.org, "teacher", level=60, scope_type=org_scope, permissions=["grade.input"]),
        )
        cls.student = make_user("fxh_pw_student", first="Tələ", last="Bə")
        add_membership(
            cls.org, cls.student, make_role(cls.org, "student", level=10, scope_type=org_scope, permissions=[])
        )
        cls.superuser = User.objects.create_superuser("fxh_pw_super", "fxh_pw_super@qku.edu.az", "pw")

    def test_numeric_and_date_passwords_rejected_only_for_privileged(self):
        for password in ("19850412", "12.04.1985", "1985-04-12", "12/04/85 11"):
            for user in (self.rim, self.full, self.superuser):
                with self.subTest(password=password, user=user.username):
                    self.assertIn("password_numeric_privileged", _codes(password, user))
            for user in (self.teacher, self.student, None):
                with self.subTest(password=password, user=getattr(user, "username", None)):
                    self.assertNotIn("password_numeric_privileged", _codes(password, user))

    def test_privileged_password_with_a_letter_is_fine(self):
        self.assertEqual(_codes("Baki1985", self.rim), set())
        self.assertEqual(_codes("qala2026", self.superuser), set())

    def test_owner_of_an_organization_is_privileged_but_not_of_a_personal_workspace(self):
        self.assertTrue(password_policy.is_privileged_account(self.org.owner))
        Organization.objects.create(
            name="Şəxsi", slug="fxh-pw-ws", org_type=OrganizationType.INDIVIDUAL, owner=self.student, status="active"
        )
        self.assertFalse(password_policy.is_privileged_account(User.objects.get(pk=self.student.pk)))
        self.assertNotIn("org_owner", password_policy.PRIVILEGED_ROLE_NAMES)

    def test_rule_holds_under_an_empty_rls_context(self):
        # Review P2: anonim OTP bərpasında RLS konteksti boşdur — üzvlük görünmürdü, rektor qaydadan qaçırdı.
        from django.db import connection, transaction

        if connection.vendor != "postgresql":
            self.skipTest("RLS PostgreSQL tələb edir")
        rim = User.objects.get(pk=self.rim.pk)
        owner = User.objects.get(pk=self.org.owner_id)
        with transaction.atomic():
            with connection.cursor() as cursor:
                for name in ("app.bypass_rls", "app.current_org_id", "app.current_user_id"):
                    cursor.execute("SELECT set_config(%s, %s, true)", [name, "off" if name == "app.bypass_rls" else ""])
                cursor.execute("SET LOCAL ROLE rls_app_role")
                cursor.execute("SELECT count(*) FROM organizations_membership WHERE user_id = %s", [rim.pk])
                visible_without_bypass = cursor.fetchone()[0]
            privileged = password_policy.is_privileged_account(rim)
            owner_privileged = password_policy.is_privileged_account(owner)
        self.assertEqual(visible_without_bypass, 0, "test RLS kontekstini simulyasiya etmir")
        self.assertTrue(privileged)
        self.assertTrue(owner_privileged)

    def test_inactive_privileged_membership_does_not_count(self):
        Membership.objects.filter(user=self.rim).update(is_active=False)
        self.assertFalse(password_policy.is_privileged_account(User.objects.get(pk=self.rim.pk)))


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class MinLengthFloorTest(TestCase):
    def tearDown(self):
        rs.invalidate()

    def test_floor_is_eight(self):
        actor = User.objects.create_superuser("fxh_rs_super", "fxh_rs_super@qku.edu.az", "pw")
        for value in ("6", "7"):
            with self.subTest(value=value):
                with self.assertRaises(runtime_settings_admin.RuntimeSettingsError) as ctx:
                    runtime_settings_admin.save_values(actor=actor, data={"password.min_length": value})
                self.assertIn("password.min_length", ctx.exception.errors)

    def test_stale_six_in_the_database_falls_back_to_eight(self):
        RuntimeSetting.objects.create(key="password.min_length", value=6)
        rs.invalidate()
        self.assertEqual(password_policy.min_length(), 8)

    def test_rate_window_error_names_the_window(self):
        actor = User.objects.create_superuser("fxh_rs_super2", "fxh_rs_super2@qku.edu.az", "pw")
        with self.assertRaises(runtime_settings_admin.RuntimeSettingsError) as ctx:
            runtime_settings_admin.save_values(
                actor=actor, data={"login.device_rate.count": "10", "login.device_rate.window": "0"}
            )
        message = str(ctx.exception.errors["login.device_rate"])
        self.assertIn("1440", message)
        self.assertNotIn("3–100", message)


# ── 5. «Məlumat natamam» süzgəci ────────────────────────────────────────────────────────────────────────


@override_settings(PROFILE_COMPLETION_ENABLED=True)
class IncompleteFilterMatchesGateTest(TestCase):
    def test_first_login_inactive_and_archived_accounts_are_not_counted(self):
        names = {}
        for key in ("plain", "first_login", "inactive", "archived"):
            user = User.objects.create_user(f"fxh_inc_{key}", f"fxh_inc_{key}@gmail.com", "pw")
            names[key] = user.username
            profile = user.profile
            profile.fin = None
            profile.password_change_required = key == "first_login"
            if key == "archived":
                profile.access_state = "archived"
            profile.save()
            if key == "inactive":
                User.objects.filter(pk=user.pk).update(is_active=False)
        found = set(User.objects.filter(policy.missing_users_q()).values_list("username", flat=True))
        self.assertIn(names["plain"], found)
        for key in ("first_login", "inactive", "archived"):
            self.assertNotIn(names[key], found, key)


class RateWindowHelperTest(SimpleTestCase):
    def test_window_check(self):
        self.assertTrue(runtime_settings_admin._rate_window_ok("10/10m"))
        self.assertFalse(runtime_settings_admin._rate_window_ok("10/0m"))
        self.assertFalse(runtime_settings_admin._rate_window_ok("10/2000m"))
        self.assertFalse(runtime_settings_admin._rate_window_ok("10/abcm"))


# ── 6. Soft-deny → 403 ──────────────────────────────────────────────────────────────────────────────────


class SoftDenyIs403Test(TestCase):
    def test_unprivileged_reads_get_403_with_empty_payload(self):
        user = User.objects.create_user("fxh_plain", "fxh_plain@gmail.com", "pw")
        client = Client()
        client.force_login(user)
        for name in (
            "accounts:people_academic_groups",
            "accounts:journal_hygiene_rows",
            "accounts:legacy_review_groups",
        ):
            with self.subTest(name=name):
                response = client.get(reverse(name), headers={"X-Requested-With": "XMLHttpRequest"})
                self.assertEqual(response.status_code, 403, name)
                payload = response.json()
                self.assertFalse(payload.get("results"))


# ── 7. QA-2 F-08 / F-09 ─────────────────────────────────────────────────────────────────────────────────


class CapacityAndContractsTest(SimpleTestCase):
    def test_capacity_is_checked_only_when_configured(self):
        from types import SimpleNamespace
        from unittest import mock

        from apps.accounts.services.people import movements
        from apps.accounts.services.student_groups import configured_capacity

        self.assertIsNone(configured_capacity(SimpleNamespace(settings={})))
        self.assertIsNone(configured_capacity(SimpleNamespace(settings={"capacity": "0"})))
        self.assertEqual(configured_capacity(SimpleNamespace(settings={"capacity": "5"})), 5)
        with mock.patch("apps.accounts.services.student_groups.occupancy_map") as occupancy:
            movements._assert_capacity(SimpleNamespace(organization=None), SimpleNamespace(settings={}, pk=1))
        occupancy.assert_not_called()  # tutum yazılmayıb → hardkod 30 ilə bloklanmır

    def test_registry_content_errors_do_not_claim_no_access(self):
        import json

        from apps.accounts.services.rim.policy import RimAccessError
        from apps.accounts.views.student_registry import _error

        conflict = json.loads(_error(RimAccessError("group_full", "dolu", status=409)).content)
        denied = json.loads(_error(RimAccessError("forbidden", "yox", status=403)).content)
        self.assertTrue(conflict["has_access"])
        self.assertFalse(denied["has_access"])

    def test_workload_input_errors_are_not_403(self):
        from apps.workload.services import WorkloadDenied
        from apps.workload.views.distribution_api import _write_denied

        self.assertEqual(_write_denied(WorkloadDenied("workload.invalid_reason", "x")).status_code, 400)
        self.assertEqual(_write_denied(WorkloadDenied("workload.hours_exceeded", "x")).status_code, 409)
        self.assertEqual(_write_denied(WorkloadDenied("workload.manage_denied", "x")).status_code, 403)
