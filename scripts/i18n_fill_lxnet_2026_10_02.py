#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-02 LXNET: canlı viktorinada zəif şəbəkə (sualın gec çatması).

Əlavə olunan mətnlər:
  * `live_exam.player`: başlıqdakı bağlantı göstəricisi (yaxşı / zəif); «bərpa olunur» mövcuddur
    (`net_reconnecting`);
  * `live_exam.host_lobby.js`: müəllim panelində «N/M aldı» — sualı telefonuna alan oyunçu sayı
    (`{received}` / `{total}` yer tutucuları JS-də doldurulur, tərcümədə saxlanmalıdır);
  * `live_exam.host_lobby`: həmin sayğacın izahı (title).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_lxnet_2026_10_02.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")


def _t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


PLAYER = "live_exam.player"
HOST_JS = "live_exam.host_lobby.js"
HOST = "live_exam.host_lobby"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    PLAYER: {
        "net_good": _t("Bağlantı yaxşıdır", "Connection is good", "Соединение хорошее", "Bağlantı iyi"),
        "net_weak": _t(
            "Bağlantı zəifdir — sual bir az gec gələ bilər",
            "Weak connection — questions may arrive a little late",
            "Слабое соединение — вопрос может прийти с задержкой",
            "Bağlantı zayıf — soru biraz geç gelebilir",
        ),
    },
    HOST_JS: {
        "received_counter": _t(
            "{received}/{total} aldı",
            "{received}/{total} received",
            "получили {received}/{total}",
            "{received}/{total} aldı",
        ),
    },
    HOST: {
        "received_title": _t(
            "Cari sualı telefonuna artıq alan oyunçular (zəif internetli oyunçular gecikə bilər)",
            "Players whose phone has already received the current question (weak connections may lag)",
            "Игроки, чей телефон уже получил текущий вопрос (при слабом интернете возможна задержка)",
            "Mevcut soruyu telefonuna almış oyuncular (zayıf bağlantılılar gecikebilir)",
        ),
    },
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
