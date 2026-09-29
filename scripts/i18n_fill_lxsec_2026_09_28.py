#!/usr/bin/env python3
"""EMSArena i18n — Audit 2026-09-28 remediasiyası, iş paketi LX-SEC (canlı imtahan pentest).

Əlavə olunan mətnlər:
  * `live_exam.view.message` — çıxarılmış klientin geri qoşulması (LXS-09), profil /
    ad yalnız lobbidə və kilidli lobbidə ad dondurulur (LXS-07), reaksiyalar yalnız
    lobbidə (LXS-11), AI xülasəsinə yalnız səhifənin öz sorğusu (LXS-12);
  * `live_exam.results.export` — canlı sessiya nəticələrinin CSV ixracının başlıqları.

DÜZƏLİŞ (FORCE): `live_exam.view.message` / `game_already_started` dörd dildə «Bu cəhd
artıq dayandırılıb və bərpa edilə bilməz» idi (imtahan cəhdi mesajından kopyalanıb) —
gec qoşulan tələbə və host «oyun artıq başlayıb» əvəzinə anlaşılmaz mesaj görürdü.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_lxsec_2026_09_28.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

VM = "live_exam.view.message"
EX = "live_exam.results.export"

# ctx → msgid → {az, en, ru, tr}
ENTRIES = {
    VM: {
        "game_already_started": {
            "az": "Oyun artıq başlayıb.",
            "en": "The game has already started.",
            "ru": "Игра уже началась.",
            "tr": "Oyun zaten başladı.",
        },
        "removed_by_host": {
            "az": "Müəllim səni bu oyundan çıxarıb.",
            "en": "The host removed you from this game.",
            "ru": "Ведущий удалил вас из этой игры.",
            "tr": "Öğretmen seni bu oyundan çıkardı.",
        },
        "profile_changes_lobby_only": {
            "az": "Ad və avatarı yalnız oyun başlamazdan əvvəl dəyişmək olar.",
            "en": "Nickname and avatar can only be changed before the game starts.",
            "ru": "Ник и аватар можно менять только до начала игры.",
            "tr": "Rumuz ve avatar yalnızca oyun başlamadan önce değiştirilebilir.",
        },
        "nickname_locked": {
            "az": "Lobbi kilidlənib — adı dəyişmək olmaz.",
            "en": "The lobby is locked — the nickname cannot be changed.",
            "ru": "Лобби закрыто — ник изменить нельзя.",
            "tr": "Lobi kilitli — rumuz değiştirilemez.",
        },
        "reactions_lobby_only": {
            "az": "Reaksiyalar yalnız gözləmə otağında göndərilir.",
            "en": "Reactions can only be sent in the waiting room.",
            "ru": "Реакции можно отправлять только в комнате ожидания.",
            "tr": "Tepkiler yalnızca bekleme odasında gönderilebilir.",
        },
        "ai_summary_invalid_request": {
            "az": "AI xülasəsi yalnız nəticə səhifəsindən istənilə bilər.",
            "en": "The AI summary can only be requested from the results page.",
            "ru": "ИИ-сводку можно запросить только со страницы результатов.",
            "tr": "Yapay zekâ özeti yalnızca sonuç sayfasından istenebilir.",
        },
    },
    EX: {
        "export_nickname": {"az": "Oyunçu", "en": "Player", "ru": "Игрок", "tr": "Oyuncu"},
        "export_total_score": {"az": "Ümumi bal", "en": "Total score", "ru": "Общий балл", "tr": "Toplam puan"},
        "export_question_number": {"az": "Sual №", "en": "Question #", "ru": "№ вопроса", "tr": "Soru no."},
        "export_question": {"az": "Sual", "en": "Question", "ru": "Вопрос", "tr": "Soru"},
        "export_answer": {"az": "Cavab", "en": "Answer", "ru": "Ответ", "tr": "Cevap"},
        "export_correct": {"az": "Düzgün", "en": "Correct", "ru": "Верно", "tr": "Doğru"},
        "export_points": {"az": "Bal", "en": "Points", "ru": "Баллы", "tr": "Puan"},
        "export_answer_ms": {
            "az": "Cavab müddəti (ms)",
            "en": "Answer time (ms)",
            "ru": "Время ответа (мс)",
            "tr": "Cevap süresi (ms)",
        },
        "export_yes": {"az": "Bəli", "en": "Yes", "ru": "Да", "tr": "Evet"},
        "export_no": {"az": "Xeyr", "en": "No", "ru": "Нет", "tr": "Hayır"},
    },
}

# Mövcud, lakin SƏHV tərcümə — həmişə üstələnir.
FORCE = {
    (VM, "game_already_started"),
}


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
