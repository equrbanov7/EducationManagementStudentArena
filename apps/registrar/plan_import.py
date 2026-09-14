"""Universitet saytındakı «Tədris planı» PDF-lərinin oxunması və uyğunlaşdırılması.

Sahib (2026-09-09): «burdakı tədris planlarını yükləyib hər ixtisasa əlavə etmək
lazımdı» — mənbə: https://wcu.edu.az/az/page/undergraduate-programs

NƏ EDİR / NƏ ETMİR
------------------
Bu modul YALNIZ oxuyur və uyğunlaşdırır: PDF-dən cədvəl sətirlərini çıxarır,
fənn adını mövcud `Subject` kataloqu ilə tutuşdurur və nəticəni HESABAT kimi
qaytarır. Bazaya HEÇ NƏ yazmır — yazma qərarı komandadadır və default DRY-RUN-dır.

NİYƏ BELƏ EHTİYATLI
-------------------
Tədris planı dərs yükünü, jurnalı və məzuniyyət yoxlamasını idarə edir; səhv
kredit və ya səhv fənn planı sükutla korlayır. Praktikada mənbə PDF-lər üç cür
problem verir və hər üçü sətir səviyyəsində İŞARƏLƏNİR, uydurulmur:

1. **Homoqlif** — bəzi adlar kiril «А» (U+0410) ilə başlayır («Аzərbaycanın
   tarixi»). Normallaşdırma bunu latına çevirir, əks halda fənn «tapılmadı»
   görünür.
2. **Seçmə bloklar** — bir xanada bir neçə fənn olur («I blok: 1. Sosiologiya
   2. AR Konstitusiyası …»). Bu, TƏK fənn deyil; sətir `elective_block` kimi
   qeyd olunur və avtomatik idxal EDİLMİR.
3. **Fərqli düzüm** — bəzi PDF-lərdə cədvəl başqa cür qurulub (məs. «Mühasibat»
   cəmi 6 sətir verir). Belə fayl `low_yield` kimi işarələnir.
"""

from __future__ import annotations

import re
import unicodedata

#: Plan sətri sayılmaq üçün minimum sütun.
MIN_COLUMNS = 8

#: Bu sayda az sətir çıxan fayl şübhəlidir (4 illik plan ~35–50 sətirdir).
LOW_YIELD = 20

#: Kiril homoqlifləri — mənbə PDF-lərdə latın hərflərin yerinə işlənir.
_HOMOGLYPHS = str.maketrans(
    {
        "А": "A",
        "В": "B",
        "С": "C",
        "Е": "E",
        "Н": "H",
        "К": "K",
        "М": "M",
        "О": "O",
        "Р": "P",
        "Т": "T",
        "Х": "X",
        "а": "a",
        "с": "c",
        "е": "e",
        "о": "o",
        "р": "p",
        "х": "x",
        "у": "y",
    }
)

#: «I blok: 1. … 2. …» kimi seçmə blok sətirləri.
#: ⚠️ Bəzi planlar (məs. Regionşünaslıq) İNGİLİS dilində dərc olunub — orada
#: eyni sətir «I block 1. Philosophy …» şəklindədir; əks halda seçmə blok
#: «tapılmayan fənn» kimi görünürdü.
#: ⚠️ 2026-09-10: blok sözü hər sənəddə eyni yazılmır — «I Seçmə fənn bloku:
#: 1.Bioloji müxtəliflik …» və «ÜFS I blok 1.Fəlsəfə …» nə rum rəqəmi ilə
#: BAŞLAYIR, nə də «blok»dan dərhal sonra iki nöqtə gəlir. Ona görə üçüncü
#: qayda əlavə edilib: «blok/bloku» sözündən sonra NÖMRƏLƏNMİŞ siyahı («1.»)
#: gəlirsə, xana tərifinə görə bir neçə fənndir. Bu 6 sətir əvvəl `unknown`
#: səbətinə düşürdü — `--create-subjects` onları kataloqa UYDURMA fənn kimi
#: yazardı.
_ELECTIVE = re.compile(
    r"^\s*[IVX]+\s*blo[kc]k?\b"
    r"|blo[kc]k?\s*:"
    r"|blo[kc]k?u?\b\s*:?\s*\d\s*[.)]"
    r"|^\s*(birinci|ikinci|üçüncü|dördüncü|beşinci)\s+blok",
    re.I,
)


def normalize(value: str) -> str:
    """Müqayisə üçün ad: homoqlif → latın, durğu/boşluq sadələşdirilir."""
    text = unicodedata.normalize("NFC", (value or "")).translate(_HOMOGLYPHS)
    text = text.casefold().replace("i̇", "i")
    text = re.sub(r"[«»\"'(),.\-–—:;]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_elective_block(name: str) -> bool:
    """Sətir TƏK fənn deyil, seçmə blokdur?

    İki naxış birləşir:
    * söz-əsaslı («I blok:», «I block 1. …») — `_ELECTIVE`;
    * NÖMRƏLƏNMİŞ siyahı («1 Membranologiya 2. Nanobiotexnologiya 3. Gen
      mühəndisliyi») — işçi tədris planı düzümündə bloklar məhz belə yazılır,
      «blok» sözü ÜMUMİYYƏTLƏ olmaya bilər. Bu naxış olmadan `--create-subjects`
      belə sətirləri kataloqa UYDURMA fənn kimi yazardı (430 sətir).
    """
    from apps.registrar.plan_import_work import is_enumerated_block

    return bool(_ELECTIVE.search(name or "")) or is_enumerated_block(name)


def _to_int(value: str):
    digits = re.sub(r"[^\d]", "", value or "")
    return int(digits) if digits else None


def extract_rows(pdf_path: str) -> list[dict]:
    """PDF-dən plan sətirlərini çıxarır (`fitz.find_tables`).

    Qaytarılan hər sətir: ``{no, code, name, credits, total_hours, semester}``.
    Sütun düzümü fayldan-fayla dəyişir, ona görə YALNIZ sabit olanlar oxunur:
    birinci sütun sıra nömrəsi, üçüncü sütun ad, dördüncü sütun kreditdir.
    """
    import fitz  # PyMuPDF — yalnız bu axın üçün lazımdır

    rows: list[dict] = []
    with fitz.open(pdf_path) as document:
        for page in document:
            found = page.find_tables()
            for table in found.tables if found else []:
                for raw in table.extract():
                    cells = [(cell or "").replace("\n", " ").strip() for cell in raw]
                    if len(cells) < MIN_COLUMNS:
                        continue
                    if not re.fullmatch(r"\d{1,3}", cells[0] or ""):
                        continue
                    name = cells[2]
                    if len(name) < 4:
                        continue
                    rows.append(
                        {
                            "no": int(cells[0]),
                            "code": cells[1],
                            "name": name,
                            "credits": _to_int(cells[3]),
                            "total_hours": _to_int(cells[4]) if len(cells) > 4 else None,
                            "semester": cells[-2] if len(cells) > 2 else "",
                        }
                    )
    return rows


def is_placeholder(name: str) -> bool:
    """«Ali məktəb tərəfindən müəyyən edilən fənn» kimi YER TUTUCU sətir?

    Belə sətirlər konkret fənn deyil — sonradan universitetin doldurduğu yerdir.
    Onları `unknown` səbətinə atmaq təhlükəlidir: `--create-subjects` rejimi
    onları kataloqa UYDURMA fənn kimi yazardı.
    """
    return bool(_PLACEHOLDER.match((name or "").strip()))


#: «AMTSF: Biotexnologiya…», «ATMF: Su bioehtiyatları…» — addan ƏVVƏL gələn
#: bölüm kodu. Kataloqda fənn TƏMİZ adla saxlanılır, ona görə prefiks atılır;
#: əks halda eyni fənn həm «Biotexnologiya», həm «AMTSF: Biotexnologiya» kimi
#: kataloqa İKİ dəfə düşərdi.
_ROW_PREFIX = re.compile(r"^[A-ZƏÖÜĞİŞÇ]{2,6}\s*[:—–-]\s+")


def clean_subject_name(name: str) -> str:
    """Sətir adını kataloq üçün təmizləyir (bölüm prefiksi + artıq boşluq)."""
    text = _ROW_PREFIX.sub("", (name or "").strip())
    return re.sub(r"\s+", " ", text).strip()


def match_rows(rows: list[dict], subjects_by_name: dict) -> dict:
    """Sətirləri fənn kataloqu ilə tutuşdurur; heç nə yazmır.

    ``subjects_by_name`` — ``{normalize(ad): Subject}``. Səbətlər:
    ``matched`` (kataloqda var) · ``electives`` (seçmə blok) ·
    ``placeholders`` (yer tutucu) · ``unknown`` (əsl fənn, kataloqda yoxdur).
    """
    matched, electives, placeholders, unknown = [], [], [], []
    for raw in rows:
        row = {**raw, "name": clean_subject_name(raw["name"])}
        if is_elective_block(row["name"]):
            electives.append(row)
            continue
        if is_placeholder(row["name"]):
            placeholders.append(row)
            continue
        subject = subjects_by_name.get(normalize(row["name"]))
        if subject is None:
            unknown.append(row)
        else:
            matched.append({**row, "subject": subject})
    return {
        "rows": rows,
        "matched": matched,
        "electives": electives,
        "placeholders": placeholders,
        "unknown": unknown,
        "low_yield": len(rows) < LOW_YIELD,
    }


# ── Magistratura düzümü ─────────────────────────────────────────────────────
#
# Magistr planları BAŞQA cür qurulub: sətir = fənn BÖLÜMÜ, fənlərin özü isə TƏK
# xanada, sətir-sətir yığılıb:
#
#   [3] "MHF – B01\nXarici dil\nMHF – B02\nAli məktəb\npedaqogikası\n…"
#   [4] "6\n4\n2\n2"
#
# Yəni kod sətri fənni AÇIR, ondan sonrakı sətirlər adın davamıdır; kreditlər
# ayrı xanada eyni sırada gəlir. Bakalavr parseri bu faylları 0 sətir oxuyurdu.

#: «MHF – B01», «İXF-B12», «PF – B3» kimi fənn kodu sətri.
_MASTER_CODE = re.compile(r"^[A-ZƏÖÜĞİŞÇ]{2,6}\s*[–—-]\s*[A-ZƏ]?\d{1,3}\*?$")

#: Yer tutucu sətirlər — konkret fənn DEYİL, sonradan doldurulan yer.
#: Magistr planlarında ixtisas hissəsi məhz belə verilir («İxtisaslaşmaya
#: ayrılan fənlər** — 42 kredit»); bunları `CurriculumSubject` kimi yazmaq
#: planı uydurma fənnlə doldurardı.
#:
#: ⚠️ 2026-09-10: sənədlər eyni yer tutucunu ÜÇ cür yazır və köhnə qayda
#: yalnız birini tuturdu:
#:   * «Ali məktəbin müəyyən **etdiyi** fənn» — `ed` deyil, `et` ilə;
#:   * «Ali **təhsil müəssisəsi** tərəfindən müəyyən edilən fənlər»;
#:   * «Seçmə **fənlər**\*» — tək «n» ilə.
#: Hər üçü `unknown` səbətinə düşürdü; `--create-subjects` onları kataloqa
#: uydurma fənn kimi yazardı.
_PLACEHOLDER = re.compile(
    r"^\s*(seçmə\s+fən(n|lər)"
    r"|ali\s+(məktəb(in)?|təhsil\s+müəssisəsi(nin)?)\s+(tərəfindən\s+)?"
    r"(müəyyən\s+(ed|et)|seçilən|seçilmiş|seçdiyi)"
    r"|ixtisaslaşmaya\s+ayrılan"
    r"|ixtisas(laşma)?\s+fənləri\s*\**\s*$)",
    re.I,
)


def extract_master_rows(pdf_path: str) -> list[dict]:
    """Magistr planından fənn sətirləri (kod + ad + kredit).

    ⚠️ Fənn adı SƏHİFƏ SƏRHƏDİNİ keçir. Səh. 8-də xana «Psixologiya⏎MHF – B04…»
    ilə başlayır — yəni ilk sətir əvvəlki fənnin ADININ DAVAMIdır, kod deyil.
    Əvvəlki versiya xananın İLK sətrinin kod olmasını tələb edirdi və belə
    xanaları TAM atırdı; magistr planlarından cəmi 3–8 fənn çıxırdı (real say
    15–25). İndi vəziyyət SƏNƏD SƏVİYYƏSİNDƏ saxlanılır: kod yeni fənni açır,
    qalan sətirlər (səhifə keçidindən sonra belə) cari adın davamı sayılır.

    Kredit uyğunluğu: xanada AÇILAN kod sayı ilə kredit sayı üst-üstə düşməsə,
    kredit `None` qalır — TAXMİN EDİLMİR. Yanlış kredit planı sükutla korlayır;
    `--apply` kreditsiz sətri yazmır.
    """
    import fitz

    rows: list[dict] = []
    state = {"code": "", "parts": [], "credit": None}

    def close():
        """Açıq fənni siyahıya yazır (adı artıq tam toplanıb)."""
        name = " ".join(state["parts"]).strip()
        if state["code"] and name and not _PLACEHOLDER.match(name):
            rows.append(
                {
                    "no": len(rows) + 1,
                    "code": state["code"],
                    "name": name,
                    "credits": state["credit"],
                    "total_hours": None,
                    "semester": "",
                }
            )
        state["code"], state["parts"], state["credit"] = "", [], None

    with fitz.open(pdf_path) as document:
        for page in document:
            found = page.find_tables()
            for table in found.tables if found else []:
                for raw in table.extract():
                    if len(raw) < 5:
                        continue
                    lines = [part.strip() for part in (raw[3] or "").split("\n") if part.strip()]
                    codes = [line for line in lines if _MASTER_CODE.match(line)]
                    if not codes and not state["code"]:
                        continue  # başlıq / xülasə sətri
                    credits = [c.strip() for c in (raw[4] or "").split("\n") if c.strip()]
                    # Kredit YALNIZ say üst-üstə düşəndə bağlanır.
                    aligned = credits if len(credits) == len(codes) else [None] * len(codes)
                    index = 0
                    for line in lines:
                        if _MASTER_CODE.match(line):
                            close()
                            state["code"] = line
                            state["credit"] = _to_int(aligned[index])
                            index += 1
                        else:
                            state["parts"].append(line)
        close()
    return rows


def extract_any(pdf_path: str) -> tuple[list[dict], str]:
    """Düzümü ÖZÜ seçir: bakalavr → magistr → işçi tədris planı.

    Qaytarır ``(sətirlər, düzüm)`` — ``"bachelor"`` / ``"master"`` / ``"work"``.

    ⚠️ Saytda ÜÇ ayrı cədvəl düzümü var. Üçüncüsü — «İŞÇİ TƏDRİS PLANI»
    (`PLAN_<ad>.docx.pdf`, `00_<ad>.pdf`) — 2026-09-10 süpürgəsində üzə çıxdı və
    əvvəlki iki parserin heç biri onu oxumurdu (0 sətir). O düzüm ən qiymətlisidir:
    semestr bölgüsünü SAXLAYIR. Bax `plan_import_work.py`.
    """
    from apps.registrar.plan_import_work import extract_work_rows

    rows = extract_rows(pdf_path)
    if len(rows) >= LOW_YIELD:
        return rows, "bachelor"
    master = extract_master_rows(pdf_path)
    best, layout = (master, "master") if len(master) > len(rows) else (rows, "bachelor")
    if len(best) >= LOW_YIELD:
        return best, layout
    work = extract_work_rows(pdf_path)
    return (work, "work") if len(work) > len(best) else (best, layout)


__all__ = [
    "extract_rows",
    "is_placeholder",
    "clean_subject_name",
    "extract_master_rows",
    "extract_any",
    "match_rows",
    "normalize",
    "is_elective_block",
    "LOW_YIELD",
]
