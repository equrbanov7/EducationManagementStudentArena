#!/usr/bin/env python3
"""EMSArena i18n — «Yük bölgüsü»: müəllim seçicisi + vəziyyət/fəaliyyət süzgəcləri + «Filtrləri sıfırla», 2026-10-25.

msgid AZ cümlədir → az msgstr = msgid. ``django`` domeni kontekstlə, ``djangojs`` — kontekstsiz (JS kataloqu).
Mövcud açarlar atlanır (idempotent); sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

W = "accounts.workload"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ALL = t("All", "Все", "Tümü", "Alle")

ENTRIES = {
    W: {
        "Hamısı": ALL,
        "Müəllim": t("Teacher", "Преподаватель", "Öğretmen", "Lehrkraft"),
        "Müəllim axtar…": t("Search teacher…", "Поиск преподавателя…", "Öğretmen ara…", "Lehrkraft suchen…"),
        "Uyğun müəllim tapılmadı": t(
            "No matching teacher",
            "Подходящий преподаватель не найден",
            "Uygun öğretmen bulunamadı",
            "Keine passende Lehrkraft",
        ),
        "Vəziyyət": t("Status", "Состояние", "Durum", "Status"),
        "Vakantı olan": t("With vacant hours", "С вакантными часами", "Boş saati olan", "Mit vakanten Stunden"),
        "Tam bölünmüş": t("Fully distributed", "Полностью распределено", "Tam dağıtılmış", "Vollständig verteilt"),
        "Qismən bölünmüş": t("Partly distributed", "Частично распределено", "Kısmen dağıtılmış", "Teilweise verteilt"),
        "Heç bölünməmiş": t(
            "Not distributed at all", "Совсем не распределено", "Hiç dağıtılmamış", "Gar nicht verteilt"
        ),
        "Saathesabı": t("Hourly-paid", "Почасовая оплата", "Saat hesabı", "Stundenbasiert"),
        "İntensiv": t("Intensive", "Интенсив", "Yoğun", "Intensiv"),
        "Fəaliyyət": t("Activity", "Вид занятий", "Etkinlik", "Aktivität"),
        "Filtrləri sıfırla": t("Reset filters", "Сбросить фильтры", "Filtreleri sıfırla", "Filter zurücksetzen"),
        "Süzgəcləri dəyişin və ya «Filtrləri sıfırla» düyməsinə basın.": t(
            "Change the filters or press “Reset filters”.",
            "Измените фильтры или нажмите «Сбросить фильтры».",
            "Filtreleri değiştirin veya «Filtreleri sıfırla» düğmesine basın.",
            "Ändern Sie die Filter oder klicken Sie auf „Filter zurücksetzen“.",
        ),
    },
}

JS_ENTRIES = {
    "Hamısı": ALL,
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _write(path, blocks):
    if not blocks:
        return
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text.rstrip("\n") + "\n\n" + "\n".join(blocks))


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    blocks = []
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
    _write(path, blocks)

    js_path = po_path(lang, "djangojs")
    js_existing = {entry.msgid for entry in polib.pofile(js_path) if not entry.obsolete and not entry.msgctxt}
    js_blocks = []
    for msgid, translations in JS_ENTRIES.items():
        if msgid in js_existing:
            continue
        msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
        js_blocks.append(f'msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
    _write(js_path, js_blocks)
    print(f"{lang}: +{len(blocks)} django, +{len(js_blocks)} djangojs")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
