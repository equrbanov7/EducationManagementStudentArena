"""«Dəyərləndirilmiş nəticələr» / «Yoxlanılacaqlar» qrup süzgəci reyestr qrupundan (sahib 2026-10-25).

Köhnə ``StudentGroup`` xəritəsi reyestr qrupları ilə işləyən müəllimdə boş idi — qrup siyahısı boş qalır,
seçilən qrup atılır, süzgəc «işləmirdi». İndi sətrin qrupu tələbənin CARİ reyestr qrupudur.
"""

from __future__ import annotations

from django.test import TestCase

from apps.accounts.views._dashboard_helpers.formatters import _attach_registry_groups
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.rls import bypass_rls


class RegistryGroupFilterTest(SubgroupFixture, TestCase):
    PREFIX = "rgf"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()

    def test_rows_get_registry_group_and_selector_lists_it(self):
        items = [
            {"student": self.student, "group_name": ""},
            {"student": self.host, "group_name": "Köhnə kurs qrupu"},
            {"student": self.teacher, "group_name": "Köhnə kurs qrupu"},
        ]
        with bypass_rls():
            groups = _attach_registry_groups(items, ["Köhnə kurs qrupu"])
        self.assertEqual(items[0]["group_name"], self.group2.name)
        self.assertEqual(items[1]["group_name"], self.group1.name)  # reyestr köhnə xəritədən üstündür
        self.assertEqual(items[2]["group_name"], "Köhnə kurs qrupu")  # reyestr qeydi yoxdur — ehtiyat
        self.assertEqual(set(groups), {self.group1.name, self.group2.name, "Köhnə kurs qrupu"})
