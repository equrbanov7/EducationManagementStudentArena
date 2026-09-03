"""`sync_journal_permissions` — MÖVCUD universitetlərə `journal.*` açarlarının verilməsi.

NİYƏ BU TEST VAR. Rol şablonları (``UNIVERSITY_ROLES``) YALNIZ təşkilat
yaradılanda tətbiq olunur. Şablona `journal.roster` yazmaq artıq mövcud
universitetin dekanına/koordinatoruna heç nə vermir — «Alt qrupdan tələbə əlavə
et» düyməsi onlara GÖRÜNMƏZ qalır. Yəni sinxronlaşdırma əmri funksiyanın
görünməsi üçün MƏCBURİ addımdır və sınaqsız qalmamalıdır.

Yoxlanılan invariantlar:

* quru işləyiş (defolt) HEÇ NƏ yazmır;
* ``--apply`` çatışmayan açarları əlavə edir;
* əməl ADDITIVE-dir — mövcud icazələr heç vaxt silinmir;
* yalnız ``is_system`` rollara toxunur (universitetin öz rolları qorunur);
* təkrar işləyiş idempotentdir.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.organizations.models import Organization, Role
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()

ROSTER = "journal.roster"
#: Şablonda `journal.roster` daşıyan rollar (bax default_roles_university.py).
ROSTER_ROLES = ("program_coordinator", "dean")


class SyncJournalPermissionsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sjp_owner", "sjp_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SJP Univ",
                slug="sjp-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )

    def _strip_roster(self):
        """Köhnə (şablon yenilənməmiş) universiteti təqlid et — açarı geri al."""
        with bypass_rls():
            for role in Role.objects.filter(organization=self.org, name__in=ROSTER_ROLES):
                role.permissions = [p for p in (role.permissions or []) if p != ROSTER]
                role.save(update_fields=["permissions"])

    def _permissions(self, name):
        with bypass_rls():
            return list(Role.objects.get(organization=self.org, name=name).permissions or [])

    def test_dry_run_does_not_write(self):
        self._strip_roster()
        out = StringIO()
        call_command("sync_journal_permissions", "--org", self.org.slug, stdout=out)
        self.assertIn("QURU İŞLƏYİŞ", out.getvalue())
        for name in ROSTER_ROLES:
            self.assertNotIn(ROSTER, self._permissions(name))

    def test_apply_grants_missing_key(self):
        self._strip_roster()
        call_command("sync_journal_permissions", "--org", self.org.slug, "--apply", stdout=StringIO())
        for name in ROSTER_ROLES:
            self.assertIn(ROSTER, self._permissions(name), name)

    def test_sync_is_additive_and_keeps_custom_permissions(self):
        self._strip_roster()
        with bypass_rls():
            role = Role.objects.get(organization=self.org, name="program_coordinator")
            role.permissions = list(role.permissions or []) + ["custom.keep_me"]
            role.save(update_fields=["permissions"])

        call_command("sync_journal_permissions", "--org", self.org.slug, "--apply", stdout=StringIO())

        after = self._permissions("program_coordinator")
        self.assertIn(ROSTER, after)
        self.assertIn("custom.keep_me", after)  # heç nə silinmir

    def test_custom_non_system_role_is_untouched(self):
        self._strip_roster()
        with bypass_rls():
            custom = Role.objects.create(
                organization=self.org,
                name="program_coordinator_custom",
                level=40,
                permissions=["course.view"],
                is_system=False,
            )
        call_command("sync_journal_permissions", "--org", self.org.slug, "--apply", stdout=StringIO())
        with bypass_rls():
            custom.refresh_from_db()
        self.assertEqual(custom.permissions, ["course.view"])

    def test_second_run_is_idempotent(self):
        self._strip_roster()
        call_command("sync_journal_permissions", "--org", self.org.slug, "--apply", stdout=StringIO())
        before = self._permissions("program_coordinator")

        out = StringIO()
        call_command("sync_journal_permissions", "--org", self.org.slug, stdout=out)
        self.assertIn("Əlavə ediləcək icazə yoxdur", out.getvalue())
        self.assertEqual(self._permissions("program_coordinator"), before)
