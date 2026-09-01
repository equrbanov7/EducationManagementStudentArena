"""AXTARIŞ İNVARİANTI: **ekranda göstərilən hər şifr axtarışda da tapılmalıdır.**

Niyə ayrıca test faylı
----------------------
Bu, tək bir view-un davranışı deyil, ÇARPAZ qaydadır və məhz onun pozulması
real bloker idi:

``Program.display_label`` cari (NK 503/2024) şifr yoxdursa **köhnə** şifrə geri
çəkilir, amma ixtisas seçicisi yalnız ``official_code`` üzrə süzürdü. Nəticədə
istifadəçi ekranda «Dünya iqtisadiyyatı · 050401» görürdü, `050401` yazanda
**sıfır** nəticə alırdı — yalnız-köhnə-şifrli 6 proqram (050401, 050645,
050639, 050644, 050405, 060411) öz GÖSTƏRİLƏN şifri ilə tapıla bilmirdi.

Testlər etiketi «bilmir»: hər proqramın ``display_label``-indən şifr hissəsini
ÇIXARIB onu sorğu kimi verir. Yəni etiket qaydası dəyişsə (məsələn üçüncü nəsil
şifr əlavə olunsa) test avtomatik onu da tələb edir — sabit kodlanmış «050401»
siyahısına baxmır.

MUTASİYA SINAĞI: ``core.program_codes.PROGRAM_CODE_SEARCH_FIELDS``-dən
``legacy_official_code`` çıxarılsa bu faylın testləri ÇÖKMƏLİDİR.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.services.people.lookups import _program_options
from apps.organizations.models import Organization, OrgUnit
from apps.organizations.scoping import ORG_WIDE_SCOPE
from apps.registrar.models import Program
from core.constants import OrganizationType, OrgUnitType
from core.program_codes import program_code_search_q, program_display_label
from core.rls import bypass_rls

from .people_fixture import PeopleFixture

User = get_user_model()

#: Üç şifr forması — hər biri ayrı davranış yolunu təmsil edir.
#:
#: ``legacy_only`` MƏHZ blokerin nümunəsidir: yeni təsnifatda ləğv olunmuş
#: ixtisas, diplomda köhnə şifr yazılıb.
_PROGRAMS = (
    ("PBOTH", "Kompüter mühəndisliyi", "6006022", "050631"),
    ("PCURRENT", "İnformasiya təhlükəsizliyi", "6006017", ""),
    ("PLEGACY", "Dünya iqtisadiyyatı", "", "050401"),
    ("PNONE", "Ümumi idarəetmə", "", ""),
)


@override_settings(UNIVERSITY_MODE=True)
class ProgramCodeSearchInvariantTests(TestCase):
    """Göstərilən şifr → axtarışda tapılır (səth: `records_program_search`)."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("pcs_owner", "pcs_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="PCS Univ",
                slug="pcs-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="pcs-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.chair = OrgUnit.objects.create(
                organization=cls.org,
                name="Kafedra",
                slug="pcs-chair",
                unit_type=OrgUnitType.CHAIR,
                parent=cls.faculty,
            )
            cls.programs = {}
            for code, name, official, legacy in _PROGRAMS:
                cls.programs[code] = Program.objects.create(
                    organization=cls.org,
                    code=code,
                    name=name,
                    official_code=official,
                    legacy_official_code=legacy,
                    specialty_unit=cls.chair,
                )

    def _client(self):
        client = Client()
        client.force_login(self.owner)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _search(self, query):
        resp = self._client().get(reverse("accounts:records_program_search"), {"q": query})
        self.assertEqual(resp.status_code, 200)
        return resp.json()["results"]

    @staticmethod
    def _shown_code(program):
        """Etiketdə İSTİFADƏÇİYƏ göstərilən şifr hissəsi (sabit kodlanmır)."""
        label = program.display_label
        return label.split(" · ", 1)[1] if " · " in label else ""

    # ── İnvariantın özü ───────────────────────────────────────────────────
    def test_every_displayed_code_is_findable_by_that_code(self):
        """HƏR proqram üçün: etiketdəki şifri yaz → həmin proqram gəlsin.

        Bu, blokerin birbaşa reqressiya qapısıdır.
        """
        checked = 0
        for program in self.programs.values():
            shown = self._shown_code(program)
            if not shown:
                continue  # şifrsiz proqram — göstərilən şifr yoxdur, tələb də yoxdur
            checked += 1
            with self.subTest(program=program.name, code=shown):
                ids = {row["id"] for row in self._search(shown)}
                self.assertIn(
                    str(program.pk),
                    ids,
                    f"«{program.display_label}» ekranda «{shown}» şifri ilə görünür, "
                    f"amma həmin şifr üzrə axtarışda tapılmır.",
                )
        # Fixture həqiqətən şifrli proqram verib (boş döngü «yaşıl» olmasın).
        self.assertEqual(checked, 3)

    def test_legacy_only_program_is_found_by_its_legacy_code(self):
        """Blokerin dəqiq nümunəsi — «Dünya iqtisadiyyatı · 050401»."""
        legacy_only = self.programs["PLEGACY"]
        self.assertEqual(legacy_only.display_label, "Dünya iqtisadiyyatı · 050401")

        results = self._search("050401")
        self.assertEqual([row["id"] for row in results], [str(legacy_only.pk)])
        self.assertEqual(results[0]["text"], "Dünya iqtisadiyyatı · 050401")

    def test_dual_code_program_is_found_by_both_generations(self):
        """Hər iki şifri olan proqram İKİSİ ilə də tapılır (köhnəsi diplomdadır)."""
        both = self.programs["PBOTH"]
        for query in ("6006022", "050631"):
            with self.subTest(query=query):
                self.assertIn(str(both.pk), {row["id"] for row in self._search(query)})

    def test_search_still_matches_the_program_name(self):
        """Şifr axtarışı ad axtarışını ƏVƏZ ETMİR — ikisi də işləyir."""
        self.assertIn(
            str(self.programs["PNONE"].pk),
            {row["id"] for row in self._search("Ümumi idarəetmə")},
        )

    def test_search_does_not_leak_the_internal_myedu_code(self):
        """Daxili ``Program.code`` NƏ axtarılır, NƏ göstərilir."""
        self.assertEqual(self._search("PLEGACY"), [])
        for row in self._search("iqtisadiyyatı"):
            self.assertNotIn("PLEGACY", row["text"])

    def test_unrelated_code_returns_nothing(self):
        """Yalançı-pozitiv yoxdur: mövcud olmayan şifr boş nəticə verir."""
        self.assertEqual(self._search("999999"), [])

    # ── Filtr açılışı eyni etiketi qurur ──────────────────────────────────
    def test_people_catalog_filter_shows_the_same_codes(self):
        """İnsanlar kataloqunun «İxtisas» filtri də şifrli etiket verir.

        Əvvəl bu səth sahələri ƏL İLƏ birləşdirirdi və yalnız cari şifrə
        baxırdı — yalnız-köhnə-şifrli proqram orada şifrsiz görünürdü.
        """
        with bypass_rls():
            options = _program_options(self.org, ORG_WIDE_SCOPE)
        by_id = {row["id"]: row["text"] for row in options}
        for program in self.programs.values():
            with self.subTest(program=program.name):
                self.assertEqual(by_id[str(program.pk)], program.display_label)


@override_settings(UNIVERSITY_MODE=True)
class GlobalSearchProgramCodeInvariantTests(TestCase):
    """⌘K qlobal axtarışı — alt sətirdə GÖSTƏRİLƏN şifr axtarıla bilməlidir.

    Bu səth `templates/base.html`-dədir, yəni HƏR autentifikasiya olunmuş
    səhifədə. Tələbə nəticəsinin alt sətri ``program.display_label`` çap edir
    («Dünya iqtisadiyyatı · 050401»), amma süzgəc yalnız ad/username/email üzrə
    idi: istifadəçi eyni qutuda GÖRDÜYÜ şifri yazanda SIFIR nəticə alırdı.
    """

    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()
        with bypass_rls():
            Program.objects.filter(pk=cls.fx.program_a.pk).update(
                official_code="6006022", legacy_official_code="050631"
            )
            Program.objects.filter(pk=cls.fx.program_b.pk).update(official_code="", legacy_official_code="050401")
            cls.program_a = Program.objects.get(pk=cls.fx.program_a.pk)
            cls.program_b = Program.objects.get(pk=cls.fx.program_b.pk)

    def _client(self):
        client = Client()
        client.force_login(self.fx.rector)
        session = client.session
        session["active_organization"] = self.fx.org.slug
        session.save()
        return client

    def _students(self, query):
        with bypass_rls():
            resp = self._client().get(reverse("accounts:global_search"), {"q": query})
        self.assertEqual(resp.status_code, 200)
        groups = {group["key"]: group["items"] for group in resp.json()["groups"]}
        return groups.get("students", [])

    @staticmethod
    def _shown_code(subtitle):
        """Alt sətirdə İSTİFADƏÇİYƏ göstərilən şifr — sabit kodlanmır."""
        head = subtitle.split(" · ")
        return head[1] if len(head) > 1 else ""

    def test_subtitle_shows_the_code_and_that_code_finds_the_student(self):
        """İnvariantın özü: göstərilən şifri geri yaz → eyni tələbə gəlsin."""
        by_name = self._students("Aysel")
        self.assertTrue(by_name, "Ad üzrə axtarış işləməlidir (baza yoxlanışı)")
        shown = self._shown_code(by_name[0]["subtitle"])
        self.assertEqual(shown, "6006022", "Alt sətir rəsmi şifri göstərməlidir")

        found = self._students(shown)
        self.assertEqual([item["title"] for item in found], [item["title"] for item in by_name])

    def test_legacy_only_program_is_findable_by_its_displayed_code(self):
        """Blokerin dəqiq nümunəsi — ekranda «· 050401», qutuya «050401»."""
        by_name = self._students("Bəxtiyar")
        self.assertTrue(by_name)
        self.assertIn("050401", by_name[0]["subtitle"])

        found = self._students("050401")
        self.assertEqual([item["title"] for item in found], [item["title"] for item in by_name])

    def test_both_generations_of_the_code_find_the_student(self):
        """Diplomda köhnə şifr yazılıb — o da tapılmalıdır."""
        for query in ("6006022", "050631"):
            with self.subTest(query=query):
                self.assertTrue(self._students(query), f"«{query}» şifri ilə tələbə tapılmadı")

    def test_program_name_also_matches(self):
        """Şifr axtarışı ad axtarışını ƏVƏZ ETMİR."""
        self.assertTrue(self._students("Proqram A"))

    def test_unrelated_code_returns_nothing(self):
        self.assertEqual(self._students("999999"), [])

    def test_internal_myedu_code_is_neither_shown_nor_searched(self):
        """Daxili ``Program.code`` sızmır."""
        self.assertEqual(self._students("PA"), [])
        for item in self._students("Aysel"):
            self.assertNotIn("PA ", item["subtitle"])

    def test_code_search_query_count_is_flat_in_the_number_of_rows(self):
        """Performans qapısı: N+1 YOXDUR — sorğu sayı sətir sayından ASILI deyil.

        Bu səth HƏR səhifədədir, ona görə şifr süzgəci sətir başına əlavə sorğu
        açsa, xərc bütün sayta yayılır. ``program``/``group`` onsuz da
        ``select_related``-dədir; şifr filtri həmin forward-FK join-unu təkrar
        işlədir, yeni tur açmır.
        """
        client = self._client()
        url = reverse("accounts:global_search")
        with bypass_rls():
            # İSTİLİK turu: ilk sorğu sessiya/icazə üçün birdəfəlik lazy yükləmə
            # edir — ölçmə ondan SONRA başlayır, əks halda fərq N+1 deyil, warm-up
            # olur.
            client.get(url, {"q": "6006022"})
            with CaptureQueriesContext(connection) as one_row:
                first = client.get(url, {"q": "6006022"})
            for index in range(3):
                self.fx.add_student(f"pcs_extra_{index}", faculty="a", first=f"Əlavə{index}", last="Tələbəyev")
            with CaptureQueriesContext(connection) as many_rows:
                second = client.get(url, {"q": "6006022"})

        def student_count(response):
            groups = {group["key"]: group["items"] for group in response.json()["groups"]}
            return len(groups.get("students", []))

        # Test boş qaçmasın: sətir sayı HƏQİQƏTƏN artmalıdır.
        self.assertEqual(student_count(first), 1)
        self.assertEqual(student_count(second), 4)
        self.assertEqual(len(many_rows.captured_queries), len(one_row.captured_queries))

    def test_code_search_joins_the_program_table_once(self):
        """Şifr filtri ƏLAVƏ JOIN açmır — `select_related` join-u təkrar işlənir."""
        from django.apps import apps as django_apps

        from core.program_codes import program_code_search_q

        Record = django_apps.get_model("registrar", "StudentAcademicRecord")
        with bypass_rls():
            sql = str(
                Record.objects.filter(organization=self.fx.org)
                .filter(program_code_search_q("6006022", prefix="program__"))
                .select_related("student", "program", "group")
                .query
            )
        self.assertEqual(sql.count('JOIN "registrar_program"'), 1, sql)


class ProgramCodeSearchQTests(TestCase):
    """``program_code_search_q`` — saf qatın davranışı (DB-siz semantika)."""

    def test_blank_query_is_a_no_op(self):
        self.assertEqual(len(program_code_search_q("   ").children), 0)

    def test_query_covers_both_generations(self):
        rendered = str(program_code_search_q("0504"))
        self.assertIn("official_code__icontains", rendered)
        self.assertIn("legacy_official_code__icontains", rendered)

    def test_prefix_is_applied_to_every_field(self):
        rendered = str(program_code_search_q("0504", prefix="program__"))
        self.assertIn("program__official_code__icontains", rendered)
        self.assertIn("program__legacy_official_code__icontains", rendered)

    def test_label_falls_back_to_the_legacy_code(self):
        """Etiket qaydası ilə axtarış qaydası eyni sahə dəstinə baxır."""
        self.assertEqual(program_display_label("Dünya iqtisadiyyatı", "", "050401"), "Dünya iqtisadiyyatı · 050401")
        self.assertNotIn("·", program_display_label("Ümumi idarəetmə", "", ""))
