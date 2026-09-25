"""Şəxs axtarışı — «Ad Soyad» və az/ing diakritika dözümlülüyü (sahib 2026-09-21).

Şikayət: view-as panelində «Ad Soyad» (boşluqla) yazanda heç nə çıxmır; «ı/i»,
«ə/e», «ş/s» kimi klaviatura fərqləri nəticəni sıfırlayır. Yoxlanılır: token
məntiqi (VƏ), diakritika sinifləri, regex qaçırması, view-as search API-si və
RİM rəhbərinin bölmə görünürlüyü (rol icazələri dar olsa belə «Qruplar» var).
"""

from django.urls import reverse

from apps.accounts.services.person_search import person_q, tokens_of, tolerant_regex

from .test_view_as import PASSWORD, User, ViewAsTestBase, _add_member, _make_role


class PersonSearchUnitTest(ViewAsTestBase):
    def test_tokens_and_regex(self):
        self.assertEqual(tokens_of("  Aydan   Alyarova "), ["Aydan", "Alyarova"])
        self.assertEqual(tokens_of("a b c d e f"), ["a", "b", "c", "d"])
        self.assertEqual(tolerant_regex("is"), "[iıİI][sSşŞ]")
        # metasimvol qaçırılır; «a» 2026-09-26-dan «ə» ilə bir sinifdədir (core.search_text)
        self.assertEqual(tolerant_regex("a.b"), "[aAəƏ]\\.[bB]")
        self.assertIsNone(person_q("   ", ("first_name",)))

    def test_person_q_matches_name_order_and_diacritics(self):
        User.objects.create_user(
            "ismayil.huseynov", "ih@example.com", PASSWORD, first_name="İsmayıl", last_name="Hüseynov"
        )
        User.objects.create_user("aydan.alyarova", "aa@example.com", PASSWORD, first_name="Aydan", last_name="Alyarova")
        fields = ("username", "first_name", "last_name")
        for query, expected in (
            ("Aydan Alyarova", "aydan.alyarova"),
            ("alyarova aydan", "aydan.alyarova"),
            ("Ismayil Huseynov", "ismayil.huseynov"),
            ("HUSEYNOV", "ismayil.huseynov"),
            ("ismayil.hus", "ismayil.huseynov"),
        ):
            with self.subTest(query=query):
                names = list(User.objects.filter(person_q(query, fields)).values_list("username", flat=True))
                self.assertEqual(names, [expected])
        # İki token EYNİ adamda olmalıdır — «Aydan Hüseynov» heç kimi tapmır.
        self.assertFalse(User.objects.filter(person_q("Aydan Huseynov", fields)).exists())


class ViewAsSearchByFullNameTest(ViewAsTestBase):
    def test_search_api_finds_by_full_name_and_tolerates_diacritics(self):
        target = User.objects.create_user("aysu.meherremova", "am@example.com", PASSWORD)
        target.first_name, target.last_name = "Aysu", "Məhərrəmova"
        target.save(update_fields=["first_name", "last_name"])
        _add_member(target, self.org, self.student_role)
        self._login(self.admin)
        for query in ("Aysu Məhərrəmova", "Meherremova Aysu", "aysu meherr"):
            with self.subTest(query=query):
                response = self.client.get(reverse("accounts:view_as_search"), {"q": query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([r["username"] for r in response.json()["results"]], ["aysu.meherremova"])


class RimHeadSeesGroupsRegistryTest(ViewAsTestBase):
    def test_rim_head_gets_groups_registry_even_with_narrow_role_permissions(self):
        """Sahib 2026-09-21: «RİM rəhbəri Qruplar bölməsini görmür — bərpa et»."""
        role = _make_role(self.org, "ikt_rehber", 95, permissions=["journal.correct"])
        user = User.objects.create_user("rim_head", "rim@example.com", PASSWORD)
        _add_member(user, self.org, role)
        self._login(user)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        sections = set(response.context["allowed_sections"])
        self.assertIn("groups-registry", sections)
        self.assertIn("org-structure-tree", sections)
