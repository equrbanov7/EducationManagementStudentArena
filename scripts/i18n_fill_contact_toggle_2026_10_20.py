#!/usr/bin/env python3
"""EMSArena i18n — «Sistem tənzimləmələri → Açıq səhifələr»: «Əlaqə» səhifəsinin açarı (2026-10-20).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

RS = "core.runtime_settings"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    RS: {
        "Açıq səhifələr": t("Public pages", "Публичные страницы", "Herkese açık sayfalar", "Öffentliche Seiten"),
        "«Əlaqə» səhifəsi (/contact/)": t(
            "“Contact” page (/contact/)",
            "Страница «Контакты» (/contact/)",
            "“İletişim” sayfası (/contact/)",
            "„Kontakt“-Seite (/contact/)",
        ),
        "Söndürüləndə /contact/ ünvanı açılmır (404), menyu, footer və «Haqqımızda» səhifəsindəki «Əlaqə» "
        "keçidləri gizlənir. Əvvəl gəlmiş mesajlar silinmir. Yandırılanda səhifə və keçidlər geri qayıdır.": t(
            "When turned off, /contact/ does not open (404) and the “Contact” links in the menu, the footer and the "
            "“About” page are hidden. Messages received earlier are not deleted. When turned on, the page and the "
            "links return.",
            "Если выключено, адрес /contact/ не открывается (404), ссылки «Контакты» в меню, футере и на странице "
            "«О нас» скрываются. Ранее полученные сообщения не удаляются. При включении страница и ссылки "
            "возвращаются.",
            "Kapatıldığında /contact/ adresi açılmaz (404); menüdeki, alt bilgideki ve “Hakkımızda” sayfasındaki "
            "“İletişim” bağlantıları gizlenir. Daha önce gelen mesajlar silinmez. Açıldığında sayfa ve bağlantılar "
            "geri gelir.",
            "Wenn ausgeschaltet, öffnet sich /contact/ nicht (404), und die „Kontakt“-Links im Menü, in der Fußzeile "
            "und auf der Seite „Über uns“ werden ausgeblendet. Zuvor eingegangene Nachrichten werden nicht gelöscht. "
            "Beim Einschalten kehren Seite und Links zurück.",
        ),
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
