#!/usr/bin/env python3
"""EMSArena i18n — «Sistem tənzimləmələri → Monitorinq» açarları + monitorinq pauzası (sahib 2026-10-21).

Mənbələr: ``core/runtime_settings_monitoring.py`` (core.runtime_settings), ``apps/monitoring/switches.py``
(monitoring.switch), ``apps/monitoring/wording.py`` (monitoring.alert — yeni alert başlıqları).

msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud msgctxt+msgid toxunulmur);
sonra `compilemessages -i .claude -i venv`.
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

RS = "core.runtime_settings"
SWITCH = "monitoring.switch"
ALERT = "monitoring.alert"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


AZ_OVERRIDES = {}

ENTRIES = {
    RS: {
        "Monitorinq": t("Monitoring", "Мониторинг", "İzleme", "Monitoring"),
        "Tətbiq daxili monitorinq («Sistem monitorinqi» səhifəsi)": t(
            "In-app monitoring (the «System monitoring» page)",
            "Мониторинг в приложении (страница «Мониторинг системы»)",
            "Uygulama içi izleme («Sistem izleme» sayfası)",
            "Monitoring in der Anwendung (Seite «Systemmonitoring»)",
        ),
        "Söndürüləndə «Sistem monitorinqi» səhifəsi «Monitorinq söndürülüb» bildirişi göstərir və "
        "Prometheus/Loki/Alertmanager-ə heç bir sorğu göndərmir; in-app insident uzlaşdırması dayanır. "
        "Alertlər (e-poçt), Watchdog və imtahan nəzarəti işləməyə davam edir. Monitorinq konteynerlərini "
        "dayandırmaq üçün «Prod host maintenance» → monitoring-pause əməliyyatı var.": t(
            "When off, the «System monitoring» page shows a «Monitoring is turned off» notice and sends no "
            "queries to Prometheus/Loki/Alertmanager; in-app incident reconciliation stops. Alerts (e-mail), "
            "the Watchdog and exam supervision keep working. To stop the monitoring containers use the "
            "«Prod host maintenance» → monitoring-pause action.",
            "Если выключено, страница «Мониторинг системы» показывает уведомление «Мониторинг выключен» и не "
            "отправляет запросов в Prometheus/Loki/Alertmanager; сверка инцидентов в приложении "
            "останавливается. Оповещения (e-mail), Watchdog и наблюдение за экзаменами продолжают работать. "
            "Чтобы остановить контейнеры мониторинга, используйте действие «Prod host maintenance» → "
            "monitoring-pause.",
            "Kapalıyken «Sistem izleme» sayfası «İzleme kapatıldı» bildirimi gösterir ve Prometheus/Loki/"
            "Alertmanager'a hiçbir sorgu göndermez; uygulama içi olay uzlaştırması durur. Uyarılar (e-posta), "
            "Watchdog ve sınav gözetimi çalışmaya devam eder. İzleme konteynerlerini durdurmak için «Prod host "
            "maintenance» → monitoring-pause işlemi vardır.",
            "Wenn deaktiviert, zeigt die Seite «Systemmonitoring» den Hinweis «Monitoring ist ausgeschaltet» und "
            "sendet keine Anfragen an Prometheus/Loki/Alertmanager; der In-App-Abgleich von Vorfällen stoppt. "
            "Alarme (E-Mail), der Watchdog und die Prüfungsaufsicht laufen weiter. Zum Anhalten der "
            "Monitoring-Container gibt es die Aktion «Prod host maintenance» → monitoring-pause.",
        ),
        "Server yüklü olanda monitorinqi avtomatik dayandır": t(
            "Pause monitoring automatically when the server is overloaded",
            "Автоматически приостанавливать мониторинг при высокой нагрузке на сервер",
            "Sunucu yüklüyken izlemeyi otomatik olarak duraklat",
            "Monitoring bei hoher Serverlast automatisch pausieren",
        ),
        "Yandırılıbsa server yükü (son 1 dəqiqənin orta yükü) aşağıdakı həddi keçəndə «Sistem "
        "monitorinqi» səhifəsinin sorğuları və in-app insident uzlaşdırması müvəqqəti dayanır; yük azalan "
        "kimi özü bərpa olunur. Alertlər bundan asılı deyil.": t(
            "When on, the «System monitoring» page queries and in-app incident reconciliation pause while the "
            "server load (1-minute load average) is above the threshold below, and resume by themselves once "
            "the load drops. Alerts do not depend on this.",
            "Если включено, запросы страницы «Мониторинг системы» и сверка инцидентов в приложении временно "
            "останавливаются, пока нагрузка на сервер (средняя за 1 минуту) выше порога ниже, и сами "
            "возобновляются, когда нагрузка снижается. Оповещения от этого не зависят.",
            "Açıksa sunucu yükü (son 1 dakikanın ortalama yükü) aşağıdaki eşiği aştığında «Sistem izleme» "
            "sayfasının sorguları ve uygulama içi olay uzlaştırması geçici olarak durur; yük azalınca kendiliğinden "
            "devam eder. Uyarılar buna bağlı değildir.",
            "Wenn aktiviert, pausieren die Abfragen der Seite «Systemmonitoring» und der In-App-Abgleich von "
            "Vorfällen, solange die Serverlast (1-Minuten-Mittel) über der unten stehenden Schwelle liegt, und "
            "laufen bei sinkender Last von selbst weiter. Alarme hängen davon nicht ab.",
        ),
        "Avtomatik dayandırma həddi (yük ÷ nüvə sayı)": t(
            "Automatic pause threshold (load ÷ number of cores)",
            "Порог автоматической паузы (нагрузка ÷ число ядер)",
            "Otomatik duraklatma eşiği (yük ÷ çekirdek sayısı)",
            "Schwelle für automatische Pause (Last ÷ Anzahl Kerne)",
        ),
        "Son 1 dəqiqənin orta yükü «bu dəyər × prosessor nüvələrinin sayı»nı keçəndə monitorinq "
        "dayandırılır. Məs. 1,5 və 10 nüvədə hədd 15-dir. Avtomatik bərpa (autoheal) yük altında "
        "restartları 2 × nüvədə dayandırır — monitorinq ondan əvvəl geri çəkilsin deyə defolt 1,5-dir.": t(
            "Monitoring pauses when the 1-minute load average exceeds «this value × number of CPU cores». E.g. "
            "1.5 with 10 cores gives a threshold of 15. Automatic recovery (autoheal) stops restarts under load "
            "at 2 × cores — the default is 1.5 so that monitoring backs off before that.",
            "Мониторинг приостанавливается, когда средняя нагрузка за 1 минуту превышает «это значение × число "
            "ядер процессора». Напр. при 1,5 и 10 ядрах порог равен 15. Автовосстановление (autoheal) под "
            "нагрузкой прекращает перезапуски при 2 × ядра — по умолчанию 1,5, чтобы мониторинг отступал раньше.",
            "Son 1 dakikanın ortalama yükü «bu değer × işlemci çekirdeği sayısı»nı aştığında izleme durdurulur. "
            "Örn. 1,5 ve 10 çekirdekte eşik 15'tir. Otomatik kurtarma (autoheal) yük altında yeniden başlatmaları "
            "2 × çekirdekte durdurur — izleme ondan önce geri çekilsin diye varsayılan 1,5'tir.",
            "Das Monitoring pausiert, wenn das 1-Minuten-Lastmittel «diesen Wert × Anzahl der CPU-Kerne» "
            "übersteigt. Z. B. ergibt 1,5 bei 10 Kernen eine Schwelle von 15. Die automatische Wiederherstellung "
            "(autoheal) stoppt Neustarts unter Last bei 2 × Kerne — der Standard ist 1,5, damit das Monitoring "
            "vorher zurücktritt.",
        ),
        "× nüvə": t("× cores", "× ядер", "× çekirdek", "× Kerne"),
        "Monitorinq məlumatının yenilənmə intervalı": t(
            "Monitoring data refresh interval",
            "Интервал обновления данных мониторинга",
            "İzleme verilerinin yenilenme aralığı",
            "Aktualisierungsintervall der Monitoringdaten",
        ),
        "Prometheus/Loki/Alertmanager cavabları bu müddət ərzində ortaq keşdən verilir — səhifəni neçə "
        "nəfər açıq saxlasa da, eyni sorğu bu intervalda bir dəfədən çox göndərilmir. Böyük dəyər yükü "
        "azaldır, qrafiklər isə bir o qədər gec yenilənir.": t(
            "Prometheus/Loki/Alertmanager answers are served from a shared cache for this long — however many "
            "people keep the page open, the same query is sent at most once per interval. A larger value "
            "lowers the load, but the charts refresh correspondingly later.",
            "Ответы Prometheus/Loki/Alertmanager в течение этого времени выдаются из общего кэша — сколько бы "
            "человек ни держали страницу открытой, один и тот же запрос отправляется не чаще раза за интервал. "
            "Большее значение снижает нагрузку, но графики обновляются соответственно позже.",
            "Prometheus/Loki/Alertmanager yanıtları bu süre boyunca ortak önbellekten verilir — sayfayı kaç kişi "
            "açık tutarsa tutsun, aynı sorgu bu aralıkta bir kereden fazla gönderilmez. Büyük değer yükü azaltır, "
            "grafikler ise o kadar geç yenilenir.",
            "Antworten von Prometheus/Loki/Alertmanager werden so lange aus einem gemeinsamen Cache geliefert — "
            "egal wie viele Personen die Seite offen halten, dieselbe Abfrage wird höchstens einmal pro Intervall "
            "gesendet. Ein größerer Wert senkt die Last, die Diagramme werden aber entsprechend später "
            "aktualisiert.",
        ),
        "saniyə": t("seconds", "секунд", "saniye", "Sekunden"),
    },
    SWITCH: {
        "Server yüklüdür (yük %(load)s > hədd %(threshold)s) — monitorinq sorğuları yük azalana qədər "
        "avtomatik dayandırılıb. Alertlər işləyir.": t(
            "The server is overloaded (load %(load)s > threshold %(threshold)s) — monitoring queries are paused "
            "automatically until the load drops. Alerts keep working.",
            "Сервер перегружен (нагрузка %(load)s > порог %(threshold)s) — запросы мониторинга автоматически "
            "приостановлены до снижения нагрузки. Оповещения работают.",
            "Sunucu yüklü (yük %(load)s > eşik %(threshold)s) — izleme sorguları yük azalana kadar otomatik "
            "olarak durduruldu. Uyarılar çalışıyor.",
            "Der Server ist überlastet (Last %(load)s > Schwelle %(threshold)s) — Monitoring-Abfragen sind bis "
            "zum Sinken der Last automatisch pausiert. Alarme laufen weiter.",
        ),
        "Monitorinq söndürülüb («Sistem tənzimləmələri → Monitorinq»). Prometheus/Loki sorğuları göndərilmir; "
        "alertlər (e-poçt) və imtahan nəzarəti işləyir.": t(
            "Monitoring is turned off («System settings → Monitoring»). No Prometheus/Loki queries are sent; "
            "alerts (e-mail) and exam supervision keep working.",
            "Мониторинг выключен («Системные настройки → Мониторинг»). Запросы к Prometheus/Loki не "
            "отправляются; оповещения (e-mail) и наблюдение за экзаменами работают.",
            "İzleme kapatıldı («Sistem ayarları → İzleme»). Prometheus/Loki sorguları gönderilmiyor; uyarılar "
            "(e-posta) ve sınav gözetimi çalışıyor.",
            "Monitoring ist ausgeschaltet («Systemeinstellungen → Monitoring»). Es werden keine Prometheus/Loki-"
            "Abfragen gesendet; Alarme (E-Mail) und die Prüfungsaufsicht laufen weiter.",
        ),
    },
    ALERT: {
        "Monitorinq konteynerləri 12 saatdan çoxdur dayandırılıb": t(
            "The monitoring containers have been paused for more than 12 hours",
            "Контейнеры мониторинга остановлены более 12 часов",
            "İzleme konteynerleri 12 saatten uzun süredir durduruldu",
            "Die Monitoring-Container sind seit über 12 Stunden pausiert",
        ),
        "Monitorinq pauzası bitib, amma pauza işarəsi qalıb — bəzi alertlər susdurulub": t(
            "The monitoring pause is over, but the pause marker remained — some alerts are silenced",
            "Пауза мониторинга закончилась, но метка паузы осталась — часть оповещений заглушена",
            "İzleme duraklatması bitti ama duraklatma işareti kaldı — bazı uyarılar susturuldu",
            "Die Monitoring-Pause ist vorbei, aber die Pausenmarkierung ist geblieben — einige Alarme sind "
            "stummgeschaltet",
        ),
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
                msgstr = AZ_OVERRIDES.get((ctx, msgid), msgid)
            else:
                msgstr = translations.get(lang) or msgid
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
