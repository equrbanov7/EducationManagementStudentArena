#!/usr/bin/env python3
"""EMSArena i18n — sadə parol siyasəti 2026-10-15.

Sahib: «Parolu təyin etməni yüngülləşdir, 8 simvol olsun, amma çox da zorlamasın … sadə kod qoymağa icazə
olsun». Əlavə olunan mətnlər:
  * `accounts.password_policy` — validator mesajları və ipucu (`apps/accounts/password_policy.py`);
  * `core.runtime_settings` — «Parolun minimum uzunluğu» tənzimləməsi (`core/runtime_settings.py`);
  * `profile.password` — «Şifrəni dəyiş» bölməsinin tələb kartı və göstərici etiketləri
    (`_change_password.html`);
  * `accounts.first_login` — ilk giriş səhifəsinin placeholder-i (`first_login_set_password.html`).

msgid AZ cümlədir → az msgstr = msgid. `{% blocktrans %}` dəyişəni kataloqda `%(ad)s` kimidir.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir (mövcudluq `polib`
ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_password_simple_2026_10_15.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

POLICY = "accounts.password_policy"
RUNTIME = "core.runtime_settings"
PROFILE = "profile.password"
FIRST_LOGIN = "accounts.first_login"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    POLICY: {
        "Ən azı %(min_length)d simvol. Yadda saxlaya biləcəyiniz sadə parol da olar.": {
            "en": "At least %(min_length)d characters. A simple password you can remember is fine too.",
            "ru": "Не менее %(min_length)d символов. Подойдёт и простой пароль, который вы легко запомните.",
            "tr": "En az %(min_length)d karakter. Hatırlayabileceğiniz basit bir parola da olur.",
            "de": "Mindestens %(min_length)d Zeichen. Ein einfaches Passwort, das Sie sich merken können, ist auch in "
            "Ordnung.",
        },
        "Parol ən azı %(min_length)d simvol olmalıdır.": {
            "en": "The password must be at least %(min_length)d characters long.",
            "ru": "Пароль должен содержать не менее %(min_length)d символов.",
            "tr": "Parola en az %(min_length)d karakter olmalıdır.",
            "de": "Das Passwort muss mindestens %(min_length)d Zeichen lang sein.",
        },
        "Bu parol çox asan təxmin olunur. Başqa birini seçin.": {
            "en": "This password is too easy to guess. Please choose another one.",
            "ru": "Этот пароль слишком легко угадать. Выберите другой.",
            "tr": "Bu parola çok kolay tahmin edilir. Lütfen başka bir parola seçin.",
            "de": "Dieses Passwort ist zu leicht zu erraten. Bitte wählen Sie ein anderes.",
        },
        "«12345678», «password» kimi çox yayılmış parollar və istifadəçi adınız olmaz.": {
            "en": "Very common passwords such as «12345678» or «password», and your username, are not allowed.",
            "ru": "Нельзя использовать очень распространённые пароли вроде «12345678», «password» и своё имя "
            "пользователя.",
            "tr": "«12345678», «password» gibi çok yaygın parolalar ve kullanıcı adınız kullanılamaz.",
            "de": "Sehr verbreitete Passwörter wie «12345678» oder «password» sowie Ihr Benutzername sind nicht "
            "erlaubt.",
        },
    },
    RUNTIME: {
        "Parolun minimum uzunluğu": {
            "en": "Minimum password length",
            "ru": "Минимальная длина пароля",
            "tr": "Minimum parola uzunluğu",
            "de": "Mindestlänge des Passworts",
        },
        "Yeni parol ən azı bu qədər simvol olmalıdır. Böyük hərf, rəqəm və ya simvol tələb olunmur — yalnız "
        "«12345678» kimi çox asan parollar və istifadəçi adı rədd edilir.": {
            "en": "A new password must have at least this many characters. Uppercase letters, digits or symbols are "
            "not required — only very easy passwords such as «12345678» and the username are rejected.",
            "ru": "Новый пароль должен содержать не менее указанного числа символов. Заглавные буквы, цифры или "
            "символы не требуются — отклоняются только очень простые пароли вроде «12345678» и имя пользователя.",
            "tr": "Yeni parola en az bu kadar karakter olmalıdır. Büyük harf, rakam veya sembol gerekmez — yalnızca "
            "«12345678» gibi çok kolay parolalar ve kullanıcı adı reddedilir.",
            "de": "Ein neues Passwort muss mindestens so viele Zeichen haben. Großbuchstaben, Ziffern oder Symbole "
            "sind nicht nötig — abgelehnt werden nur sehr einfache Passwörter wie «12345678» und der Benutzername.",
        },
        "simvol": {"en": "characters", "ru": "символов", "tr": "karakter", "de": "Zeichen"},
    },
    PROFILE: {
        "Hələ qısadır": {"en": "Still too short", "ru": "Пока коротко", "tr": "Henüz kısa", "de": "Noch zu kurz"},
        "Uyğundur": {"en": "Acceptable", "ru": "Подходит", "tr": "Uygun", "de": "Passt"},
        "Ən azı %(min_length)s simvol": {
            "en": "At least %(min_length)s characters",
            "ru": "Не менее %(min_length)s символов",
            "tr": "En az %(min_length)s karakter",
            "de": "Mindestens %(min_length)s Zeichen",
        },
        "«12345678», «password» kimi çox asan parol və ya istifadəçi adınız olmasın": {
            "en": "Not a very easy password such as «12345678» or «password», and not your username",
            "ru": "Не очень простой пароль вроде «12345678», «password» и не ваше имя пользователя",
            "tr": "«12345678», «password» gibi çok kolay bir parola veya kullanıcı adınız olmasın",
            "de": "Kein sehr einfaches Passwort wie «12345678» oder «password» und nicht Ihr Benutzername",
        },
        "Böyük hərf, rəqəm və ya simvol məcburi deyil — yadda saxlaya biləcəyiniz sadə parol da olar.": {
            "en": "Uppercase letters, digits or symbols are not required — a simple password you can remember is "
            "fine too.",
            "ru": "Заглавные буквы, цифры или символы не обязательны — подойдёт и простой пароль, который вы легко "
            "запомните.",
            "tr": "Büyük harf, rakam veya sembol zorunlu değildir — hatırlayabileceğiniz basit bir parola da olur.",
            "de": "Großbuchstaben, Ziffern oder Symbole sind nicht nötig — ein einfaches Passwort, das Sie sich merken "
            "können, ist auch in Ordnung.",
        },
    },
    FIRST_LOGIN: {
        "ən azı %(min_length)s simvol": {
            "en": "at least %(min_length)s characters",
            "ru": "не менее %(min_length)s символов",
            "tr": "en az %(min_length)s karakter",
            "de": "mindestens %(min_length)s Zeichen",
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
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
            flag = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flag}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
