#!/usr/bin/env python3
"""EMSArena i18n — 2026-11-19: «Cari yükə bərpa et»: eyni adlı köhnə fənn sətri xəbərdarlığı.

``django`` kataloquna beş dildə;
AZ msgstr = msgid. İdempotent. İstifadə:  python scripts/i18n_add_history_restore_alias_2026_11_20.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ("az", "en", "ru", "tr", "de")
_E = "workload.history_restore"

#: (kontekst, msgid) → (en, ru, tr, de)
STRINGS = {
    (_E, "Bu jurnalın yükü eyni adlı köhnə fənn sətrindədir"): (
        "This journal's load is on a row with an older, same-named subject",
        "Нагрузка этого журнала находится в строке со старым одноимённым предметом",
        "Bu günlüğün yükü aynı adlı eski ders satırında",
        "Die Lehrlast dieses Journals steht in einer Zeile mit einem älteren, gleichnamigen Fach",
    ),
    (
        _E,
        "Yeni sətir yaradılmır (yük ikiqat sayılardı). «Yük bölgüsü»ndə həmin sətrin fənnini jurnalın fənninə dəyişin — "
        "jurnal cari yükə qayıdır, qeydlər dəyişmir.",
    ): (
        "No new row is created (the load would be counted twice). In «Load distribution», change that row's subject "
        "to the journal's subject — the journal returns to the current load and records stay unchanged.",
        "Новая строка не создаётся (нагрузка учитывалась бы дважды). В «Распределении нагрузки» замените предмет этой "
        "строки на предмет журнала — журнал вернётся в текущую нагрузку, записи не изменятся.",
        "Yeni satır oluşturulmaz (yük iki kez sayılırdı). «Yük dağılımı»nda o satırın dersini günlüğün dersiyle "
        "değiştirin — günlük mevcut yüke döner, kayıtlar değişmez.",
        "Es wird keine neue Zeile angelegt (die Last würde doppelt gezählt). Ändern Sie in der «Lastverteilung» das Fach "
        "dieser Zeile auf das Fach des Journals — das Journal kehrt in die aktuelle Last zurück, Einträge bleiben.",
    ),
}


def main():
    for lang in LOCALES:
        path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
        po = polib.pofile(path)
        existing = {(e.msgctxt or "", e.msgid) for e in po}
        added = 0
        for (ctx, msgid), (en, ru, tr, de) in STRINGS.items():
            if (ctx, msgid) in existing:
                continue
            msgstr = {"az": msgid, "en": en, "ru": ru, "tr": tr, "de": de}[lang]
            po.append(polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=msgstr))
            added += 1
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
        print(f"django/{lang}: +{added}")


if __name__ == "__main__":
    main()
