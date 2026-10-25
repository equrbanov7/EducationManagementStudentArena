"""Qrup kartının boş xanaları (sahib 2026-10-26: «ana qrup əyanidirsə alt qrup da əyani, az dilidirsə alt qrup da az —
boş xana qalmasın»).

* Köhnə datanın ``sector`` açarı reyestrdə dil kimi görünür (``group_meta``) və ``language_sector``-a yazılır.
* Boş alt qrup ana qrupun dilini/formasını alır; ana qrupun boş forması alt qrupların yekdil dəyərindən gəlir.
* Köhnə datada alt qrupun dili FƏRQLİDİRSƏ saxlanır (ziddiyyət sayılır).
* Dry-run yazmır; ``--apply`` yalnız boş xananı yazır; təkrar qaçış 0 yazır; stdout yalnız saylar.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.organizations.groups_registry import group_meta
from apps.organizations.models import Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class GroupSettingsGapsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("gsg_owner", "gsg_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="GSG Univ",
                slug="gsg-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            faculty = cls._unit("Filologiya", OrgUnitType.FACULTY, None, {})
            spec = cls._unit("Filologiya ixtisası", OrgUnitType.SPECIALTY, faculty, {})
            cls.parent = cls._unit("336 F", OrgUnitType.GROUP, spec, {"language_sector": "az"})
            cls.f1 = cls._unit(
                "336F1",
                OrgUnitType.GROUP,
                spec,
                {"sector": "az", "education_form": "full_time", "parent_group": "", "degree_level": "bachelor"},
            )
            cls.f2 = cls._unit("336F2", OrgUnitType.GROUP, spec, {"education_form": "full_time"})
            cls.f3 = cls._unit("336F3", OrgUnitType.GROUP, spec, {"sector": "en", "education_form": "full_time"})
            for sub in (cls.f1, cls.f2, cls.f3):
                sub.settings["parent_group"] = str(cls.parent.pk)
                sub.save(update_fields=["settings"])
            cls.lonely = cls._unit("237 K", OrgUnitType.GROUP, spec, {"sector": "ru"})

    @classmethod
    def _unit(cls, name, unit_type, parent, settings):
        return OrgUnit.objects.create(
            organization=cls.org,
            name=name,
            slug=f"gsg-{name}".replace(" ", "-").lower(),
            unit_type=unit_type,
            parent=parent,
            settings=settings,
        )

    def _settings(self, unit):
        with bypass_rls():
            return OrgUnit.objects.get(pk=unit.pk).settings

    def test_registry_reads_legacy_sector(self):
        self.assertEqual(group_meta(self.lonely)["language_sector"], "ru")

    def test_dry_run_then_apply(self):
        out = StringIO()
        call_command("fill_group_settings_gaps", org=self.org.slug, stdout=out)
        self.assertIn("mode=dry_run", out.getvalue())
        self.assertNotIn("language_sector", self._settings(self.f2))

        out = StringIO()
        call_command("fill_group_settings_gaps", org=self.org.slug, apply=True, stdout=out)
        text = out.getvalue()
        self.assertIn("language_conflict_with_parent=1", text)
        self.assertNotIn("336", text)
        self.assertEqual(self._settings(self.parent)["education_form"], "full_time")
        self.assertEqual(self._settings(self.f1)["language_sector"], "az")
        self.assertEqual(self._settings(self.f2)["language_sector"], "az")
        self.assertEqual(self._settings(self.f3)["language_sector"], "en")
        self.assertEqual(self._settings(self.lonely)["language_sector"], "ru")

        out = StringIO()
        call_command("fill_group_settings_gaps", org=self.org.slug, apply=True, stdout=out)
        self.assertIn("written=0", out.getvalue())
