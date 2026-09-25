"""Defolt sual dəsti — «Müəllimin tədrisinin tələbə tərəfindən qiymətləndirilməsi» v1.

Mənbələr: SEEQ (Marsh — öyrənmə/dəyər, təşkilat/aydınlıq, qrup qarşılıqlı əlaqəsi,
fərdi münasibət, imtahan/qiymətləndirmə, tapşırıq/materiallar, iş yükü), IDEA və
EvaSys tipli universitet anketləri. Seçim qaydaları:

* ≤ 20 bənd (sorğu yorğunluğu — cavab keyfiyyəti uzun anketlərdə kəskin düşür);
* hər bənd MÜŞAHİDƏ OLUNAN tədris davranışı barədədir (şəxsiyyət haqqında deyil);
* «Fikrim yoxdur» variantı YOXDUR (forced choice) — tələbə hər bəndi yaşayıb;
* açıq suallar tədrisə yönəlib («nəyi bəyəndiniz», «nə təklif edərdiniz») — bu,
  şəxsi/təhqiramiz şərhləri azaldır; tələbəyə şəxsi məlumat yazmamaq xatırladılır;
* iş yükü (13) və tövsiyə (15) ayrıca göstəricidir, Likert indeksinə DAXİL DEYİL
  (SEEQ-də iş yükü/çətinlik tədris effektivliyinin kompozitinə girmir).

Mətnlər AZ mənbədir; en/ru/tr tərcümələri ``scripts/i18n_add_survey_core_2026_09_25.py``-dadır
(kontekst ``surveys.question``).
"""

from __future__ import annotations

from .constants import QuestionKind, Section

DEFAULT_TEMPLATE_NAME = "Müəllimin tədrisinin qiymətləndirilməsi"
DEFAULT_TEMPLATE_VERSION = 1

_T = Section.TEACHER
_G = Section.GENERAL
_L = QuestionKind.LIKERT5
_S = QuestionKind.SCALE10
_X = QuestionKind.TEXT

#: Açıq sualların altında göstərilən ümumi xatırlatma.
TEXT_PRIVACY_HINT = "Ad, qrup və ya sizi tanıda biləcək məlumat yazmayın — cavabınız anonim qalsın."

#: (code, section, kind, text, help_text, required, in_index)
DEFAULT_QUESTIONS = [
    ("organization", _T, _L, "Müəllim dərsə hazırlıqlı gəlir, dərsi planlı və ardıcıl aparır.", "", True, True),
    ("clarity", _T, _L, "Mövzuları aydın və başa düşülən şəkildə izah edir.", "", True, True),
    (
        "syllabus",
        _T,
        _L,
        "Sillabusda göstərilən mövzulara, tələblərə və qiymətləndirmə qaydasına əməl edir.",
        "",
        True,
        True,
    ),
    ("punctuality", _T, _L, "Dərsləri vaxtında başlayır və dərs vaxtından səmərəli istifadə edir.", "", True, True),
    ("engagement", _T, _L, "Suallar verməyə, müzakirəyə və fəal iştiraka həvəsləndirir.", "", True, True),
    ("respect", _T, _L, "Tələbələrə hörmətlə, ədalətli və qərəzsiz yanaşır.", "", True, True),
    (
        "fair_assessment",
        _T,
        _L,
        "Qiymətləndirmə meyarları əvvəlcədən aydın idi və ballar bu meyarlara uyğun verilirdi.",
        "",
        True,
        True,
    ),
    (
        "feedback",
        _T,
        _L,
        "Tapşırıq, sərbəst iş və midterm nəticələri üzrə vaxtında və faydalı rəy (izah) verir.",
        "",
        True,
        True,
    ),
    (
        "availability",
        _T,
        _L,
        "Dərsdən kənar (məsləhət saatı, e-poçt və s.) suallara cavab vermək üçün əlçatandır.",
        "",
        True,
        True,
    ),
    ("relevance", _T, _L, "Nəzəri bilikləri praktiki nümunələr və real həyatla əlaqələndirir.", "", True, True),
    (
        "materials",
        _T,
        _L,
        "Dərs materialları (təqdimat, ədəbiyyat, tapşırıqlar) faydalı və müasirdir.",
        "",
        True,
        True,
    ),
    ("learning", _T, _L, "Bu fənn üzrə bilik və bacarıqlarım nəzərəçarpacaq dərəcədə artdı.", "", True, True),
    (
        "workload",
        _T,
        _L,
        "Fənnin iş yükü (tapşırıq, hazırlıq) onun kreditinə uyğun idi.",
        "Razılıq iş yükünün uyğun olduğunu bildirir — çox və ya az olması uyğunsuzluqdur.",
        True,
        False,
    ),
    (
        "overall",
        _T,
        _S,
        "Bu müəllimin bu fəndəki tədrisini ümumilikdə 1–10 bal şkalası ilə qiymətləndirin.",
        "1 — çox zəif, 10 — əla.",
        True,
        False,
    ),
    ("recommend", _T, _L, "Bu müəllimin dərsini digər tələbələrə tövsiyə edərdim.", "", True, False),
    ("strengths", _T, _X, "Bu müəllimin tədrisində ən çox nəyi bəyəndiniz?", "", False, False),
    ("improve", _T, _X, "Dərsin daha yaxşı olması üçün nə təklif edərdiniz?", "", False, False),
    ("satisfaction", _G, _L, "Bu semestr tədris prosesindən ümumilikdə məmnunam.", "", True, False),
    (
        "facilities",
        _G,
        _L,
        "Tədris şəraiti (auditoriya, texniki təchizat, kitabxana, elektron resurslar) təhsilim üçün yetərli idi.",
        "",
        True,
        False,
    ),
    (
        "suggestions",
        _G,
        _X,
        "Universitetdə tədrisi və tələbə xidmətlərini daha da yaxşılaşdırmaq üçün nə təklif edərdiniz?",
        "",
        False,
        False,
    ),
]

#: Likert 1–5 cavab etiketləri (şkala «razılıq» formasındadır).
LIKERT_LABELS = (
    (1, "Tamamilə razı deyiləm"),
    (2, "Razı deyiləm"),
    (3, "Qismən razıyam"),
    (4, "Razıyam"),
    (5, "Tamamilə razıyam"),
)

#: 1–10 şkalasının iki ucunun etiketi.
SCALE_ANCHORS = ("Çox zəif", "Əla")
