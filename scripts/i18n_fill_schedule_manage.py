#!/usr/bin/env python3
"""EMSArena i18n — «Cədvəl idarəetməsi» bölməsinin sətirləri (4 dil). İdempotent.

Yeni bölmənin (schedule-manage) UI mətnləri, `schedule.*` icazə etiketləri,
sidebar adı, saxlama-öncəsi validasiya/konflikt mesajları və cədvəl dəyişikliyi
bildirişinin mətnləri doldurulur.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silə bilir) — skript
yalnız ƏLAVƏ edir və mövcud girişə toxunmur (bax i18n_fill_teaching_handover.py).

İstifadə:  python scripts/i18n_fill_schedule_manage.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    # ── İcazə etiketləri (permission-editor + «səlahiyyətləriniz» paneli) ───
    "organizations.permission.label": {
        "Dərs cədvəlinə baxış": {
            "en": "View the class timetable",
            "ru": "Просмотр расписания занятий",
            "tr": "Ders programını görüntüleme",
        },
        "Dərs cədvəlini idarə etmək (slot əlavə/sil)": {
            "en": "Manage the class timetable (add/remove slots)",
            "ru": "Управление расписанием занятий (добавление/удаление слотов)",
            "tr": "Ders programını yönetme (slot ekleme/silme)",
        },
    },
    # ── Sidebar ─────────────────────────────────────────────────────────────
    "profile.sidebar": {
        "Cədvəl idarəetməsi": {
            "en": "Timetable management",
            "ru": "Управление расписанием",
            "tr": "Program yönetimi",
        },
    },
    # ── Servis qatı: validasiya, konflikt səbəbi, bildiriş ──────────────────
    "registrar.schedule_manage": {
        "Həftənin günü 1–7 aralığında olmalıdır.": {
            "en": "The weekday must be between 1 and 7.",
            "ru": "День недели должен быть от 1 до 7.",
            "tr": "Haftanın günü 1–7 aralığında olmalıdır.",
        },
        "Başlama və bitmə vaxtı düzgün seçilməlidir.": {
            "en": "A valid start and end time must be selected.",
            "ru": "Необходимо выбрать корректное время начала и окончания.",
            "tr": "Geçerli bir başlangıç ve bitiş saati seçilmelidir.",
        },
        "Bitmə vaxtı başlama vaxtından sonra olmalıdır.": {
            "en": "The end time must be later than the start time.",
            "ru": "Время окончания должно быть позже времени начала.",
            "tr": "Bitiş saati başlangıç saatından sonra olmalıdır.",
        },
        "Bu semestr bitib — cədvəl slotu əlavə edilə bilməz.": {
            "en": "This semester has ended — no timetable slot can be added.",
            "ru": "Этот семестр завершён — слот расписания добавить нельзя.",
            "tr": "Bu dönem sona erdi — programa slot eklenemez.",
        },
        "Bu slot artıq cədvəldədir.": {
            "en": "This slot is already in the timetable.",
            "ru": "Этот слот уже есть в расписании.",
            "tr": "Bu slot programda zaten var.",
        },
        "Bu vaxt %(subject)s ilə üst-üstə düşür (%(reason)s).": {
            "en": "This time overlaps with %(subject)s (%(reason)s).",
            "ru": "Это время пересекается с %(subject)s (%(reason)s).",
            "tr": "Bu saat %(subject)s ile çakışıyor (%(reason)s).",
        },
        "Dərs cədvəli dəyişdi: %(subject)s %(when)s": {
            "en": "The class timetable changed: %(subject)s %(when)s",
            "ru": "Расписание занятий изменилось: %(subject)s %(when)s",
            "tr": "Ders programı değişti: %(subject)s %(when)s",
        },
        "Slot cədvəldən silindi.": {
            "en": "The slot was removed from the timetable.",
            "ru": "Слот удалён из расписания.",
            "tr": "Slot programdan silindi.",
        },
        "Cədvələ yeni slot əlavə edildi.": {
            "en": "A new slot was added to the timetable.",
            "ru": "В расписание добавлен новый слот.",
            "tr": "Programa yeni bir slot eklendi.",
        },
        "Slot yadda saxlanılmadı — məlumatları yoxlayın.": {
            "en": "The slot was not saved — check the details.",
            "ru": "Слот не сохранён — проверьте данные.",
            "tr": "Slot kaydedilmedi — bilgileri kontrol edin.",
        },
        # Konflikt səbəbi (qısa etiketlər — mesajın içinə yerləşir).
        "qrup": {"en": "group", "ru": "группа", "tr": "grup"},
        "müəllim": {"en": "teacher", "ru": "преподаватель", "tr": "öğretim elemanı"},
        "auditoriya": {"en": "room", "ru": "аудитория", "tr": "derslik"},
    },
    # ── Bölmənin öz mətnləri (panel + JSON səthi) ──────────────────────────
    "accounts.schedule_manage": {
        "Cədvəl idarəetməsi": {
            "en": "Timetable management",
            "ru": "Управление расписанием",
            "tr": "Program yönetimi",
        },
        (
            "Qrupun həftəlik dərs cədvəlini qurun: slot əlavə edin, konflikti saxlamadan əvvəl görün, "
            "lazımsız slotu silin. Dəyişiklik müəllimə və qrupun tələbələrinə bildiriş kimi gedir."
        ): {
            "en": (
                "Build the group's weekly timetable: add slots, see clashes before saving, remove "
                "slots you no longer need. Every change is sent to the teacher and the group's students."
            ),
            "ru": (
                "Составьте недельное расписание группы: добавляйте слоты, видьте конфликты до "
                "сохранения, удаляйте лишние. Изменение уходит уведомлением преподавателю и студентам группы."
            ),
            "tr": (
                "Grubun haftalık ders programını kurun: slot ekleyin, çakışmaları kaydetmeden önce "
                "görün, gereksiz slotu silin. Değişiklik öğretim elemanına ve grubun öğrencilerine bildirilir."
            ),
        },
        "Dərs cədvəlini idarə etmək üçün icazəniz yoxdur.": {
            "en": "You do not have permission to manage the class timetable.",
            "ru": "У вас нет прав на управление расписанием занятий.",
            "tr": "Ders programını yönetme yetkiniz yok.",
        },
        ("Dərs cədvəlini idarə etmək üçün icazəniz yoxdur — bu bölmə yalnız səlahiyyətli rollar üçündür."): {
            "en": (
                "You do not have permission to manage the class timetable — this section is for "
                "authorised roles only."
            ),
            "ru": (
                "У вас нет прав на управление расписанием занятий — этот раздел только для " "уполномоченных ролей."
            ),
            "tr": ("Ders programını yönetme yetkiniz yok — bu bölüm yalnızca yetkili roller içindir."),
        },
        "Naməlum əməliyyat.": {
            "en": "Unknown operation.",
            "ru": "Неизвестная операция.",
            "tr": "Bilinmeyen işlem.",
        },
        "Bütün universitet": {"en": "The whole university", "ru": "Весь университет", "tr": "Tüm üniversite"},
        "Yalnız öz struktur bölmələriniz": {
            "en": "Only your own structural units",
            "ru": "Только ваши структурные подразделения",
            "tr": "Yalnızca kendi yapısal biriminiz",
        },
        "Səlahiyyət sahəniz": {"en": "Your authority scope", "ru": "Ваша зона полномочий", "tr": "Yetki alanınız"},
        "Tədris ili": {"en": "Academic year", "ru": "Учебный год", "tr": "Öğretim yılı"},
        "Semestr": {"en": "Semester", "ru": "Семестр", "tr": "Dönem"},
        "Görünüş": {"en": "View", "ru": "Вид", "tr": "Görünüm"},
        "Qrup cədvəli": {"en": "Group timetable", "ru": "Расписание группы", "tr": "Grup programı"},
        "Müəllim cədvəli": {
            "en": "Teacher timetable",
            "ru": "Расписание преподавателя",
            "tr": "Öğretim elemanı programı",
        },
        "Qrup": {"en": "Group", "ru": "Группа", "tr": "Grup"},
        "Müəllim": {"en": "Teacher", "ru": "Преподаватель", "tr": "Öğretim elemanı"},
        "Seçin…": {"en": "Select…", "ru": "Выберите…", "tr": "Seçin…"},
        (
            "Səlahiyyət sahənizdə qrup yoxdur. Üzvlüyünüzə struktur bölməsi (scope_unit) təyin "
            "edilməyibsə siyahı boş qalır."
        ): {
            "en": (
                "There is no group in your authority scope. If no structural unit (scope_unit) is set "
                "on your membership, the list stays empty."
            ),
            "ru": (
                "В вашей зоне полномочий нет групп. Если в вашем членстве не задано структурное "
                "подразделение (scope_unit), список остаётся пустым."
            ),
            "tr": ("Yetki alanınızda grup yok. Üyeliğinize yapısal birim (scope_unit) atanmamışsa liste " "boş kalır."),
        },
        "Bu təşkilatda akademik semestr yoxdur — əvvəlcə semestr yaradılmalıdır.": {
            "en": "This organisation has no academic semester — a semester must be created first.",
            "ru": "В этой организации нет учебного семестра — сначала нужно создать семестр.",
            "tr": "Bu kurumda akademik dönem yok — önce bir dönem oluşturulmalıdır.",
        },
        "Slotlar": {"en": "Slots", "ru": "Слоты", "tr": "Slotlar"},
        "Gün": {"en": "Day", "ru": "День", "tr": "Gün"},
        "Saat": {"en": "Time", "ru": "Время", "tr": "Saat"},
        "Fənn": {"en": "Subject", "ru": "Предмет", "tr": "Ders"},
        "Növ": {"en": "Type", "ru": "Тип", "tr": "Tür"},
        "Otaq": {"en": "Room", "ru": "Аудитория", "tr": "Derslik"},
        "Həftə": {"en": "Week", "ru": "Неделя", "tr": "Hafta"},
        "Əməliyyat": {"en": "Action", "ru": "Действие", "tr": "İşlem"},
        "Slotu sil": {"en": "Delete slot", "ru": "Удалить слот", "tr": "Slotu sil"},
        "Bu görünüşdə hələ slot yoxdur.": {
            "en": "There is no slot in this view yet.",
            "ru": "В этом представлении пока нет слотов.",
            "tr": "Bu görünümde henüz slot yok.",
        },
        "Slot əlavə et": {"en": "Add slot", "ru": "Добавить слот", "tr": "Slot ekle"},
        "Dərs növü": {"en": "Lesson type", "ru": "Тип занятия", "tr": "Ders türü"},
        "Dərs saatı": {"en": "Lesson hour", "ru": "Пара", "tr": "Ders saati"},
        "Sərbəst vaxt…": {"en": "Custom time…", "ru": "Своё время…", "tr": "Serbest saat…"},
        "Başlama": {"en": "Start", "ru": "Начало", "tr": "Başlangıç"},
        "Bitmə": {"en": "End", "ru": "Окончание", "tr": "Bitiş"},
        "məs. Otaq 304 · II korpus": {
            "en": "e.g. Room 304 · Building II",
            "ru": "напр. Аудитория 304 · Корпус II",
            "tr": "örn. Derslik 304 · II. Blok",
        },
        "Konflikti yoxla": {"en": "Check for clashes", "ru": "Проверить конфликты", "tr": "Çakışmayı kontrol et"},
        "Bu qrup üçün seçilmiş semestrdə dərs açılışı yoxdur — əvvəlcə fənn açılışı yaradılmalıdır.": {
            "en": (
                "This group has no course offering in the selected semester — an offering must be " "created first."
            ),
            "ru": ("У этой группы нет учебных дисциплин в выбранном семестре — сначала нужно создать " "дисциплину."),
            "tr": ("Bu grubun seçilen dönemde ders açılışı yok — önce bir ders açılışı oluşturulmalıdır."),
        },
        "Slotu silmək?": {"en": "Delete the slot?", "ru": "Удалить слот?", "tr": "Slot silinsin mi?"},
        "Silinmə müəllimə və qrupun tələbələrinə bildiriş kimi gedir və audit jurnalına yazılır.": {
            "en": "The removal is sent to the teacher and the group's students and written to the audit log.",
            "ru": "Удаление уходит уведомлением преподавателю и студентам группы и пишется в журнал аудита.",
            "tr": "Silme işlemi öğretim elemanına ve grubun öğrencilerine bildirilir ve denetim günlüğüne yazılır.",
        },
        "İmtina": {"en": "Cancel", "ru": "Отмена", "tr": "Vazgeç"},
        "Sil": {"en": "Delete", "ru": "Удалить", "tr": "Sil"},
        "Əməliyyat yerinə yetirilmədi.": {
            "en": "The operation was not completed.",
            "ru": "Операция не выполнена.",
            "tr": "İşlem tamamlanmadı.",
        },
        "Slot əlavə edildi.": {"en": "The slot was added.", "ru": "Слот добавлен.", "tr": "Slot eklendi."},
        "Slot silindi.": {"en": "The slot was deleted.", "ru": "Слот удалён.", "tr": "Slot silindi."},
        "Konflikt yoxdur — slot əlavə edilə bilər.": {
            "en": "No clash — the slot can be added.",
            "ru": "Конфликтов нет — слот можно добавить.",
            "tr": "Çakışma yok — slot eklenebilir.",
        },
        "Konflikt": {"en": "Clash", "ru": "Конфликт", "tr": "Çakışma"},
        "Yoxlanılır…": {"en": "Checking…", "ru": "Проверка…", "tr": "Kontrol ediliyor…"},
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
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
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
