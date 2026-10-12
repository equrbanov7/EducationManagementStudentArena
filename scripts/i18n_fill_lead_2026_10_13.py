#!/usr/bin/env python3
"""EMSArena i18n — rol auditi 2026-10-13 B10 «Qrupum» (baş tələbə) bölməsi (lead).

Əlavə olunan mətnlər:
  * `profile.sidebar` — «Qrupum» menyu bəndi / bölmə başlığı;
  * `accounts.my_group` — panel mətnləri (`sections/_my_group.html`).
msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Orkestrator serial işlədir; sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_lead_2026_10_13.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

SIDEBAR = "profile.sidebar"
MG = "accounts.my_group"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    SIDEBAR: {
        "Qrupum": {"en": "My group", "ru": "Моя группа", "tr": "Grubum"},
    },
    MG: {
        "Sizə təyin olunmuş akademik qrup tapılmadı.": {
            "en": "No academic group is assigned to you.",
            "ru": "Закреплённая за вами академическая группа не найдена.",
            "tr": "Size atanmış bir akademik grup bulunamadı.",
        },
        "Qrup nümayəndəsi rolu qrupa bağlanmayıb. Dekanlığa müraciət edin.": {
            "en": "Your group representative role is not linked to a group. Please contact the dean's office.",
            "ru": "Роль старосты не привязана к группе. Обратитесь в деканат.",
            "tr": "Grup temsilcisi rolünüz bir gruba bağlı değil. Lütfen dekanlığa başvurun.",
        },
        "Tələbə sayı: %(total)s": {
            "en": "Students: %(total)s",
            "ru": "Студентов: %(total)s",
            "tr": "Öğrenci sayısı: %(total)s",
        },
        ("Davamiyyət: %(period)s %(year)s — qayıb saatı və dərs saatına nisbəti (faiz). " "Yalnız baxış üçündür."): {
            "en": "Attendance: %(period)s %(year)s — absence hours and their share of class hours (percent). View only.",
            "ru": (
                "Посещаемость: %(period)s %(year)s — часы пропусков и их доля от учебных часов (процент). "
                "Только просмотр."
            ),
            "tr": (
                "Devam durumu: %(period)s %(year)s — devamsızlık saatleri ve ders saatine oranı (yüzde). "
                "Yalnızca görüntüleme."
            ),
        },
        "Cari tədris dövrü müəyyən edilməyib — yalnız qrup siyahısı göstərilir.": {
            "en": "The current academic period is not set — only the group list is shown.",
            "ru": "Текущий учебный период не определён — показан только список группы.",
            "tr": "Geçerli akademik dönem belirlenmemiş — yalnızca grup listesi gösteriliyor.",
        },
        "Qrupda qeydiyyatlı tələbə yoxdur.": {
            "en": "There are no enrolled students in the group.",
            "ru": "В группе нет зачисленных студентов.",
            "tr": "Grupta kayıtlı öğrenci yok.",
        },
        "%(group)s qrupunun tələbələri və fənn üzrə davamiyyəti": {
            "en": "Students of group %(group)s and their attendance by subject",
            "ru": "Студенты группы %(group)s и их посещаемость по предметам",
            "tr": "%(group)s grubunun öğrencileri ve derslere göre devam durumu",
        },
        "Tələbə": {"en": "Student", "ru": "Студент", "tr": "Öğrenci"},
        "Tələbə nömrəsi": {"en": "Student number", "ru": "Номер студента", "tr": "Öğrenci numarası"},
        "Ümumi qayıb": {"en": "Total absences", "ru": "Всего пропусков", "tr": "Toplam devamsızlık"},
        "%(absence)s / %(hours)s saat": {
            "en": "%(absence)s / %(hours)s hours",
            "ru": "%(absence)s / %(hours)s ч",
            "tr": "%(absence)s / %(hours)s saat",
        },
        "Bu fənnə yazılmayıb": {
            "en": "Not enrolled in this subject",
            "ru": "Не записан на этот предмет",
            "tr": "Bu derse kayıtlı değil",
        },
        "Rəng izahı": {"en": "Colour legend", "ru": "Обозначения цветов", "tr": "Renk açıklaması"},
        "Qayıb həddinə yaxındır": {
            "en": "Close to the absence limit",
            "ru": "Близко к лимиту пропусков",
            "tr": "Devamsızlık sınırına yakın",
        },
        "Qayıb həddi aşılıb": {
            "en": "Absence limit exceeded",
            "ru": "Лимит пропусков превышен",
            "tr": "Devamsızlık sınırı aşıldı",
        },
        "Bu dövr üçün fənn yazılışı hələ yoxdur.": {
            "en": "There are no subject enrolments for this period yet.",
            "ru": "Записей на предметы в этом периоде пока нет.",
            "tr": "Bu dönem için henüz ders kaydı yok.",
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
            if f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\n' in text:
                continue
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
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
