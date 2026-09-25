"""«Sorğu nəticələri» — sorğu büdcəsi: hər görünüşün SQL sorğu sayı sabitdir (cavab/müəllim
sayından asılı deyil) və yuxarı həddi keçmir. İki ölçülü dünya eyni sayda sorğu verməlidir."""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.rls import bypass_rls

from .factories import client_for, member
from .results_world import add_general, add_responses, build_results_world

FRAGMENT = "accounts:profile_section_fragment"
#: Ölçülmüş dəyər + 3 ehtiyat (2026-09-25: overview 75, teachers 68, general 80, drawer 50,
#: export 81, search 13). Fraqment yolu kabinet qabığının sorğularını da sayır (~35, bax
#: test_cabinet_shell_query_budget); bölmənin özü sabit sayda aqreqat sorğusudur.
BUDGETS = {"overview": 78, "teachers": 71, "general": 83, "drawer": 53, "export": 84, "search": 16}


def _grow(world, extra):
    """Eyni strukturda daha çox müəllim və cavab — sorğu sayı DƏYİŞMƏMƏLİDİR."""
    with bypass_rls():
        for index in range(extra):
            teacher = member(world["org"], f"{world['org'].slug}_x{index}", "teacher", unit=world["chair_b"])
            add_responses(
                world,
                world["campaign"],
                teacher=teacher,
                department=world["chair_b"],
                faculty=world["faculty"],
                subject=world["phys"],
                group=world["group"],
                count=4 + index,
                score=4,
                overall=7,
            )
    add_general(world, world["campaign"], group=world["group"], faculty=world["faculty"], count=7, score=3)


class ResultsQueryBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.small = build_results_world("svqa")
        cls.large = build_results_world("svqb")
        _grow(cls.large, 5)

    def _count(self, world, name):
        client = client_for(world["org"], world["rector"])
        urls = {
            "overview": reverse(FRAGMENT, kwargs={"section": "evaluation-results"}),
            "teachers": reverse(FRAGMENT, kwargs={"section": "evaluation-results"}) + "?er_tab=teachers",
            "general": reverse(FRAGMENT, kwargs={"section": "evaluation-results"}) + "?er_tab=general",
            "drawer": reverse("surveys:results_teacher", args=[world["teacher_a"].pk]),
            "export": reverse("surveys:results_export", args=["xlsx"]),
            "search": reverse("surveys:results_teachers") + "?q=",
        }
        client.get(urls[name], HTTP_X_REQUESTED_WITH="XMLHttpRequest")  # isinmə (sessiya/keş)
        with CaptureQueriesContext(connection) as queries:
            response = client.get(urls[name], HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200, name)
        return len(queries)

    def test_every_view_is_bounded_and_independent_of_data_size(self):
        measured = {}
        for name, budget in BUDGETS.items():
            with self.subTest(view=name):
                small, large = self._count(self.small, name), self._count(self.large, name)
                measured[name] = (small, large)
                self.assertEqual(small, large, f"{name}: sorğu sayı məlumat həcmindən asılıdır")
                self.assertLessEqual(large, budget, f"{name}: {large} > büdcə {budget}")
        print("\n[query budget] " + ", ".join(f"{name}={small}" for name, (small, _large) in measured.items()))
