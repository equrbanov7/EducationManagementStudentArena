"""`seed_staff_roster` — eyniadlılıq qapısı (2026-09-06 klon tapıntısı + yeniləmə).

NİYƏ. Komanda mövcud hesabı YALNIZ ad+soyada görə tapırdı. Klonda 463 eyni
ad-soyad qrupu var; nəticədə 21 heyət rolu SƏHV hesaba yapışmışdı — o cümlədən
`vice_rector` bir TƏLƏBƏ hesabına. Prod-da eyni qaçış tələbəyə prorektor
səlahiyyəti verərdi.

2026-09-06 sahib qərarı («bəziləri yeni ola bilər, hesabı yoxdusa yarat»)
qapının əhatəsini daraltdı: YALNIZ birdən çox HEYƏT hesabı adaşlığı fail-closed
qalır (kimin kim olduğunu bilmək mümkün deyil, TƏXMİN edilmir). Digər iki hal
(yalnız tələbə/məzun adaşı, fayl-daxili adaşlıq) artıq ATLANMIR — YENİ hesab
yaradılır və hesabatda ayrıca qeyd olunur ki, əl ilə birləşdirmə lazım ola bilər.
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
    """Dry-run/apply: yalnız birdən-çox-HEYƏT-adaşlığı «çox mənalı» sayılır."""

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

    def test_a_new_account_is_created_for_a_student_only_namesake(self):
        """Yalnız tələbə hesabı tapılırsa: tələbə hesabına TOXUNULMUR, YENİ
        heyət hesabı yaradılır (2026-09-06 sahib qərarı: «yeni ola bilər»)."""
        student = self._member("sr_student", "Günay", "Qasımova", "student")
        rows = [("Elmi Kitabxana", ""), ("Qasımova Günay Elşən", "Kitabxanaçı")]
        before_user_count = User.objects.count()
        output = self._run(rows, apply=True)
        # Fail-closed «çox mənalı» bölməsi bura aid deyil (yalnız staff-staff adaşlığı) —
        # amma hesabat YENİ hesabın adaş-tapılmış şəraitdə yarandığını aydın qeyd edir.
        self.assertNotIn("ÇOX MƏNALI", output)
        self.assertIn("YENİ HESAB", output)
        self.assertIn("yalnız tələbə/məzun hesabı tapıldı", output)
        with bypass_rls():
            # Tələbə hesabı DƏYİŞMƏYİB — hələ də tək (tələbə) üzvlüyü var,
            # `staff_position` yazılmayıb (komanda ona TOXUNMADI).
            self.assertEqual(Membership.objects.filter(user=student, organization=self.org).count(), 1)
            student.refresh_from_db()
            self.assertEqual(student.profile.staff_position, "")
            self.assertEqual(User.objects.count(), before_user_count + 1)
            new_membership = (
                Membership.objects.filter(organization=self.org).exclude(user=student).order_by("-id").first()
            )
            self.assertIsNotNone(new_membership)
            self.assertNotEqual(new_membership.user_id, student.id)

    def test_two_staff_accounts_with_the_same_name_are_refused(self):
        """Birdən çox HEYƏT hesabı adaşlığı hələ də fail-closed atlanır."""
        self._member("sr_a", "Rəşad", "Bağırov", "teacher")
        self._member("sr_b", "Rəşad", "Bağırov", "teacher")
        rows = [("Prorektor", ""), ("Bağırov Rəşad Hüseynqulu", "İcraçı prorektor")]
        before_membership_count = Membership.objects.count()
        output = self._run(rows, apply=True)
        self.assertIn("birdən çox HEYƏT hesabı", output)
        # Hesabat namizədləri (username + e-poçt) göstərir ki, sahib saniyələr
        # içində əl ilə həll edə bilsin — üçüncü dublikat hesab YARADILMIR.
        self.assertIn("sr_a", output)
        self.assertIn("sr_b", output)
        with bypass_rls():
            self.assertEqual(Membership.objects.count(), before_membership_count)

    def test_repeating_the_run_does_not_duplicate_namesake_accounts(self):
        """İDEMPOTENTLİK: adaş sətirlər ikinci qaçışda TƏZƏ hesab yaratmır.

        Sətrin öz hesabı bölməyə görə tanınır (üzvlüyün `scope_unit`-i),
        yoxsa hər `--apply` eyni iki adama yeni hesab açardı.
        """
        from apps.organizations.models import OrgUnit
        from core.constants import OrgUnitType

        with bypass_rls():
            for name, slug in (("Arxiv şöbəsi", "sr-arxiv"), ("Filologiya məktəbi", "sr-filologiya")):
                OrgUnit.objects.create(
                    organization=self.org, name=name, slug=slug, unit_type=OrgUnitType.DEPARTMENT
                )
        rows = [
            ("Arxiv şöbəsi", ""),
            ("Vəliyeva Fəridə Rəsul", "Müdir"),
            ("Filologiya məktəbi", ""),
            ("Vəliyeva Fəridə Rəsul", "Müavin"),
        ]
        self._run(rows, apply=True)
        with bypass_rls():
            after_first = User.objects.filter(first_name="Fəridə", last_name="Vəliyeva").count()
        self.assertEqual(after_first, 2)

        self._run(rows, apply=True)
        with bypass_rls():
            after_second = User.objects.filter(first_name="Fəridə", last_name="Vəliyeva").count()
        self.assertEqual(after_second, 2, "ikinci qaçış yeni hesab yaratmamalıdır")

    def test_a_name_repeated_in_the_file_creates_two_distinct_accounts(self):
        """Fayl-daxili adaşlıq = iki fərqli insan → hər sətrə ayrı hesab,
        `claim_username` istifadəçi adlarını dublikatlaşdırmır."""
        rows = [
            ("Arxiv şöbəsi", ""),
            ("Vəliyeva Fəridə Rəsul", "Müdir"),
            ("Filologiya məktəbi", ""),
            ("Vəliyeva Fəridə Rəsul", "Müavin"),
        ]
        output = self._run(rows, apply=True)
        self.assertNotIn("ÇOX MƏNALI", output)
        self.assertIn("siyahıda eyni ad-soyad", output)
        with bypass_rls():
            memberships = Membership.objects.filter(
                organization=self.org, user__first_name__iexact="Fəridə", user__last_name__iexact="Vəliyeva"
            ).select_related("user")
            self.assertEqual(memberships.count(), 2)
            usernames = {membership.user.username for membership in memberships}
            self.assertEqual(len(usernames), 2)  # `claim_username` fərqli ad verib

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
