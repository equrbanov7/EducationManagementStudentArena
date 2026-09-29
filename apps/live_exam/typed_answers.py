"""
Yazılı cavab (typed answer) qaydaları — canlı viktorina.

Kahoot «Type answer» / Quizizz «Fill-in-the-blank» analoqu. Bu modul SAF
funksiyalardır (DB sorğusu yalnız ``typed_eligibility``-də, prefetched
``options`` üzərindən): normallaşdırma, rəqəm ekvivalentliyi, bir-səhv
tolerantlığı (Damerau–Levenshtein ≤ 1), uyğunluq və reveal xülasəsi.

Uyğunluq qaydası (docs/live_exam/ENGINE.md «Typed answers»):

1. NFKC + Azərbaycan/Türk hərflərinin qatlanması (ə→e, ı/İ/I→i, ö→o, ü→u, ş→s,
   ç→c, ğ→g) + casefold;
2. rəqəmdirsə (``3``, ``3,0``, ``3.0``, ``-2,50``) — kanonik ədəd formasına
   çevrilir və YALNIZ ədəd bərabərliyi ilə müqayisə olunur (səhv tolerantlığı yox);
3. əks halda durğu işarələri boşluğa çevrilir, boşluqlar sıxılır;
4. dəqiq uyğunluq, yaxud qəbul olunan cavab ≥ 6 simvoldursa və tolerantlıq
   açıqdırsa — Damerau–Levenshtein məsafəsi ≤ 1.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

#: Mətn sahəsinin maksimal uzunluğu (xam, strip-dən sonra).
TEXT_MAX_LENGTH = 60
#: Bir sual üçün maksimal qəbul olunan cavab sayı.
ACCEPTED_MAX_ITEMS = 10
#: Səhv tolerantlığı yalnız bu uzunluqdan (normallaşdırılmış qəbul cavabı) başlayır.
TYPO_MIN_LENGTH = 6
#: Reveal xülasəsində göstərilən qrup sayı.
TYPED_SUMMARY_LIMIT = 8

_FOLD_MAP = str.maketrans(
    {
        "ə": "e",
        "Ə": "e",
        "ı": "i",
        "İ": "i",
        "I": "i",
        "ö": "o",
        "Ö": "o",
        "ü": "u",
        "Ü": "u",
        "ş": "s",
        "Ş": "s",
        "ç": "c",
        "Ç": "c",
        "ğ": "g",
        "Ğ": "g",
        "−": "-",  # riyazi minus → defis (rəqəm tanınması üçün)
    }
)
_NUMERIC_RE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")
_CANONICAL_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def clean_text_input(value: Any) -> str:
    """Oyunçunun/müəllimin xam mətni: str, strip, daxili boşluqlar sıxılmış."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def _canonical_number(text: str) -> str | None:
    if not _NUMERIC_RE.match(text):
        return None
    try:
        number = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    if number == 0:
        return "0"
    rendered = format(number.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def normalize_typed_text(value: Any) -> str:
    """Müqayisə forması (boş sətir → boş cavab)."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.translate(_FOLD_MAP).casefold()
    # «İ».casefold() → «i̇» (U+0307 birləşən nöqtə) — qalıqları təmizləyirik.
    text = text.replace("̇", "")
    number = _canonical_number(text.strip())
    if number is not None:
        return number
    text = "".join(" " if unicodedata.category(ch).startswith("P") else ch for ch in text)
    return " ".join(text.split())


def is_numeric_form(normalized: str) -> bool:
    return bool(_CANONICAL_NUMBER_RE.match(normalized or ""))


def within_one_edit(left: str, right: str) -> bool:
    """Damerau–Levenshtein (optimal string alignment) məsafəsi ≤ 1 — O(n)."""
    if left == right:
        return True
    len_left, len_right = len(left), len(right)
    if abs(len_left - len_right) > 1:
        return False
    if len_left == len_right:
        index = next(i for i in range(len_left) if left[i] != right[i])
        if left[index + 1 :] == right[index + 1 :]:
            return True  # əvəzetmə
        return (
            index + 1 < len_left
            and left[index] == right[index + 1]
            and left[index + 1] == right[index]
            and left[index + 2 :] == right[index + 2 :]
        )  # qonşu yerdəyişmə
    longer, shorter = (left, right) if len_left > len_right else (right, left)
    index = 0
    while index < len(shorter) and longer[index] == shorter[index]:
        index += 1
    return longer[index + 1 :] == shorter[index:]  # əlavə / silmə


def typed_answer_matches(text: Any, accepted: Iterable[str], *, typo_tolerance: bool = True) -> bool:
    candidate = normalize_typed_text(text)
    if not candidate:
        return False
    for raw_accepted in accepted or ():
        target = normalize_typed_text(raw_accepted)
        if not target:
            continue
        if candidate == target:
            return True
        if (
            typo_tolerance
            and len(target) >= TYPO_MIN_LENGTH
            and not is_numeric_form(target)
            and not is_numeric_form(candidate)
            and within_one_edit(candidate, target)
        ):
            return True
    return False


def dedupe_accepted(values: Iterable[Any]) -> list[str]:
    """Təkrarları normallaşdırılmış formaya görə atır (ilk yazılış qalır)."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in values or ():
        cleaned = clean_text_input(raw)
        key = normalize_typed_text(cleaned)
        if not cleaned or not key or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _option_text(option: Any) -> str:
    for attr in ("text", "title", "content", "answer", "option_text", "body"):
        value = getattr(option, attr, None)
        if isinstance(value, str) and value.strip():
            return clean_text_input(value)
    return ""


def typed_eligibility(exam_question: Any) -> tuple[bool, list[str]]:
    """``(typed_eligible, typed_default_accepted)``.

    * variantlı sual: tək-seçimli (``answer_mode != "multiple"``), DƏQİQ bir
      düzgün variant, mətni 1–60 simvol → default = həmin mətn;
    * variantsız sual: ``correct_answer``-də 1–10 boş olmayan sətir, hər biri
      ≤ 60 simvol → default = həmin sətirlər.
    """
    options = list(exam_question.options.all())
    if options:
        if str(getattr(exam_question, "answer_mode", "") or "").strip().lower() == "multiple":
            return False, []
        correct = [option for option in options if getattr(option, "is_correct", False)]
        if len(correct) != 1:
            return False, []
        text = _option_text(correct[0])
        if not (1 <= len(text) <= TEXT_MAX_LENGTH):
            return False, []
        return True, [text]

    raw_lines = str(getattr(exam_question, "correct_answer", "") or "").splitlines()
    lines = [clean_text_input(line) for line in raw_lines if clean_text_input(line)]
    if not (1 <= len(lines) <= ACCEPTED_MAX_ITEMS) or any(len(line) > TEXT_MAX_LENGTH for line in lines):
        return False, []
    return True, dedupe_accepted(lines)


def build_typed_summary(
    answers: Iterable[dict[str, Any]],
    *,
    limit: int = TYPED_SUMMARY_LIMIT,
    accepted: Iterable[str] | None = None,
    typo_tolerance: bool = True,
) -> list[dict[str, Any]]:
    """Reveal üçün: normallaşdırılmış formaya görə qruplar, ən çox → az (≤ ``limit``).

    * qrup açarı uyğunluqla EYNİ normallaşdırmadır → eyni formalar bir qrupdur, hər qrupun
      ``text``-i ÖZ ən çox yazılan xam formasıdır (bərabərlikdə ən erkən) — iki qrup eyni
      etiketi ala bilməz (səhv tolerantlığı ilə qəbul olunan variant ayrıca qrupdur);
    * ``correct`` — ``accepted`` verilibsə həmin qrupun UYĞUNLUQ nəticəsi (yenidən
      hesablanır), əks halda saxlanmış ``is_correct``.
    """
    accepted_list = list(accepted) if accepted is not None else None
    groups: dict[str, dict[str, Any]] = {}
    for order, answer in enumerate(answers):
        raw = clean_text_input(answer.get("text_answer"))
        key = normalize_typed_text(raw)
        if not key:
            continue
        group = groups.setdefault(key, {"spellings": Counter(), "first_seen": {}, "count": 0, "correct": False})
        group["count"] += 1
        group["spellings"][raw] += 1
        group["first_seen"].setdefault(raw, order)
        group["correct"] = group["correct"] or bool(answer.get("is_correct"))

    rows = []
    for group in groups.values():
        spellings = group["spellings"]
        display = min(spellings, key=lambda text: (-spellings[text], group["first_seen"][text]))
        correct = group["correct"]
        if accepted_list is not None:
            correct = typed_answer_matches(display, accepted_list, typo_tolerance=typo_tolerance)
        rows.append({"text": display, "count": group["count"], "correct": correct})
    rows.sort(key=lambda row: (-row["count"], not row["correct"], row["text"]))
    return rows[:limit]
