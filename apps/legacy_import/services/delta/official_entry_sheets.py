"""Köhnə sistemin RƏSMİ bal vərəqləri (``balvereqi_logs``) — oxu və hədəf giriş balı qaydası (SAF funksiyalar).

Niyə (SYS-1, 2026-11-03)
------------------------
J5b (``rehearsal_journal_entry_scores_source``) tarixi giriş balını yalnız köhnə ``yekun`` cədvəlindən DƏQİQ
götürür, o cədvəl isə yalnız 2022/2023 Payızı əhatə edir. Sonrakı semestrlərdə giriş balı düsturla
(``10 − 0.5×qayıb + k1..k3 + si``) BƏRPA olunub — köhnə sistemin özü isə davamiyyəti ``10×(N−qayıb)/N`` kimi,
seminarı ortalama ilə hesablayırdı. Nəticə: bəzi tələbələrin yeni kabinetində giriş 1–8 bal fərqlidir və
51 həddinin ətrafında «keçib» → «kəsr» olur (məs. 34+17=51 → 33+17=50).

Köhnə sistemin çap etdiyi rəsmi vərəq ``balvereqi_logs.data``-dadır (HTML export, bir export-da qrup başına bir
cədvəl). Sütunlar::

    № | A.S.A. | Davamiyyət | Sərbəst iş | Sem/lab | Giriş | İmtahan | Güzəşt G/İ | Yekun | T.imtahan | Qiymət | Qeyd

Hədəf giriş balı (:func:`target_entry`)
--------------------------------------
Çap olunmuş «Giriş» sütunu ara dəyərləri (davamiyyəti 1 onluğa) yuvarlaqlaşdırıb toplayır, «Yekun» isə
yuvarlaqlaşdırılmamış girişdən hesablanır — sətirlərin ~2 %-ində ``Yekun = Giriş − 1 + İmtahan`` olur
(məs. 9.46 + 8 + 29 → Giriş 47, Yekun 46.46 + 25 = 71). Keçid/kəsr qərarını köhnə sistem YEKUN-dan verib,
yeni sistemdə isə yekun = giriş (tam ədəd) + imtahan. Ona görə:

* Yekun və onu izah edən imtahan (``T.imtahan`` > 0 isə o, yoxsa ``İmtahan``) varsa və ``Yekun − imtahan``
  ``{Giriş, Giriş − 1}``-dirsə → hədəf ``Yekun − imtahan`` (yeni yekun rəsmi yekunla EYNİ olur);
* əks halda → çap olunmuş ``Giriş``;
* 0..50 xaricindədirsə (mənfi davamiyyət, ``NAN``) → hədəf yoxdur.

``T.imtahan = 0`` köhnə vərəqdə «təkrar imtahan yoxdur» deməkdir (Yekun ``İmtahan`` ilə uyğun gəlir).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

ENTRY_MAX = Decimal("50")
ZERO = Decimal("0")

_TABLE = re.compile(r"<table\b([^>]*)>(.*?)</table>", re.S)
_ROW = re.compile(r'<tr class="user_(\d+)"[^>]*>(.*?)</tr>', re.S)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_PHP = re.compile(r"<\?php.*?\?>", re.S)
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?")
_GROUP_ID = re.compile(r'data-id="(\d+)"')
_SUBJECT = re.compile(r"Fənn:\s*(.*?)<br", re.S)
_TEACHER = re.compile(r"Müəllim:\s*(.*?)<br", re.S)
_HOURS = re.compile(r"Seçilmiş dərs saatı:\s*(\d+)")
ATTENDANCE_FAIL_MARK = "(Kəsr)"
CELL_COUNT = 12


@dataclass(frozen=True)
class SheetRow:
    """Bir tələbənin vərəqdəki sətri (rəqəm deyilsə ``None``)."""

    student_id: int
    entry: Decimal | None
    exam: Decimal | None
    total: Decimal | None
    resit: Decimal | None
    concession: str
    attendance_fail: bool


@dataclass(frozen=True)
class SheetTable:
    """Export-dakı bir cədvəl — bir qrup × fənn × müəllim."""

    group_id: int
    subject: str
    teacher: str
    hours: int | None
    rows: tuple[SheetRow, ...]


def _clean(fragment: str) -> str:
    """Xana mətni: teq atılır, entity-lər (ikiqat qaçırılmış ola bilər) açılır, boşluq sıxılır."""

    value = _SPACE.sub(" ", _TAG.sub(" ", fragment))
    return _SPACE.sub(" ", html.unescape(html.unescape(value))).strip()


def number(value: str) -> Decimal | None:
    match = _NUMBER.match((value or "").strip())
    if not match:
        return None
    try:
        return Decimal(match.group(0))
    except InvalidOperation:  # pragma: no cover - regex yalnız rəqəm buraxır
        return None


def parse_export(data: str) -> list[SheetTable]:
    """``balvereqi_logs.data`` → cədvəllər. Format tanınmayan cədvəl/sətir sadəcə atılır."""

    document = _PHP.sub("", html.unescape(data or ""))
    tables = []
    for attrs, body in _TABLE.findall(document):
        group = _GROUP_ID.search(attrs)
        subject = _SUBJECT.search(body)
        if not group or not subject:
            continue
        teacher = _TEACHER.search(body)
        hours = _HOURS.search(body)
        rows = []
        for student_id, row in _ROW.findall(body):
            cells = [_clean(cell) for cell in _CELL.findall(row)]
            if len(cells) != CELL_COUNT:
                continue
            rows.append(
                SheetRow(
                    student_id=int(student_id),
                    entry=number(cells[5]),
                    exam=number(cells[6]),
                    total=number(cells[8]),
                    resit=number(cells[9]),
                    concession=cells[7],
                    attendance_fail=ATTENDANCE_FAIL_MARK in cells[2],
                )
            )
        tables.append(
            SheetTable(
                group_id=int(group.group(1)),
                subject=_clean(subject.group(1)),
                teacher=_clean(teacher.group(1)) if teacher else "",
                hours=int(hours.group(1)) if hours else None,
                rows=tuple(rows),
            )
        )
    return tables


def counted_exam(*, entry, exam, total, resit) -> Decimal | None:
    """Rəsmi yekunun içindəki imtahan balı: ``T.imtahan`` (> 0) yekunu izah edirsə o, yoxsa ``İmtahan``."""

    if total is None or entry is None:
        return None
    for candidate in (resit if resit else None, exam):
        if candidate is not None and total - candidate in (entry, entry - 1):
            return candidate
    return None


def target_entry(row: dict) -> tuple[Decimal | None, str]:
    """Paket sətri → ``(hədəf giriş balı, mənbə)``; mənbə ``total`` / ``entry`` və ya imtina səbəbi."""

    entry = _decimal(row.get("entry"))
    if entry is None:
        return None, "no_entry"
    total = _decimal(row.get("total"))
    exam = counted_exam(entry=entry, exam=_decimal(row.get("exam")), total=total, resit=_decimal(row.get("resit")))
    value, source = (total - exam, "total") if exam is not None else (entry, "entry")
    if value != value.to_integral_value() or not ZERO <= value <= ENTRY_MAX:
        return None, "out_of_range"
    return value, source


def official_finals(row: dict) -> tuple[Decimal | None, Decimal | None]:
    """Yekunu izah edən rəsmi ``(imtahan, 25 % balı)`` — yeni sistemdə boşdursa doldurmaq üçün.

    Yalnız vərəq öz-özünə uyğundursa (``counted_exam`` tapılır): 25 % balı yalnız yekunu MƏHZ o izah edirsə
    qaytarılır (``T.imtahan = 0`` / yekuna girməyən dəyər «təkrar imtahan yoxdur» deməkdir).
    """

    entry, exam, total, resit = (_decimal(row.get(key)) for key in ("entry", "exam", "total", "resit"))
    counted = counted_exam(entry=entry, exam=exam, total=total, resit=resit)
    if counted is None:
        return None, None
    used_resit = bool(resit) and counted == resit and resit != exam
    return exam, (resit if used_resit else None)


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


__all__ = [
    "ENTRY_MAX",
    "SheetRow",
    "SheetTable",
    "counted_exam",
    "number",
    "official_finals",
    "parse_export",
    "target_entry",
]
