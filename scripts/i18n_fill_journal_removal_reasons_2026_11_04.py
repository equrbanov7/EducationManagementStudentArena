#!/usr/bin/env python3
"""EMSArena i18n — jurnaldan çıxarılma səbəbi + «Jurnaldan çıxarılmalar» bölməsi (sahib 2026-11-04).

Kontekstlər: ``registrar.journal_removal`` (səbəb siyahısı, modal sahələri, doğrulama mesajları),
``registrar.journal_history`` (tarixçə növləri), ``accounts.journal_removals`` (RİM kabinet bölməsi + Excel),
``profile.section`` (menyu adı), ``registrar.model.journal_removal.meta``. msgid AZ cümlədir → az msgstr = msgid
(model meta istisna — ingilis msgid, az tərcümə). ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları
əlavə edir, idempotentdir. Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_journal_removal_reasons_2026_11_04.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]


def t(en, ru, tr, de, az=None):
    return {"en": en, "ru": ru, "tr": tr, "de": de, "az": az}


ENTRIES = {
    "registrar.journal_removal": {
        "Uzaqlaşdırma": t("Suspension", "Отстранение", "Uzaklaştırma", "Suspendierung"),
        "Fənn əvəzlənməsi (sənəd təqdim edib)": t(
            "Subject substitution (document submitted)",
            "Замена предмета (представлен документ)",
            "Ders muafiyeti/eşdeğerliği (belge sundu)",
            "Fachersatz (Dokument vorgelegt)",
        ),
        "Kredit tanınması / köçürmə": t(
            "Credit recognition / transfer",
            "Признание кредитов / перевод",
            "Kredi tanınması / transfer",
            "Anrechnung von Credits / Übertragung",
        ),
        "Səhv əlavə olunub": t(
            "Added by mistake", "Добавлен по ошибке", "Yanlışlıkla eklendi", "Irrtümlich hinzugefügt"
        ),
        "Başqa qrupa / alt qrupa keçid": t(
            "Moved to another group / subgroup",
            "Переход в другую группу / подгруппу",
            "Başka gruba / alt gruba geçiş",
            "Wechsel in eine andere Gruppe / Untergruppe",
        ),
        "Digər": t("Other", "Другое", "Diğer", "Sonstiges"),
        "Fəndən azad": t("Exempt from subject", "Освобождён от предмета", "Dersten muaf", "Vom Fach befreit"),
        "Alt qrupdan əlavə geri götürüldü": t(
            "Subgroup addition withdrawn",
            "Добавление из подгруппы отменено",
            "Alt gruptan ekleme geri alındı",
            "Hinzufügung aus Untergruppe zurückgenommen",
        ),
        "Çıxarılma səbəbini seçin.": t(
            "Select the removal reason.",
            "Выберите причину исключения.",
            "Çıkarma nedenini seçin.",
            "Wählen Sie den Grund der Entfernung.",
        ),
        "Çıxarılma səbəbi tanınmadı — siyahıdan seçin.": t(
            "Unknown removal reason — choose one from the list.",
            "Причина исключения не распознана — выберите из списка.",
            "Çıkarma nedeni tanınmadı — listeden seçin.",
            "Unbekannter Entfernungsgrund — wählen Sie einen aus der Liste.",
        ),
        "«Digər» seçiləndə qeyd yazılmalıdır.": t(
            "A note is required when «Other» is selected.",
            "При выборе «Другое» необходимо написать примечание.",
            "«Diğer» seçildiğinde not yazılmalıdır.",
            "Bei «Sonstiges» ist eine Notiz erforderlich.",
        ),
        "Sistem": t("System", "Система", "Sistem otomatiği", "System"),
        "Çıxarılma səbəbi": t("Removal reason", "Причина исключения", "Çıkarma nedeni", "Grund der Entfernung"),
        "— Səbəbi seçin —": t("— Select a reason —", "— Выберите причину —", "— Neden seçin —", "— Grund wählen —"),
        "Qeyd": t("Note", "Примечание", "Not", "Notiz"),
        "(istəyə bağlı)": t("(optional)", "(необязательно)", "(isteğe bağlı)", "(optional)"),
        "(«Digər» üçün məcburi)": t(
            "(required for «Other»)",
            "(обязательно для «Другое»)",
            "(«Diğer» için zorunlu)",
            "(Pflicht bei «Sonstiges»)",
        ),
        "Məs.: sənəd №, əmr tarixi, hansı fənnlə əvəzlənib": t(
            "E.g.: document no., order date, which subject replaces it",
            "Напр.: № документа, дата приказа, каким предметом заменён",
            "Örn.: belge no, emir tarihi, hangi dersle değiştirildi",
            "z. B.: Dokument-Nr., Datum der Anordnung, durch welches Fach ersetzt",
        ),
        "Jurnaldan çıxarılır:": t(
            "Removing from the journal:",
            "Исключается из журнала:",
            "Yoklama defterinden çıkarılıyor:",
            "Wird aus dem Journal entfernt:",
        ),
    },
    "registrar.journal_history": {
        "Jurnaldan çıxarıldı": t(
            "Removed from the journal",
            "Исключён из журнала",
            "Yoklama defterinden çıkarıldı",
            "Aus dem Journal entfernt",
        ),
        "Jurnala qaytarıldı": t(
            "Returned to the journal",
            "Возвращён в журнал",
            "Yoklama defterine geri alındı",
            "Ins Journal zurückgeholt",
        ),
        "Siyahıdan çıxarılma": t(
            "Roster removals", "Исключения из списка", "Listeden çıkarma", "Entfernungen aus der Liste"
        ),
    },
    "profile.section": {
        "Jurnaldan çıxarılmalar": t(
            "Journal removals",
            "Исключения из журналов",
            "Yoklama defterinden çıkarmalar",
            "Entfernungen aus Journalen",
        ),
    },
    "registrar.model.journal_removal.meta": {
        "journal removal": t(
            "journal removal record",
            "запись об исключении из журнала",
            "yoklama defterinden çıkarma kaydı",
            "Journal-Entfernungseintrag",
            az="jurnaldan çıxarılma qeydi",
        ),
        "journal removals": t(
            "journal removal records",
            "записи об исключении из журнала",
            "yoklama defterinden çıkarma kayıtları",
            "Journal-Entfernungseinträge",
            az="jurnaldan çıxarılma qeydləri",
        ),
    },
    "accounts.journal_removals": {
        "Ad, soyad və ya istifadəçi adı": t(
            "First name, last name or username",
            "Имя, фамилия или имя пользователя",
            "Ad, soyad veya kullanıcı adı",
            "Vorname, Nachname oder Benutzername",
        ),
        "Bu bölmə yalnız RİM rəhbəri və superadmin üçündür.": t(
            "This section is only for the head of the Registrar's office and superadmins.",
            "Этот раздел доступен только руководителю РИМ и суперадмину.",
            "Bu bölüm yalnızca RİM yöneticisi ve süper yönetici içindir.",
            "Dieser Bereich ist nur für die Leitung des Registrars und Superadmins.",
        ),
        "Bərpa olunub": t("Restored", "Восстановлен", "Geri alındı", "Wiederhergestellt"),
        "Excel-ə ixrac": t("Export to Excel", "Экспорт в Excel", "Excel'e aktar", "Nach Excel exportieren"),
        "Fakültə": t("Faculty", "Факультет", "Fakülte", "Fakultät"),
        "Fayl ilk %(n)s sətirlə məhdudlaşdırılıb — süzgəcləri daraldıb yenidən yükləyin.": t(
            "The file is limited to the first %(n)s rows — narrow the filters and download again.",
            "Файл ограничен первыми %(n)s строками — сузьте фильтры и скачайте снова.",
            "Dosya ilk %(n)s satırla sınırlandı — filtreleri daraltıp yeniden indirin.",
            "Die Datei ist auf die ersten %(n)s Zeilen begrenzt — Filter eingrenzen und erneut herunterladen.",
        ),
        "Fənn": t("Subject", "Предмет", "Ders", "Fach"),
        "Fənn / jurnal": t("Subject / journal", "Предмет / журнал", "Ders / yoklama defteri", "Fach / Journal"),
        "Fənn kodu": t("Subject code", "Код предмета", "Ders kodu", "Fachcode"),
        "Hamısı": t("All", "Все", "Tümü", "Alle"),
        "Hələ jurnaldan çıxarılma qeydə alınmayıb": t(
            "No journal removals recorded yet",
            "Исключения из журналов ещё не зафиксированы",
            "Henüz yoklama defterinden çıkarma kaydedilmedi",
            "Noch keine Entfernungen aus Journalen erfasst",
        ),
        "Jurnalda «Fəndən azad et» və ya alt qrup «Çıxar» səbəb seçilərək ediləndə qeyd burada görünəcək.": t(
            "When «Exempt from subject» or the subgroup «Remove» is done in a journal with a reason, the record will "
            "appear here.",
            "Когда в журнале выполняется «Освободить от предмета» или «Исключить» из подгруппы с указанием причины, "
            "запись появится здесь.",
            "Yoklama defterinde «Dersten muaf tut» veya alt grup «Çıkar» bir neden seçilerek yapıldığında kayıt burada "
            "görünecek.",
            "Wenn im Journal «Vom Fach befreien» oder «Entfernen» (Untergruppe) mit Grund ausgeführt wird, erscheint "
            "der Eintrag hier.",
        ),
        "Jurnaldan çıxarılan hər tələbə səbəb kateqoriyası və qeydlə burada qeyd olunur: fəndən azad etmə, alt qrupdan əlavənin geri götürülməsi və xarici nəticənin tanınması. Süzgəclərlə səbəbə, tarixə, fakültəyə, kafedraya, müəllimə və tələbəyə görə daraldın.": t(
            "Every student removed from a journal is recorded here with a reason category and note: subject "
            "exemption, withdrawal of a subgroup addition and recognition of an external result. Use the filters to "
            "narrow by reason, date, faculty, chair, teacher and student.",
            "Каждый исключённый из журнала студент фиксируется здесь с категорией причины и примечанием: "
            "освобождение от предмета, отмена добавления из подгруппы и признание внешнего результата. Сужайте "
            "список фильтрами по причине, дате, факультету, кафедре, преподавателю и студенту.",
            "Yoklama defterinden çıkarılan her öğrenci neden kategorisi ve notla burada kaydedilir: dersten muafiyet, "
            "alt gruptan eklemenin geri alınması ve dış sonucun tanınması. Filtrelerle nedene, tarihe, fakülteye, "
            "bölüme, öğretim elemanına ve öğrenciye göre daraltın.",
            "Jeder aus einem Journal entfernte Studierende wird hier mit Grundkategorie und Notiz erfasst: "
            "Fachbefreiung, Rücknahme einer Untergruppen-Hinzufügung und Anerkennung eines externen Ergebnisses. "
            "Mit den Filtern nach Grund, Datum, Fakultät, Lehrstuhl, Lehrkraft und Studierendem eingrenzen.",
        ),
        "Jurnaldan çıxarılmaların ixracı": t(
            "Export of journal removals",
            "Экспорт исключений из журналов",
            "Yoklama defterinden çıkarmaların dışa aktarımı",
            "Export der Entfernungen aus Journalen",
        ),
        "Kafedra": t("Chair", "Кафедра", "Bölüm", "Lehrstuhl"),
        "Müəllim": t("Teacher", "Преподаватель", "Öğretim elemanı", "Lehrkraft"),
        "Müəllimin adı": t("Teacher's name", "Имя преподавателя", "Öğretim elemanının adı", "Name der Lehrkraft"),
        "Növbəti": t("Next", "Следующая", "Sonraki", "Weiter"),
        "Nəticə: %(n)s qeyd": t(
            "Result: %(n)s records", "Результат: %(n)s записей", "Sonuç: %(n)s kayıt", "Ergebnis: %(n)s Einträge"
        ),
        "Qeyd": t("Note", "Примечание", "Not", "Notiz"),
        "Qrup": t("Group", "Группа", "Grup", "Gruppe"),
        "Qüvvədə": t("In effect", "Действует", "Yürürlükte", "In Kraft"),
        "Semestr": t("Semester", "Семестр", "Yarıyıl", "Semester"),
        "Süzgəcləri dəyişin və ya «Sıfırla» basın.": t(
            "Change the filters or press «Reset».",
            "Измените фильтры или нажмите «Сбросить».",
            "Filtreleri değiştirin veya «Sıfırla»ya basın.",
            "Ändern Sie die Filter oder klicken Sie auf «Zurücksetzen».",
        ),
        "Süzgəcə uyğun çıxarılma yoxdur": t(
            "No removals match the filters",
            "Нет исключений, соответствующих фильтрам",
            "Filtreye uygun çıkarma yok",
            "Keine Entfernungen entsprechen den Filtern",
        ),
        "Səbəb": t("Reason", "Причина", "Neden", "Grund"),
        "Səbəb üzrə say": t("Count by reason", "Количество по причинам", "Nedene göre sayı", "Anzahl nach Grund"),
        "Səhifə %(page)s / %(last)s": t(
            "Page %(page)s / %(last)s",
            "Страница %(page)s / %(last)s",
            "Sayfa %(page)s / %(last)s",
            "Seite %(page)s / %(last)s",
        ),
        "Səhifələr": t("Pages", "Страницы", "Sayfalar", "Seiten"),
        "Tarix": t("Date", "Дата", "Tarih", "Datum"),
        "Tarixdən": t("From date", "С даты", "Başlangıç tarihi", "Ab Datum"),
        "Tarixədək": t("To date", "По дату", "Bitiş tarihi", "Bis Datum"),
        "Tələbə": t("Student", "Студент", "Öğrenci", "Studierende(r)"),
        "Vəziyyət": t("Status", "Состояние", "Durum", "Status"),
        "Çıxaran": t("Removed by", "Кем исключён", "Çıkaran", "Entfernt von"),
        "İstifadəçi adı": t("Username", "Имя пользователя", "Kullanıcı adı", "Benutzername"),
        "Əməl": t("Action", "Действие", "İşlem", "Aktion"),
        "Əvvəlki": t("Previous", "Предыдущая", "Önceki", "Zurück"),
    },
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain="django"):
    path = po_path(lang, domain)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = (translations.get("az") or msgid) if lang == "az" else translations[lang]
            flag = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flag}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for lang in LOCALES:
        fill(lang)
