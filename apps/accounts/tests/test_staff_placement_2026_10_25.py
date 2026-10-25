"""Heyət yerləşdirməsi + «Kafedra» seçicisinin tərifi (sahib 2026-10-25).

Kilidlənən qaydalar:

* kafedra = ``chair``; ``chair`` işlədən təşkilatda inzibati şöbə (``department``) kafedra seçicisinə DÜŞMÜR;
  ``chair`` işlətməyən (köhnə) təşkilatda ``department`` kafedra olaraq qalır;
* Forma 7-də başqa kafedrada olan müəllim → həmin kafedrada üzvlük + əsas kafedra ora keçir, artıq (yüksüz)
  kafedra üzvlüyü deaktiv olur; dekanın əsas (dekan) üzvlüyünə toxunulmur, ona ƏLAVƏ müəllim üzvlüyü verilir;
* yalnız deaktiv üzvlüyü qalmış hesab Forma 7 ilə tapılır və kafedraya qaytarılır;
* Forma 7-də olmayan, amma cari semestrdə jurnalı olan müəllim BLOKLANMIR; yüksüz olan bloklanır;
* tətbiq idempotentdir, ``undo`` vəziyyəti qaytarır; əmr defolt dry-run, adlı hesabat 0600.
"""

from __future__ import annotations

import io
import os
import stat
import tempfile
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

import openpyxl

from apps.accounts.services.people.lookups import _unit_options
from apps.accounts.services.staff_placement import apply as placement_apply
from apps.accounts.services.staff_placement import plan as placement_plan
from apps.accounts.services.staff_placement import sources as placement_sources
from apps.accounts.services.teacher_roster.parsing import parse_sheet_rows
from apps.accounts.services.teacher_roster.plan import build_plan
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.organizations.public import ORG_WIDE_SCOPE, kafedra_q, kafedra_unit_types, narrow_kafedra_rows
from apps.registrar.models import CourseOffering, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

from .people_fixture import add_membership, make_role, make_user

FORMA7 = [
    ("2026/2027-ci tədris ili üçün dərs yükü haqqında", None, None, None),
    ("Alfa kafedrası", None, None, None),
    ("N", "Soyad, ad, ata adı", "Elmi dərəcə", "Ştat vahidi"),
    (1, "Dekanov Dekan Dekanoviç", "dosent", "s/h"),
    (2, "Yatmışova Yuxu Oyaq", "müəllim", "ştat"),
    (None, "Cəmi", None, None),
    ("Beta kafedrası", None, None, None),
    ("N", "Soyad, ad, ata adı", "Elmi dərəcə", "Ştat vahidi"),
    (1, "Köçəriyev Köçən Köç", "müəllim", "ştat"),
    (2, "Yerindəyev Yer Yurd", "müəllim", "ştat"),
    (None, "Cəmi", None, None),
]


def _xlsx(rows) -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Aktiv - Passiv"
    for row in rows:
        sheet.append(list(row))
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


class _World(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("sp_owner", first="Sahib", last="Sahibov")
        cls.root = make_user("sp_root", first="Kök", last="Köklü")
        with bypass_rls():
            type(cls.root).objects.filter(pk=cls.root.pk).update(is_superuser=True)
            cls.org = Organization.objects.create(
                name="Placement Univ",
                slug="placement-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            unit = lambda name, kind, parent=None: OrgUnit.objects.create(  # noqa: E731
                organization=cls.org, name=name, slug=f"sp-{name.lower()}", unit_type=kind, parent=parent
            )
            cls.faculty = unit("Fakulte", OrgUnitType.FACULTY)
            cls.chair_a = unit("Alfa kafedrası", OrgUnitType.CHAIR, cls.faculty)
            cls.chair_b = unit("Beta kafedrası", OrgUnitType.CHAIR, cls.faculty)
            cls.office = unit("Elmi Kitabxana", OrgUnitType.DEPARTMENT)
            cls.group = unit("101", OrgUnitType.GROUP, cls.faculty)
            cls.teacher_role = make_role(
                cls.org, "teacher", level=50, scope_type=RoleScopeType.COURSE, permissions=["grade.input"]
            )
            dean_role = make_role(cls.org, "dean", level=80, scope_type=RoleScopeType.UNIT, permissions=[])

            cls.mover = make_user("sp_mover", first="Köçən", last="Köçəriyev", patronymic="Köç")
            add_membership(cls.org, cls.mover, cls.teacher_role, unit=cls.chair_a)
            cls.staying = make_user("sp_staying", first="Yer", last="Yerindəyev", patronymic="Yurd")
            add_membership(cls.org, cls.staying, cls.teacher_role, unit=cls.chair_b)
            cls.dean = make_user("sp_dean", first="Dekan", last="Dekanov", patronymic="Dekanoviç")
            add_membership(cls.org, cls.dean, dean_role, unit=cls.faculty)
            cls.dormant = make_user("sp_dormant", first="Yuxu", last="Yatmışova", patronymic="Oyaq")
            add_membership(cls.org, cls.dormant, cls.teacher_role, unit=cls.chair_b)
            Membership.objects.filter(user=cls.dormant).update(is_active=False)
            cls.gone = make_user("sp_gone", first="Getmiş", last="Getmişov", patronymic="Ata")
            add_membership(cls.org, cls.gone, cls.teacher_role, unit=cls.chair_a)
            cls.teaching = make_user("sp_teaching", first="Dərs", last="Deyən", patronymic="Ata")
            add_membership(cls.org, cls.teaching, cls.teacher_role, unit=cls.chair_a)
            Membership.objects.filter(organization=cls.org).update(is_primary=True)

            period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-15",
                end_date="2027-01-31",
                is_current=True,
            )
            subject = Subject.objects.create(organization=cls.org, code="SP101", name="Fənn")
            CourseOffering.objects.create(
                organization=cls.org, subject=subject, period=period, group=cls.group, instructor=cls.teaching
            )

    def sources(self):
        with bypass_rls():
            types = kafedra_unit_types(self.org)
            chairs = list(OrgUnit.objects.filter(organization=self.org, unit_type__in=types, is_active=True))
            result = placement_sources.Sources()
            placement_sources.read_forma7(_xlsx(FORMA7), chairs, {}, result)
            return result

    def plan(self):
        with bypass_rls():
            return placement_plan.build(self.org, self.sources(), academic_year="2026/2027")

    def membership(self, user, unit):
        with bypass_rls():
            return Membership.objects.filter(user=user, scope_unit=unit, role=self.teacher_role).first()


class KafedraTypesTest(_World):
    def test_office_is_not_a_kafedra_when_chairs_exist(self):
        with bypass_rls():
            self.assertEqual(kafedra_unit_types(self.org), (OrgUnitType.CHAIR,))
            names = set(OrgUnit.objects.filter(kafedra_q(), organization=self.org).values_list("name", flat=True))
            self.assertEqual(names, {"Alfa kafedrası", "Beta kafedrası"})
            options = _unit_options(self.org, ORG_WIDE_SCOPE, kafedra_unit_types(self.org))
        self.assertNotIn("Elmi Kitabxana", {item["text"] for item in options})
        self.assertEqual(len(options), 2)

    def test_legacy_org_keeps_department_as_kafedra(self):
        with bypass_rls():
            legacy = Organization.objects.create(
                name="Legacy", slug="sp-legacy", org_type=OrganizationType.UNIVERSITY, owner=self.owner
            )
            OrgUnit.objects.create(organization=legacy, name="Kafedra", slug="sp-l-k", unit_type="department")
            self.assertEqual(set(kafedra_unit_types(legacy)), {"chair", "department"})
            self.assertEqual(OrgUnit.objects.filter(kafedra_q(), organization=legacy).count(), 1)
        rows = [("a", "chair"), ("b", "department")]
        self.assertEqual(narrow_kafedra_rows(rows, lambda row: row[1]), [("a", "chair")])
        self.assertEqual(len(narrow_kafedra_rows(rows[1:], lambda row: row[1])), 1)


class PlacementPlanTest(_World):
    def test_plan_moves_joins_and_keeps_dean_primary(self):
        plan = self.plan()
        kinds = {(action.user_id, action.kind, action.unit_id) for action in plan.actions}
        a, b = str(self.chair_a.pk), str(self.chair_b.pk)
        self.assertIn((self.mover.pk, placement_plan.JOIN, b), kinds)
        self.assertIn((self.mover.pk, placement_plan.PRIMARY, b), kinds)
        self.assertIn((self.mover.pk, placement_plan.DEACTIVATE, a), kinds)
        self.assertIn((self.dean.pk, placement_plan.JOIN, a), kinds)
        self.assertNotIn(placement_plan.PRIMARY, {kind for user, kind, _u in kinds if user == self.dean.pk})
        self.assertIn((self.dormant.pk, placement_plan.JOIN, a), kinds)
        self.assertIn(self.dormant.pk, plan.dormant_ids)
        self.assertFalse([action for action in plan.actions if action.user_id == self.staying.pk])

    def test_apply_is_idempotent_and_undo_restores(self):
        plan = self.plan()
        with bypass_rls():
            result = placement_apply.execute(plan, actor=self.root, reason="Sınaq: heyət yerləşdirmə auditi tətbiqi")
        self.assertEqual(len(result["join"]), 3)
        mover_b = self.membership(self.mover, self.chair_b)
        self.assertTrue(mover_b.is_active and mover_b.is_primary)
        self.assertFalse(self.membership(self.mover, self.chair_a).is_active)
        dean_join = self.membership(self.dean, self.chair_a)
        self.assertTrue(dean_join.is_active and not dean_join.is_primary)
        with bypass_rls():
            self.assertTrue(Membership.objects.get(user=self.dean, role__name="dean").is_primary)
        self.assertEqual(self.plan().actions, [])  # təkrar → 0 yazı

        with bypass_rls():
            undone = placement_apply.undo(result["batch"], actor=self.root)
        self.assertEqual((undone["reactivated"], undone["joins_reverted"]), (1, 3))
        mover_a = self.membership(self.mover, self.chair_a)
        self.assertTrue(mover_a.is_active and mover_a.is_primary)
        self.assertFalse(self.membership(self.mover, self.chair_b).is_active)


class BlockProtectionTest(_World):
    def test_teacher_with_current_journal_is_not_blocked(self):
        with bypass_rls():
            block = build_plan(self.org, parse_sheet_rows(FORMA7), academic_year="2026/2027", workload=False)
        blocked = {account.user_id for account in block.block}
        protected = {account.user_id: reasons for account, reasons in block.protected}
        self.assertIn(self.gone.pk, blocked)
        self.assertNotIn(self.teaching.pk, blocked)
        self.assertIn("teaching_now", protected[self.teaching.pk])


class CommandTest(_World):
    def test_dry_run_counts_only_and_private_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            forma7 = os.path.join(tmp, "f7.xlsx")
            with open(forma7, "wb") as handle:
                handle.write(_xlsx(FORMA7))
            report = os.path.join(tmp, "r.md")
            out = StringIO()
            call_command(
                "audit_staff_placement", organization="placement-univ", forma7=forma7, report=report, stdout=out
            )
            self.assertEqual(stat.S_IMODE(os.stat(report).st_mode), 0o600)
            with open(report, encoding="utf-8") as handle:
                self.assertIn("sp_mover", handle.read())
        text = out.getvalue()
        self.assertIn("DRY-RUN", text)
        self.assertNotIn("sp_mover", text)
        self.assertNotIn("Köçəriyev", text)
        self.assertTrue(self.membership(self.mover, self.chair_a).is_primary)

    def test_apply_requires_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            forma7 = os.path.join(tmp, "f7.xlsx")
            with open(forma7, "wb") as handle:
                handle.write(_xlsx(FORMA7))
            with self.assertRaises(CommandError):
                call_command(
                    "audit_staff_placement",
                    organization="placement-univ",
                    forma7=forma7,
                    apply=True,
                    i_know_this_is_production=True,
                    stdout=StringIO(),
                )


class WorkflowWhitelistTest(TestCase):
    def test_prod_data_ops_runs_command_with_encrypted_bundle(self):
        from pathlib import Path

        text = (Path(__file__).resolve().parents[3] / ".github/workflows/prod-data-ops.yml").read_text(encoding="utf-8")
        self.assertIn("          - audit_staff_placement\n", text)
        self.assertIn("'^staff-placement-[0-9a-z-]+$'", text)
        self.assertIn("'^placement-[0-9a-z-]+$'", text)
        self.assertIn("args+=(--block-inactive)", text)
        self.assertIn("/tmp/staff_placement_*.zip", text)  # konteynerdə qalıq silinir
