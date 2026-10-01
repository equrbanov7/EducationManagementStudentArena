#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-01 imtahan zalı bayrağı (sahib: «İmtahan zalları yerində bütün otaqlar görünür»).

Əlavə olunan mətnlər:
  * `exams.final_center.halls` — İmtahan Nəzarət Sistemi → zallar (korpus qrupları, «Göstər»
    süzgəci, plitələr, «İmtahan zalı kimi qeyd et» / «İmtahan zallarından çıxar» düyməsi,
    təsdiq/rədd mesajları), AJAX endpoint cavabları, kabinet bölməsinin nişan/dialoq mətnləri;
  * `accounts.superadmin_exam_rooms` — kabinet «İmtahan zalları» bölməsinin süzgəci, KPI, boş vəziyyət;
  * `exams.model.exam_room.field` / `.help` — `ExamRoom.is_exam_hall` sahəsinin adı və izahı.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_halls_2026_10_01.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

HL = "exams.final_center.halls"
SAR = "accounts.superadmin_exam_rooms"


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


_SHOW = _t("Göstər", "Show", "Показать", "Göster")
_ONLY_HALLS = _t("Yalnız imtahan zalları", "Exam halls only", "Только экзаменационные залы", "Yalnızca sınav salonları")
_ALL_ROOMS = _t("Hamısı (bütün otaqlar)", "All (every room)", "Все (все аудитории)", "Tümü (tüm odalar)")
_HALL = _t("İmtahan zalı", "Exam hall", "Экзаменационный зал", "Sınav salonu")
_NO_BUILDING = _t("Korpus göstərilməyib", "No building set", "Корпус не указан", "Bina belirtilmemiş")

_HALLS = [
    # ── Xidmət qatı (rədd / təsdiq) ─────────────────────────────────────────
    _t(
        "«%(room)s» zalında hazırda imtahan gedir — oturum bitənə qədər zalı imtahan zallarından çıxarmaq olmaz.",
        "An exam is running in “%(room)s” right now — it cannot be removed from the exam halls until the "
        "session ends.",
        "В зале «%(room)s» сейчас идёт экзамен — до окончания сеанса его нельзя исключить из экзаменационных "
        "залов.",
        "«%(room)s» salonunda şu anda sınav yapılıyor — oturum bitene kadar salon sınav salonlarından "
        "çıkarılamaz.",
    ),
    _t(
        "«%(room)s» zalında %(n)d aktiv kompüter qeydiyyatdadır — onlardan final imtahanına giriş mümkündür. "
        "Əvvəlcə kompüterləri deaktiv edin və ya silin (zal idarəetməsi).",
        "“%(room)s” has %(n)d active registered computers — they can still be used to enter final exams. "
        "Deactivate or delete the computers first (hall management).",
        "В зале «%(room)s» зарегистрировано активных компьютеров: %(n)d — с них возможен вход на итоговый "
        "экзамен. Сначала деактивируйте или удалите компьютеры (управление залами).",
        "«%(room)s» salonunda %(n)d etkin kayıtlı bilgisayar var — bunlardan final sınavına giriş mümkündür. "
        "Önce bilgisayarları devre dışı bırakın veya silin (salon yönetimi).",
    ),
    _t(
        "«%(room)s» zalında %(n)d planlaşdırılmış oturum var. Zal imtahan zallarından çıxarılsın? Oturumlar "
        "silinmir, zal monitoru onlar üçün açıq qalır.",
        "“%(room)s” has %(n)d scheduled sessions. Remove it from the exam halls? The sessions are not deleted "
        "and the hall monitor stays available for them.",
        "В зале «%(room)s» запланировано сеансов: %(n)d. Исключить его из экзаменационных залов? Сеансы не "
        "удаляются, монитор зала для них остаётся доступным.",
        "«%(room)s» salonunda %(n)d planlanmış oturum var. Salon sınav salonlarından çıkarılsın mı? Oturumlar "
        "silinmez, salon monitörü onlar için açık kalır.",
    ),
    # ── AJAX endpoint ──────────────────────────────────────────────────────
    _t(
        "İmtahan zallarını yalnız zal idarəçiləri dəyişə bilər.",
        "Only hall managers can change exam halls.",
        "Изменять экзаменационные залы могут только управляющие залами.",
        "Sınav salonlarını yalnızca salon yöneticileri değiştirebilir.",
    ),
    _t("Otaq tapılmadı.", "Room not found.", "Аудитория не найдена.", "Oda bulunamadı."),
    _t(
        "Sorğu natamamdır: is_exam_hall göstərilməyib.",
        "Incomplete request: is_exam_hall is missing.",
        "Неполный запрос: не указан is_exam_hall.",
        "Eksik istek: is_exam_hall belirtilmemiş.",
    ),
    _t(
        "«%(room)s» imtahan zalı kimi qeyd edildi.",
        "“%(room)s” marked as an exam hall.",
        "«%(room)s» отмечен как экзаменационный зал.",
        "«%(room)s» sınav salonu olarak işaretlendi.",
    ),
    _t(
        "«%(room)s» imtahan zallarından çıxarıldı.",
        "“%(room)s” removed from the exam halls.",
        "«%(room)s» исключён из экзаменационных залов.",
        "«%(room)s» sınav salonlarından çıkarıldı.",
    ),
    # ── Şablonlar ──────────────────────────────────────────────────────────
    _NO_BUILDING,
    _t(
        "İmtahan zalı kimi qeyd et",
        "Mark as exam hall",
        "Отметить как экзаменационный зал",
        "Sınav salonu olarak işaretle",
    ),
    _t(
        "İmtahan zallarından çıxar",
        "Remove from exam halls",
        "Исключить из экзаменационных залов",
        "Sınav salonlarından çıkar",
    ),
    _t(
        "Zal imtahan zallarından çıxarılsın?",
        "Remove the hall from the exam halls?",
        "Исключить зал из экзаменационных?",
        "Salon sınav salonlarından çıkarılsın mı?",
    ),
    _t("Bəli, çıxar", "Yes, remove", "Да, исключить", "Evet, çıkar"),
    _t(
        "Əməliyyat alınmadı. Səhifəni yeniləyib yenidən cəhd edin.",
        "The action failed. Refresh the page and try again.",
        "Не удалось выполнить действие. Обновите страницу и попробуйте снова.",
        "İşlem başarısız oldu. Sayfayı yenileyip tekrar deneyin.",
    ),
    _HALL,
    _t("Adi otaq", "Regular room", "Обычная аудитория", "Normal oda"),
    _t("Mərtəbə", "Floor", "Этаж", "Kat"),
    _t("Otaq", "Rooms", "Аудиторий", "Oda"),
    _t("cəmi otaq: %(n)s", "rooms in total: %(n)s", "всего аудиторий: %(n)s", "toplam oda: %(n)s"),
    _SHOW,
    _ONLY_HALLS,
    _ALL_ROOMS,
    _t("Korpus", "Building", "Корпус", "Bina"),
    _t("Bütün korpuslar", "All buildings", "Все корпуса", "Tüm binalar"),
    _t(
        "Bütün otaqlar korpuslar üzrə — otağı bir kliklə imtahan zalı kimi qeyd edin və ya zallardan çıxarın",
        "All rooms by building — mark a room as an exam hall or remove it with one click",
        "Все аудитории по корпусам — отметьте аудиторию как экзаменационный зал или исключите её одним кликом",
        "Binalara göre tüm odalar — bir tıkla odayı sınav salonu olarak işaretleyin veya salonlardan çıkarın",
    ),
    _t(
        "Hələ imtahan zalı qeyd olunmayıb.",
        "No exam halls have been marked yet.",
        "Экзаменационные залы ещё не отмечены.",
        "Henüz sınav salonu işaretlenmedi.",
    ),
    _t(
        "«Hamısı» görünüşündə otağı imtahan zalı kimi qeyd edin.",
        "Switch to “All” and mark a room as an exam hall.",
        "Перейдите в режим «Все» и отметьте аудиторию как экзаменационный зал.",
        "«Tümü» görünümünde odayı sınav salonu olarak işaretleyin.",
    ),
    _t("Bütün otaqları göstər", "Show all rooms", "Показать все аудитории", "Tüm odaları göster"),
    _t(
        "İmtahan zalı (imtahan mərkəzinin zal siyahısında görünür)",
        "Exam hall (appears in the exam centre's hall list)",
        "Экзаменационный зал (отображается в списке залов экзаменационного центра)",
        "Sınav salonu (sınav merkezinin salon listesinde görünür)",
    ),
    _t(
        "Bu otaq imtahan zalı deyil — kompüter qeydiyyatı yalnız imtahan zalları üçündür. Əvvəlcə cədvəldə "
        "«İmtahan zalı kimi qeyd et» düyməsini vurun.",
        "This room is not an exam hall — computers can be registered only in exam halls. First press "
        "“Mark as exam hall” in the table.",
        "Эта аудитория не является экзаменационным залом — регистрировать компьютеры можно только в "
        "экзаменационных залах. Сначала нажмите «Отметить как экзаменационный зал» в таблице.",
        "Bu oda sınav salonu değil — bilgisayar kaydı yalnızca sınav salonları içindir. Önce tabloda "
        "«Sınav salonu olarak işaretle» düğmesine basın.",
    ),
]

_SAR = [
    _t(
        "Hələ imtahan zalı qeyd olunmayıb",
        "No exam halls have been marked yet",
        "Экзаменационные залы ещё не отмечены",
        "Henüz sınav salonu işaretlenmedi",
    ),
    _t(
        "«Göstər: Hamısı» seçin və otağı «İmtahan zalı kimi qeyd et» düyməsi ilə zala çevirin.",
        "Choose “Show: All” and turn a room into a hall with the “Mark as exam hall” button.",
        "Выберите «Показать: Все» и превратите аудиторию в зал кнопкой «Отметить как экзаменационный зал».",
        "«Göster: Tümü» seçin ve «Sınav salonu olarak işaretle» düğmesiyle odayı salona dönüştürün.",
    ),
    _NO_BUILDING,
    _SHOW,
    _ONLY_HALLS,
    _ALL_ROOMS,
    _HALL,
    _t("cəmi otaq: %(n)d", "rooms in total: %(n)d", "всего аудиторий: %(n)d", "toplam oda: %(n)d"),
]

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    HL: {row["az"]: row for row in _HALLS},
    SAR: {row["az"]: row for row in _SAR},
    "exams.model.exam_room.field": {
        "is_exam_hall": _t("İmtahan zalı", "Exam hall", "Экзаменационный зал", "Sınav salonu"),
    },
    "exams.model.exam_room.help": {
        "is_exam_hall": _t(
            "İşarələnmiş otaqlar imtahan mərkəzinin zal siyahısında görünür; digər otaqlar yalnız otaq "
            "reyestrindədir (jurnal, cədvəl).",
            "Marked rooms appear in the exam centre's hall list; other rooms stay only in the room registry "
            "(journal, timetable).",
            "Отмеченные аудитории отображаются в списке залов экзаменационного центра; остальные остаются "
            "только в реестре аудиторий (журнал, расписание).",
            "İşaretli odalar sınav merkezinin salon listesinde görünür; diğer odalar yalnızca oda kaydında "
            "kalır (yoklama defteri, ders programı).",
        ),
    },
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
                entry = polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want)
                if "%(" in msgid:
                    entry.flags.append("python-format")
                po.append(entry)
                index[(ctx, msgid)] = entry
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
