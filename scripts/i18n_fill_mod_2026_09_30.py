#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-30 ad moderasiyası (nalayiq söz filtri, WP «MOD»).

Əlavə olunan mətnlər:
  * `moderation.profanity` — nalayiq ad rədd mesajı və təkrar cəhd (rate-limit)
    mesajı (canlı imtahan ləqəbi, profil ad/soyad, RİM redaktə/yaratma, qeydiyyat);
  * `audit.section` — audit jurnalında «Nalayiq ad cəhdləri» filtri və resurs
    tipinin oxunaqlı adı.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_mod_2026_09_30.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

MOD = "moderation.profanity"
AUD = "audit.section"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    MOD: {
        "Bu ad qəbul edilmir: tərkibində nalayiq ifadə var. Zəhmət olmasa başqa ad yazın.": {
            "az": "Bu ad qəbul edilmir: tərkibində nalayiq ifadə var. Zəhmət olmasa başqa ad yazın.",
            "en": "This name can't be used because it contains inappropriate language. Please choose another name.",
            "ru": "Это имя нельзя использовать: оно содержит недопустимые выражения. Пожалуйста, выберите другое.",
            "tr": "Bu ad kullanılamaz: uygunsuz bir ifade içeriyor. Lütfen başka bir ad yazın.",
        },
        "Çox sayda nalayiq ad cəhdi edildi. Bir neçə dəqiqədən sonra yenidən cəhd edin.": {
            "az": "Çox sayda nalayiq ad cəhdi edildi. Bir neçə dəqiqədən sonra yenidən cəhd edin.",
            "en": "Too many attempts with inappropriate names. Please try again in a few minutes.",
            "ru": "Слишком много попыток с недопустимыми именами. Повторите попытку через несколько минут.",
            "tr": "Çok fazla uygunsuz ad denemesi yapıldı. Birkaç dakika sonra tekrar deneyin.",
        },
    },
    AUD: {
        "Nalayiq ad cəhdləri": {
            "az": "Nalayiq ad cəhdləri",
            "en": "Inappropriate name attempts",
            "ru": "Попытки недопустимых имён",
            "tr": "Uygunsuz ad denemeleri",
        },
        "Moderasiya › nalayiq ad": {
            "az": "Moderasiya › nalayiq ad",
            "en": "Moderation › inappropriate name",
            "ru": "Модерация › недопустимое имя",
            "tr": "Moderasyon › uygunsuz ad",
        },
    },
}

# Mövcud olan, amma yanlış tərcümələr — həmişə üstələnir (bu dəst üçün boşdur).
FORCE: set = set()


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def fill(lang):
    path = po_path(lang)
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
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if ((ctx, msgid) in FORCE or stale) and entry.msgstr != want:
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
