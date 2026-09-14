"""Sahibin qərarı 2026-09-14 (deploy hazırlığı): `myedu.*` istifadəçi adları → real `ad.soyad`."""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.accounts.services.username_repair import (
    UsernameCandidate,
    institutional_handle,
    name_base,
    plan_renames,
    slug_name,
)

User = get_user_model()


class SlugAndHandleTests(SimpleTestCase):
    def test_azerbaijani_letters_become_ascii(self):
        self.assertEqual(slug_name("Rüstəm"), "rustem")
        self.assertEqual(slug_name("ƏSGƏRLİ"), "esgerli")
        self.assertEqual(slug_name("Şövqi Çingiz oğlu"), "sovqicingizoglu")
        self.assertEqual(slug_name("Qazıxanov"), "qazixanov")
        self.assertEqual(slug_name("Işıq"), "isiq")

    def test_html_entities_and_diacritics_are_cleaned(self):
        self.assertEqual(slug_name("&Uuml;LVİ"), "ulvi")
        self.assertEqual(slug_name(" Ayg&uuml;n "), "aygun")
        self.assertEqual(slug_name("José-Ünal"), "joseunal")

    def test_name_base(self):
        self.assertEqual(name_base("Elvin", "Qurbanov"), "elvin.qurbanov")
        self.assertEqual(name_base("", "Qurbanov"), "qurbanov")
        self.assertEqual(name_base("", ""), "")

    def test_institutional_handle_only_for_university_domain(self):
        self.assertEqual(institutional_handle("Rustem.Kerimov@WCU.edu.az"), "rustem.kerimov")
        self.assertEqual(institutional_handle("aygun.akbarova.230k@wcu.edu.az"), "aygun.akbarova.230k")
        self.assertEqual(institutional_handle("mahammad.cahangirli.230k@wcu.edu"), "mahammad.cahangirli.230k")
        self.assertEqual(institutional_handle("turalaga0@gmail.com"), "")
        self.assertEqual(institutional_handle("myedu.student.5@placeholder.invalid"), "")
        self.assertEqual(institutional_handle(""), "")
        self.assertEqual(institutional_handle("123@wcu.edu.az"), "")
        # Sərbəst seçilmiş (ad.soyad olmayan) universitet hesabları götürülmür.
        for free in ("asif.66666", "memmed_gym", "elvin12682", "maurra.m", "rihat.547", "solmazalasgerova"):
            self.assertEqual(institutional_handle(f"{free}@wcu.edu.az"), "", free)


class PlanTests(SimpleTestCase):
    def _c(self, pk, username, first, last, email=""):
        return UsernameCandidate(pk, username, first, last, email)

    def test_duplicates_get_numeric_suffix_in_pk_order(self):
        rows = plan_renames(
            [
                self._c(3, "myedu.student.3", "Elvin", "Qurbanov"),
                self._c(1, "myedu.student.1", "Elvin", "Qurbanov"),
                self._c(2, "myedu.worker.2", "ELVİN", "QURBANOV"),
            ],
            reserved=["qa.teacher"],
        )
        self.assertEqual(
            [(r.pk, r.new) for r in rows], [(1, "elvin.qurbanov"), (2, "elvin.qurbanov2"), (3, "elvin.qurbanov3")]
        )

    def test_reserved_names_are_never_taken_case_insensitively(self):
        rows = plan_renames([self._c(9, "myedu.student.9", "Elvin", "Qurbanov")], reserved=["Elvin.Qurbanov"])
        self.assertEqual(rows[0].new, "elvin.qurbanov2")

    def test_institutional_handle_wins_over_name(self):
        rows = plan_renames(
            [self._c(5, "myedu.student.5", "Aygün", "Əkbərova", "aygun.akbarova.230k@wcu.edu.az")], reserved=[]
        )
        self.assertEqual((rows[0].new, rows[0].source), ("aygun.akbarova.230k", "institutional"))

    def test_nameless_account_gets_fallback(self):
        rows = plan_renames([self._c(77, "myedu.worker.77", "", "")], reserved=[])
        self.assertEqual((rows[0].new, rows[0].source), ("hesab77", "fallback"))

    def test_rerun_is_idempotent(self):
        first = plan_renames([self._c(1, "myedu.student.1", "Elvin", "Qurbanov")], reserved=[])
        again = plan_renames([self._c(1, first[0].new, "Elvin", "Qurbanov")], reserved=[])
        self.assertEqual((again[0].new, again[0].source), ("elvin.qurbanov", "keep"))


class CommandTests(TestCase):
    def setUp(self):
        User.objects.create_user("myedu.student.10", "a@gmail.com", "x", first_name="Elvin", last_name="Qurbanov")
        User.objects.create_user("myedu.student.11", "b@gmail.com", "x", first_name="Elvin", last_name="Qurbanov")
        User.objects.create_user("myedu.worker.12", "rustem.kerimov@wcu.edu.az", "x", first_name="R", last_name="K")
        User.objects.create_user("qa.teacher", "q@example.com", "x", first_name="QA", last_name="Teacher")
        User.objects.create_user("elvin.qurbanov", "e@example.com", "x", first_name="E", last_name="Q")

    def test_dry_run_changes_nothing(self):
        out = StringIO()
        call_command("rename_legacy_usernames", stdout=out)
        self.assertIn("DRY-RUN", out.getvalue())
        self.assertTrue(User.objects.filter(username="myedu.student.10").exists())

    def test_apply_renames_only_legacy_accounts(self):
        out = StringIO()
        call_command("rename_legacy_usernames", "--apply", stdout=out)
        names = set(User.objects.values_list("username", flat=True))
        # Mövcud `elvin.qurbanov` toxunulmur → legacy ikisi 2 və 3 alır.
        self.assertIn("elvin.qurbanov", names)
        self.assertIn("elvin.qurbanov2", names)
        self.assertIn("elvin.qurbanov3", names)
        self.assertIn("rustem.kerimov", names)
        self.assertIn("qa.teacher", names)
        self.assertFalse(any(n.startswith("myedu.") for n in names))
        # Təkrar icra sabitdir.
        call_command("rename_legacy_usernames", "--apply", stdout=StringIO())
        self.assertEqual(set(User.objects.values_list("username", flat=True)), names)


class FinalizeUniversityIdentityTests(TestCase):
    def setUp(self):
        from apps.organizations.models import Organization
        from core.constants import OrganizationType

        self.owner = User.objects.create_user("owner.qku", "o@example.com", "x")
        self.org = Organization.objects.create(
            name="MyEdu Universiteti (rehearsal)",
            slug="myedu-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        from apps.registrar.models import Subject

        Subject.objects.create(organization=self.org, code="MYEDU-L2295", name="Multikulturalizmə giriş")
        Subject.objects.create(organization=self.org, code="AZD-101", name="Rəsmi kodlu fənn")
        for pk, ident in ((1, "myedu-student-1090"), (2, "myedu-student-7")):
            user = User.objects.create_user(f"student.{pk}", f"s{pk}@example.com", "x")
            profile = user.profile
            profile.organization = self.org
            profile.institutional_identifier = ident
            profile.save(update_fields=["organization", "institutional_identifier"])

    def test_dry_run_then_apply(self):
        from apps.accounts.models import UserProfile
        from apps.organizations.models import Organization

        call_command("finalize_university_identity", stdout=StringIO())
        self.assertTrue(Organization.objects.filter(slug="myedu-univ").exists())

        out = StringIO()
        call_command("finalize_university_identity", "--apply", stdout=out)
        org = Organization.objects.get(pk=self.org.pk)
        self.assertEqual((org.name, org.slug), ("Qərbi Kaspi Universiteti", "qku"))
        idents = sorted(
            UserProfile.objects.filter(organization=org, institutional_identifier__isnull=False).values_list(
                "institutional_identifier", flat=True
            )
        )
        self.assertEqual(idents, ["1090", "7"])
        from apps.registrar.models import Subject

        self.assertEqual(sorted(Subject.objects.values_list("code", flat=True)), ["AZD-101", "QKU-2295"])
        # Təkrar icra (slug artıq `qku`) — idempotent, xəta yox.
        call_command("finalize_university_identity", "--apply", stdout=StringIO())
        self.assertEqual(Organization.objects.get(pk=self.org.pk).slug, "qku")
