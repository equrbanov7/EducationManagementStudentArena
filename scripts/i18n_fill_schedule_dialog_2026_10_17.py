#!/usr/bin/env python3
"""EMSArena i18n — «Xanaya dərs qoy» dialoqunda «Korpus → Otaq» seçiciləri 2026-10-17.

Sahib: «Xanaya dərs qoy yeri dizaynı pozulmuş kimi görünür, select optionlar — onlara bax. Bir də korpusa
uyğun otaqları düz seç.» Otaq sahəsi native datalist-li mətn sahəsi idi; indi stilli «Korpus» + «Otaq»
seçiciləridir (otaqlar seçilmiş korpusa görə süzülür). Əlavə olunan mətnlər:
  * ``django`` / `accounts.schedule_manage` — dialoq sahələri + ipucları (`schedule/_cell_fields.html`) və
    planlayıcının «Seçilmiş korpus» qeydi (`schedule/_planner.html`, `{campus}` JS-də əvəz olunur);
  * ``django`` / `registrar.schedule_rooms` — otaq mətni «33 · 40 nəfər» (`apps/registrar/schedule_rooms.py`).
  * ``djangojs`` — yoxdur (JS mətnləri şablondan gəlir).

msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları
əlavə edir, idempotentdir (mövcudluq `polib` ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_schedule_dialog_2026_10_17.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

MANAGE = "accounts.schedule_manage"
ROOMS = "registrar.schedule_rooms"


def tr(en, ru, tr_, de):
    return {"en": en, "ru": ru, "tr": tr_, "de": de}


# domen → ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    "django": {
        MANAGE: {
            "Korpus": tr("Building", "Корпус", "Bina", "Gebäude"),
            "Bütün korpuslar": tr("All buildings", "Все корпуса", "Tüm binalar", "Alle Gebäude"),
            "Otaq axtar…": tr("Search rooms…", "Поиск аудитории…", "Derslik ara…", "Raum suchen…"),
            "Bu korpusda uyğun otaq yoxdur": tr(
                "No matching room in this building",
                "В этом корпусе нет подходящей аудитории",
                "Bu binada uygun derslik yok",
                "Kein passender Raum in diesem Gebäude",
            ),
            "Otaq seçilməyib": tr("No room selected", "Аудитория не выбрана", "Derslik seçilmedi", "Kein Raum gewählt"),
            "Korpus qrupun ixtisasına görə seçilib — dəyişə bilərsiniz; otaqlar korpusa görə süzülür.": tr(
                "The building is preset from the group's programme — you can change it; rooms are filtered by building.",
                "Корпус выбран по специальности группы — его можно изменить; аудитории фильтруются по корпусу.",
                "Bina grubun programına göre seçildi — değiştirebilirsiniz; derslikler binaya göre süzülür.",
                "Das Gebäude ist nach dem Studiengang der Gruppe vorbelegt — Sie können es ändern; "
                "Räume werden nach Gebäude gefiltert.",
            ),
            "Əvvəlcə korpusu seçin — otaq siyahısı həmin korpusun otaqlarıdır.": tr(
                "Pick the building first — the room list shows that building's rooms.",
                "Сначала выберите корпус — в списке будут аудитории этого корпуса.",
                "Önce binayı seçin — derslik listesi o binanın derslikleridir.",
                "Wählen Sie zuerst das Gebäude — die Raumliste zeigt dessen Räume.",
            ),
            "Bu otaq otaq reyestrində yoxdur — saxlanılır; dəyişmək üçün siyahıdan seçin.": tr(
                "This room is not in the room registry — it is kept; pick one from the list to change it.",
                "Этой аудитории нет в реестре — она сохраняется; чтобы изменить, выберите из списка.",
                "Bu derslik derslik kaydında yok — korunur; değiştirmek için listeden seçin.",
                "Dieser Raum ist nicht im Raumverzeichnis — er bleibt erhalten; zum Ändern aus der Liste wählen.",
            ),
            "Otaq reyestri boşdur — otaqlar «İmtahan otaqları» bölməsində əlavə olunur.": tr(
                "The room registry is empty — rooms are added in the “Exam rooms” section.",
                "Реестр аудиторий пуст — аудитории добавляются в разделе «Экзаменационные аудитории».",
                "Derslik kaydı boş — derslikler «Sınav salonları» bölümünde eklenir.",
                "Das Raumverzeichnis ist leer — Räume werden im Bereich „Prüfungsräume“ angelegt.",
            ),
            "Seçilmiş korpus: {campus} — otaqlar əvvəlcə bu korpusdan": tr(
                "Selected building: {campus} — its rooms come first",
                "Выбранный корпус: {campus} — сначала его аудитории",
                "Seçilen bina: {campus} — önce bu binanın derslikleri",
                "Gewähltes Gebäude: {campus} — seine Räume zuerst",
            ),
        },
        ROOMS: {
            "%(room)s · %(count)s nəfər": tr(
                "%(room)s · %(count)s seats",
                "%(room)s · %(count)s мест",
                "%(room)s · %(count)s kişilik",
                "%(room)s · %(count)s Plätze",
            ),
        },
    },
    "djangojs": {},
}


def po_path(lang, domain):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _flags(msgid):
    return "#, python-format\n" if "%(" in msgid else ""


def fill(lang, domain):
    if not ENTRIES.get(domain):
        print(f"{lang}/{domain}: +0 entry")
        return
    path = po_path(lang, domain)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES[domain].items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            head = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            blocks.append(f'{_flags(msgid)}{head}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        for name in ("django", "djangojs"):
            fill(locale, name)
