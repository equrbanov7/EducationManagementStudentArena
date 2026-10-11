#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-11: «Kurs işi» RİM «Sistem tənzimləmələri»ndə açar (sahib: hələlik söndür).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_11_coursework.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


ENTRIES = {
    "core.runtime_settings": {
        "Kurs işi (jurnalda)": _t(
            "Kurs işi (jurnalda)",
            "Coursework (in the journal)",
            "Курсовая работа (в журнале)",
            "Dönem ödevi (defterde)",
        ),
        "Söndürülüdə jurnalda «Kurs işi» tabı, addımı və düzəlişi görünmür, tələbə öz jurnalında da görmür. "
        "Kurs işi balı imtahana qədər bala daxil deyil — hesablamalar dəyişmir. Yalnız 2026/2027 və sonrakı "
        "semestrlərə aiddir; köhnə semestrlərdə və mövcud datada heç nə silinmir.": _t(
            "Söndürülüdə jurnalda «Kurs işi» tabı, addımı və düzəlişi görünmür, tələbə öz jurnalında da görmür. "
            "Kurs işi balı imtahana qədər bala daxil deyil — hesablamalar dəyişmir. Yalnız 2026/2027 və sonrakı "
            "semestrlərə aiddir; köhnə semestrlərdə və mövcud datada heç nə silinmir.",
            "When off, the journal shows no «Coursework» tab, step or correction, and students do not see it in "
            "their own journal. Coursework is not part of the pre-exam score, so no calculation changes. Applies "
            "only to 2026/2027 and later semesters; nothing is deleted in earlier semesters or existing data.",
            "В выключенном состоянии в журнале нет вкладки, шага и исправлений «Курсовая работа», студент тоже "
            "не видит её в своём журнале. Курсовая работа не входит в балл до экзамена — расчёты не меняются. "
            "Действует только для семестров 2026/2027 и позже; в прошлых семестрах и данных ничего не удаляется.",
            "Kapalıyken ders defterinde «Dönem ödevi» sekmesi, adımı ve düzeltmesi görünmez; öğrenci de kendi "
            "defterinde görmez. Dönem ödevi sınav öncesi puana dahil değildir — hesaplamalar değişmez. Yalnızca "
            "2026/2027 ve sonraki dönemlere uygulanır; önceki dönemlerde ve mevcut verilerde hiçbir şey silinmez.",
        ),
    },
    "registrar.correction": {
        "Bu semestrdə kurs işi tətbiq olunmur — düzəliş mümkün deyil.": _t(
            "Bu semestrdə kurs işi tətbiq olunmur — düzəliş mümkün deyil.",
            "Coursework is not used this semester — it cannot be corrected.",
            "В этом семестре курсовая работа не применяется — исправление невозможно.",
            "Bu dönemde dönem ödevi uygulanmıyor — düzeltme yapılamaz.",
        ),
    },
}


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
                added += 1
            elif not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
