"""TAPŞIRIQ kitabçasının (kafedra vərəqləri) TƏMİZ oxunması — DB-siz.

Sahibin qərarı 2026-09-19. Vərəq → sətir dict-ləri; qrup/seçmə bloku/xüsusi sətir
qaydaları burada; kataloqla tutuşdurma `task_workbook_import`-dadır.
"""

from __future__ import annotations

import html
import re
import unicodedata
from datetime import date

from apps.workload.constants import RowKind

_AZ_MAP = str.maketrans(
    {
        "ə": "e",
        "Ə": "e",
        "ö": "o",
        "Ö": "o",
        "ü": "u",
        "Ü": "u",
        "ğ": "g",
        "Ğ": "g",
        "ş": "s",
        "Ş": "s",
        "ç": "c",
        "Ç": "c",
        "ı": "i",
        "I": "i",
        "İ": "i",
    }
)


def slug_name(value) -> str:
    """«Rüstəm Əli» → `rustemeli` — AZ hərfləri ASCII, yalnız [a-z0-9] (modul dövrü olmasın deyə
    `accounts.username_repair.slug_name`-in yerli surəti)."""
    text = html.unescape(str(value or ""))
    text = unicodedata.normalize("NFKC", text).translate(_AZ_MAP)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]", "", text)


#: Vərəq adı (prefiks) → kafedra adı (OrgUnit chair). Kitabça vərəq adlarını qısaldır.
SHEET_TO_CHAIR = {
    "xarici dil": "Xarici dillər",
    "ekologiya": "Ekologiya",
    "tebiet elml": "Təbiət elmləri",
    "mexanika": "Mexanika və riyaziyyat",
    "proqramlasdirma": "Proqramlaşdırma və informasiya təhlükəsizliyi",
    "informasiya texnolog": "İnformasiya texnologiyaları",
}
#: İxtisas sütunundakı qısaltmalar → ixtisas (OrgUnit specialty) adı.
SPECIALTY_ALIASES = {
    "psixologiya": "Psixologiya",
    "teh sos ps x": "Təhsildə sosial psixoloji xidmət",
    "tehsos": "Təhsildə sosial psixoloji xidmət",
    "sosial is": "Sosial Iş",
    "komp muh": "Kompüter Mühəndisliyi",
    "kompmuh": "Kompüter Mühəndisliyi",
    "inform teh": "İnformasiya Təhlükəsizliyi",
    "informteh": "İnformasiya Təhlükəsizliyi",
    "komp elm": "Kompüter elmləri",
    "kompelm": "Kompüter elmləri",
    "mexat ve rob": "Mexatronika və robototexnika mühəndisliyi",
    "mexatverob": "Mexatronika və robototexnika mühəndisliyi",
    "inform tex": "İnformasiya Texnologiyaları",
    "informtex": "İnformasiya Texnologiyaları",
    "cihaz muh": "Cihaz Mühəndisliyi",
    "cihazmuh": "Cihaz Mühəndisliyi",
    "biologiya": "Biologiya",
    "ekologiya": "Ekologiya",
    "mesecilik": "Meşəçilik",
    "ekolog muh": "Ekologiya Mühəndisliyi",
    "ekologmuh": "Ekologiya Mühəndisliyi",
    "iqtisadiyyat": "İqtisadiyyat",
    "maliyye": "Maliyyə",
    "muhasibat": "Mühasibat",
    "marketinq": "Marketinq",
    "biznesin idare edilmesi": "Biznesin idarə edilməsi",
    "turizm": "Turizm işi",
    "filologiya azerbaycan dili ve edebiyyati": "Azərbaycan dili və ədəbiyyatı",
    "filologiya ingilis dili ve edebiyyati": "Filologiya (İngilis dili və ədəbiyyatı)",
    "qida muh": "Qida mühəndisliyi",
    "qidamuh": "Qida mühəndisliyi",
    "su bioehtiyyatlari": "Su Bioehtiyyatları və Akvakultura",
    "genetika": "Genetika",
    "malekulyar biologiya": "Malekulyar biologiya",
    "molekulyar biologiya": "Malekulyar biologiya",
    "beynelxalq munasibetler": "Beynəlxalq münasibətlər",
    "regionsunasliq": "Regionşünaslıq",
    "dov beled id": "Dövlət və bələdiyyə idarəetməsi",
    "dovbeledid": "Dövlət və bələdiyyə idarəetməsi",
    "qrafik dizayn": "Dizayn (Qrafik)",
    "interyer dizayn": "Dizayn (İnteryer)",
    "felsefe": "Fəlsəfə",
    "tarix": "Tarix",
    "yer qur ve kad": "Yerquruluşu və daşınmaz əmlakın kadastrı",
    "yerqurvekad": "Yerquruluşu və daşınmaz əmlakın kadastrı",
    "biotex": "Biotexnologiya",
    "biotexnolog": "Biotexnologiya",
    "bioekologiya": "Bioekologiya",
    "etraf muh": "Ətraf mühitin mühafizə və bərpa metodları",
}
#: Qrup kodu → sektor sözləri (qrup adının sonunda) — «az» defoltdur, DB-də bəzən yazılmır.
SECTOR_WORDS = ("az", "ing", "rus", "AZ", "ING", "İNG", "RUS", "Az", "Ing")
#: Qrup kodundakı ixtisas hərfləri (İxtisas sütunu boş/uyğunsuz olanda ehtiyat).
GROUP_CODE_SPECIALTY = {
    "K": "Kompüter Mühəndisliyi",
    "KE": "Kompüter elmləri",
    "İ": "İnformasiya Təhlükəsizliyi",
    "IT": "İnformasiya Texnologiyaları",
    "İT": "İnformasiya Texnologiyaları",
    "MRM": "Mexatronika və robototexnika mühəndisliyi",
    "CM": "Cihaz Mühəndisliyi",
    "BİO": "Biologiya",
    "BIO": "Biologiya",
    "SBİO": "Su Bioehtiyyatları və Akvakultura",
    "SBIO": "Su Bioehtiyyatları və Akvakultura",
    "EKO": "Ekologiya",
    "EM": "Ekologiya Mühəndisliyi",
    "M": "Meşəçilik",
    "QM": "Qida mühəndisliyi",
    "Bİ": "Biznesin idarə edilməsi",
    "BI": "Biznesin idarə edilməsi",
    "ML": "Maliyyə",
    "MU": "Mühasibat",
    "MRK": "Marketinq",
    "TSPX": "Təhsildə sosial psixoloji xidmət",
    "Sİ": "Sosial Iş",
    "SI": "Sosial Iş",
    "BM": "Beynəlxalq münasibətlər",
    "R": "Regionşünaslıq",
    "G": "Genetika",
    "MB": "Malekulyar biologiya",
    "E": "Ekologiya",
    "F": "Azərbaycan dili və ədəbiyyatı",
    "T": "Turizm işi",
    "TB": "Turizm bələdçiliyi",
}
SEASONS = {"payiz": "fall", "yaz": "spring"}
PERIODS = {
    "fall": ("Payız", date(2026, 9, 15), date(2027, 1, 31)),
    "spring": ("Yaz", date(2027, 2, 1), date(2027, 6, 30)),
}
_SPLIT_RE = re.compile(r"[\n|;,]+|\s{3,}")
_BLOCK_CHOSEN_RE = re.compile(r"^\s*\d+[.)]?\s*(.+?)\s*\+\s*$")
_ITEM_RE = re.compile(r"^\s*\d+[.)]\s*")
_QKU_CODE_RE = re.compile(r"^QKU-(\d+)$")


def _title_az(word: str) -> str:
    """«MİNAYƏ» → «Minayə» (Python title() «İ»-ni pozur)."""
    word = _text(word)
    if not word:
        return ""
    lower = "".join("i" if ch == "İ" else "ı" if ch == "I" else ch.lower() for ch in word[1:])
    return word[0] + lower


_GROUP_YEAR_RE = re.compile(r"^(?:\d/)?(\d{3,4})")


def group_year_from_name(token: str, default_year: int) -> int:
    """QKU qrup adı → qəbul ili: rəqəm blokunun son rəqəmi ilin son rəqəmidir
    («235 K» → 2025, «2236 M» → 2026, «3/336 F» → 2026); tanınmasa default."""
    match = _GROUP_YEAR_RE.match(str(token or "").strip())
    if not match:
        return default_year
    digit = int(match.group(1)[-1])
    decade = default_year // 10 * 10
    year = decade + digit
    return year if year <= default_year else year - 10


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def _int(value) -> int:
    try:
        return int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def _sum_numbers(value) -> int:
    return sum(int(part) for part in re.findall(r"\d+", _text(value)))


def _key(value) -> str:
    """Qrup/ad açarı: boşluqsuz, kiçik hərf, İ/I fərqsiz, apostrofsuz."""
    text = _text(value).replace("İ", "i").replace("I", "i").replace("ı", "i")
    return re.sub(r"[\s'’`.\-_()]+", "", text).lower()


_GROUP_BOUNDARY_RE = re.compile(r"\s+(?=\d{2,4}(?:/\d+)?\s*[A-Za-zİƏÖÜĞŞÇ])")


def split_tokens(value) -> list[str]:
    """«036\\n3/336 F», «235 K     235 İT», «336 F1,2», «233 K ing 233 İT ing» → ayrı qrup adları."""
    raw = _text(value)
    match = re.match(r"^(\S+\s+\D+?)(\d)\s*,\s*(\d)\s*$", raw)
    if match:
        return [f"{match.group(1)}{match.group(2)}", f"{match.group(1)}{match.group(3)}"]
    tokens = []
    for part in _SPLIT_RE.split(raw):
        for piece in _GROUP_BOUNDARY_RE.split(part.strip()):
            piece = re.sub(r"\s+", " ", piece.strip().strip("'’"))
            if not piece or piece in SECTOR_WORDS or (piece.isdigit() and len(piece) < 3):
                continue
            tokens.append(piece)
    return tokens


def is_block(raw: str) -> bool:
    slug = slug_name(raw)
    return "blok" in slug or "secme" in slug or "sesme" in slug or re.match(r"^\s*(ATMF|SF\b|S\.F)", raw) is not None


def block_chosen_subject(raw: str) -> str:
    """Seçmə bloku → seçilən fənn: «+» ilə işarələnən; tək bənd; və ya «ATMF: X» formasında X."""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    for line in lines:
        match = _BLOCK_CHOSEN_RE.match(line)
        if match:
            return match.group(1).strip(" +")
    items = [_ITEM_RE.sub("", line).strip(" +") for line in lines if _ITEM_RE.match(line)]
    if len(items) == 1:
        return items[0]
    if not items:
        head = re.sub(r"^\s*(ATMF|SF|S\.F)[^:]*:\s*", "", " ".join(lines)).strip()
        if head and head != " ".join(lines):
            return head
    return ""


def _special_row_kind(record: dict) -> str:
    """Kontakt saatı olmayan xüsusi sətirlər: təcrübə / buraxılış-dissertasiya / dissertant."""
    if record["lecture_total"] or record["seminar_total"] or record["lab_total"]:
        return ""
    slug = slug_name(record["subject_text"])
    if "tecrube" in slug:
        return RowKind.PRACTICE
    if "buraxilis" in slug or "dissertasiya" in slug or "magistr" in slug:
        return RowKind.THESIS
    if "doktorant" in slug or "dissertant" in slug:
        return RowKind.POSTGRAD
    return ""


def clean_subject_name(raw: str) -> str:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    return " ".join(lines)[:255]


def parse_sheet(ws) -> tuple[str, list[dict]]:
    """Vərəq → sətir dict-ləri. İki düzülüş: tam (21 sütun) və qısa (Proqramlaşdırma)."""
    compact = ws.max_column <= 13
    records = []
    for index, row in enumerate(ws.iter_rows(values_only=True), 1):
        if index < 11:
            continue
        season = SEASONS.get(slug_name(row[0]))
        subject = _text(row[2]) if len(row) > 2 else ""
        if not season or not subject:
            continue

        def get(i, row=row):
            return row[i] if i < len(row) else None

        record = {
            "sheet": ws.title,
            "line": index,
            "season": season,
            "groups_text": _text(get(1)),
            "subject_text": subject,
            "specialty_text": _text(get(3)),
            "student_count_text": _text(get(4)),
            "student_count": _sum_numbers(get(4)),
        }
        if compact:
            record.update(
                union_count=1,
                subgroup_count=1,
                lecture_total=_int(get(5)),
                seminar_total=_int(get(6)),
                lab_total=_int(get(7)),
                teacher_text=_text(get(8)),
                total_hours=_int(get(9)),
                credits="",
            )
        else:
            record.update(
                union_count=max(_int(get(5)), 1),
                subgroup_count=max(_int(get(6)), 1),
                lecture_plan=_int(get(7)),
                lecture_total=_int(get(8)),
                seminar_plan=_int(get(9)),
                seminar_total=_int(get(10)),
                lab_plan=_int(get(11)),
                lab_total=_int(get(12)),
                consult_hours=_int(get(13)),
                exam_hours=_int(get(14)),
                thesis_hours=_int(get(15)),
                postgrad_hours=_int(get(16)),
                practice_research_hours=_int(get(17)),
                practice_production_hours=_int(get(18)),
                total_hours=_int(get(19)),
                credits=_text(get(20)),
                teacher_text="",
            )
        records.append(record)
    return ws.title, records
