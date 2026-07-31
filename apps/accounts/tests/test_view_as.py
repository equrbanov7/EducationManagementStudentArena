"""
"View as" (istifadəçi profilinə baxış) testləri.

Təhlükəsizlik fokusu:
- tenant izolyasiyası (başqa org-un istifadəçisinə keçid QADAĞANDIR),
- rol iyerarxiyası (aşağı səviyyə yuxarını görə bilməz),
- readonly rejimdə unsafe metodların bloklanması,
- FULL rejimdə belə həssas əməliyyatların (şifrə/hesab) bloklanması,
- superuser hədəf ola bilməz, nested view-as yoxdur.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.accounts.services.view_as import (
    MODE_FULL,
    MODE_LIMITED,
    MODE_READONLY,
    VIEW_AS_SESSION_KEY,
    resolve_actor_access,
    validate_target,
)
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from core.constants import OrganizationType, OrgUnitType, RoleScopeType

User = get_user_model()

PASSWORD = "StrongPass123!"


def _make_role(organization, name, level, permissions=None):
    role, _ = Role.objects.update_or_create(
        organization=organization,
        name=name,
        defaults={
            "display_name": name.replace("_", " ").title(),
            "level": level,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": permissions or [],
            "is_system": False,
            "is_active": True,
        },
    )
    return role


def _add_member(user, organization, role):
    return Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={"role": role, "is_active": True, "is_primary": True},
    )[0]


class ViewAsTestBase(TestCase):
    def setUp(self):
        self.client = Client()

        self.owner = User.objects.create_user("org_owner", "owner@example.com", PASSWORD)
        self.org = Organization.objects.create(
            name="Test Univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.other_owner = User.objects.create_user("other_owner", "other@example.com", PASSWORD)
        self.other_org = Organization.objects.create(
            name="Other Univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.other_owner,
            status="active",
            is_active=True,
        )

        self.admin_role = _make_role(self.org, ProfileRole.ORG_ADMIN, 80)
        self.teacher_role = _make_role(self.org, ProfileRole.TEACHER, 60)
        self.student_role = _make_role(self.org, ProfileRole.STUDENT, 10)
        self.tutor_role = _make_role(self.org, "tutor", 40)

        self.admin = User.objects.create_user("org_admin", "admin@example.com", PASSWORD)
        self.teacher = User.objects.create_user("teacher1", "teacher@example.com", PASSWORD)
        self.student = User.objects.create_user("student1", "student@example.com", PASSWORD)
        self.tutor = User.objects.create_user("tutor1", "tutor@example.com", PASSWORD)
        _add_member(self.admin, self.org, self.admin_role)
        _add_member(self.teacher, self.org, self.teacher_role)
        self.student_membership = _add_member(self.student, self.org, self.student_role)
        self.tutor_membership = _add_member(self.tutor, self.org, self.tutor_role)

        # Tyutor unit-scoped roldur: tələbə ilə eyni unitə bağlanır.
        self.unit = OrgUnit.objects.create(
            organization=self.org,
            unit_type=OrgUnitType.FACULTY,
            name="Test Faculty",
            slug="test-faculty",
            is_active=True,
        )
        self.tutor_membership.scope_unit = self.unit
        self.tutor_membership.save(update_fields=["scope_unit"])
        self.student_membership.scope_unit = self.unit
        self.student_membership.save(update_fields=["scope_unit"])

        other_student_role = _make_role(self.other_org, ProfileRole.STUDENT, 10)
        self.other_student = User.objects.create_user("student2", "student2@example.com", PASSWORD)
        _add_member(self.other_student, self.other_org, other_student_role)

        self.superadmin = User.objects.create_superuser("root", "root@example.com", PASSWORD)

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _start(self, target, org=None):
        data = {"user_id": target.pk}
        if org is not None:
            data["org"] = org.pk
        return self.client.post(reverse("accounts:view_as_start"), data)


class ViewAsPermissionTests(ViewAsTestBase):
    def test_org_admin_gets_full_mode(self):
        mode, level, _m = resolve_actor_access(self.admin, self.org)
        self.assertEqual(mode, MODE_FULL)
        self.assertGreaterEqual(level, 80)

    def test_tutor_gets_readonly_mode(self):
        mode, _level, _m = resolve_actor_access(self.tutor, self.org)
        self.assertEqual(mode, MODE_READONLY)

    def test_student_has_no_access(self):
        mode, _level, _m = resolve_actor_access(self.student, self.org)
        self.assertIsNone(mode)

    def test_cross_org_target_rejected(self):
        """Tenant izolyasiyası: başqa org-un istifadəçisi hədəf ola bilməz."""
        target, mode = validate_target(self.admin, self.org, self.other_student.pk)
        self.assertIsNone(target)
        self.assertIsNone(mode)

    def test_superuser_cannot_be_target(self):
        _add_member(self.superadmin, self.org, self.student_role)
        target, _mode = validate_target(self.admin, self.org, self.superadmin.pk)
        self.assertIsNone(target)

    def test_hierarchy_lower_cannot_view_higher(self):
        """Tyutor (40) müəllimi (60) görə bilməz."""
        target, _mode = validate_target(self.tutor, self.org, self.teacher.pk)
        self.assertIsNone(target)

    def test_tutor_can_view_student_in_own_unit(self):
        target, mode = validate_target(self.tutor, self.org, self.student.pk)
        self.assertIsNotNone(target)
        self.assertEqual(mode, MODE_READONLY)

    def test_tutor_cannot_view_student_outside_unit(self):
        """Unit scoping: tələbə tyutorun alt-ağacından çıxarılırsa görünmür."""
        self.student_membership.scope_unit = None
        self.student_membership.save(update_fields=["scope_unit"])
        target, _mode = validate_target(self.tutor, self.org, self.student.pk)
        self.assertIsNone(target)


class ViewAsFlowTests(ViewAsTestBase):
    def test_admin_starts_and_profile_shows_target(self):
        self._login(self.admin)
        response = self._start(self.teacher)
        self.assertEqual(response.status_code, 302)
        self.assertIn(VIEW_AS_SESSION_KEY, self.client.session)

        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        # request.user hədəflə əvəzlənir → kontekstdəki user müəllimdir.
        self.assertEqual(response.context["user"].pk, self.teacher.pk)
        view_as = response.context["view_as"]
        self.assertTrue(view_as["active"])
        self.assertEqual(view_as["mode"], MODE_FULL)
        self.assertEqual(view_as["real_user"].pk, self.admin.pk)
        self.assertContains(response, "data-toast-item")
        self.assertNotContains(response, "data-profile-flash-message")

    def test_readonly_blocks_unsafe_methods(self):
        self._login(self.tutor)
        self._start(self.student)
        self.assertIn(VIEW_AS_SESSION_KEY, self.client.session)

        response = self.client.post(
            reverse("accounts:profile"),
            {"profile_form": "edit-profile", "first_name": "Hack"},
        )
        # Bloklanır və redirect (HTML) qaytarılır.
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertNotEqual(self.student.first_name, "Hack")

        json_response = self.client.post(
            reverse("accounts:profile"),
            {"profile_form": "edit-profile"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(json_response.status_code, 403)

    def test_full_mode_blocks_sensitive_forms(self):
        self._login(self.admin)
        self._start(self.teacher)

        response = self.client.post(
            reverse("accounts:profile"),
            {"profile_form": "change-password", "new_password1": "x", "new_password2": "x"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse("accounts:delete_account"),
            {},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_start(self):
        self._login(self.student)
        self._start(self.teacher)
        self.assertNotIn(VIEW_AS_SESSION_KEY, self.client.session)

    def test_cross_org_start_rejected(self):
        self._login(self.admin)
        self._start(self.other_student)
        self.assertNotIn(VIEW_AS_SESSION_KEY, self.client.session)

    def test_stop_returns_to_self(self):
        self._login(self.admin)
        self._start(self.teacher)
        response = self.client.post(reverse("accounts:view_as_stop"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(VIEW_AS_SESSION_KEY, self.client.session)

        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.context["user"].pk, self.admin.pk)

    def test_nested_view_as_rejected(self):
        self._login(self.admin)
        self._start(self.teacher)
        state_before = dict(self.client.session[VIEW_AS_SESSION_KEY])
        # Aktiv sessiya içində yenidən start → middleware unsafe POST-u
        # icazəli sayır (full), amma view nested keçidi rədd edir.
        self._start(self.student)
        self.assertEqual(self.client.session[VIEW_AS_SESSION_KEY]["target_id"], state_before["target_id"])

    def test_search_api_excludes_cross_org_and_superuser(self):
        self._login(self.admin)
        response = self.client.get(reverse("accounts:view_as_search"), {"type": "users"})
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.json()["results"]}
        self.assertIn(self.teacher.pk, ids)
        self.assertIn(self.student.pk, ids)
        self.assertNotIn(self.other_student.pk, ids)
        self.assertNotIn(self.superadmin.pk, ids)
        self.assertNotIn(self.admin.pk, ids)

    def test_search_api_forbidden_for_student(self):
        self._login(self.student)
        response = self.client.get(reverse("accounts:view_as_search"), {"type": "users"})
        self.assertEqual(response.status_code, 403)

    def test_org_search_superadmin_only(self):
        self._login(self.admin)
        response = self.client.get(reverse("accounts:view_as_search"), {"type": "orgs"})
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.superadmin)
        response = self.client.get(reverse("accounts:view_as_search"), {"type": "orgs"})
        self.assertEqual(response.status_code, 200)
        names = {row["name"] for row in response.json()["results"]}
        self.assertIn("Test Univ", names)

    def test_superadmin_cross_org_start(self):
        self.client.force_login(self.superadmin)
        response = self._start(self.other_student, org=self.other_org)
        self.assertEqual(response.status_code, 302)
        self.assertIn(VIEW_AS_SESSION_KEY, self.client.session)

        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.context["user"].pk, self.other_student.pk)
        # Org konteksti hədəfin org-una keçir.
        self.assertEqual(self.client.session["active_organization"], self.other_org.slug)


class ViewAsAccountTakeoverTests(ViewAsTestBase):
    """P0 reqressiya: view-as altında hədəfin KİMLİK SÜBUTU axını bloklanmalıdır.

    Tapıntı: ``ViewAsMiddleware`` ``FirstLoginPasswordMiddleware``-dən ƏVVƏL
    işlədiyi üçün ``password_change_required=True`` olan hədəfdə hər sorğu
    parol-təyini səhifəsinə yönləndirilirdi; blok siyahısında yalnız 3
    ``profile_form`` dəyəri vardı, ona görə aktor hədəfin parolunu təyin edib
    hesabı tam ələ keçirə bilərdi.
    """

    def _make_pending_first_login_target(self):
        target = User.objects.create_user("pending_user", "pending@example.com", PASSWORD)
        _add_member(target, self.org, self.teacher_role)
        profile = target.profile
        profile.password_change_required = True
        profile.save(update_fields=["password_change_required"])
        return target

    def test_first_login_target_is_not_selectable(self):
        """İlk-girişini tamamlamamış hesab hədəf siyahısında görünməməlidir."""
        target = self._make_pending_first_login_target()
        self._login(self.admin)

        response = self.client.get(reverse("accounts:view_as_search"), {"type": "users"})
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.json()["results"]}
        self.assertNotIn(target.pk, ids)

    def test_start_view_as_on_first_login_target_is_rejected(self):
        target = self._make_pending_first_login_target()
        self._login(self.admin)

        self._start(target)
        self.assertNotIn(VIEW_AS_SESSION_KEY, self.client.session)

    def test_set_initial_password_post_is_blocked_in_full_mode(self):
        """FULL rejimdə belə parol-təyini POST-u bloklanır (hesab ələ keçirmə)."""
        self._login(self.admin)
        self._start(self.teacher)
        self.assertIn(VIEW_AS_SESSION_KEY, self.client.session)

        response = self.client.post(
            reverse("accounts:set_initial_password"),
            {"new_password1": "AttackerPass123!", "new_password2": "AttackerPass123!"},
        )
        self.assertEqual(response.status_code, 302)

        # Hədəfin parolu DƏYİŞMƏMƏLİDİR.
        self.teacher.refresh_from_db()
        self.assertFalse(self.teacher.check_password("AttackerPass123!"))
        self.assertTrue(self.teacher.check_password(PASSWORD))

    def test_otp_endpoints_are_blocked_in_full_mode(self):
        """E-poçt OTP axını da kimlik sübutudur — hər iki rejimdə bloklanır."""
        self._login(self.admin)
        self._start(self.teacher)

        for url_name in ("accounts:send_otp_api", "accounts:verify_otp_api", "accounts:resend_otp_api"):
            with self.subTest(url_name=url_name):
                response = self.client.post(reverse(url_name), {}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
                self.assertEqual(response.status_code, 403)
                self.assertTrue(response.json().get("view_as_blocked"))


class ViewAsLimitedModeTests(ViewAsTestBase):
    """İmtahan Mərkəzi / İKT üçün MƏHDUD dəyişiklik rejimi (2026-07-31 auditi).

    İstifadəçi qaydası: başqa rolun səhifəsinə dəyişiklik səlahiyyəti ilə YALNIZ
    İmtahan Mərkəzi və İKT Mərkəzi girə bilər; İmtahan Mərkəzinin dəyişikliyi
    imtahan əməliyyatları ilə, İKT-ninki isə açıq şəkildə icazə verilmiş sistem
    əməliyyatları ilə məhdudlaşır.
    """

    def setUp(self):
        super().setUp()
        # Səviyyələr real konfiqurasiyadakı kimidir: hər ikisi org_admin-dən (80)
        # YUXARIDIR — məhz buna görə köhnə səviyyə-əsaslı şərt onlara tam
        # səlahiyyət verirdi.
        self.exam_center_role = _make_role(self.org, ProfileRole.EXAM_CENTER, 85)
        self.ikt_role = _make_role(self.org, ProfileRole.IKT_REHBER, 88)
        self.exam_center = User.objects.create_user("exam_center1", "ec@example.com", PASSWORD)
        self.ikt = User.objects.create_user("ikt1", "ikt@example.com", PASSWORD)
        _add_member(self.exam_center, self.org, self.exam_center_role)
        _add_member(self.ikt, self.org, self.ikt_role)

    def test_exam_center_gets_limited_not_full(self):
        mode, _level, _m = resolve_actor_access(self.exam_center, self.org)
        self.assertEqual(mode, MODE_LIMITED)

    def test_ikt_gets_limited_not_full(self):
        mode, _level, _m = resolve_actor_access(self.ikt, self.org)
        self.assertEqual(mode, MODE_LIMITED)

    def test_high_level_role_without_mapping_gets_no_access(self):
        """Səviyyə tək başına səlahiyyət vermir — xəritədə olmayan rol girə bilməz."""
        stranger_role = _make_role(self.org, "vice_rector_unmapped", 95)
        stranger = User.objects.create_user("stranger1", "stranger@example.com", PASSWORD)
        _add_member(stranger, self.org, stranger_role)

        mode, _level, _m = resolve_actor_access(stranger, self.org)

        self.assertIsNone(mode)

    def test_limited_actor_cannot_target_org_admin(self):
        """Məxfi HR/idarəçi məlumatı: admin hesabı hədəf ola bilməz."""
        target, mode = validate_target(self.ikt, self.org, self.admin.pk)

        self.assertIsNone(target)
        self.assertIsNone(mode)

    def test_limited_actor_cannot_target_admin_equivalent_roles(self):
        """Blok siyahısının ada görə olması real boşluq idi (2026-07-31 audit).

        `ProfileRole` `org_admin` aliasını `ADMIN_EQUIVALENT_ROLE_NAMES` üzvlüyünə
        VƏ ya `level >= 80` şərtinə görə verir. Əl ilə yazılmış beş adlıq siyahı
        isə `department_head` (80), `senior_instructor` (80) və `vice_dean` (85)
        rollarını buraxırdı — yəni imtahan mərkəzi (85) kafedra müdirinə keçib
        org-üzvləri, rollar və icazə redaktoru bölmələrini aça bilirdi.

        Test hər admin-ekvivalent rolu ayrıca yoxlayır ki, siyahı yenidən
        daralsa dərhal düşsün.
        """
        for role_name, level in (("department_head", 80), ("senior_instructor", 80), ("vice_dean", 85)):
            with self.subTest(role=role_name):
                role = _make_role(self.org, role_name, level)
                victim = User.objects.create_user(f"victim_{role_name}", f"{role_name}@example.com", PASSWORD)
                _add_member(victim, self.org, role)

                target, mode = validate_target(self.ikt, self.org, victim.pk)

                self.assertIsNone(target, f"{role_name} hədəf ola bilməməlidir")
                self.assertIsNone(mode)

    def test_limited_actor_cannot_target_a_custom_role_at_admin_level(self):
        """Tenant öz adı ilə rol yarada bilər — alias səviyyəyə görə verilir."""
        role = _make_role(self.org, "kadrlar_uzre_prorektor", 90)
        victim = User.objects.create_user("victim_custom", "custom@example.com", PASSWORD)
        _add_member(victim, self.org, role)

        target, mode = validate_target(self.ikt, self.org, victim.pk)

        self.assertIsNone(target)
        self.assertIsNone(mode)

    def test_forbidden_target_set_is_derived_not_hand_written(self):
        """Siyahı mənbədən törəməlidir ki, mənbə dəyişəndə sürüşməsin."""
        from apps.accounts.services.view_as import LIMITED_FORBIDDEN_TARGET_ROLES

        missing = ProfileRole.ADMIN_EQUIVALENT_ROLE_NAMES - set(LIMITED_FORBIDDEN_TARGET_ROLES)
        self.assertFalse(missing, f"admin-ekvivalent rollar blok siyahısında yoxdur: {sorted(missing)}")

    def test_limited_actor_can_still_target_exam_center_staff(self):
        """Muaf rollar istisnadan KƏNARDADIR — İKT müşahidə imkanını itirməməlidir.

        `exam_center` səviyyəsi 85-dir, yəni sırf səviyyə filtri onu da kəsərdi;
        amma o, alias-muafdır və org_admin səthini ALMIR.
        """
        staff_role = _make_role(self.org, "exam_center_staff", 70)
        staff = User.objects.create_user("ec_staff", "ecstaff@example.com", PASSWORD)
        _add_member(staff, self.org, staff_role)

        target, mode = validate_target(self.ikt, self.org, staff.pk)

        self.assertEqual(target, staff)
        self.assertEqual(mode, MODE_LIMITED)

    def test_limited_actor_can_target_teacher(self):
        target, mode = validate_target(self.exam_center, self.org, self.teacher.pk)

        self.assertEqual(target, self.teacher)
        self.assertEqual(mode, MODE_LIMITED)

    def test_limited_write_is_blocked_outside_the_allowlist(self):
        """Siyahıda olmayan marşruta POST bloklanır (URL ilə birbaşa cəhd)."""
        self._login(self.exam_center)
        self._start(self.teacher)

        response = self.client.post(
            reverse("accounts:profile"),
            {"profile_form": "some-other-form"},
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(VIEW_AS_SESSION_KEY, self.client.session)

    def test_ikt_write_allowlist_is_empty_by_design(self):
        """İKT üçün heç bir sistem əməliyyatı hələ açıq şəkildə icazəli deyil."""
        from apps.accounts.services.view_as import actor_limited_write_url_names

        self.assertEqual(actor_limited_write_url_names(self.ikt, self.org), frozenset())

    def test_exam_center_allowlist_holds_only_exam_routes(self):
        from apps.accounts.services.view_as import actor_limited_write_url_names

        allowed = actor_limited_write_url_names(self.exam_center, self.org)

        self.assertTrue(allowed)
        self.assertTrue(all(name.startswith("exams:") for name in allowed), sorted(allowed)[:5])
        # Auditdə açıq şəkildə istisna edilənlər siyahıya düşməməlidir.
        self.assertNotIn("exams:exam_center_ticket_remove", allowed)
        self.assertNotIn("accounts:exam_chance", allowed)
        self.assertNotIn("registrar:correction_apply", allowed)

    def test_blocked_write_is_recorded_in_audit(self):
        from apps.audit.models import AuditLog

        self._login(self.exam_center)
        self._start(self.teacher)
        before = AuditLog.objects.filter(reason="view_as_action_blocked").count()

        self.client.post(reverse("accounts:profile"), {"profile_form": "some-other-form"})

        self.assertEqual(AuditLog.objects.filter(reason="view_as_action_blocked").count(), before + 1)

        entry = AuditLog.objects.filter(reason="view_as_action_blocked").order_by("-id").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.user, self.exam_center)
        self.assertFalse(entry.changes.get("allowed"))
        self.assertEqual(entry.changes.get("mode"), MODE_LIMITED)


class ViewAsAdminSurfaceTests(ViewAsTestBase):
    """Django admin view-as altında tam bağlıdır.

    Admin-də `password_change`, admin 2FA təsdiqi və bütün modellərin CRUD
    marşrutları var. Middleware yalnız `is_superuser` HƏDƏFLƏRİNİ istisna edir,
    `is_staff`-i yox — yəni staff hədəf seçilsə bütün admin səthi açılırdı.
    """

    def test_admin_is_blocked_under_view_as(self):
        self.teacher.is_staff = True
        self.teacher.save(update_fields=["is_staff"])
        self._login(self.admin)
        self._start(self.teacher)

        response = self.client.get(reverse("admin:index"), follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("/admin/", response.headers.get("Location", ""))

    def test_admin_stays_reachable_without_view_as(self):
        """Qadağa YALNIZ view-as sessiyasına aiddir — normal admin girişi qalır."""
        self.admin.is_staff = True
        self.admin.save(update_fields=["is_staff"])
        self._login(self.admin)

        response = self.client.get(reverse("admin:index"), follow=False)

        self.assertNotEqual(response.status_code, 403)


class ViewAsAuditAttributionTests(ViewAsTestBase):
    """Domen audit qeydləri əsl aktoru daşımalıdır.

    ``ViewAsMiddleware`` ``request.user``-i hədəflə əvəz edir, ona görə domen
    qatındakı `by_user=request.user` çağırışları hədəfin adını yazır. Damğa
    ``core.audit.log_action``-da mərkəzi qoyulur.
    """

    def test_domain_audit_records_carry_the_real_actor(self):
        from apps.audit.models import AuditLog

        self._login(self.admin)
        self._start(self.teacher)

        # QEYD: audit cədvəli APPEND-ONLY-dir (postgres trigger-i DELETE-i
        # bloklayır), ona görə təmizləmək olmaz — unikal `reason` ilə süzürük.
        # sqlite-da trigger yoxdur, yəni bu tələ yalnız CI-də görünürdü.
        from core.audit import log_action
        from core.constants import AuditAction

        request = self.client.get(reverse("accounts:profile")).wsgi_request
        log_action(
            action=AuditAction.UPDATE,
            user=request.user,  # = HƏDƏF (impersonasiya)
            organization=self.org,
            obj=self.teacher,
            reason="domain_write",
            request=request,
        )

        entry = AuditLog.objects.filter(reason="domain_write").order_by("-id").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.user, self.teacher)  # domen qatı hədəfi yazır
        stamp = entry.changes.get("impersonated_by")
        self.assertIsNotNone(stamp, "impersonasiya damğası yoxdur")
        self.assertEqual(stamp["username"], self.admin.username)
        self.assertEqual(stamp["mode"], MODE_FULL)


class ViewAsBannerModeTests(ViewAsTestBase):
    """Banner ÜÇ rejimi də düzgün göstərməlidir.

    `MODE_LIMITED` əlavə olunanda banner şablonu və CSS-i yenilənməmişdi:
    * `view-as-banner--limited` class-ının heç bir qaydası yox idi, baza qayda
      isə `color: var(--ems-neutral-0)` (ağ) verir → ağ üzərində ağ mətn;
    * etiket `{% if readonly %}…{% else %}FULL{% endif %}` idi, yəni məhdud
      səlahiyyətli istifadəçiyə «tam səlahiyyət» yazılırdı — yanlış məlumat.
    """

    def setUp(self):
        super().setUp()
        self.exam_center_role = _make_role(self.org, ProfileRole.EXAM_CENTER, 85)
        self.exam_center = User.objects.create_user("banner_ec", "banner_ec@example.com", PASSWORD)
        _add_member(self.exam_center, self.org, self.exam_center_role)

    def _banner_html(self, actor, target):
        self._login(actor)
        self._start(target)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_limited_mode_uses_its_own_banner_class(self):
        html = self._banner_html(self.exam_center, self.teacher)

        self.assertIn("view-as-banner--limited", html)
        self.assertIn("view-as-pill--limited", html)
        self.assertIn("view-as-frame--limited", html)

    def test_limited_mode_is_not_labelled_as_full_control(self):
        from django.utils.translation import pgettext

        html = self._banner_html(self.exam_center, self.teacher)

        self.assertIn(pgettext("accounts.view_as", "mode_limited"), html)
        self.assertNotIn(pgettext("accounts.view_as", "mode_full"), html)

    def test_full_mode_still_labelled_as_full(self):
        from django.utils.translation import pgettext

        html = self._banner_html(self.admin, self.teacher)

        self.assertIn("view-as-banner--full", html)
        self.assertIn(pgettext("accounts.view_as", "mode_full"), html)

    def test_every_mode_class_has_css_rules(self):
        """Şablon `--{{ mode }}` yazır: hər rejim üçün qayda OLMALIDIR."""
        import pathlib

        from apps.accounts.services.view_as import MODE_FULL, MODE_LIMITED, MODE_READONLY

        css = pathlib.Path("static/css/view_as.css").read_text(encoding="utf-8")
        for mode in (MODE_FULL, MODE_LIMITED, MODE_READONLY):
            for block in ("banner", "pill", "frame"):
                with self.subTest(mode=mode, block=block):
                    self.assertIn(f".view-as-{block}--{mode}", css)

    def test_every_mode_defines_a_coloured_surface(self):
        """Rejimin RƏNG PALİTRASI da olmalıdır, təkcə class adı yox.

        `MODE_LIMITED` əlavə olunanda məhz bu sındı: class adı şablondan
        gəlirdi, amma `--view-as-limited-*` dəyişənləri yox idi. Baza qaydası
        mətni ağ (`--ems-neutral-0`) edir, fon isə rejim qaydasından gəlir —
        fon olmayanda istifadəçi AĞ FONDA AĞ MƏTN görürdü: «Öz profilimə qayıt»
        düyməsi və «TAM SƏLAHİYYƏT» nişanı tamamilə oxunmaz idi.

        Class adını yoxlamaq bunu tutmurdu, çünki `.view-as-banner--limited`
        yalnız bir alt-element qaydasında iştirak etsə belə mətndə görünür.
        """
        import pathlib

        from apps.accounts.services.view_as import MODE_FULL, MODE_LIMITED, MODE_READONLY

        css = pathlib.Path("static/css/view_as.css").read_text(encoding="utf-8")
        for mode in (MODE_FULL, MODE_LIMITED, MODE_READONLY):
            for suffix in ("", "-bg", "-border"):
                variable = f"--view-as-{mode}{suffix}"
                with self.subTest(mode=mode, variable=variable):
                    self.assertIn(f"{variable}:", css, f"{variable} təyin olunmayıb")

            # Çıxış düyməsi və nişan üçün fon MÜTLƏQ verilməlidir.
            for element in ("__exit", "__chip"):
                with self.subTest(mode=mode, element=element):
                    rule = f".view-as-banner--{mode} .view-as-banner{element}"
                    self.assertIn(rule, css, f"{rule} üçün qayda yoxdur")
                    tail = css.split(rule, 1)[1].split("}", 1)[0]
                    self.assertIn("background", tail, f"{rule} fon təyin etmir — ağ fonda ağ mətn riski")


class MutatingGetRouteScanTests(TestCase):
    """`MUTATING_GET_URL_NAMES` siyahısı köhnəlməməlidir.

    View-as qapısı HTTP metoduna bağlıdır: `GET` təhlükəsiz sayılır. Amma bəzi
    marşrutlar GET ilə də server vəziyyətini dəyişir — məsələn
    `live_create_session_by_slug` əvvəlcə işləyən sessiyaları bitirir. Belə
    marşrut siyahıda olmasa, READONLY aktor sadəcə linkə keçməklə canlı imtahanı
    dayandıra bilər və audit-də iz qalmaz.

    Bu test marşrut cədvəlini skan edir: metod qapısı olmayan və mutasiya edən
    hər funksiya-view ya siyahıda, ya da təsdiqlənmiş istisnalarda olmalıdır.
    Yeni belə view əlavə olunanda test düşür və adam qərar verməli olur.
    """

    #: Skanın tutduğu, lakin view-as üçün TƏHLÜKƏSİZ sayılan marşrutlar.
    #: Hər biri yalnız yan-təsir yazır (sayğac, ixrac qeydi, QR keşi) və
    #: istifadəçinin görə biləcəyi vəziyyəti dəyişmir.
    REVIEWED_SAFE = {
        "accounts:profile_badges_api",
        "accounts:public_profile",
        "accounts:statistics_export_csv",
        "exams:exam_center_stats_export",
        "liveExam:qr_png",
    }

    def test_no_unreviewed_mutating_get_route_exists(self):
        import inspect
        import re

        from django.urls import URLPattern, URLResolver, get_resolver

        from apps.accounts.services.view_as import MUTATING_GET_URL_NAMES

        mutation = re.compile(r"\.(save|delete|create|bulk_create|get_or_create|update_or_create)\(")
        guard = re.compile(r"request\.method|require_POST|require_http_methods|http_method_names")

        def walk(patterns, namespace=""):
            for entry in patterns:
                if isinstance(entry, URLResolver):
                    yield from walk(entry.url_patterns, entry.namespace or namespace)
                elif isinstance(entry, URLPattern) and entry.name:
                    yield (f"{namespace}:{entry.name}" if namespace else entry.name), entry.callback

        unreviewed = []
        for name, callback in walk(get_resolver().url_patterns):
            if name.startswith(("admin:", "django")):
                continue
            view = getattr(callback, "view_class", callback)
            if inspect.isclass(view):
                continue  # CBV — GET və POST ayrı metodlardır
            try:
                source = inspect.getsource(view)
            except (OSError, TypeError):
                continue
            if not mutation.search(source) or guard.search(source):
                continue
            if name in MUTATING_GET_URL_NAMES or name in self.REVIEWED_SAFE:
                continue
            unreviewed.append(name)

        self.assertFalse(
            unreviewed,
            "Bu marşrutlar GET ilə mutasiya edir və view-as qapısında nəzərə "
            "alınmayıb. Vəziyyəti dəyişirsə MUTATING_GET_URL_NAMES-ə, yalnız "
            "yan-təsir yazırsa REVIEWED_SAFE-ə əlavə edin:\n  " + "\n  ".join(sorted(unreviewed)),
        )
