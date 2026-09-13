#!/usr/bin/env python3
"""EMSArena i18n — frontend məxfilik və cilalama (Codex audit, 2026-09-13).

Codex audit §7: «Statistik CSV əvvəlki göndəriş selector-larını ixrac edir;
düymə "Göndərişlər (CSV)" adlandırıldı». Statistika bölməsinə ikinci ixrac —
«Göstəricilər (CSV)» — əlavə olundu (`apps/accounts/views/profile/
statistics_export_metrics.py`). Bu skript həmin düymənin və CSV başlıq/bölmə
sətirlərinin msgid-lərini dörd kataloqa əlavə edir (kontekst `profile.statistics`).

⚠️ `makemessages` İŞLƏDİLMİR (o, əl ilə yazılmış blokları silir) — skript yalnız
əlavə edir və idempotentdir. TR qarşılıqları QƏSDƏN AZ mənbədən fərqlidir —
i18n qapısı `msgstr == msgid` sətrini «tərcümə olunmamış» sayır.

İstifadə:  python scripts/i18n_fill_frontend_polish_2026_09_13.py
           python manage.py compilemessages
"""

import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]

STX = "profile.statistics"

# msgid = AZ mətn; msgstr: az = msgid, digərləri lüğətdən.
ENTRIES = {
    STX: {
        # ── düymə (sections/statistics/_header_actions.html) ──
        "Göstəricilər (CSV)": {"en": "Metrics (CSV)", "ru": "Показатели (CSV)", "tr": "Göstergeler (CSV)"},
        # ── CSV başlığı (statistics_export_metrics.py) ──
        "Bölmə": {"en": "Section", "ru": "Раздел", "tr": "Bölüm"},
        "Sətir": {"en": "Row", "ru": "Строка", "tr": "Satır"},
        "Göstərici": {"en": "Metric", "ru": "Показатель", "tr": "Gösterge"},
        "Dəyər": {"en": "Value", "ru": "Значение", "tr": "Değer"},
        "Vahid": {"en": "Unit", "ru": "Единица", "tr": "Birim"},
        "Qeyd": {"en": "Note", "ru": "Примечание", "tr": "Not"},
        # ── CSV bölmə/kontekst sətirləri ──
        "Kontekst": {"en": "Context", "ru": "Контекст", "tr": "Bağlam"},
        "Profil": {"en": "Profile", "ru": "Профиль", "tr": "Profil türü"},
        "Əhatə": {"en": "Scope", "ru": "Охват", "tr": "Kapsam"},
        "Dövr": {"en": "Period", "ru": "Период", "tr": "Dönem"},
        "Əsas göstəricilər": {"en": "Key metrics", "ru": "Ключевые показатели", "tr": "Temel göstergeler"},
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
