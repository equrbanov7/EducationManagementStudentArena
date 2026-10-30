"""Append missing staff-creation strings without rewriting existing catalogues."""

import json
from pathlib import Path

import polib

ROOT = Path(__file__).resolve().parents[1]
MESSAGES = {
    "profile.rim": {
        "Bu rol təşkilatı bütövlükdə əhatə edir; bölmə sahəsini boş saxlayın.": (
            "This role covers the whole organization; leave the department field empty.",
            "Эта роль охватывает всю организацию; оставьте поле подразделения пустым.",
            "Bu rol tüm kurumu kapsar; bölüm alanını boş bırakın.",
            "Diese Rolle gilt für die gesamte Organisation; lassen Sie das Abteilungsfeld leer.",
        ),
        "Bu vəzifə üçün kafedra və ya bölmə seçin.": (
            "Select a department or unit for this position.",
            "Выберите кафедру или подразделение для этой должности.",
            "Bu görev için bir bölüm veya birim seçin.",
            "Wählen Sie für diese Position einen Fachbereich oder eine Organisationseinheit.",
        ),
        "Bölmə tapılmadı və ya icazə əhatənizdən kənardadır.": (
            "The unit was not found or is outside your permission scope.",
            "Подразделение не найдено или находится вне ваших полномочий.",
            "Birim bulunamadı veya yetki alanınızın dışında.",
            "Die Organisationseinheit wurde nicht gefunden oder liegt außerhalb Ihres Berechtigungsbereichs.",
        ),
        "Vəzifə seçilməyib və ya bu rolu təyin etmək üçün icazəniz yoxdur.": (
            "No position was selected, or you do not have permission to assign this role.",
            "Должность не выбрана или у вас нет права назначать эту роль.",
            "Görev seçilmedi veya bu rolü atama yetkiniz yok.",
            "Es wurde keine Position ausgewählt oder Sie dürfen diese Rolle nicht zuweisen.",
        ),
        "Kafedra / bölmə": (
            "Department / unit",
            "Кафедра / подразделение",
            "Bölüm / birim",
            "Fachbereich / Organisationseinheit",
        ),
        "Vəzifə və kafedra/bölmə seçimi ilə yeni əməkdaş hesabı.": (
            "A new staff account with a selected position and department or unit.",
            "Новая учётная запись сотрудника с выбором должности и кафедры или подразделения.",
            "Görev ve bölüm veya birim seçimiyle yeni personel hesabı.",
            "Ein neues Mitarbeiterkonto mit ausgewählter Position und Organisationseinheit.",
        ),
        "Yeni inzibati heyət hesabı": (
            "New administrative staff account",
            "Новая учётная запись административного сотрудника",
            "Yeni idari personel hesabı",
            "Neues Konto für Verwaltungspersonal",
        ),
        "İnzibati heyət": (
            "Administrative staff",
            "Административный персонал",
            "İdari personel",
            "Verwaltungspersonal",
        ),
        "Əməkdaş hesabı yaradıldı.": (
            "The staff account was created.",
            "Учётная запись сотрудника создана.",
            "Personel hesabı oluşturuldu.",
            "Das Mitarbeiterkonto wurde erstellt.",
        ),
        "Əməkdaş hesabında boş qala bilər — istifadəçi ilk girişdə özü yazacaq.": (
            "Optional for staff accounts; the user will enter it at first login.",
            "Для учётных записей сотрудников можно оставить пустым; пользователь заполнит при первом входе.",
            "Personel hesaplarında boş bırakılabilir; kullanıcı ilk girişte kendisi doldurur.",
            "Für Mitarbeiterkonten optional; der Benutzer ergänzt dies bei der ersten Anmeldung.",
        ),
        "Məs.: Laborant, Kafedra müdiri": (
            "E.g. laboratory assistant, department head",
            "Например: лаборант, заведующий кафедрой",
            "Örn.: laboratuvar görevlisi, bölüm başkanı",
            "Z. B. Laborassistenz, Fachbereichsleitung",
        ),
        "Vəzifə / rol": ("Position / role", "Должность / роль", "Görev / rol", "Position / Rolle"),
        "Vəzifə nəticələri": (
            "Position results",
            "Результаты поиска должностей",
            "Görev sonuçları",
            "Positionsergebnisse",
        ),
        "Vəzifəni axtarıb siyahıdan seçin. Kafedra vəzifələrində bölmə də seçilməlidir.": (
            "Search for a position and select it from the list. Department positions also require a unit.",
            "Найдите должность и выберите её из списка. Для кафедральных должностей также выберите подразделение.",
            "Görevi arayıp listeden seçin. Bölüm görevleri için birim de seçilmelidir.",
            "Suchen Sie eine Position und wählen Sie sie aus der Liste. Fachbereichspositionen erfordern auch eine Einheit.",
        ),
    },
    "student_intake": {
        "Əməkdaş üçün vəzifə / rol seçilməlidir.": (
            "A position or role must be selected for the staff member.",
            "Для сотрудника необходимо выбрать должность или роль.",
            "Personel için bir görev veya rol seçilmelidir.",
            "Für den Mitarbeiter muss eine Position oder Rolle ausgewählt werden.",
        ),
    },
}


def fill():
    counts = {}
    for language, index in (("az", 0), ("en", 0), ("ru", 1), ("tr", 2), ("de", 3)):
        path = ROOT / "locale" / language / "LC_MESSAGES" / "django.po"
        catalog = polib.pofile(path)
        blocks = []
        for context, messages in MESSAGES.items():
            for message, translations in messages.items():
                if catalog.find(message, msgctxt=context):
                    continue
                value = message if language == "az" else translations[index]
                blocks.append(
                    "\n".join(
                        key + " " + json.dumps(text, ensure_ascii=False)
                        for key, text in (("msgctxt", context), ("msgid", message), ("msgstr", value))
                    )
                )
        if blocks:
            with path.open("a", encoding="utf-8") as handle:
                handle.write("\n" + "\n\n".join(blocks) + "\n")
        polib.pofile(path).save_as_mofile(path.with_suffix(".mo"))
        counts[language] = len(blocks)
    print(json.dumps(counts, sort_keys=True))


if __name__ == "__main__":
    fill()
