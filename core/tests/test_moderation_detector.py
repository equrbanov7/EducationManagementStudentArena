"""Ad moderasiyası — detektorun vahid testləri (sahib 2026-09-30, WP MOD).

* POZİTİVLƏR: dörd dildə (az / tr / en / ru) söyüşlər və gizlətmə formaları
  (leetspeak, ayırıcılar, zero-width, fullwidth / riyazi hərflər, homoqliflər,
  hərf təkrarı, qarışıq əlifba, boşluqsuz ifadə);
* NEQATİVLƏR: REAL Azərbaycan adları / soyadları (həm «ə/ş/ç»-li, həm də ingilis
  klaviaturası ilə yazılış), fənn / kurs sözləri, «içində pis kök daşıyan» təmiz
  sözlər (Scunthorpe problemi) — heç biri bloklanmamalıdır;
* lüğət fayllarının özü: hər sətir düzgün regex-ə çevrilir, allowlist işləyir.

Yeni lüğət qaydası əlavə edəndə ƏVVƏLCƏ bu faylı işlədin.
"""

from __future__ import annotations

import re

from django.test import SimpleTestCase

from core.moderation import contains_profanity, find_profanity, mask_value
from core.moderation.normalize import raw_tokens, tokenize
from core.moderation.wordlist import LANGUAGES, Engine, engines, read_allowlist, read_rules

POSITIVES = {
    "az": (
        "Sik",
        "SİKDİR",
        "siktir git",
        "sikdirin",
        "sikim",
        "sikerem",
        "sikəcəm",
        "sikeyim",
        "sikik",
        "ananı sikim",
        "anavı sikim",
        "amcıq",
        "amciq",
        "qancıq",
        "gancig",
        "qəhbə",
        "gehbe",
        "qahba",
        "fahişə",
        "fahise",
        "oğraş",
        "oghrash",
        "peysər",
        "peyser",
        "göt",
        "götveren",
        "gotveren",
        "şərəfsiz",
        "serefsiz",
        "namussuz",
        "dıllaq",
        "gijdıllax",
        "vələdüzna",
        "köpək oğlu",
        "it oğlu",
    ),
    "tr": (
        "orospu",
        "orosbu çocuğu",
        "piç",
        "ibne",
        "yavşak",
        "pezevenk",
        "kahpe",
        "yarrak",
        "taşak",
        "sürtük",
        "kaltak",
        "amına koyayım",
        "amina koyim",
        "kancık",
        "siktiğimin",
    ),
    "en": (
        "fuck",
        "FUCK",
        "motherfucker",
        "fuuuuck",
        "phuck",
        "bitch",
        "son of a bitch",
        "asshole",
        "shit",
        "bullshit",
        "cunt",
        "whore",
        "slut",
        "bastard",
        "nigger",
        "faggot",
        "retard",
        "dickhead",
        "pussy",
        "wanker",
        "dildo",
        "porn",
        "jackass",
    ),
    "ru": (
        "хуй",
        "ХУЙ",
        "хуйня",
        "иди нахуй",
        "пизда",
        "пиздец",
        "блядь",
        "бля",
        "сука",
        "ебать",
        "ёбаный",
        "ёб твою мать",
        "заебал",
        "уебок",
        "мудак",
        "пидорас",
        "гандон",
        "залупа",
        "шлюха",
        "долбоёб",
        "чмо",
        "жопа",
        "говно",
        "сукин сын",
        "blyat",
        "cyka blyat",
        "suka",
        "pizdec",
        "nahuy",
        "pohuy",
        "pidor",
        "mudak",
        "ebat",
        "dolboeb",
        "zaebal",
    ),
}

#: Gizlətmə cəhdləri — hamısı tutulmalıdır.
OBFUSCATED = (
    "s1kdir",
    "s!kt!r",
    "$1kt1r",
    "S I K T I R",
    "s.i.k.t.i.r",
    "s_i_k_t_i_r",
    "s-i-k",
    "siiiiiktiiiir",
    "s​i​k​t​i​r",  # zero-width space
    "s‍i‍k",  # zero-width joiner
    "‮siktir‬",  # bidi override
    "ｓｉｋｔｉｒ",  # fullwidth
    "𝐬𝐢𝐤𝐭𝐢𝐫",  # riyazi qalın
    "ⓢⓘⓚⓣⓘⓡ",  # dairəvi
    "s̶i̶k̶t̶i̶r̶",  # birləşən üstdən xətt
    "f*ck",
    "f u c k",
    "fu ck",
    "f.u.c.k",
    "fvck",
    "fυck",  # yunan «υ»
    "sh1t",
    "$hit",
    "ѕһіt",  # kiril homoqliflər
    "a$$hole",
    "b1tch",
    "n1gger",
    "p0rn",
    "0r0spu",
    "aminakoyim",  # boşluqsuz ifadə
    "ananısikim",
    "köpəkoğlu",
    "х у й",
    "xуй",  # latın x + kiril
    "сyка",  # kiril + latın y
    "cyka",
    "бl9дь",
    "бл9ть",
    "6лядь",
    "пи3да",
    "пиzда",
)

#: REAL adlar / soyadlar — heç biri bloklanmamalıdır.
REAL_NAMES = """
Abbas Abdulla Adil Ağa Akif Ayaz Aqil Anar Araz Arif Arzu Asif Aslan Azad Azər Babək Bəhruz Bəxtiyar Cabbar Cavad
Cavid Ceyhun Cəlal Cəmil Cümşüd Coşqun Dadaş Dilavər Dilqəm Elçin Eldar Eldəniz Elgün Elxan Elmir Elnur Elşad Elşən
Elvin Emil Emin Etibar Eyvaz Fazil Fərid Fərhad Fəxri Fikrət Fuad Füzuli Hafiz Hikmət Hüseyn Həsən Heydər İbrahim
İlham İlkin İlqar İsa İslam İsmayıl Kamal Kamil Kamran Kənan Kərim Qabil Qasım Qəzənfər Qurban Mahir Məhəmməd Məmməd
Mehman Mirzə Mübariz Murad Musa Mustafa Nadir Namiq Natiq Nicat Nihad Nizami Nurlan Oqtay Orxan Pərviz Pünhan Rafael
Rafiq Ramil Ramin Rasim Rauf Rəşad Rəşid Rövşən Ruslan Rüstəm Samir Sakit Səbuhi Seymur Sənan Siyavuş Sübhan Sərxan
Şahin Şamil Şəhriyar Şəmsi Tahir Tapdıq Teymur Tofiq Toğrul Turan Tural Ülvi Vasif Vüqar Vüsal Xaqani Xəyal Xəyyam
Yaqub Yusif Zakir Zaur Zamiq Zöhrab Ziya Sikandar İsgəndər Səməd Pənah Nəsimi Qəhrəman Şükür Ələkbər Allahverdi Hacı
Novruz Bayram Dəmir Pirverdi Kazım Talıb Tərlan Zahid Yavər Bahadur Bəşir Çingiz Firuz Gündüz Afaq Aida Aynur Aysel
Aygün Aytən Almaz Amina Aminə Amin Əmin Amil Aişə Bahar Banu Bəsti Cəmilə Dilarə Dilbər Dürdanə Elmira Elnarə Esmira
Fatimə Fidan Firəngiz Gülnar Gülnarə Gülşən Gültəkin Günay Günel Gülər Həcər Hicran İlahə İradə Jalə Kamilə Kəmalə
Könül Lalə Leyla Lamiyə Mədinə Mehriban Minayə Nailə Nərmin Nigar Nuranə Nəzrin Pərvanə Pərvin Rəna Rəhilə Röya Sabina
Səbinə Sevda Sevinc Sevil Solmaz Sona Səma Şəbnəm Şəfəq Şəhla Tamilla Təranə Türkan Ülkər Ülviyyə Vəfa Xanım Xədicə
Xuraman Yeganə Zemfira Zəhra Zərifə Zülfiyyə Nəzakət Ofelya Pakizə Qızılgül Sədaqət Şükufə Tünzalə Səkinə Sükeynə
Abbasov Abbasova Abdullayev Axundov Ağayev Əhmədov Əliyev Əliyeva Əlizadə Ələkbərov Əsədov Əsgərov Əzimov Əzizov
Allahverdiyev Babayev Bağırov Bayramov Cabbarov Cəfərov Cəlilov Cavadov Dadaşov Dəmirov Eyvazov Fərzəliyev Hacıyev
Həsənov Həşimov Heydərov Hümbətov Hüseynov Hüseynova İbrahimov İsgəndərov İsmayılov Kazımov Kərimov Qasımov Qədirov
Quliyev Quliyeva Qurbanov Mahmudov Mehdiyev Məlikov Məmmədov Məmmədova Mirzəyev Musayev Mustafayev Nağıyev Nəbiyev
Nəsibov Novruzov Orucov Paşayev Pənahov Rəhimov Rəsulov Rüstəmov Rzayev Sadıqov Salmanov Səfərov Səmədov Süleymanov
Sultanov Şahbazov Şükürov Şıxəliyev Şirinov Talıbov Tağıyev Vəliyev Xəlilov Yusifov Zeynalov Hüseynzadə Məmmədli
Qarayev Qəhrəmanov Pirverdiyev Sikandarov İskəndərli Səmədzadə Kərimli Mirzəzadə Gözəlov Seyidov Tahirov Xudiyev
Xudaverdiyev Muradov Nuriyev Şərifov Şərəfov Namazov Poladov Amirov Səkkizov Göyüşov Mürsəlov Puşkin Gəncəli
Samedov Panahov Aliyev Mammadov Huseynov Hasanov Guliyev Gurbanov Ismayilov Karimov Gasimov Sadigov Shukurov Shikhaliyev
Sirinov Vusal Vugar Gunay Gulnar Ulviyya Nargiz Ilkin Chingiz Farid Farhad Toghrul Rashad Samira Khayal Xayal Khalilov
Khuraman Aliyeva Mammadli Askerov Pashayev Tapdig Gulshan Sabuhi Mehdi Sahin Iskandarov
Иван Петров Сергей Сукачев Суконцев Бляхин Мудров Хуторской Говоров Шалаев Ayşe Yılmaz Işık Kahraman Amine Ebru Huynh
Hui Suki Huevos Huelva Pusan Pushkin Shitov Gandhi Pizarro Dickens Dickinson Hancock Hitchcock Cockburn Cummings Bassett
""".split()

#: Fənn / kurs / gündəlik sözlər və «içində pis kök daşıyan» təmiz sözlər.
CLEAN_WORDS = """
Riyaziyyat Fizika Kimya Biologiya İqtisadiyyat Tarix Ədəbiyyat Musiqi Klassik Sikkə sikkələr Şikayət şikayət sikayet
Mühasibat Menecment Marketinq Hüquq Psixologiya Pedaqogika İnformatika Proqramlaşdırma Alqoritmlər Verilənlər bazası
Mühəndislik Fəlsəfə Sosiologiya Coğrafiya Dilçilik Tərcümə Jurnalistika Beynəlxalq münasibətlər Maliyyə Turizm Dizayn
Memarlıq Tibb Əczaçılıq Stomatologiya Kitabxanaçılıq qrup kurs mövzu sillabus imtahan tələbə müəllim dekan kafedra
fakültə Göytürk Götürmək götürdü götürün Amerika Amsterdam Pikasso picnic Siyasət sikl siklon işıq Sıxlıq sıxma fahiş
qiymət amillər turşusu amortizasiya Kəmiyyət qanun peyk namus şərəf bitki bitiş kokteyl dikkat sükut müdafiə hücum pul
puştu yaraq şik şıq sık sıkıntı SIKINTI ISIK amca Götürmek Yarasa Taşkent Taşkın got
Scunthorpe assassin class classic Sussex Essex Middlesex cocktail cockpit peacock therapist Matsushita shiitake shitake
Titanic petition analysis grape button Wankel Wankhede niggle niggling snigger Niger Nigeria retardant Slutsk Bitcoin
Fukuoka Fukushima Assisi passive Arsenal Horsham Hue Pizza Pisa Blat Blake
употреблять оскорблять корабля рубля Херсон мандарин сукно сучок сучковатый застрахуй подстрахуй Гондурас Хуан Хабаровск
педикюр шить шитьё курвиметр хулиган хурма
""".split()

CLEAN_PHRASES = (
    "Əli Məmmədov",
    "Vüqar Hüseynov",
    "Ali Veli 2005",
    "Ali_007",
    "Nigar-2",
    "O'Neil",
    "Ülviyyə & Co",
    "A. B. Məmmədov",
    "A. M. K.",
    "Bank işi",
    "Fahiş qiymət",
    "Amin Amina",
    "I am Ali",
    "Bit oğlu",
    "Иван Петров",
    "Е. Б. Иванова",
    # Təhlükəsizlik baxışı 2026-09-30: ad + soyad sərhədində / ifadə prefiksində yanlış pozitivlər.
    "Amina Goyushova",
    "AMINA GOYUSHOVA",
    "Amina Qoyunova",
    "Amina Koyuncu",
    "Isik Tiryaki",
    "Asiq Direk",
    "Asiq Dirili",
    "Yusif Uckun",
    "Arif Uckun",
    "Latif Uckun",
    "Сучков",
    "Сучкова Анна",
)


class DetectorPositiveTest(SimpleTestCase):
    def test_every_language_is_caught(self):
        for language, samples in POSITIVES.items():
            for sample in samples:
                with self.subTest(language=language, sample=sample):
                    match = find_profanity(sample)
                    self.assertIsNotNone(match, sample)

    def test_language_is_reported(self):
        self.assertEqual(find_profanity("siktir").language, "az")
        self.assertEqual(find_profanity("orospu").language, "tr")
        self.assertEqual(find_profanity("motherfucker").language, "en")
        self.assertEqual(find_profanity("пиздец").language, "ru")

    def test_obfuscations_are_caught(self):
        for sample in OBFUSCATED:
            with self.subTest(sample=repr(sample)):
                self.assertTrue(contains_profanity(sample), repr(sample))

    def test_profanity_inside_a_longer_name(self):
        for sample in ("Ali Siktir", "Kamran sikim", "Pro fucker 2000", "Leyla blyat", "Иван хуйло"):
            with self.subTest(sample=sample):
                self.assertTrue(contains_profanity(sample))


class DetectorNegativeTest(SimpleTestCase):
    def test_real_names_are_never_blocked(self):
        hits = {name: find_profanity(name) for name in REAL_NAMES if find_profanity(name) is not None}
        self.assertEqual(hits, {})

    def test_clean_words_are_never_blocked(self):
        hits = {word: find_profanity(word) for word in CLEAN_WORDS if find_profanity(word) is not None}
        self.assertEqual(hits, {})

    def test_clean_phrases_are_never_blocked(self):
        for phrase in CLEAN_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIsNone(find_profanity(phrase))

    def test_full_name_combinations(self):
        first_names, surnames = REAL_NAMES[:120], REAL_NAMES[300:420]
        for first, last in zip(first_names, surnames):
            with self.subTest(name=f"{first} {last}"):
                self.assertIsNone(find_profanity(f"{first} {last}"))

    def test_guest_nickname_generator_is_clean(self):
        from apps.live_exam.session_settings import NICKNAME_ADJECTIVES, NICKNAME_NOUNS

        for adjective in NICKNAME_ADJECTIVES:
            for noun in NICKNAME_NOUNS:
                self.assertIsNone(find_profanity(f"{adjective} {noun} 42"), (adjective, noun))

    def test_folding_is_asymmetric(self):
        """«s» qaydası «ş»-ni, «i» qaydası «ı»-nı tutmur; «=göt» yalnız «ö» ilə."""
        self.assertIsNone(find_profanity("şik"))
        self.assertIsNone(find_profanity("sık"))
        self.assertIsNone(find_profanity("got"))
        self.assertIsNotNone(find_profanity("göt"))
        # «ş» hərfli qayda isə diakritiksiz yazılışı TUTUR.
        self.assertIsNotNone(find_profanity("serefsiz"))

    def test_empty_and_non_text_input(self):
        for value in (None, "", "   ", "12345", "!!!", "​​"):
            with self.subTest(value=repr(value)):
                self.assertIsNone(find_profanity(value))


class NormalizationTest(SimpleTestCase):
    def test_single_letter_runs_are_merged(self):
        self.assertEqual(raw_tokens("s i k t i r"), ["siktir"])
        self.assertEqual(raw_tokens("a b məmmədov"), ["ab", "məmmədov"])

    def test_protected_letters_survive_and_other_marks_are_folded(self):
        forms = tokenize("Şəbnəm Ülviyyə fùck Йога")
        self.assertEqual(forms[0].latin[0], "şəbnəm")
        self.assertEqual(forms[1].latin[0], "ülviyyə")
        self.assertEqual(forms[2].latin[0], "fuck")
        self.assertEqual(forms[3].cyrillic[0], "иога")

    def test_pure_cyrillic_word_is_not_read_phonetically(self):
        # «шить» (tikmək) fonetik oxunuşda «shit» olardı — yalnız vizual oxunur.
        self.assertEqual(tokenize("шить")[0].latin, [])


class WordlistFilesTest(SimpleTestCase):
    def test_every_language_file_has_rules_that_compile(self):
        for language in LANGUAGES:
            rules = read_rules(language)
            self.assertGreater(len(rules), 5, language)
            for rule in rules:
                with self.subTest(language=language, term=rule.term):
                    re.compile(rule.pattern)
                    self.assertIsNotNone(find_profanity(rule.term.strip("=*")), rule.term)

    def test_allowlist_does_not_hide_whole_word_rules(self):
        exact, prefixes = read_allowlist()
        latin, cyrillic = engines()
        for token in exact | set(prefixes):
            with self.subTest(token=token):
                self.assertIsNone(latin.match_token(token))
                self.assertIsNone(cyrillic.match_token(token))

    def test_allowlist_is_what_keeps_innocent_words_clean(self):
        latin, cyrillic = engines()
        bare_latin = Engine([rule for rules in latin.rules.values() for rule in rules], frozenset(), ())
        bare_cyrillic = Engine([rule for rules in cyrillic.rules.values() for rule in rules], frozenset(), ())
        for word, bare in (("niggle", bare_latin), ("retardant", bare_latin), ("сучковатый", bare_cyrillic)):
            with self.subTest(word=word):
                self.assertIsNotNone(bare.match_token(word))
                self.assertIsNone(find_profanity(word))


class MaskTest(SimpleTestCase):
    def test_mask_keeps_first_letter_only(self):
        self.assertEqual(mask_value("Siktir"), "S*****")
        self.assertEqual(mask_value("  Ali   Siktir "), "A** ******")
        self.assertEqual(mask_value(""), "")
        self.assertEqual(len(mask_value("x" * 200)), 40)
