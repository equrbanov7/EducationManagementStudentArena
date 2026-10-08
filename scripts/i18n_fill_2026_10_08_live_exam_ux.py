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
        # L1 — lobbi siyahısı sürüşür.
        "Hamısını görmək üçün siyahını sürüşdürün": (
            "Scroll the list to see everyone",
            "Прокрутите список, чтобы увидеть всех",
            "Herkesi görmek için listeyi kaydırın",
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
        "Çox sayda cəhd edildi. Zəhmət olmasa bir az sonra yenidən cəhd edin.": (
            "Too many attempts. Please try again a little later.",
            "Слишком много попыток. Пожалуйста, повторите чуть позже.",
            "Çok fazla deneme yapıldı. Lütfen biraz sonra tekrar deneyin.",
        ),
        "Çox sayda sorğu göndərildi. Zəhmət olmasa bir az sonra yenidən cəhd edin.": (
            "Too many requests. Please try again a little later.",
            "Слишком много запросов. Пожалуйста, повторите чуть позже.",
            "Çok fazla istek gönderildi. Lütfen biraz sonra tekrar deneyin.",
        ),
        "Oyun artıq başlayıb və müəllim gecikənlərin qoşulmasını bağlayıb.": (
            "The game has already started and the teacher has turned off joining late.",
            "Игра уже началась, и преподаватель отключил вход для опоздавших.",
            "Oyun zaten başladı ve öğretmen geç katılımı kapattı.",
        ),
    },
    "live_exam.pin_entry": {
        "Canlı imtahana qoşul": ("Join a live exam", "Присоединитесь к живому экзамену", "Canlı sınava katıl"),
        "Canlı": ("Live", "Прямой эфир", "Canlı oyun"),
        "Müəllimin göstərdiyi PIN-i yaz, sonra adını seçib oyuna daxil ol.": (
            "Enter the PIN shown by the teacher, then choose your name and join the game.",
            "Введите PIN, который показал преподаватель, затем выберите имя и войдите в игру.",
            "Öğretmenin gösterdiği PIN kodunu gir, sonra adını seçip oyuna katıl.",
        ),
        "Oyun PIN-i": ("Game PIN", "PIN игры", "Oyun PIN'i"),
        "Məsələn: 3A8K2B94F1": ("Example: 3A8K2B94F1", "Например: 3A8K2B94F1", "Örnek: 3A8K2B94F1"),
        "Davam et": ("Continue", "Продолжить", "Devam et"),
        "PIN-i ekranda gördüyün kimi daxil et. Növbəti addımda ad və avatar seçəcəksən.": (
            "Type the PIN exactly as shown on screen. You will choose your nickname and avatar next.",
            "Введите PIN точно как на экране. На следующем шаге вы выберете ник и аватар.",
            "PIN kodunu ekrandaki gibi gir. Sonraki adımda rumuz ve avatar seçeceksin.",
        ),
        "Saniyələr içində qoşul": ("Join in seconds", "Подключение за несколько секунд", "Saniyeler içinde katıl"),
        "Telefon, planşet və kompüterdən işləyir": (
            "Works on phone, tablet, and desktop",
            "Работает на телефоне, планшете и компьютере",
            "Telefon, tablet ve bilgisayarda çalışır",
        ),
        "Canlı nəticə və liderlik cədvəli": (
            "Live results and leaderboard",
            "Живые результаты и таблица лидеров",
            "Canlı sonuç ve lider tablosu",
        ),
        "Hazırsan?": ("Ready to play?", "Готовы?", "Hazır mısın?"),
        "Bir URL, bir PIN, hamısı eyni oyunda.": (
            "One link, one PIN, everyone in the same session.",
            "Одна ссылка, один PIN, одна общая сессия.",
            "Tek link, tek PIN, herkes aynı oturumda.",
        ),
        "Müəllim ekranında PIN və QR kod görünür.": (
            "The teacher screen shows the PIN and QR code.",
            "На экране преподавателя видны PIN и QR-код.",
            "Öğretmen ekranında PIN ve QR kod görünür.",
        ),
        "Daxil olduqdan sonra avatar və ad seçimi gəlir.": (
            "After this step, students choose nickname and avatar.",
            "После этого шага ученик выбирает ник и аватар.",
            "Bu adımdan sonra öğrenci ad ve avatar seçer.",
        ),
        "Yoxlanılır...": ("Checking...", "Проверяем...", "Kontrol ediliyor..."),
        "Düzgün PIN daxil et.": ("Enter a valid PIN.", "Введите действительный PIN.", "Geçerli bir PIN gir."),
        "Bu PIN tapılmadı və ya oyun bağlanıb.": (
            "This PIN was not found or the session is closed.",
            "Такой PIN не найден или сессия уже закрыта.",
            "Bu PIN bulunamadı veya oturum kapanmış.",
        ),
    },
    "live_exam.join": {
        "Əvvəlki qoşulma tapıldı": ("Previous join found", "Найдено предыдущее подключение", "Önceki katılım bulundu"),
        "{nickname} adı ilə bu oyuna artıq daxil olmusan.": (
            "You already joined this game as {nickname}.",
            "Вы уже вошли в эту игру как {nickname}.",
            "Bu oyuna zaten {nickname} adıyla katıldın.",
        ),
        "İstəsən həmin oyunçu ilə davam et, istəsən yeni ad və avatarla yenidən qoşul.": (
            "Continue with that player or join again with a new nickname and avatar.",
            "Можно продолжить с этим игроком или войти заново с новым именем и аватаром.",
            "İstersen aynı oyuncuyla devam et, istersen yeni rumuz ve avatarla tekrar katıl.",
        ),
        "{nickname} kimi davam et": (
            "Continue as {nickname}",
            "Продолжить как {nickname}",
            "{nickname} olarak devam et",
        ),
        "Əvvəlki adla davam etmək istəyirsən?": (
            "Continue with your previous name?",
            "Продолжить с прежним именем?",
            "Önceki adınla devam etmek ister misin?",
        ),
        "Bu PIN üçün aktiv oyunçu profilin var. Həmin profil ilə gözləmə otağına qayıda və ya yeni ad/avatar seçib yenidən daxil ola bilərsən.": (
            "You already have an active player profile for this PIN. You can jump back into the waiting room or join again with a new nickname and avatar.",
            "Для этого PIN уже есть активный профиль игрока. Вы можете вернуться в комнату ожидания или войти заново с новым именем и аватаром.",
            "Bu PIN için aktif bir oyuncu profilin var. Bekleme odasına geri dönebilir ya da yeni rumuz ve avatarla yeniden katılabilirsin.",
        ),
        "Yenidən daxil ol": ("Join again", "Войти заново", "Yeniden katıl"),
        "Bağla": ("Close", "Закрыть", "Kapat"),
        "Bu ad artıq istifadə olunur. Başqa ad seç.": (
            "This nickname is already in use. Choose another one.",
            "Этот ник уже используется. Выберите другой.",
            "Bu rumuz zaten kullanılıyor. Başka bir ad seç.",
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
