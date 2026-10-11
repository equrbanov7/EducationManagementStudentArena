"""«Forma 7» ``--create-missing`` — «hesab yoxdur» sətirlərinə FİN-siz müəllim hesabı (sahib 2026-10-11).

Kilidlənən qaydalar:

* YALNIZ ``not_found`` sətirlər; çox mənalı / ata adı fərqli / oxşar / yalnız tələbə — yaradılmır;
* hesab: ``ad.soyad`` (tutulubsa ``ad.soyad2``), FİN ``NULL`` (iki FİN-siz hesab toqquşmur), placeholder e-poçt,
  ilk girişdə öz parolu; kafedra üzvlüyü (tanınmayan kafedra → təşkilat səviyyəli), elmi ad/dərəcə, yük profili;
  eyni ad + ata adı iki kafedrada → BİR hesab, iki üzvlük, ştat cəmlənir;
* defolt dry-run heç nə yaratmır; təkrar ``--apply`` yeni hesab yaratmır; ``undo`` toxunulmamış hesabı silir,
  istifadə olunmuşu bloklayır; parollar yalnız ``--credentials-out`` (0600) faylına düşür.
"""

from __future__ import annotations

import csv
import os
import stat
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.accounts.services.teacher_roster import apply as roster_apply
from apps.accounts.services.teacher_roster.create import plan_new_accounts
from apps.accounts.services.teacher_roster.parsing import parse_sheet_rows
from apps.accounts.services.teacher_roster.plan import build_plan
from apps.organizations.models import Membership
from apps.workload.models import TeacherWorkloadProfile
from core.rls import bypass_rls

from .people_fixture import make_user
from .test_teacher_roster_2026_10_11 import SHEET, _RosterBase

User = get_user_model()

#: Baza vərəqi + yeni adamlar: «Tapılmaz Heçkim» iki kafedrada (bir hesab), «Yenisov Birinci» (adı tutulub →
#: ``birinci.yenisov2``), «Unikal Kimsə» sistemdə olmayan kafedrada (təşkilat səviyyəli üzvlük).
SHEET_NEW = [
    *SHEET[:11],
    (7, "Tapılmaz Heçkim Heçnə oğlu", "dosent, f.ü.f.d", "0,5 ştat"),
    (8, "Yenisov Birinci Ata", "Professor", "s/h"),
    *SHEET[11:],
    ("Marketinq kafedrası", None, None, None),
    ("N", "Soyad, ad, ata adı", "Elmi dərəcə", "Ştat vahidi"),
    (1, "Unikal Kimsə Ata", "-", "Ştat"),
    (None, "Cəmi", None, None),
]
REASON = "Forma 7 aktiv müəllim siyahısı — test tətbiqi"
NEW_USERNAMES = {"heckim.tapilmaz", "birinci.yenisov2", "kimse.unikal"}


class _CreateBase(_RosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.taken = make_user("birinci.yenisov", first="Başqa", last="Adam")  # üzvlüyü yoxdur

    def plan(self, **kwargs):
        with bypass_rls():
            plan = build_plan(
                self.org,
                parse_sheet_rows(SHEET_NEW),
                academic_year="2026/2027",
                protect_ids={self.explicit.pk},
                **kwargs,
            )
            plan.new_accounts = plan_new_accounts(plan)
        return plan

    def _execute(self, **kwargs):
        with bypass_rls():
            return roster_apply.execute(self.plan(), actor=self.owner, reason=REASON, **kwargs)

    def _created(self):
        return User.objects.filter(username__in=NEW_USERNAMES)


class CreateMissingServiceTest(_CreateBase):
    def test_plan_only_not_found_rows_and_previews_usernames(self):
        plan = self.plan()
        self.assertEqual({item.username for item in plan.new_accounts}, NEW_USERNAMES)
        merged = next(item for item in plan.new_accounts if item.username == "heckim.tapilmaz")
        self.assertEqual(merged.chair_ids, [self.chair_a.pk, self.chair_b.pk])
        self.assertEqual((merged.title, merged.degree, merged.position), ("docent", "phd", "dosent"))
        self.assertEqual((merged.staff_fraction, merged.is_external), (Decimal("1.5"), False))
        self.assertFalse(self._created().exists())  # plan YAZMIR

    def test_apply_creates_fin_less_teachers_then_is_idempotent_and_undoable(self):
        before = User.objects.count()
        result = self._execute()
        self.assertEqual({entry["username"] for entry in result["created"]}, NEW_USERNAMES)
        self.assertEqual(result["credentials"], [])  # parol saxlanmır
        self.assertEqual(User.objects.count(), before + 3)

        users = {user.username: user for user in self._created().select_related("profile")}
        for user in users.values():
            profile = user.profile
            self.assertIsNone(profile.fin)  # iki+ FİN-siz hesab eyni qaçışda — unikal indeks pozulmur
            self.assertTrue(user.email.endswith("@placeholder.invalid"))
            self.assertFalse(user.has_usable_password())
            self.assertTrue(profile.password_change_required)
            self.assertEqual(profile.role, "teacher")
        merged = users["heckim.tapilmaz"]
        self.assertEqual(
            (merged.last_name, merged.first_name, merged.profile.patronymic), ("Tapılmaz", "Heçkim", "Heçnə")
        )
        self.assertEqual((merged.profile.academic_title, merged.profile.academic_degree), ("docent", "phd"))
        with bypass_rls():
            scopes = set(
                Membership.objects.filter(user=merged, role__name="teacher", is_active=True).values_list(
                    "scope_unit_id", flat=True
                )
            )
            self.assertEqual(scopes, {self.chair_a.pk, self.chair_b.pk})
            org_level = Membership.objects.get(user=users["kimse.unikal"], role__name="teacher")
            self.assertIsNone(org_level.scope_unit_id)
            workload = TeacherWorkloadProfile.objects.get(teacher=merged, academic_year="2026/2027")
            self.assertEqual((workload.position, workload.staff_fraction), ("dosent", Decimal("1.50")))
            hourly = TeacherWorkloadProfile.objects.get(teacher=users["birinci.yenisov2"])
            self.assertEqual((hourly.position, hourly.is_external), ("professor", True))

        # Çox mənalı / ata adı fərqli / oxşar / tələbə sətirləri üçün hesab YARANMIR.
        self.assertEqual(User.objects.filter(last_name="Quliyev").count(), 1)
        self.assertEqual(User.objects.filter(last_name="Babayev").count(), 1)
        self.assertEqual(User.objects.filter(last_name="Yeniyev").count(), 0)
        self.assertEqual(User.objects.filter(last_name="Məmmədova").count(), 2)

        again = self._execute()  # yaradılanlar artıq «tapıldı» → yenidən yaradılmır
        self.assertEqual(again["created"], [])
        self.assertEqual(User.objects.count(), before + 3)

        with bypass_rls():
            undone = roster_apply.undo(result["batch"], actor=self.owner)
            self.assertEqual(sorted(undone["created"]["deleted"]), sorted(e["user"] for e in result["created"]))
            self.assertFalse(TeacherWorkloadProfile.objects.filter(teacher_id=merged.pk).exists())
            second = roster_apply.undo(result["batch"], actor=self.owner)
        self.assertEqual(second["created"], {"deleted": [], "deactivated": [], "kept": []})
        self.assertFalse(self._created().exists())
        self.assertTrue(User.objects.filter(pk=self.taken.pk).exists())

    def test_undo_blocks_instead_of_deleting_a_used_account(self):
        result = self._execute()
        used = User.objects.get(username="kimse.unikal")
        User.objects.filter(pk=used.pk).update(last_login=timezone.now())
        with bypass_rls():
            undone = roster_apply.undo(result["batch"], actor=self.owner)
        self.assertEqual(undone["created"]["deactivated"], [used.pk])
        self.assertEqual(len(undone["created"]["deleted"]), 2)
        used.refresh_from_db()
        self.assertFalse(used.is_active)
        self.assertIn(f"[{result['batch']}]", used.profile.block_reason)


class CreateMissingCommandTest(_CreateBase):
    def _xlsx(self):
        import openpyxl

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Aktiv - Passiv"
        for row in SHEET_NEW:
            sheet.append(list(row))
        handle = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        workbook.save(handle.name)
        self.addCleanup(Path(handle.name).unlink)
        return handle.name

    def test_dry_run_creates_nothing_and_keeps_names_out_of_stdout(self):
        path = self._xlsx()
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.md"
            out = StringIO()
            call_command(
                "reconcile_teacher_roster",
                path,
                organization="roster-univ",
                create_missing=True,
                report=str(report),
                stdout=out,
            )
            text = report.read_text(encoding="utf-8")
        self.assertIn("YENİ HESAB yaradılacaq (FİN-siz, «hesab yoxdur»): 3", out.getvalue())
        self.assertNotIn("Tapılmaz", out.getvalue())
        self.assertNotIn("heckim.tapilmaz", out.getvalue())
        self.assertIn("yaradılacaq müəllim hesabı (FİN-siz): **3**", text)
        self.assertIn("`heckim.tapilmaz`", text)
        self.assertLess(text.index("## Yeni hesablar"), text.index("## Nümunələr"))
        self.assertLess(text.index("## Nümunələr"), text.index("`heckim.tapilmaz`"))  # adlar loga düşməyən hissədə
        self.assertFalse(self._created().exists())

    def test_apply_with_credentials_file_and_gates(self):
        path = self._xlsx()
        with self.assertRaises(CommandError):
            call_command("reconcile_teacher_roster", path, organization="roster-univ", credentials_out="/tmp/x.csv")
        with tempfile.TemporaryDirectory() as tmp:
            creds = Path(tmp) / "creds.csv"
            out = StringIO()
            call_command(
                "reconcile_teacher_roster",
                path,
                organization="roster-univ",
                create_missing=True,
                apply=True,
                skip_blocks=True,
                reason=REASON,
                credentials_out=str(creds),
                i_know_this_is_production=True,
                stdout=out,
            )
            self.assertEqual(stat.S_IMODE(os.stat(creds).st_mode), 0o600)
            with creds.open(encoding="utf-8") as handle:
                rows = list(csv.reader(handle))[1:]
        self.assertEqual({row[0] for row in rows}, NEW_USERNAMES)
        for username, _name, _chair, password in rows:
            self.assertNotIn(password, out.getvalue())
            self.assertTrue(User.objects.get(username=username).check_password(password))
        self.assertIn("yeni hesab 3", out.getvalue())
        self.gone.refresh_from_db()
        self.assertTrue(self.gone.is_active)  # --skip-blocks
