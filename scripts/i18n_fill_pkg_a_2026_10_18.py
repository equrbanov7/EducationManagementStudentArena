#!/usr/bin/env python3
"""EMSArena i18n — Paket A (tələbə nəticə ekranları redizaynı, 2026-10-18).

«Nəticələrim», «Təyin olunmuş tapşırıqlar», imtahan nəticəsi, «Mənim cavablarım», tələbə jurnalı
və ortaq status kataloqunun (`core/ui/status_catalog.py`) yeni ailələri.
msgid AZ cümlədir → az msgstr = msgid. İdempotentdir (mövcud (ctx, msgid) cütü toxunulmur);
sonra `compilemessages -i .claude -i venv`. Bu skripti orkestrator İŞƏ SALIR (paralel agentlər).
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

ST = "ui.status"
MR = "profile.results.ui"
TA = "profile.assigned_tasks.ui"
SB = "ui.score_breakdown"
XH = "exams.student_history"
RJ = "registrar.journal"

ENTRIES = {
    ST: {
        "Qiymətləndirilib": {"en": "Graded", "ru": "Оценено", "tr": "Değerlendirildi", "de": "Bewertet"},
        "Gözləmədə": {"en": "Pending", "ru": "В ожидании", "tr": "Beklemede", "de": "Ausstehend"},
        "Təqdim edilib": {"en": "Submitted", "ru": "Отправлено", "tr": "Gönderildi", "de": "Eingereicht"},
        "İmtahandan çıxarılıb": {
            "en": "Removed from exam",
            "ru": "Удалён с экзамена",
            "tr": "Sınavdan çıkarıldı",
            "de": "Von der Prüfung ausgeschlossen",
        },
        "Təhvil verilib": {"en": "Handed in", "ru": "Сдано", "tr": "Teslim edildi", "de": "Abgegeben"},
        "Yoxlanılır": {"en": "Under review", "ru": "На проверке", "tr": "İnceleniyor", "de": "Wird geprüft"},
        "Müddəti keçib": {"en": "Time expired", "ru": "Время истекло", "tr": "Süre doldu", "de": "Zeit abgelaufen"},
        "Gizlidir": {"en": "Hidden", "ru": "Скрыто", "tr": "Gizli", "de": "Verborgen"},
        "Gözləyir": {"en": "Waiting", "ru": "Ожидает", "tr": "Bekliyor", "de": "Wartet"},
        "Keçdi": {"en": "Passed", "ru": "Сдал", "tr": "Geçti", "de": "Bestanden"},
        "Davam edir": {"en": "In progress", "ru": "Продолжается", "tr": "Devam ediyor", "de": "Läuft"},
        "Kəsildi": {"en": "Failed", "ru": "Не сдал", "tr": "Kaldı", "de": "Nicht bestanden"},
        "Kəsilir": {"en": "Barred", "ru": "Не допущен", "tr": "Kalıyor", "de": "Nicht zugelassen"},
        "Nəticə yazılmayıb": {
            "en": "No result recorded",
            "ru": "Результат не записан",
            "tr": "Sonuç girilmedi",
            "de": "Kein Ergebnis erfasst",
        },
        "Aktiv": {"en": "Active", "ru": "Активно", "tr": "Aktif", "de": "Aktiv"},
        "Bağlı": {"en": "Closed", "ru": "Закрыто", "tr": "Kapalı", "de": "Geschlossen"},
    },
    MR: {
        "Nəticə növü": {"en": "Result type", "ru": "Тип результата", "tr": "Sonuç türü", "de": "Ergebnisart"},
        "Axtarış": {"en": "Search", "ru": "Поиск", "tr": "Arama", "de": "Suche"},
        "Apellyasiya: %(status)s": {
            "en": "Appeal: %(status)s",
            "ru": "Апелляция: %(status)s",
            "tr": "İtiraz: %(status)s",
            "de": "Einspruch: %(status)s",
        },
    },
    TA: {
        "Tapşırıq növü": {"en": "Task type", "ru": "Тип задания", "tr": "Görev türü", "de": "Aufgabentyp"},
    },
    SB: {
        "Final imtahan": {
            "en": "Final exam",
            "ru": "Финальный экзамен",
            "tr": "Final sınavı",
            "de": "Abschlussprüfung",
        },
    },
    XH: {
        "Maksimum bal": {
            "en": "Maximum score",
            "ru": "Максимальный балл",
            "tr": "En yüksek puan",
            "de": "Höchstpunktzahl",
        },
        "İmtahan vəziyyəti": {
            "en": "Exam status",
            "ru": "Статус экзамена",
            "tr": "Sınav durumu",
            "de": "Prüfungsstatus",
        },
        "Bitib": {"en": "Ended", "ru": "Завершён", "tr": "Bitti", "de": "Beendet"},
        "Aktiv": {"en": "Active", "ru": "Активен", "tr": "Aktif", "de": "Aktiv"},
        "Passiv": {"en": "Inactive", "ru": "Неактивен", "tr": "Pasif", "de": "Inaktiv"},
        "Geri": {"en": "Back", "ru": "Назад", "tr": "Geri", "de": "Zurück"},
        "%(count)s sual": {
            "en": "%(count)s questions",
            "ru": "%(count)s вопр.",
            "tr": "%(count)s soru",
            "de": "%(count)s Fragen",
        },
    },
    RJ: {
        "Status nişanları": {
            "en": "Status badges",
            "ru": "Значки статуса",
            "tr": "Durum rozetleri",
            "de": "Statusabzeichen",
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
