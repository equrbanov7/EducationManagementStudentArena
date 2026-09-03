"""Saf (SQL-siz) hesablama funksiyaları — hesabatın bütün riyaziyyatı burada.

Bu modul qəsdən heç bir bazaya toxunmur: nərdivan (ladder) balansı, histoqram
bölgüsü, xana təsnifatının Python güzgüsü və Markdown formatlayıcıları burada
saxlanılır ki, testlər canlı baza olmadan da işləsin.
"""

from __future__ import annotations

import html
import random
import re
from dataclasses import dataclass, field
from decimal import Decimal

_WHITESPACE = re.compile(r"\s+")

# ── Mənbə xana təsnifatı (import fazalarının güzgüsü) ─────────────────────────
# Bu sabitlər ``apps/legacy_import/services/rehearsal_journal_points_source.py``
# ilə EYNİ olmalıdır.  Güzgü qəsdəndir: hesabat müqayisə etdiyi məntiqi
# MÜSTƏQİL şəkildə yenidən hesablayır (J8 fazasının öz prinsipi).
CALENDAR_MONTHS = frozenset(f"{month:02d}" for month in range(1, 13))
KOLLOKVIUM_MONTHS = ("k1", "k2", "k3")
SELF_WORK_MONTH = "si"
EXAM_MONTH = "im"
RESIT_MONTH = "im2"
COMPONENT_MONTHS = frozenset((*KOLLOKVIUM_MONTHS, SELF_WORK_MONTH))
FINAL_MONTHS = frozenset((EXAM_MONTH, RESIT_MONTH))

PRESENT_TOKEN = "ie"  # «iştirak edib» — DAVAMİYYƏT, bal deyil
ABSENT_TOKEN = "qb"  # «qayıb»
MARK_SCORE_MAX = 10
COMPONENT_SCORE_MAX = 10
FINAL_SCORE_MAX = 100
DEFAULT_ENTRY_SCORE_MAX = 50
ARCHIVE_CUTOFF = "2022-03-30"

DOMAIN_MARKS = "marks"
DOMAIN_COMPONENTS = "components"
DOMAIN_FINALS = "finals"
DOMAIN_UNKNOWN = "unknown_code"
DOMAINS = (DOMAIN_MARKS, DOMAIN_COMPONENTS, DOMAIN_FINALS)

DOMAIN_LABELS = {
    DOMAIN_MARKS: "Təqvim xanaları (davamiyyət + gündəlik bal)",
    DOMAIN_COMPONENTS: "Komponent xanaları (kollokvium + sərbəst iş)",
    DOMAIN_FINALS: "İmtahan xanaları (im / im2)",
    DOMAIN_UNKNOWN: "Naməlum ay kodu",
}

OUTCOME_EMPTY = "empty"
OUTCOME_UNREADABLE = "unreadable"
OUTCOME_WRITABLE = "writable"
OUTCOME_OUT_OF_SCOPE = "out_of_scope"


def domain_of(month_id: str) -> str:
    """``month_id`` → domen adı; tanınmayan kod ``unknown_code``-dur.

    DİQQƏT: import-un ``_domain_of``-u tanınmayan kodu say balansından TAMAM
    kənarda saxlayır.  Hesabat onu gizlətmir — ayrıca sətir kimi göstərir.
    """

    if month_id in CALENDAR_MONTHS:
        return DOMAIN_MARKS
    if month_id in COMPONENT_MONTHS:
        return DOMAIN_COMPONENTS
    return DOMAIN_FINALS if month_id in FINAL_MONTHS else DOMAIN_UNKNOWN


def _is_digits(text: str) -> bool:
    return text.isdigit()


def classify_cell(month_id: str, day_number: str, point: str) -> tuple[str, str]:
    """``(domen, nəticə)`` — import təsnifatçılarının saf güzgüsü.

    ``nəticə`` ∈ {``empty``, ``unreadable``, ``writable``, ``out_of_scope``}.
    ``writable`` = "bu xana hədəfdə bir sətir yaratmalıdır" deməkdir.
    """

    domain = domain_of(month_id)
    if domain == DOMAIN_UNKNOWN:
        return domain, OUTCOME_OUT_OF_SCOPE
    if domain == DOMAIN_MARKS:
        if point == "":
            return domain, OUTCOME_EMPTY
        if point in (PRESENT_TOKEN, ABSENT_TOKEN):
            return domain, OUTCOME_WRITABLE
        if _is_digits(point) and int(point) <= MARK_SCORE_MAX:
            return domain, OUTCOME_WRITABLE
        return domain, OUTCOME_UNREADABLE
    ceiling = COMPONENT_SCORE_MAX if domain == DOMAIN_COMPONENTS else FINAL_SCORE_MAX
    if point == "":
        return domain, OUTCOME_EMPTY
    if _is_digits(point) and int(point) <= ceiling:
        return domain, OUTCOME_WRITABLE
    return domain, OUTCOME_UNREADABLE


# ── Sətir mühasibatı: nərdivan ───────────────────────────────────────────────


@dataclass
class Ladder:
    """Bir domenin «mənbədən hədəfə» nərdivanı.

    ``steps`` ardıcıl çıxılan pillələrdir; ``target`` hədəfdə FAKTİKİ tapılan
    sətir sayıdır.  ``unexplained`` sıfır deyilsə hesabat bunu AÇIQ şəkildə
    «İZAH OLUNMAMIŞ FƏRQ» kimi yazır — səssiz itki ən qorxulu haldır.
    """

    name: str
    source_total: int
    target: int
    steps: list[tuple[str, int]] = field(default_factory=list)

    def deduct(self, label: str, count: int) -> None:
        self.steps.append((label, int(count)))

    @property
    def deducted(self) -> int:
        return sum(count for _label, count in self.steps)

    @property
    def expected(self) -> int:
        """Mənbədən çıxılan pillələrdən sonra hədəfdə gözlənilən sətir sayı."""

        return self.source_total - self.deducted

    @property
    def unexplained(self) -> int:
        """``gözlənilən − faktiki``.  Müsbət = itki, mənfi = hədəfdə artıq."""

        return self.expected - self.target

    @property
    def balanced(self) -> bool:
        return self.unexplained == 0


def ladder_table(ladder: Ladder) -> list[list[str]]:
    """Nərdivanı Markdown cədvəli sətirlərinə çevir (başlıqsız)."""

    rows: list[list[str]] = [["Mənbə sətri (xam)", fmt_int(ladder.source_total), ""]]
    running = ladder.source_total
    for label, count in ladder.steps:
        running -= count
        rows.append([f"− {label}", f"−{fmt_int(count)}", fmt_int(running)])
    rows.append(["**= Gözlənilən hədəf sətri**", "", f"**{fmt_int(ladder.expected)}**"])
    rows.append(["**Hədəfdə FAKTİKİ**", "", f"**{fmt_int(ladder.target)}**"])
    rows.append([unexplained_label(ladder.unexplained), "", f"**{fmt_signed(ladder.unexplained)}**"])
    return rows


def unexplained_label(delta: int) -> str:
    if delta == 0:
        return "✅ **İZAH OLUNMAMIŞ FƏRQ**"
    return "🔴 **İZAH OLUNMAMIŞ FƏRQ**"


# ── Bal bütövlüyü: histoqram ─────────────────────────────────────────────────

DELTA_BUCKETS = ("0", "±1", "±2", "±3–5", ">5")


def delta_bucket(delta: Decimal | float | int) -> str:
    """Fərqi histoqram qutusuna sal (0 / ±1 / ±2 / ±3–5 / >5)."""

    magnitude = abs(Decimal(str(delta)))
    if magnitude == 0:
        return "0"
    if magnitude <= 1:
        return "±1"
    if magnitude <= 2:
        return "±2"
    return "±3–5" if magnitude <= 5 else ">5"


def bucket_deltas(deltas) -> dict[str, int]:
    """Fərq siyahısını qutu → say lüğətinə çevir (bütün qutular mövcuddur)."""

    counts = dict.fromkeys(DELTA_BUCKETS, 0)
    for delta in deltas:
        counts[delta_bucket(delta)] += 1
    return counts


# ── Yekun balının güzgüsü (``finals.compute_final_result``) ──────────────────


def entry_score(lesson_sum, kollokvium_sum, cap=DEFAULT_ENTRY_SCORE_MAX) -> Decimal:
    """Giriş balı = (dərs balları + kollokvium), ``entry_score_max`` ilə clamp.

    ⚠️ Bu düstur HAZIRDA YENİLƏNİR (sahib dəqiq variantı verəcək) — hesabat
    giriş balı fərqini XƏTA kimi göstərmir, ayrıca «düstur gözləyir» bölməsində
    verir.
    """

    total = Decimal(str(lesson_sum or 0)) + Decimal(str(kollokvium_sum or 0))
    return min(total, Decimal(str(cap)))


def total_score(entry, exam, resit=None, bonus=0) -> Decimal:
    """Yekun = giriş + effektiv imtahan (təkrar varsa o) + bonus, 0..100 clamp."""

    effective_exam = Decimal(str(resit)) if resit is not None else Decimal(str(exam or 0))
    total = Decimal(str(entry)) + effective_exam + Decimal(str(bonus or 0))
    return max(Decimal("0"), min(Decimal("100"), total))


# ── Nümunə xanalarının dedup-u və xülasəsi (saf) ─────────────────────────────

# ``sample_cells_sql`` sütun sırası.
CELL_UNIQID, CELL_STUDENT, CELL_MONTH, CELL_DAY, CELL_TIME = 0, 1, 2, 3, 4
CELL_POINT, CELL_COUNTER, CELL_UPDATED, CELL_PK = 5, 6, 7, 8


def dedup_cells(rows):
    """J-V4 qalibləri: açar = jurnal + tələbə + ay + gün + saat.

    Sıralama import-un ``cell_rank``-ı ilə eynidir: ən böyük ``update_counter``
    → ən son ``updated_at`` → ən böyük ``id``.
    """

    best: dict = {}
    for row in rows:
        key = (row[CELL_UNIQID], row[CELL_STUDENT], row[CELL_MONTH], row[CELL_DAY], row[CELL_TIME])
        rank = (int(row[CELL_COUNTER] or 0), str(row[CELL_UPDATED] or ""), int(row[CELL_PK] or 0))
        current = best.get(key)
        if current is None or rank > current[0]:
            best[key] = (rank, row)
    return [entry[1] for entry in best.values()]


def summarise_cells(rows) -> dict:
    """Dedup edilmiş xanaları ``(tələbə, jurnal)`` üzrə xülasəyə çevir."""

    summary: dict = {}
    for row in dedup_cells(rows):
        key = (str(row[CELL_STUDENT]), row[CELL_UNIQID])
        bucket = summary.setdefault(
            key,
            {
                "qayib": 0,
                "istirak": 0,
                "seminar_sum": Decimal("0"),
                "seminar_count": 0,
                "kollokvium": Decimal("0"),
                "serbest": Decimal("0"),
                "imtahan": None,
                "tekrar": None,
            },
        )
        month, point = row[CELL_MONTH], row[CELL_POINT]
        domain, outcome = classify_cell(month, row[CELL_DAY], point)
        if outcome != OUTCOME_WRITABLE:
            continue
        if domain == DOMAIN_MARKS:
            if point == ABSENT_TOKEN:
                bucket["qayib"] += 1
            elif point == PRESENT_TOKEN:
                bucket["istirak"] += 1
            else:
                bucket["seminar_sum"] += Decimal(point)
                bucket["seminar_count"] += 1
        elif domain == DOMAIN_COMPONENTS:
            field_name = "serbest" if month == SELF_WORK_MONTH else "kollokvium"
            bucket[field_name] += Decimal(point)
        elif domain == DOMAIN_FINALS:
            bucket["imtahan" if month == EXAM_MONTH else "tekrar"] = Decimal(point)
    return summary


# ── Təkrarlana bilən nümunə seçimi ───────────────────────────────────────────


def pick_sample(keys, *, seed: int, size: int) -> list:
    """Toxumla təkrarlana bilən nümunə: eyni toxum → eyni tələbələr.

    Siyahı əvvəlcə sıralanır ki, mənbə sıralaması dəyişsə də nəticə sabit qalsın.
    """

    ordered = sorted(keys)
    if len(ordered) <= size:
        return ordered
    return sorted(random.Random(seed).sample(ordered, size))


# ── MariaDB ``-B`` (batch) çıxışının açılması ────────────────────────────────

_BATCH_ESCAPES = {"0": "\0", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}


def unescape_batch_field(text: str) -> str:
    """``mariadb -B`` sətirlərində qaçırılmış xüsusi simvolları geri qaytar."""

    if "\\" not in text:
        return text
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            nxt = text[index + 1]
            out.append(_BATCH_ESCAPES.get(nxt, nxt))
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


# ── Legacy mətnin təmizlənməsi ───────────────────────────────────────────────


def clean_legacy_text(value) -> str:
    """MyEdu mətnini oxunaqlı et: HTML entity-lərini aç, boşluqları yığ.

    Legacy sahələrdə ``tərc&uuml;mə`` kimi ikiqat kodlanmış mətn və cüt boşluqlar
    var.  Bunlar məzmun fərqi DEYİL — müqayisədə saxta 🔴 verməsinlər deyə hər
    iki tərəf eyni normalizasiyadan keçir.
    """

    if value is None:
        return ""
    text = html.unescape(str(value))
    if "&" in text:  # ikiqat kodlanmış hallar (``&amp;uuml;``)
        text = html.unescape(text)
    return _WHITESPACE.sub(" ", text).strip()


# ── Markdown formatlayıcıları ────────────────────────────────────────────────


def fmt_int(value) -> str:
    """``2833993`` → ``2,833,993`` (boş dəyər ``—``)."""

    if value is None:
        return "—"
    return f"{int(value):,}"


def fmt_signed(value) -> str:
    if value is None:
        return "—"
    number = int(value)
    return "0" if number == 0 else f"{number:+,}"


def fmt_num(value, digits: int = 2) -> str:
    """Onluq dəyər; tam ədəddirsə kəsr hissəsi yazılmır."""

    if value is None or value == "":
        return "—"
    number = Decimal(str(value))
    if number == number.to_integral_value():
        return str(int(number))
    return f"{number:.{digits}f}"


def fmt_pct(part, whole, digits: int = 1) -> str:
    if not whole:
        return "—"
    return f"{(100.0 * float(part) / float(whole)):.{digits}f} %"


def fmt_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    return f"{int(seconds // 60)} dəq {seconds % 60:.0f} s"


def md_table(headers, rows) -> str:
    """Sadə Markdown cədvəli; hüceyrələrdəki ``|`` qaçırılır."""

    def cell(value) -> str:
        return str(value).replace("|", "\\|")

    lines = ["| " + " | ".join(cell(head) for head in headers) + " |"]
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(cell(value) for value in row) + " |")
    return "\n".join(lines)


EXACT_MATCH = Decimal("0")  # B008: default arqument çağırış olmasın deyə modul səviyyəsində


def diff_flag(source_value, target_value, tolerance: Decimal = EXACT_MATCH) -> str:
    """Yan-yana müqayisədə qırmızı işarə (fərq varsa)."""

    if source_value is None and target_value is None:
        return ""
    if source_value is None or target_value is None:
        return "🔴"
    delta = abs(Decimal(str(source_value)) - Decimal(str(target_value)))
    return "" if delta <= tolerance else "🔴"
