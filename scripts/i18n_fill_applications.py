#!/usr/bin/env python3
"""EMSArena i18n — «Müraciətlər» modulunun sətirləri (4 dil). İdempotent.

Statuslar, zaman xətti hadisələri, göndərən ailələri, aidiyyət qaydaları,
model adları və üç icazə etiketi.

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
ƏLAVƏ edir və mövcud girişə TOXUNMUR.

İstifadə:  python scripts/i18n_fill_applications.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

_STATUS = {
    "Yeni": {"en": "New", "ru": "Новое", "tr": "Yeni"},
    "Baxılır": {"en": "In review", "ru": "На рассмотрении", "tr": "İnceleniyor"},
    "Təyin edilib": {"en": "Assigned", "ru": "Назначено", "tr": "Atandı"},
    "Yönləndirilib": {"en": "Forwarded", "ru": "Перенаправлено", "tr": "Yönlendirildi"},
    "Məlumat gözlənilir": {"en": "Awaiting information", "ru": "Ожидается информация", "tr": "Bilgi bekleniyor"},
    "Düzəliş üçün qaytarılıb": {
        "en": "Returned for correction",
        "ru": "Возвращено на доработку",
        "tr": "Düzeltme için iade edildi",
    },
    "Həll olunub": {"en": "Resolved", "ru": "Решено", "tr": "Çözüldü"},
    "Rədd edilib": {"en": "Rejected", "ru": "Отклонено", "tr": "Reddedildi"},
    "Bağlanıb": {"en": "Closed", "ru": "Закрыто", "tr": "Kapatıldı"},
    "Ləğv edilib": {"en": "Cancelled", "ru": "Отменено", "tr": "İptal edildi"},
}

_EVENTS = {
    "Göndərildi": {"en": "Submitted", "ru": "Отправлено", "tr": "Gönderildi"},
    "Baxışa götürüldü": {"en": "Taken into review", "ru": "Принято к рассмотрению", "tr": "İncelemeye alındı"},
    "Qeyd": {"en": "Note", "ru": "Заметка", "tr": "Not"},
    "Məsul şəxsə təyin edildi": {
        "en": "Assigned to a responsible person",
        "ru": "Назначено ответственному",
        "tr": "Sorumlu kişiye atandı",
    },
    "Əlavə məlumat istənildi": {
        "en": "Additional information requested",
        "ru": "Запрошена дополнительная информация",
        "tr": "Ek bilgi istendi",
    },
    "Əlavə məlumat verildi": {
        "en": "Additional information provided",
        "ru": "Предоставлена дополнительная информация",
        "tr": "Ek bilgi verildi",
    },
    "Başqa şöbəyə yönləndirildi": {
        "en": "Forwarded to another unit",
        "ru": "Перенаправлено в другое подразделение",
        "tr": "Başka birime yönlendirildi",
    },
    "Düzəliş üçün qaytarıldı": {
        "en": "Returned for correction",
        "ru": "Возвращено на доработку",
        "tr": "Düzeltme için iade edildi",
    },
    "Düzəlişdən sonra yenidən göndərildi": {
        "en": "Resubmitted after correction",
        "ru": "Повторно отправлено после доработки",
        "tr": "Düzeltmeden sonra yeniden gönderildi",
    },
    "Həll olundu": {"en": "Resolved", "ru": "Решено", "tr": "Çözüldü"},
    "Rədd edildi": {"en": "Rejected", "ru": "Отклонено", "tr": "Reddedildi"},
    "Bağlandı": {"en": "Closed", "ru": "Закрыто", "tr": "Kapatıldı"},
    "Ləğv edildi": {"en": "Cancelled", "ru": "Отменено", "tr": "İptal edildi"},
}

_FAMILIES = {
    "Tələbə": {"en": "Student", "ru": "Студент", "tr": "Öğrenci"},
    "Müəllim": {"en": "Teacher", "ru": "Преподаватель", "tr": "Öğretim elemanı"},
    "Əməkdaş": {"en": "Staff member", "ru": "Сотрудник", "tr": "Personel"},
}

_RESOLVE_BY = {
    "Bütün təşkilat (mərkəzi şöbə)": {
        "en": "The whole organization (central unit)",
        "ru": "Вся организация (центральное подразделение)",
        "tr": "Tüm kurum (merkezi birim)",
    },
    "Göndərənin fakültəsi": {
        "en": "The sender's faculty",
        "ru": "Факультет отправителя",
        "tr": "Gönderenin fakültesi",
    },
    "Göndərənin kafedrası": {
        "en": "The sender's department",
        "ru": "Кафедра отправителя",
        "tr": "Gönderenin bölümü",
    },
    "Göndərənin ixtisası": {
        "en": "The sender's specialty",
        "ru": "Специальность отправителя",
        "tr": "Gönderenin uzmanlık alanı",
    },
}

_MODELS = {
    "müraciət": {"en": "application", "ru": "обращение", "tr": "başvuru"},
    "müraciətlər": {"en": "applications", "ru": "обращения", "tr": "başvurular"},
    "müraciət şöbəsi": {"en": "application unit", "ru": "подразделение обращений", "tr": "başvuru birimi"},
    "müraciət şöbələri": {"en": "application units", "ru": "подразделения обращений", "tr": "başvuru birimleri"},
    "müraciət növü": {"en": "application kind", "ru": "тип обращения", "tr": "başvuru türü"},
    "müraciət növləri": {"en": "application kinds", "ru": "типы обращений", "tr": "başvuru türleri"},
    "müraciət nömrə sayğacı": {
        "en": "application number counter",
        "ru": "счётчик номеров обращений",
        "tr": "başvuru numarası sayacı",
    },
    "müraciət nömrə sayğacları": {
        "en": "application number counters",
        "ru": "счётчики номеров обращений",
        "tr": "başvuru numarası sayaçları",
    },
    "müraciət hadisəsi": {"en": "application event", "ru": "событие обращения", "tr": "başvuru olayı"},
    "müraciət hadisələri": {"en": "application events", "ru": "события обращений", "tr": "başvuru olayları"},
    "müraciət izləməsi": {"en": "application watch", "ru": "наблюдение за обращением", "tr": "başvuru takibi"},
    "müraciət izləmələri": {
        "en": "application watches",
        "ru": "наблюдения за обращениями",
        "tr": "başvuru takipleri",
    },
    "müraciət sənədi": {"en": "application attachment", "ru": "документ обращения", "tr": "başvuru belgesi"},
    "müraciət sənədləri": {"en": "application attachments", "ru": "документы обращений", "tr": "başvuru belgeleri"},
}

_PERMISSIONS = {
    "Müraciət göndərmək": {"en": "Submit an application", "ru": "Отправлять обращение", "tr": "Başvuru göndermek"},
    "Gələn müraciətə baxmaq və qərar vermək": {
        "en": "Review an incoming application and decide on it",
        "ru": "Рассматривать поступившее обращение и принимать решение",
        "tr": "Gelen başvuruyu incelemek ve karar vermek",
    },
    "Müraciət kataloqunu idarə etmək və hamısına baxmaq": {
        "en": "Manage the application catalogue and read every application",
        "ru": "Управлять каталогом обращений и просматривать все обращения",
        "tr": "Başvuru kataloğunu yönetmek ve tümünü görüntülemek",
    },
}

ENTRIES = {
    "applications": {**_STATUS, **_EVENTS, **_FAMILIES, **_RESOLVE_BY, **_MODELS},
    "organizations.permission.label": _PERMISSIONS,
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
            probe = f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n'
            if probe in text:
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
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
