"""«Müəllimlər» / «Tələbələr» kataloqu — scope, icazə və filtr müqavilələri.

Kilidlənən davranışlar:

1. **Scope matrisi** — dekan yalnız öz fakültəsini, kafedra müdiri öz
   kafedrasını, rektor bütün təşkilatı görür.
2. **Fail-closed** — ``scope_unit`` təyin EDİLMƏMİŞ UNIT rolu BOŞ siyahı alır
   (əvvəllər bu sinif səhv bütün təşkilatı açırdı — BLOKER tapıntı).
3. **PII qapıları** — əlaqə və demoqrafiya sütunları AYRI açarlarla gəlir:
   siyahını görmək telefon nömrəsini görmək demək deyil.
4. **«Təyin edilməyib» səbəti** — cins/yaş datası seyrək olduğu üçün naməlum
   səbətlər açıq şəkildə filtrlənə bilir.
"""

from __future__ import annotations

from datetime import date

from django.test import RequestFactory, TestCase

from apps.accounts.models import UserProfile
from apps.accounts.services import people
from apps.accounts.services.people.constants import DEFAULT_PAGE_SIZE, TEACHER_SORT_OPTIONS
from core.rls import bypass_rls

from .people_fixture import PeopleFixture


def _request(user, organization):
    request = RequestFactory().get("/accounts/profile/")
    request.user = user
    request.organization = organization
    return request


def _filters(**params):
    return people.parse_filters(params, sort_options=TEACHER_SORT_OPTIONS, default_page_size=DEFAULT_PAGE_SIZE)


class PeopleDirectoryTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()

    def actor_for(self, user):
        return people.resolve_actor(_request(user, self.fx.org))

    def teacher_names(self, user, **params):
        actor = self.actor_for(user)
        with bypass_rls():
            payload = people.build_teachers_page(actor=actor, filters=_filters(**params))
        return payload, {row["username"] for row in payload["results"]}

    def student_names(self, user, **params):
        actor = self.actor_for(user)
        with bypass_rls():
            payload = people.build_students_page(actor=actor, filters=_filters(**params))
        return payload, {row["username"] for row in payload["results"]}


class ScopeMatrixTest(PeopleDirectoryTestBase):
    def test_rector_sees_every_teacher(self):
        _payload, names = self.teacher_names(self.fx.rector)
        self.assertIn("ppl_teacher_a", names)
        self.assertIn("ppl_teacher_b", names)

    def test_dean_sees_only_own_faculty_teachers(self):
        _payload, names = self.teacher_names(self.fx.dean_a)
        self.assertIn("ppl_teacher_a", names)
        self.assertNotIn(
            "ppl_teacher_b",
            names,
            "Dekan A başqa fakültənin müəllimini gördü — scope sızması.",
        )

    def test_chair_sees_only_own_department(self):
        _payload, names = self.teacher_names(self.fx.chair_a1)
        self.assertEqual(names, {"ppl_teacher_a"})

    def test_dean_sees_only_own_faculty_students(self):
        _payload, names = self.student_names(self.fx.dean_a)
        self.assertIn("ppl_student_a", names)
        self.assertNotIn("ppl_student_b", names)

    def test_rector_sees_every_student(self):
        _payload, names = self.student_names(self.fx.rector)
        self.assertIn("ppl_student_a", names)
        self.assertIn("ppl_student_b", names)

    def test_unscoped_unit_manager_sees_nothing(self):
        """FAIL-CLOSED: scope_unit-siz dekan BOŞ siyahı alır, bütün org DEYİL."""
        payload, names = self.teacher_names(self.fx.dean_unscoped)
        self.assertEqual(names, set())
        self.assertEqual(payload["total"], 0)

        payload, names = self.student_names(self.fx.dean_unscoped)
        self.assertEqual(names, set())
        self.assertEqual(payload["total"], 0)

    def test_plain_teacher_has_no_catalog_access(self):
        payload, names = self.teacher_names(self.fx.teacher_a)
        self.assertFalse(payload["has_access"])
        self.assertEqual(names, set())

        payload, names = self.student_names(self.fx.student_a)
        self.assertFalse(payload["has_access"])
        self.assertEqual(names, set())


class PermissionGateTest(PeopleDirectoryTestBase):
    def test_contacts_hidden_without_permission(self):
        """`people.view_contacts` olmayan kafedra müdiri telefon/FİN görmür."""
        _payload, _names = self.teacher_names(self.fx.chair_a1)
        actor = self.actor_for(self.fx.chair_a1)
        self.assertFalse(actor.can_view_contacts)
        with bypass_rls():
            payload = people.build_teachers_page(actor=actor, filters=_filters())
        row = payload["results"][0]
        self.assertEqual(row["phone"], "")
        self.assertEqual(row["email"], "")
        self.assertEqual(row["fin"], "")

    def test_contacts_visible_with_permission(self):
        actor = self.actor_for(self.fx.dean_a)
        self.assertTrue(actor.can_view_contacts)
        with bypass_rls():
            payload = people.build_teachers_page(actor=actor, filters=_filters())
        row = next(r for r in payload["results"] if r["username"] == "ppl_teacher_a")
        self.assertTrue(row["phone"])

    def test_demographics_hidden_without_permission(self):
        actor = self.actor_for(self.fx.chair_a1)
        self.assertFalse(actor.can_view_demographics)
        with bypass_rls():
            payload = people.build_teachers_page(actor=actor, filters=_filters())
        row = payload["results"][0]
        self.assertEqual(row["gender"], "")
        self.assertIsNone(row["age"])

    def test_demographics_visible_with_permission(self):
        actor = self.actor_for(self.fx.dean_a)
        with bypass_rls():
            payload = people.build_teachers_page(actor=actor, filters=_filters())
        row = next(r for r in payload["results"] if r["username"] == "ppl_teacher_a")
        self.assertEqual(row["gender"], UserProfile.Gender.MALE)
        self.assertIsNotNone(row["age"])

    def test_granted_permissions_are_reported(self):
        actor = self.actor_for(self.fx.dean_a)
        self.assertIn("people.view_teachers", actor.granted_permissions)
        self.assertIn("people.manage_status", actor.granted_permissions)
        actor = self.actor_for(self.fx.chair_a1)
        self.assertNotIn("people.manage_status", actor.granted_permissions)


class FilterContractTest(PeopleDirectoryTestBase):
    def test_search_matches_patronymic_in_any_word_order(self):
        _payload, names = self.teacher_names(self.fx.rector, q="Əliyev Elvin")
        self.assertEqual(names, {"ppl_teacher_a"})
        _payload, reversed_names = self.teacher_names(self.fx.rector, q="Elvin Əliyev")
        self.assertEqual(reversed_names, names)

    def test_structure_filter_narrows_within_scope(self):
        _payload, names = self.teacher_names(self.fx.rector, faculty=str(self.fx.faculty_b.pk))
        self.assertEqual(names, {"ppl_teacher_b"})

    def test_structure_filter_cannot_widen_scope(self):
        """Dekan A əl ilə B fakültəsini yazsa BOŞ nəticə alır, B-nin siyahısını yox."""
        payload, names = self.teacher_names(self.fx.dean_a, faculty=str(self.fx.faculty_b.pk))
        self.assertEqual(names, set())
        self.assertEqual(payload["total"], 0)

    def test_gender_unspecified_bucket_is_filterable(self):
        """Datanın ~79 %-i «təyin edilməyib»dir — səbət ünvanlana bilməlidir."""
        _payload, names = self.teacher_names(self.fx.rector, gender="unspecified")
        self.assertIn("ppl_teacher_b", names)
        self.assertNotIn("ppl_teacher_a", names)

    def test_gender_known_bucket(self):
        _payload, names = self.teacher_names(self.fx.rector, gender="male")
        self.assertEqual(names, {"ppl_teacher_a"})

    def test_age_range_uses_birth_date(self):
        today = date.today()
        age = today.year - 1985 - ((today.month, today.day) < (5, 10))
        _payload, names = self.teacher_names(self.fx.rector, age_min=age, age_max=age)
        self.assertEqual(names, {"ppl_teacher_a"})

    def test_age_unknown_bucket_inverts_the_filter(self):
        _payload, names = self.teacher_names(self.fx.rector, age="unknown")
        self.assertIn("ppl_teacher_b", names)
        self.assertNotIn("ppl_teacher_a", names)

    def test_status_filter_separates_blocked_accounts(self):
        with bypass_rls():
            self.fx.teacher_b.is_active = False
            self.fx.teacher_b.save(update_fields=["is_active"])
        try:
            _payload, active_names = self.teacher_names(self.fx.rector, status="active")
            _payload, blocked_names = self.teacher_names(self.fx.rector, status="blocked")
        finally:
            with bypass_rls():
                self.fx.teacher_b.is_active = True
                self.fx.teacher_b.save(update_fields=["is_active"])
        self.assertNotIn("ppl_teacher_b", active_names)
        self.assertEqual(blocked_names, {"ppl_teacher_b"})

    def test_subject_filter_uses_offerings(self):
        _payload, names = self.teacher_names(self.fx.rector, subject=str(self.fx.subject.pk))
        self.assertEqual(names, {"ppl_teacher_a"})

    def test_student_subject_filter_uses_enrollments(self):
        _payload, names = self.student_names(self.fx.rector, subject=str(self.fx.subject.pk))
        self.assertEqual(names, {"ppl_student_a"})

    def test_unknown_sort_falls_back_instead_of_failing(self):
        payload, _names = self.teacher_names(self.fx.rector, sort="; DROP TABLE")
        self.assertTrue(payload["has_access"])
        self.assertEqual(payload["filters"]["sort"], "name")


class RowShapeTest(PeopleDirectoryTestBase):
    def test_teacher_row_carries_structure_names(self):
        with bypass_rls():
            payload = people.build_teachers_page(actor=self.actor_for(self.fx.rector), filters=_filters())
        row = next(r for r in payload["results"] if r["username"] == "ppl_teacher_a")
        self.assertEqual(row["faculty_name"], "Fakültə A")
        self.assertEqual(row["kafedra_name"], "Kafedra A1")
        self.assertEqual(row["kind"], "teacher")

    def test_student_row_carries_group_and_program(self):
        with bypass_rls():
            payload = people.build_students_page(actor=self.actor_for(self.fx.rector), filters=_filters())
        row = next(r for r in payload["results"] if r["username"] == "ppl_student_a")
        self.assertEqual(row["group_name"], "Qrup A1-1")
        self.assertEqual(row["faculty_name"], "Fakültə A")
        self.assertIn("Proqram A", row["program_label"])
        self.assertEqual(row["admission_year"], 2024)

    def test_student_row_label_carries_the_official_program_code(self):
        """MUTASİYA QAPISI — `students.py` sətir etiketi ŞİFRSİZ qala bilməz.

        Əvvəlki test yalnız ``assertIn("Proqram A", …)`` yazırdı: etiket
        qurucusu ``program_display_label(...)`` → ``program_name``-ə endirilsə
        (şifr TAMAMİLƏ silinsə) test yenə keçirdi — mutasiya qaçırdı. Burada
        etiket ``Program.display_label`` ilə TAM bərabərliyə bağlanır, ona görə
        şifri atan hər dəyişiklik ÇÖKÜR.

        Sabit sətir yazılmır: gözlənilən dəyər modelin öz xassəsindən gəlir, ona
        görə etiket qaydası dəyişsə test qaydanı izləyir, köhnəlmir.
        """
        with bypass_rls():
            Program = self.fx.program_a.__class__
            Program.objects.filter(pk=self.fx.program_a.pk).update(
                official_code="6006022", legacy_official_code="050631"
            )
            program = Program.objects.get(pk=self.fx.program_a.pk)
            payload = people.build_students_page(actor=self.actor_for(self.fx.rector), filters=_filters())
        row = next(r for r in payload["results"] if r["username"] == "ppl_student_a")

        self.assertEqual(row["program_label"], program.display_label)
        self.assertEqual(row["program_label"], "Proqram A · 6006022")
        # Mutasiyanın öldürücü hissəsi: şifr etiketin İÇİNDƏ olmalıdır.
        self.assertIn("6006022", row["program_label"])
        self.assertNotEqual(row["program_label"], row["program_name"])

    def test_student_row_label_falls_back_to_the_legacy_code(self):
        """Yalnız-köhnə-şifrli ixtisas sətirdə ŞİFRSİZ görünə bilməz.

        `program_code` annotasiyası (SQL ``Coalesce``/``NullIf``) `display_code`
        ilə eyni geri çəkilməni etməlidir — əks halda ləğv olunmuş ixtisasın
        tələbəsi kataloqda şifrsiz qalır.
        """
        with bypass_rls():
            Program = self.fx.program_b.__class__
            Program.objects.filter(pk=self.fx.program_b.pk).update(official_code="", legacy_official_code="050401")
            program = Program.objects.get(pk=self.fx.program_b.pk)
            payload = people.build_students_page(actor=self.actor_for(self.fx.rector), filters=_filters())
        row = next(r for r in payload["results"] if r["username"] == "ppl_student_b")

        self.assertEqual(row["program_label"], program.display_label)
        self.assertEqual(row["program_label"], "Proqram B · 050401")

    def test_student_row_label_has_no_dangling_separator_without_a_code(self):
        """Şifrsiz ixtisasda ayırıcı ASILI qalmır (uydurma «—» da yoxdur)."""
        with bypass_rls():
            payload = people.build_students_page(actor=self.actor_for(self.fx.rector), filters=_filters())
        row = next(r for r in payload["results"] if r["username"] == "ppl_student_a")
        self.assertEqual(row["program_label"], "Proqram A")
        self.assertNotIn("·", row["program_label"])

    def test_students_can_be_found_by_the_program_code_shown_in_the_row(self):
        """AXTARIŞ İNVARİANTI — kataloq sətri şifri GÖSTƏRİR, deməli AXTARIR da.

        Bloker: operator cədvəldə «Proqram B · 050401» görürdü, eyni səhifənin
        axtarış qutusuna «050401» yazanda SIFIR nəticə alırdı — `search_q`
        yalnız şəxs sahələrinə (ad/username/email/FİN) baxırdı.
        """
        with bypass_rls():
            Program = self.fx.program_a.__class__
            Program.objects.filter(pk=self.fx.program_a.pk).update(
                official_code="6006022", legacy_official_code="050631"
            )
            Program.objects.filter(pk=self.fx.program_b.pk).update(official_code="", legacy_official_code="050401")

        for query, expected in (
            ("6006022", {"ppl_student_a"}),  # cari nəsil şifr
            ("050631", {"ppl_student_a"}),  # köhnə nəsil şifr (diplomdakı)
            ("050401", {"ppl_student_b"}),  # YALNIZ köhnə şifrli ixtisas
            ("Proqram B", {"ppl_student_b"}),  # ixtisasın adı
        ):
            with self.subTest(query=query):
                _payload, names = self.student_names(self.fx.rector, q=query)
                self.assertEqual(names, expected)

    def test_program_code_search_still_ands_the_other_tokens(self):
        """«ad + şifr» qarışıq sorğu AND semantikasını POZMUR."""
        with bypass_rls():
            Program = self.fx.program_a.__class__
            Program.objects.filter(pk=self.fx.program_a.pk).update(official_code="6006022")

        _payload, hit = self.student_names(self.fx.rector, q="Aysel 6006022")
        self.assertEqual(hit, {"ppl_student_a"})
        # Başqa tələbənin adı + bu şifr → heç nə (AND, OR deyil).
        _payload, miss = self.student_names(self.fx.rector, q="Bəxtiyar 6006022")
        self.assertEqual(miss, set())

    def test_teacher_catalog_search_is_unchanged(self):
        """Müəllim kataloqunda ixtisas anlayışı yoxdur — `extra` ora sızmır."""
        _payload, names = self.teacher_names(self.fx.rector, q="Əli")
        self.assertEqual(names, {"ppl_teacher_a"})

    def test_initials_replace_missing_avatar(self):
        with bypass_rls():
            payload = people.build_teachers_page(actor=self.actor_for(self.fx.rector), filters=_filters())
        row = next(r for r in payload["results"] if r["username"] == "ppl_teacher_a")
        self.assertEqual(row["avatar_url"], "")
        self.assertEqual(row["initials"], "ƏE")

    def test_each_person_appears_once_despite_multiple_memberships(self):
        """İkili rol (müəllim + kafedra müdiri) cədvəldə TƏK sətir olmalıdır."""
        from .people_fixture import add_membership

        with bypass_rls():
            add_membership(self.fx.org, self.fx.teacher_a, self.fx.role_chair, unit=self.fx.kafedra_a1)
        payload, names = self.teacher_names(self.fx.rector)
        usernames = [row["username"] for row in payload["results"]]
        self.assertEqual(usernames.count("ppl_teacher_a"), 1)
        self.assertIn("ppl_teacher_a", names)


class FilterOptionsTest(PeopleDirectoryTestBase):
    def test_options_are_populated_from_real_data(self):
        actor = self.actor_for(self.fx.rector)
        with bypass_rls():
            options = people.build_filter_options(actor=actor, kind="students", filters=_filters())
        self.assertTrue(options["has_access"])
        self.assertTrue(options["faculties"], "Fakültə açılışı BOŞ qalmamalıdır")
        self.assertTrue(options["kafedras"])
        self.assertTrue(options["groups"])
        self.assertTrue(options["programs"])
        self.assertTrue(options["subjects"])
        self.assertTrue(options["years"])

    def test_options_are_scope_limited(self):
        actor = self.actor_for(self.fx.dean_a)
        with bypass_rls():
            options = people.build_filter_options(actor=actor, kind="students", filters=_filters())
        faculty_names = {row["text"] for row in options["faculties"]}
        self.assertEqual(faculty_names, {"Fakültə A"})

    def test_gender_facet_always_reports_unspecified_bucket(self):
        actor = self.actor_for(self.fx.rector)
        with bypass_rls():
            options = people.build_filter_options(actor=actor, kind="teachers", filters=_filters())
        self.assertIn("unspecified", options["gender_facets"])
        self.assertGreaterEqual(options["gender_facets"]["unspecified"], 1)

    def test_demographics_facets_hidden_without_permission(self):
        actor = self.actor_for(self.fx.chair_a1)
        with bypass_rls():
            options = people.build_filter_options(actor=actor, kind="teachers", filters=_filters())
        self.assertFalse(options["can_filter_demographics"])
        self.assertEqual(options["demographics_coverage"]["total"], 0)


class SyncPeoplePermissionsCommandTest(PeopleDirectoryTestBase):
    """Mövcud təşkilatlara açar əlavə edən əmr — additive və opt-in olmalıdır."""

    def test_dry_run_does_not_write(self):
        from io import StringIO

        from django.core.management import call_command

        from apps.organizations.models import Role

        with bypass_rls():
            Role.objects.filter(organization=self.fx.org, name="chair_head").update(
                permissions=["unit.view"], is_system=True
            )
            out = StringIO()
            call_command("sync_people_permissions", org=self.fx.org.slug, stdout=out)
            permissions = Role.objects.get(organization=self.fx.org, name="chair_head").permissions
        self.assertIn("QURU İŞLƏYİŞ", out.getvalue())
        self.assertNotIn("people.view_teachers", permissions)

    def test_apply_adds_missing_keys_without_removing_existing(self):
        from django.core.management import call_command

        from apps.organizations.models import Role

        with bypass_rls():
            Role.objects.filter(organization=self.fx.org, name="chair_head").update(
                permissions=["unit.view"], is_system=True
            )
            call_command("sync_people_permissions", org=self.fx.org.slug, apply=True)
            permissions = Role.objects.get(organization=self.fx.org, name="chair_head").permissions
        self.assertIn("unit.view", permissions, "Mövcud açar silinməməlidir (additive).")
        self.assertIn("people.view_teachers", permissions)
        self.assertIn("people.view_students", permissions)
        self.assertNotIn("people.manage_status", permissions, "Kafedra müdirinə əməl açarı verilməməlidir.")

    def test_custom_roles_are_untouched(self):
        from django.core.management import call_command

        from apps.organizations.models import Role

        with bypass_rls():
            Role.objects.filter(organization=self.fx.org, name="dean").update(
                permissions=["unit.view"], is_system=False
            )
            call_command("sync_people_permissions", org=self.fx.org.slug, apply=True)
            permissions = Role.objects.get(organization=self.fx.org, name="dean").permissions
        self.assertEqual(permissions, ["unit.view"], "is_system olmayan rola toxunulmamalıdır.")
