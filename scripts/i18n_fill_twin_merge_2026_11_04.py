#!/usr/bin/env python3
"""EMSArena i18n — fənn birləşdirməsində əkiz jurnal / qiymətsiz qeydiyyat həlləri (K2/K3) 2026-11-04.

Əlavə olunan mətnlər (``django`` domeni, `registrar.subject_merge`): `subject_merge_conflicts.py`-ın iki yeni
«Həll olunur» mesajı. msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız
çatışmayan blokları əlavə edir, idempotentdir. Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_twin_merge_2026_11_04.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

MERGE = "registrar.subject_merge"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    MERGE: {
        "%(period)s · %(group)s: ləğv olunmuş BOŞ əkiz jurnal silinir (tam snapshot audit-də, geri qaytarmada eyni id ilə bərpa olunur); bağlı imtahanlar saxlanılan jurnala keçir.": t(
            "%(period)s · %(group)s: the cancelled EMPTY twin journal is deleted (full snapshot in the audit, restored "
            "with the same id on undo); linked exams move to the kept journal.",
            "%(period)s · %(group)s: отменённый ПУСТОЙ журнал-двойник удаляется (полный снимок в аудите, при отмене "
            "восстанавливается с тем же id); связанные экзамены переходят в сохраняемый журнал.",
            "%(period)s · %(group)s: iptal edilmiş BOŞ ikiz yoklama defteri silinir (tam anlık görüntü denetimde, geri "
            "almada aynı id ile geri yüklenir); bağlı sınavlar korunan deftere geçer.",
            "%(period)s · %(group)s: Das stornierte LEERE Zwillingsjournal wird gelöscht (vollständiger Snapshot im "
            "Audit, beim Rückgängigmachen mit derselben ID wiederhergestellt); verknüpfte Prüfungen wechseln ins "
            "beibehaltene Journal.",
        ),
        "%(student)s · %(period)s: hər iki fənn üzrə qeydiyyat var — qiymətsiz təkrar qeydiyyat bağlanır (dropped), qiymətli qeydiyyat qalır.": t(
            "%(student)s · %(period)s: enrolled under both subjects — the ungraded duplicate enrollment is closed "
            "(dropped), the graded one stays.",
            "%(student)s · %(period)s: есть запись по обеим дисциплинам — запись без оценок закрывается (dropped), "
            "запись с оценками остаётся.",
            "%(student)s · %(period)s: her iki ders için kayıt var — notsuz yinelenen kayıt kapatılır (dropped), notlu "
            "kayıt kalır.",
            "%(student)s · %(period)s: Einschreibung unter beiden Fächern — die unbewertete doppelte Einschreibung wird "
            "geschlossen (dropped), die bewertete bleibt.",
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
