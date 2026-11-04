#!/usr/bin/env python3
"""EMSArena i18n — müəllim müəyyən tarixdən bu günə keçmiş tarixli dərs əlavə edə bilər (sahib 2026-11-04).

«Sistem tənzimləmələri»nin ``journal.backdate_since_enabled`` / ``journal.backdate_since`` açarları, yazma
pəncərəsinin mesajları və jurnal modalı/grid ipucları. msgid AZ cümlədir → az msgstr = msgid. İdempotentdir
(mövcud msgctxt+msgid toxunulmur); sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    "core.runtime_settings": {
        "Müəllimlər müəyyən tarixdən bu günə keçmiş tarixli dərs əlavə edə bilər": t(
            "Teachers may add past-dated lessons from a set date up to today",
            "Преподаватели могут добавлять занятия задним числом с заданной даты по сегодня",
            "Öğretmenler belirli bir tarihten bugüne geçmiş tarihli ders ekleyebilir",
            "Lehrkräfte dürfen Stunden rückwirkend ab einem festen Datum bis heute anlegen",
        ),
        (
            "Yandırılanda müəllim aşağıdakı başlanğıc tarixindən bu günədək istənilən tarixə dərs aça və həmin "
            "dərslərin boş xanalarına q/b, i/e və bal yaza bilər — adi «gecikmiş yazı müddəti» həddindən köhnə "
            "olsa da. Gələcək tarixə dərs açılmır; semestr sərhədi, yazılmış xananın kilidi və bağlı jurnal "
            "qaydası dəyişmir. Söndürüləndə adi yazma müddəti qayıdır."
        ): t(
            "When on, a teacher can open a lesson on any date from the start date below up to today and record "
            "absences, attendance and scores in the empty cells of those lessons — even if the date is older than "
            "the usual late entry period. Lessons cannot be opened for a future date; the semester boundary, the "
            "lock on recorded cells and the closed-journal rule do not change. When off, the usual entry period "
            "applies again.",
            "Когда включено, преподаватель может открыть занятие на любую дату с указанной ниже начальной даты по "
            "сегодня и записать пропуски, посещаемость и баллы в пустые ячейки этих занятий — даже если дата "
            "старше обычного срока поздней записи. Занятие на будущую дату не открывается; граница семестра, "
            "блокировка записанной ячейки и правило закрытого журнала не меняются. При выключении возвращается "
            "обычный срок записи.",
            "Açıkken öğretmen aşağıdaki başlangıç tarihinden bugüne kadar herhangi bir tarihe ders açabilir ve bu "
            "derslerin boş hücrelerine devamsızlık, katılım ve puan yazabilir — tarih olağan geç yazma süresinden "
            "eski olsa bile. Gelecek tarihe ders açılmaz; dönem sınırı, yazılmış hücrenin kilidi ve kapalı defter "
            "kuralı değişmez. Kapatıldığında olağan yazma süresi geri gelir.",
            "Wenn aktiviert, kann eine Lehrkraft an jedem Datum vom unten angegebenen Startdatum bis heute eine "
            "Stunde anlegen und in den leeren Zellen dieser Stunden Fehlzeiten, Anwesenheit und Punkte erfassen — "
            "auch wenn das Datum älter als die übliche Nachtragsfrist ist. Für ein zukünftiges Datum wird keine "
            "Stunde angelegt; Semestergrenze, Sperre erfasster Zellen und die Regel des geschlossenen Journals "
            "ändern sich nicht. Wenn deaktiviert, gilt wieder die übliche Eintragungsfrist.",
        ),
        "Keçmiş tarixli dərsin başlanğıc tarixi": t(
            "Start date for past-dated lessons",
            "Начальная дата для занятий задним числом",
            "Geçmiş tarihli derslerin başlangıç tarihi",
            "Startdatum für rückwirkende Stunden",
        ),
        (
            "Yuxarıdakı bayraq yandırılıbsa müəllim bu tarixdən (daxil) bu günədək dərs əlavə edə bilər. "
            "Bayraq söndürülüdürsə bu tarix tətbiq olunmur."
        ): t(
            "If the switch above is on, a teacher can add lessons from this date (inclusive) up to today. If the "
            "switch is off, this date is not applied.",
            "Если переключатель выше включён, преподаватель может добавлять занятия с этой даты (включительно) по "
            "сегодня. Если переключатель выключен, дата не применяется.",
            "Yukarıdaki anahtar açıksa öğretmen bu tarihten (dahil) bugüne kadar ders ekleyebilir. Anahtar "
            "kapalıysa bu tarih uygulanmaz.",
            "Ist der Schalter oben aktiviert, kann eine Lehrkraft Stunden ab diesem Datum (einschließlich) bis heute "
            "anlegen. Ist er deaktiviert, wird dieses Datum nicht angewendet.",
        ),
    },
    "registrar.journal_timing": {
        "Dərs tarixi %(date)s tarixindən əvvəl ola bilməz. Daha köhnə tarix üçün RİM-ə müraciət edin.": t(
            "The lesson date cannot be before %(date)s. For an older date, contact the Registrar's Office.",
            "Дата занятия не может быть раньше %(date)s. Для более ранней даты обратитесь в регистратуру.",
            "Ders tarihi %(date)s tarihinden önce olamaz. Daha eski bir tarih için Kayıt Ofisine başvurun.",
            "Das Unterrichtsdatum darf nicht vor dem %(date)s liegen. Für ein älteres Datum wenden Sie sich an das "
            "Studienbüro.",
        ),
        "%(date)s tarixli dərsə yeni qeyd yazmaq olmaz — keçmiş dərslərə yazı %(since)s tarixindən açıqdır.": t(
            "A new record cannot be written for the lesson of %(date)s — entries for past lessons are open from "
            "%(since)s.",
            "Нельзя записать новую отметку на занятие %(date)s — запись на прошедшие занятия открыта с %(since)s.",
            "%(date)s tarihli derse yeni kayıt yazılamaz — geçmiş derslere yazma %(since)s tarihinden itibaren "
            "açıktır.",
            "Für die Stunde vom %(date)s kann kein neuer Eintrag erfasst werden — Einträge für vergangene Stunden "
            "sind ab dem %(since)s möglich.",
        ),
    },
    "registrar.journal": {
        "Keçmiş tarixə dərs %(date)s tarixindən bu günədək açmaq olar.": t(
            "A lesson can be opened for any past date from %(date)s up to today.",
            "Занятие можно открыть на прошедшую дату с %(date)s по сегодня.",
            "Geçmiş tarihe ders %(date)s tarihinden bugüne kadar açılabilir.",
            "Eine Stunde kann für ein vergangenes Datum vom %(date)s bis heute angelegt werden.",
        ),
        (
            "Davamiyyət %(date)s tarixindən bu günədək keçirilmiş dərslərə qeyd edilə bilər · yazılmış qeyd %(w)s "
            "sonra kilidlənir — düzəliş üçün RİM-ə (sənədli düzəliş) müraciət edilir."
        ): t(
            "Attendance can be recorded for lessons held from %(date)s up to today · a recorded mark locks after "
            "%(w)s — for a correction, apply to the Digital Development Centre (RİM) for a documented correction.",
            "Посещаемость можно отмечать для занятий, проведённых с %(date)s по сегодня · записанная отметка "
            "блокируется через %(w)s — для исправления обращаются в RİM (документальное исправление).",
            "Devam, %(date)s tarihinden bugüne kadar yapılmış dersler için kaydedilebilir · yazılan kayıt %(w)s "
            "sonra kilitlenir — düzeltme için RİM'e (belgeli düzeltme) başvurulur.",
            "Die Anwesenheit kann für Stunden erfasst werden, die vom %(date)s bis heute stattgefunden haben · ein "
            "Eintrag wird nach %(w)s gesperrt — für eine Korrektur wenden Sie sich an das RİM (dokumentierte "
            "Korrektur).",
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
