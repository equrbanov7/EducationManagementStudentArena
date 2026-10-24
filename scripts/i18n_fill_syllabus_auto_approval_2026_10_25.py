#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-25: «Sillabus təsdiqi tələb olunur» açarı + avtomatik təsdiq mətnləri.

Mənbələr: ``core/runtime_settings_syllabus.py`` (core.runtime_settings), ``apps/syllabus/models/syllabus.py``
(syllabus.model), ``apps/syllabus/document.py`` (syllabus.document), ``apps/accounts/views/syllabus/api.py``
(accounts.syllabus).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir; sonra ``compilemessages -i .claude -i venv``.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

CR = "core.runtime_settings"
SM = "syllabus.model"
SD = "syllabus.document"
AS = "accounts.syllabus"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


ENTRIES = {
    CR: {
        "Sillabus": t("Syllabus", "Силлабус", "Müfredat belgesi (sillabus)", "Syllabus"),
        "Sillabus təsdiqi tələb olunur (kafedra müdiri)": t(
            "Syllabus approval required (head of department)",
            "Требуется утверждение силлабуса (заведующий кафедрой)",
            "Sillabus onayı gerekli (bölüm başkanı)",
            "Genehmigung des Syllabus erforderlich (Lehrstuhlleiter)",
        ),
        "Söndürülübsə (defolt) müəllim sillabusu təsdiqə göndərən kimi o avtomatik təsdiqlənir: kafedra müdirinin təsdiq növbəsində gözləyən sillabus olmur, tarixçədə «avtomatik təsdiq (sistem tənzimləməsi)» görünür. Yandırılanda əvvəlki qayda qayıdır: sillabus kafedra müdirinin təsdiqini gözləyir. Açarı dəyişmək artıq göndərilmiş sillabusların statusunu dəyişmir — söndürülü vəziyyətdə gözləyənləri toplu təsdiqləmək üçün «syllabus_auto_approve_pending» əməliyyatı var.": t(
            "When off (default), a syllabus is approved automatically the moment the teacher submits it: nothing waits in the head of department's approval queue, and the history shows “automatic approval (system setting)”. When on, the previous rule returns: the syllabus waits for the head of department's approval. Changing the switch does not change syllabuses that were already submitted — to approve those waiting while it is off there is the “syllabus_auto_approve_pending” operation.",
            "Если выключено (по умолчанию), силлабус утверждается автоматически в момент отправки преподавателем: в очереди утверждения заведующего кафедрой ничего не ждёт, в истории видно «автоматическое утверждение (системная настройка)». Если включено, возвращается прежнее правило: силлабус ждёт утверждения заведующего кафедрой. Переключение не меняет статус уже отправленных силлабусов — чтобы утвердить ожидающие при выключенном переключателе, есть операция «syllabus_auto_approve_pending».",
            "Kapalıysa (varsayılan) öğretim elemanı sillabusu onaya gönderdiği anda otomatik onaylanır: bölüm başkanının onay kuyruğunda bekleyen sillabus olmaz, geçmişte «otomatik onay (sistem ayarı)» görünür. Açıkken önceki kural geri gelir: sillabus bölüm başkanının onayını bekler. Anahtarı değiştirmek zaten gönderilmiş sillabusların durumunu değiştirmez — kapalıyken bekleyenleri toplu onaylamak için «syllabus_auto_approve_pending» işlemi vardır.",
            "Wenn aus (Standard), wird ein Syllabus automatisch genehmigt, sobald die Lehrkraft ihn einreicht: in der Genehmigungswarteschlange des Lehrstuhlleiters wartet nichts, im Verlauf steht „automatische Genehmigung (Systemeinstellung)“. Wenn an, gilt wieder die bisherige Regel: Der Syllabus wartet auf die Genehmigung des Lehrstuhlleiters. Das Umschalten ändert bereits eingereichte Syllabi nicht — um wartende bei ausgeschaltetem Schalter zu genehmigen, gibt es die Operation „syllabus_auto_approve_pending“.",
        ),
    },
    SM: {
        "Avtomatik təsdiq (sistem tənzimləməsi)": t(
            "Automatic approval (system setting)",
            "Автоматическое утверждение (системная настройка)",
            "Otomatik onay (sistem ayarı)",
            "Automatische Genehmigung (Systemeinstellung)",
        ),
    },
    SD: {
        "Təsdiq: avtomatik (sistem tənzimləməsi)": t(
            "Approval: automatic (system setting)",
            "Утверждение: автоматическое (системная настройка)",
            "Onay: otomatik (sistem ayarı)",
            "Genehmigung: automatisch (Systemeinstellung)",
        ),
    },
    AS: {
        "Sillabus göndərildi və avtomatik təsdiqləndi.": t(
            "The syllabus was submitted and approved automatically.",
            "Силлабус отправлен и автоматически утверждён.",
            "Sillabus gönderildi ve otomatik onaylandı.",
            "Der Syllabus wurde eingereicht und automatisch genehmigt.",
        ),
    },
}


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang):
    path = po_path(lang)
    if not os.path.exists(path):
        print(f"{lang}: django.po yoxdur — keçildi")
        return
    existing = {(entry.msgctxt, entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES.items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = "#, python-format\n" if "%(" in msgid else ""
            blocks.append(f'{flags}msgctxt "{esc(ctx)}"\nmsgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        fill(locale)
