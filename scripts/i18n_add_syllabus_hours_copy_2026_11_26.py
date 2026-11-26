#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-26: «Kopyala və uyğunlaşdır» — dərs saatları fərqlidirsə xəbərdarlıq + cədvəlin uyğunlaşması.

Mətnlər ``apps/accounts/views/syllabus/copy_fit_context.py``-dadır (dialoqun JSON-u serverdə tərcümə olunur, JS-də
yeni mətn yoxdur).  ``django`` kataloquna (``accounts.syllabus``) beş dildə əlavə edir; AZ msgstr = msgid.
İdempotent (mövcud kontekst + msgid ötürülür).
İstifadə:  python scripts/i18n_add_syllabus_hours_copy_2026_11_26.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_S = "accounts.syllabus"

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    ("django", _S, "Mənbə: %(source)s · Bu jurnal: %(target)s"): (
        "Source: %(source)s · This journal: %(target)s",
        "Источник: %(source)s · Этот журнал: %(target)s",
        "Kaynak: %(source)s · Bu yoklama defteri: %(target)s",
        "Quelle: %(source)s · Dieses Journal: %(target)s",
    ),
    ("django", _S, "%(hours)s saat (%(rows)s həftə)"): (
        "%(hours)s hours (%(rows)s weeks)",
        "%(hours)s ч. (недель: %(rows)s)",
        "%(hours)s saat (%(rows)s hafta)",
        "%(hours)s Stunden (%(rows)s Wochen)",
    ),
    ("django", _S, "saat məlum deyil (%(rows)s həftə)"): (
        "hours unknown (%(rows)s weeks)",
        "часы неизвестны (недель: %(rows)s)",
        "saat bilinmiyor (%(rows)s hafta)",
        "Stunden unbekannt (%(rows)s Wochen)",
    ),
    ("django", _S, "%(hours)s saat (%(rows)s sətir)"): (
        "%(hours)s hours (%(rows)s rows)",
        "%(hours)s ч. (строк: %(rows)s)",
        "%(hours)s saat (%(rows)s satır)",
        "%(hours)s Stunden (%(rows)s Zeilen)",
    ),
    ("django", _S, "saat məlum deyil"): (
        "hours unknown",
        "часы неизвестны",
        "saat bilinmiyor",
        "Stunden unbekannt",
    ),
    ("django", _S, "Dərs saatları fərqlidir"): (
        "Lesson hours differ",
        "Учебные часы различаются",
        "Ders saatleri farklı",
        "Die Unterrichtsstunden unterscheiden sich",
    ),
    ("django", _S, "Mənbənin dərs saatı məlum deyil"): (
        "The source's lesson hours are unknown",
        "Учебные часы источника неизвестны",
        "Kaynağın ders saatleri bilinmiyor",
        "Die Unterrichtsstunden der Quelle sind unbekannt",
    ),
    (
        "django",
        _S,
        "Kopyalananda qaralama bu jurnalın saatını alır, həftəlik plan %(rows)s sətrə gətirilir: sondan %(count)s sətir "
        "kəsiləcək.",
    ): (
        "When copied, the draft takes this journal's hours and the weekly plan is fitted to %(rows)s rows: "
        "%(count)s rows will be cut from the end.",
        "При копировании черновик получает часы этого журнала, недельный план приводится к %(rows)s строкам: "
        "с конца будет удалено строк: %(count)s.",
        "Kopyalandığında taslak bu defterin saatlerini alır, haftalık plan %(rows)s satıra getirilir: sondan "
        "%(count)s satır kesilecek.",
        "Beim Kopieren übernimmt der Entwurf die Stunden dieses Journals, der Wochenplan wird auf %(rows)s Zeilen "
        "gebracht: %(count)s Zeilen werden am Ende entfernt.",
    ),
    (
        "django",
        _S,
        "Kopyalananda qaralama bu jurnalın saatını alır, həftəlik plan %(rows)s sətrə gətirilir: %(count)s boş sətir "
        "əlavə olunacaq.",
    ): (
        "When copied, the draft takes this journal's hours and the weekly plan is fitted to %(rows)s rows: "
        "%(count)s empty rows will be added.",
        "При копировании черновик получает часы этого журнала, недельный план приводится к %(rows)s строкам: "
        "будет добавлено пустых строк: %(count)s.",
        "Kopyalandığında taslak bu defterin saatlerini alır, haftalık plan %(rows)s satıra getirilir: %(count)s boş "
        "satır eklenecek.",
        "Beim Kopieren übernimmt der Entwurf die Stunden dieses Journals, der Wochenplan wird auf %(rows)s Zeilen "
        "gebracht: %(count)s leere Zeilen werden hinzugefügt.",
    ),
    (
        "django",
        _S,
        "Kopyalananda qaralama bu jurnalın saatını alır; sətir sayı eynidir (%(rows)s) — saatlar bu jurnalın planına "
        "görə yenidən bölünəcək.",
    ): (
        "When copied, the draft takes this journal's hours; the number of rows is the same (%(rows)s) — the hours "
        "will be redistributed according to this journal's plan.",
        "При копировании черновик получает часы этого журнала; число строк то же (%(rows)s) — часы будут "
        "перераспределены по плану этого журнала.",
        "Kopyalandığında taslak bu defterin saatlerini alır; satır sayısı aynı (%(rows)s) — saatler bu defterin "
        "planına göre yeniden dağıtılacak.",
        "Beim Kopieren übernimmt der Entwurf die Stunden dieses Journals; die Zeilenzahl bleibt gleich (%(rows)s) — "
        "die Stunden werden nach dem Plan dieses Journals neu verteilt.",
    ),
    (
        "django",
        _S,
        "Bu jurnalın rəsmi dərs saatı tapılmadı — həftəlik plan olduğu kimi köçürülür, saatı redaktorda seçin.",
    ): (
        "This journal's official lesson hours were not found — the weekly plan is copied as is; choose the hours "
        "in the editor.",
        "Официальные учебные часы этого журнала не найдены — недельный план копируется как есть, выберите часы "
        "в редакторе.",
        "Bu defterin resmi ders saatleri bulunamadı — haftalık plan olduğu gibi kopyalanır, saatleri düzenleyicide "
        "seçin.",
        "Die offiziellen Unterrichtsstunden dieses Journals wurden nicht gefunden — der Wochenplan wird unverändert "
        "kopiert; wählen Sie die Stunden im Editor.",
    ),
    ("django", _S, "Bəli, uyğunlaşdırıb kopyala"): (
        "Yes, fit and copy",
        "Да, скопировать с подгонкой",
        "Evet, uyarlayarak kopyala",
        "Ja, anpassen und kopieren",
    ),
    ("django", _S, "Davam etmək üçün düyməni bir daha basın."): (
        "Press the button once more to continue.",
        "Чтобы продолжить, нажмите кнопку ещё раз.",
        "Devam etmek için düğmeye bir kez daha basın.",
        "Drücken Sie die Schaltfläche noch einmal, um fortzufahren.",
    ),
}


def main():
    for domain in ("django",):
        for lang in LOCALES:
            path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")
            po = polib.pofile(path)
            existing = {(e.msgctxt, e.msgid) for e in po}
            added = 0
            for (dom, ctx, msgid), (en, ru, tr, de) in STRINGS.items():
                if dom != domain or (ctx, msgid) in existing:
                    continue
                msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
                flags = ["python-format"] if "%(" in msgid else []
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr, flags=flags))
                added += 1
            po.save(path)
            subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
            print(f"{domain}/{lang}: +{added}")


if __name__ == "__main__":
    main()
