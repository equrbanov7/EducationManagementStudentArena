"""Fənn seçicisində eyni görünən fənlərin ayırd edilməsi (sahib 2026-10-26).

Sahib: «Təkrar fənn varsa göstərməsin». Kataloqda eyni fənn iki dəfə ola bilər («Verilənlər bazası» və
«Verilenler bazasi», «Veb-proqramlaşdırma» və «Veb proqramlaşdırma») — müəllim seçicidə iki eyni görünən
sətir görür və təsadüfən jurnalı OLMAYAN fənni seçir → nəticə jurnala düşmür. Məlumat BİRLƏŞDİRİLMİR
(fənlərin öz jurnalları / tarixçəsi var); sadəcə ad normallaşdırıldıqda üst-üstə düşən sətirlərə ayırd edici
işarə əlavə olunur: fənn kodu + müəllimin cari dövrdə bu fənn üzrə jurnallarının qrupları, qrup yoxdursa
fənnin cari dövrdəki jurnal sayı («2 jurnal» / «jurnal yoxdur»).

Normallaşdırma: kiçik hərf; ə→e, ü→u, ö→o, ı/İ/I→i, ş→s, ç→c, ğ→g; boşluq, defis və durğu işarələri atılır
(yalnız hərf və rəqəm qalır). DB tərəfi eyni qaydanı SQL ilə təkrarlayır (``_normalized_name_sql``).
"""

from __future__ import annotations

import logging

from django.db.models import CharField, F, Func, Value
from django.db.models.functions import Lower
from django.utils.translation import pgettext

from apps.exams.services.subject_labels import subject_option

logger = logging.getLogger(__name__)

_FOLD_FROM = "ƏəÜüÖöıİIŞşÇçĞğ"
_FOLD_TO = "eeuuooiiissccgg"
_FOLD = str.maketrans(_FOLD_FROM, _FOLD_TO)
#: Ayırd edici işarədə göstərilən qrup adlarının həddi (qalanı «…»).
MAX_HINT_GROUPS = 3


def normalize_subject_name(name) -> str:
    """Fənn adının müqayisə açarı (bax modul docstring-i)."""
    folded = str(name or "").translate(_FOLD).lower()
    return "".join(ch for ch in folded if ch.isalnum())


def _normalized_name_sql():
    """``normalize_subject_name``-in PostgreSQL güzgüsü (``translate`` + ``lower`` + ``regexp_replace``)."""
    translated = Func(F("name"), Value(_FOLD_FROM), Value(_FOLD_TO), function="translate", output_field=CharField())
    return Func(
        Lower(translated),
        Value("[^[:alnum:]]"),
        Value(""),
        Value("g"),
        function="regexp_replace",
        output_field=CharField(),
    )


def _duplicate_subject_ids(page, queryset) -> set:
    """Səhifədəki fənlərdən adı normallaşdırıldıqda siyahının (``queryset``) başqa fənni ilə üst-üstə düşənlər."""
    keys = {}
    for subject in page:
        key = normalize_subject_name(subject.name)
        if key:
            keys.setdefault(key, set()).add(subject.pk)
    if not keys:
        return set()
    rows = (
        queryset.order_by()
        .annotate(ems_norm_name=_normalized_name_sql())
        .filter(ems_norm_name__in=list(keys))
        .values_list("pk", "ems_norm_name")
    )
    for pk, key in rows:
        keys.setdefault(key, set()).add(pk)
    page_ids = {subject.pk for subject in page}
    return {pk for ids in keys.values() if len(ids) > 1 for pk in ids if pk in page_ids}


def _hint_text(subject, hint) -> str:
    groups = list((hint or {}).get("teacher_groups") or [])
    if groups:
        shown = ", ".join(groups[:MAX_HINT_GROUPS])
        place = shown + ("…" if len(groups) > MAX_HINT_GROUPS else "")
    else:
        count = int((hint or {}).get("count") or 0)
        place = (
            pgettext("exams.subject_picker", "%(count)s jurnal") % {"count": count}
            if count
            else pgettext("exams.subject_picker", "jurnal yoxdur")
        )
    code = (subject.code or "").strip()
    return f"{code} · {place}" if code else place


def subject_options(page, queryset, *, organization, teacher=None) -> list:
    """Səhifənin seçici nəticələri (``subject_option``) — eyni görünən fənlərə ayırd edici işarə ilə.

    İşarəli sətir: ``text`` = «Ad (KOD · 234 K, 235 K)», ``meta`` = «KOD · 234 K, 235 K», ``hint`` = eyni.
    Best-effort: xəta seçicini sındırmır (işarəsiz siyahı qaytarılır)."""
    page = list(page)
    options = [subject_option(subject) for subject in page]
    try:
        duplicates = _duplicate_subject_ids(page, queryset)
        if not duplicates:
            return options
        from apps.registrar.public import exam_journal_link

        hints = exam_journal_link.subject_journal_hints(organization, list(duplicates), teacher=teacher)
    except Exception:  # noqa: BLE001 — işarə köməkçidir, axtarışı sındırmır
        logger.exception("subject_picker_hints: duplicate hint failed")
        return options
    for subject, option in zip(page, options):
        if subject.pk not in duplicates:
            continue
        hint = _hint_text(subject, hints.get(subject.pk))
        name = (subject.name or subject.code or "").strip()
        option.update({"text": f"{name} ({hint})", "meta": hint, "hint": hint})
    return options


__all__ = ["MAX_HINT_GROUPS", "normalize_subject_name", "subject_options"]
