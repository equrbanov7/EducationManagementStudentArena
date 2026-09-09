"""«Rol təyin et» / «Rolları idarə et» — TƏK rol kataloqu reqressiya qapısı.

SAHİB ŞİKAYƏTİ (2026-09-09): «Bir nəfərə həm proqram koordinatoru, həm müəllim
edəcəm — proqram koordinatoru rolunu görmürəm.»

KÖK SƏBƏB: iki ekran iki fərqli kataloqdan oxuyurdu — «Rol təyin et» təşkilatın
`organizations.Role` kataloqundan, «Rolları idarə et» isə köhnə
`core.roles.ProfileRole` enum-undan (orada `program_coordinator` YOXDUR). Ona
görə həmin rol ikinci ekranda nə nişan kimi görünürdü, nə də verilə bilirdi.

Bu modul üç şeyi dondurur:
  1. bir şəxsin BÜTÜN aktiv təşkilat rolları HƏR İKİ ekranda görünür;
  2. «Rolları idarə et» rol seçicisi təşkilat kataloqunu göstərir
     (`program_coordinator` daxil) və ikinci rol verəndə birincini söndürmür;
  3. səviyyə qapısı yerindədir — aktor öz EFFEKTİV səviyyəsinə bərabər və ya
     ondan yuxarı rolu verə bilməz (kataloqun öz `level` sütunu ilə RBAC
     səviyyəsi fərqlidir, bax `services/role_catalog.effective_level`).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.services.role_catalog import effective_level
from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

PROFILE_URL = reverse("accounts:profile")
COORDINATOR_LABEL = "Proqram koordinatoru"
TEACHER_LABEL = "Müəllim"


class MultiRoleCatalogueTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ru_owner", "ru_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Roles UI Univ",
                slug="roles-ui-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org,
                name="Mühəndislik fakültəsi",
                slug="ru-fak",
                unit_type=OrgUnitType.FACULTY,
            )
            cls.role_teacher = cls.org.roles.get(name="teacher")
            cls.role_coordinator = cls.org.roles.get(name="program_coordinator")
            cls.role_dean = cls.org.roles.get(name="dean")
            cls.role_vice_rector = cls.org.roles.get(name="vice_rector")
            cls.role_rector = cls.org.roles.get(name="rector")

            # Aktor: rektor — universitet seed-ində `role.assign`/`*` daşıyan
            # yeganə rol (`org.manage_members` qapısı `_gates`-dədir).
            cls.actor = User.objects.create_user("ru_actor", "ru_actor@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.actor,
                organization=cls.org,
                role=cls.role_rector,
                is_primary=True,
                is_active=True,
            )

            # Hədəf: eyni anda «Proqram koordinatoru» + «Müəllim».
            cls.multi_user = User.objects.create_user("ru_multi", "ru_multi@qku.edu.az", "pw")
            cls.multi_user.first_name = "Aysel"
            cls.multi_user.last_name = "Məmmədova"
            cls.multi_user.save(update_fields=["first_name", "last_name"])
            Membership.objects.create(
                user=cls.multi_user,
                organization=cls.org,
                role=cls.role_coordinator,
                scope_unit=cls.faculty,
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=cls.multi_user,
                organization=cls.org,
                role=cls.role_teacher,
                is_active=True,
            )

            # Yalnız müəllim — ikinci rol vermə axını üçün.
            cls.plain_teacher = User.objects.create_user("ru_teacher", "ru_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.plain_teacher,
                organization=cls.org,
                role=cls.role_teacher,
                is_primary=True,
                is_active=True,
            )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _active_roles(self, user):
        with bypass_rls():
            return set(
                Membership.objects.filter(user=user, organization=self.org, is_active=True).values_list(
                    "role__name", flat=True
                )
            )


class MultiRoleVisibilityTest(MultiRoleCatalogueTestBase):
    """Hər iki ekran şəxsin BÜTÜN rollarını göstərir."""

    def test_manage_roles_section_shows_every_organization_role_of_a_person(self):
        response = self._client(self.actor).get(f"{PROFILE_URL}?section=manage-roles")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, COORDINATOR_LABEL)
        self.assertContains(response, TEACHER_LABEL)

    def test_role_assignment_section_shows_every_organization_role_of_a_person(self):
        response = self._client(self.actor).get(f"{PROFILE_URL}?section=role-assignment")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, COORDINATOR_LABEL)
        self.assertContains(response, TEACHER_LABEL)

    def test_manage_roles_grant_picker_offers_the_organization_role_catalogue(self):
        """Köhnə səthdə seçici `ProfileRole` enum-u idi — `program_coordinator` yox idi."""
        response = self._client(self.actor).get(f"{PROFILE_URL}?section=manage-roles")
        options = response.context["manage_roles_section"]["grantable_roles"]
        labels = {option["label"] for option in options}
        values = {option["value"] for option in options}
        self.assertIn(str(self.role_coordinator.id), values)
        self.assertTrue(any(COORDINATOR_LABEL in label for label in labels))
        self.assertTrue(any(TEACHER_LABEL in label for label in labels))

    def test_both_sections_read_the_same_role_catalogue(self):
        client = self._client(self.actor)
        manage = client.get(f"{PROFILE_URL}?section=manage-roles")
        assign = client.get(f"{PROFILE_URL}?section=role-assignment")
        manage_ids = {option["value"] for option in manage.context["manage_roles_section"]["grantable_roles"]}
        assign_ids = {option["value"] for option in assign.context["role_assignment_section"]["role_choices"]}
        self.assertEqual(manage_ids, assign_ids)

    def test_manage_roles_row_carries_both_role_chips(self):
        response = self._client(self.actor).get(f"{PROFILE_URL}?section=manage-roles")
        rows = response.context["manage_roles_section"]["table_rows"]
        row = next(item for item in rows if item["data"]["username"] == self.multi_user.username)
        self.assertEqual({chip["name"] for chip in row["data"]["roles"]}, {"program_coordinator", "teacher"})
        # Əhatə vahidi nişanın üstündə görünür (koordinator fakültə üzrədir).
        scopes = {chip["name"]: chip["scope"] for chip in row["data"]["roles"]}
        self.assertEqual(scopes["program_coordinator"], self.faculty.name)


class MultiRoleGrantTest(MultiRoleCatalogueTestBase):
    """«Rol ver» ikinci üzvlük yaradır, birincini söndürmür."""

    def test_grant_adds_a_second_membership_and_keeps_the_first(self):
        response = self._client(self.actor).post(
            reverse("accounts:manage_roles"),
            {
                "action": "grant_role",
                "user_id": str(self.plain_teacher.id),
                "role_id": str(self.role_coordinator.id),
                "scope_unit": str(self.faculty.id),
                "reason": "Əmr 12/9",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._active_roles(self.plain_teacher), {"teacher", "program_coordinator"})

    def test_revoke_deactivates_only_the_selected_membership(self):
        with bypass_rls():
            membership = Membership.objects.get(
                user=self.multi_user, organization=self.org, role=self.role_teacher, is_active=True
            )
        self._client(self.actor).post(
            reverse("accounts:manage_roles"),
            {"action": "revoke_role", "membership_id": str(membership.id), "reason": "səhv təyinat"},
            follow=True,
        )
        self.assertEqual(self._active_roles(self.multi_user), {"program_coordinator"})

    def test_last_membership_cannot_be_revoked_here(self):
        with bypass_rls():
            membership = Membership.objects.get(
                user=self.plain_teacher, organization=self.org, role=self.role_teacher, is_active=True
            )
        self._client(self.actor).post(
            reverse("accounts:manage_roles"),
            {"action": "revoke_role", "membership_id": str(membership.id)},
            follow=True,
        )
        self.assertEqual(self._active_roles(self.plain_teacher), {"teacher"})


class MultiRoleLevelGuardTest(MultiRoleCatalogueTestBase):
    """Səviyyə qapısı: aktor öz EFFEKTİV səviyyəsindən aşağı rolları verə bilər."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            # Seed-də dekanda `role.assign` YOXDUR — bu qapı ayrıca sınanır
            # (`test_manage_roles_scope.py`). Burada məqsəd SƏVİYYƏ qapısıdır,
            # ona görə icazə «İcazələr» ekranının etdiyi kimi rola əlavə edilir.
            cls.role_dean.permissions = list(cls.role_dean.permissions or []) + ["role.assign"]
            cls.role_dean.save(update_fields=["permissions"])

            cls.dean = User.objects.create_user("ru_dean", "ru_dean@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.dean,
                organization=cls.org,
                role=cls.role_dean,
                scope_unit=cls.faculty,
                is_primary=True,
                is_active=True,
            )
            cls.scoped_teacher = User.objects.create_user("ru_scoped", "ru_scoped@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.scoped_teacher,
                organization=cls.org,
                role=cls.role_teacher,
                scope_unit=cls.faculty,
                is_primary=True,
                is_active=True,
            )

    def test_effective_level_beats_the_catalogue_column(self):
        """Kataloq `level` sütunu RBAC səviyyəsi DEYİL — qapı effektiv səviyyəyə baxır."""
        self.assertEqual(self.role_teacher.level, 50)
        self.assertEqual(effective_level(self.role_teacher), 60)
        self.assertEqual(self.role_dean.level, 80)
        self.assertEqual(effective_level(self.role_dean), 90)
        self.assertEqual(effective_level(self.role_vice_rector), 95)

    def test_actor_cannot_grant_a_role_above_own_level(self):
        self._client(self.dean).post(
            reverse("accounts:manage_roles"),
            {
                "action": "grant_role",
                "user_id": str(self.scoped_teacher.id),
                "role_id": str(self.role_vice_rector.id),
            },
            follow=True,
        )
        self.assertEqual(self._active_roles(self.scoped_teacher), {"teacher"})

    def test_actor_cannot_grant_a_role_at_own_level(self):
        self._client(self.dean).post(
            reverse("accounts:manage_roles"),
            {"action": "grant_role", "user_id": str(self.scoped_teacher.id), "role_id": str(self.role_dean.id)},
            follow=True,
        )
        self.assertEqual(self._active_roles(self.scoped_teacher), {"teacher"})

    def test_actor_can_grant_a_role_below_own_level(self):
        self._client(self.dean).post(
            reverse("accounts:manage_roles"),
            {
                "action": "grant_role",
                "user_id": str(self.scoped_teacher.id),
                "role_id": str(self.role_coordinator.id),
                "scope_unit": str(self.faculty.id),
            },
            follow=True,
        )
        self.assertEqual(self._active_roles(self.scoped_teacher), {"teacher", "program_coordinator"})

    def test_grantable_catalogue_hides_roles_at_or_above_actor_level(self):
        response = self._client(self.dean).get(f"{PROFILE_URL}?section=manage-roles")
        values = {option["value"] for option in response.context["manage_roles_section"]["grantable_roles"]}
        self.assertNotIn(str(self.role_dean.id), values)
        self.assertNotIn(str(self.role_vice_rector.id), values)
        self.assertIn(str(self.role_coordinator.id), values)
