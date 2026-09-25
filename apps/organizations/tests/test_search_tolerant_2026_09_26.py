"""Dözümlü axtarış — «Qruplar» reyestri, namizəd seçicisi, struktur (sahib 2026-09-26).

Sahib: «qrup nömrəsi «234 K ing»dir, «234king» və s. kombinasiyada da işləsin; az
dili hərfləri ilə yazanda en dilə olan nəticə də gəlsin». Kanonik API:
``core.search_text.tolerant_q`` (qrup adı/kodu kod rejimində, şəxs adları normal).
"""

from django.contrib.auth import get_user_model

from apps.accounts.tests.test_groups_registry_add_students import _AddStudentsBase
from apps.organizations.models import OrgUnit
from apps.organizations.structure_views._shared import head_candidate_memberships
from core.constants import OrgUnitType

User = get_user_model()


class GroupsRegistryTolerantSearchTest(_AddStudentsBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ing_group = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.specialty,
            unit_type=OrgUnitType.GROUP,
            name="234 K ing",
            slug="ds2-234-k-ing",
            settings={"language_sector": "EN", "course_year": 2},
        )
        cls.k1_group = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.specialty,
            unit_type=OrgUnitType.GROUP,
            name="234 K-1",
            slug="ds2-234-k-1",
            settings={"language_sector": "AZ", "course_year": 2},
        )

    def _names(self, query):
        response = self._fragment("teaching_office_head", "groups-registry", gr_q=query)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return {row["name"] for row in response.context["groups_registry_section"]["rows"]}

    def test_compact_spellings_find_the_english_sector_group(self):
        for query in ("234king", "234 K ing", "234-K-ing", "234k ing", "234KING", "234 king"):
            with self.subTest(query=query):
                self.assertEqual(self._names(query), {"234 K ing"})

    def test_short_prefix_finds_every_matching_group(self):
        names = self._names("234k")
        self.assertIn("234 K ing", names)
        self.assertIn("234 K-1", names)

    def test_numbered_subgroup_is_found_without_separators(self):
        self.assertEqual(self._names("234k1"), {"234 K-1"})

    def test_code_is_searched_in_compact_mode_too(self):
        self.assertIn(self.group_b.name, self._names("ke24b"))

    def test_blank_query_keeps_the_full_list(self):
        names = self._names("   ")
        self.assertTrue({"234 K ing", "234 K-1", self.group.name}.issubset(names))

    def test_unrelated_query_matches_nothing(self):
        self.assertEqual(self._names("999zz"), set())


class GroupCandidatesTolerantSearchTest(_AddStudentsBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        student = cls.free[0].student
        student.first_name, student.last_name = "Şahzad", "Əliyev"
        student.save(update_fields=["first_name", "last_name"])

    def _texts(self, query):
        response = self._client("teaching_office_head").get(self._candidates_url(), {"q": query})
        self.assertEqual(response.status_code, 200, response.content[:300])
        return [row["text"] for row in response.json()["results"]]

    def test_latin_spellings_find_the_azerbaijani_name(self):
        for query in ("Aliyev", "Eliyev", "Əliyev", "Sahzad", "Shahzad", "shahzad aliyev"):
            with self.subTest(query=query):
                texts = self._texts(query)
                self.assertEqual(len(texts), 1, texts)
                self.assertIn("Əliyev", texts[0])

    def test_program_code_is_searched_in_compact_mode(self):
        self.assertEqual(len(self._texts("6050-100")), 2)

    def test_unrelated_name_matches_nothing(self):
        self.assertEqual(self._texts("Məmmədzadə"), [])


class HeadCandidateTolerantSearchTest(_AddStudentsBase):
    def test_head_candidates_fold_azerbaijani_letters(self):
        user = self.users["teaching_office_head"]
        user.first_name, user.last_name = "Çingiz", "Əliyev"
        user.save(update_fields=["first_name", "last_name"])
        found = {m.user_id for m in head_candidate_memberships(self.org, search="chingiz aliyev")}
        self.assertIn(user.pk, found)
        self.assertEqual(list(head_candidate_memberships(self.org, search="Zzqx")), [])
