#!/usr/bin/env python3
"""EMSArena i18n — «Yük bölgüsü»nün «Bütün kafedralar» rejimi (2026-11-04).

Əlavə olunan mətnlər: ``django`` domeni (`accounts.workload` — seçici variantı + izah zolağı) və ``djangojs``
(yalnız oxu kartının düyməsi / nişanı). RİM «yeni hesab» formunun kafedra seçicisi MÖVCUD mətnləri işlədir.
msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə
edir, idempotentdir. Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_chair_select_all_loads_2026_11_04.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

WORKLOAD = "accounts.workload"
#: djangojs — kontekstsiz `gettext()`.
NO_CTX = ""


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "django": {
        WORKLOAD: {
            "Bütün kafedralar": t("All departments", "Все кафедры", "Tüm bölümler", "Alle Lehrstühle"),
            "Bütün kafedralar: siyahı yalnız baxış üçündür. Sətri dəyişmək üçün «Kafedrada redaktə et» düyməsi ilə onun kafedrasına keçin.": t(
                "All departments: the list is read-only. To change a row, open its department with «Edit in department».",
                "Все кафедры: список только для просмотра. Чтобы изменить строку, перейдите на её кафедру кнопкой "
                "«Редактировать на кафедре».",
                "Tüm bölümler: liste yalnızca görüntüleme içindir. Bir satırı değiştirmek için «Bölümde düzenle» "
                "düğmesiyle kendi bölümüne geçin.",
                "Alle Lehrstühle: Die Liste ist schreibgeschützt. Um eine Zeile zu ändern, öffnen Sie mit «Im Lehrstuhl "
                "bearbeiten» ihren Lehrstuhl.",
            ),
        },
    },
    "djangojs": {
        NO_CTX: {
            "Kafedrada redaktə et": t(
                "Edit in department", "Редактировать на кафедре", "Bölümde düzenle", "Im Lehrstuhl bearbeiten"
            ),
            "Yalnız baxış": t("View only", "Только просмотр", "Yalnızca görüntüleme", "Nur Ansicht"),
        },
    },
}


def po_path(lang, domain):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain):
    path = po_path(lang, domain)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES[domain].items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else translations[lang]
            flag = "#, python-format\n" if "%(" in msgid else ""
            context = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            blocks.append(f'{flag}{context}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        for catalog in ENTRIES:
            fill(locale, catalog)
