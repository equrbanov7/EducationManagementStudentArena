"""Ümumi üzrlü saatlar: beş dilə idempotent, yalnız yeni kataloq əlavələri."""

import subprocess
from pathlib import Path

import polib

BASE = Path(__file__).resolve().parent.parent
CTX = "registrar.absence_credit"
# Source, English, Russian, Turkish, German.
ROWS = [
    (
        "Qeydiyyat dəyişib. Səhifəni yeniləyib təkrar edin.",
        "The enrolment changed. Refresh the page and try again.",
        "Запись изменилась. Обновите страницу и повторите попытку.",
        "Kayıt değişti. Sayfayı yenileyip tekrar deneyin.",
        "Die Einschreibung wurde geändert. Seite aktualisieren und erneut versuchen.",
    ),
    (
        "Üzrlü qayıb (ümumi saat)",
        "Excused absence (total hours)",
        "Уважительные пропуски (часы)",
        "Mazeretli devamsızlık (toplam saat)",
        "Entschuldigte Fehlzeit (Stunden)",
    ),
    (
        "Seçilmiş fənn üzrə qayıb saatına güzəşt verilir. Dərs tarixləri və iştirak xanaları dəyişmir.",
        "The absence allowance applies to the selected subject. Lesson dates and attendance cells remain unchanged.",
        "Зачёт уважительных пропусков применяется к выбранному предмету. Даты занятий и ячейки посещаемости не меняются.",
        "Devamsızlık indirimi seçilen derse uygulanır. Ders tarihleri ve yoklama hücreleri değişmez.",
        "Die Gutschrift gilt für das gewählte Fach. Unterrichtsdaten und Anwesenheitseinträge bleiben unverändert.",
    ),
    ("Tələbə", "Student", "Студент", "Öğrenci", "Studierende Person"),
    ("Tələbəni seçin", "Select a student", "Выберите студента", "Öğrenci seçin", "Person auswählen"),
    ("saat", "hours", "часов", "saat", "Stunden"),
    ("Üzrlü sayılan saat", "Excused hours", "Зачтённые часы", "Mazeretli saatler", "Entschuldigte Stunden"),
    ("Səbəb", "Reason", "Причина", "Neden", "Grund"),
    ("Tətbiq et", "Apply", "Применить", "Uygula", "Anwenden"),
    ("Geri alma səbəbi", "Reversal reason", "Причина отмены", "Geri alma nedeni", "Grund der Rücknahme"),
    ("Geri al", "Reverse", "Отменить", "Geri al", "Zurücknehmen"),
    (
        "Ümumi üzrlü: %(hours)s saat",
        "Total excused: %(hours)s hours",
        "Всего зачтено: %(hours)s часов",
        "Toplam mazeretli: %(hours)s saat",
        "Entschuldigt: %(hours)s Stunden",
    ),
    (
        "Sorğu açarı düzgün deyil.",
        "Invalid request key.",
        "Неверный ключ запроса.",
        "Geçersiz istek anahtarı.",
        "Ungültiger Anfrageschlüssel.",
    ),
    (
        "Səbəb 10–1000 simvol olmalıdır.",
        "The reason must contain 10–1000 characters.",
        "Причина должна содержать 10–1000 символов.",
        "Neden 10–1000 karakter içermelidir.",
        "Der Grund muss 10–1000 Zeichen enthalten.",
    ),
    (
        "Bu fənnin tələbə qeydiyyatı tapılmadı.",
        "The student's enrolment for this subject was not found.",
        "Запись студента на этот предмет не найдена.",
        "Bu ders için öğrenci kaydı bulunamadı.",
        "Die Einschreibung für dieses Fach wurde nicht gefunden.",
    ),
    (
        "Geri alınacaq düzəliş tapılmadı.",
        "The adjustment to reverse was not found.",
        "Корректировка для отмены не найдена.",
        "Geri alınacak düzeltme bulunamadı.",
        "Die zurückzunehmende Korrektur wurde nicht gefunden.",
    ),
    (
        "Saat müsbət tam ədəd olmalıdır.",
        "Hours must be a positive whole number.",
        "Часы должны быть положительным целым числом.",
        "Saat pozitif bir tam sayı olmalıdır.",
        "Stunden müssen eine positive ganze Zahl sein.",
    ),
    (
        "Bu sorğu açarı başqa düzəlişdə istifadə olunub.",
        "This request key was used for another adjustment.",
        "Этот ключ запроса использован для другой корректировки.",
        "Bu istek anahtarı başka bir düzeltmede kullanılmıştır.",
        "Dieser Anfrageschlüssel wurde für eine andere Korrektur verwendet.",
    ),
    (
        "Bu düzəliş artıq geri alınıb.",
        "This adjustment has already been reversed.",
        "Эта корректировка уже отменена.",
        "Bu düzeltme zaten geri alınmış.",
        "Diese Korrektur wurde bereits zurückgenommen.",
    ),
    (
        "Güzəşt mövcud üzrsüz qayıb saatından çox ola bilməz.",
        "The allowance cannot exceed current unexcused absence hours.",
        "Зачёт не может превышать текущие часы неуважительных пропусков.",
        "İndirim mevcut mazeretsiz devamsızlık saatini aşamaz.",
        "Die Gutschrift darf die unentschuldigten Fehlstunden nicht überschreiten.",
    ),
    (
        "Düzəlişə icazə yoxdur.",
        "This adjustment is not permitted.",
        "Эта корректировка не разрешена.",
        "Bu düzeltmeye izin verilmiyor.",
        "Diese Korrektur ist nicht erlaubt.",
    ),
    (
        "Ümumi üzrlü qayıb saatı yadda saxlanıldı.",
        "Total excused absence hours saved.",
        "Общее число уважительных пропусков сохранено.",
        "Toplam mazeretli devamsızlık saati kaydedildi.",
        "Die entschuldigten Fehlstunden wurden gespeichert.",
    ),
]


def main():
    for language, index in [("az", 0), ("en", 1), ("ru", 2), ("tr", 3), ("de", 4)]:
        path = BASE / "locale" / language / "LC_MESSAGES" / "django.po"
        catalog = polib.pofile(str(path))
        additions = [
            polib.POEntry(msgctxt=CTX, msgid=row[0], msgstr=row[index])
            for row in ROWS
            if catalog.find(row[0], msgctxt=CTX) is None
        ]
        added = len(additions)
        if added:
            # Preserve all existing comments, wrapping and ordering verbatim.
            with path.open("a", encoding="utf-8") as output:
                output.write("\n" + "\n".join(str(entry) for entry in additions))
            subprocess.run(["msgfmt", "-o", str(path.with_suffix(".mo")), str(path)], check=True)
        print(f"{language}: +{added}")


if __name__ == "__main__":
    main()
