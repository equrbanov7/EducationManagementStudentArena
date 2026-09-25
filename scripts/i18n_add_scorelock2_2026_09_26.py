#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-26 (ikinci mərhələ): bitmiş dövrdə İmtahan Mərkəzi boş
balı yaza bilir (60 gündən köhnə dövrdə sənədlə), yazılmış balı dəyişmək yalnız
RİM rəhbərinin düzəliş rejimindədir — banner / dialoq / sətir xətası mətnləri.
Dörd kataloqa msgctxt+msgid əlavə edir; AZ msgstr = msgid. İdempotent.
İstifadə:  python scripts/i18n_add_scorelock2_2026_09_26.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr")

_R = "registrar.exam_score_entry"

STRINGS = {
    (_R, "Bitmiş dövr — yazılmış ballar kilidlidir"): (
        "Finished period — recorded scores are locked",
        "Завершённый период — записанные баллы заблокированы",
        "Tamamlanmış dönem — yazılmış puanlar kilitli",
    ),
    (
        _R,
        "Bitmiş dövrdə yazılmış balı dəyişmək yalnız RİM rəhbəri tərəfindən düzəliş rejimində mümkündür.",
    ): (
        "In a finished period a recorded score can be changed only by the head of the RIM in correction mode.",
        "В завершённом периоде записанный балл может изменить только руководитель RİM в режиме исправления.",
        "Tamamlanmış dönemde yazılmış puanı yalnızca RİM başkanı düzeltme modunda değiştirebilir.",
    ),
    (
        _R,
        "Boş balı yazmaq olar (%(days)s gündən köhnə dövrdə sənəd məcburidir); yazılmış balı dəyişmək yalnız RİM rəhbəri tərəfindən düzəliş rejimində mümkündür.",
    ): (
        "Empty scores can be entered (a document is mandatory for periods older than %(days)s days); a recorded score can be changed only by the head of the RIM in correction mode.",
        "Пустой балл можно записать (для периода старше %(days)s дней документ обязателен); записанный балл может изменить только руководитель RİM в режиме исправления.",
        "Boş puan yazılabilir (%(days)s günden eski dönemde belge zorunludur); yazılmış puanı yalnızca RİM başkanı düzeltme modunda değiştirebilir.",
    ),
    (
        _R,
        "Bu dövr %(days)s gündən çox əvvəl bağlanıb: boş balı yalnız təqdimat əsasında (səbəb, qeyd, skan) yazmaq olar. Yazılmış balı dəyişmək yalnız RİM rəhbəri tərəfindən düzəliş rejimində mümkündür.",
    ): (
        "This period closed more than %(days)s days ago: empty scores can be entered only based on a submission (reason, note, scan). A recorded score can be changed only by the head of the RIM in correction mode.",
        "Этот период закрыт более %(days)s дней назад: пустой балл можно записать только на основании представления (причина, примечание, скан). Записанный балл может изменить только руководитель RİM в режиме исправления.",
        "Bu dönem %(days)s günden daha önce kapandı: boş puan yalnızca başvuru üzerine (gerekçe, not, tarama) yazılabilir. Yazılmış puanı yalnızca RİM başkanı düzeltme modunda değiştirebilir.",
    ),
    (
        _R,
        "Bu dövr %(days)s gündən çox əvvəl bağlanıb — köhnə nəticənin köçürülməsi təqdimat əsasındadır: səbəb, qeyd və skan edilmiş sənəd üçü də məcburidir.",
    ): (
        "This period closed more than %(days)s days ago — transferring an old result requires a submission: a reason, a note and a scanned document are all mandatory.",
        "Этот период закрыт более %(days)s дней назад — перенос старого результата делается на основании представления: причина, примечание и скан документа обязательны.",
        "Bu dönem %(days)s günden daha önce kapandı — eski sonucun aktarımı başvuruya dayanır: gerekçe, not ve taranmış belgenin üçü de zorunludur.",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt, e.msgid): e for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr}[lang]
            entry = polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=msgstr)
            if "%(" in msgid:
                entry.flags.append("python-format")
            po.append(entry)
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"{lang}: +{added}")


if __name__ == "__main__":
    main()
