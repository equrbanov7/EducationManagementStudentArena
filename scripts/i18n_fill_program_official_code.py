#!/usr/bin/env python3
"""EMSArena i18n — ``Program.official_code`` (rəsmi ixtisas kodu) sətirləri, 4 dil.

Registrar konsolundakı proqram formasının iki yeni etiketi və rəsmi kodun
izahlı ``help_text``-i. ``Kod`` etiketi ``Daxili kod``-a çevrildiyinə görə yeni
msgid kimi əlavə olunur (köhnə giriş kataloqda toxunulmadan qalır).

⚠️ ``makemessages`` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript
yalnız ƏLAVƏ edir və mövcud girişə TOXUNMUR. İdempotentdir.

İstifadə:  python scripts/i18n_fill_program_official_code.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

_CONSOLE = {
    "Daxili kod": {"en": "Internal code", "ru": "Внутренний код", "tr": "Dahili kod"},
    "Rəsmi ixtisas kodu": {
        "en": "Official program code",
        "ru": "Официальный код специальности",
        "tr": "Resmî program kodu",
    },
    "Rəsmi dövlət ixtisas kodu — məsələn 060209. İstifadəçilərə ixtisas adının "
    "yanında bu kod göstərilir. Eyni kod bir neçə ixtisasda təkrarlana bilər.": {
        "en": "The official state program code — for example 060209. It is shown to users next to the program "
        "name. The same code may repeat across several programs.",
        "ru": "Официальный государственный код специальности — например 060209. Он показывается пользователям "
        "рядом с названием специальности. Один и тот же код может повторяться у нескольких специальностей.",
        "tr": "Resmî devlet program kodu — örneğin 060209. Kullanıcılara program adının yanında gösterilir. "
        "Aynı kod birden çok programda tekrarlanabilir.",
    },
}

ENTRIES = {
    "registrar.console": _CONSOLE,
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
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n'
            if probe in text:
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
