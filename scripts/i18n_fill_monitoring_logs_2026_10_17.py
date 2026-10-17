#!/usr/bin/env python3
"""EMSArena i18n — «Sistem monitorinqi» → «Loglar» tabının xəta/boş vəziyyətləri 2026-10-17.

Sahib: «Sistem monitorinqində loglar boş göstərir». UI əvvəl Loki xətasını da, boş
nəticəni də eyni «məlumat yoxdur» ilə göstərirdi. Yeni mətnlər `monitoring.ui`
kontekstindədir və `_system_monitoring_i18n.html` JSON adasından (`logs*` açarları)
`system_monitoring_renderers.js`-ə gedir; `monitoring.alert` — yeni `LogIngestionStalled` alertinin adı. Yer tutucular `{name}` formasındadır (JS `fmt()`).

msgid AZ cümlədir → az msgstr = msgid. «Loki»/«promtail»/«HTTP» xidmət adlarıdır — tərcümə olunmur.

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir,
idempotentdir (mövcudluq `polib` ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_monitoring_logs_2026_10_17.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

UI = "monitoring.ui"
ALERT = "monitoring.alert"

# ctx → msgid → {lang: msgstr}. "az" verilməyibsə az msgstr = msgid (AZ cümlə).
ENTRIES = {
    UI: {
        "Log mənbəyinə qoşulmaq olmadı: {reason}": {
            "en": "Could not connect to the log source: {reason}",
            "ru": "Не удалось подключиться к источнику логов: {reason}",
            "tr": "Log kaynağına bağlanılamadı: {reason}",
            "de": "Verbindung zur Log-Quelle fehlgeschlagen: {reason}",
        },
        "Loki {detail} ərzində cavab vermədi": {
            "en": "Loki did not respond within {detail}",
            "ru": "Loki не ответил в течение {detail}",
            "tr": "Loki {detail} içinde yanıt vermedi",
            "de": "Loki hat nicht innerhalb von {detail} geantwortet",
        },
        "Loki xidmətinə bağlantı qurulmadı (xidmət dayanıb və ya şəbəkə əlçatmazdır)": {
            "en": "No connection to the Loki service (the service is stopped or the network is unreachable)",
            "ru": "Нет соединения со службой Loki (служба остановлена или сеть недоступна)",
            "tr": "Loki hizmetine bağlantı kurulamadı (hizmet durmuş veya ağa erişilemiyor)",
            "de": "Keine Verbindung zum Loki-Dienst (Dienst gestoppt oder Netzwerk nicht erreichbar)",
        },
        "Loki HTTP {status} xətası qaytardı": {
            "en": "Loki returned an HTTP {status} error",
            "ru": "Loki вернул ошибку HTTP {status}",
            "tr": "Loki HTTP {status} hatası döndürdü",
            "de": "Loki hat einen HTTP-{status}-Fehler zurückgegeben",
        },
        "Loki gözlənilməz cavab qaytardı": {
            "en": "Loki returned an unexpected response",
            "ru": "Loki вернул неожиданный ответ",
            "tr": "Loki beklenmeyen bir yanıt döndürdü",
            "de": "Loki hat eine unerwartete Antwort zurückgegeben",
        },
        "Log servisi müvəqqəti əlçatmazdır": {
            "en": "The log service is temporarily unavailable",
            "ru": "Служба логов временно недоступна",
            "tr": "Log hizmeti geçici olarak kullanılamıyor",
            "de": "Der Log-Dienst ist vorübergehend nicht verfügbar",
        },
        "Son {range} ərzində bu sorğuya uyğun log yoxdur": {
            "en": "No logs match this query in the last {range}",
            "ru": "За последние {range} нет логов, соответствующих этому запросу",
            "tr": "Son {range} içinde bu sorguya uyan log yok",
            "de": "In den letzten {range} gibt es keine Logs zu dieser Abfrage",
        },
        "Loki son 6 saatda heç bir konteynerdən log almayıb — problem log toplayıcıdadır (promtail), sorğuda deyil.": {
            "en": "Loki has received no logs from any container in the last 6 hours — the problem is in the log "
            "collector (promtail), not in the query.",
            "ru": "За последние 6 часов Loki не получил логов ни от одного контейнера — проблема в сборщике логов "
            "(promtail), а не в запросе.",
            "tr": "Loki son 6 saatte hiçbir konteynerden log almadı — sorun sorguda değil, log toplayıcıda (promtail).",
            "de": "Loki hat in den letzten 6 Stunden von keinem Container Logs erhalten — das Problem liegt beim "
            "Log-Sammler (promtail), nicht bei der Abfrage.",
        },
    },
    # `apps/monitoring/wording.py` — yeni `LogIngestionStalled` alertinin sadə adı.
    ALERT: {
        "Mərkəzi loglar toplanmır — «Loglar» bölməsi boş qalır": {
            "en": "Central logs are not being collected — the «Logs» section stays empty",
            "ru": "Централизованные логи не собираются — раздел «Логи» остаётся пустым",
            "tr": "Merkezî loglar toplanmıyor — «Loglar» bölümü boş kalıyor",
            "de": "Zentrale Logs werden nicht gesammelt — der Bereich «Logs» bleibt leer",
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
