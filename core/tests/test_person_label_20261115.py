"""«Soyad Ad Ata adı» — axtarış/seçici etiketinin vahid helper-i (sahib 2026-11-15)."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from core.person_names import person_label, person_label_from_parts


def _user(first="", last="", username="u1", patronymic=None):
    profile = None if patronymic is None else SimpleNamespace(patronymic=patronymic)
    return SimpleNamespace(first_name=first, last_name=last, username=username, profile=profile)


class PersonLabelTests(SimpleTestCase):
    def test_surname_first_with_patronymic(self):
        self.assertEqual(person_label(_user("Elvin", "Əliyev", patronymic="Səməd")), "Əliyev Elvin Səməd")

    def test_without_patronymic_or_profile(self):
        self.assertEqual(person_label(_user("Elvin", "Əliyev", patronymic="")), "Əliyev Elvin")
        self.assertEqual(person_label(_user("Elvin", "Əliyev")), "Əliyev Elvin")

    def test_placeholder_patronymic_is_dropped(self):
        self.assertEqual(person_label(_user("Aynur", "Məmmədova", patronymic=" - ")), "Məmmədova Aynur")

    def test_empty_name_falls_back_to_username(self):
        self.assertEqual(person_label(_user(" ", "", username="myedu.worker.7", patronymic="")), "myedu.worker.7")

    def test_none_user(self):
        self.assertEqual(person_label(None), "")

    def test_explicit_patronymic_skips_profile(self):
        user = SimpleNamespace(first_name="Elvin", last_name="Əliyev", username="e")  # profili yoxdur
        self.assertEqual(person_label(user, patronymic="Rəşad"), "Əliyev Elvin Rəşad")

    def test_from_parts(self):
        self.assertEqual(person_label_from_parts("Əliyev", "Elvin", "Səməd", "e"), "Əliyev Elvin Səməd")
        self.assertEqual(person_label_from_parts(None, None, None, "e"), "e")
        self.assertEqual(person_label_from_parts("  Quliyeva ", "Aysel", "", "a"), "Quliyeva Aysel")
