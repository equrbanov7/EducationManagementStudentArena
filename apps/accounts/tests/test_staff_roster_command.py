"""`seed_staff_roster` — eyniadlılıq qapısı (2026-09-06 klon tapıntısı).

NİYƏ. Komanda mövcud hesabı YALNIZ ad+soyada görə tapırdı. Klonda 463 eyni
ad-soyad qrupu var; nəticədə 21 heyət rolu SƏHV hesaba yapışmışdı — o cümlədən
`vice_rector` bir TƏLƏBƏ hesabına. Prod-da eyni qaçış tələbəyə prorektor
səlahiyyəti verərdi.

Qapı fail-closed-dur: şübhəli sətir üçün heç nə yazılmır, hesabatda ayrıca
göstərilir və operator əl ilə həll edir.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()


class AmbiguousMatchTest(TestCase):
    """Dry-run: eyniadlı və yalnız-tələbə halları «çox mənalı» sayılır."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sr_owner", "sr_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SR Univ",
                slug="sr-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )

    def _member(self, username, first, last, role_name):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        user.first_name, user.last_name = first, last
        user.save(update_fields=["first_name", "last_name"])
        with bypass_rls():
            Membership.objects.create(
                user=user,
                organization=self.org,
                role=self.org.roles.get(name=role_name),
                is_primary=True,
                is_active=True,
            )
        return user

    def _run(self, rows, **options):
        """Komandanı REAL CSV ilə işlədir (oxuma yolu da sınaqdan keçsin)."""
        import csv
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".csv", encoding="utf-8", newline="", delete=False) as handle:
            writer = csv.writer(handle)
            for row in rows:
                writer.writerow(row)
            path = handle.name
        out = StringIO()
        call_command("seed_staff_roster", file=path, org=self.org.slug, stdout=out, **options)
        return out.getvalue()

    def test_a_staff_role_is_not_glued_to_a_student_only_account(self):
        """Yalnız tələbə hesabı tapılırsa heyət rolu AVTOMATİK verilmir."""
        student = self._member("sr_student", "Günay", "Qasımova", "student")
        rows = [("Elmi Kitabxana", ""), ("Qasımova Günay Elşən", "Kitabxanaçı")]
        output = self._run(rows)
        self.assertIn("ÇOX MƏNALI", output)
        self.assertIn("yalnız TƏLƏBƏ hesabı", output)
        with bypass_rls():
            self.assertEqual(Membership.objects.filter(user=student, organization=self.org).count(), 1)

    def test_two_staff_accounts_with_the_same_name_are_refused(self):
        self._member("sr_a", "Rəşad", "Bağırov", "teacher")
        self._member("sr_b", "Rəşad", "Bağırov", "teacher")
        rows = [("Prorektor", ""), ("Bağırov Rəşad Hüseynqulu", "İcraçı prorektor")]
        output = self._run(rows)
        self.assertIn("birdən çox HEYƏT hesabı", output)

    def test_a_name_repeated_in_the_file_is_refused(self):
        rows = [
            ("Arxiv şöbəsi", ""),
            ("Vəliyeva Fəridə Rəsul", "Müdir"),
            ("Filologiya məktəbi", ""),
            ("Vəliyeva Fəridə Rəsul", "Müavin"),
        ]
        output = self._run(rows)
        self.assertIn("siyahıda eyni ad-soyad", output)

    def test_a_single_staff_account_wins_over_a_namesake_student(self):
        """Tələbə + heyət cütlüyündə HEYƏT hesabı seçilir (birmənalıdır)."""
        self._member("sr_stud2", "Nigar", "Babayeva", "student")
        staff = self._member("sr_staff2", "Nigar", "Babayeva", "teacher")
        rows = [("Prorektor", ""), ("Babayeva Nigar Mais", "Elmi işlər üzrə")]
        output = self._run(rows, apply=True)
        self.assertNotIn("ÇOX MƏNALI", output)
        with bypass_rls():
            self.assertTrue(
                Membership.objects.filter(user=staff, organization=self.org, role__name="vice_rector").exists()
            )
