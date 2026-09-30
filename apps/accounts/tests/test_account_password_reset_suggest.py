"""«Parol sıfırlama» — yazdıqca təklif (sahib 2026-09-30).

Yüngül siyahı: ən çoxu ``SUGGEST_LIMIT`` nəfər, sabit sorğu sayı, əhatə ``lookup`` ilə eyni
(yad tenant / daha yüksək rütbə / özü görünmür), istifadəçi adı ilə başlayan birinci, yalnız
POST + icazə. Tam kart (sıfırla düyməsi) seçimdən sonra ``lookup`` ilə qurulur.
"""

from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.services.password_reset_lookup import SUGGEST_LIMIT

from .test_account_password_reset import PasswordResetTestBase, make_user

URL = "accounts:account_password_reset_suggest"


class SuggestTests(PasswordResetTestBase):
    def suggest(self, query, client=None):
        return (client or self.client).post(reverse(URL), {"q": query}, content_type="application/json")

    def test_partial_name_lists_matching_people(self):
        self.login(self.operator)

        response = self.suggest("quli")

        self.assertEqual(response.status_code, 200)
        rows = response.json()["results"]
        self.assertEqual([row["username"] for row in rows], ["aysel.quliyeva"])
        self.assertEqual(set(rows[0]), {"id", "username", "full_name", "hint"})
        self.assertIn("Aysel", rows[0]["full_name"])

    def test_username_prefix_ranks_first(self):
        # Soyadı «A…» olsa da (əlifba sırasında öndə), istifadəçi adı uyğun gələnlərdən SONRA gəlir.
        make_user("zaur.abbasov", self.org, self.student_role, first="Elvin", last="Abbasov")
        make_user("elvin.zeynalov", self.org, self.student_role, first="Zeynal", last="Zeynalov")
        self.login(self.operator)

        usernames = [row["username"] for row in self.suggest("elvin").json()["results"]]

        self.assertEqual(set(usernames[:2]), {"elvin.aliyev", "elvin.zeynalov"})
        self.assertEqual(usernames[2], "zaur.abbasov")

    def test_scope_matches_lookup(self):
        self.login(self.operator)

        usernames = {row["username"] for row in self.suggest("r").json()["results"]} | {
            row["username"] for row in self.suggest("yad").json()["results"]
        }
        usernames |= {row["username"] for row in self.suggest("rim").json()["results"]}
        usernames |= {row["username"] for row in self.suggest("rektor").json()["results"]}

        self.assertNotIn("yad.telebe", usernames)  # yad tenant
        self.assertNotIn("rim.peer", usernames)  # eyni rütbə
        self.assertNotIn("rektor.user", usernames)  # yüksək rütbə
        self.assertNotIn("rim.rehber", usernames)  # özü

    def test_result_count_is_capped_and_queries_constant(self):
        for index in range(SUGGEST_LIMIT + 5):
            make_user(f"toplu.telebe{index}", self.org, self.student_role, first="Toplu", last=f"Tələbə{index}")
        self.login(self.operator)
        self.suggest("toplu")  # sessiya/keş istiləşməsi

        with CaptureQueriesContext(connection) as queries:
            rows = self.suggest("toplu").json()["results"]

        self.assertEqual(len(rows), SUGGEST_LIMIT)
        self.assertLess(len(queries.captured_queries), 25)

    def test_short_query_returns_nothing(self):
        self.login(self.operator)

        self.assertEqual(self.suggest("a").json()["results"], [])

    def test_requires_permission_and_post(self):
        self.login(self.student)
        self.assertEqual(self.suggest("quli").status_code, 403)
        self.login(self.operator)
        self.assertEqual(self.client.get(reverse(URL)).status_code, 405)
