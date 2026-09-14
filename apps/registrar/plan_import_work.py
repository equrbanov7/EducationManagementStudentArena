"""«İŞÇİ TƏDRİS PLANI» düzümünün oxunması (saytın ÜÇÜNCÜ cədvəl formatı).

Sahib (2026-09-10): «tədris planı orada olub burada olmama ehtimalı olmasın».
Saytın süpürgəsi göstərdi ki, bir sıra ixtisasın planı `050408 Menecment.pdf`
tipli sənəddə deyil, `PLAN_<ad>.docx.pdf` / `00_<ad>.pdf` adlı **işçi tədris
planında** dərc olunub. O sənəd nə bakalavr, nə də magistr parserinin
tanıdığı düzümdədir — hər ikisi 0 sətir qaytarır.

DÜZÜMÜN FƏRQİ
-------------
Cədvəl SEMESTRLƏRƏ bölünür və hər semestr öz başlığı ilə açılır::

    ['I semestr', '', '', '', '']
    ['Fənnin şifri', 'Fənnin adı', '', '', 'ECTS']
    ['ÜF-B02.01', 'Xarici dildə işgüzar və akademik kommunikasiya -1', '', '', '6']
    ['', 'Cəmi:', '', '', '24']

Yəni burada — digər iki düzümdən fərqli olaraq — **semestr nömrəsi VAR**.
Bu, planın ən qiymətli hissəsidir: bakalavr sənədində semestr sütunu bəzən
oxunmur, magistr sənədində isə ümumiyyətlə yoxdur.

⚠️ Sütun sayı səhifədən-səhifəyə dəyişir (5 / 7 / 4) və boş sütunlar araya
girir. Ona görə sabit indeks İŞLƏTMİRİK: şifr, ad və ECTS xanaları
məzmununa görə tanınır.

NƏ OXUNMUR (qəsdən)
-------------------
* «Cəmi», «Semestr üzrə:» — yekun sətirləridir, fənn deyil;
* «Ali təhsil müəssisəsi tərəfindən müəyyən edilən fənlər», «Ümumi fənlər
  üzrə seçmə fənlər» — bölmə başlıqlarıdır;
* nömrələnmiş seçmə blok («1.Fəlsəfə 2. Multikulturalizmə giriş …») — bir
  xanada bir neçə fənndir, TƏK `CurriculumSubject` deyil.
"""

from __future__ import annotations

import re

#: «ÜF-B02.01», «İF-BO1», «ATMF –BO5», «ÜFS-B04», «ÜF – B03».
#: ⚠️ Bəzi kodlarda rəqəm yerinə latın «O» yazılıb (`BO1`) — mənbədəki
#: yazı səhvidir, ona görə `[O0]?` icazəlidir.
_WORK_CODE = re.compile(r"^[A-ZƏÖÜĞİŞÇ]{2,5}\s*[–—-]?\s*B[O0]?\s?\d{1,2}(?:\.\d{1,2})?$")

#: «I semestr», «VII semestr».
_SEMESTER_HEAD = re.compile(r"^([IVX]+)\s*semestr\b", re.I)

#: Yekun sətirləri — fənn deyil.
_TOTAL = re.compile(r"^(cəmi|semestr\s+üzrə|yekun|ümumi)\b", re.I)

#: Cədvəl başlığı.
_COLUMN_HEAD = re.compile(r"^(fənnin\s+şifri|fənnin\s+adı|ects)$", re.I)

#: Bölmə başlıqları (fənn adı deyil, qrup adıdır).
_SECTION_HEAD = re.compile(
    r"^(ali\s+təhsil\s+müəssisəsi|ümumi\s+fənlər\s+üzrə|ixtisas\s+fənləri|seçmə\s+fənlər)",
    re.I,
)

#: «1.Fəlsəfə  2. Sosiologiya …» — bir xanada nömrələnmiş bir neçə fənn.
#: ⚠️ Nişan SAYILIR, UDULMUR: `\s*\S` ilə yazılsaydı «1. 2. 3.» kimi sətirdə
#: axtarış növbəti nişanın üstündən keçir və cəmi 1 uyğunluq sayılırdı.
_ENUM_MARK = re.compile(r"(?:^|\s)\d{1,2}\s*[.)]")

#: Sətrin ƏVVƏLİNDƏ nişan — bloka aid bənddir.
_ENUM_LEAD = re.compile(r"^\s*\d{1,2}\s*[.)]")

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}


def is_enumerated_block(name: str) -> bool:
    """Xana TƏK fənn deyil, nömrələnmiş seçmə blokdur?

    İki əlamət:
    * iki və daha çox nömrə nişanı («1.Fəlsəfə 2. Sosiologiya»);
    * sətir nişanla BAŞLAYIR («1. Avropa ölkələri…») — işçi tədris planında
      fənnin öz nömrəsi ayrıca `Fənnin şifri` sütunundadır, ona görə adın
      əvvəlindəki rəqəm həmişə blok bəndini bildirir. Bu qayda olmadan blokun
      səhifə keçidində qopan hissəsi kataloqa uydurma fənn kimi düşürdü.
    """
    text = (name or "").strip()
    if not text:
        return False
    return len(_ENUM_MARK.findall(text)) >= 2 or bool(_ENUM_LEAD.match(text))


def _cells(raw) -> list[str]:
    return [(cell or "").replace("\n", " ").strip() for cell in raw]


def _first_text(cells: list[str]) -> str:
    for cell in cells:
        if cell:
            return cell
    return ""


def _int_or_none(value: str):
    return int(value) if re.fullmatch(r"\d{1,3}", value or "") else None


def extract_work_rows(pdf_path: str) -> list[dict]:
    """«İşçi tədris planı» sənədindən fənn sətirləri.

    Qaytarılan hər sətir: ``{no, code, name, credits, total_hours, semester}``.
    ``semester`` insan oxunuşundadır («3»); `_semester()` onu tam ədədə çevirir.
    """
    import fitz  # PyMuPDF — yalnız bu axın üçün lazımdır

    rows: list[dict] = []
    semester = ""

    with fitz.open(pdf_path) as document:
        for page in document:
            found = page.find_tables()
            for table in found.tables if found else []:
                for raw in table.extract():
                    cells = _cells(raw)
                    head = _first_text(cells)
                    if not head:
                        continue

                    match = _SEMESTER_HEAD.match(head)
                    if match:
                        semester = str(_ROMAN.get(match.group(1).upper(), ""))
                        continue
                    if _TOTAL.match(head) or _COLUMN_HEAD.match(head) or _SECTION_HEAD.match(head):
                        continue

                    filled = [cell for cell in cells if cell]
                    if len(filled) < 2 or not _WORK_CODE.match(filled[0]):
                        continue

                    # Kredit — sətrin SONUNDAKI tam ədəd; ad isə şifrdən sonrakı
                    # ilk mətn xanasıdır (aralarındakı boş sütunlar buraxılır).
                    credits = _int_or_none(filled[-1])
                    name_parts = filled[1:-1] if credits is not None else filled[1:]
                    name = " ".join(name_parts).strip()
                    if len(name) < 3 or _TOTAL.match(name):
                        continue

                    rows.append(
                        {
                            "no": len(rows) + 1,
                            "code": filled[0],
                            "name": name,
                            "credits": credits,
                            "total_hours": None,
                            "semester": semester,
                        }
                    )
    return rows


__all__ = ["extract_work_rows", "is_enumerated_block"]
