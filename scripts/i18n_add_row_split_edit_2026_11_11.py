#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-11: «Yük bölgüsü» sətir bölgüsü (mühazirə → mühazirə + seminar) mesajları.

Sahib: «Tədqiqat analitikası 45 saatlıq fəndir — 30 saat mühazirə, 15 saat seminar. Bunu fixləyə bilmir».
Server (``django``, kontekst ``workload``) və JS (``djangojs``, kontekstsiz) kataloqlarına beş dildə əlavə edir;
AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_row_split_edit_2026_11_11.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_W = "workload"

#: (domen, kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    ("django", _W, "Vakant"): ("Vacant", "Вакансия", "Boş", "Unbesetzt"),
    ("django", _W, "%(teacher)s %(old)s → %(new)s s"): (
        "%(teacher)s %(old)s → %(new)s h",
        "%(teacher)s %(old)s → %(new)s ч",
        "%(teacher)s %(old)s → %(new)s sa",
        "%(teacher)s %(old)s → %(new)s Std.",
    ),
    ("django", _W, "%(teacher)s %(old)s s silinəcək"): (
        "%(teacher)s %(old)s h will be removed",
        "%(teacher)s %(old)s ч будет удалено",
        "%(teacher)s %(old)s sa silinecek",
        "%(teacher)s %(old)s Std. werden entfernt",
    ),
    (
        "django",
        _W,
        "«%(activity)s» cəmi %(total)s saata endirilir, amma bu fəaliyyətdə artıq %(assigned)s saat bölünüb "
        "(%(listed)s). Bölgü avtomatik azaldılsa: %(changes)s. Başqa bölgünü azaltmaq istəyirsinizsə, əvvəlcə kartda "
        "onun ✎ düyməsi ilə saatını dəyişin, sonra sətri yenidən saxlayın.",
    ): (
        "The “%(activity)s” total is being lowered to %(total)s hours, but %(assigned)s hours of it are already "
        "assigned (%(listed)s). If the assignment is reduced automatically: %(changes)s. To reduce a different "
        "assignment instead, first change its hours with its ✎ button on the card, then save the row again.",
        "Итог «%(activity)s» снижается до %(total)s ч, но по этому виду уже распределено %(assigned)s ч "
        "(%(listed)s). При автоматическом уменьшении: %(changes)s. Чтобы уменьшить другое распределение, сначала "
        "измените его часы кнопкой ✎ на карточке, затем сохраните строку снова.",
        "«%(activity)s» toplamı %(total)s saate düşürülüyor, ancak bu etkinlikte zaten %(assigned)s saat dağıtılmış "
        "(%(listed)s). Dağıtım otomatik azaltılırsa: %(changes)s. Başka bir dağıtımı azaltmak istiyorsanız, önce "
        "kartta onun ✎ düğmesiyle saatini değiştirin, sonra satırı yeniden kaydedin.",
        "Die Summe „%(activity)s“ wird auf %(total)s Std. gesenkt, aber davon sind bereits %(assigned)s Std. "
        "verteilt (%(listed)s). Bei automatischer Kürzung: %(changes)s. Um eine andere Zuteilung zu kürzen, ändern "
        "Sie zuerst deren Stunden mit ihrer ✎-Schaltfläche auf der Karte und speichern Sie die Zeile dann erneut.",
    ),
    (
        "django",
        _W,
        "«%(activity)s» cəmi %(total)s saatdır, digər bölgülərdə %(used)s saat var — bu bölgüyə ən çox "
        "%(available)s saat yazmaq olar (siz %(hours)s yazdınız). Daha çox lazımdırsa, əvvəlcə sətrin "
        "«%(activity)s (cəmi)» saatını «Redaktə» ilə artırın və ya digər bölgünü azaldın.",
    ): (
        "The “%(activity)s” total is %(total)s hours and other assignments hold %(used)s hours — this assignment "
        "can have at most %(available)s hours (you entered %(hours)s). If you need more, first raise the row's "
        "“%(activity)s (total)” with “Edit”, or reduce the other assignment.",
        "Итог «%(activity)s» — %(total)s ч, в других распределениях %(used)s ч — этому распределению можно "
        "задать не более %(available)s ч (вы ввели %(hours)s). Если нужно больше, сначала увеличьте «%(activity)s "
        "(итого)» строки через «Редактировать» или уменьшите другое распределение.",
        "«%(activity)s» toplamı %(total)s saat, diğer dağıtımlarda %(used)s saat var — bu dağıtıma en fazla "
        "%(available)s saat yazılabilir (siz %(hours)s yazdınız). Daha fazlası gerekiyorsa, önce satırın "
        "«%(activity)s (toplam)» saatini «Düzenle» ile artırın veya diğer dağıtımı azaltın.",
        "Die Summe „%(activity)s“ beträgt %(total)s Std., andere Zuteilungen haben %(used)s Std. — diese "
        "Zuteilung kann höchstens %(available)s Std. erhalten (Sie haben %(hours)s eingegeben). Wenn mehr nötig "
        "ist, erhöhen Sie zuerst „%(activity)s (gesamt)“ der Zeile über „Bearbeiten“ oder kürzen Sie die andere "
        "Zuteilung.",
    ),
    (
        "django",
        _W,
        "Bir axında qrupların mühazirə saatı eyni olmalıdır, burada fərqlidir: %(hours)s. Əvvəlcə «Tapşırıq "
        "sətirləri»ndə hər sətri «Redaktə» ilə düzəldin (məs. 45 saatlıq fənn: «Mühazirə» 30, «Seminar» 15), "
        "sonra axınları birləşdirin.",
    ): (
        "All groups in one stream must have the same lecture hours; here they differ: %(hours)s. First fix each "
        "row under “Task rows” with “Edit” (e.g. a 45-hour course: “Lecture” 30, “Seminar” 15), then merge the "
        "streams.",
        "У всех групп одного потока часы лекций должны совпадать, здесь они разные: %(hours)s. Сначала исправьте "
        "каждую строку в «Строках задания» через «Редактировать» (напр. курс на 45 ч: «Лекция» 30, «Семинар» 15), "
        "затем объедините потоки.",
        "Bir akıştaki grupların teorik ders saatleri aynı olmalıdır, burada farklı: %(hours)s. Önce «Görev "
        "satırları»nda her satırı «Düzenle» ile düzeltin (örn. 45 saatlik ders: «Teorik» 30, «Seminer» 15), sonra "
        "akışları birleştirin.",
        "Alle Gruppen eines Stroms müssen dieselben Vorlesungsstunden haben, hier unterscheiden sie sich: "
        "%(hours)s. Korrigieren Sie zuerst jede Zeile unter „Auftragszeilen“ mit „Bearbeiten“ (z. B. 45-Stunden-"
        "Fach: „Vorlesung“ 30, „Seminar“ 15) und führen Sie dann die Ströme zusammen.",
    ),
    ("djangojs", None, "Razısınızsa, eyni düyməni yenidən basın — bölgü yuxarıdakı kimi azaldılacaq."): (
        "If you agree, press the same button again — the assignment will be reduced as described above.",
        "Если согласны, нажмите ту же кнопку ещё раз — распределение будет уменьшено, как описано выше.",
        "Kabul ediyorsanız aynı düğmeye tekrar basın — dağıtım yukarıdaki gibi azaltılacak.",
        "Wenn Sie einverstanden sind, drücken Sie dieselbe Schaltfläche erneut — die Zuteilung wird wie oben "
        "beschrieben gekürzt.",
    ),
    (
        "djangojs",
        None,
        "Mühazirə saatları fərqlidir: %(list)s — bir axında eyni olmalıdır. Əvvəlcə sətirləri «Redaktə» ilə "
        "düzəldin.",
    ): (
        "Lecture hours differ: %(list)s — they must be equal within one stream. First fix the rows with “Edit”.",
        "Часы лекций различаются: %(list)s — в одном потоке они должны совпадать. Сначала исправьте строки через "
        "«Редактировать».",
        "Teorik ders saatleri farklı: %(list)s — bir akışta aynı olmalıdır. Önce satırları «Düzenle» ile düzeltin.",
        "Die Vorlesungsstunden unterscheiden sich: %(list)s — innerhalb eines Stroms müssen sie gleich sein. "
        "Korrigieren Sie zuerst die Zeilen mit „Bearbeiten“.",
    ),
    (
        "djangojs",
        None,
        "Sətrin cəmindən çox saat bölünüb: %(groups)s. Saatı azaldın və ya əvvəlcə sətrin cəmini «Tapşırıq "
        "sətirləri» → «Redaktə» ilə artırın.",
    ): (
        "More hours assigned than the row total: %(groups)s. Reduce the hours or first raise the row total via "
        "“Task rows” → “Edit”.",
        "Распределено больше часов, чем итог строки: %(groups)s. Уменьшите часы или сначала увеличьте итог строки "
        "через «Строки задания» → «Редактировать».",
        "Satır toplamından fazla saat dağıtılmış: %(groups)s. Saati azaltın veya önce satır toplamını «Görev "
        "satırları» → «Düzenle» ile artırın.",
        "Mehr Stunden verteilt als die Zeilensumme: %(groups)s. Kürzen Sie die Stunden oder erhöhen Sie zuerst die "
        "Zeilensumme über „Auftragszeilen“ → „Bearbeiten“.",
    ),
}


def main():
    for domain in ("django", "djangojs"):
        for lang in LOCALES:
            path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", f"{domain}.po")
            po = polib.pofile(path)
            existing = {(e.msgctxt, e.msgid) for e in po}
            added = 0
            for (dom, ctx, msgid), (en, ru, tr, de) in STRINGS.items():
                if dom != domain or (ctx, msgid) in existing:
                    continue
                msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr))
                added += 1
            po.save(path)
            subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
            print(f"{domain}/{lang}: +{added}")


if __name__ == "__main__":
    main()
