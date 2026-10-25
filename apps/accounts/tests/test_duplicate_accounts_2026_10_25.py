"""Dublikat heyət hesabları — «jurnalı yazdığı hesabı saxla, digərlərini dondur» (sahib 2026-10-25).

Kilidlənən qaydalar:

* eyni şəxs: soyad+ad (diakritik/registr, tərs sahələr), ata adı ziddiyyətsiz; Vahid ≠ Zahid — BAŞQA adam;
* adı natamam hesab («Aynur») eyni kafedradakı tam adlı hesabla birləşir; dublikatın jurnalı «Fənn təhvili» ilə
  saxlanılana keçir;
* xüsusi hal: jurnallı hesab heç vaxt girməyib, digəri girir, yük yoxdur → jurnallar GİRƏN hesaba keçir;
  yük varsa jurnallı hesab saxlanılır, girən dondurulur (RİM parol siyahısı);
* dondurulanın rolu (dekan) və bölmə rəhbərliyi saxlanılana keçir, üzvlükləri deaktiv, hesab bloklanır;
* tətbiq idempotentdir, ``undo`` hər şeyi qaytarır; əmr defolt dry-run, stdout-da ad yoxdur, hesabat 0600.
"""

from __future__ import annotations

import os
import stat
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.services.duplicate_accounts import apply as dup_apply
from apps.accounts.services.duplicate_accounts import plan as dup_plan
from apps.accounts.services.duplicate_accounts.facts import Person
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Subject, TeachingHandover
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

from .people_fixture import add_membership, make_role, make_user

YEAR = "2026/2027"


class _World(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user("da_owner", first="Sahib", last="Sahibov")
        cls.root = make_user("da_root", first="Kök", last="Köklü")
        with bypass_rls():
            type(cls.root).objects.filter(pk=cls.root.pk).update(is_superuser=True)
            cls.root.refresh_from_db()
            cls.org = Organization.objects.create(
                name="Dup Univ",
                slug="dup-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            unit = lambda name, kind, parent=None: OrgUnit.objects.create(  # noqa: E731
                organization=cls.org, name=name, slug=f"da-{len(name)}-{kind}", unit_type=kind, parent=parent
            )
            cls.faculty = unit("Fakulte", OrgUnitType.FACULTY)
            cls.chair = unit("Alfa kafedrası", OrgUnitType.CHAIR, cls.faculty)
            cls.group = unit("101", OrgUnitType.GROUP, cls.faculty)
            teacher = make_role(
                cls.org, "teacher", level=50, scope_type=RoleScopeType.COURSE, permissions=["grade.input"]
            )
            dean = make_role(cls.org, "dean", level=80, scope_type=RoleScopeType.UNIT, permissions=[])
            cls.teacher_role = teacher
            period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year=YEAR,
                start_date="2026-09-15",
                end_date="2027-01-31",
                is_current=True,
            )
            counter = iter(range(100, 200))

            def offering(instructor):
                number = next(counter)
                subject = Subject.objects.create(organization=cls.org, code=f"DA{number}", name=f"Fənn {number}")
                return CourseOffering.objects.create(
                    organization=cls.org, subject=subject, period=period, group=cls.group, instructor=instructor
                )

            # 1) Xüsusi hal: jurnallı hesab heç vaxt girməyib, eyni şəxsin digər hesabı girir (üzvlüyü sönülü).
            cls.k_journal = make_user("da_k2", first="Gülçin", last="Bəxtiyarova", patronymic="Sadıq")
            add_membership(cls.org, cls.k_journal, teacher, unit=cls.chair)
            cls.k_offerings = [offering(cls.k_journal), offering(cls.k_journal)]
            cls.k_login = make_user("da_k1", first="GÜLÇİN", last="BƏXTİYAROVA", patronymic="Sadıq qızı")
            Membership.objects.filter(pk=add_membership(cls.org, cls.k_login, teacher, unit=cls.chair).pk).update(
                is_active=False
            )
            # 2) Dekan rolu girməyən dublikatdadır; şəxs digər hesabla girir. Zahid — BAŞQA adamdır.
            cls.f_dean = make_user("da_f8", first="Lalə", last="Əhədova", patronymic="Vahid")
            add_membership(cls.org, cls.f_dean, dean, unit=cls.faculty)
            OrgUnit.objects.filter(pk=cls.faculty.pk).update(head=cls.f_dean)
            cls.f_login = make_user("da_f24", first="Lalə", last="Ahadova", patronymic="Vahid")
            add_membership(cls.org, cls.f_login, teacher, unit=cls.chair)
            cls.f_other = make_user("da_f7", first="Lalə", last="Əhədova", patronymic="Zahid")
            add_membership(cls.org, cls.f_other, teacher, unit=cls.chair)
            # 3) Adı natamam hesab («Aynur») — yük/jurnal onun üzərindədir; tam adlı dublikatın 1 jurnalı var.
            cls.r_partial = make_user("da_r", first="Aynur", last="")
            add_membership(cls.org, cls.r_partial, teacher, unit=cls.chair)
            cls.r_partial_offerings = [offering(cls.r_partial), offering(cls.r_partial)]
            cls.r_full = make_user("da_rx", first="Aynur", last="Qocayeva", patronymic="Rauf")
            add_membership(cls.org, cls.r_full, teacher, unit=cls.chair)
            cls.r_full_offering = offering(cls.r_full)
            login = timezone.now()
            type(cls.k_login).objects.filter(pk__in=[cls.k_login.pk, cls.f_login.pk]).update(last_login=login)

    def build(self):
        with bypass_rls():
            return dup_plan.build(self.org, academic_year=YEAR)

    def execute(self):
        with bypass_rls():
            return dup_apply.execute(self.build(), actor=self.root)

    def refresh(self, user):
        with bypass_rls():
            user.refresh_from_db()
            user.profile.refresh_from_db()
        return user

    def cluster_of(self, plan, user):
        return next(c for c in plan.clusters if any(p.user_id == user.pk for p in c.members))


class DuplicatePlanTests(_World):
    def test_clusters_and_kept_accounts(self):
        plan = self.build()
        flip = self.cluster_of(plan, self.k_journal)
        self.assertEqual(flip.mode, dup_plan.MODE_FLIP)
        self.assertEqual(flip.kept.user_id, self.k_login.pk)
        dean = self.cluster_of(plan, self.f_dean)
        self.assertEqual({p.user_id for p in dean.members}, {self.f_dean.pk, self.f_login.pk})
        self.assertEqual(dean.kept.user_id, self.f_login.pk)  # son giriş
        self.assertIn(self.f_other.pk, {person.user_id for person, _ in dean.excluded})
        partial = self.cluster_of(plan, self.r_partial)
        self.assertEqual(partial.kept.user_id, self.r_partial.pk)  # jurnal sayı çoxdur
        self.assertEqual(plan.ambiguous, [])

    def test_apply_moves_journals_roles_and_freezes(self):
        result = self.execute()
        self.assertEqual(result["failed"], [])
        with bypass_rls():
            for offering in self.k_offerings:
                offering.refresh_from_db()
                self.assertEqual(offering.instructor_id, self.k_login.pk)
            self.r_full_offering.refresh_from_db()
            self.assertEqual(self.r_full_offering.instructor_id, self.r_partial.pk)
            self.assertEqual(TeachingHandover.objects.filter(organization=self.org).count(), 3)
            self.assertTrue(
                Membership.objects.filter(user=self.f_login, role__name="dean", scope_unit=self.faculty, is_active=True)
            )
            self.assertEqual(OrgUnit.objects.get(pk=self.faculty.pk).head_id, self.f_login.pk)
            self.assertTrue(Membership.objects.filter(user=self.k_login, scope_unit=self.chair, is_active=True))
            self.assertFalse(Membership.objects.filter(user=self.f_dean, is_active=True).exists())
        for frozen, kept in (
            (self.k_journal, self.k_login),
            (self.f_dean, self.f_login),
            (self.r_full, self.r_partial),
        ):
            frozen = self.refresh(frozen)
            self.assertFalse(frozen.is_active)
            self.assertIn(f"Dublikat hesab — əsas hesab: {kept.username}", frozen.profile.block_reason)
        for untouched in (self.f_other, self.k_login, self.f_login, self.r_partial):
            self.assertTrue(self.refresh(untouched).is_active)
        # Sahib 2026-10-25: «tam adları əlavə edilsin» — natamam saxlanılan hesab dublikatın soyad/ata adını alır.
        partial = self.refresh(self.r_partial)
        self.assertEqual((partial.last_name, partial.profile.patronymic), ("Qocayeva", "Rauf"))
        self.assertEqual(len(result["names"]), 1)

    def test_reapply_is_noop_and_undo_restores(self):
        batch = self.execute()["batch"]
        self.assertEqual(self.build().writes, 0)
        with bypass_rls():
            outcome = dup_apply.undo(batch, actor=self.root)
        self.assertEqual(outcome["failed"], 0)
        self.assertEqual(outcome["handovers_reverted"], 3)
        with bypass_rls():
            self.assertEqual(
                set(CourseOffering.objects.filter(instructor=self.k_journal).values_list("pk", flat=True)),
                {offering.pk for offering in self.k_offerings},
            )
            self.assertEqual(OrgUnit.objects.get(pk=self.faculty.pk).head_id, self.f_dean.pk)
            self.assertFalse(Membership.objects.filter(user=self.f_login, role__name="dean", is_active=True).exists())
            self.assertTrue(Membership.objects.filter(user=self.f_dean, role__name="dean", is_active=True).exists())
        for user in (self.k_journal, self.f_dean, self.r_full):
            self.assertTrue(self.refresh(user).is_active)
        self.assertEqual(outcome["names_restored"], 1)
        self.assertEqual(self.refresh(self.r_partial).last_name, "")
        self.assertGreater(self.build().writes, 0)

    def test_command_dry_run_by_default_names_only_in_private_report(self):
        out = StringIO()
        with tempfile.TemporaryDirectory() as folder:
            report = os.path.join(folder, "dups.md")
            call_command("freeze_duplicate_accounts", "--org", self.org.slug, "--markdown", report, stdout=out)
            self.assertEqual(stat.S_IMODE(os.stat(report).st_mode), 0o600)
            with open(report, encoding="utf-8") as handle:
                self.assertIn(self.k_login.username, handle.read())
        text = out.getvalue()
        self.assertIn("DRY-RUN (heç nə yazılmadı):", text)
        for user in (self.k_login, self.k_journal, self.f_dean, self.r_full):
            self.assertNotIn(user.username, text)
        self.assertTrue(self.refresh(self.k_journal).is_active)


class DuplicateDecisionUnitTests(SimpleTestCase):
    def person(self, pk, *, journals=0, load=0, login=False, owned=(), patronymic="Ata", active=True):
        return Person(
            user_id=pk,
            username=f"u{pk}",
            last="Soyadova",
            first="Ad",
            patronymic=patronymic,
            is_active=active,
            last_login=timezone.now() if login else None,
            has_fin=False,
            owned=list(owned),
            journals=journals,
            load=load,
        )

    def decide(self, *members):
        cluster = dup_plan.Cluster(members=sorted(members, key=lambda p: p.sort_key(), reverse=True))
        original = dup_plan._blocked_offerings
        dup_plan._blocked_offerings = lambda organization, ids, today: set()
        try:
            dup_plan._decide(cluster, None, None)
        finally:
            dup_plan._blocked_offerings = original
        return cluster

    def test_patronymic_rule(self):
        self.assertEqual(dup_plan.patronymic_state("vahid", "zahid"), "different")
        self.assertEqual(dup_plan.patronymic_state("esger", "esker"), "similar")
        self.assertEqual(dup_plan.patronymic_state("", "adil"), "missing")

    def test_kept_with_load_never_logged_in_keeps_journals_and_freezes_login(self):
        cluster = self.decide(self.person(1, journals=3, load=5, owned=["o1"]), self.person(2, login=True))
        self.assertEqual(cluster.mode, dup_plan.MODE_RIM_PASSWORD)
        self.assertEqual(cluster.kept.user_id, 1)
        self.assertTrue(cluster.dups[0].block)

    def test_dup_with_load_is_not_frozen(self):
        cluster = self.decide(self.person(1, journals=4, load=9, login=True), self.person(2, journals=1, load=2))
        self.assertEqual(cluster.dups[0].skip, "has_load")
        self.assertEqual(cluster.writes, 0)

    def test_conflicting_patronymics_are_left_alone(self):
        cluster = self.decide(self.person(1, journals=1), self.person(2, patronymic="Başqa"))
        self.assertEqual(cluster.status, "patronymic_conflict")

    def test_workflow_whitelists_command(self):
        from pathlib import Path

        text = (Path(__file__).resolve().parents[3] / ".github/workflows/prod-data-ops.yml").read_text(encoding="utf-8")
        self.assertIn("          - freeze_duplicate_accounts\n", text)
        self.assertIn("^dupacct-[0-9a-z-]+$", text)
        self.assertIn("^Paket: dupacct-[0-9a-z-]+$", text)
