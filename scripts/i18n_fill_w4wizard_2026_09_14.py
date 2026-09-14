#!/usr/bin/env python3
"""EMSArena i18n — W4 `w4wizard` imtahan sehrbazı: reyestr qrupları (2026-09-14).

R2: sehrbazın «İcazəli qruplar» seçicisi köhnə imtahan kohortları (`StudentGroup`)
əvəzinə qrup REYESTRİNİ (OrgUnit GROUP, məs. «634 ing») təqdim edir; kohortlar
yalnız mövcud olduqda «Köhnə kohortlar» kimi ikinci dərəcəli qalır. Yeni
açarlar: `Exam.allowed_units` sahə/help mətni, seçici etiketi + axtarış
yer-tutucusu, köhnə kohort etiketi və tenant/əhatə xətası. R6: dublikat
toast-unun «suallar kopyalanmadı» xəbərdarlığı (dizayn: kopya sualsız yaranır).

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir və
idempotentdir. TR qarşılığı QƏSDƏN AZ mənbədən fərqlidir (i18n qapısı
`msgstr == msgid` sətrini «tərcümə olunmamış» sayır). Msgid-lər AÇARDIR
(`allowed_units` kimi) — AZ msgstr aşağıdakı `az` dəyəridir.

İstifadə:  python scripts/i18n_fill_w4wizard_2026_09_14.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "exams.model.exam.field": {
        "allowed_units": {
            "az": "Reyestr qrupları",
            "en": "Registry groups",
            "ru": "Группы реестра",
            "tr": "Kayıt grupları",
        },
    },
    "exams.model.exam.help": {
        "allowed_units": {
            "az": "Qrup reyestrindən (akademik qruplar) imtahana buraxılan qruplar.",
            "en": "Academic groups from the groups registry that are admitted to the exam.",
            "ru": "Академические группы из реестра групп, допущенные к экзамену.",
            "tr": "Grup kayıt defterinden sınava kabul edilen akademik gruplar.",
        },
    },
    "exams.template.create_exam_modal_form": {
        "allowed_units": {
            "az": "Qruplar (reyestr)",
            "en": "Groups (registry)",
            "ru": "Группы (реестр)",
            "tr": "Gruplar (kayıt)",
        },
        "search_unit_group": {
            "az": "Qrup axtar (məs. 634 ing)...",
            "en": "Search a group (e.g. 634 ing)...",
            "ru": "Поиск группы (напр. 634 ing)...",
            "tr": "Grup ara (örn. 634 ing)...",
        },
        "legacy_cohorts": {
            "az": "Köhnə kohortlar",
            "en": "Legacy cohorts",
            "ru": "Старые когорты",
            "tr": "Eski kohortlar",
        },
    },
    "exams.view.exams.message": {
        "exam_duplicated_questions_not_copied": {
            "az": "Suallar kopyalanmadı — kopya boş qaralamadır (mənbədə {count} sual qaldı). Bankdan sual əlavə edin.",
            "en": "Questions were not copied — the copy is an empty draft ({count} questions stayed in the source). Add questions from the bank.",
            "ru": "Вопросы не скопированы — копия является пустым черновиком (в источнике осталось {count} вопросов). Добавьте вопросы из банка.",
            "tr": "Sorular kopyalanmadı — kopya boş bir taslaktır (kaynakta {count} soru kaldı). Bankadan soru ekleyin.",
        },
        "exam_duplicated_source_empty": {
            "az": "Mənbə imtahanda sual yox idi — kopya boş qaralamadır, sual əlavə edin.",
            "en": "The source exam had no questions — the copy is an empty draft; add questions.",
            "ru": "В исходном экзамене не было вопросов — копия является пустым черновиком; добавьте вопросы.",
            "tr": "Kaynak sınavda soru yoktu — kopya boş bir taslaktır; soru ekleyin.",
        },
    },
    "exams.view.exams.error": {
        "allowed_units_invalid": {
            "az": "Seçilmiş qrup(lar) bu təşkilatda tapılmadı və ya əhatənizdən kənardır.",
            "en": "The selected group(s) were not found in this organization or are outside your scope.",
            "ru": "Выбранные группы не найдены в этой организации или вне вашей области.",
            "tr": "Seçilen grup(lar) bu kurumda bulunamadı veya kapsamınızın dışında.",
        },
    },
}


# JS (`exam_wizard.js` / `form.js`) — çılpaq `gettext()` ehtiyat mətnləri (`djangojs`
# kataloqu, kontekstsiz). Əsas mənbə `profile.html`-dəki `EXAM_WIZARD_I18N` /
# `EXAM_CREATE_EDIT_MODAL_I18N` lüğətidir (accounts sahibliyi — orkestrator əlavə edir):
#   endAfterStart, durationPositive, durationWithinWindow, questionCountInvalid, rowLegacyGroups.
JS_ENTRIES = {
    "Bitmə vaxtı başlama vaxtından sonra olmalıdır.": {
        "en": "The end time must be after the start time.",
        "ru": "Время окончания должно быть позже времени начала.",
        "tr": "Bitiş zamanı başlangıç zamanından sonra olmalıdır.",
    },
    "Müddət 0-dan böyük olmalıdır.": {
        "en": "The duration must be greater than 0.",
        "ru": "Длительность должна быть больше 0.",
        "tr": "Süre 0'dan büyük olmalıdır.",
    },
    "Müddət imtahan pəncərəsindən ({n} dəq) uzun ola bilməz.": {
        "en": "The duration cannot exceed the exam window ({n} min).",
        "ru": "Длительность не может превышать окно экзамена ({n} мин).",
        "tr": "Süre sınav penceresinden ({n} dk) uzun olamaz.",
    },
    "Sual sayı mənfi ola bilməz (0 = bütün suallar).": {
        "en": "The question count cannot be negative (0 = all questions).",
        "ru": "Количество вопросов не может быть отрицательным (0 = все вопросы).",
        "tr": "Soru sayısı negatif olamaz (0 = tüm sorular).",
    },
    "Köhnə kohortlar": {"en": "Legacy cohorts", "ru": "Старые когорты", "tr": "Eski kohortlar"},
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n' in text:
                continue
            msgstr = translations.get(lang) or translations["az"]
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"django/{lang}: +{added} entry")


def fill_js(lang):
    path = po_path(lang, "djangojs")
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    blocks, added = [], 0
    for msgid, translations in JS_ENTRIES.items():
        if f'msgid "{esc(msgid)}"\n' in text:
            continue
        msgstr = msgid if lang == "az" else translations.get(lang, msgid)
        blocks.append(f'msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
        added += 1
    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"djangojs/{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
        fill_js(locale)
