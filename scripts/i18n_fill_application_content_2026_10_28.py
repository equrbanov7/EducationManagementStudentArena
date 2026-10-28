"""Append application content UI translations without reformatting catalogs."""

from pathlib import Path

import polib

CONTEXT = "applications.content"
ROWS = [
    ("Müraciəti redaktə et", "Edit request", "Изменить обращение", "Başvuruyu düzenle", "Anfrage bearbeiten"),
    ("Müraciəti sil", "Delete request", "Удалить обращение", "Başvuruyu sil", "Anfrage löschen"),
    (
        "Müraciəti bərpa et",
        "Restore request",
        "Восстановить обращение",
        "Başvuruyu geri yükle",
        "Anfrage wiederherstellen",
    ),
    ("Cavabı redaktə et", "Edit reply", "Изменить ответ", "Yanıtı düzenle", "Antwort bearbeiten"),
    ("Cavabı sil", "Delete reply", "Удалить ответ", "Yanıtı sil", "Antwort löschen"),
    ("Cavabı bərpa et", "Restore reply", "Восстановить ответ", "Yanıtı geri yükle", "Antwort wiederherstellen"),
    ("Redaktə edilib", "Edited", "Изменено", "Düzenlendi", "Bearbeitet"),
    (
        "Bu müraciət silinib. Bərpa olunduqda əvvəlki vəziyyəti saxlanılacaq.",
        "This request was deleted. Restoring it preserves its previous status.",
        "Обращение удалено. При восстановлении сохранится прежний статус.",
        "Bu başvuru silindi. Geri yüklendiğinde önceki durumu korunur.",
        "Diese Anfrage wurde gelöscht. Bei der Wiederherstellung bleibt der vorherige Status erhalten.",
    ),
    (
        "Müraciət əvvəlki qərarı və yazışması ilə bərpa edilsin?",
        "Restore the request with its previous decision and conversation?",
        "Восстановить обращение с прежним решением и перепиской?",
        "Başvuru önceki kararı ve yazışmalarıyla geri yüklensin mi?",
        "Anfrage mit bisheriger Entscheidung und Unterhaltung wiederherstellen?",
    ),
    (
        "Müraciət siyahıdan çıxarılsın? Onu «Silinənlər» bölməsindən bərpa edə bilərsiniz.",
        "Remove the request from the list? You can restore it from Deleted.",
        "Убрать обращение из списка? Его можно восстановить в разделе «Удалённые».",
        "Başvuru listeden kaldırılsın mı? Silinenler bölümünden geri yükleyebilirsiniz.",
        "Anfrage aus der Liste entfernen? Sie können sie unter Gelöscht wiederherstellen.",
    ),
    (
        "Əməliyyatı təsdiqləyin. Cavab audit tarixçəsində saxlanılır.",
        "Confirm this action. The reply remains in the audit history.",
        "Подтвердите действие. Ответ сохранится в истории аудита.",
        "İşlemi onaylayın. Yanıt denetim geçmişinde saklanır.",
        "Aktion bestätigen. Die Antwort bleibt im Prüfverlauf erhalten.",
    ),
    (
        "Prorektoru seçin",
        "Select a vice rector",
        "Выберите проректора",
        "Rektör yardımcısını seçin",
        "Prorektor auswählen",
    ),
    ("Silinənlər", "Deleted", "Удалённые", "Silinenler", "Gelöscht"),
    ("Redaktə et", "Edit", "Изменить", "Düzenle", "Bearbeiten"),
    ("Mövzu", "Subject", "Тема", "Konu", "Betreff"),
    ("Mətn", "Text", "Текст", "Metin", "Text"),
    (
        "Əvvəlki mətn tarixçədə saxlanılır. Müraciətin ünvanı və qərarı dəyişmir.",
        "Previous text is kept in history. The recipient and decision remain unchanged.",
        "Прежний текст сохраняется в истории. Адресат и решение не изменяются.",
        "Önceki metin geçmişte saklanır. Alıcı ve karar değişmez.",
        "Der vorherige Text bleibt im Verlauf. Empfänger und Entscheidung bleiben unverändert.",
    ),
    ("Ləğv et", "Cancel", "Отмена", "İptal", "Abbrechen"),
    ("Yadda saxla", "Save", "Сохранить", "Kaydet", "Speichern"),
]


def fill():
    root = Path(__file__).resolve().parent.parent
    for language_index, language in enumerate(("az", "en", "ru", "tr", "de")):
        path = root / "locale" / language / "LC_MESSAGES" / "django.po"
        catalog = polib.pofile(path)
        blocks = []
        for row in ROWS:
            if catalog.find(row[0], msgctxt=CONTEXT):
                continue
            blocks.append(str(polib.POEntry(msgctxt=CONTEXT, msgid=row[0], msgstr=row[language_index])))
        if blocks:
            path.write_text(path.read_text().rstrip("\n") + "\n\n" + "\n".join(blocks))
        polib.pofile(path).save_as_mofile(str(path.with_suffix(".mo")))
        print(f"{language}: +{len(blocks)} entries")


if __name__ == "__main__":
    fill()
