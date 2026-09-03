#!/usr/bin/env python3
"""Köçürülmüş nəticənin OXUNAN qeydi (4 dil) + EN terminologiyasının vahidləşməsi.

Sahibin 2026-09-01 tələbi: köhnə sistemdən köçürülmüş bala baxan tələbə balın
dəqiq olmaya biləcəyini və dəqiqləşdirmənin İmtahan Mərkəzindən getdiyini
TOOLTIP-də yox, EKRANDA oxusun (bax
:mod:`apps.registrar.legacy_grade_read`).

Skript üç işi görür:

1. Dörd cümləni dörd kataloqa yazır:
   ``LEGACY_RESULT_CHECK_NOTICE`` (tək nəticə), ``LEGACY_SOURCE_ONLY_NOTICE``
   (kor nöqtə: sətirdə nəticə yoxdur, sübutda bal var),
   ``LEGACY_SOURCE_ONLY_STATUS`` (həmin sətrin statusu) və semestr miqyaslı
   iki qeyd.
2. EN terminologiyasını vahidləşdirir: kataloqda üstün gələn
   **«Examination Centre»** («Exam Centre» deyil) və tələbə üçün jarqonsuz
   **«the old system»** («the legacy system» deyil).  az/ru/tr-də bu problem
   yoxdur — orada onsuz da «köhnə sistem / прежняя система / eski sistem» işlənir.
3. Hər ikisini İDEMPOTENT edir: təkrar işlədilsə heç nə dəyişmir.

⚠️ ``makemessages`` İŞLƏDİLMİR (layihə qaydası): giriş dörd kataloqa birbaşa
əlavə olunur.

İstifadə::

    python scripts/i18n_fill_legacy_result_notice.py [--dry-run]
    python manage.py compilemessages
"""

from __future__ import annotations

import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")
CTX = "registrar.legacy_grade"

# msgid = mənbə (AZ) mətn — Python tərəfdəki pgettext_lazy çağırışı ilə HƏRFİ eynidir.
_NOTICE_AZ = (
    "Bu nəticə köhnə sistemdən köçürülüb və dəqiq olmaya bilər — " "dəqiqləşdirmək üçün İmtahan Mərkəzinə müraciət et."
)
_SOURCE_ONLY_AZ = (
    "Köhnə sistemdə bu fənnin balı var, amma yeni sistemə nəticə kimi keçməyib — "
    "dəqiqləşdirmək üçün İmtahan Mərkəzinə müraciət et."
)
_SOURCE_ONLY_STATUS_AZ = "Köhnə sistemdə bal var, nəticə keçməyib"
_SEMESTER_CHECK_AZ = (
    "Bu semestrin nişanlı nəticələri köhnə sistemdən köçürülüb və dəqiq olmaya bilər — "
    "dəqiqləşdirmək üçün İmtahan Mərkəzinə müraciət et."
)
_SEMESTER_MISSING_AZ = (
    "Bu semestrin bəzi fənlərində köhnə sistemin balı var, amma yeni sistemə nəticə kimi keçməyib — "
    "dəqiqləşdirmək üçün İmtahan Mərkəzinə müraciət et."
)

ENTRIES: dict[tuple[str, str], dict[str, str]] = {
    (CTX, _NOTICE_AZ): {
        "az": _NOTICE_AZ,
        "en": (
            "This result was migrated from the old system and may not be exact — "
            "contact the Examination Centre to have it confirmed."
        ),
        "ru": (
            "Этот результат перенесён из прежней системы и может быть неточным — "
            "для уточнения обратитесь в Экзаменационный центр."
        ),
        "tr": (
            "Bu sonuç eski sistemden aktarıldı ve kesin olmayabilir — " "netleştirmek için Sınav Merkezi’ne başvurun."
        ),
    },
    (CTX, _SOURCE_ONLY_AZ): {
        "az": _SOURCE_ONLY_AZ,
        "en": (
            "The old system holds a score for this course, but it did not carry over as a result — "
            "contact the Examination Centre to have it confirmed."
        ),
        "ru": (
            "В прежней системе по этому предмету есть балл, но он не перенесён как результат — "
            "для уточнения обратитесь в Экзаменационный центр."
        ),
        "tr": (
            "Eski sistemde bu ders için not var, ancak sonuç olarak aktarılmadı — "
            "netleştirmek için Sınav Merkezi’ne başvurun."
        ),
    },
    (CTX, _SOURCE_ONLY_STATUS_AZ): {
        "az": _SOURCE_ONLY_STATUS_AZ,
        "en": "Score in the old system, result not carried over",
        "ru": "Балл в прежней системе, результат не перенесён",
        "tr": "Eski sistemde not var, sonuç aktarılmadı",
    },
    (CTX, _SEMESTER_CHECK_AZ): {
        "az": _SEMESTER_CHECK_AZ,
        "en": (
            "The marked results in this semester were migrated from the old system and may not be exact — "
            "contact the Examination Centre to have them confirmed."
        ),
        "ru": (
            "Отмеченные результаты этого семестра перенесены из прежней системы и могут быть неточными — "
            "для уточнения обратитесь в Экзаменационный центр."
        ),
        "tr": (
            "Bu dönemin işaretli sonuçları eski sistemden aktarıldı ve kesin olmayabilir — "
            "netleştirmek için Sınav Merkezi’ne başvurun."
        ),
    },
    (CTX, _SEMESTER_MISSING_AZ): {
        "az": _SEMESTER_MISSING_AZ,
        "en": (
            "For some courses in this semester the old system holds a score that did not carry over as a result — "
            "contact the Examination Centre to have it confirmed."
        ),
        "ru": (
            "По некоторым предметам этого семестра в прежней системе есть балл, "
            "но он не перенесён как результат — для уточнения обратитесь в Экзаменационный центр."
        ),
        "tr": (
            "Bu dönemde bazı derslerde eski sistemin notu var, ancak sonuç olarak aktarılmadı — "
            "netleştirmek için Sınav Merkezi’ne başvurun."
        ),
    },
}

#: EN-də vahidləşmə: sol tərəf kataloqda tapılırsa sağ tərəflə əvəz olunur.
#: Yalnız ``registrar.legacy_grade`` / ``registrar.eligibility`` kontekstlərinə
#: tətbiq olunur — bunlar tələbənin köçürülmüş bal ətrafında oxuduğu ailədir.
EN_TERMINOLOGY = (
    ("Exam Centre", "Examination Centre"),
    ("the legacy system", "the old system"),
    ("The legacy system", "The old system"),
    ("Legacy system's", "The old system's"),
    ("Legacy final results table", "Old system's final results table"),
    ("Legacy exam entry/exit attempt", "Old system's exam entry/exit attempt"),
    ("Legacy exam cell", "Old system's exam cell"),
    ("Legacy resit cell", "Old system's resit cell"),
)
EN_CONTEXTS = ("registrar.legacy_grade", "registrar.eligibility")


def _unify_english(catalog) -> int:
    changed = 0
    for entry in catalog:
        if entry.obsolete or (entry.msgctxt or "") not in EN_CONTEXTS:
            continue
        text = entry.msgstr
        for old, new in EN_TERMINOLOGY:
            # «Examination Centre» artıq düzgündür — ikiqat əvəzləməni bloklayır.
            if old == "Exam Centre" and "Examination Centre" in text:
                text = text.replace("Examination Centre", "\x00")
                text = text.replace(old, new).replace("\x00", "Examination Centre")
                continue
            text = text.replace(old, new)
        if text != entry.msgstr:
            entry.msgstr = text
            changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Köçürülmüş nəticə qeydinin mətnini əlavə et")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        import polib
    except ImportError:
        print("❌ polib lazımdır: pip install polib")
        return 1

    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        catalog = polib.pofile(path)
        index = {(e.msgctxt or "", e.msgid): e for e in catalog if not e.obsolete}

        added = updated = 0
        for key, texts in ENTRIES.items():
            entry = index.get(key)
            if entry is None:
                catalog.append(polib.POEntry(msgctxt=key[0], msgid=key[1], msgstr=texts[lang]))
                added += 1
            elif entry.msgstr != texts[lang]:
                entry.msgstr = texts[lang]
                updated += 1

        unified = _unify_english(catalog) if lang == "en" else 0

        if (added or updated or unified) and not args.dry_run:
            catalog.save(path)
        print(f"  {lang}: {added} yeni, {updated} yeniləndi, {unified} terminologiya")

    print("\n✅ Bitdi. İndi: python manage.py compilemessages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
