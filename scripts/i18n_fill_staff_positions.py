#!/usr/bin/env python3
"""EMSArena i18n — vəzifə etiketi qatının sətirləri (4 dil). İdempotent.

«Üzv» doldurucusunun aradan qaldırılması + legacy vəzifə kateqoriyası +
`import_legacy_staff_positions` əmrinin hesabat sətirləri.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız ƏLAVƏ edir, mövcud girişə toxunmur.

⚠️ ŞABLON DIRNAQ TƏLƏSİ. Şablonlarda `{% trans "X" context "Y" %}` və
`{% trans 'X' context 'Y' %}` — HƏR İKİ forma işlənir. Buradakı ENTRIES xəritəsi
mətnləri AÇIQ sadaladığı üçün dırnaq forması nəticəyə TƏSİR ETMİR.

⚠️ AÇAR-ƏSASLI msgid («position» kimi) üçün AZ tərcüməsi də açıq verilməlidir —
əks halda AZ interfeysdə xam açar görünərdi. Ona görə hər giriş `az` açarını da
qəbul edir; verilməyibsə msgid-in özü AZ sayılır (AZ-msgid sxemi).

İstifadə:  python scripts/i18n_fill_staff_positions.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    # ── Profil kartındakı «Vəzifə» sətri (açar-əsaslı msgid) ────────────────
    "profile.info": {
        "position": {
            "az": "Vəzifə",
            "en": "Position",
            "ru": "Должность",
            "tr": "Görev",
        },
    },
    # ── Açıq profildəki struktur kartı ──────────────────────────────────────
    "profile.public": {
        "Vəzifə": {"en": "Position", "ru": "Должность", "tr": "Görev"},
    },
    # ── Legacy işçi kateqoriyası (core/staff_position.py) ───────────────────
    "organizations.staff_position": {
        "İnzibati işçi": {
            "en": "Administrative staff",
            "ru": "Административный сотрудник",
            "tr": "İdari personel",
        },
    },
    # ── `import_legacy_staff_positions` əmrinin çıxışı ──────────────────────
    "organizations.command.legacy_staff_positions": {
        "Mənbə faylı oxunmadı: {path}": {
            "en": "Could not read the source file: {path}",
            "ru": "Не удалось прочитать исходный файл: {path}",
            "tr": "Kaynak dosya okunamadı: {path}",
        },
        "Mənbə faylı düzgün JSON deyil: {path}": {
            "en": "The source file is not valid JSON: {path}",
            "ru": "Исходный файл не является корректным JSON: {path}",
            "tr": "Kaynak dosya geçerli JSON değil: {path}",
        },
        "Mənbə faylı JSON siyahısı olmalıdır.": {
            "en": "The source file must be a JSON list.",
            "ru": "Исходный файл должен быть списком JSON.",
            "tr": "Kaynak dosya bir JSON listesi olmalıdır.",
        },
        "Sətir {index}: «username» sahəsi tələb olunur.": {
            "en": "Row {index}: the “username” field is required.",
            "ru": "Строка {index}: поле «username» обязательно.",
            "tr": "Satır {index}: “username” alanı zorunludur.",
        },
        "Mənbə sətri: {count}": {
            "en": "Source rows: {count}",
            "ru": "Строк в источнике: {count}",
            "tr": "Kaynak satırı: {count}",
        },
        "Uyğunlaşdırılan hesab: {count}": {
            "en": "Matched accounts: {count}",
            "ru": "Сопоставлено учётных записей: {count}",
            "tr": "Eşleşen hesap: {count}",
        },
        "Hesabı tapılmayan sətir: {count}": {
            "en": "Rows with no matching account: {count}",
            "ru": "Строк без соответствующей учётной записи: {count}",
            "tr": "Hesabı bulunamayan satır: {count}",
        },
        "Vəzifəsi onsuz da doldurulmuş: {count}": {
            "en": "Position already filled in: {count}",
            "ru": "Должность уже заполнена: {count}",
            "tr": "Görevi zaten dolu olan: {count}",
        },
        "Vəzifə yazıldı: {count}": {
            "en": "Positions written: {count}",
            "ru": "Записано должностей: {count}",
            "tr": "Yazılan görev: {count}",
        },
        "Vəzifə yazılacaq: {count}": {
            "en": "Positions to be written: {count}",
            "ru": "Будет записано должностей: {count}",
            "tr": "Yazılacak görev: {count}",
        },
        "Quru işləyiş — heç nə yazılmadı (--apply ilə tətbiq edin).": {
            "en": "Dry run — nothing was written (use --apply to commit).",
            "ru": "Пробный запуск — ничего не записано (примените с --apply).",
            "tr": "Kuru çalışma — hiçbir şey yazılmadı (--apply ile uygulayın).",
        },
        "NAMƏLUM: «teacher_type» kodlarının mənası sənədləşdirilməyib — etiketə çevrilmədi.": {
            "en": (
                "UNKNOWN: the meaning of the “teacher_type” codes is undocumented "
                "— they were not turned into labels."
            ),
            "ru": ("НЕИЗВЕСТНО: значение кодов «teacher_type» не задокументировано " "— в метки они не превращались."),
            "tr": ("BİLİNMİYOR: “teacher_type” kodlarının anlamı belgelenmemiş " "— etikete dönüştürülmedi."),
        },
        "teacher_type={code}: {count} nəfər": {
            "en": "teacher_type={code}: {count} people",
            "ru": "teacher_type={code}: {count} чел.",
            "tr": "teacher_type={code}: {count} kişi",
        },
        "ƏL İLƏ TƏSDİQ — köhnə sistemdə «dekanlıq» səhifəsinə girişi olanlar:": {
            "en": "MANUAL CONFIRMATION — accounts that had access to the “deanery” page in the old system:",
            "ru": ("РУЧНОЕ ПОДТВЕРЖДЕНИЕ — у кого был доступ к странице " "«деканат» в старой системе:"),
            "tr": "ELLE ONAY — eski sistemde “dekanlık” sayfasına erişimi olanlar:",
        },
        "ƏL İLƏ TƏSDİQ — köhnə sistemdə «kafedra» səhifəsinə girişi olanlar:": {
            "en": "MANUAL CONFIRMATION — accounts that had access to the “department” page in the old system:",
            "ru": ("РУЧНОЕ ПОДТВЕРЖДЕНИЕ — у кого был доступ к странице " "«кафедра» в старой системе:"),
            "tr": "ELLE ONAY — eski sistemde “bölüm” sayfasına erişimi olanlar:",
        },
        "Rol və icazələr DƏYİŞMİR — bu əmr yalnız mətn etiketi yazır.": {
            "en": "Roles and permissions are UNCHANGED — this command only writes a text label.",
            "ru": "Роли и права НЕ МЕНЯЮТСЯ — команда записывает только текстовую метку.",
            "tr": "Roller ve izinler DEĞİŞMEZ — bu komut yalnızca metin etiketi yazar.",
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
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"'
            if probe in text:
                continue
            msgstr = translations.get(lang, msgid if lang == "az" else msgid)
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
