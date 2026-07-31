"""Terminologiya regressiya testləri (2026-07-31 auditi).

Nəyi qoruyur
------------
Kataloqun msgctxt-siz blokunda tərcümələr **əlifba sırası ilə sürüşmüşdü**: bir
çox giriş qonşusunun tərcüməsini daşıyırdı. Nəticə istifadəçi üçün təhlükəli
idi — EN/RU/TR interfeysdə «Kafedranı sil» düyməsi «Delete bank» yazırdı, yəni
istifadəçi silmək istəmədiyi obyekti silə bilərdi.

Bu testlər `docs/i18n/GLOSSARY.md`-dəki məcburi qarşılıqları **runtime-da**
(kompilyasiya olunmuş `.mo` üzərindən) yoxlayır. Yəni yalnız `.po` deyil,
`compilemessages` nəticəsi də yoxlanılır — `.mo` köhnə qalsa test düşür.

`scripts/check_i18n_catalogs.py` qapısı placeholder uyğunsuzluğunu və xam açar
sızmasını tutur, lakin **mənanı** yoxlaya bilmir. Məna qorunması buradadır.
"""

from django.test import TestCase
from django.utils import translation
from django.utils.translation import gettext, pgettext

#: Akademik struktur — sürüşmənin ən təhlükəli olduğu yer (silmə/redaktə düymələri).
STRUCTURE_TERMS = {
    "Kafedranı sil": {"en": "Delete department", "ru": "Удалить кафедру", "tr": "Bölümü sil"},
    "Kafedranı redaktə et": {"en": "Edit department", "ru": "Редактировать кафедру", "tr": "Bölümü düzenle"},
    "Fakültəni sil": {"en": "Delete faculty", "ru": "Удалить факультет", "tr": "Fakülteyi sil"},
    "Fakültə seçin": {"en": "Select faculty", "ru": "Выберите факультет", "tr": "Fakülte seçin"},
    "Fakültə yarat": {"en": "Create faculty", "ru": "Создать факультет", "tr": "Fakülte oluştur"},
    "Fakültə adı": {"en": "Faculty name", "ru": "Название факультета", "tr": "Fakülte adı"},
    "Bütün fakültələr": {"en": "All faculties", "ru": "Все факультеты", "tr": "Tüm fakülteler"},
}

#: Çoxmənalı sözlər — maşın tərcüməsi ardıcıl olaraq yanlış mənanı seçirdi.
AMBIGUOUS_TERMS = [
    # (msgctxt, msgid, {dil: gözlənilən})
    ("assignment.form.label", "grade", {"ru": "Оценка", "tr": "Not"}),
    ("assignment.detail", "table_grade", {"ru": "Оценка", "tr": "Not"}),
    ("profile.results", "score_label", {"ru": "Балл", "tr": "Puan"}),
    ("labs.template.lab_submissions", "table_score", {"ru": "Балл", "tr": "Puan"}),
]

#: Status etiketləri — düymə mətnləri ilə əvəzlənmişdi.
STATUS_TERMS = [
    (
        "exams.model.attempt.choice.status",
        "in_progress",
        {"az": "Davam edir", "en": "In progress", "ru": "В процессе", "tr": "Devam ediyor"},
    ),
    (
        "exams.model.attempt.choice.supervision_status",
        "removed",
        {"az": "Uzaqlaşdırılıb", "en": "Removed", "ru": "Удалён с экзамена", "tr": "Sınavdan çıkarıldı"},
    ),
    (
        "exams.model.attempt.choice.supervision_status",
        "locked",
        {"az": "Bloklanıb", "en": "Locked", "ru": "Заблокирован", "tr": "Kilitlendi"},
    ),
]

#: Bu sözlər tərcümədə HEÇ VAXT görünməməlidir — yanlış məna imzalarıdır.
FORBIDDEN_SENSES = {
    "ru": ("Цена", "Мед"),  # qiymət=price, bal=arı balı
    "tr": ("Fiyat", "Gol"),  # qiymət=price, hesab=futbol qolu
}


# QEYD: `SimpleTestCase` OLMAZ. Layihənin `conftest.py`-ında autouse
# `_rls_bypass_for_tests` fixture-ı var; postgres-də o, SQL icra edir və
# `SimpleTestCase` DB sorğularını qadağan etdiyi üçün `DatabaseOperationForbidden`
# atılır. sqlite-da RLS no-op olduğundan xəta lokal olaraq görünmür (CI-də
# tutuldu).
class StructureTerminologyTests(TestCase):
    """«Kafedranı sil» → «Delete bank» sinfindən sürüşmələr qayıtmasın."""

    def test_structure_buttons_keep_their_meaning(self):
        for source, expected in STRUCTURE_TERMS.items():
            for lang, want in expected.items():
                with self.subTest(source=source, lang=lang):
                    with translation.override(lang):
                        self.assertEqual(gettext(source), want)

    def test_department_buttons_never_say_bank(self):
        """Sürüşmənin konkret izi: kafedra düymələri «bank» sözü daşıyırdı."""
        for source in ("Kafedranı sil", "Kafedranı redaktə et"):
            for lang in ("en", "ru", "tr"):
                with self.subTest(source=source, lang=lang):
                    with translation.override(lang):
                        rendered = gettext(source).lower()
                    self.assertNotIn("bank", rendered)
                    self.assertNotIn("банк", rendered)


class AmbiguousWordTests(TestCase):
    """«Qiymət» = grade (price DEYİL), «bal» = score (arı balı DEYİL)."""

    def test_grade_and_score_use_the_correct_sense(self):
        for msgctxt, msgid, expected in AMBIGUOUS_TERMS:
            for lang, want in expected.items():
                with self.subTest(msgid=msgid, lang=lang):
                    with translation.override(lang):
                        self.assertEqual(pgettext(msgctxt, msgid), want)

    def test_price_and_honey_senses_never_appear(self):
        for msgctxt, msgid, expected in AMBIGUOUS_TERMS:
            for lang in expected:
                with translation.override(lang):
                    rendered = pgettext(msgctxt, msgid)
                for forbidden in FORBIDDEN_SENSES[lang]:
                    with self.subTest(msgid=msgid, lang=lang, forbidden=forbidden):
                        self.assertNotIn(forbidden, rendered)


class StatusLabelTests(TestCase):
    """Status etiketi ilə əməliyyat düyməsi eyni mətni paylaşmasın."""

    def test_status_choices_describe_state_not_action(self):
        for msgctxt, msgid, expected in STATUS_TERMS:
            for lang, want in expected.items():
                with self.subTest(msgid=msgid, lang=lang):
                    with translation.override(lang):
                        self.assertEqual(pgettext(msgctxt, msgid), want)

    def test_in_progress_is_not_described_as_under_review(self):
        """`in_progress` = tələbə HAZIRDA yazır; «yoxlanılır» deyil.

        Bu, sadəcə üslub deyil: müəllim və imtahan mərkəzi canlı cəhdi bitmiş
        sanıb səhv operativ qərar verirdi.
        """
        wrong = {"az": "Yoxlanılır", "en": "Pending processing", "ru": "Проверка", "tr": "Kontrol ediliyor"}
        for lang, bad in wrong.items():
            with self.subTest(lang=lang):
                with translation.override(lang):
                    self.assertNotEqual(pgettext("exams.model.attempt.choice.status", "in_progress"), bad)
