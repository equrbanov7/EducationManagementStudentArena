#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-08: canlı imtahan UX (müəllimin 22 nəfərlik real sessiyası).

Yeni mətnlər (AZ mənbə = msgid; en/ru/tr tərcümələr):

* L1 — lobbi siyahısı: sürüşdürmə ipucu, iştirakçı sayı;
* L2 — «Hər sual üçün vaxt» seçicisi (lobbi + idarə paneli), xəta mesajı;
* L3 — «Gecikənlər qoşula bilsin» ayarı, gec qoşulanın «növbəti sual gözlənilir» ekranı;
* L4/L5 — plitələr / yan panel (ekran oxuyucu mətnləri);
* L6 — oyun gedərkən iştirakçını çıxarmaq: siyahı çekməcəsi, təsdiq dialoqu, «çıxarıldı»;
* qoşulma / oyun səhifələrində əvvəl dil lüğətləri ilə (və ya sərt kodlanmış AZ) verilən mətnlər —
  indi gettext + pgettext kontekstləri ilə.

Kontekstlər: `live_exam.host_controls`, `live_exam.host_settings`, `live_exam.view.message`,
`live_exam.join`, `live_exam.join.js`, `live_exam.player`, `live_exam.pin_entry`, `liveExam.template.session_detail`.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları `msgfmt` ilə yenidən qurulur.
Locale birləşmə konflikti olarsa qayda: «ours» götür, sonra fill skriptlərini yenidən işlət.
İstifadə:  python scripts/i18n_fill_2026_10_08_live_exam_ux.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

# (kontekst, az) → (en, ru, tr)
ROWS = {
    "live_exam.host_controls": {
        "Hər sual üçün vaxt": ("Time per question", "Время на вопрос", "Soru başına süre"),
        "Standart · {seconds} san": (
            "Default · {seconds} s",
            "По умолчанию · {seconds} с",
            "Varsayılan · {seconds} sn",
        ),
        "{seconds} san": ("{seconds} s", "{seconds} с", "{seconds} sn"),
        "Digər ({min}–{max} san)": ("Custom ({min}–{max} s)", "Другое ({min}–{max} с)", "Özel ({min}–{max} sn)"),
        "Tətbiq et": ("Apply", "Применить", "Uygula"),
        "Dəyişiklik növbəti sualdan tətbiq olunur.": (
            "The change applies from the next question.",
            "Изменение вступит в силу со следующего вопроса.",
            "Değişiklik bir sonraki sorudan itibaren uygulanır.",
        ),
        "Hər sual bu qədər vaxt gedəcək.": (
            "Every question will run for this long.",
            "Каждый вопрос будет длиться столько.",
            "Her soru bu kadar sürecek.",
        ),
        "Standart: sualın öz vaxtı, yoxdursa imtahanın vaxtı.": (
            "Default: the question's own time, otherwise the exam's time.",
            "По умолчанию: время самого вопроса, иначе время экзамена.",
            "Varsayılan: sorunun kendi süresi, yoksa sınavın süresi.",
        ),
        "{min}–{max} saniyə arası rəqəm yazın": (
            "Enter a number between {min} and {max} seconds",
            "Введите число от {min} до {max} секунд",
            "{min}–{max} saniye arasında bir sayı girin",
        ),
        "Vaxt saxlanmadı. Yenidən cəhd edin.": (
            "The time was not saved. Please try again.",
            "Время не сохранено. Попробуйте ещё раз.",
            "Süre kaydedilmedi. Lütfen tekrar deneyin.",
        ),
        "Hər sual üçün vaxt: {value}": (
            "Time per question: {value}",
            "Время на вопрос: {value}",
            "Soru başına süre: {value}",
        ),
        "Gecikənlər bu PIN ilə qoşula bilər": (
            "Latecomers can join with this PIN",
            "Опоздавшие могут присоединиться с этим PIN",
            "Geç kalanlar bu PIN ile katılabilir",
        ),
        # L6 — «İştirakçılar» çekməcəsi və çıxarma təsdiqi.
        "Oyun idarəsi": ("Game control", "Управление игрой", "Oyun yönetimi"),
        "İştirakçılar": ("Players", "Участники", "Katılımcılar"),
        "Bağla": ("Close", "Закрыть", "Kapat"),
        "Ad üzrə axtar…": ("Search by name…", "Поиск по имени…", "Ada göre ara…"),
        "Çıxarılan iştirakçı bu oyuna həmin cihazla qayıda bilməz, balı liderlər lövhəsində göstərilmir; "
        "nəticədə «Çıxarıldı» kimi qalır.": (
            "A removed player cannot return to this game on the same device and their score is hidden from "
            "the leaderboard; the results keep them as “Removed”.",
            "Удалённый участник не сможет вернуться в эту игру с того же устройства, его баллы не показываются "
            "в таблице лидеров; в результатах он остаётся как «Удалён».",
            "Çıkarılan katılımcı bu oyuna aynı cihazla dönemez, puanı liderlik tablosunda gösterilmez; "
            "sonuçlarda “Çıkarıldı” olarak kalır.",
        ),
        "Ləğv et": ("Cancel", "Отмена", "İptal"),
        "Çıxar": ("Remove", "Удалить", "Çıkar"),
        "Növbəti sualdan": ("From next question", "Со следующего вопроса", "Sonraki sorudan"),
        "Uyğun iştirakçı yoxdur": ("No matching players", "Нет подходящих участников", "Eşleşen katılımcı yok"),
        "Hələ heç kim qoşulmayıb": ("No one has joined yet", "Пока никто не присоединился", "Henüz kimse katılmadı"),
        "«{name}» oyundan çıxarılsın?": (
            "Remove “{name}” from the game?",
            "Удалить «{name}» из игры?",
            "“{name}” oyundan çıkarılsın mı?",
        ),
        "Telefonu oyundan çıxacaq, bu cihazla geri qayıda bilməyəcək. Balı liderlər lövhəsində göstərilməyəcək.": (
            "Their phone will leave the game and cannot come back on this device. "
            "Their score will not be shown on the leaderboard.",
            "Телефон выйдет из игры и не сможет вернуться с этого устройства. "
            "Баллы не будут показаны в таблице лидеров.",
            "Telefonu oyundan çıkacak ve bu cihazla geri dönemeyecek. Puanı liderlik tablosunda gösterilmeyecek.",
        ),
        "Telefonu lobbidən çıxacaq və bu cihazla geri qayıda bilməyəcək.": (
            "Their phone will leave the lobby and cannot come back on this device.",
            "Телефон выйдет из лобби и не сможет вернуться с этого устройства.",
            "Telefonu lobiden çıkacak ve bu cihazla geri dönemeyecek.",
        ),
        "«{name}» oyundan çıxarıldı": (
            "“{name}” was removed from the game",
            "«{name}» удалён из игры",
            "“{name}” oyundan çıkarıldı",
        ),
        "Çıxarmaq alınmadı. Yenidən cəhd edin.": (
            "Could not remove the player. Please try again.",
            "Не удалось удалить участника. Попробуйте ещё раз.",
            "Çıkarılamadı. Lütfen tekrar deneyin.",
        ),
    },
    "liveExam.template.session_detail": {
        "Çıxarıldı": ("Removed", "Удалён", "Çıkarıldı"),
    },
    "live_exam.view.message": {
        "İştirakçını oyun bitənə qədər çıxarmaq olar.": (
            "A player can only be removed before the game ends.",
            "Участника можно удалить только до окончания игры.",
            "Katılımcı yalnızca oyun bitmeden çıkarılabilir.",
        ),
        "İştirakçı tapılmadı.": ("Player not found.", "Участник не найден.", "Katılımcı bulunamadı."),
        "Oyun artıq başlayıb və müəllim gecikənlərin qoşulmasını bağlayıb.": (
            "The game has already started and the teacher has turned off joining late.",
            "Игра уже началась, и преподаватель отключил вход для опоздавших.",
            "Oyun zaten başladı ve öğretmen geç katılımı kapattı.",
        ),
    },
    "live_exam.consumer.error": {
        "Növbəti sual başlayanda oyuna qoşulacaqsan.": (
            "You will join the game when the next question starts.",
            "Вы присоединитесь к игре, когда начнётся следующий вопрос.",
            "Bir sonraki soru başladığında oyuna katılacaksın.",
        ),
    },
    "live_exam.player": {
        "Oyuna qoşuldun!": ("You're in!", "Вы в игре!", "Oyuna katıldın!"),
        "Oyun artıq gedir — növbəti sual başlayanda daxil olacaqsan. Keçən suallar üçün bal verilmir.": (
            "The game is already running — you will enter when the next question starts. "
            "Missed questions give no points.",
            "Игра уже идёт — вы войдёте, когда начнётся следующий вопрос. "
            "За пропущенные вопросы баллы не начисляются.",
            "Oyun zaten sürüyor — bir sonraki soru başladığında gireceksin. Kaçırılan sorulara puan verilmez.",
        ),
    },
    "live_exam.host_settings": {
        "Sual vaxtı 5–300 saniyə olmalıdır.": (
            "The question time must be 5–300 seconds.",
            "Время вопроса должно быть от 5 до 300 секунд.",
            "Soru süresi 5–300 saniye olmalıdır.",
        ),
        "Gecikənlər qoşula bilsin": ("Allow late joining", "Разрешить вход опоздавшим", "Geç katılıma izin ver"),
        "Tövsiyə olunur": ("Recommended", "Рекомендуется", "Önerilir"),
        "Oyun başlayandan sonra gələn tələbə növbəti sualdan qoşulur: keçən suallara bal almır və onların "
        "cavablarını görmür. Kilidli lobbi, iştirakçı limiti və çıxarılanlar qaydası qüvvədədir.": (
            "A student who arrives after the start joins from the next question: no points for missed questions "
            "and their answers are not shown. Locked lobby, participant limit and removals still apply.",
            "Студент, пришедший после начала, присоединяется со следующего вопроса: за пропущенные вопросы "
            "баллов нет, их ответы не показываются. Закрытое лобби, лимит участников и удаления действуют.",
            "Oyun başladıktan sonra gelen öğrenci bir sonraki sorudan katılır: kaçırılan sorulara puan almaz ve "
            "cevaplarını görmez. Kilitli lobi, katılımcı sınırı ve çıkarılanlar kuralı geçerlidir.",
        ),
    },
}

#: Bu skriptin öz kontekstləri — dəyər həmişə buradakı ilə sinxronlanır (identity düzəlişləri).
FORCE = {"live_exam.host_controls"}


def _value(lang, az, row):
    return az if lang == "az" else row[LANGS.index(lang) - 1]


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ROWS.items():
        for msgid, row in items.items():
            want = _value(lang, msgid, row)
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=want))
                added += 1
            elif entry.msgstr != want and (
                not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete or ctx in FORCE
            ):
                entry.msgstr, entry.obsolete = want, False
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
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
