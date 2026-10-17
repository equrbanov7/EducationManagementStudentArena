"""Məcburi profil məlumatları qapısı (sahib 2026-10-17): boş FİN / telefon / e-poçt girişdən sonra doldurulur.

Kilidlənən qaydalar:

* boş vacib sahəsi olan tələbə / müəllim hər səhifədə «Məlumatlarınızı tamamlayın»a yönlənir, AJAX 403 JSON alır;
* səhifənin özü, çıxış, parol bərpası, dil seçimi, statik / sağlamlıq ucları açıqdır;
* düzgün dəyər girişi açır və vaxt damğası qoyur; yanlış FİN və başqa hesabın FİN-i rədd olunur (heç nə yazılmır);
* superuser, ``qa.*``, rolsuz / məzun hesablar və view-as dayandırılmır;
* qəza açarı və sahə açarları (``profile.*``) qapını söndürür;
* rəsmi mənbədən (ATİS) gələn dolu sahə yenidən soruşulmur və POST ilə dəyişdirilə bilmir;
* audit və loglarda FİN / telefon DƏYƏRİ yoxdur — yalnız sahə adları.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts import profile_completion as policy
from apps.accounts.models import RuntimeSetting
from apps.accounts.services.profile_completion import AUDIT_REASON_CONFLICT, AUDIT_REASON_SAVED, IDENTITY_CHECK_SCOPE
from apps.accounts.services.rim.search import FLAG_INCOMPLETE, apply_flag_filter
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization, Role
from core import runtime_settings as rs
from core.constants import OrganizationType, RoleScopeType
from core.rate_limit import clear_rate_limit

User = get_user_model()

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "profile-completion"}}
OTHER_FIN = "7XYZ99Q"
ATIS_FIN = "4ATIS01"


@override_settings(PROFILE_COMPLETION_ENABLED=True)
class ProfileCompletionGateTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("pc_owner", "pc_owner@qku.edu.az", "pw")
        cls.org = Organization.objects.create(
            name="PC Univ", slug="pc-univ", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active"
        )
        cls.roles = {}
        for name, level in (("student", 10), ("teacher", 40), ("alumni", 5)):
            cls.roles[name], _ = Role.objects.update_or_create(
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
        cls.student = cls._member("pc_student", "student", fin="", phone="050 111 22 33")
        cls.teacher = cls._member("pc_teacher", "teacher", fin="", phone="")
        cls.complete = cls._member("pc_complete", "student", fin="2CMPL01", phone="+994501112233")
        cls.atis = cls._member("pc_atis", "student", fin=ATIS_FIN, phone="")
        cls.qa_user = cls._member("qa.student", "student", fin="", phone="")
        cls.alumnus = cls._member("pc_alumnus", "alumni", fin="", phone="")
        cls.other = cls._member("pc_other", "student", fin=OTHER_FIN, phone="+994509998877")

    @classmethod
    def _member(cls, username, role, *, fin, phone, email=None):
        user = User.objects.create_user(username, email or f"{username.replace('.', '_')}@gmail.com", "pw")
        profile = user.profile
        profile.fin = fin or None
        profile.phone = phone
        profile.organization = cls.org
        profile.save(update_fields=["fin", "phone", "organization", "updated_at"])
        Membership.objects.create(
            user=user, organization=cls.org, role=cls.roles[role], is_primary=True, is_active=True
        )
        return user

    def setUp(self):
        self.client = Client()
        self.url = reverse("accounts:complete_profile")
        rs.invalidate()
        for user in (self.student, self.teacher):
            clear_rate_limit(IDENTITY_CHECK_SCOPE, user.pk)

    def _get(self, user, path=None, **headers):
        self.client.force_login(user)
        return self.client.get(path or reverse("accounts:profile"), headers=headers)

    # ── Qapı ────────────────────────────────────────────────────────────────────────────────────────────

    def test_student_missing_fin_is_redirected(self):
        response = self._get(self.student)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], self.url)

    def test_redirect_keeps_next_for_get(self):
        response = self._get(self.student, reverse("accounts:my_results"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].startswith(self.url + "?next="))

    def test_ajax_gets_403_json_with_redirect(self):
        response = self._get(self.student, reverse("accounts:my_results"), **{"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertTrue(payload["profile_completion_required"])
        self.assertEqual(payload["redirect"], self.url)

    def test_teacher_is_gated_too(self):
        response = self._get(self.teacher)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], self.url)

    def test_page_shows_only_missing_fields_with_reasons(self):
        response = self._get(self.student, self.url)
        self.assertEqual(response.status_code, 200)
        names = [field["name"] for field in response.context["fields"]]
        self.assertEqual(names, ["fin"])
        self.assertContains(response, "Nəyə lazımdır")
        self.assertContains(response, "ATİS/DİM")
        self.assertContains(response, "ictimai profilinizdə göstərilmir")

    # ── Açıq yollar ─────────────────────────────────────────────────────────────────────────────────────

    def test_allow_list(self):
        self.client.force_login(self.student)
        for path in (
            self.url,
            reverse("accounts:password_reset"),
            reverse("accounts:password_reset_done"),
            "/static/css/main.css",
            "/health/",
            "/jsi18n/",
            "/live/",
            "/exams/",
            "/exams/final/waiting/1/",
        ):
            response = self.client.get(path)
            location = response.headers.get("Location", "")
            self.assertFalse(location.startswith(self.url), f"{path} gated")
        response = self.client.post("/i18n/setlang/", {"language": "en", "next": "/"})
        self.assertFalse(response.headers.get("Location", "").startswith(self.url))
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(response.headers["Location"].startswith(self.url))

    # ── Yazı ────────────────────────────────────────────────────────────────────────────────────────────

    def test_valid_fin_unlocks_and_stamps(self):
        self.client.force_login(self.student)
        response = self.client.post(self.url, {"fin": " 5abc 12d "})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("accounts:profile"))
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.fin, "5ABC12D")
        self.assertTrue(self.student.profile.fin_self_reported)  # rəsmi idxal təsdiqləyənə qədər
        self.assertIsNotNone(self.student.profile.profile_completed_at)
        response = self.client.get(reverse("accounts:my_results"))
        self.assertFalse(response.headers.get("Location", "").startswith(self.url))
        self.assertTrue(AuditLog.objects.filter(reason=AUDIT_REASON_SAVED, object_id=str(self.student.pk)).exists())

    def test_valid_submit_returns_to_next(self):
        self.client.force_login(self.student)
        target = reverse("accounts:my_results")
        response = self.client.post(self.url, {"fin": "5ABC12D", "next": target})
        self.assertEqual(response.headers["Location"], target)
        # İkinci POST-da sahə artıq doludur → səhifə dərhal çıxarır; xarici ``next`` heç vaxt işlənmir.
        response = self.client.post(self.url, {"fin": "5ABC12D", "next": "https://evil.example/x"})
        self.assertEqual(response.headers["Location"], reverse("accounts:profile"))

    def test_invalid_fin_is_rejected(self):
        self.client.force_login(self.student)
        for bad in ("12345", "5ABC12D9", "5AB-12D", "ƏABC12D"):
            response = self.client.post(self.url, {"fin": bad})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["fields"][0]["error"])
        self.student.profile.refresh_from_db()
        self.assertIsNone(self.student.profile.fin)
        self.assertIsNone(self.student.profile.profile_completed_at)

    def test_duplicate_fin_is_rejected_and_audited_without_value(self):
        self.client.force_login(self.student)
        response = self.client.post(self.url, {"fin": OTHER_FIN.lower()})
        self.assertEqual(response.status_code, 200)
        self.assertIn("başqa hesabda", response.context["fields"][0]["error"])
        self.assertNotContains(response, "pc_other")
        self.student.profile.refresh_from_db()
        self.assertIsNone(self.student.profile.fin)
        row = AuditLog.objects.get(reason=AUDIT_REASON_CONFLICT, object_id=str(self.student.pk))
        self.assertEqual(row.changes["fields"], ["fin"])
        self.assertNotIn(OTHER_FIN, json.dumps(row.changes) + json.dumps(row.new_values or {}))

    def test_fin_uniqueness_is_not_checked_while_other_fields_are_invalid(self):
        # SEC-1 F1: «phone=x» + başqasının FİN-i → yalnız telefon xətası; FİN-in mövcudluğu SÖYLƏNMİR.
        self.client.force_login(self.teacher)
        response = self.client.post(self.url, {"fin": OTHER_FIN, "phone": "x"})
        self.assertEqual(response.status_code, 200)
        errors = {field["name"]: field["error"] for field in response.context["fields"]}
        self.assertEqual(errors["fin"], "")
        self.assertTrue(errors["phone"])
        self.assertFalse(AuditLog.objects.filter(reason=AUDIT_REASON_CONFLICT, object_id=str(self.teacher.pk)).exists())

    @override_settings(PROFILE_COMPLETION_IDENTITY_RATE_LIMIT="3/1h")
    def test_fin_uniqueness_checks_are_rate_limited(self):
        self.client.force_login(self.student)
        for _ in range(3):
            response = self.client.post(self.url, {"fin": OTHER_FIN})
            self.assertIn("başqa hesabda", response.context["fields"][0]["error"])
        response = self.client.post(self.url, {"fin": OTHER_FIN})
        error = response.context["fields"][0]["error"]
        self.assertNotIn("başqa hesabda", error)
        self.assertIn("dəqiqə", error)
        self.assertEqual(
            AuditLog.objects.filter(reason=AUDIT_REASON_CONFLICT, object_id=str(self.student.pk)).count(), 3
        )
        # Limit doluykən düzgün (boş) FİN də yazılmır — növbəti pəncərədə.
        self.client.post(self.url, {"fin": "5ABC12D"})
        self.student.profile.refresh_from_db()
        self.assertIsNone(self.student.profile.fin)

    def test_phone_operator_select_is_combined(self):
        # Sahib 2026-10-17: operator (050, 055 …) seçilir, xanaya qalan 7 rəqəm yazılır.
        self.client.force_login(self.teacher)
        page = self.client.get(self.url)
        self.assertContains(page, 'name="phone_operator"')
        self.assertContains(page, '<option value="055"')
        self.assertContains(page, "123 45 67")
        response = self.client.post(self.url, {"fin": "6TCH002", "phone_operator": "055", "phone": "123 45 67"})
        self.assertEqual(response.status_code, 302)
        self.teacher.profile.refresh_from_db()
        self.assertEqual(self.teacher.profile.phone, "+994551234567")

    def test_phone_operator_requires_seven_digits_and_keeps_choice(self):
        self.client.force_login(self.teacher)
        response = self.client.post(self.url, {"fin": "6TCH003", "phone_operator": "070", "phone": "12345"})
        self.assertEqual(response.status_code, 200)
        errors = {field["name"]: field["error"] for field in response.context["fields"]}
        self.assertIn("7 rəqəm", errors["phone"])
        self.assertEqual(response.context["phone_operator"], "070")
        self.teacher.profile.refresh_from_db()
        self.assertIsNone(self.teacher.profile.fin)

    def test_foreign_phone_with_other_operator(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            self.url, {"fin": "6TCH004", "phone_operator": "other", "phone": "+90 555 123 45 67"}
        )
        self.assertEqual(response.status_code, 302)
        self.teacher.profile.refresh_from_db()
        self.assertEqual(self.teacher.profile.phone, "+905551234567")

    def test_teacher_fills_all_three_with_phone_normalised(self):
        self.teacher.email = ""
        self.teacher.save(update_fields=["email"])
        self.client.force_login(self.teacher)
        response = self.client.get(self.url)
        self.assertEqual([field["name"] for field in response.context["fields"]], ["fin", "phone", "email"])
        response = self.client.post(
            self.url, {"fin": "6TCH001", "phone": "050 123 45 67", "email": "Muellim@Gmail.com"}
        )
        self.assertEqual(response.status_code, 302)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.profile.fin, "6TCH001")
        self.assertEqual(self.teacher.profile.phone, "+994501234567")
        self.assertEqual(self.teacher.email, "muellim@gmail.com")
        self.assertFalse(self.teacher.profile.email_verified)

    def test_placeholder_email_is_missing_and_taken_email_rejected(self):
        self.teacher.email = "intake.x@placeholder.invalid"
        self.teacher.save(update_fields=["email"])
        self.client.force_login(self.teacher)
        response = self.client.post(
            self.url, {"fin": "6TCH001", "phone": "0501234567", "email": self.other.email.upper()}
        )
        self.assertEqual(response.status_code, 200)
        errors = {field["name"]: field["error"] for field in response.context["fields"]}
        self.assertTrue(errors["email"])
        self.teacher.refresh_from_db()
        self.assertIsNone(self.teacher.profile.fin)  # xəta varsa heç nə yazılmır

    # ── Rəsmi mənbə ─────────────────────────────────────────────────────────────────────────────────────

    def test_official_source_fin_is_not_asked_or_overwritten(self):
        self.client.force_login(self.atis)
        response = self.client.get(self.url)
        self.assertEqual([field["name"] for field in response.context["fields"]], ["phone"])
        self.client.post(self.url, {"phone": "+994 55 222 33 44", "fin": "9HACK99"})
        self.atis.profile.refresh_from_db()
        self.assertEqual(self.atis.profile.fin, ATIS_FIN)
        self.assertEqual(self.atis.profile.phone, "+994552223344")

    def test_complete_user_is_not_gated_and_page_bounces(self):
        self.assertFalse(self._get(self.complete, reverse("accounts:my_results")).headers.get("Location", ""))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], reverse("accounts:profile"))

    # ── Azadlar və açarlar ──────────────────────────────────────────────────────────────────────────────

    def test_exempt_accounts_are_not_gated(self):
        superuser = User.objects.create_superuser("pc_root", "pc_root@qku.edu.az", "pw")
        for user in (superuser, self.qa_user, self.alumnus, self.owner):
            response = self._get(user, reverse("accounts:my_results"))
            self.assertFalse(response.headers.get("Location", "").startswith(self.url), user.username)

    def test_first_login_flow_takes_precedence(self):
        profile = self.student.profile
        profile.password_change_required = True
        profile.save(update_fields=["password_change_required", "updated_at"])
        response = self._get(self.student)
        self.assertEqual(response.headers["Location"], reverse("accounts:set_initial_password"))

    def test_setting_off_disables_gate(self):
        with override_settings(PROFILE_COMPLETION_ENABLED=False):
            response = self._get(self.student, reverse("accounts:my_results"))
        self.assertFalse(response.headers.get("Location", "").startswith(self.url))

    @override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
    def test_runtime_switches(self):
        rs.invalidate()
        RuntimeSetting.objects.create(key="profile.required_fields_enabled", value=False)
        rs.invalidate()
        response = self._get(self.student, reverse("accounts:my_results"))
        self.assertFalse(response.headers.get("Location", "").startswith(self.url))
        RuntimeSetting.objects.filter(key="profile.required_fields_enabled").delete()
        RuntimeSetting.objects.create(key="profile.require_fin", value=False)
        rs.invalidate()
        response = self.client.get(reverse("accounts:my_results"))
        self.assertFalse(response.headers.get("Location", "").startswith(self.url))  # yalnız FİN boş idi
        rs.invalidate()

    def test_skip_lets_through_this_session_only(self):
        # Sahib 2026-10-17: «hələlik keçmək üçün skip olsun, amma doldurana kimi hər daxil olduqca gəlsin».
        results = reverse("accounts:my_results")
        self.client.force_login(self.student)
        page = self.client.get(self.url)
        self.assertContains(page, 'name="skip"')
        response = self.client.post(self.url, {"skip": "1", "next": results})
        self.assertEqual(response.headers["Location"], results)
        response = self.client.get(results)
        self.assertFalse(response.headers.get("Location", "").startswith(self.url))
        self.student.profile.refresh_from_db()
        self.assertIsNone(self.student.profile.fin)  # heç nə yazılmır
        self.assertTrue(
            AuditLog.objects.filter(reason="profile_completion_skipped", object_id=str(self.student.pk)).exists()
        )
        # Yeni giriş → səhifə yenə gəlir.
        self.client.logout()
        self.client.force_login(self.student)
        response = self.client.get(results)
        self.assertTrue(response.headers.get("Location", "").startswith(self.url))

    @override_settings(RUNTIME_SETTINGS_ENABLED=True)
    def test_skip_can_be_switched_off(self):
        RuntimeSetting.objects.create(key="profile.allow_skip", value=False)
        rs.invalidate()
        try:
            self.client.force_login(self.student)
            self.assertNotContains(self.client.get(self.url), 'name="skip"')
            response = self.client.post(self.url, {"skip": "1"})
            self.assertEqual(response.status_code, 200)  # ötürmə qəbul olunmur — forma xətası
            response = self.client.get(reverse("accounts:my_results"))
            self.assertTrue(response.headers.get("Location", "").startswith(self.url))
        finally:
            RuntimeSetting.objects.filter(key="profile.allow_skip").delete()
            rs.invalidate()

    def test_view_as_request_is_never_gated(self):
        request = SimpleNamespace(is_view_as=True, user=self.student, org_memberships=[])
        self.assertEqual(policy.missing_for_request(request), [])

    # ── RİM filtri və loglar ────────────────────────────────────────────────────────────────────────────

    def test_rim_incomplete_filter(self):
        usernames = set(apply_flag_filter(User.objects.all(), FLAG_INCOMPLETE).values_list("username", flat=True))
        self.assertIn("pc_student", usernames)
        self.assertIn("pc_teacher", usernames)
        self.assertIn("pc_atis", usernames)
        self.assertNotIn("pc_complete", usernames)
        self.assertNotIn("qa.student", usernames)
        self.assertNotIn("pc_alumnus", usernames)

    def test_no_values_in_logs_or_audit(self):
        self.client.force_login(self.teacher)
        with self.assertLogs("apps.accounts", level=logging.DEBUG) as captured:
            logging.getLogger("apps.accounts").debug("marker")
            self.client.post(self.url, {"fin": "8SECRET", "phone": "0557654321"})
        joined = "\n".join(captured.output) + "\n".join(str(getattr(r, "fields", "")) for r in captured.records)
        self.assertNotIn("8SECRET", joined)
        self.assertNotIn("557654321", joined)
        for row in AuditLog.objects.filter(object_id=str(self.teacher.pk)):
            dumped = json.dumps([row.changes, row.old_values, row.new_values, row.resource_repr], default=str)
            self.assertNotIn("8SECRET", dumped)
            self.assertNotIn("557654321", dumped)


class ProfileCompletionCleanersTest(SimpleTestCase):
    def test_combine_phone(self):
        self.assertEqual(policy.combine_phone({"phone_operator": "050", "phone": "1234567"}), "0501234567")
        self.assertEqual(policy.combine_phone({"phone_operator": "050", "phone": "050 123 45 67"}), "0501234567")
        self.assertEqual(policy.combine_phone({"phone_operator": "099", "phone": "99 123 45 67"}), "0991234567")
        self.assertEqual(policy.combine_phone({"phone": "050 123 45 67"}), "050 123 45 67")  # köhnə forma
        self.assertEqual(policy.combine_phone({"phone_operator": "050", "phone": ""}), "")
        for bad in ("123456", "12345678", "12a4567"):
            with self.assertRaises(ValidationError):
                policy.combine_phone({"phone_operator": "050", "phone": bad})

    def test_phone_normalisation(self):
        cases = {
            "050 123 45 67": "+994501234567",
            "(055) 123-45-67": "+994551234567",
            "501234567": "+994501234567",
            "994701234567": "+994701234567",
            "+90 532 123 45 67": "+905321234567",
        }
        for raw, expected in cases.items():
            self.assertEqual(policy.clean_phone(raw), expected, raw)
        for bad in ("", "123", "abc 123 45 67", "05012345678901234"):
            with self.assertRaises(ValidationError, msg=bad):
                policy.clean_phone(bad)

    def test_fin_normalisation(self):
        self.assertEqual(policy.clean_fin(" 5abc12d "), "5ABC12D")
        for bad in ("", "5ABC12", "5ABC12DD", "5AB_12D"):
            with self.assertRaises(ValidationError, msg=bad):
                policy.clean_fin(bad)

    def test_role_family(self):
        def membership(name):
            return SimpleNamespace(is_active=True, role=SimpleNamespace(name=name, is_active=True))

        self.assertEqual(policy.role_family([membership("student")]), policy.ROLE_STUDENT)
        self.assertEqual(policy.role_family([membership("student"), membership("teacher")]), policy.ROLE_STAFF)
        self.assertEqual(policy.role_family([membership("alumni")]), "")
        self.assertEqual(policy.role_family([]), "")
