#!/usr/bin/env python3
"""EMSArena i18n — rol auditi 2026-10-13 B (struct): B9 struktur reyestri rol təyinatı, B15 rol kataloqu.

Əlavə olunan mətnlər:
  * `organizations.registry` — struktur reyestrinin yeni 403 mesajları (rəhbər / müavin / koordinator
    təyinatı və silinməsi artıq `member.edit` ilə yox, `role.assign` / `unit.assign_head` ilə);
  * `organizations.roles_registry` — «Təşkilat rolları» bölməsinin `role.view`-suz boş vəziyyəti.

msgid AZ cümlədir → az msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Orkestrator serial işlədir; sonra `compilemessages`.

İstifadə:  python scripts/i18n_fill_struct_2026_10_13.py
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

REGISTRY = "organizations.registry"
ROLES = "organizations.roles_registry"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    REGISTRY: {
        "Rəhbər təyini üçün `role.assign` və ya `unit.assign_head` lazımdır.": {
            "en": "Assigning a head requires `role.assign` or `unit.assign_head`.",
            "ru": "Для назначения руководителя нужно право `role.assign` или `unit.assign_head`.",
            "tr": "Yönetici atamak için `role.assign` veya `unit.assign_head` yetkisi gerekir.",
        },
        "Rol təyinatı üçün `role.assign` səlahiyyəti lazımdır.": {
            "en": "Assigning a role requires the `role.assign` permission.",
            "ru": "Для назначения роли нужно право `role.assign`.",
            "tr": "Rol atamak için `role.assign` yetkisi gerekir.",
        },
        "Bu rol təyinatını silmək üçün `role.assign` səlahiyyəti lazımdır.": {
            "en": "Removing this role assignment requires the `role.assign` permission.",
            "ru": "Чтобы снять это назначение роли, нужно право `role.assign`.",
            "tr": "Bu rol atamasını kaldırmak için `role.assign` yetkisi gerekir.",
        },
    },
    ROLES: {
        "Rol kataloquna baxmaq üçün «role.view» icazəsi lazımdır.": {
            "en": "Viewing the role catalogue requires the «role.view» permission.",
            "ru": "Для просмотра каталога ролей нужно право «role.view».",
            "tr": "Rol kataloğunu görüntülemek için «role.view» yetkisi gerekir.",
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
