#!/usr/bin/env python3
"""EMSArena i18n — «İmtahanlarım» zibil qutusu alt-görünüşü (`w3myexams`, 2026-09-14).

Sahib: «zibil qutusu yerini düzəlt, daha yaxşı formada». Zibil qutusu artıq
bölmənin alt-görünüşüdür (`?exam_view=trash`); iki yeni mətn
(`profile.my_exams.trash` konteksti): başlıqdakı sayğaclı ikon düyməsinin
ekran-oxuyucu etiketi və boş vəziyyətin izahı. Qalan mətnlər mövcud
`exams.template.deleted_exams` / `profile.my_exams` msgid-lərindən təkrar
istifadə olunur.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir və
idempotentdir. TR qarşılıqları QƏSDƏN AZ mənbədən fərqlidir (i18n qapısı
`msgstr == msgid` sətrini «tərcümə olunmamış» sayır).

İstifadə:  python scripts/i18n_fill_w3myexams_2026_09_14.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

CTX = "profile.my_exams.trash"

ENTRIES = {
    CTX: {
        "silinmiş imtahan": {
            "en": "deleted exams",
            "ru": "удалённых экзаменов",
            "tr": "silinmiş sınav",
        },
        "Sildiyiniz imtahanlar burada saxlanılır: nəticələri itmir və istənilən vaxt bərpa edə bilərsiniz.": {
            "en": "Exams you delete are kept here: their results are not lost and you can restore them at any time.",
            "ru": "Удалённые экзамены хранятся здесь: их результаты не теряются, и вы можете восстановить их в любой момент.",
            "tr": "Sildiğiniz sınavlar burada saklanır: sonuçları kaybolmaz ve istediğiniz zaman geri yükleyebilirsiniz.",
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
