#!/usr/bin/env python3
"""EMSArena i18n — cədvəl ekranları (sahib, 2026-10-14: müəllim görünüşündə redaktə, toqquşma
xəbərdarlığı, kart klikində modal, sürüklə-burax).

Əlavə olunan mətnlər:
  * `registrar.schedule_conflicts` — əhatədən KƏNAR toqquşmanın minimal mətnləri («fənn · qrup»);
  * `registrar.schedule_editor`    — qrup toqquşmasının rədd mesajı;
  * `accounts.schedule_manage`     — müəllim görünüşü ipucları, «Qrup» seçicisi, köçürmə modulu
    (`schedule_editor_move.js`) mətnləri, klaviatura ipucu.

msgid AZ cümlədir → az msgstr = msgid. LOCALES-ə `de` daxildir (əsl alman tərcüməsi).

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir (mövcudluq
`polib` ilə yoxlanır — çoxsətirli `msgid ""` formaları da tanınır), idempotentdir.
Sonra: `python manage.py compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_schedux_2026_10_14.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

CONFLICTS = "registrar.schedule_conflicts"
EDITOR = "registrar.schedule_editor"
MANAGE = "accounts.schedule_manage"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    CONFLICTS: {
        "Müəllimin bu saatda başqa dərsi var: %(subject)s · %(group)s.": {
            "en": "The teacher already has another lesson at this time: %(subject)s · %(group)s.",
            "ru": "У преподавателя в это время уже есть другое занятие: %(subject)s · %(group)s.",
            "tr": "Öğretmenin bu saatte başka bir dersi var: %(subject)s · %(group)s.",
            "de": "Die Lehrkraft hat zu dieser Zeit bereits eine andere Lehrveranstaltung: %(subject)s · %(group)s.",
        },
        "%(room)s auditoriyası bu saatda tutulub: %(subject)s · %(group)s.": {
            "en": "Room %(room)s is taken at this time: %(subject)s · %(group)s.",
            "ru": "Аудитория %(room)s в это время занята: %(subject)s · %(group)s.",
            "tr": "%(room)s dersliği bu saatte dolu: %(subject)s · %(group)s.",
            "de": "Raum %(room)s ist zu dieser Zeit belegt: %(subject)s · %(group)s.",
        },
    },
    EDITOR: {
        (
            "Qrupun bu saatda artıq dərsi var — qrup eyni anda iki dərsdə ola bilməz. "
            "Əvvəlcə həmin dərsi başqa xanaya köçürün və ya boş xana seçin."
        ): {
            "en": (
                "The group already has a lesson at this time — a group cannot attend two lessons at once. "
                "Move that lesson to another cell first, or pick a free cell."
            ),
            "ru": (
                "У группы в это время уже есть занятие — группа не может быть на двух занятиях одновременно. "
                "Сначала перенесите это занятие в другую ячейку или выберите свободную."
            ),
            "tr": (
                "Grubun bu saatte zaten dersi var — bir grup aynı anda iki derste olamaz. "
                "Önce o dersi başka bir hücreye taşıyın ya da boş bir hücre seçin."
            ),
            "de": (
                "Die Gruppe hat zu dieser Zeit bereits eine Lehrveranstaltung — eine Gruppe kann nicht zwei "
                "Veranstaltungen gleichzeitig besuchen. Verschieben Sie zuerst diese Veranstaltung in ein anderes "
                "Feld oder wählen Sie ein freies Feld."
            ),
        },
        "Toqquşan dərs sizin səlahiyyət sahənizdən kənardadır — məcburi dəyişiklik mümkün deyil.": {
            "en": "The conflicting lesson is outside your area of authority — a forced change is not possible.",
            "ru": "Конфликтующее занятие вне вашей зоны полномочий — принудительное изменение невозможно.",
            "tr": "Çakışan ders yetki alanınızın dışında — zorunlu değişiklik yapılamaz.",
            "de": (
                "Die kollidierende Lehrveranstaltung liegt außerhalb Ihres Zuständigkeitsbereichs — eine "
                "erzwungene Änderung ist nicht möglich."
            ),
        },
    },
    MANAGE: {
        "Müəllimi seçin — onun həftəlik cədvəli açılacaq; dərsləri buradan da qoymaq və yerini dəyişmək olar.": {
            "en": "Select a teacher — their weekly timetable opens; you can add and move lessons here as well.",
            "ru": (
                "Выберите преподавателя — откроется его недельное расписание; здесь тоже можно ставить "
                "и переносить занятия."
            ),
            "tr": "Öğretmeni seçin — haftalık programı açılır; dersleri buradan da ekleyip taşıyabilirsiniz.",
            "de": (
                "Wählen Sie eine Lehrkraft — ihr Wochenplan wird geöffnet; auch hier können Sie "
                "Lehrveranstaltungen eintragen und verschieben."
            ),
        },
        "Bu müəllimin bu semestrdə hələ dərsi yoxdur — boş xanaya klikləyib qrup və fənn seçərək dərs qoyun.": {
            "en": (
                "This teacher has no lessons this semester yet — click an empty cell and choose a group and "
                "subject to add one."
            ),
            "ru": (
                "У этого преподавателя в этом семестре ещё нет занятий — нажмите на пустую ячейку и выберите "
                "группу и предмет."
            ),
            "tr": (
                "Bu öğretmenin bu dönemde henüz dersi yok — boş bir hücreye tıklayıp grup ve ders seçerek "
                "ders ekleyin."
            ),
            "de": (
                "Diese Lehrkraft hat in diesem Semester noch keine Lehrveranstaltungen — klicken Sie auf ein "
                "freies Feld und wählen Sie Gruppe und Fach."
            ),
        },
        "Enter — redaktə et. M — köçürmə rejimi: oxlarla xana seçin, Enter — burax, Esc — ləğv.": {
            "en": "Enter — edit. M — move mode: choose a cell with the arrow keys, Enter — drop, Esc — cancel.",
            "ru": (
                "Enter — редактировать. M — режим переноса: выберите ячейку стрелками, Enter — поставить, "
                "Esc — отмена."
            ),
            "tr": "Enter — düzenle. M — taşıma modu: ok tuşlarıyla hücre seçin, Enter — bırak, Esc — iptal.",
            "de": (
                "Enter — bearbeiten. M — Verschiebemodus: Feld mit den Pfeiltasten wählen, Enter — ablegen, "
                "Esc — abbrechen."
            ),
        },
        (
            "Dərsi sürüşdürüb başqa xanaya buraxın (toxunma ekranında — basıb saxlayın); klaviaturada kartı "
            "seçib «M». Toqquşma varsa təsdiqdən əvvəl göstərilir."
        ): {
            "en": (
                "Drag a lesson to another cell (on touch screens — press and hold); with the keyboard, focus "
                "the card and press “M”. Any clash is shown before you confirm."
            ),
            "ru": (
                "Перетащите занятие в другую ячейку (на сенсорном экране — нажмите и удерживайте); с "
                "клавиатуры — выберите карточку и нажмите «M». Конфликт показывается до подтверждения."
            ),
            "tr": (
                "Dersi sürükleyip başka bir hücreye bırakın (dokunmatik ekranda — basılı tutun); klavyede "
                "kartı seçip «M»ye basın. Çakışma varsa onaydan önce gösterilir."
            ),
            "de": (
                "Ziehen Sie eine Lehrveranstaltung in ein anderes Feld (auf Touchscreens — gedrückt halten); "
                "per Tastatur die Karte wählen und „M“ drücken. Kollisionen werden vor der Bestätigung angezeigt."
            ),
        },
        "Qrup": {"en": "Group", "ru": "Группа", "tr": "Grup", "de": "Gruppe"},
        "Seçin…": {"en": "Select…", "ru": "Выберите…", "tr": "Seçin…", "de": "Auswählen…"},
        "Qrup axtar…": {"en": "Search group…", "ru": "Поиск группы…", "tr": "Grup ara…", "de": "Gruppe suchen…"},
        "Uyğun qrup yoxdur": {
            "en": "No matching group",
            "ru": "Подходящих групп нет",
            "tr": "Uygun grup yok",
            "de": "Keine passende Gruppe",
        },
        "Əvvəlcə qrupu seçin.": {
            "en": "Select the group first.",
            "ru": "Сначала выберите группу.",
            "tr": "Önce grubu seçin.",
            "de": "Wählen Sie zuerst die Gruppe.",
        },
        "Köçürülür…": {"en": "Moving…", "ru": "Переносится…", "tr": "Taşınıyor…", "de": "Wird verschoben…"},
        "Dərs köçürüldü.": {
            "en": "The lesson has been moved.",
            "ru": "Занятие перенесено.",
            "tr": "Ders taşındı.",
            "de": "Die Lehrveranstaltung wurde verschoben.",
        },
        "Dərs köçürülmədi — əvvəlki yerinə qaytarıldı.": {
            "en": "The lesson was not moved — it is back in its previous place.",
            "ru": "Занятие не перенесено — оно возвращено на прежнее место.",
            "tr": "Ders taşınamadı — eski yerine geri alındı.",
            "de": "Die Lehrveranstaltung wurde nicht verschoben — sie steht wieder an ihrem bisherigen Platz.",
        },
        "Bu xanaya köçürmək olmaz — əvvəlcə toqquşmanı aradan qaldırın.": {
            "en": "The lesson cannot be moved to this cell — resolve the clash first.",
            "ru": "В эту ячейку перенести нельзя — сначала устраните конфликт.",
            "tr": "Bu hücreye taşınamaz — önce çakışmayı giderin.",
            "de": "In dieses Feld kann nicht verschoben werden — lösen Sie zuerst die Kollision.",
        },
        (
            "Toqquşma var. Yenə də köçürmək üçün səbəb yazın — toqquşan dərs silinmir, «Yenidən "
            "yerləşdirilməli» siyahısına düşür."
        ): {
            "en": (
                "There is a clash. To move anyway, give a reason — the conflicting lesson is not deleted, it "
                "goes to the “Needs re-placing” list."
            ),
            "ru": (
                "Есть конфликт. Чтобы всё равно перенести, укажите причину — конфликтующее занятие не "
                "удаляется, а попадает в список «Требуют переноса»."
            ),
            "tr": (
                "Çakışma var. Yine de taşımak için bir gerekçe yazın — çakışan ders silinmez, «Yeniden "
                "yerleştirilmeli» listesine düşer."
            ),
            "de": (
                "Es gibt eine Kollision. Um trotzdem zu verschieben, geben Sie einen Grund an — die kollidierende "
                "Lehrveranstaltung wird nicht gelöscht, sondern landet in der Liste „Neu einzuplanen“."
            ),
        },
        "Köçürmə rejimi: oxlarla xana seçin, Enter — burax, Esc — ləğv.": {
            "en": "Move mode: choose a cell with the arrow keys, Enter — drop, Esc — cancel.",
            "ru": "Режим переноса: выберите ячейку стрелками, Enter — поставить, Esc — отмена.",
            "tr": "Taşıma modu: ok tuşlarıyla hücre seçin, Enter — bırak, Esc — iptal.",
            "de": "Verschiebemodus: Feld mit den Pfeiltasten wählen, Enter — ablegen, Esc — abbrechen.",
        },
        "Köçürmə ləğv edildi.": {
            "en": "Move cancelled.",
            "ru": "Перенос отменён.",
            "tr": "Taşıma iptal edildi.",
            "de": "Verschieben abgebrochen.",
        },
        "Məcburi köçürmə üçün ən azı 10 simvolluq səbəb yazın (auditə düşür).": {
            "en": "A forced move needs a reason of at least 10 characters (it goes to the audit log).",
            "ru": "Для принудительного переноса укажите причину не короче 10 символов (она попадает в аудит).",
            "tr": "Zorunlu taşıma için en az 10 karakterlik bir gerekçe yazın (denetim kaydına düşer).",
            "de": (
                "Für ein erzwungenes Verschieben ist ein Grund mit mindestens 10 Zeichen nötig "
                "(er wird im Audit-Protokoll gespeichert)."
            ),
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
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
