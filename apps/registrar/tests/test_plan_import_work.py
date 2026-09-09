"""«İşçi tədris planı» düzümünün təsnifat qaydaları (2026-09-10).

PDF oxunuşu burada sınanmır — o, xarici fayl tələb edir. Sınanan şey RİSKLİ
hissədir: nömrələnmiş seçmə blokun tanınması. Əgər blok tək fənn kimi
oxunsa, plana «1.Fəlsəfə 2. Sosiologiya 3.Məntiq» adlı UYDURMA fənn düşər.
"""

from django.test import SimpleTestCase

from apps.registrar.plan_import_work import is_enumerated_block


class EnumeratedBlockTest(SimpleTestCase):
    def test_numbered_list_in_one_cell_is_a_block(self):
        for name in (
            "1.Fəlsəfə 2. Multikultiralizmə giriş 3.Sosiologiya",
            "1.Azərbaycan iqtisadiyyatı 2.Müəssisənin(firmanın)iqtisadiyyatı",
            "III blok: 1. Reklam işinin təşkili 2. Menecmentin etikası",
        ):
            with self.subTest(name=name):
                self.assertTrue(is_enumerated_block(name))

    def test_single_subject_is_not_a_block(self):
        for name in (
            "Xarici dildə işgüzar və akademik kommunikasiya -1",
            "Ehtimal nəzəriyyəsi və riyazi statistika",
            "Mikroiqtisadiyyat",
        ):
            with self.subTest(name=name):
                self.assertFalse(is_enumerated_block(name))

    def test_leading_marker_means_a_block_fragment(self):
        """İşçi planda fənnin nömrəsi AYRICA sütundadır.

        Ona görə adın əvvəlindəki «1.» həmişə blok bəndidir — çox vaxt səhifə
        keçidində blokdan qopmuş hissədir. Bu qayda olmadan «1. Avropa
        ölkələri müasir beynəlxalq münasibətlər» kataloqa fənn kimi düşürdü.
        """
        for name in ("1.Mikroiqtisadiyyat", "1. Avropa ölkələri müasir beynəlxalq münasibətlər"):
            with self.subTest(name=name):
                self.assertTrue(is_enumerated_block(name))

    def test_pure_marker_noise_is_a_block(self):
        """«1. 2. 3.» — cədvəl qırığı, fənn deyil."""
        self.assertTrue(is_enumerated_block("1. 2. 3."))

    def test_empty_name_is_safe(self):
        self.assertFalse(is_enumerated_block(""))
        self.assertFalse(is_enumerated_block(None))
