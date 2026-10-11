#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-10 (WP4): jurnalda «Aktivləşdir» RİM tənzimləməsidir, «Yeni dərs» DOLU açılır.

Əlavə olunan mətnlər (hamısı `django.po`-dadır; `djangojs` kataloquna yeni mətn YOXDUR):
  * `registrar.journal_activation`: «Aktivləşdir» söndürülüdə cədvəldən kənar dərsin xətası (ona yönləndirmir);
  * `registrar.journal_prefill`: «Bu günün cədvəl dərsləri» zolağı (söndürülü rejim), «Yeni dərs» modalının
    doldurma ipucları, «cədvəldən kənar» sahəsinin ipucu;
  * `accounts.dashboard`: ana səhifədə «Jurnalı aç» düyməsinin ipucu.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_10_wp4lesson.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


AD = "accounts.dashboard"
JA = "registrar.journal_activation"
JP = "registrar.journal_prefill"

_ACTIVATION = [
    _t(
        "Bu tarix və saatda cədvəldə bu fənnin dərsi yoxdur — cədvəldən kənar dərs üçün səbəbi yazın "
        "(məs. əvəzetmə, kompensasiya dərsi). Cədvəldəki dərs üçün tarixi və saatı cədvələ uyğun seçin.",
        "The timetable has no class of this course at this date and time — enter a reason for an off-timetable "
        "lesson (e.g. substitution, make-up class). For a timetabled class choose the date and time from the timetable.",
        "В расписании нет занятия по этому предмету в эту дату и время — укажите причину занятия вне расписания "
        "(напр. замена, компенсационное занятие). Для занятия по расписанию выберите дату и время по расписанию.",
        "Bu tarih ve saatte programda bu dersin dersi yok — program dışı ders için nedeni yazın "
        "(ör. yerine ders, telafi dersi). Programdaki ders için tarihi ve saati programa uygun seçin.",
    ),
]

_PREFILL = [
    _t(
        "Dərsi «Yeni dərs» ilə açın — forma bu dərsin saatı, növü, otağı, müəllimi və növbəti mövzusu ilə dolu açılır.",
        "Open the lesson with “New lesson” — the form comes pre-filled with this class's time, type, room, "
        "teacher and next topic.",
        "Откройте занятие кнопкой «Новое занятие» — форма откроется заполненной временем, типом, аудиторией, "
        "преподавателем и следующей темой этого занятия.",
        "Dersi «Yeni ders» ile açın — form bu dersin saati, türü, dersliği, öğretim elemanı ve sonraki konusuyla "
        "dolu açılır.",
    ),
    _t("Dərs açılıb", "Lesson opened", "Занятие открыто", "Ders açıldı"),
    _t("Dərs açılmayıb", "Not opened", "Занятие не открыто", "Ders açılmadı"),
    _t(
        "Yeni dərs formasını bu cədvəl dərsinin məlumatları ilə aç",
        "Open the new lesson form filled with this timetabled class",
        "Открыть форму нового занятия с данными этого занятия по расписанию",
        "Yeni ders formunu bu programdaki dersin bilgileriyle aç",
    ),
    _t(
        "Forma bu günün cədvəl dərsindən doldurulub",
        "The form is filled from today's timetabled class",
        "Форма заполнена по сегодняшнему занятию из расписания",
        "Form bugünkü programdaki dersten dolduruldu",
    ),
    _t(
        "Saat, tip, otaq, müəllim və növbəti mövzu cədvəldən və sillabusdan götürülüb — yoxlayıb «Tətbiq et» basın.",
        "Time, type, room, teacher and the next topic come from the timetable and the syllabus — check them and "
        "press “Apply”.",
        "Время, тип, аудитория, преподаватель и следующая тема взяты из расписания и силлабуса — проверьте и "
        "нажмите «Применить».",
        "Saat, tür, derslik, öğretim elemanı ve sonraki konu programdan ve izlenceden alındı — kontrol edip "
        "«Uygula»ya basın.",
    ),
    _t(
        "Sahələr bu fənnin son dərsinə və sillabusdakı növbəti mövzuya görə doldurulub — yoxlayın, lazım olsa dəyişin.",
        "The fields are filled from this course's last lesson and the next topic in the syllabus — check them and "
        "change if needed.",
        "Поля заполнены по последнему занятию предмета и следующей теме силлабуса — проверьте и при "
        "необходимости измените.",
        "Alanlar bu dersin son dersine ve izlencedeki sonraki konuya göre dolduruldu — kontrol edin, gerekirse "
        "değiştirin.",
    ),
    _t(
        "Bu tarix və saatda cədvəldə dərs yoxdur — səbəb məcburidir və «Keçilmiş dərslər»də «cədvəldən kənar» kimi "
        "işarələnir. Cədvəldəki dərs üçün tarixi və saatı cədvələ uyğun seçin.",
        "The timetable has no class at this date and time — a reason is required and the lesson is flagged "
        "“off-timetable” in “Lessons held”. For a timetabled class choose the date and time from the timetable.",
        "В расписании нет занятия в эту дату и время — причина обязательна, а занятие помечается «вне расписания» "
        "в «Проведённых занятиях». Для занятия по расписанию выберите дату и время по расписанию.",
        "Bu tarih ve saatte programda ders yok — neden zorunludur ve ders «İşlenen dersler»de «program dışı» olarak "
        "işaretlenir. Programdaki ders için tarihi ve saati programa uygun seçin.",
    ),
]

_DASHBOARD = [
    _t(
        "Bu fənnin jurnalını aç — bu günün dərsini oradan «Yeni dərs» ilə açın (forma cədvəldən dolu gəlir)",
        "Open this course's journal — open today's class there with “New lesson” (the form comes pre-filled "
        "from the timetable)",
        "Открыть журнал предмета — откройте там сегодняшнее занятие кнопкой «Новое занятие» (форма заполняется "
        "по расписанию)",
        "Bu dersin defterini aç — bugünkü dersi oradan «Yeni ders» ile açın (form programdan dolu gelir)",
    ),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    AD: {row["az"]: row for row in _DASHBOARD},
    JA: {row["az"]: row for row in _ACTIVATION},
    JP: {row["az"]: row for row in _PREFILL},
}

FORCE = set()


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
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
