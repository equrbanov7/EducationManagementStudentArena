#!/usr/bin/env python3
"""EMSArena i18n — təsdiqlənmiş dərs yükünün redaktəsi + «Mənim dərs yüküm» birləşməsi 2026-10-15.

Sahib: «631/5K-nı birləşdir … bunları edit etmək olmur … RİM ya da kafedra müdiri edit edə bilsin,
çıxarda, əlavə edə». Əlavə olunan mətnlər:
  * ``django`` / `accounts.workload` — «Yük bölgüsü» düzəliş zolağı (`_workload_distribution.html`),
    «Mənim dərs yüküm» «Redaktə et» keçidi və sütunu (`_my_workload.html`);
  * ``django`` / `accounts.workload_overview` — ümumi baxışın kafedra sətrində «Redaktə et» (`workload_chain.py`,
    `workload/_overview_row_actions.html`);
  * ``django`` / `accounts.workload_center` — mərkəz kartında «Bölgünü redaktə et» (`_workload_center.html`);
  * ``djangojs`` (msgctxt YOX) — `workload_distribution_render.js`, `workload_distribution_amend.js`,
    `workload_my.js` mətnləri.

msgid AZ cümlədir → az msgstr = msgid. ⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları
əlavə edir, idempotentdir (mövcudluq `polib` ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_workload_edit_2026_10_15.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

WORKLOAD = "accounts.workload"
OVERVIEW = "accounts.workload_overview"
CENTER = "accounts.workload_center"

EDIT = {"en": "Edit", "ru": "Изменить", "tr": "Düzenle", "de": "Bearbeiten"}

# domen → ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    "django": {
        WORKLOAD: {
            "Redaktə": {"en": "Edit", "ru": "Редактирование", "tr": "Düzenleme", "de": "Bearbeiten"},
            "Redaktə et": EDIT,
            "Bölgü təsdiqlənib. Sətri, saatı və ya müəllimi dəyişə, fəaliyyəti çıxara, sətir əlavə edə bilərsiniz — "
            "hər dəyişiklikdə düzəliş səbəbi və qeydi soruşulur, tarixçə saxlanılır.": {
                "en": "The distribution is confirmed. You can change a row, its hours or the teacher, remove an "
                "activity or add a row — each change asks for an amendment reason and note, and the history is kept.",
                "ru": "Распределение утверждено. Можно изменить строку, часы или преподавателя, убрать вид занятий, "
                "добавить строку — при каждом изменении запрашиваются причина и примечание корректировки, история "
                "сохраняется.",
                "tr": "Dağıtım onaylandı. Satırı, saatleri veya öğretim elemanını değiştirebilir, bir etkinliği "
                "kaldırabilir, satır ekleyebilirsiniz — her değişiklikte düzeltme gerekçesi ve notu istenir, geçmiş "
                "saklanır.",
                "de": "Die Verteilung ist bestätigt. Sie können eine Zeile, Stunden oder die Lehrkraft ändern, eine "
                "Lehrform entfernen oder eine Zeile hinzufügen — bei jeder Änderung werden Korrekturgrund und Notiz "
                "abgefragt, der Verlauf bleibt erhalten.",
            },
            "Düzəliş açıqdır: dəyişikliklər müəllimə və jurnala dərhal düşür. Bitirəndə «Bölgünü təsdiqlə» ilə "
            "sənədi yenidən təsdiqləyin.": {
                "en": "An amendment is open: changes reach the teacher and the journal immediately. When you are "
                "done, confirm the document again with «Confirm distribution».",
                "ru": "Корректировка открыта: изменения сразу доходят до преподавателя и журнала. По завершении "
                "снова утвердите документ кнопкой «Утвердить распределение».",
                "tr": "Düzeltme açık: değişiklikler öğretim elemanına ve deftere hemen yansır. Bitirdiğinizde belgeyi "
                "«Dağıtımı onayla» ile yeniden onaylayın.",
                "de": "Eine Korrektur ist offen: Änderungen erreichen Lehrkraft und Journal sofort. Bestätigen Sie "
                "das Dokument danach erneut mit «Verteilung bestätigen».",
            },
        },
        OVERVIEW: {
            "Redaktə et": EDIT,
            "Əməl": {"en": "Action", "ru": "Действие", "tr": "İşlem", "de": "Aktion"},
        },
        CENTER: {
            "Bölgünü redaktə et": {
                "en": "Edit distribution",
                "ru": "Изменить распределение",
                "tr": "Dağıtımı düzenle",
                "de": "Verteilung bearbeiten",
            },
        },
    },
    "djangojs": {
        "": {
            "Redaktə et": EDIT,
            "Bölgünü redaktə et": {
                "en": "Edit assignment",
                "ru": "Изменить назначение",
                "tr": "Atamayı düzenle",
                "de": "Zuweisung bearbeiten",
            },
            "Fəaliyyəti çıxar": {
                "en": "Remove activity",
                "ru": "Убрать вид занятий",
                "tr": "Etkinliği kaldır",
                "de": "Lehrform entfernen",
            },
            "Düzəliş açıqdır": {
                "en": "Amendment open",
                "ru": "Корректировка открыта",
                "tr": "Düzeltme açık",
                "de": "Korrektur offen",
            },
            "Səbəb və qeyd məcburidir.": {
                "en": "Reason and note are required.",
                "ru": "Причина и примечание обязательны.",
                "tr": "Gerekçe ve not zorunludur.",
                "de": "Grund und Notiz sind Pflicht.",
            },
            "Bölgü yeni cəmə uyğun azaldılsın (ən son təyinatdan başlayaraq)?": {
                "en": "Reduce the assignments to the new total (starting from the latest one)?",
                "ru": "Уменьшить назначения до новой суммы (начиная с последнего)?",
                "tr": "Atamalar yeni toplama göre azaltılsın mı (en sonuncudan başlayarak)?",
                "de": "Zuweisungen auf die neue Summe kürzen (beginnend mit der neuesten)?",
            },
            "«%(activity)s» sətirdən çıxarılsın? Bu fəaliyyətin bölgüsü də silinəcək.": {
                "en": "Remove «%(activity)s» from the row? Its assignments will be deleted too.",
                "ru": "Убрать «%(activity)s» из строки? Назначения по этому виду занятий тоже будут удалены.",
                "tr": "«%(activity)s» satırdan kaldırılsın mı? Bu etkinliğin atamaları da silinecek.",
                "de": "«%(activity)s» aus der Zeile entfernen? Die Zuweisungen dieser Lehrform werden ebenfalls "
                "gelöscht.",
            },
        },
    },
}


def po_path(lang, domain):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain):
    path = po_path(lang, domain)
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES[domain].items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            if lang == "az":
                msgstr = translations.get("az", msgid)
            else:
                msgstr = translations.get(lang) or translations.get("az", msgid)
            head = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            blocks.append(f'{head}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        for name in ("django", "djangojs"):
            fill(locale, name)
