#!/usr/bin/env python3
"""EMSArena i18n — dublikat fənlərin köklü həlli (sahib 2026-11-11): K4 «passiv dublikat jurnal arxiv kartda qalır»
mesajı (`registrar.subject_merge`) və kataloq formunun «kod QKU-N olmalıdır» imtinası (`accounts.catalog`).

msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir. Sonra `.mo` faylları `msgfmt` ilə yenilənir.

İstifadə:  python scripts/i18n_fill_duplicate_subjects_2026_11_11.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

MERGE = "registrar.subject_merge"
CATALOG = "accounts.catalog"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    MERGE: {
        "%(period)s · %(group)s: birləşdirilmiş (passiv) dublikat jurnal arxivlənən fənn kartında tarixçə kimi qalır — xanaları əsas jurnala kopyalanıb.": t(
            "%(period)s · %(group)s: the merged (inactive) duplicate journal stays on the archived subject card as "
            "history — its cells were copied to the main journal.",
            "%(period)s · %(group)s: объединённый (неактивный) журнал-дубликат остаётся на архивируемой карточке "
            "дисциплины как история — его ячейки скопированы в основной журнал.",
            "%(period)s · %(group)s: birleştirilmiş (pasif) yinelenen yoklama defteri arşivlenen ders kartında geçmiş "
            "olarak kalır — hücreleri ana deftere kopyalandı.",
            "%(period)s · %(group)s: Das zusammengeführte (inaktive) doppelte Journal bleibt als Verlauf auf der "
            "archivierten Fachkarte — seine Zellen wurden ins Hauptjournal kopiert.",
        ),
    },
    CATALOG: {
        "Fənn kodu QKU-N formasında olmalıdır. Növbəti boş kod: %(code)s.": t(
            "The subject code must have the form QKU-N. Next free code: %(code)s.",
            "Код дисциплины должен иметь вид QKU-N. Следующий свободный код: %(code)s.",
            "Ders kodu QKU-N biçiminde olmalıdır. Sıradaki boş kod: %(code)s.",
            "Der Fachcode muss die Form QKU-N haben. Nächster freier Code: %(code)s.",
        ),
    },
}


def po_path(lang, domain="django"):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain="django"):
    path = po_path(lang, domain)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else translations[lang]
            flag = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flag}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
