#!/usr/bin/env python3
"""EMSArena i18n — «Fənnimə aid apellyasiyalar» kabinet bölməsi (sahib 2026-10-27).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

CTX = "appeals.teaching"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    CTX: {
        "%(a)s qəbul, %(r)s rədd": t(
            "%(a)s accepted, %(r)s rejected",
            "%(a)s принято, %(r)s отклонено",
            "%(a)s kabul, %(r)s ret",
            "%(a)s angenommen, %(r)s abgelehnt",
        ),
        "%(n)s sual": t("%(n)s question(s)", "вопросов: %(n)s", "%(n)s soru", "%(n)s Frage(n)"),
        "+%(delta)s bal əlavə olunub": t(
            "+%(delta)s points added",
            "Добавлено +%(delta)s балла",
            "+%(delta)s puan eklendi",
            "+%(delta)s Punkte hinzugefügt",
        ),
        "Ad, soyad, ata adı, istifadəçi adı…": t(
            "First name, last name, patronymic, username…",
            "Имя, фамилия, отчество, логин…",
            "Ad, soyad, baba adı, kullanıcı adı…",
            "Vorname, Nachname, Vatersname, Benutzername…",
        ),
        "Aktiv təşkilat seçilməyib": t(
            "No active organisation selected",
            "Активная организация не выбрана",
            "Aktif kurum seçilmedi",
            "Keine aktive Organisation ausgewählt",
        ),
        "Apellyasiya": t("Appeal", "Апелляция", "İtiraz", "Einspruch"),
        "Apellyasiya tapılmadı və ya baxmaq icazəniz yoxdur.": t(
            "The appeal was not found or you are not allowed to view it.",
            "Апелляция не найдена или у вас нет прав на просмотр.",
            "İtiraz bulunamadı veya görüntüleme izniniz yok.",
            "Der Einspruch wurde nicht gefunden oder Sie dürfen ihn nicht ansehen.",
        ),
        "Apellyasiyanın tarixçəsi": t(
            "Appeal history", "История апелляции", "İtiraz geçmişi", "Verlauf des Einspruchs"
        ),
        "Ata adı": t("Patronymic", "Отчество", "Baba adı", "Vatersname"),
        "Bal": t("Score", "Балл", "Puan", "Punkte"),
        "Bal düzəlişi geri alınıb": t(
            "Score adjustment reverted",
            "Корректировка балла отменена",
            "Puan düzeltmesi geri alındı",
            "Punktkorrektur zurückgenommen",
        ),
        "Bax": t("View", "Открыть", "Görüntüle", "Ansehen"),
        "Bax: %(student)s — %(exam)s": t(
            "View: %(student)s — %(exam)s",
            "Открыть: %(student)s — %(exam)s",
            "Görüntüle: %(student)s — %(exam)s",
            "Ansehen: %(student)s — %(exam)s",
        ),
        "Cəmi": t("Total", "Всего", "Toplam", "Gesamt"),
        "Dəyişmə": t("Change", "Изменение", "Değişim", "Änderung"),
        "Etiraz olunan suallar": t(
            "Disputed questions", "Оспариваемые вопросы", "İtiraz edilen sorular", "Angefochtene Fragen"
        ),
        "Excel-ə yüklə": t("Download Excel", "Скачать Excel", "Excel'e indir", "Als Excel herunterladen"),
        "Fənn": t("Subject", "Предмет", "Ders", "Fach"),
        "Fayl ilk %(n)s sətirlə məhdudlaşdırılıb — süzgəcləri daraldıb yenidən yükləyin.": t(
            "The file is limited to the first %(n)s rows — narrow the filters and download again.",
            "Файл ограничен первыми %(n)s строками — сузьте фильтры и скачайте снова.",
            "Dosya ilk %(n)s satırla sınırlandı — filtreleri daraltıp yeniden indirin.",
            "Die Datei ist auf die ersten %(n)s Zeilen begrenzt — Filter eingrenzen und erneut herunterladen.",
        ),
        "Göndərilib": t("Submitted", "Подана", "Gönderildi", "Eingereicht"),
        "Gözlənilir": t("Pending", "Ожидается", "Bekleniyor", "Ausstehend"),
        "Hamısı": t("All", "Все", "Tümü", "Alle"),
        "Kateqoriya": t("Category", "Категория", "Kategori", "Kategorie"),
        "Nəticə: %(n)s müraciət": t(
            "Result: %(n)s appeal(s)",
            "Результат: обращений — %(n)s",
            "Sonuç: %(n)s itiraz",
            "Ergebnis: %(n)s Einspruch/Einsprüche",
        ),
        "Orta bal dəyişməsi": t(
            "Average score change",
            "Среднее изменение балла",
            "Ortalama puan değişimi",
            "Durchschnittliche Punktänderung",
        ),
        "Qrup": t("Group", "Группа", "Grup", "Gruppe"),
        "Qəbul": t("Accepted", "Принято", "Kabul", "Angenommen"),
        "Qəbul / qismən": t("Accepted / partly", "Принято / частично", "Kabul / kısmen", "Angenommen / teilweise"),
        "Qəbul edildi (tam və ya qismən)": t(
            "Accepted (fully or partly)",
            "Принято (полностью или частично)",
            "Kabul edildi (tamamen veya kısmen)",
            "Angenommen (ganz oder teilweise)",
        ),
        "Qərar": t("Decision", "Решение", "Karar", "Entscheidung"),
        "Qərar tarixi": t("Decision date", "Дата решения", "Karar tarihi", "Entscheidungsdatum"),
        "Qərara əsaslandırıcı sənəd əlavə olunmayıb.": t(
            "No supporting document was attached to the decision.",
            "К решению не приложен обосновывающий документ.",
            "Karara gerekçe belgesi eklenmedi.",
            "Der Entscheidung wurde kein Nachweisdokument beigefügt.",
        ),
        "Qərarı verən müəllim": t(
            "Deciding teacher", "Преподаватель, принявший решение", "Kararı veren öğretmen", "Entscheidende Lehrkraft"
        ),
        "Rədd": t("Rejected", "Отклонено", "Ret", "Abgelehnt"),
        "Status": t("Appeal status", "Статус", "Durum", "Einspruchsstatus"),
        "Sual sayı": t("Questions", "Вопросов", "Soru sayısı", "Fragen"),
        "Suallar": t("Questions", "Вопросы", "Sorular", "Fragen"),
        "Süzgəcləri dəyişin və ya «Sıfırla» ilə hamısını göstərin.": t(
            "Change the filters or use “Reset” to show everything.",
            "Измените фильтры или нажмите «Сбросить», чтобы показать всё.",
            "Filtreleri değiştirin veya tümünü göstermek için «Sıfırla»yı kullanın.",
            "Ändern Sie die Filter oder zeigen Sie mit „Zurücksetzen“ alles an.",
        ),
        "Süzgəcə uyğun apellyasiya yoxdur": t(
            "No appeals match the filters",
            "Нет апелляций по выбранным фильтрам",
            "Filtrelere uyan itiraz yok",
            "Keine Einsprüche entsprechen den Filtern",
        ),
        "Tarixdən": t("From", "С даты", "Başlangıç", "Von"),
        "Tarixçə": t("History", "История", "Geçmiş", "Verlauf"),
        "Tarixədək": t("To", "По дату", "Bitiş", "Bis"),
        "Tədris etdiyiniz fənlər üzrə tələbələrinizin apellyasiyaları. Qərarı imtahan mərkəzi verir — burada yalnız baxış var.": t(
            "Appeals of your students in the subjects you teach. The exam centre decides — this is a read-only view.",
            "Апелляции ваших студентов по преподаваемым вами предметам. Решение принимает экзаменационный центр — здесь только просмотр.",
            "Verdiğiniz derslerde öğrencilerinizin itirazları. Kararı sınav merkezi verir — burada yalnızca görüntüleme vardır.",
            "Einsprüche Ihrer Studierenden in den von Ihnen unterrichteten Fächern. Das Prüfungszentrum entscheidet — hier nur Ansicht.",
        ),
        "Tələbə": t("Student", "Студент", "Öğrenci", "Studierende/r"),
        "Tələbə və ya imtahan": t(
            "Student or exam", "Студент или экзамен", "Öğrenci veya sınav", "Studierende/r oder Prüfung"
        ),
        "Tələbənin səbəbi": t(
            "Student's reason", "Причина студента", "Öğrencinin gerekçesi", "Begründung der/des Studierenden"
        ),
        "Təşkilatın bütün apellyasiyaları — nəzarət görünüşü. Qərarı imtahan mərkəzi verir, burada yalnız baxış var.": t(
            "All appeals of the organisation — oversight view. The exam centre decides; this is a read-only view.",
            "Все апелляции организации — режим контроля. Решение принимает экзаменационный центр, здесь только просмотр.",
            "Kurumun tüm itirazları — denetim görünümü. Kararı sınav merkezi verir, burada yalnızca görüntüleme vardır.",
            "Alle Einsprüche der Organisation — Aufsichtsansicht. Das Prüfungszentrum entscheidet; hier nur Ansicht.",
        ),
        "Yadda saxlayan": t("Saved by", "Сохранил(а)", "Kaydeden", "Gespeichert von"),
        "Yalnız baxış: qərarı imtahan mərkəzi verir.": t(
            "Read-only: the exam centre makes the decision.",
            "Только просмотр: решение принимает экзаменационный центр.",
            "Yalnızca görüntüleme: kararı sınav merkezi verir.",
            "Nur Ansicht: Das Prüfungszentrum entscheidet.",
        ),
        "Yeni bal": t("New score", "Новый балл", "Yeni puan", "Neue Punktzahl"),
        "Yükləmək üçün apellyasiya yoxdur.": t(
            "There are no appeals to download.",
            "Нет апелляций для выгрузки.",
            "İndirilecek itiraz yok.",
            "Keine Einsprüche zum Herunterladen.",
        ),
        "Yüklənir…": t("Loading…", "Загрузка…", "Yükleniyor…", "Wird geladen…"),
        "Yüklənmə alınmadı, yenidən cəhd edin.": t(
            "Loading failed, please try again.",
            "Не удалось загрузить, попробуйте ещё раз.",
            "Yüklenemedi, lütfen tekrar deneyin.",
            "Laden fehlgeschlagen, bitte erneut versuchen.",
        ),
        "qismən: %(n)s": t("partly: %(n)s", "частично: %(n)s", "kısmen: %(n)s", "teilweise: %(n)s"),
        "qərarlı müraciət başına": t(
            "per decided appeal",
            "на одну рассмотренную апелляцию",
            "karara bağlanan itiraz başına",
            "pro entschiedenem Einspruch",
        ),
        "süzgəcə uyğun müraciət": t(
            "appeals matching the filters", "апелляций по фильтрам", "filtrelere uyan itiraz", "Einsprüche gemäß Filter"
        ),
        "yalnız imtahan mərkəzi endirə bilər": t(
            "only the exam centre can download",
            "скачать может только экзаменационный центр",
            "yalnızca sınav merkezi indirebilir",
            "nur das Prüfungszentrum kann herunterladen",
        ),
        "yeni bal": t("new score", "новый балл", "yeni puan", "neue Punktzahl"),
        "İlkin bal": t("Original score", "Исходный балл", "İlk puan", "Ursprüngliche Punktzahl"),
        "İmtahan": t("Exam", "Экзамен", "Sınav", "Prüfung"),
        "İmtahan / fənn": t("Exam / subject", "Экзамен / предмет", "Sınav / ders", "Prüfung / Fach"),
        "İmtahan mərkəzinin cavabı": t(
            "Exam centre's response",
            "Ответ экзаменационного центра",
            "Sınav merkezinin yanıtı",
            "Antwort des Prüfungszentrums",
        ),
        "İmtahan mərkəzinin qeydi": t(
            "Exam centre's note",
            "Примечание экзаменационного центра",
            "Sınav merkezinin notu",
            "Anmerkung des Prüfungszentrums",
        ),
        "İstifadəçi adı": t("Username", "Логин", "Kullanıcı adı", "Benutzername"),
        "Əlavə olunmuş sənədlər": t(
            "Attached documents", "Приложенные документы", "Ekli belgeler", "Angehängte Dokumente"
        ),
        "Əməliyyat": t("Action", "Действие", "İşlem", "Aktion"),
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
