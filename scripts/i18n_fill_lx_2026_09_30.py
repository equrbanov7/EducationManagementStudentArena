#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-30 canlı oyun: sürpriz final, aparıcının «Yenilə»si (sahib).

Əlavə olunan mətnlər:
  * `live_exam.host_game`  — `liveExam/partials/_host_i18n.html` JSON blokunda (JS `tr()` oxuyur;
                             tərcümə yoxdursa JS-dəki Azərbaycan dilində ehtiyat mətn göstərilir):
                             son sualdan sonrakı «Nəticələr…» səhnəsi + lobbidəki «Yenilə» düyməsi;
  * `live_exam.host_lobby` — `liveExam/_host_control_bar.html` (idarə panelindəki «Yenilə»);
  * `live_exam.player`     — `liveExam/player_screen.html` JSON blokunda (telefonun «Nəticələr ekranda!»).

Hamısı `django.po`-dadır (şablon `{% trans %}`); `djangojs` kataloqu İSTİFADƏ OLUNMUR.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_lx_2026_09_30.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

G = "live_exam.host_game"
HL = "live_exam.host_lobby"
P = "live_exam.player"


def t(az, en, ru, tr):
    return {"az": az, "en": en, "ru": ru, "tr": tr}


# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    G: {
        "game_final_suspense_title": t("Nəticələr…", "The results…", "Итоги…", "Sonuçlar…"),
        "game_final_suspense_sub": t(
            "Kim qalib gəldi? Final səhnəsi başlayır!",
            "Who won? The final stage is about to begin!",
            "Кто победил? Начинается финальная сцена!",
            "Kim kazandı? Final sahnesi başlıyor!",
        ),
        "game_final_suspense_hint": t(
            "Final səhnəsini açmaq üçün «Növbəti» düyməsini basın",
            "Press “Next” to open the final stage",
            "Нажмите «Следующий», чтобы открыть финальную сцену",
            "Final sahnesini açmak için “Sonraki” düğmesine basın",
        ),
        "lobby_refresh": t("Yenilə", "Refresh", "Обновить", "Yenile"),
        "lobby_refresh_hint": t(
            "Oyunçu siyahısını serverdən yenilə",
            "Reload the player list from the server",
            "Заново загрузить список игроков с сервера",
            "Oyuncu listesini sunucudan yenile",
        ),
    },
    HL: {
        "Yenilə": t("Yenilə", "Refresh", "Обновить", "Yenile"),
        "Oyunçu siyahısını və sayını serverdən yenilə": t(
            "Oyunçu siyahısını və sayını serverdən yenilə",
            "Reload the player list and count from the server",
            "Заново загрузить список и число игроков с сервера",
            "Oyuncu listesini ve sayısını sunucudan yenile",
        ),
    },
    P: {
        "final_suspense_title": t(
            "Nəticələr ekranda!", "Results are on the big screen!", "Итоги — на большом экране!", "Sonuçlar ekranda!"
        ),
        "final_suspense_body": t(
            "Yerin final səhnəsində açılacaq — gözün böyük ekranda olsun 👀",
            "Your place will be revealed on the final stage — keep your eyes on the big screen 👀",
            "Твоё место откроется на финальной сцене — смотри на большой экран 👀",
            "Yerin final sahnesinde açıklanacak — gözün büyük ekranda olsun 👀",
        ),
    },
}

FORCE = set()


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def fill(lang):
    path = po_path(lang)
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
