#!/usr/bin/env python3
"""EMSArena i18n — «Bölmə imtahanları» (unit-exams) redizaynı, 2026-10-14.

Kontekst: `accounts.unit_exams` (KPI, filtr paneli, cədvəl, «İmtahan haqqında» çekmecəsi,
«əhatə yoxdur» / «imtahan yoxdur» vəziyyətləri).

msgid AZ cümlədir → az msgstr = msgid. `%(x)s` / `{x}` yer tutucuları tərcümədə saxlanılır.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_unitexams_2026_10_14.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]
CTX = "accounts.unit_exams"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


# msgid → {lang: msgstr}
ENTRIES = {
    # Vəziyyətlər / status
    "Aktiv": t("Active", "Активен", "Aktif", "Läuft"),
    "Planlaşdırılıb": t("Scheduled", "Запланирован", "Planlandı", "Geplant"),
    "Bitib": t("Finished", "Завершён", "Bitti", "Beendet"),
    "Qaralama": t("Draft", "Черновик", "Taslak", "Entwurf"),
    # KPI
    "İMTAHAN": t("EXAMS", "ЭКЗАМЕНЫ", "SINAVLAR", "PRÜFUNGEN"),
    "Bölmədə cəmi": t(
        "Total in your unit", "Всего в подразделении", "Biriminizde toplam", "Insgesamt in Ihrer Einheit"
    ),
    "AKTİV": t("ACTIVE", "АКТИВНЫЕ", "AKTİF", "LAUFEND"),
    "Planlaşdırılıb: %(n)d": t("Scheduled: %(n)d", "Запланировано: %(n)d", "Planlanan: %(n)d", "Geplant: %(n)d"),
    "BİTMİŞ": t("FINISHED", "ЗАВЕРШЁННЫЕ", "TAMAMLANAN", "BEENDET"),
    "Qaralama: %(n)d": t("Drafts: %(n)d", "Черновики: %(n)d", "Taslaklar: %(n)d", "Entwürfe: %(n)d"),
    "FİNAL / MİDTERM": t("FINAL / MIDTERM", "ИТОГОВЫЕ / ПРОМЕЖУТОЧНЫЕ", "FİNAL / VİZE", "ABSCHLUSS / ZWISCHEN"),
    "İmtahan növünə görə": t("By exam kind", "По виду экзамена", "Sınav türüne göre", "Nach Prüfungsart"),
    "İŞTİRAKÇI": t("PARTICIPANTS", "УЧАСТНИКИ", "KATILIMCILAR", "TEILNEHMENDE"),
    "Orta nəticə: %(avg)s": t(
        "Average result: %(avg)s", "Средний результат: %(avg)s", "Ortalama sonuç: %(avg)s", "Durchschnitt: %(avg)s"
    ),
    "Orta nəticə hələ yoxdur": t(
        "No average result yet", "Среднего результата пока нет", "Henüz ortalama sonuç yok", "Noch kein Durchschnitt"
    ),
    # Filtr paneli
    "Hamısı": t("All", "Все", "Tümü", "Alle"),
    "Axtarış": t("Search", "Поиск", "Arama", "Suche"),
    "İmtahan, fənn və ya müəllif": t(
        "Exam, subject or author", "Экзамен, предмет или автор", "Sınav, ders veya yazar", "Prüfung, Fach oder Autor"
    ),
    "Kafedra": t("Department", "Кафедра", "Bölüm", "Lehrstuhl"),
    "İmtahan növü": t("Exam kind", "Вид экзамена", "Sınav türü", "Prüfungsart"),
    "Forma": t("Format", "Формат", "Biçim", "Prüfungsformat"),
    "Status": t("Exam status", "Статус", "Durum", "Prüfungsstatus"),
    "Dövr": t("Term", "Период", "Dönem", "Semester"),
    "Tarixdən": t("From date", "С даты", "Başlangıç tarihi", "Ab Datum"),
    "Tarixədək": t("To date", "По дату", "Bitiş tarihi", "Bis Datum"),
    "Nəticə: %(count)d imtahan": t(
        "Result: %(count)d exams",
        "Найдено: %(count)d экзаменов",
        "Sonuç: %(count)d sınav",
        "Ergebnis: %(count)d Prüfungen",
    ),
    # Cədvəl
    "İmtahan": t("Exam", "Экзамен", "Sınav", "Prüfung"),
    "Fənn": t("Subject", "Предмет", "Ders", "Fach"),
    "Qrup(lar)": t("Group(s)", "Группа(ы)", "Grup(lar)", "Gruppe(n)"),
    "Müəllif": t("Author", "Автор", "Yazar", "Autor"),
    "Növ": t("Kind", "Вид", "Tür", "Art"),
    "Tarix": t("Date", "Дата", "Tarih", "Datum"),
    "İştirakçı / bitirən": t(
        "Participants / finished", "Участники / завершили", "Katılan / bitiren", "Teilnehmende / abgeschlossen"
    ),
    "Orta nəticə": t("Average result", "Средний результат", "Ortalama sonuç", "Durchschnittsergebnis"),
    "Ətraflı: cədvəl, qruplar, nəticələr": t(
        "Details: schedule, groups, results",
        "Подробнее: расписание, группы, результаты",
        "Ayrıntılar: takvim, gruplar, sonuçlar",
        "Details: Zeitplan, Gruppen, Ergebnisse",
    ),
    # Vəziyyətlər
    "Süzgəcə uyğun imtahan tapılmadı": t(
        "No exams match the filters",
        "Нет экзаменов, соответствующих фильтрам",
        "Filtrelere uyan sınav bulunamadı",
        "Keine Prüfungen entsprechen den Filtern",
    ),
    "Süzgəcləri dəyişin və ya «Sıfırla» düyməsini basın.": t(
        "Change the filters or press “Reset”.",
        "Измените фильтры или нажмите «Сбросить».",
        "Filtreleri değiştirin veya “Sıfırla” düğmesine basın.",
        "Ändern Sie die Filter oder klicken Sie auf „Zurücksetzen“.",
    ),
    "Bölmənizə aid imtahan hələ yoxdur": t(
        "There are no exams in your unit yet",
        "В вашем подразделении пока нет экзаменов",
        "Biriminize ait henüz sınav yok",
        "In Ihrer Einheit gibt es noch keine Prüfungen",
    ),
    (
        "Əhatəniz təyin olunub. Fakültə/kafedra müəllimləri imtahan yaradıb onu fənnə, "
        "qrupa və ya kafedraya bağladıqda burada görünəcək."
    ): t(
        "Your scope is set. Exams appear here once faculty/department teachers create them and link them to a "
        "subject, a group or a department.",
        "Ваша область назначена. Экзамены появятся здесь, когда преподаватели факультета/кафедры создадут их и "
        "привяжут к предмету, группе или кафедре.",
        "Kapsamınız tanımlı. Fakülte/bölüm öğretim elemanları sınav oluşturup onu bir derse, gruba veya bölüme "
        "bağladığında burada görünecek.",
        "Ihr Zuständigkeitsbereich ist festgelegt. Prüfungen erscheinen hier, sobald Lehrende der Fakultät bzw. des "
        "Lehrstuhls sie anlegen und einem Fach, einer Gruppe oder einem Lehrstuhl zuordnen.",
    ),
    "Üzvlüyünüzə fakültə/kafedra əhatəsi təyin edilməyib": t(
        "No faculty/department scope is assigned to your membership",
        "Вашему членству не назначена область факультета/кафедры",
        "Üyeliğinize fakülte/bölüm kapsamı atanmamış",
        "Ihrer Mitgliedschaft ist kein Fakultäts- oder Lehrstuhlbereich zugewiesen",
    ),
    (
        "Bölmə imtahanları yalnız dekan, dekan müavini və ya kafedra müdiri rolu konkret fakültəyə/kafedraya "
        "bağlı olduqda görünür. Rolunuzun vahidini təyin etmək üçün İKT və ya kadr şöbəsinə müraciət edin."
    ): t(
        "Unit exams are shown only when the dean, vice-dean or head-of-department role is bound to a specific "
        "faculty/department. Contact the ICT or HR office to have your role's unit assigned.",
        "Экзамены подразделения отображаются, только если роль декана, заместителя декана или заведующего "
        "кафедрой привязана к конкретному факультету/кафедре. Чтобы назначить подразделение вашей роли, "
        "обратитесь в отдел ИКТ или кадров.",
        "Birim sınavları yalnızca dekan, dekan yardımcısı veya bölüm başkanı rolü belirli bir fakülteye/bölüme "
        "bağlı olduğunda görünür. Rolünüzün birimini atamak için BİT veya personel birimine başvurun.",
        "Prüfungen der Einheit werden nur angezeigt, wenn die Rolle Dekan/in, Prodekan/in oder Lehrstuhlleitung "
        "einer bestimmten Fakultät bzw. einem Lehrstuhl zugeordnet ist. Wenden Sie sich an die IT- oder "
        "Personalabteilung, um die Einheit Ihrer Rolle festlegen zu lassen.",
    ),
    "Əhatənizdəki imtahanlar — yalnız baxış. Əhatə: %(scope)s": t(
        "Exams within your scope — read-only. Scope: %(scope)s",
        "Экзамены в вашей области — только просмотр. Область: %(scope)s",
        "Kapsamınızdaki sınavlar — yalnızca görüntüleme. Kapsam: %(scope)s",
        "Prüfungen in Ihrem Bereich – nur Ansicht. Bereich: %(scope)s",
    ),
    # Çekmecə
    "İmtahan haqqında": t("About the exam", "Об экзамене", "Sınav hakkında", "Über die Prüfung"),
    "Cədvəl, qruplar, suallar və nəticələrin xülasəsi — yalnız baxış.": t(
        "Schedule, groups, questions and a results summary — read-only.",
        "Расписание, группы, вопросы и сводка результатов — только просмотр.",
        "Takvim, gruplar, sorular ve sonuç özeti — yalnızca görüntüleme.",
        "Zeitplan, Gruppen, Fragen und Ergebnisübersicht – nur Ansicht.",
    ),
    "Kurs": t("Course", "Курс", "Eğitim kursu", "Lehrveranstaltung"),
    "Keçirilmə": t("Delivery", "Проведение", "Uygulama şekli", "Durchführung"),
    "Cədvəl": t("Schedule", "Расписание", "Takvim", "Zeitplan"),
    "Başlama": t("Start", "Начало", "Başlangıç", "Beginn"),
    "Bitmə": t("End", "Окончание", "Bitiş", "Ende"),
    "Yaradılıb": t("Created", "Создан", "Oluşturuldu", "Erstellt"),
    "Müddət": t("Duration", "Длительность", "Süre", "Dauer"),
    "{n} dəq": t("{n} min", "{n} мин", "{n} dk", "{n} Min."),
    "Limitsiz": t("Unlimited", "Без ограничения", "Sınırsız", "Unbegrenzt"),
    "Qruplar": t("Groups", "Группы", "Gruplar", "Gruppen"),
    "Qrup təyin edilməyib (fərdi və ya açıq imtahan).": t(
        "No group assigned (individual or open exam).",
        "Группа не назначена (индивидуальный или открытый экзамен).",
        "Grup atanmamış (bireysel veya açık sınav).",
        "Keine Gruppe zugewiesen (individuelle oder offene Prüfung).",
    ),
    "Sual": t("Questions", "Вопросы", "Soru", "Fragen"),
    "İştirakçı": t("Participants", "Участники", "Katılımcı", "Teilnehmende"),
    "Bitirən": t("Finished", "Завершили", "Bitiren", "Abgeschlossen"),
    "Bitmiş cəhd": t("Finished attempts", "Завершённые попытки", "Biten deneme", "Abgeschlossene Versuche"),
    "Keçənlərin payı (≥ 50)": t(
        "Pass rate (≥ 50)", "Доля сдавших (≥ 50)", "Geçenlerin oranı (≥ 50)", "Bestehensquote (≥ 50)"
    ),
    "Nəticələrin xülasəsi": t("Results summary", "Сводка результатов", "Sonuç özeti", "Ergebnisübersicht"),
    "Bitirən 3-dən azdır — məxfilik üçün orta nəticə göstərilmir.": t(
        "Fewer than 3 finished — the average is hidden for privacy.",
        "Завершили меньше 3 — средний результат скрыт ради конфиденциальности.",
        "Bitiren sayısı 3'ten az — gizlilik için ortalama gösterilmiyor.",
        "Weniger als 3 abgeschlossen – der Durchschnitt wird aus Datenschutzgründen ausgeblendet.",
    ),
    "Hələ bitmiş cəhd yoxdur.": t(
        "No finished attempts yet.",
        "Завершённых попыток пока нет.",
        "Henüz biten deneme yok.",
        "Noch keine abgeschlossenen Versuche.",
    ),
    "İmtahan səhifəsi": t("Exam page", "Страница экзамена", "Sınav sayfası", "Prüfungsseite"),
    "Nəticələr": t("Results", "Результаты", "Sonuçlar", "Ergebnisse"),
    "Bu baxış yalnız oxumaq üçündür; fərdi tələbə balları göstərilmir.": t(
        "This view is read-only; individual student scores are not shown.",
        "Этот вид только для чтения; индивидуальные баллы студентов не показываются.",
        "Bu görünüm yalnızca okunur; öğrencilerin bireysel puanları gösterilmez.",
        "Diese Ansicht ist schreibgeschützt; einzelne Studierendenpunkte werden nicht angezeigt.",
    ),
    "Məlumat tapılmadı — siyahını yeniləyin.": t(
        "Data not found — refresh the list.",
        "Данные не найдены — обновите список.",
        "Veri bulunamadı — listeyi yenileyin.",
        "Daten nicht gefunden – aktualisieren Sie die Liste.",
    ),
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
    for msgid, translations in ENTRIES.items():
        if f'msgctxt "{esc(CTX)}"\nmsgid "{esc(msgid)}"\n' in text:
            continue
        msgstr = msgid if lang == "az" else translations[lang]
        flag = "#, python-format\n" if "%(" in msgid else ""
        blocks.append(f'{flag}msgctxt "{esc(CTX)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
        added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
