#!/usr/bin/env python3
"""EMSArena i18n — rol auditi 2026-10-13, B hissəsi (access: B3 / B14).

Əlavə olunan mətnlər:
  * `organizations.permission.label` — yeni `notification.publish` açarının etiketi (B14);
  * `teacher_intake` — «Müəllim idxalı» bölməsinin icazə mesajı indi `user.import_staff`-ı göstərir (B3).

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Orkestrator serial işlədir; sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_access_2026_10_13.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

PERM = "organizations.permission.label"
INTAKE = "teacher_intake"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    PERM: {
        "Bildiriş göndərmək (alıcılar öz əhatəsində)": {
            "en": "Send notifications (recipients within own scope)",
            "ru": "Отправка уведомлений (получатели в пределах своей области)",
            "tr": "Bildirim göndermek (alıcılar kendi kapsamında)",
        },
    },
    INTAKE: {
        "Toplu müəllim əlavəsi üçün icazəniz yoxdur — bu bölmə yalnız `user.import_staff` açarı olan rollar üçündür.": {
            "en": (
                "You do not have permission to add teachers in bulk — this section is only for roles with the "
                "`user.import_staff` key."
            ),
            "ru": (
                "У вас нет права на массовое добавление преподавателей — этот раздел только для ролей с ключом "
                "`user.import_staff`."
            ),
            "tr": (
                "Toplu öğretmen ekleme yetkiniz yok — bu bölüm yalnızca `user.import_staff` anahtarına sahip "
                "roller içindir."
            ),
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
