#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-08: canlı imtahan UX (müəllimin 22 nəfərlik real sessiyası).

Yeni mətnlər (AZ mənbə = msgid; en/ru/tr tərcümələr):

* L1 — lobbi siyahısı: sürüşdürmə ipucu, iştirakçı sayı;
* L2 — «Hər sual üçün vaxt» seçicisi (lobbi + idarə paneli), xəta mesajı;
* L3 — «Gecikənlər qoşula bilsin» ayarı, gec qoşulanın «növbəti sual gözlənilir» ekranı;
* L4/L5 — plitələr / yan panel (ekran oxuyucu mətnləri);
* L6 — oyun gedərkən iştirakçını çıxarmaq: siyahı çekməcəsi, təsdiq dialoqu, «çıxarıldı»;
* qoşulma / oyun səhifələrində əvvəl dil lüğətləri ilə (və ya sərt kodlanmış AZ) verilən mətnlər —
  indi gettext + pgettext kontekstləri ilə.

Kontekstlər: `live_exam.host_controls`, `live_exam.host_settings`, `live_exam.view.message`,
`live_exam.join`, `live_exam.join.js`, `live_exam.player`, `live_exam.pin_entry`, `liveExam.template.session_detail`.

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları `msgfmt` ilə yenidən qurulur.
Locale birləşmə konflikti olarsa qayda: «ours» götür, sonra fill skriptlərini yenidən işlət.
İstifadə:  python scripts/i18n_fill_2026_10_08_live_exam_ux.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

# (kontekst, az) → (en, ru, tr)
ROWS = {
    "live_exam.host_controls": {
        "Hər sual üçün vaxt": ("Time per question", "Время на вопрос", "Soru başına süre"),
        "Standart · {seconds} san": (
            "Default · {seconds} s",
            "По умолчанию · {seconds} с",
            "Varsayılan · {seconds} sn",
        ),
        "{seconds} san": ("{seconds} s", "{seconds} с", "{seconds} sn"),
        "Digər ({min}–{max} san)": ("Custom ({min}–{max} s)", "Другое ({min}–{max} с)", "Özel ({min}–{max} sn)"),
        "Tətbiq et": ("Apply", "Применить", "Uygula"),
        "Dəyişiklik növbəti sualdan tətbiq olunur.": (
            "The change applies from the next question.",
            "Изменение вступит в силу со следующего вопроса.",
            "Değişiklik bir sonraki sorudan itibaren uygulanır.",
        ),
        "Hər sual bu qədər vaxt gedəcək.": (
            "Every question will run for this long.",
            "Каждый вопрос будет длиться столько.",
            "Her soru bu kadar sürecek.",
        ),
        "Standart: sualın öz vaxtı, yoxdursa imtahanın vaxtı.": (
            "Default: the question's own time, otherwise the exam's time.",
            "По умолчанию: время самого вопроса, иначе время экзамена.",
            "Varsayılan: sorunun kendi süresi, yoksa sınavın süresi.",
        ),
        "{min}–{max} saniyə arası rəqəm yazın": (
            "Enter a number between {min} and {max} seconds",
            "Введите число от {min} до {max} секунд",
            "{min}–{max} saniye arasında bir sayı girin",
        ),
        "Vaxt saxlanmadı. Yenidən cəhd edin.": (
            "The time was not saved. Please try again.",
            "Время не сохранено. Попробуйте ещё раз.",
            "Süre kaydedilmedi. Lütfen tekrar deneyin.",
        ),
        "Hər sual üçün vaxt: {value}": (
            "Time per question: {value}",
            "Время на вопрос: {value}",
            "Soru başına süre: {value}",
        ),
    },
    "live_exam.host_settings": {
        "Sual vaxtı 5–300 saniyə olmalıdır.": (
            "The question time must be 5–300 seconds.",
            "Время вопроса должно быть от 5 до 300 секунд.",
            "Soru süresi 5–300 saniye olmalıdır.",
        ),
    },
}

#: Bu skriptin öz kontekstləri — dəyər həmişə buradakı ilə sinxronlanır (identity düzəlişləri).
FORCE = {"live_exam.host_controls"}


def _value(lang, az, row):
    return az if lang == "az" else row[LANGS.index(lang) - 1]


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ROWS.items():
        for msgid, row in items.items():
            want = _value(lang, msgid, row)
            entry = index.get((ctx, msgid))
            if entry is None:
                po.append(polib.POEntry(msgctxt=ctx, msgid=msgid, msgstr=want))
                added += 1
            elif entry.msgstr != want and (
                not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete or ctx in FORCE
            ):
                entry.msgstr, entry.obsolete = want, False
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
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
