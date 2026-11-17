#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-18: «Elan statistikası» (kim görüb / oxuyub / görməyib; fakültə, kafedra, ixtisas, qrup, rol).

``django`` kataloquna beş dildə; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_announcement_stats_2026_11_18.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_S = "announcements.stats"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (_S, "Ad Soyad"): ("Full name", "ФИО", "Adı Soyadı", "Name"),
    (_S, "Axtarışa uyğun şəxs tapılmadı"): (
        "No people match the search",
        "По запросу никто не найден",
        "Aramaya uygun kişi bulunamadı",
        "Keine passenden Personen gefunden",
    ),
    (_S, "Bu seçimdə heç kim yoxdur"): (
        "Nobody matches this selection",
        "В этой выборке никого нет",
        "Bu seçimde kimse yok",
        "Niemand entspricht dieser Auswahl",
    ),
    (_S, "Bölgü"): ("Breakdown", "Разбивка", "Dağılım", "Aufschlüsselung"),
    (_S, "Bölmə"): ("Unit", "Подразделение", "Birim", "Einheit"),
    (_S, "Bölmə göstərilməyib"): (
        "No unit specified",
        "Подразделение не указано",
        "Birim belirtilmemiş",
        "Keine Einheit angegeben",
    ),
    (_S, "Bütün bölmələr"): ("All units", "Все подразделения", "Tüm birimler", "Alle Einheiten"),
    (_S, "Bütün rollar"): ("All roles", "Все роли", "Tüm roller", "Alle Rollen"),
    (_S, "Cəmi"): ("Total", "Итого", "Toplam", "Gesamt"),
    (_S, "Elan"): ("Announcement", "Объявление", "Duyuru", "Ankündigung"),
    (_S, "Elan axtar…"): ("Search announcements…", "Поиск объявления…", "Duyuru ara…", "Ankündigung suchen…"),
    (_S, "Elan dərc olunandan sonra burada kimin gördüyü görünəcək."): (
        "Once an announcement is published, you will see here who has seen it.",
        "После публикации объявления здесь будет видно, кто его увидел.",
        "Duyuru yayımlandıktan sonra burada kimin gördüğü görünecek.",
        "Nach der Veröffentlichung sehen Sie hier, wer die Ankündigung gesehen hat.",
    ),
    (_S, "Elan statistikası"): (
        "Announcement statistics",
        "Статистика объявлений",
        "Duyuru istatistikleri",
        "Ankündigungsstatistik",
    ),
    (_S, "Elanı aç"): ("Open announcement", "Открыть объявление", "Duyuruyu aç", "Ankündigung öffnen"),
    (
        _S,
        "Elanı kimin gördüyü, kimin oxuduğu və kimin hələ görmədiyi. " "Rəqəmlər elanın hədəf auditoriyasına görədir.",
    ): (
        "Who has seen the announcement, who has read it and who has not seen it yet. "
        "Figures are relative to the announcement's target audience.",
        "Кто увидел объявление, кто его прочитал и кто ещё не видел. Цифры — относительно целевой аудитории объявления.",
        "Duyuruyu kimin gördüğü, kimin okuduğu ve kimin henüz görmediği. Rakamlar duyurunun hedef kitlesine göredir.",
        "Wer die Ankündigung gesehen, wer sie gelesen und wer sie noch nicht gesehen hat. "
        "Die Zahlen beziehen sich auf die Zielgruppe der Ankündigung.",
    ),
    (_S, "Excel-ə yüklə"): ("Download Excel", "Скачать Excel", "Excel olarak indir", "Als Excel herunterladen"),
    (_S, "Fakültə"): ("Faculty", "Факультет", "Fakülte", "Fakultät"),
    (_S, "Fakültə üzrə"): ("By faculty", "По факультетам", "Fakülteye göre", "Nach Fakultät"),
    (_S, "Fakültə, kafedra, ixtisas və ya qrup…"): (
        "Faculty, department, specialty or group…",
        "Факультет, кафедра, специальность или группа…",
        "Fakülte, bölüm, uzmanlık veya grup…",
        "Fakultät, Lehrstuhl, Fachrichtung oder Gruppe…",
    ),
    (_S, "Görməyib"): ("Not seen", "Не видели", "Görmedi", "Nicht gesehen"),
    (_S, "Görməyib, %"): ("Not seen, %", "Не видели, %", "Görmedi, %", "Nicht gesehen, %"),
    (_S, "Görənlər: %(pct)s%%"): (
        "Seen: %(pct)s%%",
        "Увидели: %(pct)s%%",
        "Görenler: %(pct)s%%",
        "Gesehen: %(pct)s%%",
    ),
    (_S, "Görənlərin payı"): ("Share who saw it", "Доля увидевших", "Görenlerin oranı", "Anteil gesehen"),
    (_S, "Hamı elanı görüb"): (
        "Everyone has seen the announcement",
        "Все увидели объявление",
        "Herkes duyuruyu gördü",
        "Alle haben die Ankündigung gesehen",
    ),
    (_S, "Hədəf"): ("Target", "Цель", "Hedef", "Ziel"),
    (_S, "Hələ dərc olunmuş elan yoxdur"): (
        "No published announcements yet",
        "Пока нет опубликованных объявлений",
        "Henüz yayımlanmış duyuru yok",
        "Noch keine veröffentlichten Ankündigungen",
    ),
    (_S, "Kafedra"): ("Department", "Кафедра", "Bölüm", "Lehrstuhl"),
    (_S, "Kafedra üzrə"): ("By department", "По кафедрам", "Bölüme göre", "Nach Lehrstuhl"),
    (_S, "Kim görüb"): ("Who saw it", "Кто увидел", "Kim gördü", "Wer hat es gesehen"),
    (
        _S,
        "Müəllim və əməkdaşlar ixtisasa və qrupa bağlı deyil — onlar «Bölmə göstərilməyib» sətrindədir.",
    ): (
        "Teachers and staff are not linked to a specialty or group — they are in the «No unit specified» row.",
        "Преподаватели и сотрудники не привязаны к специальности и группе — они в строке «Подразделение не указано».",
        "Öğretim üyeleri ve çalışanlar uzmanlığa ve gruba bağlı değildir — «Birim belirtilmemiş» satırındadırlar.",
        "Lehrende und Mitarbeitende sind keiner Fachrichtung oder Gruppe zugeordnet — "
        "sie stehen in der Zeile «Keine Einheit angegeben».",
    ),
    (_S, "Oxuyub"): ("Read", "Прочитали", "Okudu", "Gelesen"),
    (_S, "Oxuyub, %"): ("Read, %", "Прочитали, %", "Okudu, %", "Gelesen, %"),
    (_S, "Oxuyub: %(day)s"): ("Read: %(day)s", "Прочитал(а): %(day)s", "Okudu: %(day)s", "Gelesen: %(day)s"),
    (_S, "Popup görüb"): ("Saw pop-up", "Видели всплывающее окно", "Açılır pencereyi gördü", "Pop-up gesehen"),
    (_S, "Popup görüb, %"): (
        "Saw pop-up, %",
        "Видели всплывающее окно, %",
        "Açılır pencereyi gördü, %",
        "Pop-up gesehen, %",
    ),
    (_S, "Popup: %(day)s"): (
        "Pop-up: %(day)s",
        "Всплывающее окно: %(day)s",
        "Açılır pencere: %(day)s",
        "Pop-up: %(day)s",
    ),
    (_S, "Qrup"): ("Group", "Группа", "Grup", "Gruppe"),
    (_S, "Qrup üzrə"): ("By group", "По группам", "Gruba göre", "Nach Gruppe"),
    (_S, "Rol"): ("Role", "Роль", "Kullanıcı rolü", "Rolle"),
    (_S, "Rol üzrə"): ("By role", "По ролям", "Role göre", "Nach Rolle"),
    (_S, "Siyahı yüklənir…"): ("Loading the list…", "Загрузка списка…", "Liste yükleniyor…", "Liste wird geladen…"),
    (_S, "Statistika filtrləri"): (
        "Statistics filters",
        "Фильтры статистики",
        "İstatistik filtreleri",
        "Statistikfilter",
    ),
    (_S, "Statistika hesablanır…"): (
        "Calculating statistics…",
        "Подсчёт статистики…",
        "İstatistikler hesaplanıyor…",
        "Statistik wird berechnet…",
    ),
    (_S, "Statistikanı yükləmək alınmadı. Bir az sonra yenidən cəhd edin."): (
        "Could not load the statistics. Please try again a little later.",
        "Не удалось загрузить статистику. Попробуйте чуть позже.",
        "İstatistikler yüklenemedi. Biraz sonra tekrar deneyin.",
        "Die Statistik konnte nicht geladen werden. Bitte versuchen Sie es etwas später erneut.",
    ),
    (_S, "Səlahiyyət yoxdur."): ("Access denied.", "Нет доступа.", "Yetki yok.", "Keine Berechtigung."),
    (
        _S,
        "Tələbələr kafedraya bağlı deyil — onlar «Bölmə göstərilməyib» sətrindədir. "
        "Tələbələr üçün fakültə, ixtisas və ya qrup bölgüsünə baxın.",
    ): (
        "Students are not linked to a department — they are in the «No unit specified» row. "
        "For students, use the faculty, specialty or group breakdown.",
        "Студенты не привязаны к кафедре — они в строке «Подразделение не указано». "
        "Для студентов смотрите разбивку по факультетам, специальностям или группам.",
        "Öğrenciler bölüme bağlı değildir — «Birim belirtilmemiş» satırındadırlar. "
        "Öğrenciler için fakülte, uzmanlık veya grup dağılımına bakın.",
        "Studierende sind keinem Lehrstuhl zugeordnet — sie stehen in der Zeile «Keine Einheit angegeben». "
        "Für Studierende nutzen Sie die Aufschlüsselung nach Fakultät, Fachrichtung oder Gruppe.",
    ),
    (_S, "Təsdiq edib"): ("Confirmed", "Подтвердили", "Onayladı", "Bestätigt"),
    (_S, "Uyğun bölmə yoxdur"): (
        "No matching unit",
        "Подходящих подразделений нет",
        "Uygun birim yok",
        "Keine passende Einheit",
    ),
    (_S, "Vəziyyət"): ("Status", "Статус", "Durum", "Status"),
    (_S, "«%(title)s» elanının statistikası"): (
        "Statistics for «%(title)s»",
        "Статистика объявления «%(title)s»",
        "«%(title)s» duyurusunun istatistikleri",
        "Statistik zu «%(title)s»",
    ),
    (_S, "«Görənlərin payı» — popup-u görən və ya elanı açıb oxuyanlar."): (
        "«Share who saw it» — people who saw the pop-up or opened and read the announcement.",
        "«Доля увидевших» — те, кто увидел всплывающее окно или открыл и прочитал объявление.",
        "«Görenlerin oranı» — açılır pencereyi gören veya duyuruyu açıp okuyanlar.",
        "«Anteil gesehen» — wer das Pop-up gesehen oder die Ankündigung geöffnet und gelesen hat.",
    ),
    (_S, "İstifadəçi adı"): ("Username", "Имя пользователя", "Kullanıcı adı", "Benutzername"),
    (_S, "İxtisas"): ("Specialty", "Специальность", "Uzmanlık", "Fachrichtung"),
    (_S, "İxtisas üzrə"): ("By specialty", "По специальностям", "Uzmanlığa göre", "Nach Fachrichtung"),
    (_S, "Şəxs filtrləri"): ("People filters", "Фильтры людей", "Kişi filtreleri", "Personenfilter"),
    (_S, "Şəxslər"): ("People", "Люди", "Kişiler", "Personen"),
    (_S, "Şəxslərdə axtar"): ("Search people", "Поиск людей", "Kişilerde ara", "Personen suchen"),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt or "", e.msgid) for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            entry = polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=msgstr)
            if "%(" in msgid or "%%" in msgid:
                entry.flags.append("python-format")
            po.append(entry)
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"django/{lang}: +{added}")


if __name__ == "__main__":
    main()
