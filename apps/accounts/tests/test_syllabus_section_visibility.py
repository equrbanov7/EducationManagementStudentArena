"""«Sillabuslar» bölmələrinin menyu görünürlüyü — permission-əsaslı və FAIL-CLOSED.

Nəyi qoruyur
------------
Sillabus səthi DÖRD yerdə qeydiyyatdan keçir və dördü də uyğun olmalıdır:

1. ``sections_api.SECTION_PARTIALS``     — hansı şablon render olunur,
2. ``sections_api.AJAX_SAFE_SECTIONS``   — fraqment endpoint-i qəbul edirmi,
3. ``profile.html`` ``data-ajax-sections`` — ön tərəf AJAX ilə yükləyirmi,
4. ``rbac._role_capabilities``           — istifadəçi ONU ALIRMI.

İlk üçünü ``test_section_registry_consistency`` kilidləyir. DÖRDÜNCÜSÜ isə
səssiz sınır: şablonlar ``{% if 'syllabus-list' in allowed_sections %}`` ilə
qorunduğu üçün icazə paylanmayanda bölmə sadəcə BOŞ render olunur — nə xəta,
nə 403. Məhz belə də olmuşdu: siyahı, redaktor, CSS və JS hazır idi, amma
``allowed_sections``-a heç vaxt düşmürdü, yəni ekran heç kimə görünmürdü.

Ona görə burada hər iki istiqamət yoxlanılır: icazəsi OLAN alır, OLMAYAN almır.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.views.profile.sections_api import AJAX_SAFE_SECTIONS, SECTION_PARTIALS
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()

PASSWORD = "StrongPass123!"

#: Bölmə açarları — dizayn paketi və `apps.syllabus` ilə eynidir.
SYLLABUS_SECTIONS = frozenset({"syllabus-list", "syllabus-editor"})


class SyllabusSectionVisibilityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("syl_owner", "syl_owner@qku.edu.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Sillabus Univ",
            slug="syllabus-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.users = {}
        # `teacher` sillabusu yaradır, `chair` təsdiqləyir, `clerk`-in isə
        # sillabusla heç bir işi yoxdur — üçü də EYNİ təşkilatdadır ki, fərq
        # yalnız icazə dəstindən gəlsin.
        matrix = {
            "syl_teacher": ["syllabus.view", "syllabus.edit", "syllabus.submit"],
            "syl_chair": ["syllabus.view", "syllabus.review", "syllabus.approve"],
            "syl_clerk": ["post.view"],
        }
        for name, permissions in matrix.items():
            role = Role.objects.create(
                organization=cls.org,
                name=name,
                display_name=name.replace("_", " ").title(),
                level=60,
                scope_type=RoleScopeType.ORGANIZATION,
                permissions=permissions,
                is_system=False,
                is_active=True,
            )
            user = User.objects.create_user(f"u_{name}", f"u_{name}@qku.edu.az", PASSWORD)
            Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
            cls.users[name] = user

    def _sections(self, role_name):
        client = Client()
        client.force_login(self.users[role_name])
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200, role_name)
        return set(response.context["allowed_sections"])

    # ── İcazəsi olan görür ──────────────────────────────────────────────────

    def test_teacher_with_view_permission_gets_both_surfaces(self):
        """Redaktor siyahıdan açılır — ikisi BİRLİKDƏ verilməlidir."""
        sections = self._sections("syl_teacher")

        self.assertTrue(
            SYLLABUS_SECTIONS.issubset(sections),
            f"`syllabus.view` olan müəllim bölmələri almadı: {sorted(SYLLABUS_SECTIONS - sections)}",
        )

    def test_chair_head_also_gets_the_surfaces(self):
        """Kafedra müdiri təsdiq üçün eyni siyahını açır (əhatəsi ayrıca dardır)."""
        self.assertTrue(SYLLABUS_SECTIONS.issubset(self._sections("syl_chair")))

    # ── İcazəsi olmayan görmür (fail-closed) ────────────────────────────────

    def test_role_without_syllabus_permission_gets_nothing(self):
        """Açar geri alınanda bölmə də dərhal itməlidir."""
        leaked = self._sections("syl_clerk") & SYLLABUS_SECTIONS

        self.assertEqual(leaked, set(), f"icazəsiz rol sillabus bölməsi aldı: {sorted(leaked)}")

    # ── Dörd qeydiyyatın uyğunluğu ──────────────────────────────────────────

    def test_granted_sections_are_registered_end_to_end(self):
        """Menyuda verilən hər bölmənin şablonu və AJAX icazəsi olmalıdır.

        Əks halda istifadəçi bölməni görür, klikləyəndə isə fraqment endpoint-i
        403 qaytarır — `test_section_registry_consistency` sənədləşdirdiyi tələ.
        """
        granted = self._sections("syl_teacher") & SYLLABUS_SECTIONS

        for section in sorted(granted):
            with self.subTest(section=section):
                self.assertIn(section, SECTION_PARTIALS)
                self.assertIn(section, AJAX_SAFE_SECTIONS)
