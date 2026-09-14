#!/usr/bin/env python3
"""EMSArena i18n — «Transkript yüklə» əməli + rəsmi PDF rekvizitləri (4 dil).

2026-09-10 sahib tələbi: «birdə tələbənin olan yerdə transkript yeri olsun.
transkript yüklə deyə vuranda rəsmi sənəd kimi transkript yükləsin.»

Yeni mətnlər:
* `accounts.student_registry` / `registrar.catalog` — sətir və çekmecə əməli;
* `registrar.pdf` — rəsmi sənəd rekvizitləri (sənəd nömrəsi, möhür yeri,
  imza altyazısı, «Səhifə N / M» altlığı).

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
ƏLAVƏ edir və idempotentdir.

İstifadə:  python scripts/i18n_fill_transcript_download_2026_09_10.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

_DOWNLOAD_HINT = {
    "en": "Download the official academic transcript as PDF",
    "ru": "Скачать официальную академическую справку (транскрипт) в PDF",
    "tr": "Resmî akademik transkripti PDF olarak indir",
}
# Düymənin adı sahibin öz sözüdür: «transkript yüklə». Tək «Transkript» sözü
# QƏSDƏN işlənmir — onun türkcə qarşılığı azərbaycancası ilə eynidir və i18n
# qapısı belə sətri «tərcümə olunmamış» sayır.
_DOWNLOAD = {
    "en": "Download transcript",
    "ru": "Скачать транскрипт",
    "tr": "Transkripti indir",
}

ENTRIES = {
    "accounts.student_registry": {
        "Transkript yüklə": _DOWNLOAD,
        "Rəsmi akademik transkripti PDF olaraq yüklə": _DOWNLOAD_HINT,
    },
    "registrar.catalog": {
        "Transkript yüklə": _DOWNLOAD,
        "Rəsmi akademik transkripti PDF olaraq yüklə": _DOWNLOAD_HINT,
    },
    "registrar.pdf": {
        "Sənəd №": {"en": "Document No.", "ru": "Документ №", "tr": "Belge No."},
        "Möhür yeri": {"en": "Seal", "ru": "Место печати", "tr": "Mühür yeri"},
        "(imza, soyad və ad)": {
            "en": "(signature, surname and name)",
            "ru": "(подпись, фамилия и имя)",
            "tr": "(imza, soyadı ve adı)",
        },
        "Səhifə %(page)s / %(total)s": {
            "en": "Page %(page)s / %(total)s",
            "ru": "Страница %(page)s / %(total)s",
            "tr": "Sayfa %(page)s / %(total)s",
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n' in text:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
