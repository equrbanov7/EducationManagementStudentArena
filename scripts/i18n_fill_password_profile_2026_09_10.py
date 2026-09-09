#!/usr/bin/env python3
"""EMSArena i18n — «Şifrəni dəyiş» + «Profili redaktə et» redizayn mətnləri (4 dil).

2026-09-10 sahib rəyi: «profil redaktə etmək və şifrəni dəyişmək hissələrini
tam profesional … modern ux/ui prinsipləri əsasında yenidən dizayn et».
Redizayn canlı şifrə güc göstəricisi, tələb siyahısı, göz düyməsi, Caps Lock
xəbərdarlığı və avatar seçicisi gətirdi — hamısı yeni mətndir.

Kontekstlər: `profile.password` (şifrə bölməsi), `profile.edit_v2` (redaktə).

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
ƏLAVƏ edir və idempotentdir.

İstifadə:  python scripts/i18n_fill_password_profile_2026_09_10.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "profile.password": {
        # ── Altbaşlıq ───────────────────────────────────────────────────────
        (
            "Şifrəni ya mövcud şifrənizlə, ya da e-poçtunuza gələn birdəfəlik kodla "
            "dəyişə bilərsiniz. Dəyişiklikdən sonra digər cihazlardakı sessiyalar qüvvədə qalır."
        ): {
            "en": (
                "You can change your password either with your current password or with a "
                "one-time code sent to your e-mail. Sessions on your other devices stay signed in."
            ),
            "ru": (
                "Пароль можно изменить с помощью текущего пароля или одноразового кода, "
                "отправленного на вашу почту. Сессии на других устройствах останутся активными."
            ),
            "tr": (
                "Şifrenizi mevcut şifrenizle ya da e-postanıza gelen tek kullanımlık kodla "
                "değiştirebilirsiniz. Diğer cihazlardaki oturumlar açık kalır."
            ),
        },
        # ── Sahə köməkçiləri ────────────────────────────────────────────────
        "Şifrəni göstər / gizlət": {
            "en": "Show / hide password",
            "ru": "Показать / скрыть пароль",
            "tr": "Şifreyi göster / gizle",
        },
        "Caps Lock açıqdır.": {
            "en": "Caps Lock is on.",
            "ru": "Включён Caps Lock.",
            "tr": "Caps Lock açık.",
        },
        "Şifrələr uyğundur.": {
            "en": "The passwords match.",
            "ru": "Пароли совпадают.",
            "tr": "Şifreler eşleşiyor.",
        },
        "Şifrələr eyni deyil.": {
            "en": "The passwords do not match.",
            "ru": "Пароли не совпадают.",
            "tr": "Şifreler aynı değil.",
        },
        # ── Güc göstəricisi ─────────────────────────────────────────────────
        "Şifrə hələ yazılmayıb": {
            "en": "No password entered yet",
            "ru": "Пароль ещё не введён",
            "tr": "Henüz şifre girilmedi",
        },
        "Zəif": {"en": "Weak", "ru": "Слабый", "tr": "Zayıf"},
        "Orta": {"en": "Fair", "ru": "Средний", "tr": "Orta"},
        "Yaxşı": {"en": "Good", "ru": "Хороший", "tr": "İyi"},
        "Güclü": {"en": "Strong", "ru": "Надёжный", "tr": "Güçlü"},
        # ── Tələb siyahısı ──────────────────────────────────────────────────
        "Şifrə tələbləri": {
            "en": "Password requirements",
            "ru": "Требования к паролю",
            "tr": "Şifre gereksinimleri",
        },
        "Ən azı 8 simvol": {
            "en": "At least 8 characters",
            "ru": "Не менее 8 символов",
            "tr": "En az 8 karakter",
        },
        "Yalnız rəqəmlərdən ibarət olmasın": {
            "en": "Must not be entirely numeric",
            "ru": "Не должен состоять только из цифр",
            "tr": "Yalnızca rakamlardan oluşmamalı",
        },
        "Ad, soyad, istifadəçi adı və ya e-poçtla oxşar olmasın": {
            "en": "Must not resemble your name, surname, username or e-mail",
            "ru": "Не должен быть похож на имя, фамилию, логин или почту",
            "tr": "Ad, soyad, kullanıcı adı veya e-posta ile benzer olmamalı",
        },
        "Böyük/kiçik hərf, rəqəm və simvol qarışığı tövsiyə olunur": {
            "en": "A mix of upper/lower case, digits and symbols is recommended",
            "ru": "Рекомендуется сочетание строчных и прописных букв, цифр и символов",
            "tr": "Büyük/küçük harf, rakam ve sembol karışımı önerilir",
        },
        "Geniş yayılmış şifrələr (məsələn «12345678», «password») server tərəfindən rədd edilir.": {
            "en": "Common passwords (for example “12345678”, “password”) are rejected by the server.",
            "ru": "Распространённые пароли (например «12345678», «password») отклоняются сервером.",
            "tr": "Yaygın şifreler (örneğin “12345678”, “password”) sunucu tarafından reddedilir.",
        },
    },
    "profile.edit_v2": {
        (
            "Şəxsi əlaqə məlumatlarınızı və akademik profilinizi buradan yeniləyin. "
            "Universitetin təyin etdiyi struktur məlumatları yalnız oxunur."
        ): {
            "en": (
                "Update your personal contact details and academic profile here. "
                "Structural data assigned by the university is read-only."
            ),
            "ru": (
                "Здесь можно обновить личные контактные данные и академический профиль. "
                "Структурные данные, заданные университетом, доступны только для чтения."
            ),
            "tr": (
                "Kişisel iletişim bilgilerinizi ve akademik profilinizi buradan güncelleyin. "
                "Üniversitenin belirlediği yapısal bilgiler yalnızca okunabilir."
            ),
        },
        "Şəkil seç": {"en": "Choose image", "ru": "Выбрать изображение", "tr": "Görsel seç"},
        "PNG və ya JPG · maksimum 5 MB": {
            "en": "PNG or JPG · 5 MB maximum",
            "ru": "PNG или JPG · максимум 5 МБ",
            "tr": "PNG veya JPG · en fazla 5 MB",
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
