#!/usr/bin/env python3
"""Tarixi buraxılış statusunun şəffaflıq mətnləri (4 dil).

Sahibin 2026-08-31 qərarı: köçürülmüş + bağlı semestrlərdə imtahana buraxılış
statusu yenidən hesablanmır, köhnə sistemin faktiki nəticəsi göstərilir.
İstifadəçi statusun NİYƏ hesablanmadığını görməlidir — bu mətnlər həmin izahı
verir (bax :mod:`apps.registrar.exam_eligibility`).

⚠️ ``makemessages`` İŞLƏDİLMİR (layihə qaydası): girişlər dörd kataloqa
birbaşa, idempotent şəkildə əlavə olunur.

İstifadə::

    python scripts/i18n_fill_frozen_eligibility.py [--dry-run]
    python manage.py compilemessages
"""

from __future__ import annotations

import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")
CTX = "registrar.eligibility"

# msgid = mənbə (AZ) mətn — kodda ``pgettext_lazy(CTX, "…")`` ilə eynidir.
_FROZEN_NOTICE_AZ = (
    "Bu semestr köhnə sistemdən köçürülüb və jurnalı bağlanıb. İmtahana buraxılış "
    "statusu yenidən hesablanmır — köhnə sistemin faktiki nəticəsi göstərilir."
)
_NO_RESULT_NOTICE_AZ = (
    "Köhnə sistem bu fənn üzrə imtahan nəticəsi yazmayıb. Ona görə status nə "
    "«keçib», nə «kəsilib» kimi göstərilir — məlumat mövcud deyil."
)
_UNKNOWN_HOURS_AZ = "Fənnin auditoriya saatı təyin olunmayıb — buraxılış statusu hesablana bilmir."
_UOMG_NA_NOTICE_AZ = (
    "ÜOMG hesablana bilmir: qəti nəticəsi olan (keçilmiş və ya kəsilmiş) fənn "
    "yoxdur. Köhnə sistem bu semestrlər üçün imtahan nəticəsi yazmayıb — bu, "
    "sıfır bal demək DEYİL."
)

ENTRIES: dict[tuple[str, str], dict[str, str]] = {
    (CTX, "Köhnə sistemdən"): {
        "az": "Köhnə sistemdən",
        "en": "From the legacy system",
        "ru": "Из прежней системы",
        "tr": "Eski sistemden",
    },
    (CTX, _FROZEN_NOTICE_AZ): {
        "az": _FROZEN_NOTICE_AZ,
        "en": (
            "This semester was migrated from the legacy system and its journal is closed. "
            "Exam eligibility is not recalculated — the legacy system's actual result is shown."
        ),
        "ru": (
            "Этот семестр перенесён из прежней системы, и его журнал закрыт. "
            "Допуск к экзамену не пересчитывается — показан фактический результат прежней системы."
        ),
        "tr": (
            "Bu dönem eski sistemden aktarıldı ve yoklama defteri kapatıldı. "
            "Sınava giriş durumu yeniden hesaplanmaz — eski sistemin fiili sonucu gösterilir."
        ),
    },
    (CTX, "Köhnə sistemdə nəticə yazılmayıb"): {
        "az": "Köhnə sistemdə nəticə yazılmayıb",
        "en": "No result was recorded in the legacy system",
        "ru": "В прежней системе результат не записан",
        "tr": "Eski sistemde sonuç kaydedilmemiş",
    },
    (CTX, _NO_RESULT_NOTICE_AZ): {
        "az": _NO_RESULT_NOTICE_AZ,
        "en": (
            "The legacy system recorded no exam result for this subject. The status is therefore shown "
            "as neither “passed” nor “failed” — the data does not exist."
        ),
        "ru": (
            "Прежняя система не записала результат экзамена по этому предмету. Поэтому статус не "
            "показывается ни как «сдал», ни как «не сдал» — данных нет."
        ),
        "tr": (
            "Eski sistem bu ders için sınav sonucu kaydetmemiş. Bu nedenle durum ne “geçti” ne de "
            "“kaldı” olarak gösterilir — veri mevcut değil."
        ),
    },
    (CTX, _UNKNOWN_HOURS_AZ): {
        "az": _UNKNOWN_HOURS_AZ,
        "en": "The subject's classroom hours are not set — exam eligibility cannot be calculated.",
        "ru": "Аудиторные часы предмета не заданы — допуск к экзамену рассчитать невозможно.",
        "tr": "Dersin sınıf saati tanımlanmamış — sınava giriş durumu hesaplanamıyor.",
    },
    # ── Aqreqat dürüstlüyü (ÜOMG) — 2026-08-31 düşmən baxışı, 1-ci bloker ────
    # «Hesablana bilmir» ≠ «0.00».  Rəsmi transkriptdə sıfır «tələbə sıfır bal
    # aldı» kimi oxunur; bu isə məlumatın YOXLUĞUdur.  Etiket həm Python
    # tərəfdə (``exam_eligibility.UOMG_UNAVAILABLE_LABEL``), həm də şablonlarda
    # (``_my_transcript.html``, ``_academic_records.html``) eyni msgid ilə
    # işlədilir — ona görə bir giriş hər ikisini örtür.
    (CTX, "Hesablana bilmir"): {
        "az": "Hesablana bilmir",
        "en": "Cannot be calculated",
        "ru": "Невозможно рассчитать",
        "tr": "Hesaplanamıyor",
    },
    (CTX, _UOMG_NA_NOTICE_AZ): {
        "az": _UOMG_NA_NOTICE_AZ,
        "en": (
            "The GPA cannot be calculated: there is no course with a definite result (passed or "
            "failed). The legacy system recorded no exam result for these semesters — this does "
            "NOT mean a score of zero."
        ),
        "ru": (
            "Средний балл рассчитать невозможно: нет предмета с окончательным результатом (сдан "
            "или не сдан). Прежняя система не записала результаты экзаменов за эти семестры — это "
            "НЕ означает нулевой балл."
        ),
        "tr": (
            "Ortalama hesaplanamıyor: kesin sonucu olan (geçilen veya kalınan) ders yok. Eski "
            "sistem bu dönemler için sınav sonucu kaydetmemiş — bu, sıfır puan anlamına GELMEZ."
        ),
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Tarixi buraxılış statusu mətnlərini əlavə et")
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

        if (added or updated) and not args.dry_run:
            catalog.save(path)
        print(f"  {lang}: {added} yeni, {updated} yeniləndi")

    print("\n✅ Bitdi. İndi: python manage.py compilemessages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
