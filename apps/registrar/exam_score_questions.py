"""Kağız imtahanın SUAL-SUAL balları — validasiya və cəm (W2 `w2paper`, 2026-09-14).

Sahibin tələbi (2026-09-14, sözbəsöz): «Kağızda verilən imtahanlarda tələbənin
aldığı qiyməti sistemə köçürmək mümkün olsun … İmtahandan max bal 50, hər
sualdan max 10, yekun bal 100-dən çox ola bilməz — hamısına nəzarət et.»

Bu modul ``exam_score_entry`` servisinin QARDAŞIDIR (modul-ölçü büdcəsi,
SOFT_CAP=600) və YALNIZ təmiz funksiyalar verir — DB-yə toxunmur, yazmır:

* :func:`clean_question_grid` — vərəqin sual şəbəkəsi (sual sayı 0..10, bir
  sualın tavanı ≥ 1);
* :func:`clean_question_scores` — bir tələbənin sual balları: hər biri TAM ədəd
  ``0..question_max``, sayı ``≤ question_count``, cəmi ``≤ cap``. **``cap``
  sxemdən gəlir** (``finals.exam_score_max`` = 100 − giriş tavanı) — 50 burada
  sabit yazılmır;
* :func:`assert_total_within_hundred` — giriş + imtahan ≤ 100 (tavanlar onsuz
  da bunu nəzərdə tutur; sahibin sözü ilə AÇIQ yoxlanır).

Hamısı fail-closed: ilk pozuntu ``ValidationError`` ilə dayandırır; mesajlar
dəqiqdir (hansı sual, hansı hədd). Yazı yolu yalnız
``exam_score_entry.record_exam_score``-dur — o, buradakı funksiyaları çağırır.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

from .models.exam_score_entry import (
    QUESTION_COUNT_DEFAULT,
    QUESTION_COUNT_MAX,
    QUESTION_MAX_DEFAULT,
)

_CTX = "registrar.exam_score_entry"
#: Sahibin qaydası (2026-09-14): bir sualın maksimumu 10-dan yuxarı qaldırıla bilməz.
QUESTION_MAX_CEILING = 10

#: Formada / idxalda sual sütunlarının etiketi («S1», «S2», …).
QUESTION_LABEL_PREFIX = "S"


def question_labels(question_count: int) -> list:
    """``["S1", …, "Sn"]`` — cədvəl başlıqları və idxal sütunları üçün."""
    return [f"{QUESTION_LABEL_PREFIX}{index}" for index in range(1, int(question_count or 0) + 1)]


def question_defaults() -> dict:
    """Yeni vərəq üçün ilkin sual şəbəkəsi (sonuncu vərəq yoxdursa)."""
    return {"question_count": QUESTION_COUNT_DEFAULT, "question_max": QUESTION_MAX_DEFAULT}


def _int_or_none(raw):
    """Boş → ``None``; əks halda TAM ədəd (``"7"``, ``7``, ``7.0`` qəbul; ``7.5`` rədd)."""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", ".")
    if not text:
        return None
    try:
        value = Decimal(text)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(pgettext(_CTX, "Bal rəqəm olmalıdır."))
    if not value.is_finite() or value != value.to_integral_value():
        raise ValidationError(pgettext(_CTX, "Bal tam ədəd olmalıdır."))
    return int(value)


def clean_question_grid(count_raw, max_raw) -> tuple:
    """Vərəqin sual şəbəkəsi: ``(question_count, question_max)``.

    Boş dəyər defolta düşür (5 sual · 10 bal). Sual sayı ``0`` = tək yekun bal
    rejimi (köhnə vərəqlər, yalnız «Bal» sütunlu idxal); ``> 10`` rədd olunur.
    """
    count = _int_or_none(count_raw)
    if count is None:
        count = QUESTION_COUNT_DEFAULT
    if count < 0 or count > QUESTION_COUNT_MAX:
        raise ValidationError(
            pgettext(_CTX, "Sual sayı 0 ilə %(max)s arasında olmalıdır.") % {"max": QUESTION_COUNT_MAX}
        )
    question_max = _int_or_none(max_raw)
    if question_max is None:
        question_max = QUESTION_MAX_DEFAULT
    # Sahibin qaydası (2026-09-14): «hər sualdan max bal 10» — tavan 10-dan yuxarı
    # qaldırıla bilməz (aşağı ola bilər: məs. 5 sual × 10 = 50, 10 sual × 5 = 50).
    if question_max < 1 or question_max > QUESTION_MAX_CEILING:
        raise ValidationError(
            pgettext(_CTX, "Bir sualın maksimum balı 1 ilə %(max)s arasında olmalıdır.") % {"max": QUESTION_MAX_CEILING}
        )
    return count, question_max


def is_blank_list(raw_scores) -> bool:
    """Bütün sual sahələri boşdursa sətir TOXUNULMUR (kütləvi silinmə riski yoxdur)."""
    if raw_scores is None:
        return True
    return all(str(value if value is not None else "").strip() == "" for value in raw_scores)


def clean_question_scores(raw_scores, *, question_count: int, question_max: int, cap) -> tuple:
    """Bir tələbənin sual balları → ``(scores, total)``; hamısı boşdursa ``(None, None)``.

    Qaydalar (sahib 2026-09-14, hamısı fail-closed):

    * sayı ``question_count``-dan çox ola bilməz (vərəqdə olmayan sual);
    * hər bal TAM ədəd, ``0..question_max`` («hər sualdan max 10»);
    * qismən doldurulmuş sətirdə boş sual ``0`` sayılır (cavabsız sual);
    * cəm ``cap``-ı aşa bilməz («imtahandan max bal 50» — ``cap`` sxemdəndir).

    ``question_count == 0`` olan vərəqdə sual balı QƏBUL OLUNMUR — tək yekun bal
    rejimidir (çağıran ``exam_score_entry._clean_score`` ilə gedir).
    """
    if is_blank_list(raw_scores):
        return None, None
    raw_scores = list(raw_scores)
    question_count = int(question_count or 0)
    if question_count <= 0:
        raise ValidationError(pgettext(_CTX, "Bu vərəq tək yekun bal rejimindədir — sual balı qəbul olunmur."))
    if len(raw_scores) > question_count:
        raise ValidationError(
            pgettext(_CTX, "Sual sayı vərəqin sual sayından (%(count)s) çox ola bilməz.") % {"count": question_count}
        )
    scores = []
    for index, raw in enumerate(raw_scores, start=1):
        try:
            value = _int_or_none(raw)
        except ValidationError:
            raise ValidationError(
                pgettext(_CTX, "%(label)s balı tam ədəd olmalıdır.") % {"label": f"{QUESTION_LABEL_PREFIX}{index}"}
            ) from None
        if value is None:
            value = 0
        if value < 0 or value > int(question_max):
            raise ValidationError(
                pgettext(_CTX, "%(label)s balı 0 ilə %(max)s arasında olmalıdır.")
                % {"label": f"{QUESTION_LABEL_PREFIX}{index}", "max": int(question_max)}
            )
        scores.append(value)
    total = sum(scores)
    if total > int(cap):
        raise ValidationError(
            pgettext(_CTX, "Sualların cəmi (%(total)s) imtahan balının tavanını (%(max)s) aşır.")
            % {"total": total, "max": int(cap)}
        )
    return scores, Decimal(total)


def assert_total_within_hundred(entry_score, exam_score) -> None:
    """Giriş + imtahan ≤ 100 — sahibin sözü ilə AÇIQ yoxlama (tavanlar onsuz da örtür)."""
    if entry_score is None or exam_score is None:
        return
    total = Decimal(entry_score) + Decimal(exam_score)
    if total > Decimal(100):
        raise ValidationError(
            pgettext(_CTX, "Giriş balı (%(entry)s) + imtahan balı (%(exam)s) 100-dən çox ola bilməz.")
            % {"entry": Decimal(entry_score).quantize(Decimal(1)), "exam": Decimal(exam_score).quantize(Decimal(1))}
        )


def same_question_scores(old, new) -> bool:
    """İki sual siyahısı eynidirmi (``None`` ↔ ``None`` eyni; ``None`` ↔ siyahı fərqli)."""
    if old is None or new is None:
        return old is None and new is None
    return [int(v) for v in old] == [int(v) for v in new]


__all__ = [
    "QUESTION_COUNT_DEFAULT",
    "QUESTION_COUNT_MAX",
    "QUESTION_LABEL_PREFIX",
    "QUESTION_MAX_DEFAULT",
    "assert_total_within_hundred",
    "clean_question_grid",
    "clean_question_scores",
    "is_blank_list",
    "question_defaults",
    "question_labels",
    "same_question_scores",
]
