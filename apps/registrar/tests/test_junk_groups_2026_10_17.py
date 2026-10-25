"""Test / zibil qruplar (QA-2 F-16): yalnız İSTİFADƏ OLUNMAYAN namizəd deaktiv olunur, heç nə silinmir."""

from __future__ import annotations

import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.organizations.models import Organization, OrgUnit
from apps.registrar import junk_groups
from apps.registrar.models import Program
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls


class JunkNameTest(SimpleTestCase):
    def test_junk_and_real_names(self):
        for name in (".", "-", "test1543", "testuchunqrup2", "Silinmelidir", "silinməli qrup", "aaa", "qwerty"):
            self.assertTrue(junk_groups.junk_reason(name), name)
        for name in ("234 K-1", "Xaric olanlar", "631/5K ing", "Kompüter mühəndisliyi", "A1"):
            self.assertEqual(junk_groups.junk_reason(name), "", name)


class ArchiveJunkGroupsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = get_user_model().objects.create_user("jg_owner", "jg_owner@jg.test", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JG", slug="jg-org", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
            )

            def unit(name, unit_type, parent=None):
                return OrgUnit.objects.create(
                    organization=cls.org, parent=parent, name=name, slug=f"jg-{abs(hash(name))}", unit_type=unit_type
                )

            faculty = unit("Fak", OrgUnitType.FACULTY)
            cls.specialty = unit("Ixt", OrgUnitType.SPECIALTY, faculty)
            cls.empty_junk = unit("test1543", OrgUnitType.GROUP, cls.specialty)
            cls.dot = unit(".", OrgUnitType.GROUP, cls.specialty)
            cls.real = unit("234 K-1", OrgUnitType.GROUP, cls.specialty)
            cls.used_specialty = unit("aaa", OrgUnitType.SPECIALTY, faculty)
            Program.objects.create(organization=cls.org, specialty_unit=cls.used_specialty, code="AA", name="AA")

    def _run(self, *extra):
        out = StringIO()
        with tempfile.TemporaryDirectory() as folder:
            call_command("archive_junk_groups", "--org", self.org.slug, "--report", folder, *extra, stdout=out)
            rows = (Path(folder) / "junk_groups.csv").read_text(encoding="utf-8")
        return out.getvalue(), rows

    def _refresh(self):
        with bypass_rls():
            for unit in (self.empty_junk, self.dot, self.real, self.used_specialty):
                unit.refresh_from_db()

    def test_dry_run_writes_nothing(self):
        output, rows = self._run()
        self.assertIn("DRY-RUN", output)
        self.assertIn("candidates=3 · archive=2 · skip_in_use=1", output)
        self.assertIn("registrar.Program.specialty_unit=1", rows)
        self._refresh()
        self.assertTrue(self.empty_junk.is_active)

    def test_apply_archives_only_unused_and_is_idempotent(self):
        output, _rows = self._run("--apply")
        self.assertIn("YAZILDI", output)
        self._refresh()
        self.assertFalse(self.empty_junk.is_active)
        self.assertFalse(self.dot.is_active)
        self.assertIn(junk_groups.JUNK_SETTING, self.empty_junk.settings)
        self.assertTrue(self.real.is_active)  # real ad
        self.assertTrue(self.used_specialty.is_active)  # proqram bağlıdır
        with bypass_rls():
            self.assertTrue(OrgUnit.objects.filter(pk=self.empty_junk.pk).exists())  # silinmir
        again, _rows = self._run("--apply")
        self.assertIn("archive=0", again)
        self.assertIn("already_inactive=2", again)


class GroupsRegistryParentLinkTest(TestCase):
    """QA-2 F-16: reyestr sətrində ana qrup adı və alt qrup sayı (2 toplu sorğu)."""

    def test_parent_links(self):
        from apps.organizations.groups_registry import _parent_links

        owner = get_user_model().objects.create_user("jgp_owner", "jgp_owner@jg.test", "pw")
        with bypass_rls():
            org = Organization.objects.create(
                name="JGP", slug="jgp-org", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
            )
            fac = OrgUnit.objects.create(organization=org, name="F", slug="jgp-f", unit_type=OrgUnitType.FACULTY)
            spec = OrgUnit.objects.create(
                organization=org, parent=fac, name="S", slug="jgp-s", unit_type=OrgUnitType.SPECIALTY
            )
            parent = OrgUnit.objects.create(
                organization=org, parent=spec, name="234 K az", slug="jgp-p", unit_type=OrgUnitType.GROUP
            )
            subs = [
                OrgUnit.objects.create(
                    organization=org,
                    parent=spec,
                    name=f"234 K-{i}",
                    slug=f"jgp-{i}",
                    unit_type=OrgUnitType.GROUP,
                    settings={"parent_group": str(parent.pk)},
                )
                for i in (1, 2)
            ]
            names, counts = _parent_links(org, [parent, *subs])
        self.assertEqual(names, {str(parent.pk): "234 K az"})
        self.assertEqual(counts, {str(parent.pk): 2})


class IdleUnderFacultyTest(ArchiveJunkGroupsTest):
    """Sahib 2026-10-25: fakültənin alt-ağacında aktiv tələbəsi və cari açılışı OLMAYAN qruplar deaktiv olunur."""

    def test_idle_groups_under_faculty_are_archived_live_ones_kept(self):
        import datetime

        from apps.organizations.models import AcademicPeriod
        from apps.registrar.models import CourseOffering, Subject
        from core.constants import AcademicPeriodType

        with bypass_rls():
            period = AcademicPeriod.objects.create(
                organization=self.org,
                name="Payız",
                academic_year="2026/2027",
                period_type=AcademicPeriodType.SEMESTER,
                start_date=datetime.date(2026, 9, 15),
                end_date=datetime.date(2099, 1, 31),
            )
            subject = Subject.objects.create(organization=self.org, code="JG-1", name="Fənn")
            CourseOffering.objects.create(organization=self.org, subject=subject, period=period, group=self.real)
        output, rows = self._run("--idle-under", "Fak", "--apply")
        self.assertIn("candidates=3 · archive=2 · skip_in_use=1", output)
        self.assertIn("live_offerings=1", rows)
        self._refresh()
        self.assertFalse(self.empty_junk.is_active)
        self.assertFalse(self.dot.is_active)
        self.assertTrue(self.real.is_active)
        self.assertTrue(self.used_specialty.is_active)  # yalnız QRUPLAR
        again, _rows = self._run("--idle-under", "Fak", "--apply")
        self.assertIn("archive=0", again)
        unknown, _rows = self._run("--idle-under", "Yoxdur")
        self.assertIn("candidates=0", unknown)
