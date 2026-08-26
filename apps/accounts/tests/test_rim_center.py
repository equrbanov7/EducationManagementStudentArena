"""RİM (Rəqəmsal İnkişaf Mərkəzi) — hesab idarəetmə modulunun testləri.

Fokus TƏHLÜKƏSİZLİKDİR: icazə qapıları, rol iyerarxiyası, tenant izolyasiyası,
soft-delete-in tarixi datanı qorumasi və audit izi. Bu testlər siyasət
sənədidir — `services/rim/policy.py` dəyişəndə əvvəlcə buraya baxın.
"""

from django.contrib.auth import authenticate, get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType
from core.roles import ProfileRole

User = get_user_model()

PASSWORD = "StrongPass123!"

# RİM operatorunun tam icazə dəsti (əməliyyat açarları; `grant_privileged` yox).
RIM_OPERATIONAL = [
    "user.search",
    "user.credentials",
    "user.block",
    "user.soft_delete",
    "user.edit",
]


def make_role(organization, name, level, permissions=None):
    role, _ = Role.objects.update_or_create(
        organization=organization,
        name=name,
        defaults={
            "display_name": name.replace("_", " ").title(),
            "level": level,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": list(permissions or []),
            "is_system": False,
            "is_active": True,
        },
    )
    return role


def add_member(user, organization, role, *, is_primary=True):
    return Membership.objects.create(
        user=user,
        organization=organization,
        role=role,
        is_active=True,
        is_primary=is_primary,
    )


def make_user(username, *, first="", last="", patronymic="", email="", fin=None, organization=None):
    user = User.objects.create_user(username, email or f"{username}@example.com", PASSWORD)
    user.first_name = first
    user.last_name = last
    user.save(update_fields=["first_name", "last_name"])
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.patronymic = patronymic
    # FİN NULL-unique-dir: boş dəyər `None` olmalıdır (iki boş sətir unikallığı pozardı).
    profile.fin = fin or None
    profile.organization = organization
    profile.save()
    return user


@override_settings(RATELIMIT_ENABLE=False)
class RimCenterTestBase(TestCase):
    """Bir təşkilat, bir RİM operatoru və bir neçə müxtəlif səviyyəli hədəf."""

    def setUp(self):
        self.client = Client()

        self.owner = User.objects.create_user("rim_owner", "owner@example.com", PASSWORD)
        self.org = Organization.objects.create(
            name="RİM Test Univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )

        # Rollar — səviyyələr real iyerarxiyanı əks etdirir.
        self.rim_role = make_role(self.org, "ikt_rehber", 88, RIM_OPERATIONAL)
        self.admin_role = make_role(self.org, ProfileRole.ORG_ADMIN, 80)
        self.teacher_role = make_role(self.org, ProfileRole.TEACHER, 50)
        self.staff_role = make_role(self.org, "department_head", 70)
        self.student_role = make_role(self.org, ProfileRole.STUDENT, 10)

        # RİM operatoru (level 88).
        self.operator = make_user("rim_operator", first="Rəşad", last="Məmmədov", organization=self.org)
        add_member(self.operator, self.org, self.rim_role)

        # Hədəflər.
        self.teacher = make_user(
            "myedu.worker.772",
            first="Elvin",
            last="Əliyev",
            patronymic="Səməd",
            email="elvin.aliyev@example.com",
            fin="7AB12CD",
            organization=self.org,
        )
        add_member(self.teacher, self.org, self.teacher_role)

        # Eyni ad+soyad, FƏRQLİ ata adı — ata adı ilə ayırd etmə testi üçün.
        self.namesake = make_user(
            "myedu.worker.913",
            first="Elvin",
            last="Əliyev",
            patronymic="Rəşad",
            email="elvin.aliyev2@example.com",
            organization=self.org,
        )
        add_member(self.namesake, self.org, self.teacher_role)

        # Aktordan YUXARI səviyyəli hədəf (90) — idarə oluna BİLMƏZ.
        self.higher = make_user("vice_rector_user", first="Vüqar", last="Həsənov", organization=self.org)
        add_member(self.higher, self.org, make_role(self.org, "vice_rector", 90))

        self.superuser = User.objects.create_superuser("root_admin", "root@example.com", PASSWORD)

    def login_operator(self):
        self.client.force_login(self.operator)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def search(self, query, **params):
        params.setdefault("q", query)
        return self.client.get(reverse("accounts:rim_user_search"), params)

    def act(self, action, target, **payload):
        payload.update({"action": action, "user_id": target.pk})
        return self.client.post(
            reverse("accounts:rim_action"),
            data=payload,
            content_type="application/json",
        )


class RimSearchTests(RimCenterTestBase):
    def test_search_by_name_surname_and_patronymic(self):
        """Əsas ssenari: username BİLİNMİR, ad+soyad+ata adı ilə tapılır."""
        self.login_operator()
        response = self.search("Əliyev Elvin Səməd")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        usernames = [row["username"] for row in payload["results"]]
        # Ata adı namesake-i kənarlaşdırır.
        self.assertEqual(usernames, ["myedu.worker.772"])

    def test_patronymic_disambiguates_namesakes(self):
        self.login_operator()
        without_patronymic = self.search("Əliyev Elvin").json()
        self.assertEqual(without_patronymic["total"], 2)

        with_patronymic = self.search("Əliyev Elvin Rəşad").json()
        self.assertEqual(with_patronymic["total"], 1)
        self.assertEqual(with_patronymic["results"][0]["username"], "myedu.worker.913")

    def test_word_order_does_not_matter(self):
        """AND-of-ORs: «Elvin Əliyev» də, «Əliyev Elvin» də eyni nəticəni verir."""
        self.login_operator()
        self.assertEqual(self.search("Elvin Əliyev Səməd").json()["total"], 1)

    def test_search_by_fin_and_email_and_username(self):
        self.login_operator()
        self.assertEqual(self.search("7AB12CD").json()["total"], 1)
        self.assertEqual(self.search("elvin.aliyev@example.com").json()["total"], 1)
        self.assertEqual(self.search("myedu.worker.772").json()["total"], 1)

    def test_results_expose_username_openly(self):
        """Operator username-i bilmir — nəticə onu AÇIQ göstərməlidir."""
        self.login_operator()
        row = self.search("Əliyev Elvin Səməd").json()["results"][0]
        self.assertEqual(row["username"], "myedu.worker.772")
        self.assertEqual(row["patronymic"], "Səməd")

    def test_higher_ranked_user_is_not_searchable(self):
        """İyerarxiya queryset səviyyəsində: yuxarı səviyyəli hesab siyahıda yoxdur."""
        self.login_operator()
        self.assertEqual(self.search("Həsənov").json()["total"], 0)

    def test_superuser_is_never_a_target(self):
        self.login_operator()
        self.assertEqual(self.search("root_admin").json()["total"], 0)

    def test_actor_cannot_find_self(self):
        self.login_operator()
        self.assertEqual(self.search("rim_operator").json()["total"], 0)


class RimPermissionGateTests(RimCenterTestBase):
    def test_user_without_permission_gets_403_on_search(self):
        """Fail-closed: `user.search` olmayan müəllim axtarış edə bilmir."""
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = self.search("Əliyev")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "permission_denied")

    def test_search_only_permission_cannot_set_password(self):
        """Bölmə açıqdır, amma dağıdıcı əməliyyat AYRICA icazə tələb edir."""
        limited_role = make_role(self.org, "rim_viewer", 75, ["user.search"])
        viewer = make_user("rim_viewer_user", organization=self.org)
        add_member(viewer, self.org, limited_role)

        self.client.force_login(viewer)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

        self.assertEqual(self.search("Əliyev").json()["total"], 2)

        response = self.act("set_password", self.teacher, reason="test")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "permission_denied")

    def test_anonymous_is_redirected(self):
        response = self.search("Əliyev")
        self.assertIn(response.status_code, (302, 403))

    def test_no_org_context_means_no_access(self):
        """Aktiv təşkilat konteksti olmadan RİM bağlıdır (fail-closed).

        QEYD: `_get_active_organization` sessiyada org yoxdursa PROFİL
        təşkilatına geri düşür — ona görə burada hər ikisi boş olan hesab
        işlədilir (əks halda operator sessiyasız da öz org-unu alır).
        """
        orphan = User.objects.create_user("orphan_operator", "orphan@example.com", PASSWORD)
        UserProfile.objects.get_or_create(user=orphan)
        self.client.force_login(orphan)
        response = self.search("Əliyev")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "permission_denied")


class RimHierarchyTests(RimCenterTestBase):
    def test_cannot_manage_equal_level_account(self):
        """Eyni səviyyəli iki RİM operatoru bir-birini idarə edə bilməz."""
        peer = make_user("rim_peer", organization=self.org)
        add_member(peer, self.org, self.rim_role)

        self.login_operator()
        response = self.act("block", peer, reason="yoxlama")
        self.assertEqual(response.status_code, 404)

    def test_cannot_manage_higher_level_account(self):
        self.login_operator()
        response = self.act("block", self.higher, reason="yoxlama")
        self.assertEqual(response.status_code, 404)
        self.higher.refresh_from_db()
        self.assertTrue(self.higher.is_active)

    def test_cannot_target_self(self):
        self.login_operator()
        response = self.act("soft_delete", self.operator, reason="özümü silim")
        self.assertEqual(response.status_code, 404)
        self.operator.refresh_from_db()
        self.assertTrue(self.operator.is_active)
        self.assertFalse(self.operator.profile.is_deleted)

    def test_cannot_target_superuser(self):
        self.login_operator()
        response = self.act("block", self.superuser, reason="yoxlama")
        self.assertEqual(response.status_code, 404)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    def test_cannot_target_organization_owner(self):
        self.login_operator()
        response = self.act("block", self.owner, reason="yoxlama")
        self.assertEqual(response.status_code, 404)

    def test_tenant_isolation_blocks_cross_org_target(self):
        other_owner = User.objects.create_user("other_owner2", "oo2@example.com", PASSWORD)
        other_org = Organization.objects.create(
            name="Başqa Univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=other_owner,
            status="active",
            is_active=True,
        )
        outsider = make_user("outsider_teacher", first="Kənar", last="İstifadəçi", organization=other_org)
        add_member(outsider, other_org, make_role(other_org, ProfileRole.TEACHER, 50))

        self.login_operator()
        self.assertEqual(self.search("Kənar").json()["total"], 0)
        response = self.act("set_password", outsider, reason="yoxlama")
        self.assertEqual(response.status_code, 404)


class RimCredentialTests(RimCenterTestBase):
    def test_set_password_returns_password_once_and_forces_change(self):
        self.login_operator()
        response = self.act("set_password", self.teacher, reason="müəllim girə bilmir")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        raw_password = payload["password"]
        self.assertTrue(raw_password)
        self.assertGreaterEqual(len(raw_password), 10)

        # Parol həqiqətən işləyir.
        self.teacher.refresh_from_db()
        self.assertTrue(self.teacher.check_password(raw_password))

        # İstifadəçi ÖZ parolunu qurmağa məcburdur.
        self.teacher.profile.refresh_from_db()
        self.assertTrue(self.teacher.profile.password_change_required)

    def test_password_value_is_never_written_to_audit(self):
        self.login_operator()
        raw_password = self.act("set_password", self.teacher, reason="bərpa").json()["password"]

        entries = AuditLog.objects.filter(resource_id=str(self.teacher.pk))
        self.assertTrue(entries.exists())
        serialized = " ".join(
            str(value)
            for entry in entries
            for value in (entry.reason, entry.changes, entry.old_values, entry.new_values)
        )
        self.assertNotIn(raw_password, serialized)
        self.assertIn("set_temporary_password", serialized)

    def test_audit_records_actor_target_and_reason(self):
        self.login_operator()
        self.act("set_password", self.teacher, reason="cutover bərpası")

        entry = AuditLog.objects.filter(resource_id=str(self.teacher.pk)).order_by("-created_at").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.user_id, self.operator.pk)
        self.assertIn("cutover bərpası", entry.reason)
        self.assertEqual(entry.changes["target_username"], self.teacher.username)

    def test_cannot_set_password_for_deleted_account(self):
        self.login_operator()
        self.act("soft_delete", self.teacher, reason="işdən çıxıb")
        response = self.act("set_password", self.teacher, reason="yenidən")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "target_is_deleted")

    @override_settings(RATELIMIT_ENABLE=True, RIM_PASSWORD_RESET_RATE_LIMIT="2/h")
    def test_password_endpoint_is_rate_limited(self):
        from django.core.cache import cache

        cache.clear()
        self.login_operator()
        self.assertEqual(self.act("set_password", self.teacher, reason="1").status_code, 200)
        self.assertEqual(self.act("set_password", self.namesake, reason="2").status_code, 200)
        throttled = self.act("set_password", self.teacher, reason="3")
        self.assertEqual(throttled.status_code, 429)
        self.assertEqual(throttled.json()["error"], "rate_limited")
        cache.clear()


class RimBlockTests(RimCenterTestBase):
    def test_block_requires_reason(self):
        self.login_operator()
        response = self.act("block", self.teacher, reason="")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "reason_required")
        self.teacher.refresh_from_db()
        self.assertTrue(self.teacher.is_active)

    def test_block_then_unblock_records_reason_and_actor(self):
        self.login_operator()
        self.act("block", self.teacher, reason="şübhəli giriş")

        self.teacher.refresh_from_db()
        self.teacher.profile.refresh_from_db()
        self.assertFalse(self.teacher.is_active)
        self.assertEqual(self.teacher.profile.block_reason, "şübhəli giriş")
        self.assertEqual(self.teacher.profile.blocked_by_id, self.operator.pk)
        self.assertIsNotNone(self.teacher.profile.blocked_at)

        self.act("unblock", self.teacher, reason="aydınlaşdı")
        self.teacher.refresh_from_db()
        self.teacher.profile.refresh_from_db()
        self.assertTrue(self.teacher.is_active)
        self.assertEqual(self.teacher.profile.block_reason, "")
        self.assertIsNone(self.teacher.profile.blocked_by_id)

    def test_blocked_account_cannot_authenticate(self):
        self.login_operator()
        self.act("block", self.teacher, reason="müvəqqəti dayandırma")
        self.assertIsNone(authenticate(username="myedu.worker.772", password=PASSWORD))


class RimSoftDeleteTests(RimCenterTestBase):
    def _make_history(self):
        """Hədəfin arxasında qalmalı olan tarixi qeydlər."""
        from apps.exams.models import StudentGroup

        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="875i")
        group.students.add(self.namesake)
        return group

    def test_soft_delete_blocks_login_but_keeps_history(self):
        group = self._make_history()
        self.login_operator()

        response = self.act("soft_delete", self.teacher, reason="universitetdən ayrılıb")
        self.assertEqual(response.status_code, 200)

        # Giriş bağlıdır.
        self.assertIsNone(authenticate(username="myedu.worker.772", password=PASSWORD))

        # HEÇ NƏ HARD DELETE OLUNMUR.
        self.assertTrue(User.objects.filter(pk=self.teacher.pk).exists())
        self.assertTrue(UserProfile.objects.filter(user_id=self.teacher.pk).exists())
        # Üzvlük SƏTİRLƏRİ qalır (yalnız deaktiv olur) — tarixçə itmir.
        self.assertTrue(Membership.objects.filter(user=self.teacher, organization=self.org).exists())
        self.assertFalse(Membership.objects.filter(user=self.teacher, organization=self.org, is_active=True).exists())
        # Akademik/tədris qeydi (müəllimin qrupu) olduğu kimi qalır.
        group.refresh_from_db()
        self.assertEqual(group.teacher_id, self.teacher.pk)

    def test_soft_delete_records_actor_and_reason(self):
        self.login_operator()
        self.act("soft_delete", self.teacher, reason="işdən çıxma")

        profile = UserProfile.objects.get(user_id=self.teacher.pk)
        self.assertTrue(profile.is_deleted)
        self.assertIsNotNone(profile.deleted_at)
        self.assertEqual(profile.deleted_by_id, self.operator.pk)
        self.assertEqual(profile.deletion_reason, "işdən çıxma")

    def test_soft_delete_is_audited_with_actor_not_target(self):
        self.login_operator()
        self.act("soft_delete", self.teacher, reason="işdən çıxma")

        entry = AuditLog.objects.filter(resource_id=str(self.teacher.pk), action="delete").first()
        self.assertIsNotNone(entry)
        # Audit əməliyyatı APARANA yazılır (hədəfə yox).
        self.assertEqual(entry.user_id, self.operator.pk)
        self.assertIn("işdən çıxma", entry.reason)

    def test_deleted_account_can_be_restored_by_same_operator(self):
        """Reqressiya: soft-delete üzvlükləri deaktiv edir — hədəf operatorun
        görünüş sahəsindən DÜŞMƏMƏLİDİR, əks halda bərpa mümkün olmazdı."""
        self.login_operator()
        self.act("soft_delete", self.teacher, reason="səhv qeyd")

        found = self.search("Əliyev Elvin Səməd", status="deleted").json()
        self.assertEqual(found["total"], 1)

        response = self.act("restore", self.teacher, reason="səhv düzəldildi")
        self.assertEqual(response.status_code, 200)

        self.teacher.refresh_from_db()
        self.teacher.profile.refresh_from_db()
        self.assertTrue(self.teacher.is_active)
        self.assertFalse(self.teacher.profile.is_deleted)
        self.assertIsNone(self.teacher.profile.deleted_by_id)

    def test_deleted_high_rank_account_keeps_its_rank(self):
        """Silinmə iyerarxiyanı sıfırlamamalıdır: silinmiş prorektoru aşağı
        səviyyəli operator bərpa edə bilməz."""
        from apps.accounts.services.rim.policy import target_level

        Membership.objects.filter(user=self.higher, organization=self.org).update(is_active=False)
        profile = self.higher.profile
        profile.is_deleted = True
        profile.save(update_fields=["is_deleted"])

        self.higher.refresh_from_db()
        self.assertEqual(target_level(self.higher, self.org), 90)

        self.login_operator()
        response = self.act("restore", self.higher, reason="bərpa")
        self.assertEqual(response.status_code, 404)

    def test_no_hard_delete_action_is_exposed(self):
        """RİM səthində hard delete YOXDUR."""
        from apps.accounts.views.rim.actions import ALLOWED_ACTIONS

        self.assertNotIn("hard_delete", ALLOWED_ACTIONS)
        self.assertNotIn("permanent_delete", ALLOWED_ACTIONS)


class RimProfileEditTests(RimCenterTestBase):
    def test_edit_updates_fields_and_audits_old_and_new(self):
        self.login_operator()
        response = self.act(
            "edit",
            self.teacher,
            first_name="Elvin",
            last_name="Əliyev",
            patronymic="Səməd oğlu",
            phone="+994501234567",
            reason="sənədə uyğunlaşdırma",
        )
        self.assertEqual(response.status_code, 200)

        self.teacher.profile.refresh_from_db()
        self.assertEqual(self.teacher.profile.patronymic, "Səməd oğlu")
        self.assertEqual(self.teacher.profile.phone, "+994501234567")

        entry = AuditLog.objects.filter(resource_id=str(self.teacher.pk)).order_by("-created_at").first()
        self.assertEqual(entry.old_values["patronymic"], "Səməd")
        self.assertEqual(entry.new_values["patronymic"], "Səməd oğlu")

    def test_email_change_resets_verification(self):
        profile = self.teacher.profile
        profile.email_verified = True
        profile.save(update_fields=["email_verified"])

        self.login_operator()
        self.act("edit", self.teacher, email="yeni.unvan@example.com", reason="email düzəlişi")

        self.teacher.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(self.teacher.email, "yeni.unvan@example.com")
        self.assertFalse(profile.email_verified)

    def test_duplicate_email_is_rejected(self):
        self.login_operator()
        response = self.act("edit", self.teacher, email=self.namesake.email, reason="test")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "email_taken")

    def test_invalid_email_is_rejected(self):
        self.login_operator()
        response = self.act("edit", self.teacher, email="bu-email-deyil", reason="test")
        self.assertEqual(response.status_code, 400)

    def test_edit_cannot_touch_academic_content(self):
        """Əsasnamə X hüdudu: RİM qiymət/jurnal MƏZMUNUNA toxunmur."""
        from apps.accounts.services.rim.profile_edit import EDITABLE_FIELDS

        forbidden = {"grade", "score", "exam_score", "attendance", "final_grade", "role", "is_superuser"}
        self.assertEqual(forbidden & set(EDITABLE_FIELDS), set())


class RimDualRoleTests(RimCenterTestBase):
    """İkili rol: bir şəxs həm müəllim, həm inzibati işçi ola bilər."""

    def setUp(self):
        super().setUp()
        # Eyni org-da İKİNCİ aktiv üzvlük (model bunu icazə verir:
        # unique_together = (user, organization, role, scope_unit)).
        self.dual = make_user("dual_role_user", first="Nigar", last="Quliyeva", organization=self.org)
        add_member(self.dual, self.org, self.teacher_role, is_primary=True)
        add_member(self.dual, self.org, self.staff_role, is_primary=False)

    def test_model_allows_two_active_memberships_in_same_org(self):
        self.assertEqual(
            Membership.objects.filter(user=self.dual, organization=self.org, is_active=True).count(),
            2,
        )

    def test_detail_lists_both_roles(self):
        self.login_operator()
        row = self.search("Quliyeva").json()["results"][0]
        role_names = sorted(role["role_name"] for role in row["roles"])
        self.assertEqual(role_names, ["department_head", "teacher"])

    def test_effective_level_is_the_maximum_of_memberships(self):
        """İnzibati qol daha güclüdür — effektiv səviyyə MAKSİMUMDUR."""
        from apps.accounts.services.rim.policy import target_level

        self.assertEqual(target_level(self.dual, self.org), 70)

    def test_effective_permissions_are_the_union_of_memberships(self):
        """Aktorun icazələri bütün aktiv üzvlüklərin BİRLƏŞMƏSİDİR."""
        from apps.accounts.services.rim.policy import resolve_actor

        academic_role = make_role(self.org, "rim_academic", 60, ["user.search"])
        admin_side_role = make_role(self.org, "rim_admin_side", 75, ["user.block"])
        combo = make_user("combo_operator", organization=self.org)
        add_member(combo, self.org, academic_role, is_primary=True)
        add_member(combo, self.org, admin_side_role, is_primary=False)

        self.client.force_login(combo)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

        request = self.client.get(reverse("accounts:rim_user_search"), {"q": "Əliyev"}).wsgi_request
        actor = resolve_actor(request)
        self.assertTrue(actor.has("user.search"))
        self.assertTrue(actor.has("user.block"))
        self.assertFalse(actor.has("user.soft_delete"))
        # Səviyyə iki üzvlüyün maksimumu.
        self.assertEqual(actor.level, 75)

    def test_dual_role_user_is_gated_by_its_highest_role(self):
        """Aktordan aşağı olsa da, EN YÜKSƏK rolu nəzərə alınır."""
        low_role = make_role(self.org, "rim_low", 65, RIM_OPERATIONAL)
        low_operator = make_user("low_operator", organization=self.org)
        add_member(low_operator, self.org, low_role)

        self.client.force_login(low_operator)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

        # dual-ın maksimum səviyyəsi 70 > 65 → idarə oluna bilməz.
        response = self.client.post(
            reverse("accounts:rim_action"),
            data={"action": "block", "user_id": self.dual.pk, "reason": "yoxlama"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)


class RimSectionGateTests(RimCenterTestBase):
    def test_section_visible_only_with_a_user_permission(self):
        from apps.accounts.views._helpers.rbac import _role_capabilities

        request = self.client.get("/").wsgi_request

        self.client.force_login(self.operator)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        request = self.client.get(reverse("accounts:profile"), {"section": "rim-center"}).wsgi_request
        capabilities = _role_capabilities(request.user, request.user.profile)
        self.assertIn("rim-center", capabilities["allowed_sections"])
        self.assertTrue(capabilities["can_use_rim_center"])

    def test_section_hidden_for_plain_teacher(self):
        from apps.accounts.views._helpers.rbac import _role_capabilities

        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        request = self.client.get(reverse("accounts:profile")).wsgi_request
        capabilities = _role_capabilities(request.user, request.user.profile)
        self.assertNotIn("rim-center", capabilities["allowed_sections"])

    def test_section_renders_for_operator(self):
        """Panel həqiqətən render olunur (şablon + data-atributlar)."""
        self.login_operator()
        response = self.client.get(reverse("accounts:profile_section_fragment", kwargs={"section": "rim-center"}))
        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]

        self.assertIn('data-profile-section-panel="rim-center"', html)
        self.assertIn("data-rim-root", html)
        # Dinamik dəyərlər data-atributla ötürülür (xarici JS `{% url %}` görmür).
        self.assertIn(reverse("accounts:rim_user_search"), html)
        self.assertIn(reverse("accounts:rim_action"), html)
        self.assertIn('data-can-set-password="1"', html)

    def test_section_markup_has_no_inline_style_or_script(self):
        """CLAUDE.md + CSP: inline `<style>` / `<script>` (src-siz) QADAĞANDIR."""
        import re

        self.login_operator()
        html = self.client.get(reverse("accounts:profile_section_fragment", kwargs={"section": "rim-center"})).json()[
            "html"
        ]

        self.assertNotIn("<style", html)
        # `<script src=...>` və `type="application/json"` data bloku icazəlidir;
        # icra olunan inline JS isə CSP tərəfindən bloklanardı.
        for tag in re.findall(r"<script[^>]*>", html):
            self.assertTrue(
                "src=" in tag or 'type="application/json"' in tag,
                f"icra olunan inline script tapıldı: {tag}",
            )

    def test_section_fragment_is_forbidden_without_permission(self):
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = self.client.get(reverse("accounts:profile_section_fragment", kwargs={"section": "rim-center"}))
        self.assertEqual(response.status_code, 403)


class RimPrivilegedGrantTests(TestCase):
    """Əsasnamə 5.5 — «yeni administrator səlahiyyəti» ayrıca açar tələb edir."""

    def test_default_rim_role_has_no_privileged_grant_key(self):
        from apps.organizations.default_roles import DEFAULT_ROLES

        university_roles = DEFAULT_ROLES[OrganizationType.UNIVERSITY]
        rim_role = next(role for role in university_roles if role["name"] == "ikt_rehber")
        self.assertNotIn("user.grant_privileged", rim_role["permissions"])
        # Wildcard da işlədilməməlidir — o, açarı gizlicə əhatə edərdi.
        self.assertNotIn("user.*", rim_role["permissions"])
        # Gündəlik əməliyyat açarları isə yerindədir.
        for permission in RIM_OPERATIONAL:
            self.assertIn(permission, rim_role["permissions"])

    def test_rim_role_can_manage_roles_and_permissions(self):
        """Əsasnamə 4.2 — «rol və səlahiyyət idarəetməsi» RİM-dədir."""
        from apps.organizations.default_roles import DEFAULT_ROLES

        university_roles = DEFAULT_ROLES[OrganizationType.UNIVERSITY]
        rim_role = next(role for role in university_roles if role["name"] == "ikt_rehber")
        self.assertIn("role.*", rim_role["permissions"])

    def test_privileged_key_is_registered_and_labeled(self):
        from apps.organizations.permissions import (
            PERMISSION_CATEGORIES,
            get_all_permissions,
            get_permission_label as permission_label,
            validate_permissions,
        )

        self.assertIn("user.grant_privileged", PERMISSION_CATEGORIES["users"])
        self.assertIn("user.grant_privileged", get_all_permissions())
        self.assertTrue(validate_permissions(["user.search", "user.grant_privileged"]))
        self.assertNotEqual(permission_label("user.search"), "user.search")

    def test_rim_role_display_name_is_rim(self):
        from apps.organizations.default_roles import DEFAULT_ROLES

        university_roles = DEFAULT_ROLES[OrganizationType.UNIVERSITY]
        rim_role = next(role for role in university_roles if role["name"] == "ikt_rehber")
        # Slug DƏYİŞMİR (kodda hardcoded istinadlar var), yalnız görünən ad.
        self.assertEqual(rim_role["name"], "ikt_rehber")
        self.assertIn("RİM", rim_role["display_name"])
