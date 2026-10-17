"""PERF-1 (FIX-F, 2026-10-17) — qrup reyestri (F-08), autentifikasiya backend-i (F-12), tələbə kataloqu (F-13).

* F-08 — reyestr bütün əhatə qruplarını JOIN-suz oxuyur; ixtisas zənciri və TYUTOR yalnız səhifə sətirləri
  üçün bir sorğu ilə gəlir (əvvəl tyutoru olan hər sətir `unit.head` üçün ayrıca SELECT açırdı); qrup
  `settings` JSON-ları bir dəfə oxunur; `student_total` Python süzgəci yoxdursa alt-sorğu ilədir.
* F-12 — `get_user` istifadəçini profili ilə BİR sorğuda oxuyur; bloklanmış (`staged`/`archived`) hesab
  yenə `None`-dır; profilsiz hesab üçün «yoxdur» keşi qalmır.
* F-13 — dekanın tələbə siyahısı əhatə alt-ağacını vahid id-lərinə açıb `group_id IN (...)` ilə süzür
  (əvvəl `group.path LIKE` OR-u hər korrelyasiyalı alt-sorğuda bütün qeydləri skan edirdi); dəst eynidir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from apps.accounts.backends import EmailOrUsernameBackend
from apps.accounts.models import UserProfile
from apps.accounts.services import people
from apps.accounts.services.people.constants import DEFAULT_PAGE_SIZE, TEACHER_SORT_OPTIONS
from apps.organizations.models import OrgUnit
from apps.organizations.public import build_groups_registry
from core.constants import OrgUnitType, RoleScopeType
from core.rls import bypass_rls

from .people_fixture import PeopleFixture, add_membership, make_role, make_user

OFFICE_PERMS = ["unit.view", "unit.group_manage", "student.records_view"]


def _registry_request(user, organization, role, **params):
    request = RequestFactory().get("/accounts/profile/", params)
    request.user = user
    request.organization = organization
    request.org_permissions = list(role.permissions)
    return request


class GroupsRegistryQueryBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()
        with bypass_rls():
            cls.role_office = make_role(
                cls.fx.org, "office_pf1", level=60, scope_type=RoleScopeType.ORGANIZATION, permissions=OFFICE_PERMS
            )
            cls.office = make_user("pf1_office", first="Ofelya", last="Ofisova")
            add_membership(cls.fx.org, cls.office, cls.role_office)
        cls._n = 0

    def _add_group_with_tutor(self):
        type(self)._n += 1
        n = self._n
        with bypass_rls():
            tutor = make_user(f"pf1_tutor_{n}", first=f"Tyutor{n}", last="Tyutorov")
            return OrgUnit.objects.create(
                organization=self.fx.org,
                name=f"PF1 qrup {n:02d}",
                slug=f"pf1-qrup-{n}",
                unit_type=OrgUnitType.GROUP,
                parent=self.fx.specialty_a1,
                head=tutor,
                settings={"language_sector": "AZ" if n % 2 else "EN", "course_year": 1, "admission_year": 2024},
            )

    def _build(self, **params):
        with bypass_rls(), CaptureQueriesContext(connection) as ctx:
            payload = build_groups_registry(
                _registry_request(self.office, self.fx.org, self.role_office, **params), self.fx.org
            )
        return payload, len(ctx.captured_queries)

    def test_query_count_does_not_grow_with_tutored_rows(self):
        for _ in range(2):
            self._add_group_with_tutor()
        self._build()  # isti-tut
        small, small_count = self._build()
        for _ in range(8):
            self._add_group_with_tutor()
        large, large_count = self._build()

        self.assertEqual(len(large["rows"]), len(small["rows"]) + 8)
        self.assertEqual(
            small_count, large_count, f"{len(small['rows'])} sətir: {small_count}, {len(large['rows'])}: {large_count}"
        )
        tutored = [row for row in large["rows"] if row["name"].startswith("PF1 qrup")]
        self.assertTrue(all(row["tutor"].startswith("Tyutor") for row in tutored))
        self.assertTrue(
            all(row["specialty_name"] == "İxtisas A1" and row["faculty_name"] == "Fakültə A" for row in tutored)
        )

    def test_options_and_totals_unchanged(self):
        for _ in range(3):
            self._add_group_with_tutor()
        payload, _count = self._build()
        self.assertEqual([option["value"] for option in payload["language_options"]], ["AZ", "EN"])
        self.assertEqual([option["value"] for option in payload["language_form_options"]][:3], ["AZ", "EN", "RU"])
        self.assertIn("2024", [option["value"] for option in payload["admission_year_options"]])
        self.assertEqual(payload["student_total"], 2)  # fixture: A1-1 və B1-1 qruplarında bir tələbə
        # Python süzgəci (dil) — sayğac süzülmüş qruplar üzrə (id siyahısı yolu).
        filtered, _count = self._build(gr_lang="AZ")
        self.assertEqual(filtered["student_total"], 0)
        self.assertTrue(all(row["language_sector"] == "AZ" for row in filtered["rows"]))
        self.assertIn({"value": str(self.fx.group_a1.pk), "label": self.fx.group_a1.name}, payload["group_options"])


class BackendGetUserTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("pf1_backend", "pf1_backend@x.test", "pw")

    def test_user_and_profile_in_one_query(self):
        backend = EmailOrUsernameBackend()
        with CaptureQueriesContext(connection) as ctx:
            user = backend.get_user(self.user.pk)
            profile = user.profile
        self.assertEqual(len(ctx.captured_queries), 1, [q["sql"] for q in ctx.captured_queries])
        self.assertEqual(profile.user_id, self.user.pk)

    def test_archived_profile_still_returns_none(self):
        # `staged` hesab DB trigger-i ilə həmişə `is_active=False`-dur (aşağıdakı test); `archived` isə aktiv
        # istifadəçidir — girişin yeganə qapısı profil vəziyyətidir və o, JOIN-dan oxunur.
        backend = EmailOrUsernameBackend()
        self.assertIsNotNone(backend.get_user(self.user.pk))
        UserProfile.objects.filter(user=self.user).update(access_state=UserProfile.AccessState.ARCHIVED)
        self.assertIsNone(backend.get_user(self.user.pk))

    def test_inactive_user_is_none(self):
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertIsNone(EmailOrUsernameBackend().get_user(self.user.pk))

    def test_missing_profile_is_not_cached_as_absent(self):
        UserProfile.objects.filter(user=self.user).delete()
        user = EmailOrUsernameBackend().get_user(self.user.pk)
        self.assertIsNotNone(user)
        self.assertNotIn("profile", user._state.fields_cache)

    def test_authenticated_request_has_no_standalone_profile_select(self):
        client = Client()
        client.force_login(self.user)
        client.get("/zz-perf1-probe/")  # isti-tut
        with CaptureQueriesContext(connection) as ctx:
            client.get("/zz-perf1-probe/")
        standalone = [
            q["sql"]
            for q in ctx.captured_queries
            if 'FROM "accounts_userprofile"' in q["sql"] and '"auth_user"' not in q["sql"]
        ]
        self.assertEqual(standalone, [])


def _people_filters(**params):
    return people.parse_filters(params, sort_options=TEACHER_SORT_OPTIONS, default_page_size=DEFAULT_PAGE_SIZE)


class StudentDirectoryScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()
        with bypass_rls():
            # Fakültə A-nın DƏRİN alt-qrupu (ixtisas → qrup → alt qrup) — alt-ağac tam açılmalıdır.
            cls.deep_group = OrgUnit.objects.create(
                organization=cls.fx.org,
                name="Qrup A1-1 / alt",
                slug="pf1-qrup-a1-1-alt",
                unit_type=OrgUnitType.GROUP,
                parent=cls.fx.group_a1,
            )
            from apps.registrar.models import StudentAcademicRecord

            cls.deep_student = make_user("pf1_deep_student", first="Dərin", last="Dərinova")
            add_membership(cls.fx.org, cls.deep_student, cls.fx.role_student)
            StudentAcademicRecord.objects.create(
                organization=cls.fx.org,
                student=cls.deep_student,
                program=cls.fx.program_a,
                curriculum=cls.fx.curriculum_a,
                group=cls.deep_group,
                admission_year=2024,
            )

    def _names(self, user, **params):
        request = RequestFactory().get("/accounts/profile/")
        request.user = user
        request.organization = self.fx.org
        actor = people.resolve_actor(request)
        with bypass_rls(), CaptureQueriesContext(connection) as ctx:
            payload = people.build_students_page(actor=actor, filters=_people_filters(**params))
        return {row["username"] for row in payload["results"]}, ctx.captured_queries

    def test_dean_sees_own_subtree_without_path_like_scan(self):
        names, queries = self._names(self.fx.dean_a)
        self.assertIn("ppl_student_a", names)
        self.assertIn("pf1_deep_student", names)
        self.assertNotIn("ppl_student_b", names)
        listing = [
            q["sql"]
            for q in queries
            if 'FROM "auth_user"' in q["sql"] and "registrar_studentacademicrecord" in q["sql"]
        ]
        self.assertTrue(listing)
        # Əhatə qeydin qrupuna JOIN + `path LIKE` ilə deyil, `group_id IN (SELECT id FROM orgunit …)` ilə.
        for sql in listing:
            self.assertIn('"group_id" IN (SELECT U0."id" AS "pk" FROM "organizations_orgunit" U0', sql)
            # `path LIKE` yalnız kiçik `orgunit` alt-sorğusunda (U0), qeydin qrup JOIN-unda yox.
            self.assertEqual(sql.count('"path"::text LIKE'), sql.count('U0."path"::text LIKE'))

    def test_dean_count_constant_with_more_students(self):
        self._names(self.fx.dean_a)  # isti-tut
        _names, before = self._names(self.fx.dean_a)
        with bypass_rls():
            for index in range(5):
                self.fx.add_student(f"pf1_more_{index}", faculty="a")
        names, after = self._names(self.fx.dean_a)
        self.assertEqual(len(before), len(after))
        self.assertTrue({f"pf1_more_{index}" for index in range(5)} <= names)

    def test_unscoped_dean_still_sees_nothing(self):
        names, _queries = self._names(self.fx.dean_unscoped)
        self.assertEqual(names, set())
