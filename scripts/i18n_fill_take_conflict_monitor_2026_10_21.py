#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-21 (sahib hesabatı, zal imtahanı):

* take-exam yalançı «başqa tabda yenilənib» konfliktinin düzəlişi — yeni konflikt / «başqa tab da açıqdır»
  xəbərdarlığı və «Səhifəni yenilə» düyməsi (`django.po`, kontekst `exams.template.take_exam`;
  `apps/exams/views/student/script_data.py`, `take_exam.html`);
* zal apellyasiyasında tam ekran örtüyü (`django.po`, kontekst `appeals.template.hall_fullscreen`;
  `apps/appeals/templates/appeals/partials/_hall_fullscreen_gate.html`);
* zal monitorunun sağdakı «Qayda pozanlar» paneli — axtarış/süzgəc/sıralama/səhifələmə (`django.po`, kontekst
  `exams.final_center.violations`; `room_monitor.html`, `apps/exams/views/exam_center/room_violations.py`).
  `djangojs.po`-ya yeni mətn yoxdur — JS mətnləri serverdən (şablon / i18n JSON) alır.

msgid AZ cümlədir → az msgstr = msgid. `djangojs.po`-da msgctxt yoxdur (ctx "").

⚠️ `makemessages` İŞLƏDİLMİR — skript yalnız çatışmayan blokları əlavə edir, idempotentdir (mövcudluq `polib`
ilə yoxlanılır). Sonra `compilemessages -i .claude -i venv`.

İstifadə:  python scripts/i18n_fill_take_conflict_monitor_2026_10_21.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr", "de"]

TAKE = "exams.template.take_exam"
HALL_FS = "appeals.template.hall_fullscreen"
MONITOR = "exams.final_center.violations"


def t(en, ru, tr, de):
    return {"en": en, "ru": ru, "tr": tr, "de": de}


# ENTRIES[domen][ctx][msgid] = {lang: msgstr}
ENTRIES = {
    "django": {
        TAKE: {
            (
                "Bu imtahan başqa tabda və ya kompüterdə də yenilənib: eyni suallara fərqli cavab verilib. "
                "Digər cavablar saxlanıldı. Davam etmək üçün səhifəni yeniləyin."
            ): t(
                "This exam was also updated in another tab or on another computer: the same questions were answered "
                "differently. Your other answers were saved. Reload the page to continue.",
                "Этот экзамен также был изменён в другой вкладке или на другом компьютере: на одни и те же вопросы "
                "даны разные ответы. Остальные ответы сохранены. Обновите страницу, чтобы продолжить.",
                "Bu sınav başka bir sekmede veya bilgisayarda da güncellendi: aynı sorulara farklı cevaplar verildi. "
                "Diğer cevaplarınız kaydedildi. Devam etmek için sayfayı yenileyin.",
                "Diese Prüfung wurde auch in einem anderen Tab oder auf einem anderen Computer geändert: dieselben "
                "Fragen wurden unterschiedlich beantwortet. Ihre übrigen Antworten wurden gespeichert. Laden Sie die "
                "Seite neu, um fortzufahren.",
            ),
            (
                "Bu imtahan başqa tabda və ya kompüterdə də açıqdır. Cavablar birləşdirilir — yalnız bir tabda "
                "davam edin."
            ): t(
                "This exam is also open in another tab or on another computer. Answers are being merged — please "
                "continue in one tab only.",
                "Этот экзамен открыт также в другой вкладке или на другом компьютере. Ответы объединяются — "
                "продолжайте только в одной вкладке.",
                "Bu sınav başka bir sekmede veya bilgisayarda da açık. Cevaplar birleştiriliyor — yalnızca tek bir "
                "sekmede devam edin.",
                "Diese Prüfung ist auch in einem anderen Tab oder auf einem anderen Computer geöffnet. Die Antworten "
                "werden zusammengeführt – bitte arbeiten Sie nur in einem Tab weiter.",
            ),
            "Səhifəni yenilə": t("Reload the page", "Обновить страницу", "Sayfayı yenile", "Seite neu laden"),
            (
                "Bu imtahan artıq başqa tabda açıqdır — bu tabdan cavablar yazılmır. "
                "İmtahanı həmin tabda davam etdirin və ya onu bağlayıb bu səhifəni yeniləyin."
            ): t(
                "This exam is already open in another tab — answers are not saved from this tab. Continue the exam "
                "in that tab, or close it and reload this page.",
                "Этот экзамен уже открыт в другой вкладке — ответы из этой вкладки не сохраняются. Продолжайте "
                "экзамен в той вкладке или закройте её и обновите эту страницу.",
                "Bu sınav zaten başka bir sekmede açık — bu sekmeden cevaplar kaydedilmez. Sınava o sekmede devam "
                "edin veya onu kapatıp bu sayfayı yenileyin.",
                "Diese Prüfung ist bereits in einem anderen Tab geöffnet – Antworten aus diesem Tab werden nicht "
                "gespeichert. Setzen Sie die Prüfung in jenem Tab fort oder schließen Sie ihn und laden Sie diese "
                "Seite neu.",
            ),
        },
        HALL_FS: {
            "Apellyasiya tam ekranda verilir": t(
                "The appeal is filed in full screen",
                "Апелляция подаётся в полноэкранном режиме",
                "İtiraz tam ekranda yapılır",
                "Der Einspruch wird im Vollbildmodus eingereicht",
            ),
            (
                "İmtahan zalında apellyasiya da imtahan kimi tam ekranda doldurulur. Davam etmək üçün düyməni " "basın."
            ): t(
                "In the exam hall, the appeal is filled in full screen, just like the exam. Press the button to "
                "continue.",
                "В экзаменационном зале апелляция, как и экзамен, заполняется в полноэкранном режиме. Нажмите "
                "кнопку, чтобы продолжить.",
                "Sınav salonunda itiraz da sınav gibi tam ekranda doldurulur. Devam etmek için düğmeye basın.",
                "Im Prüfungssaal wird der Einspruch wie die Prüfung im Vollbildmodus ausgefüllt. Drücken Sie die "
                "Schaltfläche, um fortzufahren.",
            ),
            "Tam ekran rejimindən çıxdınız": t(
                "You have left full-screen mode",
                "Вы вышли из полноэкранного режима",
                "Tam ekran modundan çıktınız",
                "Sie haben den Vollbildmodus verlassen",
            ),
            "İmtahan bitib — bu, pozuntu sayılmır. Apellyasiyanı tam ekranda davam etdirin.": t(
                "The exam is over, so this is not a violation. Please continue the appeal in full screen.",
                "Экзамен окончен — это не считается нарушением. Продолжите апелляцию в полноэкранном режиме.",
                "Sınav bitti — bu bir ihlal sayılmaz. İtiraza tam ekranda devam edin.",
                "Die Prüfung ist beendet – dies gilt nicht als Verstoß. Setzen Sie den Einspruch im Vollbildmodus "
                "fort.",
            ),
            "Tam ekranda davam et": t(
                "Continue in full screen",
                "Продолжить в полноэкранном режиме",
                "Tam ekranda devam et",
                "Im Vollbildmodus fortfahren",
            ),
            "İndilik bağla": t("Close for now", "Пока закрыть", "Şimdilik kapat", "Vorerst schließen"),
        },
        MONITOR: {
            "Ad, istifadəçi adı, yer №…": t(
                "Name, username, seat no.…",
                "Имя, логин, № места…",
                "Ad, kullanıcı adı, yer no.…",
                "Name, Benutzername, Platz-Nr.…",
            ),
            "Qayda pozanlarda axtarış": t(
                "Search rule violators",
                "Поиск среди нарушителей",
                "Kural ihlal edenlerde ara",
                "Regelverstöße durchsuchen",
            ),
            "Ciddilik": t("Severity", "Серьёзность", "Ciddiyet", "Schweregrad"),
            "Hamısı": t("All", "Все", "Tümü", "Alle"),
            "Pozuntu növü": t("Violation type", "Тип нарушения", "İhlal türü", "Verstoßart"),
            "Bütün növlər": t("All types", "Все типы", "Tüm türler", "Alle Arten"),
            "Sıralama": t("Sorting", "Сортировка", "Sıralama", "Sortierung"),
            "Ciddiliyə görə": t("By severity", "По серьёзности", "Ciddiyete göre", "Nach Schweregrad"),
            "Ən yenilər": t("Most recent", "Самые новые", "En yeniler", "Neueste"),
            "Bu ekranda hələ açılmamış yeni hadisəsi olan tələbələr": t(
                "Students with new events not yet opened on this screen",
                "Студенты с новыми событиями, ещё не открытыми на этом экране",
                "Bu ekranda henüz açılmamış yeni olayları olan öğrenciler",
                "Studierende mit neuen, auf diesem Bildschirm noch nicht geöffneten Ereignissen",
            ),
            "Yalnız yenilər": t("New only", "Только новые", "Yalnızca yeniler", "Nur neue"),
            "Daha çox göstər": t("Show more", "Показать ещё", "Daha fazla göster", "Mehr anzeigen"),
            "Hamısını göstər": t("Show all", "Показать все", "Tümünü göster", "Alle anzeigen"),
            "Az göstər": t("Show less", "Показать меньше", "Daha az göster", "Weniger anzeigen"),
            "%(shown)s / %(total)s göstərilir": t(
                "Showing %(shown)s / %(total)s",
                "Показано %(shown)s / %(total)s",
                "%(shown)s / %(total)s gösteriliyor",
                "%(shown)s / %(total)s angezeigt",
            ),
            "Süzgəcə uyğun tələbə yoxdur.": t(
                "No students match the filter.",
                "Нет студентов, соответствующих фильтру.",
                "Filtreye uyan öğrenci yok.",
                "Keine Studierenden entsprechen dem Filter.",
            ),
            "Son hadisələr": t("Latest events", "Последние события", "Son olaylar", "Letzte Ereignisse"),
            "Hadisələr yüklənir…": t(
                "Loading events…", "Загрузка событий…", "Olaylar yükleniyor…", "Ereignisse werden geladen…"
            ),
            # «Bax» düyməsinin mövcud tərcüməsi ilə eyni: View / Открыть / Bak / Anzeigen.
            "Tam tarixçə və qeyd üçün «Bax» düyməsini basın.": t(
                "Press «View» for the full history and notes.",
                "Нажмите «Открыть», чтобы увидеть полную историю и заметки.",
                "Tam geçmiş ve not için «Bak» düğmesine basın.",
                "Für den vollständigen Verlauf und Notizen auf «Anzeigen» klicken.",
            ),
            "+%(count)s növ": t("+%(count)s types", "+%(count)s типов", "+%(count)s tür", "+%(count)s Arten"),
            "Son hadisə": t("Last event", "Последнее событие", "Son olay", "Letztes Ereignis"),
            "Yeni": t("New", "Новое", "Yeni", "Neu"),
        },
    },
    "djangojs": {
        "": {},
    },
}


def po_path(lang, domain):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")


def esc(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fill(lang, domain):
    path = po_path(lang, domain)
    if not os.path.exists(path):
        print(f"{lang}/{domain}: fayl yoxdur, atlandı")
        return
    existing = {(entry.msgctxt or "", entry.msgid) for entry in polib.pofile(path) if not entry.obsolete}
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    blocks, added = [], 0
    for ctx, messages in ENTRIES[domain].items():
        for msgid, translations in messages.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = msgid if lang == "az" else (translations.get(lang) or msgid)
            flags = ""
            if "%(" in msgid:
                flags = "#, python-format\n" if domain == "django" else "#, javascript-format\n"
            head = f'msgctxt "{esc(ctx)}"\n' if ctx else ""
            blocks.append(f'{flags}{head}msgid "{esc(msgid)}"\nmsgstr "{esc(msgstr)}"\n')
            added += 1

    if blocks:
        text = text.rstrip("\n") + "\n\n" + "\n".join(blocks)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    print(f"{lang}/{domain}: +{added} entry")


if __name__ == "__main__":
    for locale in LOCALES:
        for po_domain in ENTRIES:
            fill(locale, po_domain)
