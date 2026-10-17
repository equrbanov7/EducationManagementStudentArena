#!/usr/bin/env python3
"""EMSArena i18n — FIX-H (QA dalğası 2026-10-17: QA-2 / SEC-1 / SEC-2 qalıqları).

Əlavə olunan mətnlər:
  * `accounts.password_policy` — rəhbər hesabında tam rəqəm / tarix parolu (SEC-1 F5);
  * `core.runtime_settings` — `password.min_length` izahı (alt hədd 8, rəhbər qaydası);
  * `accounts.runtime_settings` — rate pəncərəsi xətası (QA-2 F-09);
  * `accounts.schedule_editor` — əhatədən kənar / olmayan qrup və dərs 404 mətni (QA-2 F-09);
  * `accounts.schedule_manage` — rəqəmli korpus adı «Korpus 1» (QA-2 F-11).

QA-2 F-15: «Sistem tənzimləmələri» izahlarında «Söndürülüdə» / «Yanılıda» / «Yanılıdırsa» qeyri-sözləri
«Söndürüləndə» / «Yandırılanda» / «Yandırılıbsa» ilə əvəzləndi (``core/runtime_settings.py``). msgid dəyişdiyi üçün
həmin girişlər YENİ msgid ilə əlavə olunur, en/ru/tr/de tərcüməsi köhnə msgid-in mövcud tərcüməsindən götürülür
(mətnin mənası dəyişməyib — yalnız AZ yazılışı düzəlib). Köhnə girişlər faylda qalır (zərərsizdir).

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir (mövcudluq `polib`
ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_fixh_2026_10_17.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

PW = "accounts.password_policy"
RS = "core.runtime_settings"
RSA = "accounts.runtime_settings"
SE = "accounts.schedule_editor"
SM = "accounts.schedule_manage"

#: QA-2 F-15 — ``core/runtime_settings.py``-dakı ilə EYNİ əvəzləmə (sıra vacibdir: uzun söz əvvəl).
RS_WORD_FIXES = (
    ("Söndürülüdə", "Söndürüləndə"),
    ("Yanılıdırsa", "Yandırılıbsa"),
    ("yanılıdırsa", "yandırılıbsa"),
    ("Yanılıda", "Yandırılanda"),
)

MIN_LENGTH_HELP = (
    "Yeni parol ən azı bu qədər simvol olmalıdır (8-dən az olmaz). Böyük hərf, rəqəm və ya simvol "
    "tələb olunmur — yalnız «12345678» kimi çox asan parollar və istifadəçi adı rədd edilir. Rəhbər "
    "hesablarda (superadmin, RİM rəhbəri, rektor, Qəyyumlar Şurasının sədri) yalnız rəqəmdən və ya "
    "tarixdən ibarət parol da qəbul olunmur."
)

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    PW: {
        "Rəhbər hesabı üçün yalnız rəqəmdən və ya tarixdən ibarət parol olmaz — ən azı bir hərf əlavə edin.": {
            "en": "For a leadership account the password cannot consist only of digits or a date — add at least "
            "one letter.",
            "ru": "Для руководящей учётной записи пароль не может состоять только из цифр или даты — добавьте хотя "
            "бы одну букву.",
            "tr": "Yönetici hesabı için parola yalnızca rakamlardan veya bir tarihten oluşamaz — en az bir harf "
            "ekleyin.",
            "de": "Bei einem Leitungskonto darf das Passwort nicht nur aus Ziffern oder einem Datum bestehen – "
            "fügen Sie mindestens einen Buchstaben hinzu.",
        },
        "Rəhbər hesablarda parol yalnız rəqəmdən və ya tarixdən ibarət ola bilməz.": {
            "en": "On leadership accounts the password cannot consist only of digits or a date.",
            "ru": "В руководящих учётных записях пароль не может состоять только из цифр или даты.",
            "tr": "Yönetici hesaplarında parola yalnızca rakamlardan veya bir tarihten oluşamaz.",
            "de": "Bei Leitungskonten darf das Passwort nicht nur aus Ziffern oder einem Datum bestehen.",
        },
    },
    RS: {
        MIN_LENGTH_HELP: {
            "en": "A new password must be at least this many characters long (no fewer than 8). Capital letters, "
            "digits or symbols are not required — only very easy passwords such as «12345678» and the username "
            "are rejected. On leadership accounts (superadmin, head of RİM, rector, chair of the Board of "
            "Trustees) a password made only of digits or a date is not accepted either.",
            "ru": "Новый пароль должен содержать не меньше указанного числа символов (не меньше 8). Заглавные "
            "буквы, цифры или символы не требуются — отклоняются только очень простые пароли вроде «12345678» "
            "и имя пользователя. Для руководящих учётных записей (суперадмин, руководитель РИМ, ректор, "
            "председатель Попечительского совета) не принимается и пароль только из цифр или даты.",
            "tr": "Yeni parola en az bu kadar karakterden oluşmalıdır (8'den az olamaz). Büyük harf, rakam veya "
            "sembol gerekmez — yalnızca «12345678» gibi çok kolay parolalar ve kullanıcı adı reddedilir. "
            "Yönetici hesaplarında (süper yönetici, RİM başkanı, rektör, Mütevelli Heyeti başkanı) yalnızca "
            "rakamlardan veya bir tarihten oluşan parola da kabul edilmez.",
            "de": "Ein neues Passwort muss mindestens so viele Zeichen haben (nicht weniger als 8). Großbuchstaben, "
            "Ziffern oder Sonderzeichen sind nicht erforderlich – abgelehnt werden nur sehr einfache Passwörter "
            "wie «12345678» und der Benutzername. Bei Leitungskonten (Superadmin, RİM-Leitung, Rektor, Vorsitz "
            "des Kuratoriums) wird auch ein Passwort nur aus Ziffern oder einem Datum nicht akzeptiert.",
        },
    },
    SE: {
        "Qrup tapılmadı və ya əhatənizdə deyil.": {
            "en": "Group not found or outside your scope.",
            "ru": "Группа не найдена или вне вашей зоны ответственности.",
            "tr": "Grup bulunamadı veya yetki alanınızın dışında.",
            "de": "Gruppe nicht gefunden oder außerhalb Ihres Zuständigkeitsbereichs.",
        },
        "Dərs tapılmadı və ya əhatənizdə deyil.": {
            "en": "Lesson not found or outside your scope.",
            "ru": "Занятие не найдено или вне вашей зоны ответственности.",
            "tr": "Ders bulunamadı veya yetki alanınızın dışında.",
            "de": "Unterrichtsstunde nicht gefunden oder außerhalb Ihres Zuständigkeitsbereichs.",
        },
    },
    SM: {
        # QA-2 F-11: yalnız rəqəmdən ibarət korpus adı seçicidə «Korpus 1».
        "Korpus %(number)s": {
            "en": "Building %(number)s",
            "ru": "Корпус %(number)s",
            "tr": "Bina %(number)s",
            "de": "Gebäude %(number)s",
        },
    },
    RSA: {
        "Müddət 1–1440 dəqiqə (24 saat) aralığında olmalıdır.": {
            "en": "The window must be between 1 and 1440 minutes (24 hours).",
            "ru": "Период должен быть от 1 до 1440 минут (24 часа).",
            "tr": "Süre 1–1440 dakika (24 saat) aralığında olmalıdır.",
            "de": "Das Zeitfenster muss zwischen 1 und 1440 Minuten (24 Stunden) liegen.",
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fixed_msgid(msgid):
    for old, new in RS_WORD_FIXES:
        msgid = msgid.replace(old, new)
    return msgid


def renamed_entries(po):
    """QA-2 F-15: köhnə yazılışlı ``core.runtime_settings`` girişləri → (yeni msgid, köhnə tərcümə)."""
    for entry in po:
        if entry.obsolete or entry.msgctxt != RS:
            continue
        new_msgid = fixed_msgid(entry.msgid)
        if new_msgid != entry.msgid:
            yield new_msgid, entry.msgstr


def fill(lang):
    path = po_path(lang)
    po = polib.pofile(path)
    existing = {(entry.msgctxt, entry.msgid) for entry in po if not entry.obsolete}
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
            blocks.append(f'msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            existing.add((ctx, msgid))
            added += 1

    for new_msgid, old_msgstr in renamed_entries(po):
        if (RS, new_msgid) in existing:
            continue
        msgstr = new_msgid if lang == "az" else (old_msgstr or new_msgid)
        blocks.append(f'msgctxt "{esc(RS)}"\nmsgid "{esc(new_msgid)}"\nmsgstr "{esc(msgstr)}"\n')
        existing.add((RS, new_msgid))
        added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
