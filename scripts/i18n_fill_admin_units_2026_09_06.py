#!/usr/bin/env python3
"""EMSArena i18n — RİM «Yeni inzibati bölmə» axınının mətnləri. İdempotent.

RİM mərkəzinə şöbə/mərkəz yaratma seçimi əlavə edildi (chooser + dialoq +
valideyn seçicisi). Bu skript həmin mətnləri 4 dilə doldurur.
⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız ƏLAVƏ edir, mövcud girişə toxunmur.
İstifadə:  python scripts/i18n_fill_admin_units_2026_09_06.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

#: Bölmə sahələrinin etiketləri (ad / tip / kod / «Seçin…») QƏSDƏN buradadır
#: DEYİL: onlar ağac ekranının `accounts.structure_tree` kontekstində ARTIQ var
#: və dialoq həmin girişləri təkrar işlədir (bax `_rim_create_unit.html`).
ENTRIES = {
    "profile.rim": {
        "Nə yaratmaq istəyirsiniz?": {
            "en": "What would you like to create?",
            "ru": "Что вы хотите создать?",
            "tr": "Ne oluşturmak istiyorsunuz?",
        },
        "Hesab və ya inzibati bölmə seçin.": {
            "en": "Choose an account or an administrative unit.",
            "ru": "Выберите учётную запись или административное подразделение.",
            "tr": "Bir hesap ya da idari birim seçin.",
        },
        "Yeni yarat": {
            "en": "Create new",
            "ru": "Создать",
            "tr": "Yeni oluştur",
        },
        "Yeni bölmə": {
            "en": "New unit",
            "ru": "Новое подразделение",
            "tr": "Yeni birim",
        },
        "Yeni inzibati bölmə": {
            "en": "New administrative unit",
            "ru": "Новое административное подразделение",
            "tr": "Yeni idari birim",
        },
        "Şöbə, mərkəz, institut və ya laboratoriya.": {
            "en": "Department, centre, institute or laboratory.",
            "ru": "Отдел, центр, институт или лаборатория.",
            "tr": "Şube, merkez, enstitü veya laboratuvar.",
        },
        "Şöbə, mərkəz, institut və ya laboratoriya — struktur ağacında yaradılır.": {
            "en": "Department, centre, institute or laboratory — created in the structure tree.",
            "ru": "Отдел, центр, институт или лаборатория — создаётся в дереве структуры.",
            "tr": "Şube, merkez, enstitü veya laboratuvar — yapı ağacında oluşturulur.",
        },
        "Bölmə struktur ağacında yaradılır və dəyişiklik audit jurnalına düşür.": {
            "en": "The unit is created in the structure tree and the change is written to the audit log.",
            "ru": "Подразделение создаётся в дереве структуры, изменение записывается в журнал аудита.",
            "tr": "Birim yapı ağacında oluşturulur ve değişiklik denetim günlüğüne yazılır.",
        },
        "Valideyn bölmə": {
            "en": "Parent unit",
            "ru": "Родительское подразделение",
            "tr": "Üst birim",
        },
        "Valideyn bölmə nəticələri": {
            "en": "Parent unit results",
            "ru": "Результаты по родительским подразделениям",
            "tr": "Üst birim sonuçları",
        },
        "Rektorat, fakültə və ya şöbənin adını yazın": {
            "en": "Type the name of the rectorate, faculty or department",
            "ru": "Введите название ректората, факультета или отдела",
            "tr": "Rektörlük, fakülte veya şube adını yazın",
        },
        "Yeni bölmə bu vahidin altında yaranacaq.": {
            "en": "The new unit will be created under this one.",
            "ru": "Новое подразделение будет создано под этим.",
            "tr": "Yeni birim bunun altında oluşturulacak.",
        },
        "Məsələn: Beynəlxalq əlaqələr şöbəsi": {
            "en": "For example: International Relations Department",
            "ru": "Например: отдел международных связей",
            "tr": "Örneğin: Uluslararası İlişkiler Şubesi",
        },
        "Fakültə, kafedra və ixtisas akademik ağacdadır — «Universitet strukturu» ekranından qurulur.": {
            "en": (
                "Faculties, chairs and specialities live in the academic tree — "
                "build them on the «University structure» screen."
            ),
            "ru": (
                "Факультет, кафедра и специальность находятся в академическом дереве — "
                "они создаются на экране «Структура университета»."
            ),
            "tr": "Fakülte, bölüm ve program akademik ağaçtadır — «Üniversite yapısı» ekranından kurulur.",
        },
        "Boş qala bilər — sənəd dövriyyəsindəki qısa işarə.": {
            "en": "May be left empty — the short code used in document circulation.",
            "ru": "Можно оставить пустым — краткое обозначение в документообороте.",
            "tr": "Boş bırakılabilir — evrak akışındaki kısa işaret.",
        },
        "İnzibati bölmə yaradıldı.": {
            "en": "The administrative unit has been created.",
            "ru": "Административное подразделение создано.",
            "tr": "İdari birim oluşturuldu.",
        },
        "Bölmə": {
            "en": "Unit",
            "ru": "Подразделение",
            "tr": "Birim",
        },
        "Tip": {
            "en": "Type",
            "ru": "Тип",
            "tr": "Tür",
        },
        "Rəhbər təyini, adın dəyişdirilməsi və arxivləmə «Universitet strukturu» ekranındadır — orada öz açarları ilə.": {
            "en": (
                "Head assignment, renaming and archiving are on the «University structure» screen — "
                "each with its own permission."
            ),
            "ru": (
                "Назначение руководителя, переименование и архивирование — на экране "
                "«Структура университета», каждое со своим правом."
            ),
            "tr": (
                "Yönetici ataması, ad değişikliği ve arşivleme «Üniversite yapısı» ekranındadır — "
                "her biri kendi yetkisiyle."
            ),
        },
        "Struktur ağacında aç": {
            "en": "Open in the structure tree",
            "ru": "Открыть в дереве структуры",
            "tr": "Yapı ağacında aç",
        },
        "Daha bir bölmə yarat": {
            "en": "Create another unit",
            "ru": "Создать ещё одно подразделение",
            "tr": "Bir birim daha oluştur",
        },
        "Bölməni yarat": {
            "en": "Create the unit",
            "ru": "Создать подразделение",
            "tr": "Birimi oluştur",
        },
        "Bölmə yaradılır…": {
            "en": "Creating the unit…",
            "ru": "Создание подразделения…",
            "tr": "Birim oluşturuluyor…",
        },
        "Bölmə yaradılmadı. Yenidən cəhd edin.": {
            "en": "The unit was not created. Please try again.",
            "ru": "Подразделение не создано. Попробуйте ещё раз.",
            "tr": "Birim oluşturulmadı. Yeniden deneyin.",
        },
        "Valideyn bölməni siyahıdan seçin.": {
            "en": "Pick the parent unit from the list.",
            "ru": "Выберите родительское подразделение из списка.",
            "tr": "Üst birimi listeden seçin.",
        },
        "Valideyn bölmə tapılmadı — siyahıdan yenidən seçin.": {
            "en": "The parent unit was not found — pick it from the list again.",
            "ru": "Родительское подразделение не найдено — выберите его из списка заново.",
            "tr": "Üst birim bulunamadı — listeden yeniden seçin.",
        },
        "Bölmənin adı boş ola bilməz.": {
            "en": "The unit name cannot be empty.",
            "ru": "Название подразделения не может быть пустым.",
            "tr": "Birim adı boş olamaz.",
        },
        "Bölmə tipi bu təşkilat üçün keçərli deyil.": {
            "en": "The unit type is not valid for this organisation.",
            "ru": "Тип подразделения недопустим для этой организации.",
            "tr": "Birim türü bu kurum için geçerli değil.",
        },
        "Struktur bölməsi yaratmaq üçün icazəniz yoxdur.": {
            "en": "You do not have permission to create a structural unit.",
            "ru": "У вас нет права создавать структурное подразделение.",
            "tr": "Yapısal birim oluşturma yetkiniz yok.",
        },
    },
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
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            head = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            probe = f'{head}msgid "{esc(msgid)}"\nmsgstr'
            if probe in text:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            blocks.append(f'{head}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1
    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
