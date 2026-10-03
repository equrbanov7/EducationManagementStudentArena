#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-04: sorğu kampaniyası «bağlı jurnal N / M» və hədəfsiz kampaniya xəbərdarlığı.

Əlavə olunan mətnlər:
  * `surveys.cabinet`: semestr seçimində «bağlı jurnal N / M», kartda «Bağlı jurnal», «Hədəf yoxdur»
    çipi və izah;
  * `surveys.manage`: bağlı jurnalı olmayan dövr üçün açılış mesajı.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_04_survey_targets.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


SC = "surveys.cabinet"
SM = "surveys.manage"

_CABINET = [
    _t(
        "bağlı jurnal %(closed)s / %(total)s",
        "closed journals %(closed)s / %(total)s",
        "закрытых журналов %(closed)s / %(total)s",
        "kapalı günlük %(closed)s / %(total)s",
    ),
    _t("Bağlı jurnal", "Closed journals", "Закрытые журналы", "Kapalı günlükler"),
    _t("Hədəf yoxdur", "No targets", "Нет целей", "Hedef yok"),
    _t(
        "Bu semestrin heç bir jurnalı bağlanmayıb — tələbələr sorğunu görmür. Hədəflər RİM jurnalları "
        "bağlayanda özü yaranır; sınaq deyilsə kampaniyanı bağlayın.",
        "No journal of this semester has been closed yet — students do not see the survey. Targets appear "
        "automatically when the RİM closes the journals; close the campaign unless this is a test.",
        "В этом семестре ещё не закрыт ни один журнал — студенты не видят опрос. Цели появляются "
        "автоматически, когда RİM закрывает журналы; если это не проверка, закройте кампанию.",
        "Bu dönemin hiçbir günlüğü kapatılmadı — öğrenciler anketi görmüyor. Hedefler RİM günlükleri "
        "kapattığında kendiliğinden oluşur; deneme değilse kampanyayı kapatın.",
    ),
]

_MANAGE = [
    _t(
        "Kampaniya açıldı, amma bu semestrin heç bir jurnalı bağlanmayıb — tələbələr sorğunu hələ görməyəcək. "
        "Hədəflər RİM jurnalları bağlayanda özü yaranır.",
        "The campaign is open, but no journal of this semester has been closed yet — students will not see the "
        "survey for now. Targets appear automatically when the RİM closes the journals.",
        "Кампания открыта, но в этом семестре ещё не закрыт ни один журнал — студенты пока не увидят опрос. "
        "Цели появляются автоматически, когда RİM закрывает журналы.",
        "Kampanya açıldı, ancak bu dönemin hiçbir günlüğü henüz kapatılmadı — öğrenciler anketi şimdilik "
        "görmeyecek. Hedefler RİM günlükleri kapattığında kendiliğinden oluşur.",
    ),
]

ENTRIES = {
    SC: {row["az"]: row for row in _CABINET},
    SM: {row["az"]: row for row in _MANAGE},
}

FORCE = set()


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want))
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if ((ctx, msgid) in FORCE or stale) and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
