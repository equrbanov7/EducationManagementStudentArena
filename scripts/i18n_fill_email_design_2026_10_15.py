#!/usr/bin/env python3
"""EMSArena i18n — vahid müasir e-poçt şablonu 2026-10-15.

Sahib: «Mailə gələn template-in dizaynını yaxşılaşdır.» Bütün məktublar
`templates/emails/base_email.html` / `base_email.txt`-dən törəyir. Əlavə olunan
mətnlər (`email.layout` konteksti):
  * altlıq — «avtomatik göndərilib, cavab yazmayın» + dəstək ünvanı sətri;
  * düymənin altındakı link ehtiyatı;
  * OTP qutusunun etibarlılıq sətri və gizli önbaxış (preheader) mətni;
  * linksiz təsdiq məktubunun giriş cümləsi (əvvəl «addımlardan birini» deyirdi, halbuki yalnız kod var);
  * blog bildirişinin «Postu oxu» düyməsi (əvvəl sabit AZ idi).

Məktub BİR dildə render olunur (`translation.override`, sahib 2026-09-21) — ona görə
hər dil tam doldurulur. msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir (mövcudluq `polib` ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_email_design_2026_10_15.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

LAYOUT = "email.layout"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    LAYOUT: {
        "Bu məktub avtomatik göndərilib, cavab yazmayın.": {
            "en": "This email was sent automatically; please do not reply.",
            "ru": "Это письмо отправлено автоматически, пожалуйста, не отвечайте на него.",
            "tr": "Bu e-posta otomatik olarak gönderildi, lütfen yanıtlamayın.",
            "de": "Diese E-Mail wurde automatisch versendet, bitte antworten Sie nicht darauf.",
        },
        "Sualınız varsa, yazın:": {
            "en": "Questions? Write to:",
            "ru": "Есть вопросы? Пишите:",
            "tr": "Sorunuz varsa yazın:",
            "de": "Fragen? Schreiben Sie an:",
        },
        "Düymə işləmirsə, bu linki brauzerinizə köçürün:": {
            "en": "If the button does not work, copy this link into your browser:",
            "ru": "Если кнопка не работает, скопируйте эту ссылку в браузер:",
            "tr": "Düğme çalışmıyorsa bu bağlantıyı tarayıcınıza kopyalayın:",
            "de": "Falls die Schaltfläche nicht funktioniert, kopieren Sie diesen Link in Ihren Browser:",
        },
        "Kodunuz: %(code)s · %(minutes)s dəqiqə etibarlıdır": {
            "en": "Your code: %(code)s · valid for %(minutes)s minutes",
            "ru": "Ваш код: %(code)s · действует %(minutes)s мин.",
            "tr": "Kodunuz: %(code)s · %(minutes)s dakika geçerlidir",
            "de": "Ihr Code: %(code)s · %(minutes)s Minuten gültig",
        },
        "Etibarlılıq müddəti: %(minutes)s dəqiqə": {
            "en": "Valid for %(minutes)s minutes",
            "ru": "Срок действия: %(minutes)s мин.",
            "tr": "Geçerlilik süresi: %(minutes)s dakika",
            "de": "Gültigkeit: %(minutes)s Minuten",
        },
        "Salam <strong>%(name)s</strong>, %(action)s üçün aşağıdakı kodu daxil edin.": {
            "en": "Hello <strong>%(name)s</strong>, enter the code below for %(action)s.",
            "ru": "Здравствуйте, <strong>%(name)s</strong>, введите приведённый ниже код для %(action)s.",
            "tr": "Merhaba <strong>%(name)s</strong>, %(action)s için aşağıdaki kodu girin.",
            "de": "Hallo <strong>%(name)s</strong>, geben Sie für %(action)s den folgenden Code ein.",
        },
        "Postu oxu": {
            "en": "Read the post",
            "ru": "Читать публикацию",
            "tr": "Yazıyı oku",
            "de": "Beitrag lesen",
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
