"""Sahib 2026-10-23: dərs yükü faylındakı müəllim adı → hesab (hərf səhvinə dözümlü) və ya FİN-siz yeni hesab.

* Xanadakı elmi dərəcə / vəzifə / ştat qeydi / il atılır, «dos.Ağayeva» kimi yapışıq yazı ayrılır.
* Eyni ad + soyad, FƏRQLİ ata adı → başqa adamdır: yeni hesab (``created_namesake``), mövcud hesaba TOXUNULMUR.
* Eyni adlı iki hesab, ata adı yoxdur → ``ambiguous`` — təxmin yoxdur, hesab yaradılmır.
* Bloklanmış hesaba uyğunluq → ``blocked`` (təkrar hesab açılmır).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.accounts.models import UserProfile
from apps.accounts.services.teacher_roster.chair_teachers import ChairTeacherResolver, person_name, split_name
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from core.constants import OrganizationType, OrgUnitType

User = get_user_model()


class SplitNameTests(SimpleTestCase):
    def test_degree_position_and_year_are_dropped(self):
        cases = {
            "b.ü.f.d. Məmmədov Ayaz Məmməd oğlu": ["Məmmədov", "Ayaz", "Məmməd", "oğlu"],
            "b.ü.f.d.  dos.Ağayeva Səltənət Əli qızı": ["Ağayeva", "Səltənət", "Əli", "qızı"],
            "baş müəllim İsmayılova İlahə 2019-cu ildən işləyir": ["İsmayılova", "İlahə"],
            "MƏMMƏDOV AYAZ": ["Məmmədov", "Ayaz"],
            "prof. Qazı-zadə Elnarə": ["Qazı-zadə", "Elnarə"],
        }
        for text, words in cases.items():
            self.assertEqual(split_name(text)[0], words, text)

    def test_initials(self):
        self.assertEqual(split_name("Məmmədov A.M."), (["Məmmədov"], ["a", "m"]))

    def test_person_name(self):
        name = person_name(["Ağayeva", "Səltənət", "Əli", "qızı"])
        self.assertEqual((name.last, name.first, name.patronymic), ("Ağayeva", "Səltənət", "Əli"))
        self.assertIsNone(person_name(["Məmmədov"]))


class ChairTeacherResolverTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user("ct_owner", "o@x.test", "pw")
        self.org = Organization.objects.create(
            name="CT", slug="ct", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
        )
        self.chair = OrgUnit.objects.create(organization=self.org, name="Xarici dillər", unit_type=OrgUnitType.CHAIR)
        self.role, _ = Role.objects.update_or_create(
            organization=self.org,
            name="teacher",
            defaults={"display_name": "Teacher", "level": 30, "permissions": ["grade.input"], "is_active": True},
        )
        self.actor = User.objects.create_superuser("ct_admin", "a@x.test", "pw")

    def _teacher(self, username, first, last, patronymic="", *, active=True):
        user = User.objects.create_user(username, f"{username}@x.test", "pw", first_name=first, last_name=last)
        UserProfile.objects.filter(user=user).update(patronymic=patronymic)
        Membership.objects.create(
            user=user, organization=self.org, role=self.role, scope_unit=self.chair, is_active=True
        )
        if not active:
            User.objects.filter(pk=user.pk).update(is_active=False)
        return user

    def _resolver(self):
        return ChairTeacherResolver(self.org, self.chair, actor_user=self.actor, apply=True, tag="test")

    def test_namesake_with_other_patronymic_gets_a_new_account(self):
        tahir = self._teacher("fidan.eliyeva7", "Fidan", "Əliyeva", "Tahir")
        result = self._resolver().resolve("Əliyeva Fidan Elşən qızı")
        self.assertEqual(result.status, "created_namesake")
        self.assertNotEqual(result.user.pk, tahir.pk)
        self.assertEqual(result.user.profile.patronymic, "Elşən")
        self.assertIsNone(result.user.profile.fin)
        self.assertFalse(result.user.has_usable_password())
        self.assertIn("fidan.eliyeva7", result.candidates)

    def test_one_letter_patronymic_difference_is_matched_with_warning(self):
        tahir = self._teacher("fidan.eliyeva7", "Fidan", "Əliyeva", "Tahir")
        result = self._resolver().resolve("Əliyeva Fidan Mahir qızı")
        self.assertEqual((result.status, result.user), ("patronymic_similar", tahir))

    def test_typo_and_cache(self):
        sekine = self._teacher("sekine.h", "Səkinə", "Həsənova", "Ramiz")
        resolver = self._resolver()
        self.assertEqual(resolver.resolve("Həsənova Səkinə Ramiz qızı").user, sekine)
        self.assertEqual(resolver.resolve("Hesenova Sekine Ramiz").user, sekine)  # diakritiksiz yazı
        typo = resolver.resolve("Həsənva Səkinə Ramiz")
        self.assertEqual((typo.status, typo.user), ("fuzzy", sekine))
        self.assertEqual(resolver.resolve("Həsənova S.R.").user, sekine)

    def test_two_namesakes_without_patronymic_are_not_guessed(self):
        self._teacher("aysel.q", "Aysel", "Quliyeva", "Rauf")
        self._teacher("aysel.q2", "Aysel", "Quliyeva", "Elçin")
        users = User.objects.count()
        result = self._resolver().resolve("Quliyeva Aysel")
        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(result.user)
        self.assertEqual(User.objects.count(), users)

    def test_blocked_account_is_not_duplicated(self):
        self._teacher("rehile.q", "Rəhilə", "Qorçuyeva", "Vaqif", active=False)
        users = User.objects.count()
        result = self._resolver().resolve("Qorçuyeva Rəhilə Vaqif")
        self.assertEqual(result.status, "blocked")
        self.assertEqual(User.objects.count(), users)

    def test_same_new_name_twice_creates_one_account(self):
        resolver = self._resolver()
        first = resolver.resolve("dos. Quliyev Tural Vaqif oğlu")
        second = resolver.resolve("Quliyev Tural Vaqif")
        self.assertEqual(first.status, "created")
        self.assertEqual(first.user.pk, second.user.pk)
        self.assertEqual(User.objects.filter(last_name="Quliyev").count(), 1)
        self.assertEqual(first.user.profile.academic_title, "docent")
