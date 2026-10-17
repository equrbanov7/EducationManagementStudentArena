"""``ensure_parent_groups`` — alt qruplar üçün ortaq ana qrup (sahib 2026-10-17).

Kilidlənən qaydalar: K-1/K-2 üçün ana qrup yaradılır və alt qruplar ``settings.parent_group`` ilə bağlanır
(``group_split`` modeli); mövcud ana qrup təkrar istifadə olunur; ad kursun konvensiyasına uyğundur
(« az» şəkilçisi yalnız kurs onu işlədirsə); qeyri-müəyyən hallar (fərqli ixtisas, arxiv qrupla ad
toqquşması, eyni adlı iki ana qrup) yazılmır, hesabata düşür; dry-run heç nə yazmır; təkrar apply
idempotentdir; tələbə qrupu dəyişmir.
"""

from __future__ import annotations

import csv
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from apps.organizations.models import Organization, OrgUnit
from apps.registrar.parent_groups import subgroup_label
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

META = {"course_year": 2, "admission_year": 2025, "education_form": "full_time", "language_sector": "az"}


class SubgroupLabelTest(SimpleTestCase):
    def test_forms(self):
        self.assertEqual(subgroup_label("234 K-1").label.sub, "1")
        self.assertEqual(subgroup_label("234 K-2 ing").label.sector, "ing")
        ing = subgroup_label("234 K ing-1")
        self.assertEqual((ing.label.sector, ing.label.sub, ing.legacy), ("ing", "1", False))
        self.assertEqual(subgroup_label("236 SBİO-2 az").label.sub, "2")
        self.assertTrue(subgroup_label("534 TB 1").legacy)
        for name in ("234 K az", "235 K", "233KE", "236 İT ing", "229 PM /1"):
            self.assertIsNone(subgroup_label(name), name)


class EnsureParentGroupsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("epg_owner", "epg_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="EPG Univ",
                slug="epg-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.km = cls._unit("Kompüter Mühəndisliyi", OrgUnitType.SPECIALTY, None)
            cls.sb = cls._unit("Su Bioehtiyyatları", OrgUnitType.SPECIALTY, None)
            cls.it = cls._unit("İnformasiya Texnologiyaları", OrgUnitType.SPECIALTY, None)
            cls.other = cls._unit("Başqa ixtisas", OrgUnitType.SPECIALTY, None)
            # 234 kursu « az» şəkilçisini işlədir; 235 kursu işlətmir.
            cls.k_parent = cls._group("234 K az", cls.km)
            cls.k1 = cls._group("234 K-1", cls.km)
            cls.k2 = cls._group("234 K-2", cls.km)
            cls._group("234 BİO az", cls.sb)
            cls.eko1 = cls._group("234 EKO-1", cls.sb, META)
            cls.eko2 = cls._group("234 EKO-2", cls.sb, META)
            cls._group("235 KE", cls.km)
            cls._group("235 M", cls.sb)
            cls.sbio1 = cls._group("235 SBİO-1", cls.sb, META)
            cls.sbio2 = cls._group("235 SBİO-2", cls.sb, META)
            cls.ing1 = cls._group("234 K ing-1", cls.km)
            cls.ing2 = cls._group("234 K-2 ing", cls.km)
            # Qeyri-müəyyən: alt qruplar fərqli ixtisasda.
            cls.split1 = cls._group("236 İT-1", cls.it)
            cls.split2 = cls._group("236 İT-2", cls.other)
            # Qeyri-müəyyən: arxiv qrupla ad toqquşması.
            cls._group("237 M", cls.sb, active=False)
            cls.m1 = cls._group("237 M-1", cls.sb)
            cls.m2 = cls._group("237 M-2", cls.sb)
            # Qeyri-müəyyən: eyni adlı iki ana qrup.
            cls._group("235 K", cls.km)
            cls._group("235 K", cls.km)
            cls.dk1 = cls._group("235 K-1", cls.km)
            cls.dk2 = cls._group("235 K-2", cls.km)

    _seq = 0

    @classmethod
    def _unit(cls, name, unit_type, parent, settings=None, active=True):
        cls._seq += 1
        return OrgUnit.objects.create(
            organization=cls.org,
            name=name,
            slug=f"epg-{cls._seq}",
            unit_type=unit_type,
            parent=parent,
            settings=dict(settings or {}),
            is_active=active,
        )

    @classmethod
    def _group(cls, name, parent, settings=None, active=True):
        return cls._unit(name, OrgUnitType.GROUP, parent, settings, active)

    def _run(self, *extra):
        out = StringIO()
        with tempfile.TemporaryDirectory() as folder:
            call_command("ensure_parent_groups", "--org", self.org.slug, "--report", folder, *extra, stdout=out)
            with (Path(folder) / "parent_groups.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        return out.getvalue(), rows

    def _groups(self):
        with bypass_rls():
            return {
                (unit.name, unit.parent_id): unit
                for unit in OrgUnit.objects.filter(organization=self.org, unit_type=OrgUnitType.GROUP)
            }

    def _trail(self, unit):
        unit.refresh_from_db()
        return (unit.settings or {}).get("parent_group")

    def test_dry_run_writes_nothing(self):
        before = self._groups()
        output, rows = self._run()
        self.assertIn("DRY-RUN", output)
        self.assertIn("parents_created=3", output)
        self.assertIn("parents_existing=1", output)
        self.assertIn("subgroups_linked=8", output)
        self.assertIn("ambiguous=3", output)
        self.assertEqual(set(self._groups()), set(before))
        self.assertIsNone(self._trail(self.k1))
        self.assertIn("235 SBİO", {row["parent"] for row in rows if row["action"] == "created"})

    def test_apply_creates_links_and_is_idempotent(self):
        output, rows = self._run("--apply")
        self.assertIn("YAZILDI", output)
        groups = self._groups()
        # Mövcud ana qrup təkrar istifadə olunur.
        self.assertEqual(self._trail(self.k1), str(self.k_parent.pk))
        self.assertEqual(self._trail(self.k2), str(self.k_parent.pk))
        # Yeni ana qrup: eyni ixtisas, metadata alt qrupdan; 235 kursu şəkilçisiz, 234 kursu « az».
        sbio = groups[("235 SBİO", self.sb.pk)]
        self.assertEqual(self._trail(self.sbio1), str(sbio.pk))
        self.assertEqual(self._trail(self.sbio2), str(sbio.pk))
        self.assertEqual(sbio.settings["course_year"], 2)
        self.assertEqual(sbio.settings["education_form"], "full_time")
        eko = groups[("234 EKO az", self.sb.pk)]
        self.assertEqual(self._trail(self.eko1), str(eko.pk))
        ing = groups[("234 K ing", self.km.pk)]
        self.assertEqual({self._trail(self.ing1), self._trail(self.ing2)}, {str(ing.pk)})
        # Qeyri-müəyyən hallar yazılmır.
        for unit in (self.split1, self.split2, self.m1, self.m2, self.dk1, self.dk2):
            self.assertIsNone(self._trail(unit), unit.name)
        self.assertNotIn(("236 İT", self.it.pk), groups)
        reasons = {row["reason"] for row in rows if row["action"] == "ambiguous"}
        self.assertEqual(reasons, {"subgroups_in_different_specialties", "archived_name_clash", "duplicate_parent"})

        again, _rows = self._run("--apply")
        self.assertIn("parents_created=0", again)
        self.assertIn("subgroups_linked=0", again)
        self.assertIn("parents_existing=4", again)
        self.assertEqual(set(self._groups()), set(groups))
