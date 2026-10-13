#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-13 (gecə): vaxtla məhdud nəzarətçi növbələri + zal monitoru əlavələri.

Mənbə: `apps/exams/templates/exams/exam_center/{_duty_strip,room_monitor,room_list}.html`,
`apps/exams/views/exam_center/{duties,room_monitor}.py`,
`apps/exams/services/final_center/duty_admin.py`, `apps/exams/services/supervision/signals.py`,
`apps/exams/templatetags/proctoring.py`, `apps/exams/domain/final_center/duties.py`.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_examsuperv_2026_10_13.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr, msgid=None):
    row = {"az": az, "en": en, "ru": ru, "tr": tr}
    row["msgid"] = msgid or az
    return row


DUTY = "exams.final_center.duty"
SIGNAL = "exams.proctoring.signal"
MONITOR = "exams.proctoring.monitor"
FIELD = "exams.model.invigilator_duty.field"
META = "exams.model.invigilator_duty.meta"

_DUTY = [
    _t("Nəzarət növbələriniz", "Your invigilation duties", "Ваши дежурства наблюдателя", "Gözetmenlik görevleriniz"),
    _t(
        "İmtahan davam edir — çıxış ən gec %(t)s-a qədər açıqdır",
        "The exam is still running — access stays open until %(t)s at the latest",
        "Экзамен продолжается — доступ открыт не позднее чем до %(t)s",
        "Sınav sürüyor — erişim en geç %(t)s saatine kadar açık",
    ),
    _t(
        "Çıxış %(t)s-da avtomatik bağlanır",
        "Access closes automatically at %(t)s",
        "Доступ автоматически закроется в %(t)s",
        "Erişim %(t)s saatinde otomatik kapanır",
    ),
    _t(
        "Hazırda aktiv nəzarət növbəniz yoxdur.",
        "You have no active invigilation duty right now.",
        "Сейчас у вас нет активного дежурства.",
        "Şu anda aktif gözetmenlik göreviniz yok.",
    ),
    _t(
        "Növbəni imtahan mərkəzi rəhbəri yazır; çıxış növbədən 30 dəqiqə əvvəl açılır və imtahan/gün bitəndə avtomatik bağlanır.",
        "Duties are assigned by the exam centre head; access opens 30 minutes before the duty and closes "
        "automatically when the exam or the day ends.",
        "Дежурство назначает руководитель экзаменационного центра; доступ открывается за 30 минут до начала "
        "и автоматически закрывается по окончании экзамена или дня.",
        "Görevi sınav merkezi başkanı atar; erişim görevden 30 dakika önce açılır ve sınav ya da gün bitince "
        "otomatik kapanır.",
    ),
    _t(
        "Nəzarət növbəniz bitdi — bu zala çıxış bağlandı.",
        "Your invigilation duty has ended — access to this hall is closed.",
        "Ваше дежурство закончилось — доступ к этому залу закрыт.",
        "Gözetmenlik göreviniz bitti — bu salona erişim kapandı.",
    ),
    _t("Zallara qayıt", "Back to halls", "Вернуться к залам", "Salonlara dön"),
    _t("Nəzarətçi növbələri", "Invigilator duties", "Дежурства наблюдателей", "Gözetmen görevleri"),
    _t(
        "Nəzarətçinin çıxışı növbədən %(lead)s dəqiqə əvvəl açılır; imtahan bitəndə (son saatdan %(grace)s dəqiqə "
        "sonra, zalda canlı imtahan qalmayıbsa) və ya gün sonunda avtomatik bağlanır.",
        "Invigilator access opens %(lead)s minutes before the duty and closes automatically when the exam ends "
        "(%(grace)s minutes after the end time, if no live exam remains in the hall) or at the end of the day.",
        "Доступ наблюдателя открывается за %(lead)s минут до дежурства и автоматически закрывается по окончании "
        "экзамена (через %(grace)s минут после времени окончания, если в зале нет идущего экзамена) или в конце дня.",
        "Gözetmen erişimi görevden %(lead)s dakika önce açılır; sınav bitince (bitiş saatinden %(grace)s dakika "
        "sonra, salonda canlı sınav kalmadıysa) veya gün sonunda otomatik kapanır.",
    ),
    _t("Aktiv", "Active", "Активно", "Aktif"),
    _t("%(t)s-da açılır", "Opens at %(t)s", "Откроется в %(t)s", "%(t)s saatinde açılır"),
    _t("Ləğv edilib", "Revoked", "Отменено", "İptal edildi"),
    _t("Bitib", "Ended", "Завершено", "Bitti"),
    _t(
        "Növbə ləğv edilsin? Nəzarətçinin çıxışı dərhal bağlanacaq.",
        "Revoke this duty? The invigilator's access will close immediately.",
        "Отменить дежурство? Доступ наблюдателя будет закрыт немедленно.",
        "Görev iptal edilsin mi? Gözetmenin erişimi hemen kapanacak.",
    ),
    _t("Ləğv et", "Revoke", "Отменить", "İptal et"),
    _t(
        "Bu zal üçün bu gün və sonrakı günlərə növbə yazılmayıb.",
        "No duties are scheduled for this hall today or later.",
        "Для этого зала на сегодня и последующие дни дежурств нет.",
        "Bu salon için bugün ve sonraki günlere görev atanmadı.",
    ),
    _t("Yeni növbə", "New duty", "Новое дежурство", "Yeni görev"),
    _t("Gün", "Date", "Дата", "Tarih"),
    _t("Başlanğıc", "Start", "Начало", "Başlangıç"),
    _t("Son", "End", "Конец", "Bitiş"),
    _t("Qeyd (istəyə bağlı)", "Note (optional)", "Примечание (необязательно)", "Not (isteğe bağlı)"),
    _t("Növbəni yaz", "Assign duty", "Назначить дежурство", "Görevi ata"),
    _t(
        "Köhnə daimi təyinatlar silinsin?",
        "Remove the old permanent assignments?",
        "Удалить старые постоянные назначения?",
        "Eski kalıcı atamalar silinsin mi?",
    ),
    _t(
        "Köhnə daimi təyinatlar (yalnız canlı imtahan zamanı işləyir):",
        "Old permanent assignments (only work while an exam is live):",
        "Старые постоянные назначения (действуют только во время идущего экзамена):",
        "Eski kalıcı atamalar (yalnızca canlı sınav sırasında geçerli):",
    ),
    _t("Təmizlə", "Clear", "Очистить", "Temizle"),
    _t("Nəzarət müddəti bitdi", "Invigilation period ended", "Время наблюдения истекло", "Gözetim süresi bitti"),
    _t("s", "h", "ч", "sa"),
    _t("dəq", "min", "мин", "dk"),
    _t("san", "sec", "с", "sn"),
    _t("Qalan vaxt", "Time left", "Осталось времени", "Kalan süre"),
    _t("Yeni şübhəli", "New suspicious", "Новый подозрительный", "Yeni şüpheli"),
    _t("Bağla", "Close", "Закрыть", "Kapat"),
    _t("Nəzarətçi qeydi", "Invigilator note", "Заметка наблюдателя", "Gözetmen notu"),
    _t(
        "Məs.: telefonla danışırdı, xəbərdarlıq edildi",
        "E.g.: was on the phone, warned",
        "Напр.: говорил по телефону, сделано предупреждение",
        "Örn.: telefonla konuşuyordu, uyarıldı",
    ),
    _t("Qeydi yaz", "Save note", "Сохранить заметку", "Notu kaydet"),
    _t(
        "Qeyd yazıldı — xronologiyada görünəcək.",
        "Note saved — it will appear in the timeline.",
        "Заметка сохранена — она появится в хронологии.",
        "Not kaydedildi — zaman çizelgesinde görünecek.",
    ),
    _t("Qeyd yazılmadı.", "The note was not saved.", "Заметка не сохранена.", "Not kaydedilmedi."),
    _t(
        "Tarix və ya saat formatı yanlışdır.",
        "Invalid date or time format.",
        "Неверный формат даты или времени.",
        "Tarih veya saat biçimi hatalı.",
    ),
    _t(
        "Keçmiş gün üçün növbə yazmaq olmaz.",
        "A duty cannot be assigned for a past day.",
        "Нельзя назначить дежурство на прошедший день.",
        "Geçmiş bir gün için görev atanamaz.",
    ),
    _t(
        "Növbəni ən çox %(days)d gün irəli yazmaq olar.",
        "A duty can be scheduled at most %(days)d days ahead.",
        "Дежурство можно назначить не более чем на %(days)d дней вперёд.",
        "Görev en fazla %(days)d gün ileriye atanabilir.",
    ),
    _t(
        "Bitmə saatı başlama saatından sonra olmalıdır.",
        "The end time must be after the start time.",
        "Время окончания должно быть позже времени начала.",
        "Bitiş saati başlangıç saatinden sonra olmalıdır.",
    ),
    _t(
        "Bu vaxt aralığı artıq bitib.",
        "This time range has already ended.",
        "Этот интервал времени уже закончился.",
        "Bu zaman aralığı zaten sona erdi.",
    ),
    _t(
        "Ən azı bir nəzarətçi seçin.",
        "Select at least one invigilator.",
        "Выберите хотя бы одного наблюдателя.",
        "En az bir gözetmen seçin.",
    ),
    _t(
        "Bir növbəyə ən çox %(n)d nəzarətçi təyin etmək olar.",
        "At most %(n)d invigilators can be assigned to one duty.",
        "На одно дежурство можно назначить не более %(n)d наблюдателей.",
        "Bir göreve en fazla %(n)d gözetmen atanabilir.",
    ),
    _t(
        "Seçilənlərdən bəziləri nəzarətçi ola bilməz (tələbə və ya kənar istifadəçi).",
        "Some of the selected people cannot be invigilators (student or outside user).",
        "Некоторые из выбранных не могут быть наблюдателями (студент или посторонний пользователь).",
        "Seçilenlerden bazıları gözetmen olamaz (öğrenci veya dış kullanıcı).",
    ),
    _t(
        "%(count)d nəzarətçi növbəsi yazıldı.",
        "%(count)d invigilator duties assigned.",
        "Назначено дежурств наблюдателей: %(count)d.",
        "%(count)d gözetmen görevi atandı.",
    ),
    _t(
        "Növbə ləğv edildi — nəzarətçinin çıxışı bağlandı.",
        "Duty revoked — the invigilator's access is closed.",
        "Дежурство отменено — доступ наблюдателя закрыт.",
        "Görev iptal edildi — gözetmenin erişimi kapandı.",
    ),
    _t(
        "Növbə artıq ləğv olunub.",
        "The duty is already revoked.",
        "Дежурство уже отменено.",
        "Görev zaten iptal edildi.",
    ),
    _t("Qeyd boşdur.", "The note is empty.", "Заметка пуста.", "Not boş."),
    _t(
        "Çox sayda qeyd — bir az gözləyin.",
        "Too many notes — please wait a moment.",
        "Слишком много заметок — подождите немного.",
        "Çok fazla not — biraz bekleyin.",
    ),
]

_SIGNAL = [
    _t(
        "İmtahan eyni anda iki səhifədə/cihazda açıqdır",
        "The exam is open in two pages/devices at the same time",
        "Экзамен открыт одновременно на двух страницах/устройствах",
        "Sınav aynı anda iki sayfada/cihazda açık",
    ),
    _t(
        "İmtahan zamanı IP ünvanı dəyişdi",
        "The IP address changed during the exam",
        "IP-адрес изменился во время экзамена",
        "Sınav sırasında IP adresi değişti",
    ),
    _t("Nəzarətçi qeydi", "Invigilator note", "Заметка наблюдателя", "Gözetmen notu"),
]

_MONITOR = [
    _t("Nəzarətçi qeydi", "Invigilator note", "Заметка наблюдателя", "Gözetmen notu"),
]

_FIELD = [
    _t("Təşkilat", "Organization", "Организация", "Kurum", msgid="organization"),
    _t("Zal", "Hall", "Зал", "Salon", msgid="room"),
    _t("Nəzarətçi", "Invigilator", "Наблюдатель", "Gözetmen", msgid="user"),
    _t("Başlanğıc", "Starts at", "Начало", "Başlangıç", msgid="starts_at"),
    _t("Son", "Ends at", "Окончание", "Bitiş", msgid="ends_at"),
    _t("Qeyd", "Note", "Примечание", "Not", msgid="note"),
]

_META = [
    _t("Nəzarətçi növbəsi", "Invigilator duty", "Дежурство наблюдателя", "Gözetmen görevi", msgid="singular"),
    _t("Nəzarətçi növbələri", "Invigilator duties", "Дежурства наблюдателей", "Gözetmen görevleri", msgid="plural"),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    DUTY: {row["msgid"]: row for row in _DUTY},
    SIGNAL: {row["msgid"]: row for row in _SIGNAL},
    MONITOR: {row["msgid"]: row for row in _MONITOR},
    FIELD: {row["msgid"]: row for row in _FIELD},
    META: {row["msgid"]: row for row in _META},
}

#: Hazırda məcburi düzəliş yoxdur (yalnız boş/fuzzy girişlər doldurulur).
FORCE: set = set()


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
                flags = ["python-format"] if "%(" in msgid else []
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want, flags=flags))
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
