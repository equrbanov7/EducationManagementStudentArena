#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-17: imtahan balı + «Apellyasiya balı» xanası, midterm tək sütun, istəyə bağlı sahələr.

Sahib: «balın yanında appel xanası da olsun, 2 xana; appelyasiya xanasından gələn bal əsas götürülür»,
«Midterm 1 sütun 30 ballıq», «İmtahan tarixi, Nəzarətçi optional», «1 saat balları redaktə etmək müddəti».
``django`` kataloquna beş dildə; AZ msgstr = msgid. «Edit within 15 minutes» növ etiketinin TƏRCÜMƏLƏRİ müddətdən
asılı olmayan mətnə çevrilir (msgid dəyişmir — model seçimi miqrasiyasız qalır). İdempotent.
İstifadə:  python scripts/i18n_add_exam_appeal_cell_2026_11_17.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_E = "registrar.exam_score_entry"
_K = "registrar.exam_score_entry_kind"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (_E, "Apellyasiya balı"): ("Appeal score", "Балл апелляции", "İtiraz puanı", "Einspruchspunktzahl"),
    (_E, "Midterm tək sütundur — bir bal, maksimum 30."): (
        "The midterm has a single column — one score, maximum 30.",
        "Мидтерм — одна колонка: один балл, максимум 30.",
        "Ara sınav tek sütundur — tek puan, en fazla 30.",
        "Die Zwischenprüfung hat eine Spalte — eine Punktzahl, maximal 30.",
    ),
    (_E, "Midterm tək sütundur — hər tələbəyə bir bal, maksimum %(cap)s."): (
        "The midterm has a single column — one score per student, maximum %(cap)s.",
        "Мидтерм — одна колонка: один балл на студента, максимум %(cap)s.",
        "Ara sınav tek sütundur — her öğrenciye tek puan, en fazla %(cap)s.",
        "Die Zwischenprüfung hat eine Spalte — eine Punktzahl je Studierenden, maximal %(cap)s.",
    ),
    (
        _E,
        "Bu tələbənin apellyasiya balı var — əsas bal apellyasiya balıdır. Dəyişikliyi «Apellyasiya balı» xanasında edin.",
    ): (
        "This student has an appeal score — the appeal score is the score of record. Make the change in the “Appeal score” cell.",
        "У этого студента есть балл апелляции — основным считается он. Вносите изменение в ячейку «Балл апелляции».",
        "Bu öğrencinin itiraz puanı var — esas puan itiraz puanıdır. Değişikliği «İtiraz puanı» hücresinde yapın.",
        "Für diese/n Studierende/n gibt es eine Einspruchspunktzahl — sie ist maßgeblich. Ändern Sie sie in der Zelle „Einspruchspunktzahl“.",
    ),
    (_E, "Apellyasiya balı yalnız imtahan balı yazılmış tələbəyə yazılır."): (
        "An appeal score can only be entered for a student who already has an exam score.",
        "Балл апелляции вносится только студенту, у которого уже есть балл за экзамен.",
        "İtiraz puanı yalnızca sınav puanı girilmiş öğrenciye yazılır.",
        "Eine Einspruchspunktzahl kann nur bei vorhandener Prüfungspunktzahl eingetragen werden.",
    ),
    (_E, "Apellyasiya balını yalnız İmtahan Mərkəzinin / RİM rəhbəri, imtahan balı yazılmış tələbəyə yazır."): (
        "Only the head of the Exam Center / Registrar enters an appeal score, and only for a student who has an exam score.",
        "Балл апелляции вносит только руководитель Экзаменационного центра / РИМ и только студенту с баллом за экзамен.",
        "İtiraz puanını yalnızca Sınav Merkezi / RİM yöneticisi, sınav puanı girilmiş öğrenciye yazar.",
        "Nur die Leitung des Prüfungszentrums / RİM trägt eine Einspruchspunktzahl ein, und nur bei vorhandener Prüfungspunktzahl.",
    ),
    (_E, "Apellyasiya nəticəsini «Apellyasiya balı» xanasına yazın — yekun bal odur."): (
        "Enter the appeal result in the “Appeal score” cell — it becomes the score of record.",
        "Запишите результат апелляции в ячейку «Балл апелляции» — он станет итоговым.",
        "İtiraz sonucunu «İtiraz puanı» hücresine yazın — esas puan odur.",
        "Tragen Sie das Einspruchsergebnis in die Zelle „Einspruchspunktzahl“ ein — es ist maßgeblich.",
    ),
    (_E, "apellyasiya balı yazılacaq (yekun bal odur)"): (
        "appeal score(s) will be written (they become the score of record)",
        "балл(ов) апелляции будет записано (они станут итоговыми)",
        "itiraz puanı yazılacak (esas puan odur)",
        "Einspruchspunktzahl(en) werden eingetragen (sie sind maßgeblich)",
    ),
    (_E, "Apellyasiya balı 0 ilə maksimum arasında tam ədəd olmalıdır."): (
        "The appeal score must be a whole number between 0 and the maximum.",
        "Балл апелляции должен быть целым числом от 0 до максимума.",
        "İtiraz puanı 0 ile en yüksek değer arasında tam sayı olmalıdır.",
        "Die Einspruchspunktzahl muss eine ganze Zahl zwischen 0 und dem Maximum sein.",
    ),
    (_E, "istəyə bağlı"): ("optional", "необязательно", "isteğe bağlı", "optional"),
}

#: Mövcud girişin TƏRCÜMƏSİ dəyişir (msgid sabit): (kontekst, msgid) → {dil: msgstr}
RETRANSLATE = {
    (_K, "Edit within 15 minutes"): {
        "az": "Redaktə müddətində düzəliş",
        "en": "Edit within the edit window",
        "ru": "Исправление в пределах срока",
        "tr": "Düzeltme süresi içinde düzeltme",
        "de": "Korrektur innerhalb der Frist",
    },
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt or "", e.msgid): e for e in po}
        added = changed = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            entry = polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=msgstr)
            if "%(" in msgid:
                entry.flags.append("python-format")
            po.append(entry)
            added += 1
        for key, by_lang in RETRANSLATE.items():
            entry = existing.get(key)
            if entry is not None and entry.msgstr != by_lang[lang]:
                entry.msgstr = by_lang[lang]
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                changed += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"django/{lang}: +{added} ~{changed}")


if __name__ == "__main__":
    main()
