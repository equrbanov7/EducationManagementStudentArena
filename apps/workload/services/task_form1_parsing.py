"""Kafedranın «Forma 1» dərs yükü cədvəli (Word, ``.docx``) — DB-siz oxu (sahib 2026-10-12).

Hər müəllim blokunda: müəllim xanası (elmi dərəcə + Soyad Ad Ata adı + ştat qeydi),
sətirlər (qrup, fənn, tələbə sayı, iki semestrin Mühazirə/Məşğələ/Laboratoriya saatları),
«CƏMİ» / «Ştat ümumi» / «UNİVERSİTET ÜZRƏ CƏMİ» yekunları və bəzən «SAAT HESABI DƏRS YÜKÜ»
alt-başlığı (ondan sonrakı sətirlər növbəti yekuna qədər saathesabıdır).

Sütunlar fayldan-fayla fərqlidir (Təbiət: 30 sütun, fənn iki birləşmiş xanada; İT: 26
sütun, ayrıca sütun-nömrəsi sətri) — mövqe SABİT YAZILMIR, başlıq sətirlərinin
etiketlərindən tapılır: «Müəllim…» / «…QRUP…» / «FƏNNİN ADI» / «Tələbə…»; semestr
«BİRİNCİ» / «İKİNCİ» üst başlığından, fəaliyyət «Mühazirə» / «Məşğələ (seminar)» /
«Laboratoriya» etiketindən. Seçmə blokunun seçimi :mod:`.task_workbook_choice` ilə
(qalın > ayrıca «+» > tək bənd > operatorun ``--choice``-u).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .task_workbook_choice import CHOSEN_NONE, choose_block_subject, docx_cell_chunks
from .task_workbook_parsing import is_block, slug_name, split_tokens

_ACTIVITY_LABELS = (("muhazire", "lecture"), ("mesgele", "seminar"), ("seminar", "seminar"), ("laborator", "lab"))
_SEMESTERS = (("birinci", "fall"), ("ikinci", "spring"))
_SECTORS = {"az", "ing", "rus"}
#: Müəllim xanasında ad OLMAYAN sözlər (slug): dərəcə/ad/vəzifə/ştat/ata adı şəkilçisi.
_NAME_STOPWORDS = {
    "b", "u", "f", "d", "e", "t", "r", "p", "k", "i", "dos", "dosent", "prof", "professor", "kafedra",
    "mudiri", "muellim", "bas", "baskicik", "elmi", "isci", "stat", "yarimstat", "yarim", "saat", "hesabi",
    "s", "h", "q", "o", "qizi", "oglu", "ci", "cu", "cı", "ilden", "isleyir", "ve", "kafedrasi",
}  # fmt: skip
_HOURLY_SECTION_RE = re.compile(r"saathesabi(ders|desr|dersler)")


@dataclass
class Form1Entry:
    line: int
    teacher_text: str
    name_words: tuple
    hourly: bool
    season: str
    groups_text: str
    group_keys: frozenset
    subject_text: str
    chosen_subject: str
    chosen_by: str
    hours: dict = field(default_factory=dict)


def hours_value(text) -> int:
    """«30» → 30, «15*2» → 30, «9+8+10» → 27, «» → 0."""
    total = 0
    for part in re.split(r"\s*\+\s*", str(text or "").strip()):
        numbers = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", part)]
        if not numbers:
            continue
        value = 1.0
        for number in numbers if "*" in part or "x" in part.lower() else numbers[:1]:
            value *= number
        total += int(value)
    return total


def group_key(token: str) -> str:
    """Qrup açarı: boşluqsuz, kiçik, İ/I fərqsiz, sonundakı «az» atılır («234 BİO AZ» = «234 BİO»)."""
    key = re.sub(r"[\s'’`.\-_()]+", "", str(token or "").replace("İ", "i").replace("I", "i").replace("ı", "i"))
    key = key.lower()
    return key[:-2] if key.endswith("az") and len(key) > 4 else key


def group_tokens(text: str) -> list[str]:
    """Forma 1 qrup xanası → qrup adları; «233BİO SBİO İNG» → «233 BİO İNG», «233 SBİO İNG»."""
    result = []
    for part in re.split(r"[\n,;]+", str(text or "")):
        for token in split_tokens(part.strip()):
            words = token.split()
            match = re.match(r"^((?:\d+/)?\d{2,4})\s*(\S*)$", words[0]) if words else None
            if not match or len(words) == 1:
                result.append(token)
                continue
            number, codes, sector = match.group(1), [match.group(2)] if match.group(2) else [], ""
            for word in words[1:]:
                if slug_name(word) in _SECTORS:
                    sector = word
                else:
                    codes.append(word)
            for code in codes or [""]:
                result.append(" ".join(x for x in (number, code, sector) if x))
    return result


def name_words(text: str) -> tuple:
    """Müəllim xanası → ad sözlərinin slug-ları (dərəcə, vəzifə, ştat qeydi, il atılır)."""
    head = re.split(r"(?i)\d{4}\s*[-–]?\s*c[iıuü]", str(text or ""))[0]
    head = re.sub(r"^\s*\d+\s*[.)]?", " ", head)
    # «b.ü.f.dMahmud» — dərəcə ilə ad yapışıb: kiçik → böyük hərf sərhədində ayır.
    head = re.sub(r"(?<=[a-zəöüğışç])(?=[A-ZƏÖÜĞŞÇİ])", " ", head)
    words = []
    for word in re.split(r"[\s.,;:()/\\\-–]+", head):
        slug = slug_name(word)
        if len(slug) < 3 or slug in _NAME_STOPWORDS or re.search(r"\d", word):
            continue
        words.append(slug)
    return tuple(words)


def is_hourly_teacher(text: str) -> bool:
    slug = slug_name(text)
    return "saathesabi" in slug or bool(re.search(r"(?i)\bs\s*/\s*h\b", str(text or "")))


def _columns(table) -> dict:
    """Başlıq sətirlərindən sütun xəritəsi; tapılmasa ``ValueError``."""
    header_rows = []
    for index, row in enumerate(table.rows[:8]):
        texts = [slug_name(cell.text) for cell in row.cells]
        header_rows.append(texts)
        if any(text.startswith("muhazire") for text in texts):
            label_row = index
            break
    else:
        raise ValueError("Forma 1: «Mühazirə» başlığı tapılmadı")
    labels = header_rows[label_row]
    width = len(labels)
    columns = {"label_row": label_row, "activities": {}}
    for key, needle in (("teacher", "muellim"), ("groups", "qrup"), ("subject", "fenn"), ("students", "telebe")):
        for col in range(width):
            if any(needle in rows[col] for rows in header_rows if col < len(rows)):
                columns[key] = col
                break
    for col, label in enumerate(labels):
        semester = ""
        for rows in header_rows[:label_row]:
            for word, season in _SEMESTERS:
                if col < len(rows) and rows[col].startswith(word):
                    semester = season
        for needle, activity in _ACTIVITY_LABELS:
            if semester and label.startswith(needle):
                columns["activities"].setdefault((semester, activity), col)
    missing = [k for k in ("teacher", "groups", "subject") if k not in columns]
    if missing or not columns["activities"]:
        raise ValueError(f"Forma 1: sütunlar tapılmadı: {missing or 'fəaliyyət saatları'}")
    return columns


def _is_total(*texts) -> bool:
    # «Ümumi:», «Ştat ümumi:», «Saat hesabı ümumi:», «Ümumi yük» yekundur; «Ümumi kimya» / «Ümumi biologiya»
    # isə FƏNNDİR (2026-10-15: əvvəlki «"umumi" in s» belə fənləri səssizcə atırdı).
    slugs = [slug_name(text) for text in texts]
    return any(
        s.startswith("cemi")
        or s.endswith("cemi")
        or "universitet" in s
        or s.endswith("umumi")
        or s.startswith("umumiyuk")
        or "netice" in s
        for s in slugs
        if s
    )


def parse_form1(document, overrides: dict | None = None) -> tuple[list[Form1Entry], list[dict]]:
    """``docx.Document`` → (yük sətirləri, ötürülən sətirlərin qeydləri). ``line`` = cədvəl sətir indeksi (0-dan)."""
    overrides = overrides or {}
    table = document.tables[0]
    cols = _columns(table)
    entries, skipped = [], []
    teacher_text, hourly_section = "", False
    used_overrides = set()
    for index, row in enumerate(table.rows):
        if index <= cols["label_row"]:
            continue
        cells = row.cells
        texts = [cell.text.strip() for cell in cells]
        if all(not t or t.isdigit() for t in texts):
            continue  # sütun nömrələri / boş sətir
        current_teacher = texts[cols["teacher"]]
        if current_teacher and current_teacher != teacher_text:
            teacher_text, hourly_section = current_teacher, False
        groups_text, subject_text = texts[cols["groups"]], texts[cols["subject"]]
        if _HOURLY_SECTION_RE.search(slug_name(groups_text) + slug_name(subject_text)):
            hourly_section = True
            continue
        if _is_total(groups_text, subject_text):
            # İT: «Ştat ümumi:» yekunundan sonra saathesabı sətirləri gəlir; digər yekunlar bölməni bağlayır.
            hourly_section = slug_name(subject_text).startswith("statumumi")
            continue
        if not subject_text or slug_name(subject_text).startswith("magdis"):
            if subject_text:
                skipped.append({"line": index, "reason": "non_teaching", "subject": subject_text})
            continue
        hours = {
            key: hours_value(texts[col]) for key, col in cols["activities"].items() if col < len(texts)
        }  # fmt: skip
        chosen, chosen_by = "", ""
        if is_block(subject_text):
            override = overrides.get(index, "")
            chosen, chosen_by = choose_block_subject(docx_cell_chunks(cells[cols["subject"]]), override)
            if override:
                used_overrides.add(index)
                if chosen_by != "override":
                    raise ValueError(f"--choice {index}: xanada artıq seçim işarəsi var ({chosen_by})")
        base = {
            "line": index,
            "teacher_text": teacher_text,
            "name_words": name_words(teacher_text),
            "hourly": hourly_section or is_hourly_teacher(teacher_text),
            "groups_text": groups_text,
            "group_keys": frozenset(group_key(t) for t in group_tokens(groups_text)),
            "subject_text": subject_text,
            "chosen_subject": chosen,
            "chosen_by": chosen_by,
        }
        produced = False
        for season in ("fall", "spring"):
            season_hours = {a: h for (s, a), h in hours.items() if s == season and h}
            if season_hours:
                entries.append(Form1Entry(season=season, hours=season_hours, **base))
                produced = True
        if not produced:
            skipped.append({"line": index, "reason": "no_contact_hours", "subject": subject_text})
        elif chosen_by == CHOSEN_NONE:
            skipped.append({"line": index, "reason": "no_choice_marker", "subject": subject_text})
    unknown = sorted(set(overrides) - used_overrides)
    if unknown:
        raise ValueError(f"--choice: bu sətirlər seçmə bloku deyil və ya cədvəldə yoxdur: {unknown}")
    return entries, skipped


__all__ = ["Form1Entry", "group_key", "group_tokens", "hours_value", "is_hourly_teacher", "name_words", "parse_form1"]
