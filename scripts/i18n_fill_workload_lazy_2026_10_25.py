#!/usr/bin/env python3
"""EMSArena i18n — «Yük bölgüsü»: müəllimə görə süzgəc + tənbəl yükləmə, 2026-10-25.

msgid AZ cümlədir → az msgstr = msgid. ``django`` domeni kontekstlə, ``djangojs`` — kontekstsiz (JS kataloqu).
İdempotentdir; sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

W = "accounts.workload"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


CLEAR = t(
    "Remove the teacher filter",
    "Снять фильтр по преподавателю",
    "Öğretmen filtresini kaldır",
    "Lehrkraft-Filter entfernen",
)

ENTRIES = {
    W: {
        "Müəllim süzgəci:": t("Teacher filter:", "Фильтр по преподавателю:", "Öğretmen filtresi:", "Lehrkraft-Filter:"),
        "Müəllim süzgəcini götür": CLEAR,
        "Süzgəcə uyğun sətir tapılmadı": t(
            "No rows match the filter",
            "Строк, соответствующих фильтру, нет",
            "Filtreye uyan satır bulunamadı",
            "Keine Zeilen entsprechen dem Filter",
        ),
        "Müəllim süzgəcini götürün, axtarışı təmizləyin və ya semestri «Hamısı» seçin.": t(
            "Remove the teacher filter, clear the search or set the semester to “All”.",
            "Снимите фильтр по преподавателю, очистите поиск или выберите семестр «Все».",
            "Öğretmen filtresini kaldırın, aramayı temizleyin veya dönemi «Tümü» seçin.",
            "Entfernen Sie den Lehrkraft-Filter, leeren Sie die Suche oder wählen Sie das Semester „Alle“.",
        ),
        "Daha çox göstər": t("Show more", "Показать ещё", "Daha fazla göster", "Mehr anzeigen"),
        "Növbəti sətirlər yüklənmədi — yenidən cəhd edin.": t(
            "The next rows could not be loaded — try again.",
            "Не удалось загрузить следующие строки — повторите попытку.",
            "Sonraki satırlar yüklenemedi — yeniden deneyin.",
            "Die nächsten Zeilen konnten nicht geladen werden — bitte erneut versuchen.",
        ),
        "Müəllimin üstünə vurun — solda yalnız ona bölgüsü olan sətirlər qalsın. Təkrar vurun və ya × ilə süzgəci götürün.": t(
            "Click a teacher to keep only the rows assigned to them on the left. Click again or use × to remove the filter.",
            "Нажмите на преподавателя — слева останутся только строки с его нагрузкой. Нажмите ещё раз или × — фильтр снимется.",
            "Bir öğretmene tıklayın — solda yalnızca ona dağıtılan satırlar kalsın. Tekrar tıklayın veya × ile filtreyi kaldırın.",
            "Klicken Sie auf eine Lehrkraft — links bleiben nur die ihr zugeteilten Zeilen. Erneut klicken oder × entfernt den Filter.",
        ),
    },
}

JS_ENTRIES = {
    "Göstərilir: %(shown)s / %(total)s sətir": t(
        "Showing %(shown)s of %(total)s rows",
        "Показано %(shown)s из %(total)s строк",
        "%(total)s satırdan %(shown)s tanesi gösteriliyor",
        "%(shown)s von %(total)s Zeilen angezeigt",
    ),
    "Seçilmiş müəllim": t("Selected teacher", "Выбранный преподаватель", "Seçilen öğretmen", "Ausgewählte Lehrkraft"),
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
