"""RİM (İKT) rəhbərinin `journal.correct` səlahiyyəti + onu paylaya bilməsi.

Sahibin qərarı: «RİM rəhbərinin təyin etdiyi işçi» üçün AYRICA rol yaradılmır —
RİM rəhbəri icazə redaktorundan (``role.assign``) istənilən aşağı rola
``journal.correct`` verir, həmin rol da sənədli düzəliş edə bilir. Bu dəst
zəncirin hər üç halqasını yoxlayır:

  1. ``ikt_rehber`` rolunun tərifində və seed miqrasiyasında ``journal.correct`` var;
  2. RİM rəhbəri icazə redaktorundan bu açarı başqa rola verə bilir;
  3. həmin rolu daşıyan işçi ``corrections.can_correct_journal`` qapısından keçir,
     icazəsi olmayan isə keçmir.
"""

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()

CORRECT_PERMISSION = "journal.correct"


class IktRehberRoleDefinitionTest(SimpleTestCase):
    """Rol tərifi + AZ etiket (DB tələb etmir)."""

    def test_role_definition_carries_journal_correct(self):
        from apps.organizations.default_roles_university import UNIVERSITY_ROLES

        role = next(item for item in UNIVERSITY_ROLES if item["name"] == "ikt_rehber")
        self.assertIn(CORRECT_PERMISSION, role["permissions"])
        # İcazə redaktorunu işlədə bilməsi üçün `role.*` da olmalıdır.
        self.assertIn("role.*", role["permissions"])

    def test_seed_migration_carries_journal_correct(self):
        """Mövcud universitetlərə geriyə-doldurma da eyni açarı daşıyır."""
        import importlib

        module = importlib.import_module("apps.organizations.migrations.0026_seed_ikt_rehber_role")
        self.assertIn(CORRECT_PERMISSION, module._IKT_REHBER["permissions"])

    def test_permission_has_azerbaijani_label(self):
        from apps.organizations.permissions import PERMISSION_CATEGORIES, PERMISSION_LABELS

        self.assertIn(CORRECT_PERMISSION, PERMISSION_CATEGORIES["journal"])
        self.assertEqual(str(PERMISSION_LABELS[CORRECT_PERMISSION]), "Jurnalda sənədli düzəliş etmək")


class RimDelegatesJournalCorrectTest(TestCase):
    """RİM rəhbəri → icazə redaktoru → başqa rol sənədli düzəliş edə bilir."""

    def setUp(self):
        self.owner = User.objects.create_user("rd_owner", "rd_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="RD Univ",
                slug="rd-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.rim_head = User.objects.create_user("rd_rim", "rd_rim@qku.edu.az", "pw")
            self.staffer = User.objects.create_user("rd_staff", "rd_staff@qku.edu.az", "pw")
            self.rim_role = self.org.roles.get(name="ikt_rehber")
            # «RİM rəhbərinin təyin etdiyi işçi» — hələlik adi kafedra katibi rolu.
            self.staff_role = self.org.roles.filter(is_active=True, level__lt=self.rim_role.level).order_by("-level")[0]
            Membership.objects.create(
                user=self.rim_head,
                organization=self.org,
                role=self.rim_role,
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=self.staffer,
                organization=self.org,
                role=self.staff_role,
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

    def _correction_request(self, user):
        """`can_correct_journal` ÜÇÜN GERÇƏK request.

        İcazə həlli middleware-in bağladığı ``org_memberships``/``org_permissions``
        üzərindən gedir (bax ``core.permissions.request_has_permission``), ona görə
        süni ``RequestFactory`` requesti yaramır — real cavabın
        ``wsgi_request``-ini götürürük."""
        return self._client(user).get(reverse("accounts:profile")).wsgi_request

    def test_rim_head_itself_can_correct(self):
        from apps.registrar import corrections

        self.assertTrue(corrections.can_correct_journal(self._correction_request(self.rim_head)))

    def test_staffer_cannot_correct_before_delegation(self):
        from apps.registrar import corrections

        self.assertNotIn(CORRECT_PERMISSION, self.staff_role.permissions or [])
        self.assertFalse(corrections.can_correct_journal(self._correction_request(self.staffer)))

    def test_rim_head_grants_journal_correct_and_staffer_can_correct(self):
        from apps.registrar import corrections

        resp = self._client(self.rim_head).post(
            reverse("accounts:permission_editor"),
            {
                "role_id": str(self.staff_role.id),
                "action": "add",
                "permission": CORRECT_PERMISSION,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.staff_role.refresh_from_db()
        self.assertIn(CORRECT_PERMISSION, self.staff_role.permissions)
        # Təyin edilən işçi indi sənədli düzəliş qapısından keçir.
        self.assertTrue(corrections.can_correct_journal(self._correction_request(self.staffer)))

    def test_plain_member_cannot_open_the_permission_editor(self):
        resp = self._client(self.staffer).get(reverse("accounts:permission_editor"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:profile"))
