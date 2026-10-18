#!/usr/bin/env python3
"""EMSArena i18n — Tədris şöbəsi səthlərinin xəta düzəlişləri 2026-10-19.

Əlavə olunan mətnlər (hamısı ``django`` domeni):
  * `accounts.curriculum` — plan sətri dialoqunun seçmə sahələri
    (`teaching_office/_plan_row_fields.html`) və server xətaları (`registrar/curriculum_elective.py`);
  * `accounts.semester` — dövr dialoqunun təqvim pəncərələri (`teaching_office/_period_fields.html`),
    «Dövrü redaktə et» düyməsi (`_semester_header_actions.html`), pəncərə xəta/xəbərdarlıqları
    (`registrar/semester_period_windows.py`) və model doğrulaması (`registrar/semester_actions.py`);
  * `accounts.structure_tree` — ağacdan rəhbər təyinində tələbə qoruması (`organizations/structure_actions.py`).

msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan
blokları əlavə edir, idempotentdir (mövcudluq `polib` ilə yoxlanılır). Sonra
`compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_teaching_office_fixes_2026_10_19.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

CURRICULUM = "accounts.curriculum"
SEMESTER = "accounts.semester"
TREE = "accounts.structure_tree"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    CURRICULUM: {
        "Seçmə fənn": {
            "en": "Elective subject",
            "ru": "Дисциплина по выбору",
            "tr": "Seçmeli ders",
            "de": "Wahlfach",
        },
        "Seçmə fənn blokdan seçilir; bayraq söndürülsə sətir məcburi olur.": {
            "en": "An elective is chosen from a block; if the flag is cleared the row becomes mandatory.",
            "ru": "Дисциплина по выбору выбирается из блока; если снять флажок, строка станет обязательной.",
            "tr": "Seçmeli ders bir bloktan seçilir; işaret kaldırılırsa satır zorunlu olur.",
            "de": "Ein Wahlfach wird aus einem Block gewählt; ohne Häkchen wird die Zeile zum Pflichtfach.",
        },
        "Seçmə bloku": {
            "en": "Elective block",
            "ru": "Блок по выбору",
            "tr": "Seçmeli blok",
            "de": "Wahlblock",
        },
        "Məs. SB1": {"en": "E.g. SB1", "ru": "Напр. SB1", "tr": "Örn. SB1", "de": "z. B. SB1"},
        "Eyni blokun sətirləri eyni adı daşıyır.": {
            "en": "Rows of the same block carry the same name.",
            "ru": "Строки одного блока имеют одинаковое название.",
            "tr": "Aynı bloğun satırları aynı adı taşır.",
            "de": "Zeilen desselben Blocks tragen denselben Namen.",
        },
        "Seçiləcək fənn sayı": {
            "en": "Number of subjects to choose",
            "ru": "Количество выбираемых дисциплин",
            "tr": "Seçilecek ders sayısı",
            "de": "Anzahl zu wählender Fächer",
        },
        "Blokun bütün sətirlərinə şamil olunur.": {
            "en": "Applies to every row of the block.",
            "ru": "Применяется ко всем строкам блока.",
            "tr": "Bloğun tüm satırlarına uygulanır.",
            "de": "Gilt für alle Zeilen des Blocks.",
        },
        "Seçmə fənn üçün seçmə bloku göstərilməlidir.": {
            "en": "An elective subject needs an elective block.",
            "ru": "Для дисциплины по выбору нужно указать блок.",
            "tr": "Seçmeli ders için seçmeli blok belirtilmelidir.",
            "de": "Für ein Wahlfach muss ein Wahlblock angegeben werden.",
        },
        "Seçiləcək fənn sayı 1–20 aralığında olmalıdır.": {
            "en": "The number of subjects to choose must be between 1 and 20.",
            "ru": "Количество выбираемых дисциплин должно быть от 1 до 20.",
            "tr": "Seçilecek ders sayısı 1–20 arasında olmalıdır.",
            "de": "Die Anzahl zu wählender Fächer muss zwischen 1 und 20 liegen.",
        },
    },
    SEMESTER: {
        "Təqvim pəncərələri": {
            "en": "Calendar windows",
            "ru": "Календарные окна",
            "tr": "Takvim pencereleri",
            "de": "Kalenderfenster",
        },
        "Opsionaldır. İmtahan balının kilidi, mühasibatlığın tədris pəncərəsi və seçmə fənn qeydiyyatı bu tarixlərə "
        "baxır.": {
            "en": "Optional. The exam score lock, the accounting teaching window and elective registration use "
            "these dates.",
            "ru": "Необязательно. Блокировка экзаменационных баллов, учебное окно бухгалтерии и запись на "
            "дисциплины по выбору опираются на эти даты.",
            "tr": "İsteğe bağlı. Sınav notu kilidi, muhasebenin öğretim penceresi ve seçmeli ders kaydı bu "
            "tarihlere bakar.",
            "de": "Optional. Die Sperre der Prüfungsnoten, das Lehrfenster der Buchhaltung und die "
            "Wahlfach-Anmeldung richten sich nach diesen Daten.",
        },
        "İmtahan sessiyasının başlanğıcı": {
            "en": "Exam session start",
            "ru": "Начало экзаменационной сессии",
            "tr": "Sınav döneminin başlangıcı",
            "de": "Beginn des Prüfungszeitraums",
        },
        "İmtahan sessiyasının sonu": {
            "en": "Exam session end",
            "ru": "Конец экзаменационной сессии",
            "tr": "Sınav döneminin sonu",
            "de": "Ende des Prüfungszeitraums",
        },
        "Semestrin bitmə tarixindən sonraya uzana bilər.": {
            "en": "May extend past the semester end date.",
            "ru": "Может выходить за дату окончания семестра.",
            "tr": "Dönemin bitiş tarihinden sonraya uzayabilir.",
            "de": "Darf über das Semesterende hinausgehen.",
        },
        "Seçim (qeydiyyat) pəncərəsi başlanğıcı": {
            "en": "Elective (registration) window start",
            "ru": "Начало окна выбора (записи)",
            "tr": "Seçim (kayıt) penceresinin başlangıcı",
            "de": "Beginn des Wahl- (Anmelde-)fensters",
        },
        "Seçim (qeydiyyat) pəncərəsi sonu": {
            "en": "Elective (registration) window end",
            "ru": "Конец окна выбора (записи)",
            "tr": "Seçim (kayıt) penceresinin sonu",
            "de": "Ende des Wahl- (Anmelde-)fensters",
        },
        "Dövrü redaktə et": {
            "en": "Edit period",
            "ru": "Изменить период",
            "tr": "Dönemi düzenle",
            "de": "Zeitraum bearbeiten",
        },
        "Tarix düzgün deyil.": {
            "en": "The date is not valid.",
            "ru": "Неверная дата.",
            "tr": "Tarih geçerli değil.",
            "de": "Das Datum ist ungültig.",
        },
        "%(window)s üçün həm başlanğıc, həm də son tarix göstərilməlidir.": {
            "en": "%(window)s needs both a start and an end date.",
            "ru": "Для «%(window)s» нужно указать и дату начала, и дату окончания.",
            "tr": "%(window)s için hem başlangıç hem de bitiş tarihi belirtilmelidir.",
            "de": "Für %(window)s müssen Beginn und Ende angegeben werden.",
        },
        "%(window)s: son tarix başlanğıcdan əvvəl ola bilməz.": {
            "en": "%(window)s: the end date cannot be before the start.",
            "ru": "%(window)s: дата окончания не может быть раньше начала.",
            "tr": "%(window)s: bitiş tarihi başlangıçtan önce olamaz.",
            "de": "%(window)s: Das Enddatum darf nicht vor dem Beginn liegen.",
        },
        "İmtahan sessiyası": {
            "en": "Exam session",
            "ru": "Экзаменационная сессия",
            "tr": "Sınav dönemi",
            "de": "Prüfungszeitraum",
        },
        "Seçim (qeydiyyat) pəncərəsi": {
            "en": "Elective (registration) window",
            "ru": "Окно выбора (записи)",
            "tr": "Seçim (kayıt) penceresi",
            "de": "Wahl- (Anmelde-)fenster",
        },
        "İmtahan sessiyası semestr tarixləri daxilində başlamır — tarixləri yoxlayın.": {
            "en": "The exam session does not start within the semester dates — check the dates.",
            "ru": "Экзаменационная сессия начинается вне дат семестра — проверьте даты.",
            "tr": "Sınav dönemi yarıyıl tarihleri içinde başlamıyor — tarihleri kontrol edin.",
            "de": "Der Prüfungszeitraum beginnt nicht innerhalb des Semesters — prüfen Sie die Daten.",
        },
        "Seçim pəncərəsi semestr tarixlərindən xeyli kənardadır — tarixləri yoxlayın.": {
            "en": "The elective window is far outside the semester dates — check the dates.",
            "ru": "Окно выбора далеко за пределами дат семестра — проверьте даты.",
            "tr": "Seçim penceresi yarıyıl tarihlerinin çok dışında — tarihleri kontrol edin.",
            "de": "Das Wahlfenster liegt weit außerhalb des Semesters — prüfen Sie die Daten.",
        },
        "Dövr məlumatları düzgün deyil.": {
            "en": "The period details are not valid.",
            "ru": "Данные периода неверны.",
            "tr": "Dönem bilgileri geçerli değil.",
            "de": "Die Angaben zum Zeitraum sind ungültig.",
        },
    },
    TREE: {
        "Tələbə hesabına rəhbər rolu verilə bilməz.": {
            "en": "A student account cannot be given a head role.",
            "ru": "Учётной записи студента нельзя назначить роль руководителя.",
            "tr": "Öğrenci hesabına yönetici rolü verilemez.",
            "de": "Einem Studierendenkonto kann keine Leitungsrolle zugewiesen werden.",
        },
    },
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    """Çatışmayan blokları faylın SONUNA əlavə edir (mövcud mətn yenidən formatlanmır)."""
    path = po_path(lang)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    blocks = []
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = translations.get("az", msgid) if lang == "az" else translations.get(lang) or msgid
            flag = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flag}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
    if blocks:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.rstrip("\n") + "\n\n" + "\n".join(blocks))
    print(f"{lang}/django: +{len(blocks)} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
