"""«Forma 7» müəllim siyahısının tutuşdurulması (sahib 2026-10-11).

Kilidlənən qaydalar:

* oxuma: kafedra blokları, «Cəmi», ad (oğlu/qızı, mötərizə, «Ad Soyad»), elmi ad/dərəcə, ştat — səliqəsiz
  yazılışlar kanonik formaya düşür, tanınmayan dəyər uydurulmur;
* tutuşdurma: dəqiq / yazılış fərqi / tərs sıra / ata adı fərqli / çox mənalı / tələbə / yoxdur;
* qoruma: inzibati rol (başqa təşkilatda da), sahib, superuser, ``--protect`` — HEÇ VAXT bloklanmır;
  sətrin istənilən namizədi (çox mənalı, ata adı fərqli) da bloklanmır;
* tətbiq: profil + yük profili + mövcud blok servisi (səbəb kodu, müraciət, paket markeri), audit manifesti;
  təkrar tətbiq idempotentdir; ``undo`` hamısını qaytarır və təkrar ``undo`` zərərsizdir;
* əmr: defolt dry-run, ``--apply`` səbəbsiz / markersiz bazada rədd edilir.
"""

from __future__ import annotations

import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.accounts.services.teacher_roster import apply as roster_apply
from apps.accounts.services.teacher_roster.matching import chair_score, match_chairs
from apps.accounts.services.teacher_roster.parsing import (
    parse_name,
    parse_rate,
    parse_sheet_rows,
    parse_title_degree,
)
from apps.accounts.services.teacher_roster.plan import build_plan
from apps.audit.models import AuditLog
from apps.organizations.models import Organization, OrgUnit
from apps.workload.models import TeacherWorkloadProfile
from core.constants import OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

from .people_fixture import add_membership, make_role, make_user

SHEET = [
    ("Qərbi Kaspi Universitetinin", None, None, None),
    ("2026/2027-ci tədris ili üçün dərs yükü haqqında", None, None, None),
    ("N", "Soyad, ad, ata adı", "Elmi dərəcə", "Ştat vahidi"),
    ("Riyaziyyat kafedrası", None, None, None),
    ("N", "Soyad, ad, ata adı", "Elmi dərəcə", "Ştat vahidi"),
    (1, "Əliyev Elvin Səməd oğlu", "Kafedra müdiri,dosent.", "0,5 ştat"),
    (2, "Leyla Hüseynova Elmar", "f.e.d. professor", "Ştat"),
    (3, "Quliyev Anar Rauf", "müəllim", "s/h"),
    (4, "Məmmədova Aysel Kamal", "b,ü,f,d", "Tam"),
    (5, "Babayev Bəxtiyar Oruc", "doktorant", "S/H"),
    (6, "Yeniyev Yeni Yenioğlu", "-", "ştat"),
    (None, "Cəmi", None, None),
    ("Fizika kafedrası", None, None, None),
    ("N", "Soyad, ad", "Elmi dərəcə", "Ştat vahidi"),
    (1, "Kərimova Nərgiz (baş müəllim)", None, "əvəzçi"),
    (2, "Tapılmaz Heçkim Heçnə", "-", "ştat"),
    (None, "Cəmi", None, None),
]


class ParsingTest(SimpleTestCase):
    def test_sheet_blocks_rows_and_year(self):
        roster = parse_sheet_rows(SHEET)
        self.assertEqual(roster.academic_year, "2026/2027")
        self.assertEqual(roster.chairs, ["Riyaziyyat kafedrası", "Fizika kafedrası"])
        self.assertEqual(len(roster.rows), 8)
        self.assertEqual(roster.skipped, [])
        self.assertEqual({row.chair for row in roster.rows[-1:]}, {"Fizika kafedrası"})

    def test_names(self):
        name = parse_name("Əliyev Elvin Səməd oğlu")
        self.assertEqual((name.last, name.first, name.patronymic), ("Əliyev", "Elvin", "Səməd"))
        self.assertEqual(parse_name("Qazı-zadə Elnarə Adil q.").patronymic_key, "adil")
        two = parse_name("Kərimova Nərgiz (baş müəllim)")
        self.assertTrue(two.two_part)
        self.assertEqual(two.note, "baş müəllim")
        self.assertIsNone(parse_name("Cəmi"))

    def test_title_and_degree(self):
        cases = {
            "Professor,f.ü.f.d": ("professor", "phd"),
            "Kafedra müdiri,dosent.": ("docent", None),
            "s.e.f.d.,dos": ("docent", "phd"),
            "T.ü.e.d. prof.": ("professor", "dsc"),
            "f-r.e.d. professor": ("professor", "dsc"),
            "i.e.n, baş müəllim": ("senior_teacher", "phd"),
            "b,ü,f, d Dosent": ("docent", "phd"),
            "Memarlıq üzrə elmlər doktoru": (None, "dsc"),
            "Sənətşünaslıq üzrə fəlsəfə doktoru": (None, "phd"),
            "müəllim": ("teacher", None),
            "doktorant": (None, None),
            "dekan QKU": (None, None),
            "-": (None, None),
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_title_degree(raw), expected)
        self.assertEqual(parse_title_degree("", "baş müəllim"), ("senior_teacher", None))

    def test_rates(self):
        full = ("Ştat", "ştat", "Tam", "1,0 ştat", "Ştat , (k.m)", "Ştat (dekan)")
        half = ("0,5 ştat", "0.5 ştat", "0,5 Ştat", "0.5", "yarım ştat", "yarımştat", "y/ş", "Y/ştat Kafedra.müd.")
        hourly = ("s/h", "S/h", "s.h", "S/H", "S\\H", "Saat hesabı", "saat hesabı", "Saathesabı")
        for raw in full:
            self.assertEqual((parse_rate(raw).kind, parse_rate(raw).fraction), ("full", Decimal("1")), raw)
        for raw in half:
            self.assertEqual((parse_rate(raw).kind, parse_rate(raw).fraction), ("half", Decimal("0.5")), raw)
        for raw in hourly:
            rate = parse_rate(raw)
            self.assertEqual((rate.kind, rate.fraction, rate.external), ("hourly", Decimal("0"), True), raw)
        for raw in ("əvəzçi", "", None):
            self.assertEqual(parse_rate(raw).kind, "unknown")

    def test_chair_names_are_fuzzy_but_reported(self):
        units = [(1, "İngilis dili və tərcümə"), (2, "İngilis dilçiliyi və ədəbiyyatı"), (3, "İngilis dili mərkəzi")]
        mapped = match_chairs(["İngilis dili və ədəbiyyatı kafedrası", "Marketinq kafedrası"], units)
        self.assertEqual(mapped["İngilis dili və ədəbiyyatı kafedrası"]["unit"], (2, "İngilis dilçiliyi və ədəbiyyatı"))
        self.assertIsNone(mapped["Marketinq kafedrası"]["unit"])
        forced = match_chairs(["Marketinq kafedrası"], units, {"Marketinq kafedrası": "İngilis dili mərkəzi"})
        self.assertEqual(forced["Marketinq kafedrası"]["source"], "override")
        self.assertGreater(chair_score("Tarix kafedrası", "Tarix və fəlsəfə"), 0.5)


class _RosterBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        cls.owner = make_user("rs_owner", first="Sahib", last="Sahibov")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Roster Univ",
                slug="roster-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.other_org = Organization.objects.create(
                name="Other Univ",
                slug="other-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
            )
            faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="rs-fak", unit_type=OrgUnitType.FACULTY
            )
            cls.chair_a = OrgUnit.objects.create(
                organization=cls.org, name="Riyaziyyat", slug="rs-a", unit_type=OrgUnitType.CHAIR, parent=faculty
            )
            cls.chair_b = OrgUnit.objects.create(
                organization=cls.org, name="Fizika", slug="rs-b", unit_type=OrgUnitType.CHAIR, parent=faculty
            )
            teacher = make_role(cls.org, "teacher", level=50, scope_type=RoleScopeType.COURSE, permissions=[])
            dean = make_role(cls.org, "dean", level=80, scope_type=RoleScopeType.UNIT, permissions=[])
            student = make_role(cls.org, "student", level=10, scope_type=RoleScopeType.UNIT, permissions=[])
            rim = make_role(cls.other_org, "rim_staff", level=60, scope_type=RoleScopeType.ORGANIZATION, permissions=[])

            def teacher_in(user, unit):
                add_membership(cls.org, user, teacher, unit=unit)
                return user

            cls.matched = teacher_in(
                make_user("rs_matched", first="Elvin", last="Əliyev", patronymic="Səməd oğlu"), cls.chair_b
            )
            cls.swapped = teacher_in(
                make_user("rs_swapped", first="Leyla", last="Hüseynova", patronymic="Elmar"), cls.chair_a
            )
            cls.conflict = teacher_in(
                make_user("rs_conflict", first="Anar", last="Quliyev", patronymic="Vaqif"), cls.chair_a
            )
            cls.dup_a = teacher_in(
                make_user("rs_dup_a", first="Aysel", last="Məmmədova", patronymic="Kamal"), cls.chair_a
            )
            cls.dup_b = teacher_in(
                make_user("rs_dup_b", first="Aysel", last="Məmmədova", patronymic="Kamal"), cls.chair_b
            )
            cls.partial = teacher_in(make_user("rs_partial", first="Nərgiz", last="Kərimova"), cls.chair_b)
            # Adı natamam hesab (soyad boş) — «Yeniyev Yeni» sətrinin özü ola bilər, bloklanmamalıdır.
            cls.half_named = teacher_in(make_user("rs_half", first="Yeni", last=""), cls.chair_a)
            cls.pupil = make_user("rs_pupil", first="Bəxtiyar", last="Babayev", patronymic="Oruc")
            add_membership(cls.org, cls.pupil, student, unit=cls.chair_a)

            cls.gone = teacher_in(make_user("rs_gone", first="Getdi", last="Getdiyev", patronymic="Ata"), cls.chair_a)
            cls.dean = teacher_in(make_user("rs_dean", first="Dekan", last="Dekanov"), cls.chair_a)
            add_membership(cls.org, cls.dean, dean, unit=faculty)
            cls.foreign = teacher_in(make_user("rs_foreign", first="Rim", last="Rimov"), cls.chair_a)
            add_membership(cls.other_org, cls.foreign, rim)
            cls.owner_teacher = teacher_in(cls.owner, cls.chair_a)
            cls.root = teacher_in(make_user("rs_root", first="Kök", last="Köklü"), cls.chair_a)
            user_model.objects.filter(pk=cls.root.pk).update(is_superuser=True)
            cls.explicit = teacher_in(make_user("rs_explicit", first="Qoru", last="Qorunan"), cls.chair_a)
            cls.matched.profile.academic_title = "teacher"
            cls.matched.profile.save(update_fields=["academic_title"])

    def plan(self, **kwargs):
        with bypass_rls():
            return build_plan(
                self.org, parse_sheet_rows(SHEET), academic_year="2026/2027", protect_ids={self.explicit.pk}, **kwargs
            )


class MatchingAndProtectionTest(_RosterBase):
    def test_statuses(self):
        plan = self.plan()
        by_seq = {
            (match.row.chair[0].replace("R", "A").replace("F", "B"), match.row.seq): match for match in plan.matches
        }
        self.assertEqual(by_seq[("A", "1")].status, "matched")
        self.assertEqual(by_seq[("A", "1")].account.user_id, self.matched.pk)
        self.assertEqual(by_seq[("A", "2")].status, "fuzzy")  # «Ad Soyad Ata» sırası
        self.assertEqual(by_seq[("A", "2")].account.user_id, self.swapped.pk)
        self.assertEqual(by_seq[("A", "3")].status, "conflict")  # ata adı fərqli
        self.assertEqual(by_seq[("A", "4")].status, "matched")  # eyni kafedra üstündür
        self.assertEqual(by_seq[("A", "4")].account.user_id, self.dup_a.pk)
        self.assertEqual(by_seq[("A", "5")].status, "student_only")
        self.assertEqual(by_seq[("A", "6")].status, "review")  # adı natamam hesab namizəddir
        self.assertEqual([account.user_id for account in by_seq[("A", "6")].candidates], [self.half_named.pk])
        self.assertEqual(by_seq[("B", "2")].status, "not_found")
        self.assertEqual(by_seq[("B", "1")].status, "matched")
        self.assertIn("patronymic_unverified", by_seq[("B", "1")].flags)

    def test_user_plan_values_and_chair_mismatch_is_only_reported(self):
        plan = self.plan()
        matched = plan.users[self.matched.pk]
        self.assertEqual(matched.profile_changes, {"academic_title": ("teacher", "docent")})
        self.assertEqual(
            (matched.position, matched.staff_fraction, matched.is_external), ("dosent", Decimal("0.5"), False)
        )
        self.assertIn("chair_mismatch", matched.flags)
        swapped = plan.users[self.swapped.pk]
        self.assertEqual(swapped.profile_changes["academic_degree"], ("", "dsc"))
        partial = plan.users[self.partial.pk]
        self.assertEqual(partial.title, "senior_teacher")  # mötərizədəki «(baş müəllim)»
        self.assertIsNone(partial.staff_fraction)  # «əvəzçi» — uydurulmur

    def test_only_unlisted_unprotected_teachers_are_blocked(self):
        plan = self.plan()
        self.assertEqual([account.user_id for account in plan.block], [self.gone.pk])
        protected = {account.user_id: reasons for account, reasons in plan.protected}
        self.assertIn("staff_role:dean", protected[self.dean.pk])
        self.assertIn("staff_role:rim_staff", protected[self.foreign.pk])  # başqa təşkilatdakı rol
        self.assertIn("org_owner", protected[self.owner.pk])
        self.assertIn("superuser", protected[self.root.pk])
        self.assertIn("explicit", protected[self.explicit.pk])
        for candidate in (self.conflict, self.dup_b):  # namizəd olan heç vaxt bloklanmır
            self.assertIn(candidate.pk, plan.candidate_ids)
            self.assertNotIn(candidate.pk, protected)
        self.assertNotIn(self.pupil.pk, [account.user_id for account in plan.block])
        self.assertIn(self.half_named.pk, plan.candidate_ids)


class ApplyUndoTest(_RosterBase):
    REASON = "Forma 7 aktiv müəllim siyahısı — test tətbiqi"

    def _execute(self):
        with bypass_rls():
            return roster_apply.execute(self.plan(), actor=self.owner, reason=self.REASON)

    def test_apply_is_audited_idempotent_and_undoable(self):
        result = self._execute()
        self.gone.refresh_from_db()
        profile = self.gone.profile
        self.assertFalse(self.gone.is_active)
        self.assertEqual((profile.block_reason_code, profile.block_contact_code), ("employment_ended", "hr"))
        self.assertIn(f"[{result['batch']}]", profile.block_reason)
        self.assertEqual(result["blocked"], [self.gone.pk])
        self.matched.profile.refresh_from_db()
        self.assertEqual(self.matched.profile.academic_title, "docent")
        with bypass_rls():
            workload = TeacherWorkloadProfile.objects.get(organization=self.org, teacher=self.matched)
            self.assertEqual(
                (workload.position, workload.staff_fraction, workload.is_external), ("dosent", Decimal("0.50"), False)
            )
            hourly = TeacherWorkloadProfile.objects.filter(teacher=self.conflict).exists()
            self.assertFalse(hourly)  # ata adı fərqli sətir heç nə yazmır
            self.assertTrue(
                AuditLog.objects.filter(resource_type=roster_apply.BATCH_RESOURCE, resource_id=result["batch"]).exists()
            )

        again = self._execute()  # idempotent
        self.assertEqual((again["profiles"], again["workload"], again["blocked"]), ([], [], []))

        with bypass_rls():
            undone = roster_apply.undo(result["batch"], actor=self.owner)
            self.assertEqual(undone["unblocked"], [self.gone.pk])
            self.assertFalse(TeacherWorkloadProfile.objects.filter(teacher=self.matched).exists())
            second = roster_apply.undo(result["batch"], actor=self.owner)  # təkrar undo zərərsizdir
        self.assertEqual(second["unblocked"], [])
        self.gone.refresh_from_db()
        self.matched.profile.refresh_from_db()
        self.assertTrue(self.gone.is_active)
        self.assertEqual(self.gone.profile.block_reason_code, "")
        self.assertEqual(self.matched.profile.academic_title, "teacher")

    def test_undo_leaves_accounts_blocked_for_another_reason(self):
        result = self._execute()
        from django.contrib.auth import get_user_model

        from apps.accounts.models import UserProfile

        UserProfile.objects.filter(user=self.gone).update(block_reason="Başqa səbəb", block_reason_code="discipline")
        with bypass_rls():
            undone = roster_apply.undo(result["batch"], actor=self.owner)
        self.assertEqual(undone["skipped"], [self.gone.pk])
        self.assertFalse(get_user_model().objects.get(pk=self.gone.pk).is_active)

    def test_reason_is_required(self):
        with self.assertRaises(roster_apply.RosterError):
            with bypass_rls():
                roster_apply.execute(self.plan(), actor=self.owner, reason="qısa")


class CommandTest(_RosterBase):
    def _xlsx(self):
        import openpyxl

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Aktiv - Passiv"
        for row in SHEET:
            sheet.append(list(row))
        handle = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        workbook.save(handle.name)
        self.addCleanup(Path(handle.name).unlink)
        return handle.name

    def test_dry_run_writes_report_and_changes_nothing(self):
        path = self._xlsx()
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.md"
            out = StringIO()
            call_command("reconcile_teacher_roster", path, organization="roster-univ", report=str(report), stdout=out)
            text = report.read_text(encoding="utf-8")
        self.assertIn("DRY-RUN", out.getvalue())
        self.assertIn("hesab yoxdur | 1", text)
        self.gone.refresh_from_db()
        self.assertTrue(self.gone.is_active)

    def test_apply_gates_then_apply_and_undo(self):
        path = self._xlsx()
        with self.assertRaises(CommandError):  # test bazasında repetisiya markeri yoxdur
            call_command(
                "reconcile_teacher_roster", path, organization="roster-univ", apply=True, reason=ApplyUndoTest.REASON
            )
        with self.assertRaises(CommandError):  # səbəb qısadır
            call_command(
                "reconcile_teacher_roster",
                path,
                organization="roster-univ",
                apply=True,
                reason="qısa",
                i_know_this_is_production=True,
                stdout=StringIO(),
            )
        out = StringIO()
        call_command(
            "reconcile_teacher_roster",
            path,
            organization="roster-univ",
            apply=True,
            reason=ApplyUndoTest.REASON,
            i_know_this_is_production=True,
            stdout=out,
        )
        self.gone.refresh_from_db()
        self.assertFalse(self.gone.is_active)
        batch = out.getvalue().split("--undo ")[-1].strip()
        call_command(
            "reconcile_teacher_roster",
            organization="roster-univ",
            undo=batch,
            i_know_this_is_production=True,
            stdout=StringIO(),
        )
        self.gone.refresh_from_db()
        self.assertTrue(self.gone.is_active)
