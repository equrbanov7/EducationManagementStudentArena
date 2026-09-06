"""Heyət siyahısının oxunması və vəzifə → rol xəritəsi (2026-09-06 sahib tapşırığı)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.accounts.services import staff_roster as roster


class ParseRowsTest(SimpleTestCase):
    ROWS = [
        ("Qəyyumlar şurası", ""),
        ("Bağırov Hüseynqulu Seyid", "Sədir"),
        ("Prorektor", ""),
        ("Bağırov Rəşad Hüseynqulu", "İcraçı prorektor"),
        ("Babayeva Nigar Mais", ""),  # vəzifə mətni boşdur, amma bu ŞƏXSdir
        ("Elmi Kitabxana", ""),
        ("Novruzova Rəhiməxanım Bayram", "Kitabxanaçı"),
    ]

    def test_headers_are_not_treated_as_people(self):
        people = roster.parse_rows(self.ROWS)
        names = [person["name"] for person in people]
        self.assertNotIn("Qəyyumlar şurası", names)
        self.assertNotIn("Elmi Kitabxana", names)
        self.assertEqual(len(people), 4)

    def test_person_with_empty_position_keeps_its_section(self):
        people = roster.parse_rows(self.ROWS)
        nigar = next(person for person in people if person["name"].startswith("Babayeva"))
        self.assertEqual(nigar["section"], "Prorektor")

    def test_looks_like_person_rejects_unit_names(self):
        self.assertTrue(roster.looks_like_person("Bağırov Rəşad Hüseynqulu"))
        self.assertFalse(roster.looks_like_person("Tədrisin Təşkili və idarə olunması"))
        self.assertFalse(roster.looks_like_person("Elmi Kitabxana"))


class RoleMappingTest(SimpleTestCase):
    def test_faculty_leadership(self):
        self.assertEqual(roster.role_for("İqtisadiyyat Məktəbi", "Dekan"), ("dean", True))
        self.assertEqual(roster.role_for("Ekologiya Məktəbi", "Dekan müvini"), ("vice_dean", True))
        self.assertEqual(roster.role_for("Filologiya və tərcümə məktəbi", "Müavin"), ("vice_dean", True))

    def test_every_prorektor_row_is_vice_rector(self):
        """Vəzifə mətni portfeldir («Elmi işlər üzrə») — bölmə həlledicidir."""
        for title in ("İcraçı prorektor", "Elmi işlər üzrə", "Ümumi İşlər üzrə", ""):
            self.assertEqual(roster.role_for("Prorektor", title), ("vice_rector", True), title)

    def test_kafedra_head_and_staff(self):
        self.assertEqual(roster.role_for("Tarix kafedrası", "Müdir"), ("chair_head", True))
        self.assertEqual(roster.role_for("Tarix kafedrası", "Laborant"), ("lab_assistant", True))
        # Kafedrada «müdir müavini» rəhbər DEYİL — uydurulmuş rol verilmir.
        self.assertEqual(roster.role_for("Tarix kafedrası", "Müdir müavini"), (roster.FALLBACK_ROLE, False))

    def test_named_centres(self):
        """Türk «İ» kiçildikdə birləşən nöqtə verir — folding olmasa bu tutmur."""
        self.assertEqual(roster.role_for("Rəqəmsal İnkişaf mərkəzi", "Müdir"), ("ikt_rehber", True))
        self.assertEqual(roster.role_for("Rəqəmsal İnkişaf mərkəzi", "Proqramçı"), ("rim_staff", True))
        self.assertEqual(roster.role_for("Rəqəmsal İnkişaf mərkəzi", "Müdir müavini"), ("rim_staff", True))
        self.assertEqual(roster.role_for("Imtahan Mərkəzi", "Müdir"), ("exam_center_head", True))
        self.assertEqual(roster.role_for("Imtahan Mərkəzi", "Baş mütəxəssi"), ("exam_center_staff", True))
        self.assertEqual(roster.role_for("İnsan Resusları şöbəsi", "Mütəxəssis"), ("hr", True))

    def test_unknown_position_falls_back_without_inventing_a_role(self):
        for section, title in (
            ("Elmi Kitabxana", "Kitabxanaçı"),
            ("Beynəlxalq şöbə", "Koorinator"),
            ("Direktor", "İnkişaf üzrə direktor"),
        ):
            role, mapped = roster.role_for(section, title)
            self.assertEqual(role, roster.FALLBACK_ROLE, f"{section}/{title}")
            self.assertFalse(mapped)

    def test_bas_direktor_maps_to_rector(self):
        """2026-09-06 sahib qərarı: «Baş direktor» = rektorla eyni səviyyə."""
        self.assertEqual(roster.role_for("Direktor", "Baş direktor"), ("rector", True))
        # Siyahıdakı əsl yazı səhvi («Baş dirketor») da tutulmalıdır.
        self.assertEqual(roster.role_for("Direktor", "Baş dirketor"), ("rector", True))
        # Eyni bölmədəki QOHUM vəzifə qərara düşməyib — uydurulmur.
        self.assertEqual(roster.role_for("Direktor", "İnkişaf üzrə direktor"), (roster.FALLBACK_ROLE, False))

    def test_qeyyumlar_surasi_maps_to_trustee(self):
        """2026-09-06 sahib qərarı: bölmənin hər üzvü — vəzifədən asılı olmayaraq."""
        for title in ("Sədir", "Sədr", "Üzv", ""):
            self.assertEqual(roster.role_for("Qəyyumlar şurası", title), ("trustee", True), title)
        # Case/Türk «İ» folding-ə davamlı olmalıdır (bax `_FOLD`/`_norm`).
        self.assertEqual(roster.role_for("QƏYYUMLAR ŞURASI", "Sədir"), ("trustee", True))
        self.assertEqual(roster.role_for("qəyyumlar şurası", "Sədir"), ("trustee", True))

    def test_unmatched_section_head_maps_to_admin_unit_head(self):
        """2026-09-06 sahib qərarı: qarşılıqsız bölmədə «Müdir» artıq member deyil."""
        for section in ("Arxiv şöbəsi", "Beynəlxalq şöbə", "Maliyyə və Mühasibat şöbəsi"):
            self.assertEqual(roster.role_for(section, "Müdir"), ("admin_unit_head", True), section)
        # «Müdir müavini» rəhbər DEYİL — bu qərara aid deyil, əvvəlki kimi qalır.
        self.assertEqual(roster.role_for("Arxiv şöbəsi", "Müdir müavini"), (roster.FALLBACK_ROLE, False))
        # Qarşılığı OLAN bölmələrdə mövcud domen-spesifik rol dəyişməyib.
        self.assertEqual(roster.role_for("Tarix kafedrası", "Müdir"), ("chair_head", True))


class NameHelpersTest(SimpleTestCase):
    def test_split_name_uses_surname_first_order(self):
        self.assertEqual(roster.split_name("Bağırov Rəşad Hüseynqulu"), ("Rəşad", "Bağırov"))

    def test_username_seed_is_ascii(self):
        seed = roster.username_seed("Şəfiyeva Şəlalə Firdovsi")
        self.assertEqual(seed, "s.sefiyeva")
        self.assertTrue(seed.replace(".", "").isascii())


class UnitMatchTest(SimpleTestCase):
    class _Unit:
        def __init__(self, name):
            self.name = name

    def test_exact_and_fuzzy_matches(self):
        units = [self._Unit("Azərbaycan dili və ədəbiyyatı"), self._Unit("Tarix və fəlsəfə")]
        # Siyahıda yazı səhvi var («Azərbbaycan») — simvol oxşarlığı tutur.
        matched = roster.match_unit("Azərbbaycan dili və ədəbiyyat kafedrası", units)
        self.assertIsNotNone(matched)
        self.assertEqual(matched.name, "Azərbaycan dili və ədəbiyyatı")

    def test_unknown_section_returns_none(self):
        units = [self._Unit("Tarix və fəlsəfə")]
        self.assertIsNone(roster.match_unit("Maliyyə və Mühasibat şöbəsi", units))
