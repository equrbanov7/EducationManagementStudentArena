"""«Heyət idarəetməsi» (`student-organization-management`) — reqressiya testləri.

Bölmə 2026-09-09-da sahibin tapşırığı ilə yenidən quruldu (dəvət/müraciət
panelləri silindi, yerində YALNIZ üzv reyestri qaldı). Bu modul həmin
yenidənqurmanın iki KRİTİK zəmanətini kilidləyir:

1. **Uzaqlaşdırma SOFT-dur.** «Çıxar» heç bir sətri silmir — `Membership`
   sətri bazada qalır, yalnız `is_active` bayrağı düşür, `User` və
   `UserProfile` toxunulmur, səbəb `apps.audit`-ə yazılır. Beləliklə əməl
   BƏRPA OLUNA BİLƏNDİR.
2. **Sorğu büdcəsi səhifə ölçüsündən ASILI DEYİL.** Səhifələmə server
   tərəfdədir və səhifədəki şəxslərin üzvlükləri TƏK sorğu ilə yığılır, ona
   görə 25 və 100 sətirlik səhifə eyni sayda SQL sorğusu ilə qurulur (N+1 yox).
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import ProfileRole, UserProfile
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

REGISTRY = "apps.accounts.views._helpers.org_sections._members_registry"
SECTION_URL_PARAMS = "?section=student-organization-management"


def _make_org(name, slug, owner):
    return Organization.objects.create(
        name=name,
        slug=slug,
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )


def _join(user, organization, membership_role_name, profile_role):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    return Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={
            "role": organization.roles.get(name=membership_role_name),
            "is_primary": True,
            "is_active": True,
        },
    )[0]


def _login_with_org(client, user, organization):
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()


class StaffManagementSoftRemovalTest(TestCase):
    """«Çıxar» heç nəyi SİLMİR — yalnız üzvlüyü deaktiv edir."""

    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username="hm_soft_owner", email="hm_soft_owner@example.com", password="pw12345678"
        )
        self.org = _make_org("Soft Removal Org", "soft-removal-org", self.owner)
        self.target = User.objects.create_user(
            username="hm_soft_target", email="hm_soft_target@example.com", password="pw12345678"
        )
        self.membership = _join(self.target, self.org, "student", ProfileRole.STUDENT)
        _login_with_org(self.client, self.owner, self.org)

    def test_remove_org_member_is_soft_and_recoverable(self):
        reason = "Təhsilini başqa universitetdə davam etdirir."
        membership_pk = self.membership.pk
        audit_before = AuditLog.objects.filter(organization=self.org, resource_type="membership").count()

        response = self.client.post(
            reverse("accounts:student_organization_management"),
            {"action": "remove_org_member", "user_id": str(self.target.id), "remove_reason": reason},
        )
        self.assertEqual(response.status_code, 302)

        # 1) Üzvlük SƏTRİ bazada QALIR — yalnız bayraq düşür.
        self.assertTrue(
            Membership.objects.filter(pk=membership_pk).exists(),
            "Membership sətri SİLİNİB — uzaqlaşdırma soft olmalıdır",
        )
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.is_active)
        self.assertFalse(self.membership.is_primary)
        # Sətrin özəyi dəyişməyib: eyni şəxs, eyni təşkilat, eyni rol.
        self.assertEqual(self.membership.user_id, self.target.id)
        self.assertEqual(self.membership.organization_id, self.org.id)
        self.assertIsNotNone(self.membership.role_id)

        # 2) Hesab və profil TOXUNULMAYIB (hesab deaktiv DƏ edilmir).
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertTrue(UserProfile.objects.filter(user=self.target).exists())

        # 3) Səbəb audit jurnalına yazılıb (bərpa üçün iz).
        entry = (
            AuditLog.objects.filter(organization=self.org, resource_type="membership", resource_id=str(self.target.id))
            .order_by("-created_at")
            .first()
        )
        self.assertIsNotNone(entry, "Uzaqlaşdırma üçün audit qeydi yaradılmayıb")
        self.assertEqual(entry.reason, reason)
        self.assertEqual(
            AuditLog.objects.filter(organization=self.org, resource_type="membership").count(),
            audit_before + 1,
        )

        # 4) BƏRPA mümkündür — bayrağı qaytarmaq kifayətdir.
        Membership.objects.filter(pk=membership_pk).update(is_active=True)
        self.assertTrue(Membership.objects.filter(pk=membership_pk, is_active=True).exists())

    def test_remove_without_reason_changes_nothing(self):
        response = self.client.post(
            reverse("accounts:student_organization_management"),
            {"action": "remove_org_member", "user_id": str(self.target.id)},
        )
        self.assertEqual(response.status_code, 302)
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.is_active)


class StaffManagementQueryBudgetTest(TestCase):
    """Sorğu sayı SƏHİFƏ ÖLÇÜSÜNDƏN asılı olmamalıdır (N+1 qoruyucusu)."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="hm_budget_owner", email="hm_budget_owner@example.com", password="pw12345678"
        )
        cls.org = _make_org("Query Budget Org", "query-budget-org", cls.owner)
        # 100-dən çox üzv: 25-lik səhifə də, 100-lük səhifə də TAM dolur.
        for index in range(120):
            member = User.objects.create_user(
                username=f"hm_budget_member_{index:03d}",
                email=f"hm_budget_member_{index:03d}@example.com",
                password="pw12345678",
                first_name=f"Member{index:03d}",
                last_name="Test",
            )
            _join(member, cls.org, "student", ProfileRole.STUDENT)

    def _count_queries(self, page_size):
        client = Client()
        _login_with_org(client, self.owner, self.org)
        url = reverse("accounts:profile") + SECTION_URL_PARAMS
        with mock.patch(f"{REGISTRY}.PAGE_SIZE", page_size):
            # İlk sorğu keşləri (icazə/rol) qızdırır — ölçmə ikincidədir.
            client.get(url)
            with CaptureQueriesContext(connection) as ctx:
                response = client.get(url)
            self.assertEqual(response.status_code, 200)
            section = response.context["student_org_management_section"]
            self.assertEqual(len(section["rows"]), page_size)
            return len(ctx.captured_queries)

    def test_query_count_is_independent_of_page_size(self):
        small = self._count_queries(25)
        large = self._count_queries(100)
        self.assertEqual(
            small,
            large,
            f"Sorğu sayı səhifə ölçüsü ilə DƏYİŞİR (25 → {small}, 100 → {large}); "
            "bu, səhifədəki sətirlər üçün N+1 deməkdir.",
        )
