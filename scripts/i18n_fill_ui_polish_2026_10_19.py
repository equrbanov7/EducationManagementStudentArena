#!/usr/bin/env python3
"""EMSArena i18n — UI cilası (sahib 2026-10-19): ortaq «AI ilə test sualı yarat» paneli, «Suallar bankından
seç» modalının redizaynı (təkrar əlavə qoruması, xəta vəziyyətləri) və «Sorğular» boş vəziyyət kartı.

msgid AZ cümlədir → az msgstr = msgid. Şablon `blocktrans` dəyişəni ``%(n)s`` kimi (python-format).
İdempotentdir (mövcud ctx+msgid toxunulmur); sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

AI = "exams.template.ai_question_bank"
BP = "exams.template.bank_picker"
BM = "exams.view.bank.message"
SI = "surveys.inbox"
SC = "surveys.cabinet"


def t(en, ru, tr, de, az=None):
    row = {"en": en, "ru": ru, "tr": tr, "de": de}
    if az is not None:
        row["az"] = az
    return row


ENTRIES = {
    AI: {
        "Fayl seçin və ya bura atın": t(
            "Choose a file or drop it here",
            "Выберите файл или перетащите его сюда",
            "Dosya seçin veya buraya bırakın",
            "Datei auswählen oder hier ablegen",
        ),
        "Faylı çıxar": t("Remove file", "Убрать файл", "Dosyayı kaldır", "Datei entfernen"),
        "Bu fayl növü dəstəklənmir — PDF, TXT, PNG və ya JPG seçin.": t(
            "This file type is not supported — choose a PDF, TXT, PNG or JPG.",
            "Этот тип файла не поддерживается — выберите PDF, TXT, PNG или JPG.",
            "Bu dosya türü desteklenmiyor — PDF, TXT, PNG veya JPG seçin.",
            "Dieser Dateityp wird nicht unterstützt — wählen Sie PDF, TXT, PNG oder JPG.",
        ),
        "Fayl çıxarıldı.": t("File removed.", "Файл убран.", "Dosya kaldırıldı.", "Datei entfernt."),
    },
    BP: {
        "Siyahı yüklənmədi": t(
            "The list could not be loaded",
            "Не удалось загрузить список",
            "Liste yüklenemedi",
            "Die Liste konnte nicht geladen werden",
        ),
        "Bağlantını yoxlayıb yenidən cəhd edin. Problem qalırsa səhifəni yeniləyin.": t(
            "Check your connection and try again. If the problem persists, reload the page.",
            "Проверьте подключение и попробуйте снова. Если проблема сохраняется, обновите страницу.",
            "Bağlantınızı kontrol edip tekrar deneyin. Sorun devam ederse sayfayı yenileyin.",
            "Prüfen Sie die Verbindung und versuchen Sie es erneut. Besteht das Problem weiter, laden Sie die Seite neu.",
        ),
        "Yenidən cəhd et": t("Try again", "Повторить", "Tekrar dene", "Erneut versuchen"),
        "Növbəti suallar yüklənmədi.": t(
            "The next questions could not be loaded.",
            "Не удалось загрузить следующие вопросы.",
            "Sonraki sorular yüklenemedi.",
            "Die nächsten Fragen konnten nicht geladen werden.",
        ),
        "Suallar əlavə olunmadı. Yenidən cəhd edin.": t(
            "The questions were not added. Please try again.",
            "Вопросы не добавлены. Попробуйте снова.",
            "Sorular eklenmedi. Lütfen tekrar deneyin.",
            "Die Fragen wurden nicht hinzugefügt. Bitte versuchen Sie es erneut.",
        ),
        "Şəbəkə xətası — bağlantını yoxlayıb yenidən cəhd edin.": t(
            "Network error — check your connection and try again.",
            "Ошибка сети — проверьте подключение и попробуйте снова.",
            "Ağ hatası — bağlantınızı kontrol edip tekrar deneyin.",
            "Netzwerkfehler — prüfen Sie die Verbindung und versuchen Sie es erneut.",
        ),
        "Bu imtahana sual əlavə etmək icazəniz yoxdur.": t(
            "You are not allowed to add questions to this exam.",
            "У вас нет права добавлять вопросы в этот экзамен.",
            "Bu sınava soru ekleme yetkiniz yok.",
            "Sie dürfen dieser Prüfung keine Fragen hinzufügen.",
        ),
        "Bank tapılmadı və ya artıq sizə açıq deyil. Siyahını yeniləyin.": t(
            "The bank was not found or is no longer available to you. Refresh the list.",
            "Банк не найден или больше вам недоступен. Обновите список.",
            "Banka bulunamadı veya artık size açık değil. Listeyi yenileyin.",
            "Die Fragenbank wurde nicht gefunden oder ist für Sie nicht mehr verfügbar. Aktualisieren Sie die Liste.",
        ),
        "Əlavə olunur…": t("Adding…", "Добавление…", "Ekleniyor…", "Wird hinzugefügt…"),
        "Ləğv et": t("Cancel", "Отмена", "İptal", "Abbrechen"),
        "Seçilmişləri imtahana əlavə et": t(
            "Add selected to the exam",
            "Добавить выбранные в экзамен",
            "Seçilenleri sınava ekle",
            "Auswahl zur Prüfung hinzufügen",
        ),
        "{n} sual seçilib": t(
            "{n} questions selected", "Выбрано вопросов: {n}", "{n} soru seçildi", "{n} Fragen ausgewählt"
        ),
        "Görünənlərin hamısını seç": t(
            "Select all shown", "Выбрать все показанные", "Gösterilenlerin tümünü seç", "Alle angezeigten auswählen"
        ),
        "%(n)s artıq imtahanda": t(
            "%(n)s already in the exam", "%(n)s уже в экзамене", "%(n)s zaten sınavda", "%(n)s bereits in der Prüfung"
        ),
        "Artıq əlavə olunub": t("Already added", "Уже добавлен", "Zaten eklendi", "Bereits hinzugefügt"),
        "çox cavablı": t("multiple answers", "несколько ответов", "çok cevaplı", "Mehrfachantwort"),
        "Daha çox göstər": t("Show more", "Показать ещё", "Daha fazla göster", "Mehr anzeigen"),
    },
    BM: {
        "Seçilmiş suallar artıq imtahanda var — yeni sual əlavə olunmadı.": t(
            "The selected questions are already in the exam — no new questions were added.",
            "Выбранные вопросы уже есть в экзамене — новые вопросы не добавлены.",
            "Seçilen sorular zaten sınavda — yeni soru eklenmedi.",
            "Die ausgewählten Fragen sind bereits in der Prüfung — es wurden keine neuen Fragen hinzugefügt.",
        ),
        "{count} sual artıq imtahanda idi — ötürüldü.": t(
            "{count} questions were already in the exam — skipped.",
            "{count} вопр. уже были в экзамене — пропущены.",
            "{count} soru zaten sınavdaydı — atlandı.",
            "{count} Fragen waren bereits in der Prüfung — übersprungen.",
        ),
    },
    SI: {
        "Baxış rejimində sorğular göstərilmir": t(
            "Surveys are not shown in view-as mode",
            "В режиме просмотра опросы не показываются",
            "Görüntüleme modunda anketler gösterilmez",
            "Im Ansichtsmodus werden keine Umfragen angezeigt",
        ),
        "Səhifəni yeniləyin; problem qalırsa İKT dəstəyinə müraciət edin.": t(
            "Reload the page; if the problem persists, contact IT support.",
            "Обновите страницу; если проблема сохраняется, обратитесь в службу ИКТ-поддержки.",
            "Sayfayı yenileyin; sorun devam ederse BT desteğine başvurun.",
            "Laden Sie die Seite neu; besteht das Problem weiter, wenden Sie sich an den IT-Support.",
        ),
        "Gözləyən sorğu yoxdur": t(
            "No pending surveys", "Нет ожидающих опросов", "Bekleyen anket yok", "Keine ausstehenden Umfragen"
        ),
        "Yeni sorğu təyin olunanda burada görünəcək və bildiriş alacaqsınız.": t(
            "When a new survey is assigned to you, it will appear here and you will get a notification.",
            "Когда вам назначат новый опрос, он появится здесь, и вы получите уведомление.",
            "Size yeni bir anket atandığında burada görünecek ve bildirim alacaksınız.",
            "Sobald Ihnen eine neue Umfrage zugewiesen wird, erscheint sie hier und Sie erhalten eine Benachrichtigung.",
        ),
    },
    SC: {
        "Açıq sorğu yoxdur": t("No open survey", "Нет открытых опросов", "Açık anket yok", "Keine offene Umfrage"),
        "Semestr sonu anonim qiymətləndirmə açılanda burada görünəcək və bildiriş alacaqsınız.": t(
            "When the end-of-semester anonymous evaluation opens, it will appear here and you will get a notification.",
            "Когда откроется анонимная оценка в конце семестра, она появится здесь, и вы получите уведомление.",
            "Dönem sonu anonim değerlendirme açıldığında burada görünecek ve bildirim alacaksınız.",
            "Sobald die anonyme Bewertung zum Semesterende geöffnet wird, erscheint sie hier und Sie erhalten eine "
            "Benachrichtigung.",
        ),
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
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            flag = "#, python-format\n" if "%%" in msgid or "%(" in msgid else ""
            blocks.append(f'{flag}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
