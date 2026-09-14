#!/usr/bin/env python3
"""EMSArena i18n — dalğa 2 (2026-09-14), audit FE-F17: ikon-only düymələrin `aria-label`-ları.

Audit (docs/audits/2026-09-13-claude/findings/frontend.md §3, F17) kabinetdən
kənar 18 ikon-only düymədə əlçatan ad tapmadı. Mümkün olan yerlərdə mövcud
msgid-lər işlədildi (`Axtar`/`search`, `Bağla`/`ui.dialog`,
`action_edit`/`action_delete`/`labs.template.manage_blocks`); qalanları üçün
aşağıdakı yeni (kontekst, msgid) cütləri əlavə olunur. msgid AZ mətndir —
az kataloqunda msgstr = msgid.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Orkestrator fill skriptlərini ardıcıl işə salır.

İstifadə:  python scripts/i18n_fill_w2a11y_2026_09_14.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

ENTRIES = {
    "assignment.legacy.review": {
        "Tapşırığı redaktə et": {"en": "Edit assignment", "ru": "Редактировать задание", "tr": "Ödevi düzenle"},
        "Tapşırığı sil": {"en": "Delete assignment", "ru": "Удалить задание", "tr": "Ödevi sil"},
    },
    "exams.template.teacher_group_list": {
        "Qrupu redaktə et": {"en": "Edit group", "ru": "Редактировать группу", "tr": "Grubu düzenle"},
        "Qrupu sil": {"en": "Delete group", "ru": "Удалить группу", "tr": "Grubu sil"},
    },
    "assignment.detail": {
        "Seçilmiş faylı sil": {
            "en": "Remove selected file",
            "ru": "Убрать выбранный файл",
            "tr": "Seçilen dosyayı kaldır",
        },
    },
    "courses.members_page": {
        "Üzvü kursdan sil": {
            "en": "Remove member from course",
            "ru": "Удалить участника из курса",
            "tr": "Üyeyi kurstan çıkar",
        },
    },
    "courses.partial.member_accordion": {
        "Üzvü kursdan sil": {
            "en": "Remove member from course",
            "ru": "Удалить участника из курса",
            "tr": "Üyeyi kurstan çıkar",
        },
    },
    # FE-F19: superadmin təşkilat sorğusu «Rədd et» təsdiqi (şablon kontekstsiz `{% trans %}` işlədir).
    "": {
        "Təşkilatın qeydiyyat sorğusu rədd edilsin? Bu əməliyyat geri qaytarıla bilməz.": {
            "en": "Reject this organization's registration request? This cannot be undone.",
            "ru": "Отклонить заявку организации на регистрацию? Это действие нельзя отменить.",
            "tr": "Kuruluşun kayıt başvurusu reddedilsin mi? Bu işlem geri alınamaz.",
        },
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def has_contextless(text, msgid_esc):
    """Kontekstsiz blok varmı? (`msgid` sətrinin üstü `msgctxt` OLMAMALIDIR.)"""
    needle = f'msgid "{msgid_esc}"\n'
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx < 0:
            return False
        line_start = text.rfind("\n", 0, idx - 1) + 1
        if not text[line_start:idx].startswith("msgctxt "):
            return True
        start = idx + len(needle)


def fill(lang):
    path = po_path(lang)
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            head = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            key = f'{head}msgid "{esc(msgid)}"\n'
            if ctx and key in text:
                continue
            if not ctx and has_contextless(text, esc(msgid)):
                continue
            msgstr = msgid if lang == "az" else translations.get(lang, msgid)
            blocks.append(f'{key}msgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
